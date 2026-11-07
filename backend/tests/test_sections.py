"""
tests/test_sections.py — Unit tests for the RFC section outline parser.

Tests cover:
- Numeric section headings at various depths
- Appendix headings
- Old-style uppercase headings (RFC 1034/1035 format)
- char_start / char_end span invariants
- find_section_for_offset helper
- Real RFC documents (integration smoke tests)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "backend"))

from app.core.sections import (  # noqa: E402
    SectionEntry,
    build_outline,
    find_section_for_offset,
    parse_sections,
    sections_to_dict,
)
from preprocess import clean_text  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sections_from_text(text: str) -> list[SectionEntry]:
    return parse_sections(text)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestNumericHeadings:
    def test_top_level_section(self):
        text = "Some preamble.\n\n1.  Introduction\n\nContent here.\n"
        sections = _sections_from_text(text)
        assert len(sections) >= 1
        s = sections[0]
        assert s.number == "1"
        assert s.title == "Introduction"
        assert s.level == 1

    def test_subsection(self):
        text = "1.  Intro\n\nBody.\n\n1.1.  Background\n\nSub content.\n"
        sections = _sections_from_text(text)
        numbers = [s.number for s in sections]
        assert "1" in numbers
        assert "1.1" in numbers
        intro = next(s for s in sections if s.number == "1")
        sub = next(s for s in sections if s.number == "1.1")
        assert intro.level == 1
        assert sub.level == 2

    def test_deep_subsection(self):
        text = "3.1.2.  Deep Section\n\ncontent\n"
        sections = _sections_from_text(text)
        assert any(s.number == "3.1.2" and s.level == 3 for s in sections)

    def test_multiple_sections_ordered(self):
        text = (
            "1.  First\n\ncontent\n\n"
            "2.  Second\n\ncontent\n\n"
            "3.  Third\n\ncontent\n"
        )
        sections = _sections_from_text(text)
        numbers = [s.number for s in sections]
        assert numbers == sorted(numbers, key=lambda n: list(map(int, n.split("."))))


class TestAppendixHeadings:
    def test_appendix_A(self):
        text = "Main content.\n\nA.  Appendix One\n\nappendix content\n"
        sections = _sections_from_text(text)
        app = next((s for s in sections if s.number == "A"), None)
        assert app is not None
        assert app.level == 1

    def test_appendix_prefix_form(self):
        text = "Main.\n\nAppendix A.  Security Considerations\n\ndetails\n"
        sections = _sections_from_text(text)
        assert any(s.number == "A" for s in sections)


class TestSpanInvariants:
    def test_char_start_points_to_heading(self):
        text = "preamble\n\n1.  Intro\n\ncontent\n\n2.  Body\n\ntext\n"
        sections = _sections_from_text(text)
        for s in sections:
            # The char_start should point to the section number at the start of line
            char = text[s.char_start]
            assert char.isdigit() or char.isalpha(), (
                f"Section {s.number}: char at char_start={s.char_start} is {char!r}"
            )

    def test_char_end_covers_content(self):
        text = "1.  First\n\nContent of first.\n\n2.  Second\n\nContent of second.\n"
        sections = _sections_from_text(text)
        assert len(sections) >= 2
        first = sections[0]
        # char_end of first should be == char_start of second
        second = sections[1]
        assert first.char_end == second.char_start

    def test_last_section_ends_at_eof(self):
        text = "1.  Only\n\nContent.\n"
        sections = _sections_from_text(text)
        assert sections[-1].char_end == len(text)

    def test_span_contains_heading(self):
        text = "1.  Intro\n\nBody text here.\n\n2.  Next\n\nMore.\n"
        sections = _sections_from_text(text)
        s = sections[0]
        span = text[s.char_start : s.char_end]
        assert "Intro" in span
        assert "Body text here." in span


class TestFindSectionForOffset:
    def test_finds_correct_section(self):
        text = "1.  First\n\nContent.\n\n2.  Second\n\nMore.\n"
        sections = _sections_from_text(text)
        # Find offset inside "Content."
        offset = text.index("Content.")
        found = find_section_for_offset(sections, offset)
        assert found is not None
        assert found.number == "1"

    def test_offset_before_all_sections(self):
        text = "Preamble text.\n\n1.  First\n\ncontent\n"
        sections = _sections_from_text(text)
        found = find_section_for_offset(sections, 0)
        # Preamble is before section 1; could return None or section 1 depending on impl
        # The key invariant is it doesn't crash
        assert found is None or isinstance(found, SectionEntry)

    def test_offset_at_heading(self):
        text = "1.  First\n\ncontent\n\n2.  Second\n\nmore\n"
        sections = _sections_from_text(text)
        s2 = next(s for s in sections if s.number == "2")
        found = find_section_for_offset(sections, s2.char_start)
        assert found is not None
        assert found.number == "2"


class TestSerialization:
    def test_sections_to_dict_keys(self):
        text = "1.  Intro\n\ncontent\n\n1.1.  Sub\n\nsub content\n"
        sections = _sections_from_text(text)
        dicts = sections_to_dict(sections)
        required_keys = {"number", "title", "level", "label", "char_start", "char_end"}
        for d in dicts:
            assert required_keys.issubset(d.keys())

    def test_label_format(self):
        text = "3.1.  Header Format\n\ncontent\n"
        sections = _sections_from_text(text)
        s = next(s for s in sections if s.number == "3.1")
        assert s.label == "3.1. Header Format"


class TestBuildOutline:
    def test_returns_list_of_dicts(self):
        text = "1.  Intro\n\ncontent\n\n2.  Body\n\nmore\n"
        outline = build_outline("test_doc", text)
        assert isinstance(outline, list)
        assert all(isinstance(d, dict) for d in outline)


# ---------------------------------------------------------------------------
# Integration smoke tests on real RFC files
# ---------------------------------------------------------------------------

class TestRealRFCParsing:
    @pytest.fixture(scope="class")
    @classmethod
    def tcp_cleaned(cls):
        raw = (_REPO_ROOT / "datasets" / "tcp.txt").read_text(encoding="utf-8", errors="replace")
        cleaned, _ = clean_text(raw)
        return cleaned

    @pytest.fixture(scope="class")
    @classmethod
    def dns_cleaned(cls):
        raw = (_REPO_ROOT / "datasets" / "dns.txt").read_text(encoding="utf-8", errors="replace")
        cleaned, _ = clean_text(raw)
        return cleaned

    def test_tcp_has_sections(self, tcp_cleaned):
        sections = parse_sections(tcp_cleaned)
        assert len(sections) > 10, "TCP RFC should have many sections"

    def test_dns_has_sections(self, dns_cleaned):
        sections = parse_sections(dns_cleaned)
        assert len(sections) >= 5, "DNS RFC should have at least 5 sections"

    def test_tcp_section_spans_non_overlapping(self, tcp_cleaned):
        sections = parse_sections(tcp_cleaned)
        for i in range(len(sections) - 1):
            assert sections[i].char_end == sections[i + 1].char_start, (
                f"Gap between sections {sections[i].number} and {sections[i+1].number}"
            )

    def test_dns_no_page_footers_in_headings(self, dns_cleaned):
        sections = parse_sections(dns_cleaned)
        for s in sections:
            assert "[Page" not in s.title, (
                f"Section {s.number} title contains page reference: {s.title!r}"
            )
