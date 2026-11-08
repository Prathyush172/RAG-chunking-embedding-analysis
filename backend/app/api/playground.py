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
    PlaygroundConfigItem,
    PlaygroundConfigResult,
    RetrievedChunkDetail,
    QuestionSchema,
)
from app.core.index import compute_cache_key, compute_corpus_hash
from dataclasses import asdict
import threading

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

    target_configs: list[dict[str, str]] = []
    if payload.configs:
        target_configs = [{"chunk_config": c.chunk_config, "model_id": c.model_id} for c in payload.configs[:3]]
    elif payload.chunk_config and payload.model_id:
        target_configs = [{"chunk_config": payload.chunk_config, "model_id": payload.model_id}]
    else:
        target_configs = [{"chunk_config": "fixed_256_0", "model_id": "minilm"}]

    pipeline = RetrievalPipeline(clean_dir=CLEAN_DIR)
    enc = tiktoken.get_encoding("cl100k_base")
    corpus_hash = compute_corpus_hash(CLEAN_DIR)

    # Check for gold question match across corpus questions
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

    config_results: list[PlaygroundConfigResult] = []

    for cfg_item in target_configs:
        c_label = cfg_item["chunk_config"]
        m_id = cfg_item["model_id"]
        c_cfg = get_chunk_config_by_label(c_label)
        model_cfg = pipeline.models_config[m_id]

        c_key = compute_cache_key(
            chunk_config=c_cfg,
            model_config=asdict(model_cfg) if hasattr(model_cfg, "__dataclass_fields__") else model_cfg,
            corpus_hash=corpus_hash,
            exclude_front_matter=True,
        )
        cache_path = pipeline.artifacts_dir / c_key
        is_cached = cache_path.exists() and (cache_path / "index.faiss").exists() and (cache_path / "meta.json").exists()

        if not is_cached:
            # Not yet cached: trigger async background build and return building status
            job_id = f"build_{c_label}_{m_id}"
            threading.Thread(
                target=pipeline.get_or_build_index,
                args=(c_cfg, m_id, True),
                daemon=True,
            ).start()
            config_results.append(
                PlaygroundConfigResult(
                    chunk_config=c_label,
                    model_id=m_id,
                    status="building",
                    job_id=job_id,
                    latency_ms=0.0,
                    retrieved_chunks=[],
                    gold_overlap=None,
                )
            )
            continue

        artifacts, _ = pipeline.get_or_build_index(chunk_config=c_cfg, model_id=m_id)
        ret_result = pipeline.retrieve(
            query=payload.query,
            chunk_config=c_cfg,
            model_id=m_id,
            k=payload.k,
        )

        chunk_lookup = {c.chunk_id: c for c in artifacts.chunks}
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

        config_results.append(
            PlaygroundConfigResult(
                chunk_config=c_label,
                model_id=m_id,
                status="ready",
                job_id=None,
                latency_ms=ret_result.latency_ms,
                retrieved_chunks=retrieved_details,
                gold_overlap=gold_overlap,
            )
        )

    # First config result for single-config compatibility
    first_res = config_results[0] if config_results else None

    return PlaygroundResponse(
        query=payload.query,
        k=payload.k,
        configs=config_results,
        matched_gold_question=QuestionSchema(**matched_q.to_dict()) if matched_q else None,
        chunk_config=first_res.chunk_config if first_res else None,
        model_id=first_res.model_id if first_res else None,
        latency_ms=first_res.latency_ms if first_res else None,
        retrieved_chunks=first_res.retrieved_chunks if first_res else [],
        gold_overlap=first_res.gold_overlap if first_res else None,
    )
