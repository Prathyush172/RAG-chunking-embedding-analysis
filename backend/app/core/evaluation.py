"""
backend/app/core/evaluation.py — Question data models, Evidence Locator, Validator, and Relevance Mapper.

Implements Phase 4 requirements:
- Locates evidence quotes in data/clean/ using whitespace-normalised matching.
- Validates quote uniqueness, body boundary (excluding front-matter), doc_ids, and question schema.
- Maps chunks to relevance based on character-span overlaps (threshold: 40 chars or full containment).
- Raises NoRelevantChunksError when a question has zero matching chunks under a configuration.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .chunkers import Chunk
from .sections import find_section_for_offset, parse_sections, sections_to_dict

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CLEAN_DIR = REPO_ROOT / "data" / "clean"
DEFAULT_QUESTIONS_PATH = REPO_ROOT / "data" / "eval" / "questions.json"

VALID_TYPES = {"factual", "definition", "procedural", "multi-hop"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}
DEFAULT_MIN_OVERLAP_CHARS = 40

FRONT_MATTER_SECTION_KEYWORDS = ("status of this memo", "abstract", "table of contents", "status of memo")

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so",
    "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "would", "you", "your", "yours", "yourself", "yourselves"
}


def compute_longest_common_word_run(s1: str, s2: str) -> int:
    """Find the length of the longest consecutive sequence of identical words."""
    w1 = re.findall(r"\b\w+\b", s1.lower())
    w2 = re.findall(r"\b\w+\b", s2.lower())
    if not w1 or not w2:
        return 0
    table = [[0] * (len(w2) + 1) for _ in range(len(w1) + 1)]
    max_run = 0
    for i in range(1, len(w1) + 1):
        for j in range(1, len(w2) + 1):
            if w1[i - 1] == w2[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
                if table[i][j] > max_run:
                    max_run = table[i][j]
            else:
                table[i][j] = 0
    return max_run


def compute_jaccard_similarity(s1: str, s2: str, stop_words: set[str] | None = None) -> float:
    """Compute word set Jaccard similarity excluding stop words."""
    stops = stop_words if stop_words is not None else STOP_WORDS
    w1 = {w for w in re.findall(r"\b\w+\b", s1.lower()) if w not in stops and len(w) > 1}
    w2 = {w for w in re.findall(r"\b\w+\b", s2.lower()) if w not in stops and len(w) > 1}
    if not w1 or not w2:
        return 0.0
    return float(len(w1 & w2)) / float(len(w1 | w2))


class EvaluationError(Exception):
    """Base error for evaluation pipeline."""


class NoRelevantChunksError(EvaluationError):
    """Raised when a question has 0 relevant chunks under a chunking configuration."""


@dataclass
class EvidenceItem:
    doc_id: str
    quote: str
    char_start: int = -1
    char_end: int = -1

    def to_dict(self) -> dict[str, Any]:
        d = {"doc_id": self.doc_id, "quote": self.quote}
        if self.char_start >= 0 and self.char_end >= 0:
            d["char_start"] = self.char_start
            d["char_end"] = self.char_end
        return d


@dataclass
class Question:
    id: str
    question: str
    doc_id: str
    section: str
    evidence: list[EvidenceItem]
    reference_answer: str
    type: str
    difficulty: str
    verified: bool = False
    drafted_by: str = "llm"
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    notes: Optional[str] = None
    lexical_overlap_run: int = 0
    lexical_overlap_jaccard: float = 0.0
    flagged_too_easy: bool = False

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "id": self.id,
            "question": self.question,
            "doc_id": self.doc_id,
            "section": self.section,
            "evidence": [e.to_dict() for e in self.evidence],
            "reference_answer": self.reference_answer,
            "type": self.type,
            "difficulty": self.difficulty,
            "verified": self.verified,
            "drafted_by": self.drafted_by,
            "lexical_overlap_run": self.lexical_overlap_run,
            "lexical_overlap_jaccard": round(self.lexical_overlap_jaccard, 4),
            "flagged_too_easy": self.flagged_too_easy,
        }
        if self.reviewer is not None:
            res["reviewer"] = self.reviewer
        if self.reviewed_at is not None:
            res["reviewed_at"] = self.reviewed_at
            res["verified_at"] = self.reviewed_at
        if self.notes is not None:
            res["notes"] = self.notes
        return res

    @property
    def verified_at(self) -> Optional[str]:
        return self.reviewed_at

    @verified_at.setter
    def verified_at(self, value: Optional[str]) -> None:
        self.reviewed_at = value

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Question:
        raw_evidence = data.get("evidence", [])
        evidence_items = []
        for item in raw_evidence:
            if isinstance(item, dict):
                evidence_items.append(
                    EvidenceItem(
                        doc_id=item["doc_id"],
                        quote=item["quote"],
                        char_start=item.get("char_start", -1),
                        char_end=item.get("char_end", -1),
                    )
                )
            elif isinstance(item, str):
                evidence_items.append(
                    EvidenceItem(doc_id=data.get("doc_id", ""), quote=item)
                )

        return cls(
            id=data["id"],
            question=data["question"],
            doc_id=data["doc_id"],
            section=data.get("section", ""),
            evidence=evidence_items,
            reference_answer=data.get("reference_answer", ""),
            type=data.get("type", "factual"),
            difficulty=data.get("difficulty", "medium"),
            verified=bool(data.get("verified", False)),
            drafted_by=data.get("drafted_by", "llm"),
            reviewer=data.get("reviewer"),
            reviewed_at=data.get("reviewed_at") or data.get("verified_at"),
            notes=data.get("notes"),
            lexical_overlap_run=int(data.get("lexical_overlap_run", 0)),
            lexical_overlap_jaccard=float(data.get("lexical_overlap_jaccard", 0.0)),
            flagged_too_easy=bool(data.get("flagged_too_easy", False)),
        )


@dataclass
class ValidationIssue:
    question_id: str
    issue_type: str
    message: str
    field_name: str = ""

    def __str__(self) -> str:
        return f"[{self.question_id}] {self.issue_type}: {self.message}"


class EvidenceLocator:
    """
    Locates quotes in cleaned RFC documents using whitespace-normalised pattern matching.
    Returns (char_start, char_end) offsets into the cleaned document.
    """

    def __init__(self, clean_dir: Path | None = None) -> None:
        self.clean_dir = clean_dir or DEFAULT_CLEAN_DIR
        self._doc_cache: dict[str, str] = {}

    def get_document_text(self, doc_id: str) -> str:
        if doc_id not in self._doc_cache:
            path = self.clean_dir / f"{doc_id}.txt"
            if not path.exists():
                raise FileNotFoundError(f"Cleaned RFC document not found: {path}")
            self._doc_cache[doc_id] = path.read_text(encoding="utf-8")
        return self._doc_cache[doc_id]

    def locate_quote(self, doc_id: str, quote: str) -> tuple[int, int, list[tuple[int, int]]]:
        """
        Locate quote in cleaned doc.
        Returns:
            (char_start, char_end, all_matches)
        If no matches: (-1, -1, [])
        If multiple matches: (first_start, first_end, all_matches)
        """
        text = self.get_document_text(doc_id)
        stripped_quote = quote.strip()
        if not stripped_quote:
            return -1, -1, []

        # 1. Exact match attempt first
        idx = text.find(stripped_quote)
        if idx != -1:
            # Check for multiple exact matches
            all_matches = []
            pos = 0
            while True:
                found = text.find(stripped_quote, pos)
                if found == -1:
                    break
                all_matches.append((found, found + len(stripped_quote)))
                pos = found + 1
            return all_matches[0][0], all_matches[0][1], all_matches

        # 2. Whitespace-normalised regex match (handles newlines/spaces)
        words = stripped_quote.split()
        if not words:
            return -1, -1, []

        pattern_str = r"\s+".join(re.escape(w) for w in words)
        regex = re.compile(pattern_str)
        matches = list(regex.finditer(text))

        if not matches:
            return -1, -1, []

        all_spans = [(m.start(), m.end()) for m in matches]
        return all_spans[0][0], all_spans[0][1], all_spans


class EvidenceValidator:
    """
    Validates evaluation questions against schema rules and cleaned text boundaries.
    """

    def __init__(
        self,
        clean_dir: Path | str | EvidenceLocator | None = None,
        locator: EvidenceLocator | None = None,
    ) -> None:
        if isinstance(clean_dir, EvidenceLocator):
            self.locator = clean_dir
            self.clean_dir = clean_dir.clean_dir
        elif locator is not None:
            self.locator = locator
            self.clean_dir = locator.clean_dir
        elif clean_dir:
            self.clean_dir = Path(clean_dir)
            self.locator = EvidenceLocator(self.clean_dir)
        else:
            self.clean_dir = DEFAULT_CLEAN_DIR
            self.locator = EvidenceLocator(self.clean_dir)
        self._body_starts: dict[str, int] = {}
        self._load_body_starts()

    def _load_body_starts(self) -> None:
        """Compute first section start offset per RFC to identify front matter."""
        for p in self.clean_dir.glob("*.txt"):
            doc_id = p.stem
            text = p.read_text(encoding="utf-8")
            secs = parse_sections(text)
            body_start = secs[0].char_start if secs else 0
            self._body_starts[doc_id] = body_start

    def get_body_start(self, doc_id: str) -> int:
        return self._body_starts.get(doc_id, 0)

    def validate_question(self, q: Question) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        # Check required fields
        if not q.id or not q.id.strip():
            issues.append(ValidationIssue(q.id, "empty_field", "Question ID cannot be empty", "id"))
        if not q.question or not q.question.strip():
            issues.append(ValidationIssue(q.id, "empty_field", "Question text cannot be empty", "question"))
        if not q.doc_id or not q.doc_id.strip():
            issues.append(ValidationIssue(q.id, "empty_field", "Question doc_id cannot be empty", "doc_id"))
        if not q.section or not q.section.strip():
            issues.append(ValidationIssue(q.id, "empty_field", "Section cannot be empty", "section"))
        if not q.reference_answer or not q.reference_answer.strip():
            issues.append(ValidationIssue(q.id, "empty_field", "Reference answer cannot be empty", "reference_answer"))

        # Check enum fields
        if q.type not in VALID_TYPES:
            issues.append(ValidationIssue(q.id, "invalid_type", f"Type '{q.type}' must be one of {sorted(VALID_TYPES)}", "type"))
        if q.difficulty not in VALID_DIFFICULTIES:
            issues.append(ValidationIssue(q.id, "invalid_difficulty", f"Difficulty '{q.difficulty}' must be one of {sorted(VALID_DIFFICULTIES)}", "difficulty"))

        # Check evidence count
        if not q.evidence:
            issues.append(ValidationIssue(q.id, "empty_field", "Question has no evidence quotes", "evidence"))
            return issues

        if q.type == "multi-hop" and len(q.evidence) < 2:
            issues.append(ValidationIssue(q.id, "multi_hop_evidence", "Multi-hop questions must have at least 2 evidence quotes", "evidence"))
        elif q.type != "multi-hop" and len(q.evidence) != 1:
            issues.append(ValidationIssue(q.id, "single_hop_evidence", f"Single-hop question of type '{q.type}' must have exactly 1 evidence quote, got {len(q.evidence)}", "evidence"))

        # Locate and validate each evidence quote
        for idx, ev in enumerate(q.evidence):
            if not ev.doc_id:
                issues.append(ValidationIssue(q.id, "empty_field", f"Evidence #{idx+1} has empty doc_id", f"evidence[{idx}].doc_id"))
                continue
            if not (self.clean_dir / f"{ev.doc_id}.txt").exists():
                issues.append(ValidationIssue(q.id, "doc_id_mismatch", f"Document '{ev.doc_id}' does not exist in clean corpus", f"evidence[{idx}].doc_id"))
                continue

            # In single-hop questions, evidence doc_id must match question doc_id
            if q.type != "multi-hop" and ev.doc_id != q.doc_id:
                issues.append(ValidationIssue(q.id, "doc_id_mismatch", f"Evidence doc_id '{ev.doc_id}' does not match question doc_id '{q.doc_id}'", f"evidence[{idx}].doc_id"))

            if not ev.quote or not ev.quote.strip():
                issues.append(ValidationIssue(q.id, "empty_field", f"Evidence #{idx+1} has empty quote", f"evidence[{idx}].quote"))
                continue

            # Locate in text
            start, end, matches = self.locator.locate_quote(ev.doc_id, ev.quote)
            if len(matches) == 0:
                issues.append(ValidationIssue(q.id, "quote_not_found", f"Evidence #{idx+1} quote not found in {ev.doc_id}.txt: '{ev.quote[:60]}...'", f"evidence[{idx}].quote"))
            elif len(matches) > 1:
                spans_str = ", ".join(f"{s}:{e}" for s, e in matches)
                issues.append(ValidationIssue(q.id, "quote_ambiguous", f"Evidence #{idx+1} quote is ambiguous ({len(matches)} occurrences at {spans_str}). Provide a longer quote.", f"evidence[{idx}].quote"))
            else:
                # Valid unique quote
                ev.char_start = start
                ev.char_end = end

                # Derive section from first evidence span and check front matter / memo boundary
                doc_text = self.locator.get_document_text(ev.doc_id)
                secs = parse_sections(doc_text)
                matched_sec = find_section_for_offset(secs, start)

                if idx == 0 and matched_sec:
                    q.section = matched_sec.label

                # Check front matter boundary (title block, status of this memo, abstract, table of contents)
                body_start = self.get_body_start(ev.doc_id)
                is_front_matter = False
                if start < body_start or matched_sec is None:
                    is_front_matter = True
                elif any(kw in matched_sec.title.lower() for kw in FRONT_MATTER_SECTION_KEYWORDS):
                    is_front_matter = True

                if is_front_matter:
                    sec_name = matched_sec.label if matched_sec else f"char_start {start} < body_start {body_start}"
                    issues.append(
                        ValidationIssue(
                            q.id,
                            "front_matter",
                            f"Evidence #{idx+1} is located in non-body front matter ({sec_name})",
                            f"evidence[{idx}].quote",
                        )
                    )

        # Compute wording overlap flags against evidence text
        if q.evidence:
            ev_combined = " ".join(e.quote for e in q.evidence if e.quote)
            run = compute_longest_common_word_run(q.question, ev_combined)
            jac = compute_jaccard_similarity(q.question, ev_combined)
            q.lexical_overlap_run = run
            q.lexical_overlap_jaccard = round(jac, 4)
            q.flagged_too_easy = bool(run >= 5 or jac > 0.5)
            if q.flagged_too_easy:
                issues.append(
                    ValidationIssue(
                        q.id,
                        "too_easy",
                        f"Question wording has excessive lexical overlap with evidence (longest run={run} words, jaccard={jac:.3f}). Rephrase question.",
                        "question",
                    )
                )

        return issues

    def validate_all(self, questions: list[Question]) -> list[ValidationIssue]:
        all_issues: list[ValidationIssue] = []

        seen_ids: set[str] = set()
        seen_texts: set[str] = set()

        for q in questions:
            # Check ID uniqueness
            if q.id in seen_ids:
                all_issues.append(ValidationIssue(q.id, "duplicate_id", f"Duplicate question ID '{q.id}'", "id"))
            seen_ids.add(q.id)

            # Check Question text uniqueness
            norm_q = " ".join(q.question.strip().lower().split())
            if norm_q in seen_texts:
                all_issues.append(ValidationIssue(q.id, "duplicate_question", f"Duplicate question text: '{q.question}'", "question"))
            seen_texts.add(norm_q)

            # Validate individual question
            q_issues = self.validate_question(q)
            all_issues.extend(q_issues)

        return all_issues


class RelevanceMapper:
    """
    Computes gold relevance for a question against an index of Chunks.
    A chunk is relevant if it overlaps an evidence span by >= min_overlap_chars
    OR fully contains the evidence span.
    """

    def __init__(self, min_overlap_chars: int = DEFAULT_MIN_OVERLAP_CHARS) -> None:
        self.min_overlap_chars = min_overlap_chars

    def is_chunk_relevant_to_span(self, chunk: Chunk, doc_id: str, span_start: int, span_end: int) -> bool:
        if chunk.doc_id != doc_id:
            return False

        # Calculate overlap
        overlap_start = max(chunk.char_start, span_start)
        overlap_end = min(chunk.char_end, span_end)
        overlap = max(0, overlap_end - overlap_start)

        # Full containment check
        if chunk.char_start <= span_start and chunk.char_end >= span_end:
            return True

        # Effective threshold: min(min_overlap_chars, span_length)
        span_length = span_end - span_start
        threshold = min(self.min_overlap_chars, span_length)
        return overlap >= threshold

    def get_relevant_chunks(
        self,
        question: Question,
        chunks: list[Chunk],
        config_label: str = "",
        allow_empty: bool = False,
    ) -> list[Chunk]:
        """
        Return the subset of chunks that are relevant to this question.
        If allow_empty is False and no chunks are relevant, raises NoRelevantChunksError.
        """
        relevant: list[Chunk] = []

        # Ensure all evidence items have resolved char_start/char_end
        for ev in question.evidence:
            if ev.char_start < 0 or ev.char_end < 0:
                raise EvaluationError(
                    f"Question '{question.id}' has unresolved evidence coordinates. Run validator first."
                )

        for chunk in chunks:
            # Chunk is relevant if it is relevant to ANY evidence span of the question
            for ev in question.evidence:
                if self.is_chunk_relevant_to_span(chunk, ev.doc_id, ev.char_start, ev.char_end):
                    relevant.append(chunk)
                    break

        if not relevant and not allow_empty:
            raise NoRelevantChunksError(
                f"Question '{question.id}' has ZERO relevant chunks under chunking config '{config_label}'"
            )

        return relevant


def load_questions(path: Path | None = None) -> list[Question]:
    """Load questions from JSON file."""
    path = path or DEFAULT_QUESTIONS_PATH
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [Question.from_dict(item) for item in data]


def save_questions(questions: list[Question], path: Path | None = None) -> None:
    """Save questions to JSON file with indentation."""
    path = path or DEFAULT_QUESTIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = [q.to_dict() for q in questions]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
