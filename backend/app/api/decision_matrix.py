from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models import ExperimentModel, ResultSummaryModel
from app.db.session import get_db
from app.schemas import (
    DecisionMatrixPreset,
    DecisionMatrixRankItem,
    DecisionMatrixRequest,
    DecisionMatrixWeights,
)

router = APIRouter(prefix="/decision-matrix", tags=["decision-matrix"])

DECISION_PRESETS = [
    DecisionMatrixPreset(
        id="accuracy_first",
        name="Accuracy first",
        description="Prioritizes maximum retrieval accuracy, MRR, and context precision.",
        weights=DecisionMatrixWeights(
            hit_at_k=0.35,
            mrr=0.30,
            context_precision=0.20,
            context_recall=0.15,
            latency=0.00,
            index_size=0.00,
            cost=0.00,
        ),
    ),
    DecisionMatrixPreset(
        id="low_latency",
        name="Low latency",
        description="Prioritizes sub-millisecond retrieval latency for real-time serving.",
        weights=DecisionMatrixWeights(
            hit_at_k=0.15,
            mrr=0.15,
            context_precision=0.10,
            context_recall=0.10,
            latency=0.35,
            index_size=0.15,
            cost=0.00,
        ),
    ),
    DecisionMatrixPreset(
        id="constrained_hardware",
        name="Constrained hardware",
        description="Minimizes index memory footprint and storage overhead on resource-limited hosts.",
        weights=DecisionMatrixWeights(
            hit_at_k=0.20,
            mrr=0.15,
            context_precision=0.10,
            context_recall=0.10,
            latency=0.15,
            index_size=0.20,
            cost=0.10,
        ),
    ),
    DecisionMatrixPreset(
        id="balanced",
        name="Balanced",
        description="Even balance across retrieval quality, latency, and index efficiency.",
        weights=DecisionMatrixWeights(
            hit_at_k=0.25,
            mrr=0.20,
            context_precision=0.15,
            context_recall=0.15,
            latency=0.10,
            index_size=0.05,
            cost=0.10,
        ),
    ),
]


@router.get("/presets", response_model=list[DecisionMatrixPreset])
def get_decision_presets() -> list[DecisionMatrixPreset]:
    return DECISION_PRESETS


@router.post("", response_model=list[DecisionMatrixRankItem])
def compute_decision_matrix(
    payload: DecisionMatrixRequest,
    db: Session = Depends(get_db),
) -> list[DecisionMatrixRankItem]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == payload.experiment_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{payload.experiment_id}' not found")

    summaries = (
        db.query(ResultSummaryModel)
        .filter(ResultSummaryModel.experiment_id == payload.experiment_id)
        .all()
    )
    # Filter out random baseline
    summaries = [s for s in summaries if s.model != "none"]

    if not summaries:
        raise HTTPException(status_code=400, detail="No evaluation summaries found for this experiment")

    # Check if groundedness was evaluated; if not, renormalise by setting its weight to 0
    has_groundedness = any(s.groundedness_score is not None for s in summaries)
    groundedness_weight = payload.weights.groundedness if has_groundedness else 0.0

    # Metrics to normalize
    criteria: dict[str, tuple[bool, float]] = {
        "hit_at_k": (True, payload.weights.hit_at_k),
        "mrr": (True, payload.weights.mrr),
        "context_precision": (True, payload.weights.context_precision),
        "context_recall": (True, payload.weights.context_recall),
        "mean_latency_ms": (False, payload.weights.latency),
        "index_size_mb": (False, payload.weights.index_size),
    }
    if has_groundedness and groundedness_weight > 0:
        criteria["groundedness_score"] = (True, groundedness_weight)

    # Min and Max per criterion
    min_max: dict[str, tuple[float, float]] = {}
    for crit, (is_pos, w) in criteria.items():
        vals = [float(getattr(s, crit, 0.0) or 0.0) for s in summaries]
        min_max[crit] = (min(vals), max(vals))

    total_weight = sum(w for is_pos, w in criteria.values())
    if total_weight <= 0:
        total_weight = 1.0

    scored_items: list[tuple[float, ResultSummaryModel, dict[str, float], dict[str, float]]] = []

    for s in summaries:
        subscores: dict[str, float] = {}
        raw_vals: dict[str, float] = {}
        total_score = 0.0

        for crit, (is_pos, weight) in criteria.items():
            val = float(getattr(s, crit, 0.0) or 0.0)
            raw_vals[crit] = val
            c_min, c_max = min_max[crit]

            if c_max == c_min:
                norm = 1.0
            elif is_pos:
                norm = (val - c_min) / (c_max - c_min)
            else:
                norm = (c_max - val) / (c_max - c_min)

            subscores[crit] = round(norm, 4)
            total_score += weight * norm

        final_utility = total_score / total_weight
        scored_items.append((final_utility, s, subscores, raw_vals))

    # Sort descending
    scored_items.sort(key=lambda x: x[0], reverse=True)

    ranks: list[DecisionMatrixRankItem] = []
    for rank, (score, s, subs, raws) in enumerate(scored_items, start=1):
        ranks.append(
            DecisionMatrixRankItem(
                rank=rank,
                config=s.config,
                model=s.model,
                total_utility_score=round(score, 4),
                subscores=subs,
                raw_metrics=raws,
            )
        )

    return ranks
