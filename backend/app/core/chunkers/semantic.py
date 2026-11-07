"""
chunkers/semantic.py — Semantic (similarity-based) chunker.

Algorithm:
1. Split the document into sentences (using the same RFC-aware splitter as
   the sentence chunker).
2. Embed each sentence using the FIXED chunking embedder (all-MiniLM-L6-v2),
   independent of the model under test. This keeps chunk boundaries identical
   across all embedding-model experiments.
3. Compute cosine similarity between adjacent sentences (window=1).
4. Identify breakpoints where similarity falls below the configured percentile
   threshold (default 25th percentile of all pairwise similarities).
5. Split at every breakpoint, then merge adjacent segments to stay within
   max_tokens (512 by default). Never produce a chunk < min_tokens (64).
6. If merging would exceed max_tokens, force a split regardless of similarity.

The boundary embedder model path is taken from configs/models.yaml
(chunking_embedder section), defaulting to sentence-transformers/all-MiniLM-L6-v2.

Invariant: chunk.text == cleaned_doc[char_start:char_end]
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from .base import BaseChunker, Chunk, count_tokens, get_tokenizer, split_oversized_text
from .sentence import split_sentences

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_chunking_model_path() -> str:
    """Read the fixed chunking embedder model path from configs/models.yaml."""
    cfg_path = _REPO_ROOT / "configs" / "models.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
        hf_path = cfg.get("chunking_embedder", {}).get("hf_path", _DEFAULT_MODEL)
        return hf_path
    return _DEFAULT_MODEL


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two L2-normalised vectors."""
    return float(np.dot(a, b))


class SemanticChunker(BaseChunker):
    """
    Semantic chunker using cosine-similarity boundary detection.

    Args:
        max_tokens:            Max tokens per chunk (default 512).
        min_tokens:            Min tokens per chunk (default 64).
        similarity_percentile: Breakpoint threshold percentile (default 25).
        model_path:            HuggingFace model path for the boundary embedder.
                               Defaults to the value in configs/models.yaml.
    """

    strategy = "semantic"

    def __init__(
        self,
        max_tokens: int = 512,
        min_tokens: int = 64,
        similarity_percentile: int = 25,
        model_path: str | None = None,
    ) -> None:
        super().__init__()
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")
        if min_tokens <= 0:
            raise ValueError(f"min_tokens must be positive, got {min_tokens}")
        if min_tokens > max_tokens:
            raise ValueError("min_tokens must be <= max_tokens")
        if not (0 <= similarity_percentile <= 100):
            raise ValueError(f"similarity_percentile must be in [0, 100]")

        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.similarity_percentile = similarity_percentile
        self._model_path = model_path or _load_chunking_model_path()
        self._model = None  # lazy-loaded
        self._emb_cache: dict[int, np.ndarray] = {}  # hash(text) -> sentence embeddings

    def _get_model(self):
        """Lazy-load the sentence-transformers model (uses local cache)."""
        if self._model is None:
            import os
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("Loading chunking embedder: %s", self._model_path)
                try:
                    self._model = SentenceTransformer(self._model_path, local_files_only=True)
                except Exception:
                    self._model = SentenceTransformer(self._model_path)
            except ImportError:
                raise ImportError(
                    "sentence-transformers is required for the semantic chunker. "
                    "Install it with: pip install sentence-transformers"
                )
        return self._model

    def _embed_sentences(self, sentences: list[str], cache_key: int | None = None) -> np.ndarray:
        """Embed a list of sentences; returns (N, D) normalised float32 array."""
        if cache_key is not None and cache_key in self._emb_cache:
            return self._emb_cache[cache_key]

        model = self._get_model()
        embeddings = model.encode(
            sentences,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )
        arr = np.array(embeddings, dtype=np.float32)
        if cache_key is not None:
            self._emb_cache[cache_key] = arr
        return arr

    def _do_chunk(
        self,
        text: str,
        doc_id: str,
        sections: list[dict],
    ) -> list[Chunk]:
        enc = self._enc

        # 1. Sentence split (RFC-aware)
        sentence_spans = split_sentences(text)
        if not sentence_spans:
            return []

        sent_texts = [s[2] for s in sentence_spans]
        n = len(sent_texts)

        if n == 1:
            char_start, char_end, sent_text = sentence_spans[0]
            chunk_text = text[char_start:char_end]
            tok_count = len(enc.encode(chunk_text))
            if tok_count > self.max_tokens:
                sub_spans = split_oversized_text(text, char_start, char_end, self.max_tokens, enc)
                return [
                    Chunk(
                        chunk_id="",
                        doc_id=doc_id,
                        text=text[s:e],
                        char_start=s,
                        char_end=e,
                        token_count=len(enc.encode(text[s:e])),
                        strategy=self.strategy,
                        metadata={"split_from_oversized": True},
                    )
                    for s, e in sub_spans
                ]
            return [
                Chunk(
                    chunk_id="",
                    doc_id=doc_id,
                    text=chunk_text,
                    char_start=char_start,
                    char_end=char_end,
                    token_count=tok_count,
                    strategy=self.strategy,
                    metadata={"split_from_oversized": False},
                )
            ]

        # 2. Embed sentences (cached by text length and first/last sentence hash)
        cache_key = hash((len(text), sent_texts[0], sent_texts[-1]))
        embeddings = self._embed_sentences(sent_texts, cache_key=cache_key)

        # 3. Compute adjacent cosine similarities (window=1)
        similarities = np.array([
            _cosine_sim(embeddings[i], embeddings[i + 1])
            for i in range(n - 1)
        ])

        # 4. Determine breakpoint threshold
        threshold = float(np.percentile(similarities, self.similarity_percentile))

        # 5. Identify breakpoints
        breakpoints: set[int] = set()
        for i, sim in enumerate(similarities):
            if sim < threshold:
                breakpoints.add(i + 1)

        # 6. Build initial segment list respecting max_tokens
        segments: list[list[int]] = []
        current: list[int] = [0]

        for i in range(1, n):
            cand_seg = current + [i]
            cand_start = sentence_spans[cand_seg[0]][0]
            cand_end = sentence_spans[cand_seg[-1]][1]
            cand_tok = len(enc.encode(text[cand_start:cand_end]))

            force_break = i in breakpoints
            would_exceed = cand_tok > self.max_tokens

            if force_break or would_exceed:
                segments.append(current)
                current = [i]
            else:
                current.append(i)

        segments.append(current)

        # 7. Merge tiny segments (< min_tokens) into neighbours
        merged_segments = _merge_small_segments(
            segments, sent_texts, text, sentence_spans, enc, self.min_tokens, self.max_tokens
        )

        # 8. Build Chunk objects from merged segments, splitting any oversized segments
        chunks: list[Chunk] = []
        for seg in merged_segments:
            if not seg:
                continue
            first_idx = seg[0]
            last_idx = seg[-1]
            char_start = sentence_spans[first_idx][0]
            char_end = sentence_spans[last_idx][1]
            chunk_text = text[char_start:char_end]
            if not chunk_text.strip():
                continue
            tok_count = len(enc.encode(chunk_text))

            if tok_count > self.max_tokens:
                sub_spans = split_oversized_text(text, char_start, char_end, self.max_tokens, enc)
                for s, e in sub_spans:
                    sub_text = text[s:e]
                    chunks.append(
                        Chunk(
                            chunk_id="",
                            doc_id=doc_id,
                            text=sub_text,
                            char_start=s,
                            char_end=e,
                            token_count=len(enc.encode(sub_text)),
                            strategy=self.strategy,
                            metadata={
                                "split_from_oversized": True,
                                "sentence_count": len(seg),
                                "threshold": threshold,
                                "similarity_percentile": self.similarity_percentile,
                            },
                        )
                    )
            else:
                chunks.append(
                    Chunk(
                        chunk_id="",
                        doc_id=doc_id,
                        text=chunk_text,
                        char_start=char_start,
                        char_end=char_end,
                        token_count=tok_count,
                        strategy=self.strategy,
                        metadata={
                            "split_from_oversized": False,
                            "sentence_count": len(seg),
                            "threshold": threshold,
                            "similarity_percentile": self.similarity_percentile,
                        },
                    )
                )

        return chunks

        return chunks

    def _config_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "max_tokens": self.max_tokens,
            "min_tokens": self.min_tokens,
            "similarity_percentile": self.similarity_percentile,
            "model_path": self._model_path,
        }


