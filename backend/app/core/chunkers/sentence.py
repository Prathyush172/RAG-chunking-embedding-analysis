"""
chunkers/sentence.py — Sentence-level greedy-packing chunker.

Strategy:
1. Pre-process the text to handle RFC quirks before sentence splitting.
2. Split into sentences with NLTK PunktSentenceTokenizer (English), augmented
   with extra abbreviation rules to prevent false splits on:
   - "e.g.", "i.e.", "etc.", "vs.", "No.", "Sec.", "Fig."
   - Section numbers appearing mid-sentence: "in Section 3.1."
   - RFC-specific: "req.", "resp.", "addr.", "std."
   - ASCII diagram lines (never split inside a block of +–|–+ characters)
3. Rejoin hard-wrapped RFC lines into logical sentences before tokenizing.
   RFC text hard-wraps at 72 chars. A "continuation" line is indented and
   does not start with a capital letter or a list bullet.
4. Greedily pack whole sentences into chunks up to max_tokens (N).
   - overlap_sentences: 0 (no overlap) or 1 (last sentence of prev chunk
     becomes first sentence of next chunk).
5. A single sentence exceeding N tokens becomes its own chunk and is flagged
   with metadata["oversized"] = True.

Invariant: chunk.text == cleaned_doc[char_start:char_end]
The char offsets are located by whitespace-normalised search in the cleaned doc.
"""
from __future__ import annotations

import re
from typing import Optional

import nltk
from nltk.tokenize import PunktSentenceTokenizer

from .base import BaseChunker, Chunk, count_tokens, get_tokenizer, split_oversized_text


# ---------------------------------------------------------------------------
# NLTK tokenizer setup
# ---------------------------------------------------------------------------

def _build_tokenizer() -> PunktSentenceTokenizer:
    """Build a PunktSentenceTokenizer with RFC-aware abbreviations."""
    try:
        tokenizer = nltk.data.load("tokenizers/punkt_tab/english.pickle")
    except (LookupError, FileNotFoundError):
        try:
            tokenizer = nltk.data.load("tokenizers/punkt/english.pickle")
        except (LookupError, FileNotFoundError):
            # Fall back to a default instance
            tokenizer = PunktSentenceTokenizer()

    # Extra abbreviations to avoid false splits
    extra_abbrevs = [
        "e.g", "i.e", "etc", "vs", "no", "sec", "fig", "req",
        "resp", "addr", "std", "ref", "approx", "dept", "est",
        "max", "min", "avg", "oct", "jan", "feb", "mar", "apr",
        "jun", "jul", "aug", "sep", "nov", "dec",
        # RFC-specific
        "rfc", "udp", "tcp", "ip", "ttl", "ack", "syn", "fin",
        "rst", "mss", "mtu", "uri", "url", "http", "dns", "ftp",
    ]
    # PunktSentenceTokenizer stores abbrevs in _params.abbrev_types
    if hasattr(tokenizer, "_params"):
        for abbr in extra_abbrevs:
            tokenizer._params.abbrev_types.add(abbr)

    return tokenizer


_TOKENIZER: PunktSentenceTokenizer | None = None


def get_sent_tokenizer() -> PunktSentenceTokenizer:
    global _TOKENIZER
    if _TOKENIZER is None:
        _TOKENIZER = _build_tokenizer()
    return _TOKENIZER


# ---------------------------------------------------------------------------
# ASCII art detection
# ---------------------------------------------------------------------------

# A line that belongs to an ASCII diagram: starts with optional whitespace then
# +, |, or is a pure +---+ border line.
_ART_LINE_RE = re.compile(r"^\s*[\+\|]", re.MULTILINE)
_ART_BORDER_RE = re.compile(r"^\s*\+[-+]+\+", re.MULTILINE)


def _is_art_line(line: str) -> bool:
    return bool(_ART_LINE_RE.match(line) or _ART_BORDER_RE.match(line))


# ---------------------------------------------------------------------------
# Line-joining for hard-wrapped RFC text
# ---------------------------------------------------------------------------

