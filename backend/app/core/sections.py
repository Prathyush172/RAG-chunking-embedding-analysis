"""
sections.py — Section outline parser for RFC documents.

Detects headings of the form:
  "3.  Title"
  "3.1.  Title"
  "3.1.2.  Title"
  "A.  Appendix Title"   (single capital letter)
  "Appendix A.  Title"

Builds a list of SectionEntry objects with:
  - number: "3.1.2"
  - title:  "Header Format"
  - level:  depth (1 = top-level, 2 = sub-section, …)
  - char_start: byte offset of the heading line in the cleaned text
  - char_end:   byte offset where the *next* section starts (or EOF)

Used for navigation and relevance labelling in the UI and evaluation pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Heading detection patterns
# ---------------------------------------------------------------------------
# Numeric section: "3.", "3.1.", "3.1.2." followed by 2+ spaces and a title
# (modern RFC style with double-space separator)
_NUMERIC_RE = re.compile(
    r"^(\d+(?:\.\d+)*\.?)\s{2,}(\S.*)$",
    re.MULTILINE,
)

# Numeric section with single space: "2.1. The history…" (old RFC style like 1034/1035)
# Title must start with a capital letter and be at least 4 chars to avoid false positives.
_NUMERIC_OLDSTYLE_RE = re.compile(
    r"^(\d+(?:\.\d+)+\.?)\s{1}([A-Z]\S.{3,})$",
    re.MULTILINE,
)

# Appendix: "A.  Title" or "Appendix A.  Title"
_APPENDIX_RE = re.compile(
    r"^(?:Appendix\s+)?([A-Z]\.)\s{2,}(\S.*)$",
    re.MULTILINE,
)

# Top-level ALL-CAPS or mixed-case headings (older RFCs like 1034/1035)
# e.g. "2. INTRODUCTION" or "3. DOMAIN NAME SPACE and RESOURCE RECORDS"
_OLDSTYLE_RE = re.compile(
    r"^(\d+)\.\s{1,4}([A-Z][A-Za-z\s\-\&\/]{3,})$",
    re.MULTILINE,
)


@dataclass
class SectionEntry:
    """One entry in the section outline of an RFC document."""

    number: str           # e.g. "3.1.2" or "A"
    title: str            # heading text (stripped)
    level: int            # 1 = top-level
    char_start: int       # start of heading line in cleaned text
    char_end: int = -1    # start of next section (filled in after parsing)
    children: list["SectionEntry"] = field(default_factory=list, repr=False)

    @property
    def label(self) -> str:
        return f"{self.number}. {self.title}"


def _level_from_number(number: str) -> int:
    """Return depth level from a dotted section number string."""
    # "3" -> 1, "3.1" -> 2, "3.1.2" -> 3, "A" -> 1
    clean = number.rstrip(".")
    if re.match(r"^[A-Z]$", clean):
        return 1
    return len(clean.split("."))


def parse_sections(text: str) -> list[SectionEntry]:
    """
    Parse section headings from cleaned RFC text.

    Returns a flat list of SectionEntry objects sorted by char_start.
    The char_end of each entry is set to the char_start of the next entry
    (or len(text) for the last one).
    """
    matches: list[tuple[int, str, str]] = []  # (char_start, number, title)

    for m in _NUMERIC_RE.finditer(text):
        num_raw = m.group(1).rstrip(".")
        matches.append((m.start(), num_raw, m.group(2).strip()))

    # Old-style single-space subsections (RFC 1034/1035: "2.1. Title")
    existing_starts = {s for s, _, _ in matches}
    for m in _NUMERIC_OLDSTYLE_RE.finditer(text):
        if m.start() not in existing_starts:
            num_raw = m.group(1).rstrip(".")
            matches.append((m.start(), num_raw, m.group(2).strip()))
            existing_starts.add(m.start())

    # Appendix headings (avoid duplicates already captured by NUMERIC_RE)
    for m in _APPENDIX_RE.finditer(text):
        if m.start() not in existing_starts:
            app_num = m.group(1).rstrip(".")
            matches.append((m.start(), app_num, m.group(2).strip()))
            existing_starts.add(m.start())

    # Old-style uppercase headings (RFC 1034/1035) — only if numeric not found
    for m in _OLDSTYLE_RE.finditer(text):
        if m.start() not in {s for s, _, _ in matches}:
            matches.append((m.start(), m.group(1), m.group(2).strip().title()))

    # Sort by position
    matches.sort(key=lambda x: x[0])

    entries: list[SectionEntry] = []
    for char_start, number, title in matches:
        level = _level_from_number(number)
        entries.append(
            SectionEntry(
                number=number,
                title=title,
                level=level,
                char_start=char_start,
            )
        )

    # Fill char_end
    for i, entry in enumerate(entries):
        if i + 1 < len(entries):
            entry.char_end = entries[i + 1].char_start
        else:
            entry.char_end = len(text)

    return entries


def find_section_for_offset(
    sections: list[SectionEntry] | list[dict],
    char_offset: int,
) -> Optional[SectionEntry | dict]:
    """
    Given a character offset in the cleaned text, return the deepest
    section entry (SectionEntry or dict) that contains it:
    char_start <= offset < char_end.
    Returns None if the offset precedes all sections.
    """
    best = None
    for entry in sections:
        start = entry.char_start if isinstance(entry, SectionEntry) else entry["char_start"]
        end = entry.char_end if isinstance(entry, SectionEntry) else entry["char_end"]
        lvl = entry.level if isinstance(entry, SectionEntry) else entry["level"]

        if start <= char_offset:
            if end == -1 or char_offset < end:
                best_lvl = best.level if isinstance(best, SectionEntry) else (best["level"] if best else -1)
                if best is None or lvl >= best_lvl:
                    best = entry
        elif start > char_offset:
            break
    return best


def sections_to_dict(sections: list[SectionEntry]) -> list[dict]:
    """Serialise section list to a JSON-serialisable list of dicts."""
    return [
        {
            "number": s.number,
            "title": s.title,
            "level": s.level,
            "label": s.label,
            "char_start": s.char_start,
            "char_end": s.char_end,
        }
        for s in sections
    ]


def build_outline(doc_id: str, clean_text: str) -> list[dict]:
    """
    Convenience wrapper: parse sections and return serialisable outline.

    Args:
        doc_id:     Document identifier (for logging).
        clean_text: Cleaned RFC text.

    Returns:
        List of section dicts with keys: number, title, level, label,
        char_start, char_end.
    """
    sections = parse_sections(clean_text)
    return sections_to_dict(sections)
