import time
from pathlib import Path
from typing import Any
import yaml
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


def get_chunk_config_by_label(label: str) -> dict[str, Any]:
    exp_yaml_path = Path("configs/experiment.yaml")
    if exp_yaml_path.exists():
        with open(exp_yaml_path, encoding="utf-8") as f:
            exp_yaml = yaml.safe_load(f) or {}
        for p in exp_yaml.get("presets", {}).values():
            for c in p.get("chunking_configs", []):
                if c.get("label") == label:
                    return c
    if label.startswith("fixed_"):
        parts = label.split("_")
        return {"strategy": "fixed", "chunk_tokens": int(parts[1]), "overlap_pct": float(parts[2]) / 100.0, "label": label}
    elif label.startswith("sent_"):
        parts = label.split("_")
        return {"strategy": "sentence", "chunk_tokens": int(parts[1]), "overlap_sentences": int(parts[2]), "label": label}
    elif "semantic" in label:
        return {"strategy": "semantic", "max_tokens": 512, "similarity_percentile": 25, "min_tokens": 64, "label": label}
    return {"strategy": "fixed", "chunk_tokens": 256, "overlap_pct": 0.0, "label": label}


@router.post("/query", response_model=PlaygroundResponse)
def execute_playground_query(payload: PlaygroundRequest) -> PlaygroundResponse:
    if not payload.query or not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    c_cfg = get_chunk_config_by_label(payload.chunk_config)
    pipeline = RetrievalPipeline(clean_dir=CLEAN_DIR)
    artifacts, _ = pipeline.get_or_build_index(chunk_config=c_cfg, model_id=payload.model_id)

    ret_result = pipeline.retrieve(
        query=payload.query,
        chunk_config=c_cfg,
        model_id=payload.model_id,
        k=payload.k,
    )

    chunk_lookup = {c.chunk_id: c for c in artifacts.chunks}
    model_cfg = pipeline.models_config[payload.model_id]
    enc = tiktoken.get_encoding("cl100k_base")
    retrieved_details: list[RetrievedChunkDetail] = []

    for rank, item in enumerate(ret_result.results, start=1):
        chunk = chunk_lookup.get(item.chunk_id)
        tok_cnt = chunk.token_count if chunk else len(enc.encode(item.text))
        retrieved_details.append(
            RetrievedChunkDetail(
                rank=rank,
                chunk_id=item.chunk_id,
                doc_id=item.doc_id,
                score=round(item.score, 4),
                section=item.section,
                token_count=tok_cnt,
                char_start=item.char_start,
                char_end=item.char_end,
                text=item.text,
                truncated=tok_cnt > model_cfg.max_seq_length,
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
        retrieved_ids = [item.chunk_id for item in ret_result.results]
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
        latency_ms=ret_result.latency_ms,
        retrieved_chunks=retrieved_details,
        matched_gold_question=QuestionSchema(**matched_q.to_dict()) if matched_q else None,
        gold_overlap=gold_overlap,
    )
