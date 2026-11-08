from fastapi import APIRouter
from app.core.embedders import load_models_config
from app.core.jobs import PRESET_CONFIGS
from app.schemas import (
    PresetInfo,
    ModelInfo,
    ChunkerInfo,
    EstimateRequest,
    EstimateResponse,
)

router = APIRouter(prefix="/configs", tags=["configs"])

CHUNKER_CATALOG = [
    {
        "id": "fixed",
        "name": "Fixed-Size Token Window",
        "strategy": "fixed",
        "description": "Splits text strictly at token boundaries with configurable token window size N and overlap percentage.",
        "parameters": {
            "token_window": [128, 256, 512],
            "overlap_percent": [0, 15],
            "tokenizer": "tiktoken (cl100k_base)",
        },
    },
    {
        "id": "sentence",
        "name": "RFC-Aware Sentence Packing",
        "strategy": "sentence",
        "description": "Splits text at RFC-aware sentence boundaries, packing complete sentences up to N tokens with 0 or 1 sentence overlap.",
        "parameters": {
            "max_tokens": [128, 256, 512],
            "overlap_sentences": [0, 1],
            "tokenizer": "tiktoken (cl100k_base)",
        },
    },
    {
        "id": "semantic",
        "name": "Semantic Coherence Splitter",
        "strategy": "semantic",
        "description": "Splits text where cosine similarity between adjacent sentence embeddings falls below the 25th percentile, respecting min/max token bounds.",
        "parameters": {
            "embedder": "all-MiniLM-L6-v2",
            "percentile_threshold": 25,
            "min_tokens": 64,
            "max_tokens": 512,
        },
    },
]


@router.get("/presets", response_model=list[PresetInfo])
def get_presets() -> list[PresetInfo]:
    return [
        PresetInfo(
            id="quick",
            name="Quick Smoke Benchmark",
            description="3 representative chunking strategies across 3 models (~1-2 min runtime on CPU).",
            chunk_configs=PRESET_CONFIGS["quick"]["configs"],
            models=PRESET_CONFIGS["quick"]["models"],
            k=PRESET_CONFIGS["quick"]["k"],
        ),
        PresetInfo(
            id="standard",
            name="Standard Research Evaluation",
            description="9 chunking configurations across 3 models (~5-10 min runtime on CPU).",
            chunk_configs=PRESET_CONFIGS["standard"]["configs"],
            models=PRESET_CONFIGS["standard"]["models"],
            k=PRESET_CONFIGS["standard"]["k"],
        ),
        PresetInfo(
            id="comprehensive",
            name="Comprehensive Full Grid",
            description="All 13 chunking configurations across 3 models (~15-20 min runtime on CPU).",
            chunk_configs=PRESET_CONFIGS["comprehensive"]["configs"],
            models=PRESET_CONFIGS["comprehensive"]["models"],
            k=PRESET_CONFIGS["comprehensive"]["k"],
        ),
    ]


@router.get("/models", response_model=list[ModelInfo])
def get_models() -> list[ModelInfo]:
    models_cfg = load_models_config()
    models: list[ModelInfo] = []
    for m_id, m in models_cfg.items():
        models.append(
            ModelInfo(
                id=m_id,
                name=m.name,
                huggingface_id=m.hf_path,
                dimension=m.embedding_dim,
                max_tokens=m.max_seq_length,
                description=m.description or f"{m.name} dense embedder",
                supports_prefix=bool(m.query_prefix or m.passage_prefix),
            )
        )
    return models


@router.get("/chunkers", response_model=list[ChunkerInfo])
def get_chunkers() -> list[ChunkerInfo]:
    return [ChunkerInfo(**c) for c in CHUNKER_CATALOG]


@router.post("/estimate", response_model=EstimateResponse)
def estimate_compute(req: EstimateRequest) -> EstimateResponse:
    num_configs = len(req.chunk_configs)
    num_models = len(req.models)
    total_combos = num_configs * num_models

    # Empirical estimates on modern CPU
    est_preprocess = num_configs * 0.4
    est_index = total_combos * 1.5
    est_eval = total_combos * (req.questions_count * 0.015)
    total_sec = est_preprocess + est_index + est_eval
    est_size_mb = total_combos * 4.5

    return EstimateResponse(
        total_combinations=total_combos,
        estimated_preprocessing_sec=round(est_preprocess, 1),
        estimated_indexing_sec=round(est_index, 1),
        estimated_eval_sec=round(est_eval, 1),
        total_estimated_sec=round(total_sec, 1),
        estimated_index_size_mb=round(est_size_mb, 1),
    )
