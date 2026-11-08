import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.metrics import compute_bootstrap_ci, compute_wilcoxon_paired
from app.db.models import ExperimentModel, ResultPerQueryModel
from app.db.session import get_db
from app.schemas import CompareRequest, CompareResponse, MetricDeltaItem

router = APIRouter(prefix="/compare", tags=["compare"])

METRIC_KEYS = [
    ("hit_at_k", "Hit@k"),
    ("reciprocal_rank", "MRR"),
    ("precision_at_k", "Precision@k"),
    ("recall_at_k", "Recall@k"),
    ("context_precision", "Context Precision"),
    ("context_recall", "Context Recall"),
]


@router.post("", response_model=CompareResponse)
def compare_runs(payload: CompareRequest, db: Session = Depends(get_db)) -> CompareResponse:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == payload.experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{payload.experiment_id}' not found")

    base_key = f"{payload.base_config}__{payload.base_model}"
    target_key = f"{payload.target_config}__{payload.target_model}"

    base_results = (
        db.query(ResultPerQueryModel)
        .filter(
            ResultPerQueryModel.experiment_id == payload.experiment_id,
            ResultPerQueryModel.run_key == base_key,
        )
        .all()
    )
    target_results = (
        db.query(ResultPerQueryModel)
        .filter(
            ResultPerQueryModel.experiment_id == payload.experiment_id,
            ResultPerQueryModel.run_key == target_key,
        )
        .all()
    )

    if not base_results:
        raise HTTPException(status_code=404, detail=f"Base run '{base_key}' not found in experiment")
    if not target_results:
        raise HTTPException(status_code=404, detail=f"Target run '{target_key}' not found in experiment")

    # Map by question_id
    base_map = {r.question_id: r for r in base_results}
    target_map = {r.question_id: r for r in target_results}
    common_qids = sorted(list(set(base_map.keys()) & set(target_map.keys())))

    if not common_qids:
        raise HTTPException(status_code=400, detail="No matching questions between base and target runs")

    metric_items: list[MetricDeltaItem] = []
    wins = 0
    losses = 0
    ties = 0

    for attr, display_name in METRIC_KEYS:
        b_vals = np.array([getattr(base_map[qid], attr, 0.0) for qid in common_qids], dtype=float)
        t_vals = np.array([getattr(target_map[qid], attr, 0.0) for qid in common_qids], dtype=float)
        deltas = t_vals - b_vals

        b_mean = float(np.mean(b_vals))
        t_mean = float(np.mean(t_vals))
        delta_mean, ci_lo, ci_hi = compute_bootstrap_ci(deltas.tolist())

        p_res = compute_wilcoxon_paired(b_vals, t_vals)
        p_val = p_res.p_value if hasattr(p_res, "p_value") else float(p_res)
        sig = bool(p_val < 0.05)

        metric_items.append(
            MetricDeltaItem(
                metric=display_name,
                base_mean=round(b_mean, 4),
                target_mean=round(t_mean, 4),
                delta=round(delta_mean, 4),
                delta_ci_lower=round(ci_lo, 4),
                delta_ci_upper=round(ci_hi, 4),
                p_value=round(p_val, 4),
                statistically_significant=sig,
            )
        )

        if attr == "hit_at_k":
            for d in deltas:
                if d > 0:
                    wins += 1
                elif d < 0:
                    losses += 1
                else:
                    ties += 1

    all_zero_diffs = all(item.delta == 0.0 and item.p_value == 1.0 for item in metric_items)
    zero_note = "All paired differences are zero (p = 1.0; identical performance on evaluated queries)." if all_zero_diffs else None

    return CompareResponse(
        experiment_id=payload.experiment_id,
        unverified_included=exp.has_unverified,
        has_unverified=exp.has_unverified,
        verified_questions_count=exp.verified_questions_count or 0,
        unverified_questions_count=exp.unverified_questions_count or 0,
        base_label=base_key,
        target_label=target_key,
        metrics=metric_items,
        win_loss_tie={"wins": wins, "losses": losses, "ties": ties},
        note=zero_note,
    )
