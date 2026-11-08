"""
backend/app/core/index.py — FAISS index builder, row-to-chunk mapper, and disk caching.

Uses FAISS IndexFlatIP (inner product search) on L2-normalised vectors (equivalent to cosine similarity).
Builds a unified index over all four RFCs combined.
Caches chunks, embeddings, and FAISS index files on disk under artifacts/ keyed by a SHA-256 hash
of (chunk_config + model_id + prefixes + corpus_hash + exclude_front_matter).
Never serves stale cache.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
import faiss

from .chunkers import Chunk

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"


def compute_corpus_hash(clean_dir: Path | None = None) -> str:
    """Compute SHA-256 hash of all cleaned RFC files concatenated in sorted order."""
    if clean_dir is None:
        clean_dir = REPO_ROOT / "data" / "clean"
    h = hashlib.sha256()
    for p in sorted(clean_dir.glob("*.txt")):
        h.update(p.name.encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()


def compute_cache_key(
    chunk_config: dict[str, Any],
    model_config: dict[str, Any],
    corpus_hash: str,
    exclude_front_matter: bool = True,
) -> str:
    """
    Generate deterministic hash key:
    hash(chunk_config + model_id + prefixes + corpus_hash + exclude_front_matter).
    """
    payload = {
        "chunk_config": chunk_config,
        "model_id": model_config.get("model_id"),
        "hf_path": model_config.get("hf_path"),
        "query_prefix": model_config.get("query_prefix", ""),
        "passage_prefix": model_config.get("passage_prefix", ""),
        "corpus_hash": corpus_hash,
        "exclude_front_matter": exclude_front_matter,
    }
    dumped = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:24]


@dataclass
class IndexArtifacts:
    index: faiss.IndexFlatIP
    chunks: list[Chunk]
    row_to_chunk_id: list[str]
    cache_key: str
    build_time_seconds: float
    index_size_mb: float
    truncation_rate: float
    embedding_time_seconds: float
    chunking_time_seconds: float
    is_cache_hit: bool = False


class FaissIndexManager:
    """
    Manages building, saving, loading, and searching FAISS IndexFlatIP indexes.
    """

    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self.artifacts_dir = artifacts_dir or ARTIFACTS_DIR
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_path(self, cache_key: str) -> Path:
        return self.artifacts_dir / cache_key

    def is_cached(self, cache_key: str) -> bool:
        cache_dir = self.get_cache_path(cache_key)
        return (
            (cache_dir / "index.faiss").exists()
            and (cache_dir / "chunks.json").exists()
            and (cache_dir / "meta.json").exists()
        )

    def load_from_cache(self, cache_key: str) -> Optional[IndexArtifacts]:
        if not self.is_cached(cache_key):
            logger.info("Cache miss for key %s", cache_key)
            return None

        logger.info("Cache hit for key %s", cache_key)
        cache_dir = self.get_cache_path(cache_key)

        index = faiss.read_index(str(cache_dir / "index.faiss"))
        with open(cache_dir / "chunks.json", encoding="utf-8") as f:
            chunks_raw = json.load(f)
        chunks = [
            Chunk(
                chunk_id=c["chunk_id"],
                doc_id=c["doc_id"],
                text=c["text"],
                char_start=c["char_start"],
                char_end=c["char_end"],
                token_count=c["token_count"],
                strategy=c["strategy"],
                section=c.get("section"),
                metadata=c.get("metadata", {}),
            )
            for c in chunks_raw
        ]

        with open(cache_dir / "meta.json", encoding="utf-8") as f:
            meta = json.load(f)

        row_to_chunk_id = [c.chunk_id for c in chunks]

        return IndexArtifacts(
            index=index,
            chunks=chunks,
            row_to_chunk_id=row_to_chunk_id,
            cache_key=cache_key,
            build_time_seconds=meta.get("build_time_seconds", 0.0),
            index_size_mb=meta.get("index_size_mb", 0.0),
            truncation_rate=meta.get("truncation_rate", 0.0),
            embedding_time_seconds=meta.get("embedding_time_seconds", 0.0),
            chunking_time_seconds=meta.get("chunking_time_seconds", 0.0),
            is_cache_hit=True,
        )

    def build_and_save(
        self,
        embeddings: np.ndarray,
        chunks: list[Chunk],
        cache_key: str,
        truncation_rate: float,
        embedding_time: float,
        chunking_time: float,
    ) -> IndexArtifacts:
        """
        Build FAISS IndexFlatIP on embeddings, save artifacts to disk, and return IndexArtifacts.
        """
        dim = embeddings.shape[1]
        t0 = time.perf_counter()

        index = faiss.IndexFlatIP(dim)
        index.add(embeddings.astype(np.float32))

        build_time = time.perf_counter() - t0

        cache_dir = self.get_cache_path(cache_key)
        cache_dir.mkdir(parents=True, exist_ok=True)

        index_file = cache_dir / "index.faiss"
        faiss.write_index(index, str(index_file))
        index_size_mb = index_file.stat().st_size / (1024 * 1024)

        # Save chunks
        chunks_json = [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "text": c.text,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "token_count": c.token_count,
                "strategy": c.strategy,
                "section": c.section,
                "metadata": c.metadata,
            }
            for c in chunks
        ]
        with open(cache_dir / "chunks.json", "w", encoding="utf-8") as f:
            json.dump(chunks_json, f)

        # Save metadata
        meta = {
            "cache_key": cache_key,
            "dim": dim,
            "count": len(chunks),
            "build_time_seconds": build_time,
            "index_size_mb": index_size_mb,
            "truncation_rate": truncation_rate,
            "embedding_time_seconds": embedding_time,
            "chunking_time_seconds": chunking_time,
            "created_at": time.time(),
        }
        with open(cache_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        row_to_chunk_id = [c.chunk_id for c in chunks]

        return IndexArtifacts(
            index=index,
            chunks=chunks,
            row_to_chunk_id=row_to_chunk_id,
            cache_key=cache_key,
            build_time_seconds=build_time,
            index_size_mb=index_size_mb,
            truncation_rate=truncation_rate,
            embedding_time_seconds=embedding_time,
            chunking_time_seconds=chunking_time,
            is_cache_hit=False,
        )

    def list_cached_configs(self) -> list[str]:
        """List cache keys for all cached index directories."""
        keys = []
        if self.artifacts_dir.exists():
            for child in self.artifacts_dir.iterdir():
                if child.is_dir() and (child / "meta.json").exists():
                    keys.append(child.name)
        return keys

    def clear_cache(self) -> int:
        """Remove all cached artifacts. Returns count of deleted directories."""
        count = 0
        if self.artifacts_dir.exists():
            for child in self.artifacts_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                    count += 1
        return count
