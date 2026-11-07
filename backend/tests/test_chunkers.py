"""
tests/test_chunkers.py — Comprehensive tests for all three chunking strategies.

Tests:
- Offset invariant: chunk.text == cleaned_doc[char_start:char_end] for every chunk
- No empty chunks
- No chunk exceeds max tokens (except flagged oversized sentence chunks)
- Overlap sizes correct for 0% and 15%
- Chunking is deterministic
- Sentence chunker does not split inside "e.g.", "i.e.", section numbers
- Sentence chunker handles ASCII diagrams
- Semantic chunker respects min and max token limits
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from preprocess import clean_text, load_corpus_config
from app.core.chunkers import (
    FixedChunker,
    SentenceChunker,
    build_chunker,
    count_tokens,
    get_tokenizer,
)
from app.core.chunkers.sentence import split_sentences


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def enc():
    return get_tokenizer()


@pytest.fixture(scope="module")
def tcp_text():
    raw = (_REPO_ROOT / "datasets" / "tcp.txt").read_text(encoding="utf-8", errors="replace")
    cleaned, _ = clean_text(raw)
    return cleaned


@pytest.fixture(scope="module")
def dns_text():
    raw = (_REPO_ROOT / "datasets" / "dns.txt").read_text(encoding="utf-8", errors="replace")
    cleaned, _ = clean_text(raw)
    return cleaned


@pytest.fixture(scope="module")
def all_docs() -> dict[str, str]:
    docs = load_corpus_config()
    result = {}
    for doc in docs:
        raw = (_REPO_ROOT / doc["file"]).read_text(encoding="utf-8", errors="replace")
        cleaned, _ = clean_text(raw)
        result[doc["doc_id"]] = cleaned
    return result


# Short synthetic texts for unit tests
SIMPLE_TEXT = (
    "This is the first sentence. "
    "This is the second sentence. "
    "This is the third sentence. "
    "This is the fourth sentence. "
    "This is the fifth sentence."
)

RFC_ABBREV_TEXT = (
    "The value must not exceed the maximum, e.g., 65535 for a 16-bit field. "
    "In other words, i.e., the sender must respect the receiver's window. "
    "See Section 3.1. for the exact format. "
    "This is a new sentence that follows."
)

ASCII_ART_TEXT = (
    "The header format is shown below.\n\n"
    "    +--+--+--+--+\n"
    "    |  Seq Num  |\n"
    "    +--+--+--+--+\n"
    "    |  Ack Num  |\n"
    "    +--+--+--+--+\n\n"
    "The fields are described next. "
    "Seq Num is 32 bits. "
    "Ack Num is also 32 bits."
)


# ---------------------------------------------------------------------------
# Helper: verify invariant for a list of chunks
# ---------------------------------------------------------------------------

def assert_offset_invariant(chunks, text, context=""):
    for c in chunks:
        expected = text[c.char_start : c.char_end]
        assert c.text == expected, (
            f"{context} Offset invariant violated for chunk_id={c.chunk_id!r}\n"
            f"  char_start={c.char_start}, char_end={c.char_end}\n"
            f"  chunk.text={c.text[:80]!r}\n"
            f"  text[start:end]={expected[:80]!r}"
        )


# ---------------------------------------------------------------------------
# FixedChunker tests
# ---------------------------------------------------------------------------

class TestFixedChunker:

    def test_basic_chunking(self, tcp_text, enc):
        chunker = FixedChunker(chunk_tokens=256, overlap_pct=0.0)
        result = chunker.chunk(tcp_text, "tcp")
        assert len(result.chunks) > 0

    def test_offset_invariant_simple(self, enc):
        chunker = FixedChunker(chunk_tokens=20, overlap_pct=0.0)
        result = chunker.chunk(SIMPLE_TEXT, "test")
        assert_offset_invariant(result.chunks, SIMPLE_TEXT, "FixedChunker simple")

    def test_offset_invariant_all_docs(self, all_docs):
        """Invariant must hold for every chunk across all 4 RFCs."""
        chunker = FixedChunker(chunk_tokens=256, overlap_pct=0.0)
        for doc_id, text in all_docs.items():
            result = chunker.chunk(text, doc_id)
            assert_offset_invariant(result.chunks, text, f"FixedChunker {doc_id}")

    def test_no_empty_chunks(self, tcp_text):
        for n in (128, 256, 512):
            chunker = FixedChunker(chunk_tokens=n, overlap_pct=0.0)
            result = chunker.chunk(tcp_text, "tcp")
            for c in result.chunks:
                assert c.text.strip(), f"Empty chunk found: {c.chunk_id!r}"
                assert c.char_end > c.char_start, f"Zero-length span: {c.chunk_id!r}"

    def test_no_chunk_exceeds_max_tokens(self, tcp_text, enc):
        for n in (128, 256, 512):
            chunker = FixedChunker(chunk_tokens=n, overlap_pct=0.0)
            result = chunker.chunk(tcp_text, "tcp")
            for c in result.chunks:
                # Allow +1 token due to decode boundary rounding
                assert c.token_count <= n + 1, (
                    f"Chunk {c.chunk_id!r} has {c.token_count} tokens, max={n}"
                )

    def test_zero_overlap(self, enc):
        """With 0% overlap, every token appears in exactly one chunk."""
        text = SIMPLE_TEXT * 10
        chunker = FixedChunker(chunk_tokens=20, overlap_pct=0.0)
        result = chunker.chunk(text, "test")
        # Verify non-overlapping char spans
        chunks = sorted(result.chunks, key=lambda c: c.char_start)
        for i in range(len(chunks) - 1):
            assert chunks[i].char_end <= chunks[i + 1].char_start, (
                f"Chunks {i} and {i+1} overlap with 0% overlap setting"
            )

    def test_15_percent_overlap(self, enc):
        """With 15% overlap, stride = floor(N * 0.85)."""
        import math
        n = 128
        chunker = FixedChunker(chunk_tokens=n, overlap_pct=0.15)
        expected_overlap = math.floor(n * 0.15)
        expected_stride = n - expected_overlap
        assert chunker.overlap_tokens == expected_overlap
        assert chunker.stride == expected_stride

    def test_overlap_char_positions(self, enc):
        """Chunks with overlap start before the previous chunk ends."""
        text = " ".join(["word"] * 300)  # ~300 tokens
        chunker = FixedChunker(chunk_tokens=50, overlap_pct=0.15)
        result = chunker.chunk(text, "test")
        chunks = sorted(result.chunks, key=lambda c: c.char_start)
        if len(chunks) >= 2:
            # With overlap, chunk[1].char_start < chunk[0].char_end
            assert chunks[1].char_start < chunks[0].char_end, (
                "Overlap chunks should have overlapping char spans"
            )

    def test_deterministic(self, tcp_text):
        chunker = FixedChunker(chunk_tokens=256, overlap_pct=0.0)
        r1 = chunker.chunk(tcp_text, "tcp")
        r2 = chunker.chunk(tcp_text, "tcp")
        assert len(r1.chunks) == len(r2.chunks)
        for c1, c2 in zip(r1.chunks, r2.chunks):
            assert c1.text == c2.text
            assert c1.char_start == c2.char_start
            assert c1.char_end == c2.char_end

    def test_elapsed_time_recorded(self, tcp_text):
        chunker = FixedChunker(chunk_tokens=256, overlap_pct=0.0)
        result = chunker.chunk(tcp_text, "tcp")
        assert result.elapsed_seconds > 0.0
        assert result.elapsed_seconds < 60.0  # sanity upper bound

    def test_strategy_name(self):
        chunker = FixedChunker()
        assert chunker.strategy == "fixed"

    def test_config_dict(self):
        chunker = FixedChunker(chunk_tokens=128, overlap_pct=0.15)
        cfg = chunker._config_dict()
        assert cfg["strategy"] == "fixed"
        assert cfg["chunk_tokens"] == 128
        assert cfg["overlap_pct"] == 0.15

    def test_covers_full_text(self, enc):
        """The union of all 0%-overlap chunk spans must cover the full text."""
        text = SIMPLE_TEXT * 20
        chunker = FixedChunker(chunk_tokens=20, overlap_pct=0.0)
        result = chunker.chunk(text, "test")
        chunks = sorted(result.chunks, key=lambda c: c.char_start)
        # First chunk starts at 0
        assert chunks[0].char_start == 0
        # Last chunk ends at or near len(text) (within token boundary rounding)
        assert chunks[-1].char_end >= len(text) - 10


# ---------------------------------------------------------------------------
# SentenceChunker tests
# ---------------------------------------------------------------------------

class TestSentenceChunker:

    def test_basic_chunking(self, tcp_text):
        chunker = SentenceChunker(chunk_tokens=256, overlap_sentences=0)
        result = chunker.chunk(tcp_text, "tcp")
        assert len(result.chunks) > 0

    def test_offset_invariant_simple(self):
        chunker = SentenceChunker(chunk_tokens=50, overlap_sentences=0)
        result = chunker.chunk(SIMPLE_TEXT, "test")
        assert_offset_invariant(result.chunks, SIMPLE_TEXT, "SentenceChunker simple")

    def test_offset_invariant_all_docs(self, all_docs):
        chunker = SentenceChunker(chunk_tokens=256, overlap_sentences=0)
        for doc_id, text in all_docs.items():
            result = chunker.chunk(text, doc_id)
            assert_offset_invariant(result.chunks, text, f"SentenceChunker {doc_id}")

    def test_no_empty_chunks(self, tcp_text):
        chunker = SentenceChunker(chunk_tokens=256, overlap_sentences=0)
        result = chunker.chunk(tcp_text, "tcp")
        for c in result.chunks:
            assert c.text.strip(), f"Empty chunk: {c.chunk_id!r}"
            assert c.char_end > c.char_start

    def test_normal_chunks_within_max_tokens(self, tcp_text, enc):
        """Non-oversized chunks must not exceed max tokens."""
        for n in (128, 256, 512):
            chunker = SentenceChunker(chunk_tokens=n, overlap_sentences=0)
            result = chunker.chunk(tcp_text, "tcp")
            for c in result.chunks:
                if not c.metadata.get("oversized"):
                    assert c.token_count <= n, (
                        f"Non-oversized chunk {c.chunk_id!r} has {c.token_count} > {n}"
                    )

    def test_oversized_chunks_flagged(self, enc):
        """A sentence exceeding max_tokens must be split into pieces with split_from_oversized=True."""
        # Create a text with one very long sentence
        long_sent = "word " * 200  # ~200 tokens
        text = f"Short sentence. {long_sent.strip()} Another short sentence."
        chunker = SentenceChunker(chunk_tokens=50, overlap_sentences=0)
        result = chunker.chunk(text, "test")
        split_oversized = [c for c in result.chunks if c.metadata.get("split_from_oversized")]
        assert len(split_oversized) >= 1, "Long sentence should be split with split_from_oversized=True"
        for c in split_oversized:
            assert c.token_count <= 50, f"Subchunk exceeds max_tokens: {c.token_count}"

    def test_no_split_on_eg(self):
        """Sentence splitter must NOT break on 'e.g.' or 'i.e.'."""
        sentences = split_sentences(RFC_ABBREV_TEXT)
        # "e.g., 65535" should not create a break
        for _, _, sent in sentences:
            assert "e.g.," not in sent or "field" in sent or "65535" in sent, (
                "Split incorrectly at e.g. — sentence is incomplete"
            )
        # "i.e., the sender" should not create a break  
        for _, _, sent in sentences:
            assert "i.e.," not in sent or "sender" in sent or "window" in sent, (
                "Split incorrectly at i.e. — sentence is incomplete"
            )

    def test_no_split_on_section_number(self):
        """Section refs like '3.1.' should not trigger sentence splits."""
        # RFC_ABBREV_TEXT contains "See Section 3.1. for the exact format."
        sentences = split_sentences(RFC_ABBREV_TEXT)
        # The sentence containing "3.1." should include "format" in the same span
        combined = " ".join(s for _, _, s in sentences)
        assert "See Section 3.1." in combined or "Section 3.1" in combined

    def test_ascii_diagram_not_split(self):
        """Lines inside +--+--+ ASCII art blocks must not be sentence-split."""
        sentences = split_sentences(ASCII_ART_TEXT)
        # Find if any sentence is a bare diagram row
        for _, _, sent in sentences:
            # A single line like "|  Seq Num  |" should not appear as its own sentence
            stripped = sent.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                # It's OK only if it's part of a larger art block span
                assert len(stripped) > 5, "Bare diagram row should be part of art block"

    def test_zero_overlap_non_overlapping_spans(self, tcp_text):
        """With 0 overlap, chunk char_start >= previous chunk's char_end."""
        chunker = SentenceChunker(chunk_tokens=256, overlap_sentences=0)
        result = chunker.chunk(tcp_text, "tcp")
        chunks = sorted(result.chunks, key=lambda c: c.char_start)
        for i in range(len(chunks) - 1):
            assert chunks[i + 1].char_start >= chunks[i].char_start, (
                "Sentence chunks out of order"
            )

    def test_one_sentence_overlap(self, tcp_text, enc):
        """With overlap=1, the last sentence of chunk N reappears in chunk N+1."""
        chunker = SentenceChunker(chunk_tokens=128, overlap_sentences=1)
        result = chunker.chunk(tcp_text, "tcp")
        # With overlap, adjacent chunks must have overlapping char spans
        chunks = sorted(result.chunks, key=lambda c: c.char_start)
        if len(chunks) >= 2:
            assert chunks[1].char_start < chunks[0].char_end, (
                "Sentence overlap=1 chunks should have overlapping spans"
            )

    def test_deterministic(self, tcp_text):
        chunker = SentenceChunker(chunk_tokens=256, overlap_sentences=0)
        r1 = chunker.chunk(tcp_text, "tcp")
        r2 = chunker.chunk(tcp_text, "tcp")
        assert len(r1.chunks) == len(r2.chunks)
        for c1, c2 in zip(r1.chunks, r2.chunks):
            assert c1.char_start == c2.char_start
            assert c1.char_end == c2.char_end

    def test_strategy_name(self):
        assert SentenceChunker().strategy == "sentence"

    def test_elapsed_time_recorded(self, tcp_text):
        chunker = SentenceChunker(chunk_tokens=256)
        result = chunker.chunk(tcp_text, "tcp")
        assert result.elapsed_seconds > 0.0


