import csv
import io
import json
from pathlib import Path
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from app.core.evaluation import (
    EvidenceItem,
    EvidenceLocator,
    EvidenceValidator,
    Question,
    compute_longest_common_word_run,
    compute_jaccard_similarity,
    load_questions,
    save_questions,
)
from app.core.sections import parse_sections, find_section_for_offset
from app.schemas import (
    QuestionSchema,
    QuestionCreateSchema,
    QuestionUpdateSchema,
    QuestionStatsResponse,
    ReviewProgressResponse,
    ValidationResponse,
    ValidationIssueSchema,
)

router = APIRouter(prefix="/questions", tags=["questions"])

QUESTIONS_FILE = Path("data/eval/questions.json")
CLEAN_DIR = Path("data/clean")


def _read_all_questions() -> list[Question]:
    return load_questions(QUESTIONS_FILE)


def _write_all_questions(questions: list[Question]) -> None:
    save_questions(questions, QUESTIONS_FILE)


@router.get("", response_model=list[QuestionSchema])
def list_questions(
    doc_id: str | None = Query(None),
    type: str | None = Query(None),
    difficulty: str | None = Query(None),
    verified: bool | None = Query(None),
    flagged_too_easy: bool | None = Query(None),
) -> list[QuestionSchema]:
    qs = _read_all_questions()
    if doc_id:
        qs = [q for q in qs if q.doc_id == doc_id]
    if type:
        qs = [q for q in qs if q.type == type]
    if difficulty:
        qs = [q for q in qs if q.difficulty == difficulty]
    if verified is not None:
        qs = [q for q in qs if q.verified == verified]
    if flagged_too_easy is not None:
        qs = [q for q in qs if q.flagged_too_easy == flagged_too_easy]

    return [QuestionSchema(**q.to_dict()) for q in qs]


@router.get("/stats", response_model=QuestionStatsResponse)
def get_questions_stats() -> QuestionStatsResponse:
    qs = _read_all_questions()
    by_doc: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_diff: dict[str, int] = {}
    verified_count = 0
    flagged_count = 0

    for q in qs:
        by_doc[q.doc_id] = by_doc.get(q.doc_id, 0) + 1
        by_type[q.type] = by_type.get(q.type, 0) + 1
        by_diff[q.difficulty] = by_diff.get(q.difficulty, 0) + 1
        if q.verified:
            verified_count += 1
        if q.flagged_too_easy:
            flagged_count += 1

    return QuestionStatsResponse(
        total=len(qs),
        verified=verified_count,
        unverified=len(qs) - verified_count,
        by_doc=by_doc,
        by_type=by_type,
        by_difficulty=by_diff,
        flagged_too_easy_count=flagged_count,
    )


@router.get("/review/progress", response_model=ReviewProgressResponse)
def get_review_progress() -> ReviewProgressResponse:
    qs = _read_all_questions()
    total = len(qs)
    verified = sum(1 for q in qs if q.verified)
    unverified = total - verified
    pct = (verified / total * 100.0) if total > 0 else 0.0
    return ReviewProgressResponse(
        total=total,
        verified=verified,
        unverified=unverified,
        percent_verified=round(pct, 1),
    )


@router.get("/review/next", response_model=QuestionSchema | None)
def get_next_unverified_question() -> QuestionSchema | None:
    qs = _read_all_questions()
    for q in qs:
        if not q.verified:
            return QuestionSchema(**q.to_dict())
    return None


@router.post("/validate", response_model=ValidationResponse)
def validate_all_questions() -> ValidationResponse:
    qs = _read_all_questions()
    validator = EvidenceValidator(CLEAN_DIR)
    issues = validator.validate_all(qs)
    return ValidationResponse(
        valid=len(issues) == 0,
        total_questions=len(qs),
        issue_count=len(issues),
        issues=[
            ValidationIssueSchema(
                question_id=iss.question_id,
                issue_type=iss.issue_type,
                message=iss.message,
                field=iss.field,
            )
            for iss in issues
        ],
    )


@router.get("/export")
def export_questions_csv() -> Response:
    qs = _read_all_questions()
    output = io.StringIO()
    fieldnames = [
        "id", "doc_id", "section", "type", "difficulty", "question",
        "evidence_quote", "reference_answer", "lexical_overlap_run",
        "lexical_overlap_jaccard", "flagged_too_easy", "verdict", "notes", "reviewer",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for q in qs:
        quote_text = "\n---\n".join(e.quote for e in q.evidence)
        writer.writerow({
            "id": q.id,
            "doc_id": q.doc_id,
            "section": q.section,
            "type": q.type,
            "difficulty": q.difficulty,
            "question": q.question,
            "evidence_quote": quote_text,
            "reference_answer": q.reference_answer,
            "lexical_overlap_run": q.lexical_overlap_run,
            "lexical_overlap_jaccard": q.lexical_overlap_jaccard,
            "flagged_too_easy": q.flagged_too_easy,
            "verdict": "approved" if q.verified else "",
            "notes": q.notes or "",
            "reviewer": q.reviewer or "",
        })

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=review_sheet.csv"},
    )


