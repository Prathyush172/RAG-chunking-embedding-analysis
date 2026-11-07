"""
backend/app/core/retrieval.py — RAG retrieval engine, latency benchmarking, and run manifests.

Coordinates:
1. Document chunking across all 4 RFCs with exclude_front_matter support
2. Model embedding with passage prefixes and truncation tracking
3. FAISS IndexFlatIP exact retrieval with disk caching
4. Per-query latency timing (query embed + FAISS search) with 5-query warm-up
5. Production of RunSummary objects with complete manifests
"""
from __future__ import annotations

import logging
import math
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from .chunkers import Chunk, build_chunker
from .embedders import ModelConfig, ModelEmbedder, get_library_versions, load_models_config
from .index import FaissIndexManager, IndexArtifacts, compute_cache_key, compute_corpus_hash
from .sections import parse_sections, sections_to_dict

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    section: Optional[str]
    char_start: int
    char_end: int
    text: str
    score: float
    rank: int


@dataclass
class RetrievalResult:
    query: str
    results: list[RetrievedChunk]
    latency_ms: float  # single query latency in milliseconds


@dataclass
class LatencyStats:
    mean_ms: float
    median_ms: float
    p95_ms: float
    std_ms: float
    count: int

    def to_dict(self) -> dict[str, float]:
        return {
            "mean_ms": self.mean_ms,
            "median_ms": self.median_ms,
            "p95_ms": self.p95_ms,
            "std_ms": self.std_ms,
            "count": self.count,
        }


@dataclass
class RunSummary:
    chunk_config: dict[str, Any]
    model_id: str
    model_name: str
    chunk_count: int
    avg_tokens_per_chunk: float
    chunking_time_seconds: float
    embedding_time_seconds: float
    index_build_time_seconds: float
    total_preprocessing_time_seconds: float
    index_size_mb: float
    truncation_rate: float
    latency_stats: Optional[LatencyStats] = None
    cache_key: str = ""
    is_cache_hit: bool = False
    device: str = "cpu"
    seed: int = 42
    corpus_hash: str = ""
    library_versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.latency_stats:
            d["latency_stats"] = self.latency_stats.to_dict()
        return d


def compute_latency_stats(latencies_ms: list[float]) -> LatencyStats:
    """Calculate mean, median, p95, and std dev over query latency measurements."""
    if not latencies_ms:
        return LatencyStats(0.0, 0.0, 0.0, 0.0, 0)
    sorted_lats = sorted(latencies_ms)
    n = len(sorted_lats)
    mean = statistics.mean(sorted_lats)
    median = statistics.median(sorted_lats)
    std = statistics.stdev(sorted_lats) if n > 1 else 0.0
    p95_idx = min(int(math.ceil(0.95 * n)) - 1, n - 1)
    p95 = sorted_lats[max(p95_idx, 0)]
    return LatencyStats(
        mean_ms=round(mean, 3),
        median_ms=round(median, 3),
        p95_ms=round(p95, 3),
        std_ms=round(std, 3),
        count=n,
    )


