"""
scripts/build_rfc_eval_set.py — Curate and validate exactly 56 questions from cleaned RFCs.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.evaluation import (
    EvidenceItem,
    EvidenceLocator,
    EvidenceValidator,
    Question,
    save_questions,
)
from app.core.sections import parse_sections

locator = EvidenceLocator()

def extract_section_paragraph(doc_id: str, section_number: str, min_chars: int = 80, max_chars: int = 600) -> str:
    """Find a clean, unique paragraph within the specified section."""
    text = locator.get_document_text(doc_id)
    secs = parse_sections(text)
    matching = [s for s in secs if s.number == section_number]
    if not matching:
        raise ValueError(f"Section {section_number} not found in {doc_id}")
    sec = matching[0]
    sec_text = text[sec.char_start:sec.char_end]
    paras = [p.strip() for p in sec_text.split("\n\n") if len(p.strip()) >= min_chars]
    for p in paras:
        if any(p.startswith(x) for x in ["+", "|", "-", "===", "["]):
            continue
        # Take at most max_chars (1-3 sentences)
        sentences = [s.strip() for s in p.split(". ") if s.strip()]
        for num_s in [2, 3, 1, 4]:
            if len(sentences) >= num_s:
                candidate = ". ".join(sentences[:num_s])
                if not candidate.endswith("."):
                    candidate += "."
                # Check uniqueness
                start, end, matches = locator.locate_quote(doc_id, candidate)
                if len(matches) == 1:
                    return candidate
        if len(matches) == 1:
            return p
    raise ValueError(f"Could not find unique paragraph in {doc_id} section {section_number}")

print("Extractor ready.")
