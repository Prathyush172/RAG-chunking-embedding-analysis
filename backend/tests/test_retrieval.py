"""
tests/test_retrieval.py — Tests for embedding, FAISS indexing, caching, and retrieval.

Tests:
- Embeddings are L2-normalised (norm approx 1.0) and deterministic.
- Query and passage prefixes are applied per model.
- Self-retrieval sanity: exact chunk text query retrieves that chunk at rank 1.
- Caching: second run is a cache hit; config changes invalidate cache.
- Truncation rate computed correctly on a synthetic example.
- Retrieval returns exactly k results, sorted by score descending, with unique chunk ids.
- Latency helper returns the right stats on a fake timer.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.core.chunkers import Chunk
from app.core.embedders import ModelConfig, ModelEmbedder, load_models_config
from app.core.index import FaissIndexManager, compute_cache_key, compute_corpus_hash
from app.core.retrieval import (
    LatencyStats,
    RetrievalPipeline,
    compute_latency_stats,
)


@pytest.fixture(scope="module")
def models_cfg():
    return load_models_config()


@pytest.fixture(scope="module")
def minilm_cfg(models_cfg):
    return models_cfg["minilm"]


@pytest.fixture(scope="module")
def bge_cfg(models_cfg):
    return models_cfg["bge_small"]


@pytest.fixture(scope="module")
def e5_cfg(models_cfg):
    return models_cfg["e5_small"]


@pytest.fixture
def sample_chunks():
    return [
        Chunk(
            chunk_id="doc1_fixed_0",
            doc_id="doc1",
            text="The Transmission Control Protocol provides reliable in-order stream delivery.",
            char_start=0,
            char_end=75,
            token_count=12,
            strategy="fixed",
            section="1. Intro",
        ),
        Chunk(
            chunk_id="doc1_fixed_75",
            doc_id="doc1",
            text="Domain Name System maps human-readable names to numeric IP addresses.",
            char_start=75,
            char_end=145,
            token_count=11,
            strategy="fixed",
            section="2. DNS",
        ),
        Chunk(
            chunk_id="doc1_fixed_145",
            doc_id="doc1",
            text="Hypertext Transfer Protocol is a stateless application-level request-response protocol.",
            char_start=145,
            char_end=232,
            token_count=13,
            strategy="fixed",
            section="3. HTTP",
        ),
    ]


class TestEmbeddings:

    def test_l2_normalisation(self, minilm_cfg, sample_chunks):
        embedder = ModelEmbedder(minilm_cfg, seed=42)
        res = embedder.embed_passages(sample_chunks)
        norms = np.linalg.norm(res.embeddings, axis=1)
        for norm in norms:
            assert np.isclose(norm, 1.0, atol=1e-5), f"Embedding norm {norm} not close to 1.0"

    def test_deterministic(self, minilm_cfg, sample_chunks):
        e1 = ModelEmbedder(minilm_cfg, seed=42).embed_passages(sample_chunks)
        e2 = ModelEmbedder(minilm_cfg, seed=42).embed_passages(sample_chunks)
        assert np.allclose(e1.embeddings, e2.embeddings, atol=1e-6)

    def test_prefixes_applied(self, e5_cfg, sample_chunks):
        """Verify model prefixes from models.yaml are applied before encoding."""
        embedder = ModelEmbedder(e5_cfg, seed=42)
        with patch.object(embedder._load_model(), "encode", wraps=embedder._load_model().encode) as spy_encode:
            embedder.embed_passages(sample_chunks)
            call_args = spy_encode.call_args[0][0]
            assert all(text.startswith("passage: ") for text in call_args)

        with patch.object(embedder._load_model(), "encode", wraps=embedder._load_model().encode) as spy_encode:
            embedder.embed_query("connection reset")
            call_args = spy_encode.call_args[0][0]
            assert call_args[0].startswith("query: connection reset")

    def test_truncation_rate_synthetic(self, minilm_cfg):
        """Test truncation rate calculation when texts exceed max_seq_length."""
        embedder = ModelEmbedder(minilm_cfg)
        # minilm has max_seq_length = 256
        short_text = "This is a brief passage."
        long_text = "word " * 300  # ~300 words will exceed 256 tokens

        rate_short = embedder.compute_truncation_rate([short_text], is_passage=True)
        assert rate_short == 0.0

        rate_long = embedder.compute_truncation_rate([long_text], is_passage=True)
        assert rate_long == 1.0

        rate_mixed = embedder.compute_truncation_rate([short_text, long_text], is_passage=True)
        assert rate_mixed == 0.5


class TestFaissIndexAndCaching:

    def test_cache_hit_and_invalidation(self, minilm_cfg, sample_chunks, tmp_path):
        manager = FaissIndexManager(artifacts_dir=tmp_path)
        embedder = ModelEmbedder(minilm_cfg, seed=42)
        emb_res = embedder.embed_passages(sample_chunks)

        chunk_cfg = {"strategy": "fixed", "chunk_tokens": 128, "overlap_pct": 0.0}
        model_dict = {"model_id": "minilm", "hf_path": minilm_cfg.hf_path}
        key1 = compute_cache_key(chunk_cfg, model_dict, corpus_hash="hash_a", exclude_front_matter=True)

        # 1. First build: miss -> save
        art1 = manager.build_and_save(
            embeddings=emb_res.embeddings,
            chunks=sample_chunks,
            cache_key=key1,
            truncation_rate=0.0,
            embedding_time=0.1,
            chunking_time=0.05,
        )
        assert art1.is_cache_hit is False

        # 2. Second read: hit
        art2 = manager.load_from_cache(key1)
        assert art2 is not None
        assert art2.is_cache_hit is True
        assert len(art2.chunks) == 3

        # 3. Changing chunk config -> different key -> cache miss
        chunk_cfg_changed = {"strategy": "fixed", "chunk_tokens": 256, "overlap_pct": 0.0}
        key_changed = compute_cache_key(chunk_cfg_changed, model_dict, corpus_hash="hash_a", exclude_front_matter=True)
        assert key_changed != key1
        assert manager.load_from_cache(key_changed) is None

        # 4. Changing corpus hash -> different key -> cache miss
        key_corpus_changed = compute_cache_key(chunk_cfg, model_dict, corpus_hash="hash_b", exclude_front_matter=True)
        assert key_corpus_changed != key1
        assert manager.load_from_cache(key_corpus_changed) is None

    def test_clear_cache(self, tmp_path):
        manager = FaissIndexManager(artifacts_dir=tmp_path)
        (tmp_path / "dummy_key").mkdir()
        (tmp_path / "dummy_key" / "index.faiss").write_bytes(b"test")
        assert manager.clear_cache() == 1
        assert not (tmp_path / "dummy_key").exists()


class TestRetrievalAndSelfRetrievalSanity:

    @pytest.mark.parametrize("model_id", ["minilm", "bge_small", "e5_small"])
    def test_self_retrieval_sanity(self, model_id, sample_chunks, tmp_path):
        """Querying with the exact text of a chunk must return that chunk at rank 1."""
        models = load_models_config()
        m_cfg = models[model_id]
        embedder = ModelEmbedder(m_cfg, seed=42)
        emb_res = embedder.embed_passages(sample_chunks)

        manager = FaissIndexManager(artifacts_dir=tmp_path)
        key = f"test_{model_id}"
        art = manager.build_and_save(
            embeddings=emb_res.embeddings,
            chunks=sample_chunks,
            cache_key=key,
            truncation_rate=0.0,
            embedding_time=0.1,
            chunking_time=0.05,
        )

        for target_chunk in sample_chunks:
            q_emb = embedder.embed_query(target_chunk.text)
            scores, indices = art.index.search(q_emb, k=3)
            top_idx = indices[0][0]
            top_chunk = sample_chunks[top_idx]
            assert top_chunk.chunk_id == target_chunk.chunk_id, (
                f"Model {model_id}: expected {target_chunk.chunk_id} at rank 1, got {top_chunk.chunk_id}"
            )
            assert scores[0][0] > scores[0][1], "Rank 1 score should be strictly greater than rank 2"

    def test_retrieval_returns_k_results_sorted(self, tmp_path, sample_chunks):
        pipeline = RetrievalPipeline(artifacts_dir=tmp_path)
        # mock index
        chunk_cfg = {"strategy": "fixed", "chunk_tokens": 128, "overlap_pct": 0.0, "label": "test"}
        res = pipeline.retrieve("DNS query", chunk_cfg, "minilm", k=2)
        assert len(res.results) == 2
        assert res.results[0].rank == 1
        assert res.results[1].rank == 2
        assert res.results[0].score >= res.results[1].score
        assert res.results[0].chunk_id != res.results[1].chunk_id
        assert res.latency_ms > 0.0


class TestLatencyStats:

    def test_compute_latency_stats(self):
        fake_latencies = [10.0, 12.0, 14.0, 16.0, 20.0, 22.0, 24.0, 26.0, 28.0, 100.0]
        stats = compute_latency_stats(fake_latencies)
        assert stats.count == 10
        assert stats.median_ms == 21.0
        assert stats.p95_ms == 100.0
        assert stats.mean_ms == 27.2
        assert stats.std_ms > 0.0