@router.post("/import")
async def import_questions_csv(request: Request) -> dict[str, Any]:
    content_bytes = await request.body()
    content = content_bytes.decode("utf-8", errors="replace")
    if "filename=" in content:
        parts = content.split("\r\n\r\n", 1)
        if len(parts) > 1:
            content = parts[1].rsplit("\r\n--", 1)[0]

    reader = csv.DictReader(io.StringIO(content))

    qs = _read_all_questions()
    qs_map = {q.id: q for q in qs}
    updated_count = 0

    for row in reader:
        qid = row.get("id")
        if not qid or qid not in qs_map:
            continue
        q = qs_map[qid]
        verdict = row.get("verdict", "").strip().lower()
        if verdict in ("approved", "yes", "true", "1"):
            q.verified = True
        elif verdict in ("rejected", "no", "false", "0"):
            q.verified = False

        if row.get("notes"):
            q.notes = row["notes"].strip()
        if row.get("reviewer"):
            q.reviewer = row["reviewer"].strip()
        updated_count += 1

    _write_all_questions(qs)
    return {"message": f"Successfully updated {updated_count} questions from review sheet."}


@router.get("/{qid}", response_model=QuestionSchema)
def get_question(qid: str) -> QuestionSchema:
    qs = _read_all_questions()
    for q in qs:
        if q.id == qid:
            return QuestionSchema(**q.to_dict())
    raise HTTPException(status_code=404, detail=f"Question '{qid}' not found")


@router.post("", response_model=QuestionSchema)
def create_question(payload: QuestionCreateSchema) -> QuestionSchema:
    qs = _read_all_questions()
    qid = payload.id or f"{payload.doc_id}-{len(qs)+1:02d}"

    if any(q.id == qid for q in qs):
        raise HTTPException(status_code=400, detail=f"Question ID '{qid}' already exists")

    # Locate evidence quotes and validate
    locator = EvidenceLocator(CLEAN_DIR)
    ev_items: list[EvidenceItem] = []
    for ev in payload.evidence:
        matches = locator.find_quote(ev.doc_id, ev.quote)
        if not matches:
            raise HTTPException(status_code=400, detail=f"Quote not found in {ev.doc_id}")
        if len(matches) > 1:
            raise HTTPException(status_code=400, detail=f"Quote is ambiguous in {ev.doc_id} ({len(matches)} occurrences)")
        start, end = matches[0]
        ev_items.append(EvidenceItem(doc_id=ev.doc_id, quote=ev.quote, char_start=start, char_end=end))

    # Derive section from first evidence span
    doc_text = locator.get_document_text(payload.doc_id)
    secs = parse_sections(doc_text)
    matched_sec = find_section_for_offset(secs, ev_items[0].char_start or 0)
    derived_section = matched_sec.label if matched_sec else "General"

    ev_combined = " ".join(e.quote for e in ev_items)
    run = compute_longest_common_word_run(payload.question, ev_combined)
    jac = compute_jaccard_similarity(payload.question, ev_combined)

    new_q = Question(
        id=qid,
        question=payload.question,
        doc_id=payload.doc_id,
        section=derived_section,
        evidence=ev_items,
        reference_answer=payload.reference_answer,
        type=payload.type,
        difficulty=payload.difficulty,
        verified=False,
        drafted_by="api",
        notes=payload.notes,
        reviewer=None,
        lexical_overlap_run=run,
        lexical_overlap_jaccard=round(jac, 4),
        flagged_too_easy=bool(run >= 5 or jac > 0.5),
    )

    qs.append(new_q)
    _write_all_questions(qs)
    return QuestionSchema(**new_q.to_dict())


@router.put("/{qid}", response_model=QuestionSchema)
def update_question(qid: str, payload: QuestionUpdateSchema) -> QuestionSchema:
    qs = _read_all_questions()
    target_q = None
    for q in qs:
        if q.id == qid:
            target_q = q
            break
    if not target_q:
        raise HTTPException(status_code=404, detail=f"Question '{qid}' not found")

    if payload.question is not None:
        target_q.question = payload.question
        ev_combined = " ".join(e.quote for e in target_q.evidence)
        run = compute_longest_common_word_run(target_q.question, ev_combined)
        jac = compute_jaccard_similarity(target_q.question, ev_combined)
        target_q.lexical_overlap_run = run
        target_q.lexical_overlap_jaccard = round(jac, 4)
        target_q.flagged_too_easy = bool(run >= 5 or jac > 0.5)

    if payload.reference_answer is not None:
        target_q.reference_answer = payload.reference_answer
    if payload.type is not None:
        target_q.type = payload.type
    if payload.difficulty is not None:
        target_q.difficulty = payload.difficulty
    if payload.verified is not None:
        target_q.verified = payload.verified
    if payload.notes is not None:
        target_q.notes = payload.notes
    if payload.reviewer is not None:
        target_q.reviewer = payload.reviewer

    _write_all_questions(qs)
    return QuestionSchema(**target_q.to_dict())


@router.delete("/{qid}")
def delete_question(qid: str) -> dict[str, str]:
    qs = _read_all_questions()
    orig_len = len(qs)
    qs = [q for q in qs if q.id != qid]
    if len(qs) == orig_len:
        raise HTTPException(status_code=404, detail=f"Question '{qid}' not found")
    _write_all_questions(qs)
    return {"message": f"Question '{qid}' deleted successfully"}
