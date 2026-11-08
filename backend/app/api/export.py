import csv
import io
import json
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.jobs import RESULTS_DIR
from app.db.models import ExperimentModel, ResultSummaryModel
from app.db.session import get_db

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/{exp_id}/summary")
def export_summary(
    exp_id: str,
    format: str = Query("csv", pattern="^(csv|markdown|latex)$"),
    db: Session = Depends(get_db),
) -> Response:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    summaries = db.query(ResultSummaryModel).filter(ResultSummaryModel.experiment_id == exp_id).all()
    if not summaries:
        raise HTTPException(status_code=404, detail="No summary rows found")

    if format == "csv":
        output = io.StringIO()
        if exp.has_unverified:
            output.write("# NOTICE: UNVERIFIED QUESTIONS INCLUDED IN THIS RUN\n")
        fieldnames = [
            "config", "model", "hit_at_k", "hit_ci_lower", "hit_ci_upper",
            "mrr", "mrr_ci_lower", "mrr_ci_upper", "precision_at_k", "recall_at_k",
            "context_precision", "context_recall", "truncation_rate", "mean_latency_ms",
            "chunk_count", "avg_tokens", "index_size_mb",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for s in summaries:
            writer.writerow({
                "config": s.config,
                "model": s.model,
                "hit_at_k": round(s.hit_at_k, 3),
                "hit_ci_lower": round(s.hit_ci_lower, 3),
                "hit_ci_upper": round(s.hit_ci_upper, 3),
                "mrr": round(s.mrr, 3),
                "mrr_ci_lower": round(s.mrr_ci_lower, 3),
                "mrr_ci_upper": round(s.mrr_ci_upper, 3),
                "precision_at_k": round(s.precision_at_k, 3),
                "recall_at_k": round(s.recall_at_k, 3),
                "context_precision": round(s.context_precision, 3),
                "context_recall": round(s.context_recall, 3),
                "truncation_rate": round(s.truncation_rate, 3),
                "mean_latency_ms": round(s.mean_latency_ms, 2),
                "chunk_count": s.chunk_count,
                "avg_tokens": round(s.avg_tokens, 1),
                "index_size_mb": round(s.index_size_mb, 2),
            })
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=summary_{exp_id}.csv"},
        )

    elif format == "markdown":
        lines = []
        if exp.has_unverified:
            lines.append("> **NOTICE:** Unverified questions were included in this evaluation.\n")
        lines.append(f"# Evaluation Summary: `{exp_id}`\n")
        lines.append("| Config | Model | Hit@5 | MRR | P@5 | R@5 | CtxPrec | CtxRec | Trunc | Latency (ms) |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for s in summaries:
            lines.append(
                f"| `{s.config}` | `{s.model}` | {s.hit_at_k:.3f} | {s.mrr:.3f} | {s.precision_at_k:.3f} | "
                f"{s.recall_at_k:.3f} | {s.context_precision:.3f} | {s.context_recall:.3f} | "
                f"{s.truncation_rate:.1%} | {s.mean_latency_ms:.1f} |"
            )
        return Response(
            content="\n".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=summary_{exp_id}.md"},
        )

    elif format == "latex":
        lines = [
            r"\begin{table}[htbp]",
            r"\centering",
            r"\caption{RAG Retrieval Evaluation Summary on IETF RFC Corpus (" + exp_id + r")}",
            r"\begin{tabular}{llrrrrrrrr}",
            r"\hline",
            r"\textbf{Config} & \textbf{Model} & \textbf{Hit@5} & \textbf{MRR} & \textbf{P@5} & \textbf{R@5} & \textbf{CtxPrec} & \textbf{CtxRec} & \textbf{Trunc} & \textbf{Lat (ms)} \\",
            r"\hline",
        ]
        for s in summaries:
            clean_cfg = s.config.replace("_", r"\_")
            clean_mdl = s.model.replace("_", r"\_")
            lines.append(
                f"{clean_cfg} & {clean_mdl} & {s.hit_at_k:.3f} & {s.mrr:.3f} & {s.precision_at_k:.3f} & "
                f"{s.recall_at_k:.3f} & {s.context_precision:.3f} & {s.context_recall:.3f} & "
                f"{s.truncation_rate*100:.1f}\\% & {s.mean_latency_ms:.1f} \\\\"
            )
        lines.extend([
            r"\hline",
            r"\end{tabular}",
            r"\end{table}",
        ])
        return Response(
            content="\n".join(lines),
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=summary_{exp_id}.tex"},
        )


@router.get("/{exp_id}/manifest")
def get_manifest(exp_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    exp = db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Experiment '{exp_id}' not found")

    manifest_path = RESULTS_DIR / exp_id / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # Return reconstructed manifest from DB
    return {
        "run_id": exp.id,
        "name": exp.name,
        "preset": exp.preset,
        "status": exp.status,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
        "started_at": exp.started_at.isoformat() if exp.started_at else None,
        "finished_at": exp.finished_at.isoformat() if exp.finished_at else None,
        "verified_only": exp.verified_only,
        "verified_questions_count": exp.verified_questions_count,
        "unverified_questions_count": exp.unverified_questions_count,
        "has_unverified": exp.has_unverified,
        "device": "cpu",
    }


@router.get("/{exp_id}/methodology")
def get_methodology_doc(exp_id: str) -> dict[str, str]:
    text = f"""# Empirical Methodology: RFC RAG Chunking Lab

## 1. Research Question & Controlled Evaluation
This study investigates how chunking strategy and embedding model choice interact to determine retrieval quality, answer groundedness, and computational cost on technical networking documentation (IETF RFCs):
- **RQ1**: How do fixed-size token windowing, RFC-aware sentence packing, and semantic similarity splitting affect retrieval precision and recall?
- **RQ2**: How does embedding model architecture (`all-MiniLM-L6-v2`, `bge-small-en-v1.5`, `e5-small-v2`) interact with chunk granularity?
- **RQ3**: What trade-offs emerge between retrieval accuracy, pre-processing / indexing overhead, index memory footprint, and query latency?

## 2. Controlled Corpus & Invariant Spans
- The corpus consists of four core IETF standards: TCP (RFC 9293), DNS Concepts (RFC 1034), DNS Implementation (RFC 1035), and HTTP Semantics (RFC 9110).
- Text is cleaned deterministically, removing page headers and footers while preserving character offsets, ASCII protocol diagrams, and section headings.
- All chunk spans adhere strictly to the offset invariant: `text == cleaned_doc[char_start:char_end]`.

## 3. Evaluation Metrics
Retrieval effectiveness is measured at $k=5$:
- **Hit@5**: Fraction of queries where at least one ground-truth passage is retrieved.
- **MRR (Mean Reciprocal Rank)**: Position-sensitive reciprocal rank of the first relevant retrieved chunk.
- **Precision@5 & Recall@5**: Proportion of retrieved chunks that are relevant, and proportion of ground-truth passages retrieved.
- **Context Precision**: Rank-weighted relevance score penalizing late hits.
- **Context Recall**: Span coverage ratio measuring how thoroughly retrieved passages cover the gold evidence.
- **Statistical Significance**: 95% Confidence Intervals computed via 1,000 bootstrap resamples. Paired model comparisons evaluated with the Wilcoxon signed-rank test.
"""
    return {"experiment_id": exp_id, "markdown": text}
