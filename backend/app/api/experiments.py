import datetime
import json
import shutil
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.evaluation import load_questions
from app.core.jobs import job_runner, RESULTS_DIR, QUESTIONS_FILE
from app.db.models import ExperimentModel, ExperimentRunModel
from app.db.session import get_db
from app.schemas import (
    ExperimentCreateRequest,
    ExperimentResponse,
    ExperimentRunResponse,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentResponse, status_code=201)
def create_experiment(
    payload: ExperimentCreateRequest,
    db: Session = Depends(get_db),
) -> ExperimentResponse:
    # Check verified questions if verified_only requested
    all_questions = load_questions(QUESTIONS_FILE)
    verified_count = sum(1 for q in all_questions if q.verified)

    if payload.verified_only and verified_count == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Conflict: 'verified_only' was set to true, but there are 0 human-verified questions "
                "in data/eval/questions.json. Human review must verify at least one question before "
                "running with verified_only=true."
            ),
        )

    run_id = f"run_{payload.preset or 'custom'}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    exp_name = payload.name or run_id

    config_dict = {
        "preset": payload.preset,
        "configs": payload.configs,
        "models": payload.models,
        "k": payload.k,
        "verified_only": payload.verified_only,
        "llm_judge": payload.llm_judge,
    }

    exp = ExperimentModel(
        id=run_id,
        name=exp_name,
        preset=payload.preset,
        config_json=json.dumps(config_dict),
        status="queued",
        verified_only=payload.verified_only,
        verified_questions_count=verified_count,
        unverified_questions_count=len(all_questions) - verified_count,
        has_unverified=not payload.verified_only,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)

    # Launch background job
    job_runner.start_experiment(
        experiment_id=run_id,
        preset=payload.preset,
        configs=payload.configs,
        models=payload.models,
        k=payload.k,
        verified_only=payload.verified_only,
        resume=False,
    )

    return _to_experiment_response(exp)


@router.get("", response_model=list[ExperimentResponse])
def list_experiments(db: Session = Depends(get_db)) -> list[ExperimentResponse]:
    exps = db.query(ExperimentModel).order_by(ExperimentModel.created_at.desc()).all()
    return [_to_experiment_response(e) for e in exps]


@router.get("/{exp_id}", response_model=ExperimentResponse)
def get_experiment(exp_id: str, db: Session = Depends(get_db)) -> ExperimentResponse:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")
    return _to_experiment_response(exp)


@router.get("/{exp_id}/events")
def stream_experiment_events(exp_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    return StreamingResponse(
        job_runner.subscribe_events(exp_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{exp_id}/log")
def get_experiment_log(
    exp_id: str,
    tail: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")
    lines = job_runner.get_logs(exp_id, tail=tail)
    return {"experiment_id": exp_id, "lines": lines}


@router.post("/{exp_id}/cancel")
def cancel_experiment(exp_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    if exp.status not in ("running", "queued"):
        return {"message": f"Experiment '{exp_id}' is not currently running (status: {exp.status})"}

    job_runner.cancel(exp_id)
    exp.status = "cancelled"
    db.commit()
    return {"message": f"Cancellation requested for experiment '{exp_id}'"}


@router.post("/{exp_id}/resume", response_model=ExperimentResponse)
def resume_experiment(exp_id: str, db: Session = Depends(get_db)) -> ExperimentResponse:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    if exp.status in ("running", "completed"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resume experiment '{exp_id}' because it is already {exp.status}",
        )

    config_dict = json.loads(exp.config_json) if exp.config_json else {}

    job_runner.start_experiment(
        experiment_id=exp_id,
        preset=config_dict.get("preset"),
        configs=config_dict.get("configs"),
        models=config_dict.get("models"),
        k=config_dict.get("k", 5),
        verified_only=config_dict.get("verified_only", False),
        resume=True,
    )

    exp.status = "running"
    db.commit()
    db.refresh(exp)
    return _to_experiment_response(exp)


@router.delete("/{exp_id}")
def delete_experiment(exp_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    # Cancel if running
    if exp.status == "running":
        job_runner.cancel(exp_id)

    db.delete(exp)
    db.commit()

    # Delete disk artifacts
    exp_dir = RESULTS_DIR / exp_id
    if exp_dir.exists():
        shutil.rmtree(exp_dir, ignore_errors=True)

    return {"message": f"Experiment '{exp_id}' and all associated artifacts deleted"}


def _to_experiment_response(exp: ExperimentModel) -> ExperimentResponse:
    return ExperimentResponse(
        id=exp.id,
        name=exp.name,
        preset=exp.preset,
        status=exp.status,
        created_at=exp.created_at,
        started_at=exp.started_at,
        finished_at=exp.finished_at,
        error=exp.error,
        verified_only=exp.verified_only,
        verified_questions_count=exp.verified_questions_count,
        unverified_questions_count=exp.unverified_questions_count,
        has_unverified=exp.has_unverified,
        runs=[
            ExperimentRunResponse(
                id=r.id,
                chunk_config=r.chunk_config,
                model_id=r.model_id,
                status=r.status,
                stage=r.stage,
                progress=r.progress,
                message=r.message,
            )
            for r in (exp.runs or [])
        ],
    )