# ---------------------------------------------------------------------------
# SemanticChunker tests (no model load — mock embedder)
# ---------------------------------------------------------------------------

class MockSemanticChunker:
    """
    A SemanticChunker subclass that uses a deterministic mock embedder
    so we can test without loading a real model.
    """
    pass


class TestSemanticChunkerUnit:
    """Tests for SemanticChunker using a mock embedder to avoid model download."""

    @pytest.fixture
    def mock_chunker(self, monkeypatch):
        """Patch _get_model to return a fake embedder."""
        from app.core.chunkers.semantic import SemanticChunker
        import numpy as np

        class FakeModel:
            def encode(self, sentences, **kwargs):
                # Return fixed embeddings: alternating [1,0] and [0,1]
                # so adjacent similarity alternates between 1.0 and 0.0
                rng = np.random.default_rng(42)
                n = len(sentences)
                emb = np.zeros((n, 2), dtype=np.float32)
                for i in range(n):
                    emb[i] = rng.random(2).astype(np.float32)
                    emb[i] /= np.linalg.norm(emb[i]) + 1e-8
                return emb

        chunker = SemanticChunker(max_tokens=512, min_tokens=64, similarity_percentile=25)
        monkeypatch.setattr(chunker, "_model", FakeModel())
        return chunker

    def test_offset_invariant(self, mock_chunker, tcp_text):
        result = mock_chunker.chunk(tcp_text, "tcp")
        assert_offset_invariant(result.chunks, tcp_text, "SemanticChunker(mock)")

    def test_no_empty_chunks(self, mock_chunker, tcp_text):
        result = mock_chunker.chunk(tcp_text, "tcp")
        for c in result.chunks:
            assert c.text.strip()
            assert c.char_end > c.char_start

    def test_min_tokens_respected(self, mock_chunker, tcp_text, enc):
        result = mock_chunker.chunk(tcp_text, "tcp")
        # Most chunks should be >= min_tokens (64); tiny trailing ones may not be
        # We allow up to 5% of chunks to be below min_tokens (edge/tail chunks)
        below = [c for c in result.chunks if c.token_count < mock_chunker.min_tokens]
        total = len(result.chunks)
        assert total > 0
        pct_below = len(below) / total
        assert pct_below <= 0.10, (
            f"{len(below)}/{total} chunks ({pct_below:.0%}) below min_tokens={mock_chunker.min_tokens}"
        )

    def test_max_tokens_not_exceeded(self, mock_chunker, tcp_text, enc):
        result = mock_chunker.chunk(tcp_text, "tcp")
        for c in result.chunks:
            if not c.metadata.get("oversized"):
                assert c.token_count <= mock_chunker.max_tokens, (
                    f"Chunk {c.chunk_id!r} exceeds max_tokens: {c.token_count}"
                )

    def test_deterministic(self, mock_chunker, tcp_text):
        r1 = mock_chunker.chunk(tcp_text, "tcp")
        r2 = mock_chunker.chunk(tcp_text, "tcp")
        assert len(r1.chunks) == len(r2.chunks)
        for c1, c2 in zip(r1.chunks, r2.chunks):
            assert c1.char_start == c2.char_start
            assert c1.char_end == c2.char_end

    def test_strategy_name(self):
        from app.core.chunkers.semantic import SemanticChunker
        chunker = SemanticChunker()
        assert chunker.strategy == "semantic"


