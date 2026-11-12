
"""
Embedding model loader, encoder, and truncation tracker.

Models:
- sentence-transformers/all-MiniLM-L6-v2
- BAAI/bge-small-en-v1.5
- intfloat/e5-small-v2

CPU-only inference.
Tracks overlength inputs and safely truncates them before encoding.
Returns float32 embeddings with optional L2 normalization.
"""

from __future__ import annotations

import gc
import logging
import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
    embeddings: np.ndarray
    elapsed_seconds: float
    truncation_rate: float
    model_id: str
    device: str
    library_versions: dict[str, str]


def load_models_config(
    config_path: Path | None = None,
) -> dict[str, ModelConfig]:
    """Load model configurations from YAML."""

    if config_path is None:
        config_path = REPO_ROOT / "configs" / "models.yaml"

    with open(config_path, encoding="utf-8") as file:
        data = yaml.safe_load(file)

    if not isinstance(data, dict) or "models" not in data:
        raise ValueError(
            f"Invalid model configuration file: {config_path}"
        )

    result: dict[str, ModelConfig] = {}

    for item in data["models"]:
        cfg = ModelConfig(
            model_id=item["model_id"],
            name=item["name"],
            hf_path=item["hf_path"],
            max_seq_length=int(item["max_seq_length"]),
            embedding_dim=int(item["embedding_dim"]),
            query_prefix=item.get("query_prefix", ""),
            passage_prefix=item.get("passage_prefix", ""),
            normalize=item.get("normalize", True),
            description=item.get("description", ""),
            notes=item.get("notes", ""),
        )

        if cfg.max_seq_length <= 0:
            raise ValueError(
                f"Invalid max_seq_length for {cfg.model_id}"
            )

        result[cfg.model_id] = cfg

    return result


def get_library_versions() -> dict[str, str]:
    """Return runtime library versions."""

    import sentence_transformers
    import transformers

    return {
        "python": platform.python_version(),
        "torch": str(torch.__version__),
        "sentence_transformers": sentence_transformers.__version__,
        "transformers": transformers.__version__,
        "platform": platform.platform(),
        "processor": platform.processor() or "CPU",
    }


