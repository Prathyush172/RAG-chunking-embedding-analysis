"""
backend/app/cli.py — Command-line interface for RFC RAG Chunking Lab.

Commands:
- preprocess: clean raw RFCs in datasets/ -> data/clean/
- validate-questions: validate schema and evidence spans of data/eval/questions.json
- export-review: export questions to results/review_sheet.csv for human grading
- import-review: read filled review sheet back and update questions.json
- run: evaluate retrieval pipeline on preset (quick | full), saving to results/<run_id>/
- report: print leaderboard table from latest run in results/
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
import yaml

from .core.embedders import get_library_versions, load_models_config
from .core.evaluation import (
    EvidenceLocator,
    EvidenceValidator,
    NoRelevantChunksError,
    Question,
    RelevanceMapper,
    load_questions,
    save_questions,
)
from .core.index import compute_corpus_hash
from .core.metrics import (
    QueryRetrievalResult,
    compute_bootstrap_ci,
    evaluate_query_retrieval,
    evaluate_random_baseline,
)
from .core.preprocess import run_preprocessing
from .core.retrieval import RetrievalPipeline

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
CONFIGS_DIR = REPO_ROOT / "configs"
QUESTIONS_FILE = REPO_ROOT / "data" / "eval" / "questions.json"


def compute_questions_hash(questions_path: Path) -> str:
    """Compute SHA-256 hash of questions.json."""
    if not questions_path.exists():
        return ""
    h = hashlib.sha256()
    h.update(questions_path.read_bytes())
    return h.hexdigest()


# -----------------------------------------------------------------------------
# 1. PREPROCESS
# -----------------------------------------------------------------------------
def cmd_preprocess(args: argparse.Namespace) -> None:
    print("\n" + "=" * 80)
    print("RUNNING RFC PREPROCESSING PIPELINE")
    print("=" * 80)
    stats = run_preprocessing()
    print("\nRemoved-line counts and preprocessing stats:")
    for doc_id, s in stats.items():
        print(f"  {doc_id:<20}: {s.get('total_lines', 0)} total lines -> {s.get('cleaned_lines', 0)} cleaned ({s.get('blank_lines_collapsed', 0)} blanks collapsed, {s.get('footers_removed', 0)} footers removed, {s.get('headers_removed', 0)} headers removed)")
    print(f"\nCleaned files written to: data/clean/")


# -----------------------------------------------------------------------------
# 2. VALIDATE QUESTIONS
# -----------------------------------------------------------------------------
def cmd_validate_questions(args: argparse.Namespace) -> None:
    print("\n" + "=" * 80)
    print("VALIDATING EVALUATION QUESTIONS (data/eval/questions.json)")
    print("=" * 80)
    questions = load_questions(QUESTIONS_FILE)
    if not questions:
        print(f"No questions found at {QUESTIONS_FILE}")
        sys.exit(1)

    validator = EvidenceValidator()
    issues = validator.validate_all(questions)

    if issues:
        print(f"\n[FAIL] Found {len(issues)} validation issue(s):")
        for iss in issues:
            print(f"  - {iss}")
        sys.exit(1)

    verified_count = sum(1 for q in questions if q.verified)
    unverified_count = len(questions) - verified_count

    print(f"\n[PASS] All {len(questions)} questions are structurally valid and unique in data/clean/!")
    print(f"Verified questions:   {verified_count}")
    print(f"Unverified questions: {unverified_count}")
    if unverified_count > 0:
        print(">> NOTICE: Dataset contains UNVERIFIED questions drafted by LLM.")

    by_doc: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_diff: dict[str, int] = {}
    for q in questions:
        by_doc[q.doc_id] = by_doc.get(q.doc_id, 0) + 1
        by_type[q.type] = by_type.get(q.type, 0) + 1
        by_diff[q.difficulty] = by_diff.get(q.difficulty, 0) + 1

    print("\nBreakdown by Document:")
    for k, v in sorted(by_doc.items()):
        print(f"  {k:<20}: {v}")
    print("\nBreakdown by Question Type:")
    for k, v in sorted(by_type.items()):
        print(f"  {k:<20}: {v}")
    print("\nBreakdown by Difficulty:")
    for k, v in sorted(by_diff.items()):
        print(f"  {k:<20}: {v}")


# -----------------------------------------------------------------------------
# 3. EXPORT REVIEW
# -----------------------------------------------------------------------------
def cmd_export_review(args: argparse.Namespace) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = RESULTS_DIR / "review_sheet.csv"
    questions = load_questions(QUESTIONS_FILE)
    if not questions:
        print(f"No questions found at {QUESTIONS_FILE}")
        sys.exit(1)

    fieldnames = [
        "id",
        "doc_id",
        "section",
        "type",
        "difficulty",
        "question",
        "evidence_quote",
        "reference_answer",
        "lexical_overlap_run",
        "lexical_overlap_jaccard",
        "flagged_too_easy",
        "verdict",
        "notes",
        "reviewer",
    ]

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for q in questions:
            quote_text = "\n---\n".join(e.quote for e in q.evidence)
            writer.writerow({
                "id": q.id,
                "doc_id": q.doc_id,
                "section": q.section,
                "type": q.type,
                "difficulty": q.difficulty,
                "question": q.question,
                "evidence_quote": quote_text,
                "reference_answer": q.reference_answer,
                "lexical_overlap_run": getattr(q, "lexical_overlap_run", 0),
                "lexical_overlap_jaccard": getattr(q, "lexical_overlap_jaccard", 0.0),
                "flagged_too_easy": getattr(q, "flagged_too_easy", False),
                "verdict": "approved" if q.verified else "",
                "notes": q.notes or "",
                "reviewer": q.reviewer or "",
            })

    print(f"Exported {len(questions)} questions to review sheet: {out_csv}")


# -----------------------------------------------------------------------------
# 4. IMPORT REVIEW
# -----------------------------------------------------------------------------
def cmd_import_review(args: argparse.Namespace) -> None:
    csv_path = Path(args.csv_file)
    if not csv_path.exists():
        print(f"CSV file not found: {csv_path}")
        sys.exit(1)

    existing_questions = {q.id: q for q in load_questions(QUESTIONS_FILE)}
    approved_count = 0
    rejected_count = 0
    edited_count = 0
    unchanged_count = 0

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = row.get("id", "").strip()
            if not qid or qid not in existing_questions:
                continue
            q = existing_questions[qid]
            verdict = row.get("verdict", "").strip().lower()
            reviewer = row.get("reviewer", "").strip()
            notes = row.get("notes", "").strip()

            if verdict in {"approve", "approved", "true", "yes"}:
                q.verified = True
                q.reviewer = reviewer or "reviewer"
                q.reviewed_at = datetime.datetime.utcnow().isoformat()
                if notes:
                    q.notes = notes
                approved_count += 1
            elif verdict in {"reject", "rejected"}:
                del existing_questions[qid]
                rejected_count += 1
            elif verdict in {"edit", "edited"}:
                q.notes = notes or "Edited during review"
                edited_count += 1
            else:
                unchanged_count += 1

    updated_list = list(existing_questions.values())
    save_questions(updated_list, QUESTIONS_FILE)

    print(f"\nReview sheet imported from: {csv_path}")
    print(f"  Approved:  {approved_count}")
    print(f"  Rejected:  {rejected_count}")
    print(f"  Edited:    {edited_count}")
    print(f"  Unchanged: {unchanged_count}")
    print(f"Saved {len(updated_list)} questions back to {QUESTIONS_FILE}")


# -----------------------------------------------------------------------------
# 5. RUN EXPERIMENT
# -----------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> None:
    preset = args.preset
    verified_only = args.verified_only
    k = args.k

    with open(CONFIGS_DIR / "experiment.yaml", encoding="utf-8") as f:
        exp_yaml = yaml.safe_load(f)

    if preset not in exp_yaml.get("presets", {}):
        print(f"Error: Unknown preset '{preset}'. Choose from {list(exp_yaml.get('presets', {}).keys())}")
        sys.exit(1)

    preset_cfg = exp_yaml["presets"][preset]
    chunk_configs = preset_cfg["chunking_configs"]
    model_ids = preset_cfg["models"]

    # Load questions
    all_questions = load_questions(QUESTIONS_FILE)
    if not all_questions:
        print(f"Error: No questions found at {QUESTIONS_FILE}")
        sys.exit(1)

    # Resolve evidence spans
    validator = EvidenceValidator()
    issues = validator.validate_all(all_questions)
    if issues:
        print(f"Error: Questions have validation issues: {issues[0]}")
        sys.exit(1)

    if verified_only:
        questions = [q for q in all_questions if q.verified]
        if not questions:
            print("\n" + "!" * 80)
            print("Error: 0 questions are verified. Cannot run with --verified-only.")
            print("!" * 80)
            sys.exit(1)
    else:
        questions = all_questions

    unverified_count = sum(1 for q in questions if not q.verified)
    has_unverified = unverified_count > 0

    run_id = f"run_{preset}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    run_dir = RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 110)
    print(f"RFC RAG CHUNKING LAB — EVALUATION RUN [{preset.upper()} PRESET]")
    if has_unverified:
        print(">>> WARNING: UNVERIFIED QUESTIONS INCLUDED IN THIS RUN <<<")
    print(f"Output directory: {run_dir}")
    print(f"Questions evaluated: {len(questions)} ({unverified_count} unverified, {len(questions)-unverified_count} verified)")
    print(f"Configs: {len(chunk_configs)} | Models: {len(model_ids)} | k: {k}")
    print("=" * 110)

    pipeline = RetrievalPipeline()
    relevance_mapper = RelevanceMapper()

    per_query_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    # Run evaluations
    total_evals = len(chunk_configs) * len(model_ids) + 1  # +1 for random baseline
    eval_idx = 0

    for c_cfg in chunk_configs:
        for m_id in model_ids:
            eval_idx += 1
            print(f"\n[{eval_idx}/{total_evals}] Evaluating Config: {c_cfg['label']} | Model: {m_id} ...")
            artifacts, run_summary = pipeline.get_or_build_index(
                chunk_config=c_cfg,
                model_id=m_id,
                exclude_front_matter=True,
            )
            all_chunks = artifacts.chunks
            chunk_lookup = {c.chunk_id: c for c in all_chunks}

            # Batch retrieve top-k across all questions
            query_texts = [q.question for q in questions]
            batch_results = pipeline.retrieve_batch(query_texts, c_cfg, m_id, k=k)

            # Evaluate each question
            query_results: list[QueryRetrievalResult] = []
            for q, ret_res in zip(questions, batch_results):
                ret_chunks = [chunk_lookup[r.chunk_id] for r in ret_res.results]
                ret_scores = [r.score for r in ret_res.results]

                eval_q = evaluate_query_retrieval(
                    question=q,
                    retrieved_chunks=ret_chunks,
                    retrieved_scores=ret_scores,
                    all_chunks_in_index=all_chunks,
                    relevance_mapper=relevance_mapper,
                    k=k,
                    latency_ms=ret_res.latency_ms,
                    config_label=c_cfg["label"],
                )
                query_results.append(eval_q)

                q_row = eval_q.to_dict()
                q_row["config"] = c_cfg["label"]
                q_row["model"] = m_id
                q_row["run_id"] = run_id
                q_row["unverified_question"] = not q.verified
                per_query_rows.append(q_row)

            # Compute statistics and bootstrap CIs
            hit_mean, hit_lo, hit_hi = compute_bootstrap_ci([r.hit_at_k for r in query_results])
            mrr_mean, mrr_lo, mrr_hi = compute_bootstrap_ci([r.mrr for r in query_results])
            p_mean, p_lo, p_hi = compute_bootstrap_ci([r.precision_at_k for r in query_results])
            r_mean, r_lo, r_hi = compute_bootstrap_ci([r.recall_at_k for r in query_results])
            cp_mean, cp_lo, cp_hi = compute_bootstrap_ci([r.context_precision for r in query_results])
            cr_mean, cr_lo, cr_hi = compute_bootstrap_ci([r.context_recall for r in query_results])
            lat_mean = float(np.mean([r.latency_ms for r in query_results]))

            summary_rows.append({
                "config": c_cfg["label"],
                "model": m_id,
                "hit_at_k": hit_mean,
                "hit_ci_lower": hit_lo,
                "hit_ci_upper": hit_hi,
                "mrr": mrr_mean,
                "mrr_ci_lower": mrr_lo,
                "mrr_ci_upper": mrr_hi,
                "precision_at_k": p_mean,
                "precision_ci_lower": p_lo,
                "precision_ci_upper": p_hi,
                "recall_at_k": r_mean,
                "recall_ci_lower": r_lo,
                "recall_ci_upper": r_hi,
                "context_precision": cp_mean,
                "context_precision_ci_lower": cp_lo,
                "context_precision_ci_upper": cp_hi,
                "context_recall": cr_mean,
                "context_recall_ci_lower": cr_lo,
                "context_recall_ci_upper": cr_hi,
                "truncation_rate": run_summary.truncation_rate,
                "mean_latency_ms": round(lat_mean, 2),
                "chunk_count": run_summary.chunk_count,
                "avg_tokens": run_summary.avg_tokens_per_chunk,
                "index_size_mb": run_summary.index_size_mb,
            })

    # Random baseline
    print(f"\n[{total_evals}/{total_evals}] Evaluating Random Retrieval Baseline ...")
    rand_cfg = chunk_configs[0]
    rand_artifacts, _ = pipeline.get_or_build_index(chunk_config=rand_cfg, model_id=model_ids[0], exclude_front_matter=True)
    rand_config_name = "random_baseline (mean of 100 draws)"
    rand_results = evaluate_random_baseline(
        questions=questions,
        all_chunks=rand_artifacts.chunks,
        relevance_mapper=relevance_mapper,
        k=k,
        num_draws=100,
        config_label=rand_config_name,
    )
    for r in rand_results:
        q_row = r.to_dict()
        q_row["config"] = rand_config_name
        q_row["model"] = "none"
        q_row["run_id"] = run_id
        q_row["unverified_question"] = not all_questions[0].verified
        per_query_rows.append(q_row)

    r_hit_mean, r_hit_lo, r_hit_hi = compute_bootstrap_ci([r.hit_at_k for r in rand_results])
    r_mrr_mean, r_mrr_lo, r_mrr_hi = compute_bootstrap_ci([r.mrr for r in rand_results])
    r_p_mean, r_p_lo, r_p_hi = compute_bootstrap_ci([r.precision_at_k for r in rand_results])
    r_r_mean, r_r_lo, r_r_hi = compute_bootstrap_ci([r.recall_at_k for r in rand_results])
    r_cp_mean, r_cp_lo, r_cp_hi = compute_bootstrap_ci([r.context_precision for r in rand_results])
    r_cr_mean, r_cr_lo, r_cr_hi = compute_bootstrap_ci([r.context_recall for r in rand_results])

    summary_rows.append({
        "config": rand_config_name,
        "model": "none",
        "hit_at_k": r_hit_mean,
        "hit_ci_lower": r_hit_lo,
        "hit_ci_upper": r_hit_hi,
        "mrr": r_mrr_mean,
        "mrr_ci_lower": r_mrr_lo,
        "mrr_ci_upper": r_mrr_hi,
        "precision_at_k": r_p_mean,
        "precision_ci_lower": r_p_lo,
        "precision_ci_upper": r_p_hi,
        "recall_at_k": r_r_mean,
        "recall_ci_lower": r_r_lo,
        "recall_ci_upper": r_r_hi,
        "context_precision": r_cp_mean,
        "context_precision_ci_lower": r_cp_lo,
        "context_precision_ci_upper": r_cp_hi,
        "context_recall": r_cr_mean,
        "context_recall_ci_lower": r_cr_lo,
        "context_recall_ci_upper": r_cr_hi,
        "truncation_rate": 0.0,
        "mean_latency_ms": 0.1,
        "chunk_count": len(rand_artifacts.chunks),
        "avg_tokens": 0.0,
        "index_size_mb": 0.0,
    })

    # Save per_query.csv
    pq_path = run_dir / "per_query.csv"
    with open(pq_path, "w", newline="", encoding="utf-8") as f:
        if has_unverified:
            f.write("# NOTICE: UNVERIFIED QUESTIONS INCLUDED IN THIS RUN\n")
        writer = csv.DictWriter(f, fieldnames=list(per_query_rows[0].keys()))
        writer.writeheader()
        writer.writerows(per_query_rows)

    # Save summary.csv
    sm_path = run_dir / "summary.csv"
    with open(sm_path, "w", newline="", encoding="utf-8") as f:
        if has_unverified:
            f.write("# NOTICE: UNVERIFIED QUESTIONS INCLUDED IN THIS RUN\n")
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    # Save manifest.json
    manifest = {
        "run_id": run_id,
        "preset": preset,
        "k": k,
        "unverified_questions_included": has_unverified,
        "verified_questions_count": len(questions) - unverified_count,
        "unverified_questions_count": unverified_count,
        "corpus_hash": compute_corpus_hash(),
        "questions_hash": compute_questions_hash(QUESTIONS_FILE),
        "library_versions": get_library_versions(),
        "device": "cpu",
        "seed": 42,
        "timestamp_utc": datetime.datetime.utcnow().isoformat(),
        "completed_runs": len(summary_rows),
    }
    with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Update latest pointer
    with open(RESULTS_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "path": str(run_dir)}, f, indent=2)

    print("\n" + "=" * 110)
    print("EVALUATION COMPLETE — LEADERBOARD SUMMARY")
    if has_unverified:
        print(">>> NOTICE: UNVERIFIED QUESTIONS INCLUDED IN THIS EVALUATION <<<")
    print("=" * 110)
    _print_leaderboard_table(summary_rows)


def _print_leaderboard_table(rows: list[dict[str, Any]]) -> None:
    header = (
        f"{'Chunk Config':<36} | {'Model':<12} | {'Hit@5':>6} | {'MRR':>6} | "
        f"{'P@5':>6} | {'R@5':>6} | {'CtxPrec':>7} | {'CtxRec':>6} | "
        f"{'Trunc':>6} | {'Lat(ms)':>7}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        row_str = (
            f"{r['config']:<36} | {r['model']:<12} | {r['hit_at_k']:>6.3f} | {r['mrr']:>6.3f} | "
            f"{r['precision_at_k']:>6.3f} | {r['recall_at_k']:>6.3f} | {r['context_precision']:>7.3f} | {r['context_recall']:>6.3f} | "
            f"{r['truncation_rate']:>5.1%} | {r['mean_latency_ms']:>7.1f}"
        )
        print(row_str)
    print("=" * len(header))


# -----------------------------------------------------------------------------
# 6. REPORT
# -----------------------------------------------------------------------------
def cmd_report(args: argparse.Namespace) -> None:
    latest_file = RESULTS_DIR / "latest.json"
    if not latest_file.exists():
        # Find latest directory in results/
        runs = sorted([p for p in RESULTS_DIR.glob("run_*") if p.is_dir()])
        if not runs:
            print(f"No run results found in {RESULTS_DIR}")
            sys.exit(1)
        target_dir = runs[-1]
    else:
        with open(latest_file, encoding="utf-8") as f:
            target_dir = Path(json.load(f)["path"])

    summary_file = target_dir / "summary.csv"
    manifest_file = target_dir / "manifest.json"

    if not summary_file.exists():
        print(f"Summary file not found: {summary_file}")
        sys.exit(1)

    has_unverified = False
    rows: list[dict[str, Any]] = []
    with open(summary_file, encoding="utf-8") as f:
        lines = f.readlines()
        if lines and lines[0].startswith("# NOTICE: UNVERIFIED"):
            has_unverified = True
            lines = lines[1:]
        reader = csv.DictReader(lines)
        for r in reader:
            for k in ["hit_at_k", "mrr", "precision_at_k", "recall_at_k", "context_precision", "context_recall", "truncation_rate", "mean_latency_ms"]:
                r[k] = float(r[k])
            rows.append(r)

    manifest_info = {}
    if manifest_file.exists():
        with open(manifest_file, encoding="utf-8") as f:
            manifest_info = json.load(f)

    print("\n" + "=" * 110)
    print(f"RFC RAG CHUNKING LAB — LATEST RUN LEADERBOARD [{target_dir.name}]")
    if has_unverified or manifest_info.get("unverified_questions_included"):
        print(">>> NOTICE: UNVERIFIED QUESTIONS INCLUDED IN THIS REPORT <<<")
    if manifest_info:
        print(f"Preset: {manifest_info.get('preset')} | Seed: {manifest_info.get('seed')} | Device: {manifest_info.get('device')} | Timestamp: {manifest_info.get('timestamp_utc')}")
    print("=" * 110)
    _print_leaderboard_table(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="RFC RAG Chunking Lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # preprocess
    subparsers.add_parser("preprocess", help="Run raw RFC cleaning pipeline")

    # validate-questions
    subparsers.add_parser("validate-questions", help="Validate evaluation questions dataset")

    # export-review
    subparsers.add_parser("export-review", help="Export questions to review sheet CSV")

    # import-review
    p_import = subparsers.add_parser("import-review", help="Import filled review sheet CSV")
    p_import.add_argument("csv_file", help="Path to filled review CSV")

    # run
    p_run = subparsers.add_parser("run", help="Run comparative evaluation benchmark")
    p_run.add_argument("--preset", choices=["quick", "full"], default="quick", help="Preset configuration")
    p_run.add_argument("--verified-only", action="store_true", help="Evaluate only human-verified questions")
    p_run.add_argument("--k", type=int, default=5, help="Top-k retrieval cut-off")

    # report
    subparsers.add_parser("report", help="Display leaderboard from latest run")

    args = parser.parse_args()

    if args.command == "preprocess":
        cmd_preprocess(args)
    elif args.command == "validate-questions":
        cmd_validate_questions(args)
    elif args.command == "export-review":
        cmd_export_review(args)
    elif args.command == "import-review":
        cmd_import_review(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