class RetrievalPipeline:
    """
    Unified retrieval pipeline over the full RFC corpus.
    """

    def __init__(
        self,
        clean_dir: Path | None = None,
        artifacts_dir: Path | None = None,
        seed: int = 42,
    ) -> None:
        self.clean_dir = clean_dir or (REPO_ROOT / "data" / "clean")
        self.artifacts_dir = artifacts_dir or (REPO_ROOT / "artifacts")
        self.seed = seed
        self.index_manager = FaissIndexManager(self.artifacts_dir)
        self.models_config = load_models_config()
        self.corpus_hash = compute_corpus_hash(self.clean_dir)

    def get_or_build_index(
        self,
        chunk_config: dict[str, Any],
        model_id: str,
        exclude_front_matter: bool = True,
        progress_cb: Callable[[str, float], None] | None = None,
    ) -> tuple[IndexArtifacts, RunSummary]:
        """
        Check disk cache or build chunking -> embedding -> FAISS index pipeline.
        Returns (IndexArtifacts, RunSummary).
        """
        if model_id not in self.models_config:
            raise ValueError(f"Unknown model_id: {model_id}. Available: {list(self.models_config.keys())}")

        m_cfg = self.models_config[model_id]
        cache_key = compute_cache_key(
            chunk_config=chunk_config,
            model_config=asdict(m_cfg),
            corpus_hash=self.corpus_hash,
            exclude_front_matter=exclude_front_matter,
        )

        cached = self.index_manager.load_from_cache(cache_key)
        if cached is not None:
            summary = RunSummary(
                chunk_config=chunk_config,
                model_id=m_cfg.model_id,
                model_name=m_cfg.name,
                chunk_count=len(cached.chunks),
                avg_tokens_per_chunk=round(sum(c.token_count for c in cached.chunks) / max(len(cached.chunks), 1), 1),
                chunking_time_seconds=cached.chunking_time_seconds,
                embedding_time_seconds=cached.embedding_time_seconds,
                index_build_time_seconds=cached.build_time_seconds,
                total_preprocessing_time_seconds=round(cached.chunking_time_seconds + cached.embedding_time_seconds + cached.build_time_seconds, 3),
                index_size_mb=round(cached.index_size_mb, 3),
                truncation_rate=round(cached.truncation_rate, 4),
                cache_key=cache_key,
                is_cache_hit=True,
                device="cpu",
                seed=self.seed,
                corpus_hash=self.corpus_hash,
                library_versions=get_library_versions(),
            )
            return cached, summary

        # Cache miss — execute full pipeline
        logger.info("Executing full pipeline for chunk_config=%s model=%s", chunk_config.get("label"), model_id)

        # 1. Chunk all RFCs
        if progress_cb:
            progress_cb("chunking", 0.1)

        strategy = chunk_config["strategy"]
        kwargs = {k: v for k, v in chunk_config.items() if k not in ("strategy", "label")}
        chunker = build_chunker(strategy, **kwargs)

        all_chunks: list[Chunk] = []
        chunking_times: list[float] = []

        for p in sorted(self.clean_dir.glob("*.txt")):
            doc_id = p.stem
            text = p.read_text(encoding="utf-8")
            sections = sections_to_dict(parse_sections(text))
            res = chunker.chunk(text, doc_id, sections=sections, verify=True, exclude_front_matter=exclude_front_matter)
            all_chunks.extend(res.chunks)
            chunking_times.append(res.elapsed_seconds)

        total_chunking_time = sum(chunking_times)

        # 2. Embed passages
        if progress_cb:
            progress_cb("embedding", 0.4)

        embedder = ModelEmbedder(m_cfg, seed=self.seed)
        emb_res = embedder.embed_passages(all_chunks)

        # 3. Build FAISS index & save to cache
        if progress_cb:
            progress_cb("indexing", 0.8)

        artifacts = self.index_manager.build_and_save(
            embeddings=emb_res.embeddings,
            chunks=all_chunks,
            cache_key=cache_key,
            truncation_rate=emb_res.truncation_rate,
            embedding_time=emb_res.elapsed_seconds,
            chunking_time=total_chunking_time,
        )

        total_prep = round(total_chunking_time + emb_res.elapsed_seconds + artifacts.build_time_seconds, 3)

        summary = RunSummary(
            chunk_config=chunk_config,
            model_id=m_cfg.model_id,
            model_name=m_cfg.name,
            chunk_count=len(all_chunks),
            avg_tokens_per_chunk=round(sum(c.token_count for c in all_chunks) / max(len(all_chunks), 1), 1),
            chunking_time_seconds=round(total_chunking_time, 3),
            embedding_time_seconds=round(emb_res.elapsed_seconds, 3),
            index_build_time_seconds=round(artifacts.build_time_seconds, 3),
            total_preprocessing_time_seconds=total_prep,
            index_size_mb=round(artifacts.index_size_mb, 3),
            truncation_rate=round(emb_res.truncation_rate, 4),
            cache_key=cache_key,
            is_cache_hit=False,
            device="cpu",
            seed=self.seed,
            corpus_hash=self.corpus_hash,
            library_versions=emb_res.library_versions,
        )

        if progress_cb:
            progress_cb("done", 1.0)

        return artifacts, summary

    def retrieve(
        self,
        query: str,
        chunk_config: dict[str, Any],
        model_id: str,
        k: int = 5,
        exclude_front_matter: bool = True,
    ) -> RetrievalResult:
        """
        Embed query, execute exact search in FAISS IndexFlatIP, and return ranked chunks with latency.
        """
        artifacts, _ = self.get_or_build_index(chunk_config, model_id, exclude_front_matter)
        m_cfg = self.models_config[model_id]
        embedder = ModelEmbedder(m_cfg, seed=self.seed)

        t0 = time.perf_counter()
        q_emb = embedder.embed_query(query)
        scores, indices = artifacts.index.search(q_emb, k)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        results: list[RetrievedChunk] = []
        for rank, (score, idx) in enumerate(zip(scores[0], indices[0]), 1):
            if idx < 0 or idx >= len(artifacts.chunks):
                continue
            chunk = artifacts.chunks[idx]
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    section=chunk.section,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    text=chunk.text,
                    score=float(score),
                    rank=rank,
                )
            )

        return RetrievalResult(
            query=query,
            results=results,
            latency_ms=round(elapsed_ms, 3),
        )

    def benchmark_latency(
        self,
        queries: list[str],
        chunk_config: dict[str, Any],
        model_id: str,
        k: int = 5,
        warmup_queries: int = 5,
    ) -> LatencyStats:
        """
        Measure per-query retrieval latency after warmup_queries.
        Reports LatencyStats (mean, median, p95, std dev in ms).
        """
        artifacts, _ = self.get_or_build_index(chunk_config, model_id)
        m_cfg = self.models_config[model_id]
        embedder = ModelEmbedder(m_cfg, seed=self.seed)

        # Warmup queries
        warmup_list = (queries * ((warmup_queries // len(queries)) + 1))[:warmup_queries] if queries else ["warmup query"] * warmup_queries
        for wq in warmup_list:
            q_emb = embedder.embed_query(wq)
            artifacts.index.search(q_emb, k)

        # Timed queries
        latencies_ms: list[float] = []
        for q in queries:
            t0 = time.perf_counter()
            q_emb = embedder.embed_query(q)
            artifacts.index.search(q_emb, k)
            latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        return compute_latency_stats(latencies_ms)