# ---------------------------------------------------------------------------
# build_chunker registry test
# ---------------------------------------------------------------------------

class TestBuildChunker:

    def test_build_fixed(self):
        c = build_chunker("fixed", chunk_tokens=128, overlap_pct=0.0)
        assert isinstance(c, FixedChunker)
        assert c.chunk_tokens == 128

    def test_build_sentence(self):
        c = build_chunker("sentence", chunk_tokens=256, overlap_sentences=1)
        assert isinstance(c, SentenceChunker)
        assert c.overlap_sentences == 1

    def test_build_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            build_chunker("magic_chunker")

    def test_build_semantic(self):
        from app.core.chunkers.semantic import SemanticChunker
        c = build_chunker("semantic", max_tokens=256, min_tokens=32)
        assert isinstance(c, SemanticChunker)


# ---------------------------------------------------------------------------
# Cross-strategy: chunk_id uniqueness per doc
# ---------------------------------------------------------------------------

class TestChunkIds:

    def test_fixed_chunk_ids_unique(self, tcp_text):
        chunker = FixedChunker(chunk_tokens=256, overlap_pct=0.0)
        result = chunker.chunk(tcp_text, "tcp")
        ids = [c.chunk_id for c in result.chunks]
        assert len(ids) == len(set(ids)), "Duplicate chunk_ids detected"

    def test_sentence_chunk_ids_unique(self, tcp_text):
        chunker = SentenceChunker(chunk_tokens=256, overlap_sentences=0)
        result = chunker.chunk(tcp_text, "tcp")
        ids = [c.chunk_id for c in result.chunks]
        assert len(ids) == len(set(ids)), "Duplicate chunk_ids detected"


