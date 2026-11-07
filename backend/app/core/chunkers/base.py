"""
chunkers/base.py — Base class and Chunk dataclass for all chunking strategies.

Every chunk carries:
  chunk_id    : str  — "{doc_id}_{strategy}_{char_start}"
  doc_id      : str  — RFC identifier (e.g. "tcp")
  text        : str  — the chunk text
  char_start  : int  — inclusive start in the cleaned document
  char_end    : int  — exclusive end in the cleaned document
  token_count : int  — tiktoken cl100k_base token count
  section     : str | None — closest section heading label (e.g. "3.1. Title")
  strategy    : str  — "fixed" | "sentence" | "semantic"
  metadata    : dict — strategy-specific extras (flags, etc.)

Invariant (enforced in chunk() and tested): chunk.text == cleaned_doc[chunk.char_start:chunk.char_end]
"""
from __future__ import annotations

import hashlib
import statistics
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import tiktoken

from ..sections import find_section_for_offset


# ---------------------------------------------------------------------------
# Shared encoder — initialised once per process
# ---------------------------------------------------------------------------

def get_tokenizer() -> tiktoken.Encoding:
    """Return the shared cl100k_base tokenizer (cached by tiktoken)."""
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, enc: tiktoken.Encoding | None = None) -> int:
    """Count tiktoken cl100k_base tokens for a text string."""
    if enc is None:
        enc = get_tokenizer()
    return len(enc.encode(text))


def split_oversized_text(
    text: str,
    char_start: int,
    char_end: int,
    max_tokens: int,
    enc: tiktoken.Encoding | None = None,
) -> list[tuple[int, int]]:
    """
    Split text[char_start:char_end] into line-boundary chunks of at most max_tokens.
    Returns a list of (sub_char_start, sub_char_end) absolute character offset tuples into text.
    Every sub-chunk has token_count <= max_tokens and is non-empty.
    """
    if enc is None:
        enc = get_tokenizer()

    block = text[char_start:char_end]
    lines: list[tuple[int, int]] = []
    pos = 0
    for line in block.splitlines(keepends=True):
        lines.append((pos, pos + len(line)))
        pos += len(line)

    if not lines:
        return []

    spans: list[tuple[int, int]] = []
    line_idx = 0
    while line_idx < len(lines):
        sub_start_rel = lines[line_idx][0]
        curr_end_rel = lines[line_idx][1]
        line_tok = len(enc.encode(block[sub_start_rel:curr_end_rel]))

        # Handle a single line that by itself exceeds max_tokens
        if line_tok > max_tokens:
            tok_ids = enc.encode(block[sub_start_rel:curr_end_rel])
            p = 0
            while p < len(tok_ids):
                sub_toks = tok_ids[p : p + max_tokens]
                rel_p_start = len(enc.decode(tok_ids[:p]))
                rel_p_end = len(enc.decode(tok_ids[: p + len(sub_toks)]))
                abs_s = char_start + sub_start_rel + rel_p_start
                abs_e = char_start + sub_start_rel + rel_p_end
                if abs_e > abs_s:
                    spans.append((abs_s, abs_e))
                p += max_tokens
            line_idx += 1
            continue

        # Greedily pack subsequent lines into this chunk
        j = line_idx + 1
        while j < len(lines):
            cand_end_rel = lines[j][1]
            cand_tok = len(enc.encode(block[sub_start_rel:cand_end_rel]))
            if cand_tok <= max_tokens:
                curr_end_rel = cand_end_rel
                j += 1
            else:
                break

        abs_s = char_start + sub_start_rel
        abs_e = char_start + curr_end_rel
        if abs_e > abs_s:
            spans.append((abs_s, abs_e))
        line_idx = j

    return spans


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """One chunk produced by a chunking strategy."""
    chunk_id: str
    doc_id: str
    text: str
    char_start: int
    char_end: int
    token_count: int
    strategy: str
    section: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def verify_invariant(self, cleaned_doc: str) -> bool:
        """Return True if text == cleaned_doc[char_start:char_end]."""
        return self.text == cleaned_doc[self.char_start : self.char_end]


@dataclass
class ChunkResult:
    """Container returned by BaseChunker.chunk()."""
    chunks: list[Chunk]
    elapsed_seconds: float
    strategy: str
    config: dict  # the chunking config parameters used


# ---------------------------------------------------------------------------
# Base chunker
# ---------------------------------------------------------------------------

class BaseChunker(ABC):
    """
    Abstract base for all chunking strategies.

    Sub-classes must implement `_do_chunk()` and declare `strategy: str`.
    The base class handles timing (median of 3 runs), front-matter filtering,
    section assignment from char_start, invariant checking, and chunk_id generation.
    """

    strategy: str = ""

    def __init__(self, **kwargs: object) -> None:
        self._enc = get_tokenizer()

    def chunk(
        self,
        text: str,
        doc_id: str,
        sections: list[dict] | None = None,
        verify: bool = True,
        exclude_front_matter: bool = True,
    ) -> ChunkResult:
        """
        Chunk text and return a ChunkResult.
        Timing is the median of 3 runs.
        """
        # Determine body start offset if front matter is excluded
        body_start = 0
        if exclude_front_matter and sections:
            body_start = sections[0].get("char_start", 0) if isinstance(sections[0], dict) else sections[0].char_start

        target_text = text[body_start:] if body_start > 0 else text

        # Measure 3 runs, take median
        run_times: list[float] = []
        last_chunks: list[Chunk] = []

        for r in range(3):
            t0 = time.perf_counter()
            chunks_run = self._do_chunk(target_text, doc_id, sections or [])
            run_times.append(time.perf_counter() - t0)
            if r == 0:
                last_chunks = chunks_run

        elapsed = statistics.median(run_times)

        # Shift offsets if front matter was excluded so char_start/end map to full text
        if body_start > 0:
            for c in last_chunks:
                c.char_start += body_start
                c.char_end += body_start
                # Re-slice from original text to ensure exact match
                c.text = text[c.char_start : c.char_end]

        # Assign section labels based on the section containing char_start
        if sections:
            for c in last_chunks:
                sec = find_section_for_offset(sections, c.char_start)
                if sec is not None:
                    c.section = sec.label if hasattr(sec, "label") else sec.get("label")
                else:
                    c.section = None

        # Generate chunk_ids
        for c in last_chunks:
            c.chunk_id = _make_chunk_id(doc_id, self.strategy, c.char_start)

        if verify:
            for c in last_chunks:
                if not c.verify_invariant(text):
                    raise ValueError(
                        f"Offset invariant violated for chunk_id={c.chunk_id!r}: "
                        f"text[{c.char_start}:{c.char_end}] != {c.text!r}"
                    )

        return ChunkResult(
            chunks=last_chunks,
            elapsed_seconds=elapsed,
            strategy=self.strategy,
            config=self._config_dict(),
        )

    @abstractmethod
    def _do_chunk(
        self,
        text: str,
        doc_id: str,
        sections: list[dict],
    ) -> list[Chunk]:
        """Produce raw chunks for text."""
        ...

    @abstractmethod
    def _config_dict(self) -> dict:
        """Return a JSON-serialisable dict describing this chunker's config."""
        ...

    def _count(self, text: str) -> int:
        return count_tokens(text, self._enc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk_id(doc_id: str, strategy: str, char_start: int) -> str:
    return f"{doc_id}_{strategy}_{char_start}"
