"""
chunkers/fixed.py — Fixed-size (sliding window) chunker.

Splits the document into chunks of exactly N tiktoken cl100k_base tokens,
advancing by a stride = N - overlap_tokens on each step.

Overlap is specified as a fraction of N (e.g. 0.15 = 15%).
The final chunk may be smaller than N tokens.

Invariant: chunk.text == cleaned_doc[chunk.char_start:chunk.char_end]
"""
from __future__ import annotations

import math
from typing import Optional

import tiktoken

from .base import BaseChunker, Chunk, count_tokens


class FixedChunker(BaseChunker):
    """
    Fixed-size sliding-window chunker.

    Args:
        chunk_tokens: Maximum tokens per chunk (N). One of {128, 256, 512}.
        overlap_pct:  Overlap fraction (0.0 or 0.15).
    """

    strategy = "fixed"

    def __init__(self, chunk_tokens: int = 256, overlap_pct: float = 0.0) -> None:
        super().__init__()
        if chunk_tokens <= 0:
            raise ValueError(f"chunk_tokens must be positive, got {chunk_tokens}")
        if not (0.0 <= overlap_pct < 1.0):
            raise ValueError(f"overlap_pct must be in [0, 1), got {overlap_pct}")
        self.chunk_tokens = chunk_tokens
        self.overlap_pct = overlap_pct
        self.overlap_tokens = math.floor(chunk_tokens * overlap_pct)
        self.stride = chunk_tokens - self.overlap_tokens

    def _do_chunk(
        self,
        text: str,
        doc_id: str,
        sections: list[dict],
    ) -> list[Chunk]:
        enc = self._enc
        # Encode the entire document once
        all_token_ids = enc.encode(text)
        total_tokens = len(all_token_ids)

        if total_tokens == 0:
            return []

        chunks: list[Chunk] = []
        pos = 0  # token position

        while pos < total_tokens:
            end_pos = min(pos + self.chunk_tokens, total_tokens)
            window_ids = all_token_ids[pos:end_pos]

            # Decode back to text
            chunk_text = enc.decode(window_ids)

            # Locate char_start: find this chunk's text in the document starting
            # from roughly where we expect it.  We track character offset via
            # decoding the prefix.
            prefix_text = enc.decode(all_token_ids[:pos])
            char_start = len(prefix_text)
            char_end = char_start + len(chunk_text)

            # Safety: clamp to actual doc length
            char_end = min(char_end, len(text))
            chunk_text = text[char_start:char_end]

            if chunk_text:  # never emit empty chunks
                chunks.append(
                    Chunk(
                        chunk_id="",  # filled by base class
                        doc_id=doc_id,
                        text=chunk_text,
                        char_start=char_start,
                        char_end=char_end,
                        token_count=len(window_ids),
                        strategy=self.strategy,
                    )
                )

            if end_pos >= total_tokens:
                break
            pos += self.stride

        return chunks

    def _config_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "chunk_tokens": self.chunk_tokens,
            "overlap_pct": self.overlap_pct,
            "overlap_tokens": self.overlap_tokens,
            "stride": self.stride,
        }
