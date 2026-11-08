import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from app.core.sections import parse_sections, find_section_for_offset
from app.schemas import DocumentSummary, SectionOutlineItem, SearchMatchItem
import tiktoken

router = APIRouter(prefix="/corpus", tags=["corpus"])

CONFIGS_DIR = Path("configs")
CLEAN_DIR = Path("data/clean")


def get_corpus_meta() -> dict:
    corpus_yaml = CONFIGS_DIR / "corpus.yaml"
    if not corpus_yaml.exists():
        return {}
    with open(corpus_yaml, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw_corpus = data.get("corpus") or data.get("documents") or {}
    if isinstance(raw_corpus, list):
        return {item["doc_id"]: item for item in raw_corpus if "doc_id" in item}
    elif isinstance(raw_corpus, dict):
        return raw_corpus
    return {}


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents() -> list[DocumentSummary]:
    meta = get_corpus_meta()
    enc = tiktoken.get_encoding("cl100k_base")
    docs: list[DocumentSummary] = []

    for doc_id, info in meta.items():
        doc_file = CLEAN_DIR / f"{doc_id}.txt"
        if not doc_file.exists():
            continue
        text = doc_file.read_text(encoding="utf-8")
        tokens = len(enc.encode(text))
        secs = parse_sections(text)
        docs.append(
            DocumentSummary(
                doc_id=doc_id,
                rfc_number=info.get("rfc_number", 0),
                title=info.get("title", ""),
                source_url=info.get("source_url", ""),
                char_count=len(text),
                token_count=tokens,
                section_count=len(secs),
            )
        )
    return docs


@router.get("/documents/{doc_id}/text")
def get_document_text(doc_id: str) -> dict[str, str]:
    doc_file = CLEAN_DIR / f"{doc_id}.txt"
    if not doc_file.exists():
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    return {"doc_id": doc_id, "text": doc_file.read_text(encoding="utf-8")}


@router.get("/documents/{doc_id}/sections", response_model=list[SectionOutlineItem])
def get_document_sections(doc_id: str) -> list[SectionOutlineItem]:
    doc_file = CLEAN_DIR / f"{doc_id}.txt"
    if not doc_file.exists():
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")
    text = doc_file.read_text(encoding="utf-8")
    secs = parse_sections(text)
    return [
        SectionOutlineItem(
            id=s.number,
            number=s.number,
            title=s.title,
            level=s.level,
            char_start=s.char_start,
            char_end=s.char_end,
            label=s.label,
        )
        for s in secs
    ]


@router.get("/search", response_model=list[SearchMatchItem])
def search_corpus(
    q: str = Query(..., min_length=2, description="Search query"),
    doc_id: str | None = Query(None, description="Optional document ID to limit search"),
    limit: int = Query(20, ge=1, le=100),
) -> list[SearchMatchItem]:
    results: list[SearchMatchItem] = []
    meta = get_corpus_meta()
    target_docs = [doc_id] if doc_id and doc_id in meta else list(meta.keys())

    q_lower = q.lower()
    for d_id in target_docs:
        doc_file = CLEAN_DIR / f"{d_id}.txt"
        if not doc_file.exists():
            continue
        text = doc_file.read_text(encoding="utf-8")
        secs = parse_sections(text)

        start = 0
        while True:
            idx = text.lower().find(q_lower, start)
            if idx == -1:
                break

            matched_sec = find_section_for_offset(secs, idx)
            snippet_start = max(0, idx - 100)
            snippet_end = min(len(text), idx + len(q) + 100)
            snippet = text[snippet_start:snippet_end].replace("\n", " ")

            results.append(
                SearchMatchItem(
                    doc_id=d_id,
                    char_start=idx,
                    char_end=idx + len(q),
                    snippet=snippet,
                    section=matched_sec.label if matched_sec else None,
                )
            )
            if len(results) >= limit:
                return results
            start = idx + len(q)

    return results
