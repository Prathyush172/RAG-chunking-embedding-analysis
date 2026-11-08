import collections
import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.evaluation import load_questions
from app.core.jobs import QUESTIONS_FILE
from app.db.models import (
    ExperimentModel,
    ResultPerQueryModel,
    ResultSummaryModel,
)
from app.db.session import get_db
from app.schemas import (
    HeatmapResponse,
    ParetoPoint,
    ResultPerQueryItem,
    ResultSummaryItem,
    ResultSummaryResponse,
)

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{exp_id}/summary", response_model=ResultSummaryResponse)
def get_experiment_summary(exp_id: str, db: Session = Depends(get_db)) -> ResultSummaryResponse:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    summaries = db.query(ResultSummaryModel).filter(ResultSummaryModel.experiment_id == exp_id).all()
    rows = [
        ResultSummaryItem(
            config=s.config,
            model=s.model,
            hit_at_k=s.hit_at_k,
            hit_ci_lower=s.hit_ci_lower,
            hit_ci_upper=s.hit_ci_upper,
            mrr=s.mrr,
            mrr_ci_lower=s.mrr_ci_lower,
            mrr_ci_upper=s.mrr_ci_upper,
            precision_at_k=s.precision_at_k,
            precision_ci_lower=s.precision_ci_lower,
            precision_ci_upper=s.precision_ci_upper,
            recall_at_k=s.recall_at_k,
            recall_ci_lower=s.recall_ci_lower,
            recall_ci_upper=s.recall_ci_upper,
            context_precision=s.context_precision,
            context_precision_ci_lower=s.context_precision_ci_lower,
            context_precision_ci_upper=s.context_precision_ci_upper,
            context_recall=s.context_recall,
            context_recall_ci_lower=s.context_recall_ci_lower,
            context_recall_ci_upper=s.context_recall_ci_upper,
            truncation_rate=s.truncation_rate,
            mean_latency_ms=s.mean_latency_ms,
            chunk_count=s.chunk_count,
            avg_tokens=s.avg_tokens,
            index_size_mb=s.index_size_mb,
            groundedness_score=s.groundedness_score,
            cost_usd=s.cost_usd,
        )
        for s in summaries
    ]

    notice = "NOTICE: UNVERIFIED QUESTIONS INCLUDED IN THIS RUN" if exp.has_unverified else None

    return ResultSummaryResponse(
        experiment_id=exp_id,
        unverified_included=exp.has_unverified,
        has_unverified=exp.has_unverified,
        verified_questions_count=exp.verified_questions_count or 0,
        unverified_questions_count=exp.unverified_questions_count or 0,
        notice=notice,
        rows=rows,
    )