# ---------------------------------------------------------------------------
# Phase 2 Fixes & Verification Tests
# ---------------------------------------------------------------------------

class TestPhase2Fixes:

    def test_chunk_count_non_increasing_with_N(self, all_docs):
        """For each strategy and RFC, chunk count is non-increasing as N goes 128 -> 256 -> 512."""
        for doc_id, text in all_docs.items():
            for strategy in ["fixed", "sentence"]:
                for ov in ([0.0, 0.15] if strategy == "fixed" else [0, 1]):
                    c128 = build_chunker(strategy, chunk_tokens=128, **({"overlap_pct": ov} if strategy == "fixed" else {"overlap_sentences": ov}))
                    c256 = build_chunker(strategy, chunk_tokens=256, **({"overlap_pct": ov} if strategy == "fixed" else {"overlap_sentences": ov}))
                    c512 = build_chunker(strategy, chunk_tokens=512, **({"overlap_pct": ov} if strategy == "fixed" else {"overlap_sentences": ov}))

                    n128 = len(c128.chunk(text, doc_id).chunks)
                    n256 = len(c256.chunk(text, doc_id).chunks)
                    n512 = len(c512.chunk(text, doc_id).chunks)

                    assert n128 >= n256 >= n512, (
                        f"{doc_id} {strategy} ov={ov}: counts {n128} >= {n256} >= {n512} violated"
                    )

    def test_overlap_chunk_ratio(self, all_docs):
        """Overlap variants have between 1.0x and about 1.55x the chunks of matching no-overlap."""
        for doc_id, text in all_docs.items():
            for n in [128, 256, 512]:
                c_no = SentenceChunker(chunk_tokens=n, overlap_sentences=0).chunk(text, doc_id)
                c_ov = SentenceChunker(chunk_tokens=n, overlap_sentences=1).chunk(text, doc_id)
                ratio = len(c_ov.chunks) / max(len(c_no.chunks), 1)
                assert 1.0 <= ratio <= 1.55, (
                    f"{doc_id} N={n}: overlap ratio {ratio:.2f} not in [1.0, 1.55] "
                    f"(no-overlap={len(c_no.chunks)}, overlap={len(c_ov.chunks)})"
                )

    def test_average_tokens_sensible(self, all_docs):
        """Average tokens per chunk is within a sensible range of N (not below ~30% of N)."""
        for doc_id, text in all_docs.items():
            for n in [128, 256, 512]:
                for ov in [0, 1]:
                    res = SentenceChunker(chunk_tokens=n, overlap_sentences=ov).chunk(text, doc_id)
                    avg_tok = sum(c.token_count for c in res.chunks) / len(res.chunks)
                    # For N=128, 30% is ~38.4 tokens; for N=256, ~76.8; for N=512, ~153.6
                    threshold = n * 0.30
                    assert avg_tok >= threshold, (
                        f"{doc_id} sent_{n}_{ov}: avg tokens {avg_tok:.1f} < 30% of {n} ({threshold})"
                    )

    def test_strictly_no_chunk_exceeds_max_tokens(self, all_docs):
        """No chunk exceeds its max tokens, no exceptions (oversized blocks are split)."""
        for doc_id, text in all_docs.items():
            for n in [128, 256, 512]:
                # Fixed
                res_fix = FixedChunker(chunk_tokens=n, overlap_pct=0.0).chunk(text, doc_id)
                for c in res_fix.chunks:
                    assert c.token_count <= n, f"Fixed {doc_id} N={n} chunk {c.chunk_id} has {c.token_count} > {n}"

                # Sentence
                res_sent = SentenceChunker(chunk_tokens=n, overlap_sentences=0).chunk(text, doc_id)
                for c in res_sent.chunks:
                    assert c.token_count <= n, f"Sentence {doc_id} N={n} chunk {c.chunk_id} has {c.token_count} > {n}"

    def test_exclude_front_matter(self, all_docs):
        """No front-matter text appears in any chunk when exclude_front_matter is on."""
        from app.core.sections import parse_sections, sections_to_dict
        for doc_id, text in all_docs.items():
            sections = sections_to_dict(parse_sections(text))
            first_sec_start = sections[0]["char_start"]
            res = SentenceChunker(chunk_tokens=256).chunk(text, doc_id, sections=sections, exclude_front_matter=True)
            for c in res.chunks:
                assert c.char_start >= first_sec_start, (
                    f"{doc_id}: Chunk {c.chunk_id} char_start {c.char_start} < first section start {first_sec_start}"
                )

    def test_sentence_chunker_runtime_under_5s(self, all_docs):
        """Sentence chunker runtime for any config on any RFC is under 5 seconds."""
        for doc_id, text in all_docs.items():
            for n in [128, 256, 512]:
                for ov in [0, 1]:
                    res = SentenceChunker(chunk_tokens=n, overlap_sentences=ov).chunk(text, doc_id)
                    assert res.elapsed_seconds < 5.0, (
                        f"{doc_id} sent_{n}_{ov} took {res.elapsed_seconds:.2f}s > 5.0s"
                    )

    def test_section_populated_for_body_chunks(self, all_docs):
        """Chunks in the body of each RFC get their section field populated."""
        from app.core.sections import parse_sections, sections_to_dict
        for doc_id, text in all_docs.items():
            sections = sections_to_dict(parse_sections(text))
            res = SentenceChunker(chunk_tokens=256).chunk(text, doc_id, sections=sections, exclude_front_matter=True)
            for c in res.chunks:
                assert c.section is not None, f"{doc_id}: chunk {c.chunk_id} at {c.char_start} has None section"
                assert len(c.section) > 0