def _join_wrapped_lines(text: str) -> str:
    """
    Rejoin hard-wrapped RFC paragraph lines into single logical lines.

    Rules:
    - Lines inside ASCII art blocks (containing +–| chars) are NEVER joined.
    - A blank line always ends a paragraph — start fresh.
    - A line starting with a digit/letter/bullet that looks like a new sentence
      is kept separate.
    - Otherwise an indented continuation line is appended to the previous.

    Returns the text with paragraphs unwrapped (preserving blank lines).
    """
    lines = text.split("\n")
    result: list[str] = []
    in_art = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Blank line: flush and reset
        if not stripped:
            result.append("")
            in_art = False
            continue

        # Detect ASCII art entry
        if _is_art_line(line):
            in_art = True
            result.append(line)
            continue

        # Exit art block when we hit a non-art non-blank line
        if in_art:
            # art blocks end at blank lines (handled above) or non-art lines
            in_art = False

        # Decide whether to join with previous line
        if (
            result
            and result[-1]  # previous non-blank
            and not _is_art_line(result[-1])
            and line.startswith("   ")  # indented continuation
            and stripped  # not blank
            and not re.match(r"^[A-Z0-9\-]", stripped)  # not a new sentence start
            and not re.match(r"^[-*•]\s", stripped)  # not a list bullet
            and not re.match(r"^\d+\.\s", stripped)   # not a numbered list
            and not re.match(r"^[A-Z][a-z].*:\s*$", stripped)  # not a label line
        ):
            result[-1] = result[-1].rstrip() + " " + stripped
        else:
            result.append(line)

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Sentence splitter
# ---------------------------------------------------------------------------

def split_sentences(text: str) -> list[tuple[int, int, str]]:
    """
    Split *text* into sentences, handling RFC quirks.

    Returns list of (char_start, char_end, sentence_text) tuples,
    where the offsets are into *text* (exact slice from cleaned doc).

    Rules:
    - ASCII art blocks (lines with +, |) are not split internally.
    - Abbreviations like "e.g.", "i.e." do not trigger false splits.
    - Section numbers like "3.1." or "Section 3.1." do not trigger false splits.
    """
    masked = list(text)

    # 1. Detect ASCII art blocks and mask their interiors so NLTK ignores them
    art_regions: list[tuple[int, int]] = []
    art_block_re = re.compile(
        r"(?:^[ \t]*\+[-=+]+\+[ \t]*\n(?:(?:[ \t]*[\+\|][^\n]*\n)*(?:[ \t]*\+[-=+]+\+[ \t]*\n)?))",
        re.MULTILINE,
    )
    for m in art_block_re.finditer(text):
        art_regions.append((m.start(), m.end()))
        for idx in range(m.start() + 1, m.end() - 1):
            if masked[idx] != "\n":
                masked[idx] = " "

    # 2. Mask periods in "e.g." and "i.e." so NLTK never splits inside them
    for m in re.finditer(r"\b(?:e\.g|i\.e)\.", text, re.IGNORECASE):
        for idx in range(m.start(), m.end()):
            if masked[idx] == ".":
                masked[idx] = " "

    # 3. Mask trailing periods in section numbers (e.g. "3.1.", "Section 3.1.")
    for m in re.finditer(r"\b\d+(?:\.\d+)*\.", text):
        # mask the trailing dot
        dot_idx = m.end() - 1
        if masked[dot_idx] == ".":
            masked[dot_idx] = " "

    masked_text = "".join(masked)
    tokenizer = get_sent_tokenizer()

    # Get sentence spans from NLTK using the masked text
    spans: list[tuple[int, int]] = list(tokenizer.span_tokenize(masked_text))

    # Merge spans that overlap art regions back to the full block boundaries
    merged_spans: list[tuple[int, int]] = []
    for start, end in spans:
        overlapping_art = [
            (as_, ae) for (as_, ae) in art_regions if as_ < end and ae > start
        ]
        if overlapping_art:
            art_start = min(as_ for as_, ae in overlapping_art)
            art_end = max(ae for as_, ae in overlapping_art)
            merged_spans.append((min(start, art_start), max(end, art_end)))
        else:
            merged_spans.append((start, end))

    # Deduplicate and sort
    seen: set[tuple[int, int]] = set()
    result: list[tuple[int, int, str]] = []
    for start, end in sorted(merged_spans):
        if (start, end) in seen:
            continue
        seen.add((start, end))
        sent_text = text[start:end].strip()
        if sent_text:
            result.append((start, end, sent_text))

    return result


