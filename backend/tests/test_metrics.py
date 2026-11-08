"""
backend/tests/test_metrics.py — Tests for retrieval metrics, bootstrap CIs, and statistical tests.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.core.chunkers import Chunk
from app.core.evaluation import EvidenceItem, Question, RelevanceMapper
from app.core.metrics import (
    compute_bootstrap_ci,
    compute_interval_coverage,
    compute_wilcoxon_paired,
    evaluate_query_retrieval,
    evaluate_random_baseline,
)


class TestMetricsHandComputed:
    """
    Hand-computed small example verification:
    k = 5
    Gold evidence: [100, 200) -> len = 100 chars in doc1
    Chunks:
      c1: [100, 200) -> Relevant (gold match)
      c2: [300, 400) -> Irrelevant
      c3: [120, 180) -> Relevant (overlap = 60 >= 40)
      c4: [500, 600) -> Irrelevant
      c5: [700, 800) -> Irrelevant
      c6: [150, 220) -> Relevant (in index, not retrieved)

    Total relevant in index = 3 (c1, c3, c6)
    Retrieved ranking: [c1, c2, c3, c4, c5]
    Relevance at rank:
      Rank 1 (c1): True
      Rank 2 (c2): False
      Rank 3 (c3): True
      Rank 4 (c4): False
      Rank 5 (c5): False

    Expected values:
    - Hit@5 = 1.0 (ranks 1 and 3 are relevant)
    - MRR = 1.0 (first relevant at rank 1: 1 / 1 = 1.0)
    - Precision@5 = 2 / 5 = 0.4000
    - Recall@5 (capped at min(k=5, total=3) = 3): 2 / 3 = 0.6667
    - Uncapped Recall@5 = 2 / 3 = 0.6667
    - Context Precision:
        Rank 1: Precision@1 = 1/1 = 1.0
        Rank 3: Precision@3 = 2/3 = 0.6667
        Context Precision = (1.0 + 2/3) / 2 = 1.6667 / 2 = 0.8333
    - Context Recall:
        c1 covers [100, 200) -> 100 chars
        c3 covers [120, 180) -> subset of [100, 200)
        Union coverage = 100 chars / 100 gold chars = 1.0000
    - all_evidence_hit = 1.0 (single evidence span covered)
    """

    def test_hand_computed_ranking_example(self):
        ev = EvidenceItem(doc_id="doc1", quote="evidence", char_start=100, char_end=200)
        q = Question(
            id="q_calc",
            question="What is the calculation?",
            doc_id="doc1",
            section="sec",
            evidence=[ev],
            reference_answer="ans",
            type="factual",
            difficulty="easy",
        )

        c1 = Chunk("c1", "doc1", "text", 100, 200, 20, "fixed")
        c2 = Chunk("c2", "doc1", "text", 300, 400, 20, "fixed")
        c3 = Chunk("c3", "doc1", "text", 120, 180, 20, "fixed")
        c4 = Chunk("c4", "doc1", "text", 500, 600, 20, "fixed")
        c5 = Chunk("c5", "doc1", "text", 700, 800, 20, "fixed")
        c6 = Chunk("c6", "doc1", "text", 150, 220, 20, "fixed")  # Not retrieved in top 5

        all_chunks = [c1, c2, c3, c4, c5, c6]
        retrieved_chunks = [c1, c2, c3, c4, c5]
        retrieved_scores = [0.95, 0.85, 0.75, 0.65, 0.55]

        mapper = RelevanceMapper(min_overlap_chars=40)
        res = evaluate_query_retrieval(
            question=q,
            retrieved_chunks=retrieved_chunks,
            retrieved_scores=retrieved_scores,
            all_chunks_in_index=all_chunks,
            relevance_mapper=mapper,
            k=5,
            latency_ms=12.5,
        )

        assert res.hit_at_k == 1.0
        assert res.mrr == 1.0
        assert res.precision_at_k == pytest.approx(0.4, rel=1e-3)
        assert res.recall_at_k == pytest.approx(2.0 / 3.0, rel=1e-3)
        assert res.context_precision == pytest.approx(0.8333, rel=1e-3)
        assert res.context_recall == pytest.approx(1.0, rel=1e-3)
        assert res.all_evidence_hit == 1.0

    def test_zero_retrieval_metrics(self):
        """When no retrieved chunk is relevant."""
        ev = EvidenceItem(doc_id="doc1", quote="evidence", char_start=100, char_end=200)
        q = Question(
            id="q_zero",
            question="None found?",
            doc_id="doc1",
            section="sec",
            evidence=[ev],
            reference_answer="ans",
            type="factual",
            difficulty="easy",
        )
        c_rel = Chunk("c_rel", "doc1", "text", 100, 200, 20, "fixed")
        c_irr1 = Chunk("c_irr1", "doc1", "text", 500, 600, 20, "fixed")
        c_irr2 = Chunk("c_irr2", "doc1", "text", 700, 800, 20, "fixed")

        all_chunks = [c_rel, c_irr1, c_irr2]
        retrieved = [c_irr1, c_irr2]

        mapper = RelevanceMapper(min_overlap_chars=40)
        res = evaluate_query_retrieval(
            question=q,
            retrieved_chunks=retrieved,
            retrieved_scores=[0.9, 0.8],
            all_chunks_in_index=all_chunks,
            relevance_mapper=mapper,
            k=2,
            latency_ms=5.0,
        )

        assert res.hit_at_k == 0.0
        assert res.mrr == 0.0
        assert res.precision_at_k == 0.0
        assert res.recall_at_k == 0.0
        assert res.context_precision == 0.0
        assert res.context_recall == 0.0
        assert res.all_evidence_hit == 0.0


class TestIntervalCoverage:
    def test_disjoint_and_overlapping_intervals(self):
        # Gold span: [0, 100) -> len 100
        # Chunks: [10, 30) (20 chars), [25, 50) (merged [10, 50) = 40 chars), [70, 90) (20 chars)
        chunks = [(10, 30), (25, 50), (70, 90)]
        cov = compute_interval_coverage(0, 100, chunks)
        # Expected: (50 - 10) + (90 - 70) = 40 + 20 = 60
        assert cov == 60


class TestBootstrapCI:
    def test_deterministic_bootstrap_ci(self):
        data = [0.8, 0.9, 1.0, 0.7, 0.85, 0.95]
        mean1, lo1, hi1 = compute_bootstrap_ci(data, seed=42)
        mean2, lo2, hi2 = compute_bootstrap_ci(data, seed=42)
        assert mean1 == mean2
        assert lo1 == lo2
        assert hi1 == hi2
        assert lo1 <= mean1 <= hi1


class TestWilcoxonPaired:
    def test_wilcoxon_all_zero_differences(self):
        """Scipy wilcoxon fails if all differences are zero. We must handle gracefully."""
        a = [1.0, 1.0, 0.8, 0.5]
        b = [1.0, 1.0, 0.8, 0.5]
        res = compute_wilcoxon_paired(a, b)
        assert res.p_value == 1.0
        assert res.effect_size == 0.0
        assert "zero" in res.note.lower()

    def test_wilcoxon_different_arrays(self):
        a = [1.0, 1.0, 0.8, 0.9, 0.7, 0.95]
        b = [0.2, 0.1, 0.3, 0.0, 0.2, 0.1]
        res = compute_wilcoxon_paired(a, b)
        assert res.p_value < 0.05
        assert res.effect_size > 0.5


class TestRandomBaseline:
    def test_random_baseline_deterministic_and_scores_low(self):
        ev = EvidenceItem(doc_id="doc1", quote="evidence", char_start=100, char_end=200)
        q = Question(
            id="q1",
            question="sample query?",
            doc_id="doc1",
            section="sec",
            evidence=[ev],
            reference_answer="ans",
            type="factual",
            difficulty="easy",
        )
        # Create 100 synthetic chunks where only 1 is relevant
        chunks = [
            Chunk(f"c_{i}", "doc1", f"text {i}", i * 1000 + 100, i * 1000 + 300, 20, "fixed")
            for i in range(100)
        ]
        # Make chunk 0 relevant
        chunks[0] = Chunk("c_0", "doc1", "text", 100, 200, 20, "fixed")

        mapper = RelevanceMapper(min_overlap_chars=40)
        res1 = evaluate_random_baseline([q], chunks, mapper, k=5, seed=42)
        res2 = evaluate_random_baseline([q], chunks, mapper, k=5, seed=42)

        assert res1[0].retrieved_chunk_ids == res2[0].retrieved_chunk_ids
        assert len(res1) == 1
