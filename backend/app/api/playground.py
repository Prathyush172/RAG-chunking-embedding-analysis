import time
from pathlib import Path
from fastapi import APIRouter, HTTPException
import tiktoken

from app.core.evaluation import (
    load_questions,
    compute_jaccard_similarity,
    RelevanceMapper,
)
from app.core.jobs import QUESTIONS_FILE, CLEAN_DIR
from app.core.retrieval import RetrievalPipeline
from app.schemas import (
    PlaygroundRequest,
    PlaygroundResponse,
    RetrievedChunkDetail,
    QuestionSchema,
)

router = APIRouter(prefix="/playground", tags=["playground"])


@router.post("/query", response_model=PlaygroundResponse)
def execute_playground_query(payload: PlaygroundRequest) -> PlaygroundResponse:
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    pipeline = RetrievalPipeline(
        chunk_config=payload.chunk_config,
        embedding_model=payload.model_id,
        clean_dir=CLEAN_DIR,
    )
    artifacts = pipeline.prepare()

    t_start = time.perf_counter()
    chunks, scores = pipeline.retrieve(payload.query, k=payload.k)
    t_end = time.perf_counter()
    latency_ms = (t_end - t_start) * 1000.0

    enc = tiktoken.get_encoding("cl100k_base")
    retrieved_details: list[RetrievedChunkDetail] = []

    for rank, (chunk, score) in enumerate(zip(chunks, scores), start=1):
        retrieved_details.append(
            RetrievedChunkDetail(
                rank=rank,
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                score=round(float(score), 4),
                section=chunk.section,
                token_count=chunk.token_count,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                text=chunk.text,
                truncated=chunk.token_count > pipeline.model.max_tokens,
            )
        )

    # Check for gold question match
    all_questions = load_questions(QUESTIONS_FILE)
    matched_q = None
    best_sim = 0.0

    for q in all_questions:
        if q.question.strip().lower() == payload.query.strip().lower():
            matched_q = q
            break
        sim = compute_jaccard_similarity(payload.query, q.question)
        if sim > best_sim:
            best_sim = sim
            if sim >= 0.7:
                matched_q = q

    gold_overlap = None
    if matched_q:
        relevance_mapper = RelevanceMapper()
        relevant_chunk_ids = relevance_mapper.get_relevant_chunks(matched_q, artifacts.chunks)
        retrieved_ids = [c.chunk_id for c in chunks]
        hits = [cid for cid in retrieved_ids if cid in relevant_chunk_ids]
        gold_overlap = {
            "matched_question_id": matched_q.id,
            "relevant_chunks_in_index": len(relevant_chunk_ids),
            "hits_in_top_k": len(hits),
            "hit_at_k": float(len(hits) > 0),
            "all_evidence_hit": bool(all(cid in retrieved_ids for cid in relevant_chunk_ids)),
        }

    return PlaygroundResponse(
        query=payload.query,
        chunk_config=payload.chunk_config,
        model_id=payload.model_id,
        k=payload.k,
        latency_ms=round(latency_ms, 2),
        retrieved_chunks=retrieved_details,
        matched_gold_question=QuestionSchema(**matched_q.to_dict()) if matched_q else None,
        gold_overlap=gold_overlap,
    )