# ---------------------------------------------------------------------------
# Sentence chunker
# ---------------------------------------------------------------------------

class SentenceChunker(BaseChunker):
    """
    Sentence-level greedy-packing chunker.

    Args:
        chunk_tokens:       Max tokens per chunk. One of {128, 256, 512}.
        overlap_sentences:  0 (no overlap) or 1 (last sentence repeated).
    """

    strategy = "sentence"

    def __init__(
        self,
        chunk_tokens: int = 256,
        overlap_sentences: int = 0,
    ) -> None:
        super().__init__()
        if chunk_tokens <= 0:
            raise ValueError(f"chunk_tokens must be positive, got {chunk_tokens}")
        if overlap_sentences not in (0, 1):
            raise ValueError(f"overlap_sentences must be 0 or 1, got {overlap_sentences}")
        self.chunk_tokens = chunk_tokens
        self.overlap_sentences = overlap_sentences

    def _do_chunk(
        self,
        text: str,
        doc_id: str,
        sections: list[dict],
    ) -> list[Chunk]:
        enc = self._enc
        sentences = split_sentences(text)

        if not sentences:
            return []

        # Precompute individual sentence token counts
        sent_tokens = [len(enc.encode(s[2])) for s in sentences]
        m_sents = len(sentences)

        chunks: list[Chunk] = []
        i = 0

        while i < m_sents:
            # Check if this sentence alone exceeds chunk_tokens
            if sent_tokens[i] > self.chunk_tokens:
                sub_spans = split_oversized_text(
                    text, sentences[i][0], sentences[i][1], self.chunk_tokens, enc
                )
                for s_start, s_end in sub_spans:
                    sub_text = text[s_start:s_end]
                    sub_tokens = len(enc.encode(sub_text))
                    chunks.append(
                        Chunk(
                            chunk_id="",
                            doc_id=doc_id,
                            text=sub_text,
                            char_start=s_start,
                            char_end=s_end,
                            token_count=sub_tokens,
                            strategy=self.strategy,
                            metadata={
                                "split_from_oversized": True,
                                "sentence_count": 1,
                            },
                        )
                    )
                i += 1
                continue

            # Greedily pack sentences starting at i
            cand_start = sentences[i][0]
            j = i
            while j < m_sents:
                if sent_tokens[j] > self.chunk_tokens:
                    # Next sentence is oversized, so terminate the current chunk before it
                    break
                cand_end = sentences[j][1]
                cand_tok = len(enc.encode(text[cand_start:cand_end]))
                if cand_tok <= self.chunk_tokens:
                    j += 1
                else:
                    break

            if j == i:
                j = i + 1

            chunk_start = sentences[i][0]
            chunk_end = sentences[j - 1][1]
            chunk_text = text[chunk_start:chunk_end]
            tok_count = len(enc.encode(chunk_text))

            chunks.append(
                Chunk(
                    chunk_id="",
                    doc_id=doc_id,
                    text=chunk_text,
                    char_start=chunk_start,
                    char_end=chunk_end,
                    token_count=tok_count,
                    strategy=self.strategy,
                    metadata={
                        "split_from_oversized": False,
                        "sentence_count": (j - i),
                    },
                )
            )

            # Overlap: start next chunk with the LAST sentence of this chunk if multi-sentence
            if self.overlap_sentences == 1 and (j - 1) > i:
                i = j - 1
            else:
                i = j

        return chunks

    def _config_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "chunk_tokens": self.chunk_tokens,
            "overlap_sentences": self.overlap_sentences,
        }
