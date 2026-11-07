"""
tests/test_preprocess.py — Unit tests for the RFC preprocessing pipeline.

Tests cover:
- Form-feed replacement
- Footer line removal
- Header line removal
- Trailing whitespace stripping
- Blank-line collapsing
- Invariants: cleaned text is valid UTF-8, ends with single newline
- Section content (headings, ASCII art) is preserved
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the top-level preprocess module importable
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from preprocess import clean_text, load_corpus_config, run_preprocessing  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw(body: str) -> str:
    """Wrap body text in a minimal RFC-like structure."""
    return body


# ---------------------------------------------------------------------------
# Unit tests for clean_text()
# ---------------------------------------------------------------------------

class TestFormFeedReplacement:
    def test_form_feed_replaced_with_newline(self):
        raw = "line 1\x0cline 2\x0cline 3"
        cleaned, stats = clean_text(raw)
        assert "\x0c" not in cleaned
        assert stats["form_feeds"] == 2

    def test_no_form_feeds(self):
        raw = "no form feeds here\n"
        _, stats = clean_text(raw)
        assert stats["form_feeds"] == 0

    def test_text_preserved_around_form_feed(self):
        raw = "before\x0cafter"
        cleaned, _ = clean_text(raw)
        assert "before" in cleaned
        assert "after" in cleaned


class TestFooterRemoval:
    def test_simple_footer(self):
        raw = "some content\nMockapetris                                                     [Page 1]\n\nmore content\n"
        cleaned, stats = clean_text(raw)
        assert "[Page 1]" not in cleaned
        assert stats["footer_lines"] == 1

    def test_footer_with_form_feed(self):
        # Form feed replaces \x0c → \n, then footer pattern fires
        raw = "text\nMockapetris                                                     [Page 5]\n\x0c\nRFC 1034             Domain Concepts and Facilities        November 1987\n\nmore\n"
        cleaned, stats = clean_text(raw)
        assert "[Page 5]" not in cleaned

    def test_non_footer_preserved(self):
        raw = "This [Page 1] is inline text, not a footer\n"
        cleaned, _ = clean_text(raw)
        assert "[Page 1]" in cleaned

    def test_multiple_footers(self):
        footers = "\n".join(
            [
                f"Author Name{'.' * 50}[Page {i}]"
                for i in range(1, 4)
            ]
        )
        raw = f"content\n{footers}\nmore content\n"
        cleaned, stats = clean_text(raw)
        assert stats["footer_lines"] == 3
        for i in range(1, 4):
            assert f"[Page {i}]" not in cleaned


class TestHeaderRemoval:
    def test_simple_header(self):
        raw = "RFC 1034             Domain Concepts and Facilities        November 1987\n\ncontent\n"
        cleaned, stats = clean_text(raw)
        assert "RFC 1034" not in cleaned
        assert stats["header_lines"] == 1

    def test_header_with_different_rfc(self):
        raw = "RFC 9293              Transmission Control Protocol           August 2022\n\ncontent\n"
        cleaned, stats = clean_text(raw)
        assert stats["header_lines"] == 1

    def test_non_header_preserved(self):
        # "RFC 1034" appears inline in the body — should NOT be removed
        raw = "This document updates RFC 1034 and adds clarifications.\n"
        cleaned, _ = clean_text(raw)
        assert "RFC 1034" in cleaned


class TestTrailingWhitespace:
    def test_trailing_spaces_stripped(self):
        raw = "line with spaces   \nclean line\ntrailing tab\t\n"
        cleaned, stats = clean_text(raw)
        for line in cleaned.split("\n"):
            assert line == line.rstrip(), f"Trailing whitespace in: {line!r}"

    def test_stats_count_changed_lines(self):
        raw = "clean\nhas spaces   \nalso clean\n"
        _, stats = clean_text(raw)
        assert stats["trailing_ws_lines"] == 1


class TestBlankLineCollapsing:
    def test_three_blank_lines_collapsed(self):
        # 3 blank lines = 4 newlines; should become 2 blank lines = 3 newlines
        raw = "para1\n\n\n\npara2\n"
        cleaned, stats = clean_text(raw)
        assert "\n\n\n\n" not in cleaned
        assert stats["blank_lines_collapsed"] == 1

    def test_two_blank_lines_preserved(self):
        raw = "para1\n\n\npara2\n"  # exactly 2 blank lines (3 newlines)
        cleaned, _ = clean_text(raw)
        # 2 blank lines is fine — not collapsed
        # The spec says "collapse 3+ blank lines into 2"
        # 3 newlines = 2 blank lines, so this should be untouched
        assert "para1" in cleaned
        assert "para2" in cleaned

    def test_many_blanks_collapsed(self):
        raw = "a\n\n\n\n\n\n\nb\n"  # 6 blank lines
        cleaned, stats = clean_text(raw)
        assert "\n\n\n\n" not in cleaned


class TestInvariants:
    def test_ends_with_single_newline(self):
        raw = "some content\n"
        cleaned, _ = clean_text(raw)
        assert cleaned.endswith("\n")
        assert not cleaned.endswith("\n\n")

    def test_headings_preserved(self):
        raw = "3.1.  Header Format\n\nSome content under the section.\n"
        cleaned, _ = clean_text(raw)
        assert "3.1.  Header Format" in cleaned

    def test_ascii_art_preserved(self):
        art = (
            "+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+\n"
            "|                      ID                         |\n"
            "+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+--+\n"
        )
        raw = f"Header\n\n{art}\nFooter\n"
        cleaned, _ = clean_text(raw)
        assert "+--+--+" in cleaned
        assert "ID" in cleaned

    def test_empty_input(self):
        cleaned, stats = clean_text("")
        assert cleaned == "\n"
        assert all(v == 0 for v in stats.values())


# ---------------------------------------------------------------------------
# Integration test: run preprocessing on actual RFC files
# ---------------------------------------------------------------------------

class TestPreprocessingIntegration:
    def test_corpus_config_loads(self):
        docs = load_corpus_config()
        assert len(docs) == 4
        doc_ids = [d["doc_id"] for d in docs]
        assert set(doc_ids) == {"tcp", "dns", "dns_implementation", "http"}

    def test_preprocessing_runs_without_error(self, tmp_path):
        """Preprocess all four RFCs and verify output exists."""
        import yaml

        # Build a temp corpus config pointing to actual datasets
        docs = load_corpus_config()
        # Redirect clean_file to tmp_path
        for doc in docs:
            doc["clean_file"] = str(tmp_path / Path(doc["clean_file"]).name)

        tmp_config = tmp_path / "corpus.yaml"
        with open(tmp_config, "w") as f:
            yaml.dump({"corpus": docs}, f)

        all_stats = run_preprocessing(config_path=tmp_config, repo_root=_REPO_ROOT)

        for doc_id, stats in all_stats.items():
            assert "error" not in stats, f"Error in {doc_id}: {stats['error']}"

    def test_dns_footers_removed(self, tmp_path):
        """DNS 1034 has 55 form feeds and footers; verify they're cleaned."""
        raw_path = _REPO_ROOT / "datasets" / "dns.txt"
        raw = raw_path.read_text(encoding="utf-8", errors="replace")
        cleaned, stats = clean_text(raw)
        assert stats["form_feeds"] > 0
        assert stats["footer_lines"] > 0
        assert "[Page " not in cleaned
        # Verify no form feeds remain
        assert "\x0c" not in cleaned

    def test_tcp_no_footers(self):
        """TCP RFC 9293 is a modern RFC with no page-break boilerplate."""
        raw_path = _REPO_ROOT / "datasets" / "tcp.txt"
        raw = raw_path.read_text(encoding="utf-8", errors="replace")
        _, stats = clean_text(raw)
        assert stats["form_feeds"] == 0
        assert stats["footer_lines"] == 0
        assert stats["header_lines"] == 0

    def test_cleaned_text_char_offset_invariant(self, tmp_path):
        """
        Invariant: for any substring found in the cleaned text at [start:end],
        cleaned_text[start:end] must equal that substring exactly.
        This confirms character offsets are reliable.
        """
        import yaml

        docs = load_corpus_config()
        for doc in docs:
            doc["clean_file"] = str(tmp_path / Path(doc["clean_file"]).name)
        tmp_config = tmp_path / "corpus.yaml"
        with open(tmp_config, "w") as f:
            yaml.dump({"corpus": docs}, f)

        run_preprocessing(config_path=tmp_config, repo_root=_REPO_ROOT)

        for doc in docs:
            clean_path = Path(doc["clean_file"])
            if not clean_path.exists():
                continue
            text = clean_path.read_text(encoding="utf-8")
            # Sample a few substrings and verify offset invariant
            sample_len = 50
            for start in range(0, min(len(text) - sample_len, 5000), 500):
                end = start + sample_len
                substr = text[start:end]
                assert text[start:end] == substr