def _merge_small_segments(
    segments: list[list[int]],
    sent_texts: list[str],
    text: str,
    sentence_spans: list[tuple[int, int, str]],
    enc,
    min_tokens: int,
    max_tokens: int,
) -> list[list[int]]:
    """
    Merge segments that are below min_tokens into an adjacent segment,
    preferring the smaller neighbour. Never exceed max_tokens.
    """
    if not segments:
        return segments

    def seg_tokens(seg: list[int]) -> int:
        start = sentence_spans[seg[0]][0]
        end = sentence_spans[seg[-1]][1]
        return len(enc.encode(text[start:end]))

    # Iterative merge (at most len(segments) passes)
    changed = True
    while changed:
        changed = False
        new_segs: list[list[int]] = []
        i = 0
        while i < len(segments):
            seg = segments[i]
            tok = seg_tokens(seg)
            if tok < min_tokens and len(segments) > 1:
                # Merge with the smaller adjacent neighbour
                prev_tok = seg_tokens(segments[i - 1]) if i > 0 else float("inf")
                next_tok = seg_tokens(segments[i + 1]) if i + 1 < len(segments) else float("inf")
                if prev_tok <= next_tok and i > 0:
                    # Merge into previous
                    combined = (new_segs[-1] if new_segs else segments[i - 1]) + seg
                    if seg_tokens(combined) <= max_tokens:
                        if new_segs:
                            new_segs[-1] = combined
                        else:
                            new_segs.append(combined)
                        changed = True
                        i += 1
                        continue
                elif i + 1 < len(segments):
                    # Merge into next
                    combined = seg + segments[i + 1]
                    if seg_tokens(combined) <= max_tokens:
                        new_segs.append(combined)
                        i += 2
                        changed = True
                        continue
            new_segs.append(seg)
            i += 1
        segments = new_segs

    return segments
