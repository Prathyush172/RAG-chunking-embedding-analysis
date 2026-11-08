"""
backend/app/core/embedders.py — Embedding model loader, encoder, and truncation tracker.

Driven entirely by configs/models.yaml:
- sentence-transformers/all-MiniLM-L6-v2 (no prefixes)
- BAAI/bge-small-en-v1.5 (query prefix, no passage prefix)
- intfloat/e5-small-v2 (query: / passage: prefixes)

All embeddings are L2-normalised (unit norm) float32 vectors.
CPU-only inference with fixed seed.
Records truncation rate (% of chunks exceeding model's max_seq_length under its tokenizer).
"""
from __future__ import annotations

import gc
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import torch
import yaml

from .chunkers import Chunk

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ModelConfig:
    model_id: str
    name: str
    hf_path: str
    max_seq_length: int
    embedding_dim: int
    query_prefix: str
    passage_prefix: str
    normalize: bool = True
    description: str = ""
    notes: str = ""


@dataclass
class EmbeddingResult:
    embeddings: np.ndarray       # (N, D) float32 L2-normalised
    elapsed_seconds: float
    truncation_rate: float       # fraction [0.0, 1.0] exceeding model's max_seq_length
    model_id: str
    device: str
    library_versions: dict[str, str]


def load_models_config(config_path: Path | None = None) -> dict[str, ModelConfig]:
    """Load configs/models.yaml and return mapping of model_id -> ModelConfig."""
    if config_path is None:
        config_path = REPO_ROOT / "configs" / "models.yaml"
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    result = {}
    for item in data["models"]:
        cfg = ModelConfig(
            model_id=item["model_id"],
            name=item["name"],
            hf_path=item["hf_path"],
            max_seq_length=item["max_seq_length"],
            embedding_dim=item["embedding_dim"],
            query_prefix=item.get("query_prefix", ""),
            passage_prefix=item.get("passage_prefix", ""),
            normalize=item.get("normalize", True),
            description=item.get("description", ""),
            notes=item.get("notes", ""),
        )
        result[cfg.model_id] = cfg
    return result


def get_library_versions() -> dict[str, str]:
    """Return dictionary of relevant runtime library versions and environment info."""
    import sentence_transformers
    import transformers

    return {
        "python": platform.python_version(),
        "torch": torch.__version__,
        "sentence_transformers": sentence_transformers.__version__,
        "transformers": transformers.__version__,
        "platform": platform.platform(),
        "processor": platform.processor() or "CPU",
    }


class ModelEmbedder:
    """
    Wrapper around SentenceTransformer with model-specific prefixes,
    truncation tracking, and exact L2-normalisation.
    """

    def __init__(self, config: ModelConfig, seed: int = 42) -> None:
        self.config = config
        self.seed = seed
        self._model = None
        self._tokenizer = None

        # Ensure offline caching is used if files exist locally
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        # Set PyTorch deterministic seed for CPU
        torch.manual_seed(self.seed)

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading model %s (%s)", self.config.model_id, self.config.hf_path)
            try:
                self._model = SentenceTransformer(self.config.hf_path, device="cpu", local_files_only=True)
            except Exception:
                self._model = SentenceTransformer(self.config.hf_path, device="cpu")
            self._model.max_seq_length = self.config.max_seq_length
            self._tokenizer = self._model.tokenizer
        return self._model

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            self._load_model()
        return self._tokenizer

    def compute_truncation_rate(self, texts: list[str], is_passage: bool = True) -> float:
        """
        Compute fraction of texts whose token count under this model's tokenizer
        (including any model prefix) exceeds max_seq_length.
        """
        if not texts:
            return 0.0

        prefix = self.config.passage_prefix if is_passage else self.config.query_prefix
        tokenizer = self.tokenizer
        max_len = self.config.max_seq_length

        truncated_count = 0
        for t in texts:
            full_text = prefix + t if prefix else t
            # count tokens under model's native tokenizer
            num_tokens = len(tokenizer.encode(full_text, truncation=False))
            if num_tokens > max_len:
                truncated_count += 1

        return truncated_count / len(texts)

    def embed_passages(
        self,
        chunks: list[Chunk],
        batch_size: int = 32,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> EmbeddingResult:
        """
        Embed a list of document chunks (applying passage prefix).
        Returns EmbeddingResult with L2-normalised vectors and truncation rate.
        """
        gc.collect()
        model = self._load_model()
        texts = [c.text for c in chunks]

        # 1. Truncation rate under model's tokenizer
        trunc_rate = self.compute_truncation_rate(texts, is_passage=True)

        # 2. Add passage prefix
        prefix = self.config.passage_prefix
        prefixed_texts = [prefix + t for t in texts] if prefix else texts

        # 3. Batch encode with timing
        gc.collect()
        t0 = time.perf_counter()
        embeddings = model.encode(
            prefixed_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=self.config.normalize,
            convert_to_numpy=True,
        )
        elapsed = time.perf_counter() - t0
        gc.collect()

        arr = np.array(embeddings, dtype=np.float32)

        # Extra safety guarantee: strictly L2-normalise
        if self.config.normalize:
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1e-12
            arr = arr / norms

        if progress_cb:
            progress_cb(len(chunks), len(chunks))

        return EmbeddingResult(
            embeddings=arr,
            elapsed_seconds=elapsed,
            truncation_rate=trunc_rate,
            model_id=self.config.model_id,
            device="cpu",
            library_versions=get_library_versions(),
        )

    def embed_queries(self, queries: list[str], batch_size: int = 32) -> np.ndarray:
        """
        Embed a list of search queries in batch (applying query prefix).
        Returns (N, D) L2-normalised float32 array.
        """
        if not queries:
            return np.empty((0, self.config.embedding_dim), dtype=np.float32)
        model = self._load_model()
        prefix = self.config.query_prefix
        full_queries = [prefix + q for q in queries] if prefix else queries

        emb = model.encode(
            full_queries,
            batch_size=batch_size,
            normalize_embeddings=self.config.normalize,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        arr = np.array(emb, dtype=np.float32)
        if self.config.normalize:
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1e-12
            arr = arr / norms
        return arr

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single search query (applying query prefix).
        Returns (1, D) L2-normalised float32 array.
        """
        return self.embed_queries([query])
