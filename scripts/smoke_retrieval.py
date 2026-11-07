"""
scripts/smoke_retrieval.py — Smoke script for Phase 3 retrieval validation.

Evaluates the 'quick' preset (3 chunkers x 3 models = 9 runs):
- Fixed (256, 0%)
- Sentence (256, 0 sentences)
- Semantic (max 512, p25, min 64)
Across models: minilm, bge_small, e5_small.

Prints:
1. Comprehensive Run Summary & Latency Table
2. Top-5 retrieved chunks for 3 canonical networking queries
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.retrieval import RetrievalPipeline

SAMPLE_QUERIES = [
    "How does TCP establish a connection?",
    "What does a DNS resource record contain?",
    "What does the HTTP 404 status code mean?",
]


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    with open(REPO_ROOT / "configs" / "experiment.yaml", encoding="utf-8") as f:
        exp_cfg = yaml.safe_load(f)

    quick_cfg = exp_cfg["presets"]["quick"]
    chunk_configs = quick_cfg["chunking_configs"]
    models = quick_cfg["models"]

    pipeline = RetrievalPipeline()

    print("\n" + "=" * 120)
    print("PHASE 3: QUICK PRESET BENCHMARK (9 RUNS)")
    print("=" * 120)
    header = (
        f"{'Chunk Config':<18} | {'Model':<12} | {'Chunks':>6} | {'AvgTok':>6} | "
        f"{'Chunk(s)':>8} | {'Emb(s)':>7} | {'Idx(s)':>6} | {'Idx(MB)':>7} | "
        f"{'TruncRate':>9} | {'MeanLat(ms)':>11}"
    )
    print(header)
    print("-" * 120)

    summaries = []

    for c_cfg in chunk_configs:
        for model_id in models:
            artifacts, summary = pipeline.get_or_build_index(
                chunk_config=c_cfg,
                model_id=model_id,
                exclude_front_matter=True,
            )

            # Benchmark latency across queries with 5 warmups
            lat_stats = pipeline.benchmark_latency(
                queries=SAMPLE_QUERIES,
                chunk_config=c_cfg,
                model_id=model_id,
                k=5,
                warmup_queries=5,
            )
            summary.latency_stats = lat_stats
            summaries.append(summary)

            row = (
                f"{c_cfg['label']:<18} | {model_id:<12} | {summary.chunk_count:>6} | {summary.avg_tokens_per_chunk:>6.1f} | "
                f"{summary.chunking_time_seconds:>8.3f} | {summary.embedding_time_seconds:>7.3f} | {summary.index_build_time_seconds:>6.3f} | {summary.index_size_mb:>7.2f} | "
                f"{summary.truncation_rate:>8.1%} | {lat_stats.mean_ms:>11.2f}"
            )
            print(row)

    print("=" * 120)

    # 2. Detailed query retrieval smoke test for a representative config
    rep_cfg = chunk_configs[1]  # sent_256_0
    rep_model = "bge_small"

    print(f"\n\n{'#' * 90}")
    print(f"SMOKE TEST RETRIEVAL OUTPUT — Config: {rep_cfg['label']}, Model: {rep_model}")
    print(f"{'#' * 90}")

    for q in SAMPLE_QUERIES:
        print(f"\n>>> QUERY: {q}")
        res = pipeline.retrieve(q, rep_cfg, rep_model, k=5)
        print(f"Latency: {res.latency_ms:.2f} ms | Results returned: {len(res.results)}")
        for r in res.results:
            preview = r.text.strip().replace("\n", " ")
            if len(preview) > 150:
                preview = preview[:150] + "..."
            print(f"  [Rank {r.rank}] Score: {r.score:.4f} | RFC: {r.doc_id:<18} | Section: {str(r.section):<30}")
            print(f"           Preview: {preview}")

    print("\n" + "=" * 90)


if __name__ == "__main__":
    main()
