"""
backend/app/core/metrics.py — Retrieval metrics, bootstrap confidence intervals, and statistical tests.

Implements Phase 4 metrics for top-k evaluation:
- Precision@5, Recall@5 (with sensible denominator capping and documentation), Hit@5, MRR
- Context Precision (rank-weighted RAGAS formulation)
- Context Recall (character span coverage of gold evidence)
- Multi-hop support (all_evidence_hit)
- Random retrieval baseline (deterministic seed 42)
- Bootstrap 95% confidence intervals (1,000 resamples, deterministic seed 42)
- Wilcoxon signed-rank paired significance testing with all-zero difference handling
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
from scipy import stats

from .chunkers import Chunk
from .evaluation import EvidenceItem, Question, RelevanceMapper

logger = logging.getLogger(__name__)


@dataclass
class QueryRetrievalResult:
    question_id: str
    doc_id: str
    question_type: str
    difficulty: str
    k: int
    retrieved_chunk_ids: list[str]
    retrieved_scores: list[float]
    relevant_chunk_ids: list[str]
    total_relevant_in_index: int

    # Core IR Metrics
    hit_at_k: float
    mrr: float
    precision_at_k: float
    recall_at_k: float             # Capped at min(k, total_relevant) for sensible maximum of 1.0
    uncapped_recall_at_k: float    # Standard IR recall: retrieved_relevant / total_relevant
    context_precision: float
    context_recall: float
    all_evidence_hit: float        # 1.0 if every evidence span was covered, else 0.0
    latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "doc_id": self.doc_id,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "k": self.k,
            "hit_at_k": round(self.hit_at_k, 4),
            "mrr": round(self.mrr, 4),
            "precision_at_k": round(self.precision_at_k, 4),
            "recall_at_k": round(self.recall_at_k, 4),
            "uncapped_recall_at_k": round(self.uncapped_recall_at_k, 4),
            "context_precision": round(self.context_precision, 4),
            "context_recall": round(self.context_recall, 4),
            "all_evidence_hit": round(self.all_evidence_hit, 4),
            "total_relevant_in_index": self.total_relevant_in_index,
            "latency_ms": round(self.latency_ms, 2),
        }


@dataclass
class MetricSummary:
    mean: float
    ci_lower: float
    ci_upper: float

    def to_dict(self) -> dict[str, float]:
        return {
            "mean": round(self.mean, 4),
            "ci_lower": round(self.ci_lower, 4),
            "ci_upper": round(self.ci_upper, 4),
        }


@dataclass
class WilcoxonResult:
    statistic: float
    p_value: float
    effect_size: float   # mean difference (config1 - config2)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "statistic": round(self.statistic, 4),
            "p_value": round(self.p_value, 6),
            "effect_size": round(self.effect_size, 4),
            "note": self.note,
        }


def compute_interval_coverage(
    span_start: int,
    span_end: int,
    chunks: list[tuple[int, int]],
) -> int:
    """
    Compute number of characters in [span_start, span_end) covered by the union of chunks.
    chunks is a list of (c_start, c_end) intervals.
    """
    if span_end <= span_start or not chunks:
        return 0

    # Intersect each chunk with [span_start, span_end)
    intervals = []
    for cs, ce in chunks:
        overlap_s = max(span_start, cs)
        overlap_e = min(span_end, ce)
        if overlap_e > overlap_s:
            intervals.append((overlap_s, overlap_e))

    if not intervals:
        return 0

    # Merge overlapping intervals
    intervals.sort(key=lambda x: x[0])
    merged = [intervals[0]]
    for cur_s, cur_e in intervals[1:]:
        prev_s, prev_e = merged[-1]
        if cur_s <= prev_e:
            merged[-1] = (prev_s, max(prev_e, cur_e))
        else:
            merged.append((cur_s, cur_e))

    covered_chars = sum(e - s for s, e in merged)
    return covered_chars


def evaluate_query_retrieval(
    question: Question,
    retrieved_chunks: list[Chunk],
    retrieved_scores: list[float],
    all_chunks_in_index: list[Chunk],
    relevance_mapper: RelevanceMapper,
    k: int = 5,
    latency_ms: float = 0.0,
    config_label: str = "",
) -> QueryRetrievalResult:
    """
    Evaluate top-k retrieval for a single question against ground truth evidence spans.
    """
    # 1. Determine all relevant chunks in index
    relevant_chunks = relevance_mapper.get_relevant_chunks(
        question, all_chunks_in_index, config_label=config_label, allow_empty=False
    )
    relevant_chunk_ids = {c.chunk_id for c in relevant_chunks}
    total_relevant = len(relevant_chunk_ids)

    # 2. Slice to top-k
    top_k_chunks = retrieved_chunks[:k]
    top_k_scores = retrieved_scores[:k]

    retrieved_chunk_ids = [c.chunk_id for c in top_k_chunks]
    is_relevant_at_rank = [cid in relevant_chunk_ids for cid in retrieved_chunk_ids]
    rel_retrieved_count = sum(is_relevant_at_rank)

    # Hit@k
    hit_at_k = 1.0 if rel_retrieved_count > 0 else 0.0

    # MRR (1 / rank of first relevant chunk; 0 if none)
    mrr = 0.0
    for idx, is_rel in enumerate(is_relevant_at_rank):
        if is_rel:
            mrr = 1.0 / (idx + 1)
            break

    # Precision@k = relevant retrieved / k
    precision_at_k = rel_retrieved_count / float(k) if k > 0 else 0.0

    # Recall@k
    # Standard IR recall = rel_retrieved_count / total_relevant
    uncapped_recall = rel_retrieved_count / float(total_relevant) if total_relevant > 0 else 0.0
    # Capped Recall@k = rel_retrieved_count / min(k, total_relevant)
    # Rationale: if there are 10 relevant chunks in the index, a system retrieving 5/5 relevant
    # chunks in top-5 achieves 1.0 rather than being penalized by an unreachable denominator.
    capped_denom = min(k, total_relevant)
    recall_at_k = rel_retrieved_count / float(capped_denom) if capped_denom > 0 else 0.0

    # Context Precision (Rank-weighted precision, RAGAS formulation)
    # Sum over relevant ranks of (precision@rank) / total relevant retrieved in top-k
    if rel_retrieved_count > 0:
        precisions_sum = 0.0
        running_rel = 0
        for i, is_rel in enumerate(is_relevant_at_rank, start=1):
            if is_rel:
                running_rel += 1
                precisions_sum += running_rel / float(i)
        context_precision = precisions_sum / float(rel_retrieved_count)
    else:
        context_precision = 0.0

    # Context Recall (Character span coverage across all gold evidence items)
    total_evidence_chars = 0
    total_covered_chars = 0
    evidence_covered_flags: list[bool] = []

    for ev in question.evidence:
        ev_len = ev.char_end - ev.char_start
        total_evidence_chars += ev_len

        # Chunks in top_k that match this doc_id
        matching_spans = [
            (c.char_start, c.char_end)
            for c in top_k_chunks
            if c.doc_id == ev.doc_id
        ]
        covered = compute_interval_coverage(ev.char_start, ev.char_end, matching_spans)
        total_covered_chars += covered

        # For all_evidence_hit: chunk must cover this evidence span
        # using the standard threshold
        ev_hit = any(
            relevance_mapper.is_chunk_relevant_to_span(c, ev.doc_id, ev.char_start, ev.char_end)
            for c in top_k_chunks
        )
        evidence_covered_flags.append(ev_hit)

    context_recall = (
        float(total_covered_chars) / float(total_evidence_chars)
        if total_evidence_chars > 0
        else 0.0
    )

    all_evidence_hit = 1.0 if all(evidence_covered_flags) else 0.0

    return QueryRetrievalResult(
        question_id=question.id,
        doc_id=question.doc_id,
        question_type=question.type,
        difficulty=question.difficulty,
        k=k,
        retrieved_chunk_ids=retrieved_chunk_ids,
        retrieved_scores=top_k_scores,
        relevant_chunk_ids=sorted(list(relevant_chunk_ids)),
        total_relevant_in_index=total_relevant,
        hit_at_k=hit_at_k,
        mrr=mrr,
        precision_at_k=precision_at_k,
        recall_at_k=recall_at_k,
        uncapped_recall_at_k=uncapped_recall,
        context_precision=context_precision,
        context_recall=context_recall,
        all_evidence_hit=all_evidence_hit,
        latency_ms=latency_ms,
    )


def compute_bootstrap_ci(
    values: list[float] | np.ndarray,
    n_resamples: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Compute mean and deterministic percentile bootstrap confidence interval.
    Returns: (mean, ci_lower, ci_upper)
    """
    arr = np.asarray(values, dtype=np.float64)
    if len(arr) == 0:
        return 0.0, 0.0, 0.0
    mean_val = float(np.mean(arr))
    if len(arr) == 1:
        return mean_val, mean_val, mean_val

    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(arr), size=(n_resamples, len(arr)))
    resamples = arr[indices]
    sample_means = np.mean(resamples, axis=1)

    alpha = 1.0 - confidence_level
    lower_pct = (alpha / 2.0) * 100.0
    upper_pct = (1.0 - alpha / 2.0) * 100.0

    ci_lower = float(np.percentile(sample_means, lower_pct))
    ci_upper = float(np.percentile(sample_means, upper_pct))

    return mean_val, ci_lower, ci_upper