class ModelEmbedder:
    """
    SentenceTransformer wrapper with:
    - Model-specific prefixes
    - Explicit token-length enforcement
    - Truncation tracking
    - L2 normalization
    """

    def __init__(
        self,
        config: ModelConfig,
        seed: int = 42,
    ) -> None:
        self.config = config
        self.seed = seed
        self._model = None
        self._tokenizer = None

        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        torch.manual_seed(self.seed)

    def _load_model(self):
        """Load the embedding model once."""

        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info(
                "Loading model %s (%s)",
                self.config.model_id,
                self.config.hf_path,
            )

            try:
                self._model = SentenceTransformer(
                    self.config.hf_path,
                    device="cpu",
                    local_files_only=True,
                )
            except Exception as offline_error:
                logger.warning(
                    "Local-only model loading failed for %s: %s. "
                    "Trying normal loading.",
                    self.config.model_id,
                    offline_error,
                )

                self._model = SentenceTransformer(
                    self.config.hf_path,
                    device="cpu",
                )

            self._model.max_seq_length = self.config.max_seq_length
            self._tokenizer = self._model.tokenizer

            logger.info(
                "Model loaded: %s | Maximum sequence length: %d",
                self.config.model_id,
                self.config.max_seq_length,
            )

        return self._model

    @property
    def tokenizer(self):
        """Return the model tokenizer, loading the model if needed."""

        if self._tokenizer is None:
            self._load_model()

        return self._tokenizer

    def _encode_token_ids(
        self,
        text: str,
        truncation: bool = False,
    ) -> list[int]:
        """
        Tokenize text without displaying long-input warnings.

        When truncation=True, the tokenizer enforces max_seq_length.
        """

        tokenizer = self.tokenizer

        try:
            token_ids = tokenizer.encode(
                text,
                add_special_tokens=True,
                truncation=truncation,
                max_length=(
                    self.config.max_seq_length
                    if truncation
                    else None
                ),
                verbose=False,
            )
        except TypeError:
            # Compatibility fallback for tokenizer versions
            # that do not accept the verbose argument.
            token_ids = tokenizer.encode(
                text,
                add_special_tokens=True,
                truncation=truncation,
                max_length=(
                    self.config.max_seq_length
                    if truncation
                    else None
                ),
            )

        return token_ids

    def _truncate_texts(
        self,
        texts: list[str],
    ) -> list[str]:
        """
        Truncate overlength inputs before model.encode().

        Texts that already fit are returned unchanged.
        Special tokens are removed before decoding so that the
        model tokenizer can add them correctly during encoding.
        """

        if not texts:
            return []

        max_len = self.config.max_seq_length
        tokenizer = self.tokenizer

        safe_texts: list[str] = []

        for text in texts:
            token_ids = self._encode_token_ids(
                text,
                truncation=False,
            )

            if len(token_ids) <= max_len:
                safe_texts.append(text)
                continue

            truncated_ids = self._encode_token_ids(
                text,
                truncation=True,
            )

            safe_text = tokenizer.decode(
                truncated_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )

            # Check the decoded text again because decoding and
            # re-tokenizing can occasionally change token boundaries.
            while safe_text:
                check_ids = self._encode_token_ids(
                    safe_text,
                    truncation=False,
                )

                if len(check_ids) <= max_len:
                    break

                truncated_ids = truncated_ids[:-1]

                safe_text = tokenizer.decode(
                    truncated_ids,
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=False,
                )

            safe_texts.append(safe_text)

        return safe_texts

    def compute_truncation_rate(
        self,
        texts: list[str],
        is_passage: bool = True,
    ) -> float:
        """Calculate the fraction of inputs exceeding the model limit."""

        if not texts:
            return 0.0

        prefix = (
            self.config.passage_prefix
            if is_passage
            else self.config.query_prefix
        )

        max_len = self.config.max_seq_length
        truncated_count = 0

        for text in texts:
            full_text = prefix + text if prefix else text

            token_count = len(
                self._encode_token_ids(
                    full_text,
                    truncation=False,
                )
            )

            if token_count > max_len:
                truncated_count += 1

        return truncated_count / len(texts)

    def _normalize(
        self,
        embeddings: np.ndarray,
    ) -> np.ndarray:
        """Convert embeddings to float32 and apply L2 normalization."""

        arr = np.asarray(embeddings, dtype=np.float32)

        if arr.size == 0:
            return arr

        if self.config.normalize:
            norms = np.linalg.norm(
                arr,
                axis=1,
                keepdims=True,
            )

            norms = np.maximum(norms, 1e-12)
            arr = arr / norms

        return arr.astype(np.float32, copy=False)

    def embed_passages(
        self,
        chunks: list[Chunk],
        batch_size: int = 8,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> EmbeddingResult:
        """Embed document chunks with passage prefixes."""

        if not chunks:
            return EmbeddingResult(
                embeddings=np.empty(
                    (0, self.config.embedding_dim),
                    dtype=np.float32,
                ),
                elapsed_seconds=0.0,
                truncation_rate=0.0,
                model_id=self.config.model_id,
                device="cpu",
                library_versions=get_library_versions(),
            )

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        gc.collect()

        model = self._load_model()

        texts = [chunk.text for chunk in chunks]

        # Measure truncation before modifying the original text.
        trunc_rate = self.compute_truncation_rate(
            texts,
            is_passage=True,
        )

        prefix = self.config.passage_prefix

        prefixed_texts = [
            prefix + text if prefix else text
            for text in texts
        ]

        # Enforce the configured token limit.
        safe_texts = self._truncate_texts(prefixed_texts)

        logger.info(
            "Embedding %d passages | Model: %s | "
            "Truncation rate: %.2f%%",
            len(safe_texts),
            self.config.model_id,
            trunc_rate * 100,
        )

        start_time = time.perf_counter()

        embeddings = model.encode(
            safe_texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=False,
            convert_to_numpy=True,
            device="cpu",
        )

        elapsed = time.perf_counter() - start_time

        arr = self._normalize(embeddings)

        if arr.ndim != 2:
            raise ValueError(
                f"Expected 2D embeddings, received shape {arr.shape}"
            )

        if arr.shape[1] != self.config.embedding_dim:
            raise ValueError(
                f"Embedding dimension mismatch for "
                f"{self.config.model_id}: expected "
                f"{self.config.embedding_dim}, received {arr.shape[1]}"
            )

        gc.collect()

        if progress_cb is not None:
            progress_cb(len(chunks), len(chunks))

        return EmbeddingResult(
            embeddings=arr,
            elapsed_seconds=elapsed,
            truncation_rate=trunc_rate,
            model_id=self.config.model_id,
            device="cpu",
            library_versions=get_library_versions(),
        )

    def embed_queries(
        self,
        queries: list[str],
        batch_size: int = 8,
    ) -> np.ndarray:
        """Embed search queries with model-specific query prefixes."""

        if not queries:
            return np.empty(
                (0, self.config.embedding_dim),
                dtype=np.float32,
            )

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        model = self._load_model()

        prefix = self.config.query_prefix

        full_queries = [
            prefix + query if prefix else query
            for query in queries
        ]

        safe_queries = self._truncate_texts(full_queries)

        embeddings = model.encode(
            safe_queries,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=False,
            convert_to_numpy=True,
            device="cpu",
        )

        arr = self._normalize(embeddings)

        if arr.ndim != 2:
            raise ValueError(
                f"Expected 2D query embeddings, received shape {arr.shape}"
            )

        if arr.shape[1] != self.config.embedding_dim:
            raise ValueError(
                f"Query embedding dimension mismatch for "
                f"{self.config.model_id}: expected "
                f"{self.config.embedding_dim}, received {arr.shape[1]}"
            )

        return arr

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single search query."""

        return self.embed_queries([query])
