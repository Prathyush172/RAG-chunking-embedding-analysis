"""
backend/tests/test_evaluation.py — Tests for EvidenceLocator, EvidenceValidator, and RelevanceMapper.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.core.chunkers import Chunk
from app.core.evaluation import (
    EvidenceItem,
    EvidenceLocator,
    EvidenceValidator,
    NoRelevantChunksError,
    Question,
    RelevanceMapper,
    ValidationIssue,
)


@pytest.fixture
def temp_clean_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Create a synthetic cleaned doc with front matter and body sections
        doc_text = (
            "RFC 9999              Experimental RFC               April 2026\n\n"
            "Table of Contents\n"
            "1. Introduction\n"
            "2. Architecture\n\n"
            "1.  Introduction\n\n"
            "The quick brown fox jumps over the lazy dog.\n"
            "This is a second unique sentence for testing.\n\n"
            "2.  Architecture\n\n"
            "The system architecture consists of a client, a server, and an intermediary proxy.\n"
            "repeated token occurs here and repeated token occurs later.\n"
        )
        (tmp_path / "test_doc.txt").write_text(doc_text, encoding="utf-8")
        yield tmp_path


class TestEvidenceLocator:
    def test_exact_match(self, temp_clean_dir: Path):
        locator = EvidenceLocator(clean_dir=temp_clean_dir)
        start, end, matches = locator.locate_quote(
            "test_doc", "The quick brown fox jumps over the lazy dog."
        )
        assert len(matches) == 1
        assert start >= 0
        assert end > start
        text = locator.get_document_text("test_doc")
        assert text[start:end] == "The quick brown fox jumps over the lazy dog."

    def test_whitespace_differences_matching(self, temp_clean_dir: Path):
        locator = EvidenceLocator(clean_dir=temp_clean_dir)
        # Quote with extra spaces and newlines
        quote = "The   quick\n  brown   fox jumps  over  the lazy dog."
        start, end, matches = locator.locate_quote("test_doc", quote)
        assert len(matches) == 1
        text = locator.get_document_text("test_doc")
        assert "quick brown fox" in text[start:end]

    def test_quote_not_found(self, temp_clean_dir: Path):
        locator = EvidenceLocator(clean_dir=temp_clean_dir)
        start, end, matches = locator.locate_quote("test_doc", "Nonexistent sentence in document.")
        assert start == -1
        assert end == -1
        assert len(matches) == 0

    def test_ambiguous_quote(self, temp_clean_dir: Path):
        locator = EvidenceLocator(clean_dir=temp_clean_dir)
        # "repeated token" occurs twice in test_doc
        start, end, matches = locator.locate_quote("test_doc", "repeated token")
        assert len(matches) == 2


class TestEvidenceValidator:
    def test_valid_question(self, temp_clean_dir: Path):
        validator = EvidenceValidator(clean_dir=temp_clean_dir)
        q = Question(
            id="test-01",
            question="What is the architecture composed of?",
            doc_id="test_doc",
            section="2. Architecture",
            evidence=[
                EvidenceItem(
                    doc_id="test_doc",
                    quote="The system architecture consists of a client, a server, and an intermediary proxy.",
                )
            ],
            reference_answer="Client, server, and intermediary proxy.",
            type="definition",
            difficulty="easy",
            verified=False,
        )
        issues = validator.validate_question(q)
        assert len(issues) == 0
        assert q.evidence[0].char_start > 0

    def test_evidence_in_front_matter(self, temp_clean_dir: Path):
        validator = EvidenceValidator(clean_dir=temp_clean_dir)
        # Quote from title line before section 1
        q = Question(
            id="test-02",
            question="What is the RFC number?",
            doc_id="test_doc",
            section="1. Introduction",
            evidence=[
                EvidenceItem(
                    doc_id="test_doc",
                    quote="Experimental RFC",
                )
            ],
            reference_answer="Experimental RFC",
            type="factual",
            difficulty="easy",
            verified=False,
        )
        issues = validator.validate_question(q)
        assert any(i.issue_type == "front_matter" for i in issues)

    def test_ambiguous_quote_validation_error(self, temp_clean_dir: Path):
        validator = EvidenceValidator(clean_dir=temp_clean_dir)
        q = Question(
            id="test-03",
            question="Where does repeated token occur?",
            doc_id="test_doc",
            section="2. Architecture",
            evidence=[
                EvidenceItem(
                    doc_id="test_doc",
                    quote="repeated token",
                )
            ],
            reference_answer="In architecture.",
            type="factual",
            difficulty="easy",
            verified=False,
        )
        issues = validator.validate_question(q)
        assert any(i.issue_type == "quote_ambiguous" for i in issues)


class TestRelevanceMapper:
    def test_relevance_threshold_overlap(self):
        mapper = RelevanceMapper(min_overlap_chars=40)
        # Span: [100, 200) -> len = 100
        ev = EvidenceItem(doc_id="doc1", quote="sample", char_start=100, char_end=200)
        q = Question(
            id="q1",
            question="sample?",
            doc_id="doc1",
            section="sec",
            evidence=[ev],
            reference_answer="ans",
            type="factual",
            difficulty="easy",
        )

        # Chunk 1: [80, 150) -> overlap = 50 >= 40 -> Relevant!
        c1 = Chunk("c1", "doc1", "text", 80, 150, 20, "fixed")
        # Chunk 2: [170, 250) -> overlap = 30 < 40 -> Not relevant
        c2 = Chunk("c2", "doc1", "text", 170, 250, 20, "fixed")
        # Chunk 3: [500, 600) -> overlap = 0 -> Not relevant
        c3 = Chunk("c3", "doc1", "text", 500, 600, 20, "fixed")

        rel = mapper.get_relevant_chunks(q, [c1, c2, c3], allow_empty=True)
        assert len(rel) == 1
        assert rel[0].chunk_id == "c1"

    def test_full_containment_short_span(self):
        # Short span < 40 chars
        mapper = RelevanceMapper(min_overlap_chars=40)
        ev = EvidenceItem(doc_id="doc1", quote="short", char_start=100, char_end=125) # 25 chars
        q = Question(
            id="q2",
            question="short?",
            doc_id="doc1",
            section="sec",
            evidence=[ev],
            reference_answer="ans",
            type="factual",
            difficulty="easy",
        )
        # Chunk fully contains the 25-char span
        c = Chunk("c_full", "doc1", "text", 90, 150, 20, "fixed")
        rel = mapper.get_relevant_chunks(q, [c], allow_empty=True)
        assert len(rel) == 1
        assert rel[0].chunk_id == "c_full"

    def test_zero_relevant_raises_error(self):
        mapper = RelevanceMapper(min_overlap_chars=40)
        ev = EvidenceItem(doc_id="doc1", quote="sample", char_start=100, char_end=200)
        q = Question(
            id="q_zero",
            question="sample?",
            doc_id="doc1",
            section="sec",
            evidence=[ev],
            reference_answer="ans",
            type="factual",
            difficulty="easy",
        )
        # Chunks far away
        c_far = Chunk("c_far", "doc1", "text", 1000, 1200, 20, "fixed")
        with pytest.raises(NoRelevantChunksError) as exc_info:
            mapper.get_relevant_chunks(q, [c_far], config_label="fixed_256_0", allow_empty=False)
        assert "q_zero" in str(exc_info.value)
        assert "fixed_256_0" in str(exc_info.value)