def compute_wilcoxon_paired(
    values_a: list[float] | np.ndarray,
    values_b: list[float] | np.ndarray,
) -> WilcoxonResult:
    """
    Compute Wilcoxon signed-rank paired test between two aligned arrays.
    Handles the edge case where all differences are zero.
    """
    a = np.asarray(values_a, dtype=np.float64)
    b = np.asarray(values_b, dtype=np.float64)

    if len(a) != len(b):
        raise ValueError(f"Array lengths must match for paired test: {len(a)} vs {len(b)}")

    diff = a - b
    effect_size = float(np.mean(diff))

    # Edge case: all differences are zero
    if np.all(diff == 0.0):
        return WilcoxonResult(
            statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            note="All pairwise differences are zero.",
        )

    # Scipy wilcoxon
    try:
        res = stats.wilcoxon(a, b, zero_method="wilcox", correction=False)
        return WilcoxonResult(
            statistic=float(res.statistic),
            p_value=float(res.pvalue),
            effect_size=effect_size,
        )
    except Exception as e:
        logger.warning("Wilcoxon calculation encountered: %s", e)
        return WilcoxonResult(
            statistic=0.0,
            p_value=1.0,
            effect_size=effect_size,
            note=f"Wilcoxon calculation fallback: {e}",
        )