@router.get("/{exp_id}/per-query", response_model=list[ResultPerQueryItem])
def get_experiment_per_query(
    exp_id: str,
    config: str | None = Query(None),
    model: str | None = Query(None),
    doc_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[ResultPerQueryItem]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    query = db.query(ResultPerQueryModel).filter(ResultPerQueryModel.experiment_id == exp_id)
    if doc_id:
        query = query.filter(ResultPerQueryModel.doc_id == doc_id)

    results = query.all()
    out = []
    for r in results:
        cfg, mdl = r.run_key.split("__", 1) if "__" in r.run_key else (r.run_key, "")
        if config and cfg != config:
            continue
        if model and mdl != model:
            continue
        out.append(
            ResultPerQueryItem(
                question_id=r.question_id,
                doc_id=r.doc_id,
                config=cfg,
                model=mdl,
                hit_at_k=r.hit_at_k,
                reciprocal_rank=r.reciprocal_rank,
                precision_at_k=r.precision_at_k,
                recall_at_k=r.recall_at_k,
                context_precision=r.context_precision,
                context_recall=r.context_recall,
                all_evidence_hit=r.all_evidence_hit,
                retrieved_chunk_ids=json.loads(r.retrieved_chunk_ids or "[]"),
                retrieved_scores=json.loads(r.retrieved_scores or "[]"),
                latency_ms=r.latency_ms,
            )
        )
    return out


@router.get("/{exp_id}/per-doc")
def get_experiment_per_doc(exp_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    pqs = db.query(ResultPerQueryModel).filter(ResultPerQueryModel.experiment_id == exp_id).all()
    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in pqs:
        grouped[p.doc_id][p.run_key].append(p)

    out = {}
    for doc_id, runs_dict in grouped.items():
        out[doc_id] = {}
        for r_key, items in runs_dict.items():
            cfg, mdl = r_key.split("__", 1) if "__" in r_key else (r_key, "")
            out[doc_id][r_key] = {
                "config": cfg,
                "model": mdl,
                "sample_count": len(items),
                "hit_at_k": sum(x.hit_at_k for x in items) / len(items),
                "mrr": sum(x.reciprocal_rank for x in items) / len(items),
                "precision_at_k": sum(x.precision_at_k for x in items) / len(items),
                "recall_at_k": sum(x.recall_at_k for x in items) / len(items),
                "context_precision": sum(x.context_precision for x in items) / len(items),
                "context_recall": sum(x.context_recall for x in items) / len(items),
            }
    return out


@router.get("/{exp_id}/questions/{qid}")
def inspect_question_across_runs(
    exp_id: str,
    qid: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    pqs = (
        db.query(ResultPerQueryModel)
        .filter(ResultPerQueryModel.experiment_id == exp_id, ResultPerQueryModel.question_id == qid)
        .all()
    )
    if not pqs:
        raise HTTPException(status_code=404, detail=f"No results for question '{qid}' in experiment '{exp_id}'")

    all_questions = {q.id: q for q in load_questions(QUESTIONS_FILE)}
    q_obj = all_questions.get(qid)

    runs_info = []
    for p in pqs:
        cfg, mdl = p.run_key.split("__", 1) if "__" in p.run_key else (p.run_key, "")
        runs_info.append({
            "run_key": p.run_key,
            "config": cfg,
            "model": mdl,
            "hit_at_k": p.hit_at_k,
            "reciprocal_rank": p.reciprocal_rank,
            "precision_at_k": p.precision_at_k,
            "recall_at_k": p.recall_at_k,
            "context_precision": p.context_precision,
            "context_recall": p.context_recall,
            "all_evidence_hit": p.all_evidence_hit,
            "retrieved_chunk_ids": json.loads(p.retrieved_chunk_ids or "[]"),
            "retrieved_scores": json.loads(p.retrieved_scores or "[]"),
        })

    return {
        "question_id": qid,
        "question": q_obj.question if q_obj else "",
        "doc_id": q_obj.doc_id if q_obj else "",
        "section": q_obj.section if q_obj else "",
        "evidence": [e.to_dict() for e in q_obj.evidence] if q_obj else [],
        "runs": runs_info,
    }


@router.get("/{exp_id}/pareto", response_model=list[ParetoPoint])
def get_pareto_points(exp_id: str, db: Session = Depends(get_db)) -> list[ParetoPoint]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    summaries = db.query(ResultSummaryModel).filter(ResultSummaryModel.experiment_id == exp_id).all()
    return [
        ParetoPoint(
            config=s.config,
            model=s.model,
            hit_at_k=s.hit_at_k,
            mrr=s.mrr,
            mean_latency_ms=s.mean_latency_ms,
            index_size_mb=s.index_size_mb,
            avg_tokens=s.avg_tokens,
            chunk_count=s.chunk_count,
        )
        for s in summaries
        if s.model != "none"  # Exclude random baseline from pareto
    ]


@router.get("/{exp_id}/heatmap", response_model=HeatmapResponse)
def get_heatmap(
    exp_id: str,
    metric: str = Query("hit_at_k", description="hit_at_k, mrr, precision_at_k, recall_at_k, context_precision, context_recall"),
    db: Session = Depends(get_db),
) -> HeatmapResponse:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    summaries = db.query(ResultSummaryModel).filter(ResultSummaryModel.experiment_id == exp_id).all()
    matrix: dict[str, dict[str, float]] = collections.defaultdict(dict)
    strategies: set[str] = set()
    models: set[str] = set()

    for s in summaries:
        if s.model == "none":
            continue
        val = getattr(s, metric, 0.0)
        matrix[s.config][s.model] = round(val, 4)
        strategies.add(s.config)
        models.add(s.model)

    return HeatmapResponse(
        metric=metric,
        strategies=sorted(list(strategies)),
        models=sorted(list(models)),
        matrix=matrix,
    )
