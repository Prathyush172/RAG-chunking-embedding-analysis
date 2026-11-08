import csv
import json
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from app.db.models import ExperimentModel, ResultSummaryModel, ResultPerQueryModel

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")


def sync_disk_results_to_db(db: Session) -> None:
    """
    On app startup:
    1. Mark any experiments left in 'running' state as 'interrupted'.
    2. Scan results/ for completed run directories and import any that are missing from SQLite.
    """
    # 1. Mark interrupted
    running_exps = db.query(ExperimentModel).filter(ExperimentModel.status == "running").all()
    for exp in running_exps:
        exp.status = "interrupted"
        exp.error = "Interrupted by server restart"
    if running_exps:
        db.commit()

    # 2. Scan disk runs
    if not RESULTS_DIR.exists():
        return

    for run_dir in RESULTS_DIR.iterdir():
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue

        manifest_file = run_dir / "manifest.json"
        summary_file = run_dir / "summary.csv"
        per_query_file = run_dir / "per_query.csv"

        if not (manifest_file.exists() and summary_file.exists()):
            continue

        run_id = run_dir.name
        existing = db.query(ExperimentModel).filter(ExperimentModel.id == run_id).first()
        if existing:
            continue

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            exp = ExperimentModel(
                id=run_id,
                name=run_id,
                preset=manifest.get("preset", "custom"),
                config_json=json.dumps(manifest),
                status="completed",
                verified_only=manifest.get("unverified_questions_included", False) is False,
                verified_questions_count=manifest.get("verified_questions_count", 0),
                unverified_questions_count=manifest.get("unverified_questions_count", 0),
                has_unverified=manifest.get("unverified_questions_included", True),
            )
            db.add(exp)
            db.flush()

            # Read summary.csv
            with open(summary_file, "r", encoding="utf-8") as f:
                lines = [line for line in f if not line.startswith("#")]
                reader = csv.DictReader(lines)
                for row in reader:
                    config = row.get("config", "")
                    model = row.get("model", "")
                    run_key = f"{config}__{model}"
                    summary = ResultSummaryModel(
                        experiment_id=run_id,
                        run_key=run_key,
                        config=config,
                        model=model,
                        hit_at_k=float(row.get("hit_at_k", 0.0)),
                        hit_ci_lower=float(row.get("hit_ci_lower", 0.0)),
                        hit_ci_upper=float(row.get("hit_ci_upper", 0.0)),
                        mrr=float(row.get("mrr", 0.0)),
                        mrr_ci_lower=float(row.get("mrr_ci_lower", 0.0)),
                        mrr_ci_upper=float(row.get("mrr_ci_upper", 0.0)),
                        precision_at_k=float(row.get("precision_at_k", 0.0)),
                        precision_ci_lower=float(row.get("precision_ci_lower", 0.0)),
                        precision_ci_upper=float(row.get("precision_ci_upper", 0.0)),
                        recall_at_k=float(row.get("recall_at_k", 0.0)),
                        recall_ci_lower=float(row.get("recall_ci_lower", 0.0)),
                        recall_ci_upper=float(row.get("recall_ci_upper", 0.0)),
                        context_precision=float(row.get("context_precision", 0.0)),
                        context_precision_ci_lower=float(row.get("context_precision_ci_lower", 0.0)),
                        context_precision_ci_upper=float(row.get("context_precision_ci_upper", 0.0)),
                        context_recall=float(row.get("context_recall", 0.0)),
                        context_recall_ci_lower=float(row.get("context_recall_ci_lower", 0.0)),
                        context_recall_ci_upper=float(row.get("context_recall_ci_upper", 0.0)),
                        truncation_rate=float(row.get("truncation_rate", 0.0)),
                        mean_latency_ms=float(row.get("mean_latency_ms", 0.0)),
                        chunk_count=int(float(row.get("chunk_count", 0))),
                        avg_tokens=float(row.get("avg_tokens", 0.0)),
                        index_size_mb=float(row.get("index_size_mb", 0.0)),
                        groundedness_score=float(row.get("groundedness_score")) if row.get("groundedness_score") else None,
                        cost_usd=float(row.get("cost_usd")) if row.get("cost_usd") else None,
                    )
                    db.add(summary)

            # Read per_query.csv if exists
            if per_query_file.exists():
                with open(per_query_file, "r", encoding="utf-8") as f:
                    lines = [line for line in f if not line.startswith("#")]
                    reader = csv.DictReader(lines)
                    for row in reader:
                        config = row.get("config", "")
                        model = row.get("model", "")
                        run_key = f"{config}__{model}"
                        pq = ResultPerQueryModel(
                            experiment_id=run_id,
                            run_key=run_key,
                            question_id=row.get("question_id", ""),
                            doc_id=row.get("doc_id", ""),
                            hit_at_k=float(row.get("hit_at_k", 0.0)),
                            reciprocal_rank=float(row.get("reciprocal_rank", 0.0)),
                            precision_at_k=float(row.get("precision_at_k", 0.0)),
                            recall_at_k=float(row.get("recall_at_k", 0.0)),
                            context_precision=float(row.get("context_precision", 0.0)),
                            context_recall=float(row.get("context_recall", 0.0)),
                            all_evidence_hit=row.get("all_evidence_hit", "False").lower() in ("true", "1"),
                            retrieved_chunk_ids=row.get("retrieved_chunk_ids", "[]"),
                            retrieved_scores=row.get("retrieved_scores", "[]"),
                            latency_ms=float(row.get("latency_ms", 0.0)),
                        )
                        db.add(pq)

            db.commit()
            logger.info("Imported historical run %s from disk", run_id)
        except Exception as e:
            db.rollback()
            logger.error("Failed to import historical run %s: %s", run_id, e)