def evaluate_random_baseline(
    questions: list[Question],
    all_chunks: list[Chunk],
    relevance_mapper: RelevanceMapper,
    k: int = 5,
    num_draws: int = 100,
    seed: int = 0,
    config_label: str = "random_baseline (mean of 100 draws)",
) -> list[QueryRetrievalResult]:
    """
    Generate deterministic random retrieval baseline averaged over 100 draws (seeds 0-99).
    Returns list of QueryRetrievalResult (one per question).
    """
    results: list[QueryRetrievalResult] = []

    for q_idx, q in enumerate(questions):
        draw_metrics: list[QueryRetrievalResult] = []
        for s in range(num_draws):
            # Deterministic RNG per question and draw
            rng = np.random.default_rng((seed + s) * 1000 + q_idx)
            if len(all_chunks) <= k:
                selected_chunks = list(all_chunks)
            else:
                chosen_indices = rng.choice(len(all_chunks), size=k, replace=False)
                selected_chunks = [all_chunks[idx] for idx in chosen_indices]

            scores = [1.0 / (idx + 1) for idx in range(len(selected_chunks))]
            eval_res = evaluate_query_retrieval(
                question=q,
                retrieved_chunks=selected_chunks,
                retrieved_scores=scores,
                all_chunks_in_index=all_chunks,
                relevance_mapper=relevance_mapper,
                k=k,
                latency_ms=0.1,
                config_label=config_label,
            )
            draw_metrics.append(eval_res)

        # Average across the num_draws for this question
        avg_res = QueryRetrievalResult(
            question_id=q.id,
            doc_id=q.doc_id,
            question_type=q.type,
            difficulty=q.difficulty,
            k=k,
            retrieved_chunk_ids=draw_metrics[0].retrieved_chunk_ids,
            retrieved_scores=draw_metrics[0].retrieved_scores,
            relevant_chunk_ids=draw_metrics[0].relevant_chunk_ids,
            total_relevant_in_index=draw_metrics[0].total_relevant_in_index,
            hit_at_k=float(np.mean([m.hit_at_k for m in draw_metrics])),
            mrr=float(np.mean([m.mrr for m in draw_metrics])),
            precision_at_k=float(np.mean([m.precision_at_k for m in draw_metrics])),
            recall_at_k=float(np.mean([m.recall_at_k for m in draw_metrics])),
            uncapped_recall_at_k=float(np.mean([m.uncapped_recall_at_k for m in draw_metrics])),
            context_precision=float(np.mean([m.context_precision for m in draw_metrics])),
            context_recall=float(np.mean([m.context_recall for m in draw_metrics])),
            all_evidence_hit=float(np.mean([m.all_evidence_hit for m in draw_metrics])),
            latency_ms=0.1,
        )
        results.append(avg_res)

    return results
