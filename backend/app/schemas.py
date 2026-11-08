from __future__ import annotations
import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Base / Generic Error Envelope
# -----------------------------------------------------------------------------
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "ok"
    device: str = "cpu"
    faiss_threads: int = 1
    python_version: str
    corpus_hash: str
    questions_hash: str
    indexed_configs: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Corpus
# -----------------------------------------------------------------------------
class DocumentSummary(BaseModel):
    doc_id: str
    rfc_number: int
    title: str
    source_url: str
    char_count: int
    token_count: int
    section_count: int


class SectionOutlineItem(BaseModel):
    id: str
    number: str
    title: str
    level: int
    char_start: int
    char_end: int
    label: str


class SearchMatchItem(BaseModel):
    doc_id: str
    char_start: int
    char_end: int
    snippet: str
    section: str | None = None


# -----------------------------------------------------------------------------
# Questions & Review
# -----------------------------------------------------------------------------
class EvidenceItemSchema(BaseModel):
    doc_id: str
    quote: str
    char_start: int | None = None
    char_end: int | None = None


class QuestionSchema(BaseModel):
    id: str
    question: str
    doc_id: str
    section: str
    evidence: list[EvidenceItemSchema]
    reference_answer: str
    type: Literal["factual", "definition", "procedural", "multi-hop"]
    difficulty: Literal["easy", "medium", "hard"]
    verified: bool = False
    drafted_by: str = "llm"
    notes: str | None = None
    reviewer: str | None = None
    lexical_overlap_run: int | None = None
    lexical_overlap_jaccard: float | None = None
    flagged_too_easy: bool = False
    verified_at: str | None = None


class QuestionReviewRequest(BaseModel):
    verdict: Literal["approve", "reject", "edit"]
    notes: str | None = None
    reviewer: str | None = None
    question: str | None = None
    reference_answer: str | None = None


class QuestionCreateSchema(BaseModel):
    id: str | None = None
    question: str
    doc_id: str
    evidence: list[EvidenceItemSchema]
    reference_answer: str
    type: Literal["factual", "definition", "procedural", "multi-hop"]
    difficulty: Literal["easy", "medium", "hard"]
    notes: str | None = None


class QuestionUpdateSchema(BaseModel):
    question: str | None = None
    reference_answer: str | None = None
    type: Literal["factual", "definition", "procedural", "multi-hop"] | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    verified: bool | None = None
    notes: str | None = None
    reviewer: str | None = None


class ValidationIssueSchema(BaseModel):
    question_id: str
    issue_type: str
    message: str
    field: str | None = None


class ValidationResponse(BaseModel):
    valid: bool
    total_questions: int
    issue_count: int
    issues: list[ValidationIssueSchema]


class QuestionStatsResponse(BaseModel):
    total: int
    verified: int
    unverified: int
    by_doc: dict[str, int]
    by_type: dict[str, int]
    by_difficulty: dict[str, int]
    flagged_too_easy_count: int


class ReviewProgressResponse(BaseModel):
    total: int
    verified: int
    unverified: int
    percent_verified: float


# -----------------------------------------------------------------------------
# Configurations & Estimation
# -----------------------------------------------------------------------------
class PresetInfo(BaseModel):
    id: str
    name: str
    description: str
    chunk_configs: list[str]
    models: list[str]
    k: int


class ModelInfo(BaseModel):
    id: str
    name: str
    huggingface_id: str
    dimension: int
    max_tokens: int
    description: str
    supports_prefix: bool


class ChunkerInfo(BaseModel):
    id: str
    name: str
    strategy: str
    description: str
    parameters: dict[str, Any]


class EstimateRequest(BaseModel):
    chunk_configs: list[str]
    models: list[str]
    questions_count: int = 56
    k: int = 5


class EstimateResponse(BaseModel):
    total_combinations: int
    estimated_preprocessing_sec: float
    estimated_indexing_sec: float
    estimated_eval_sec: float
    total_estimated_sec: float
    estimated_index_size_mb: float


# -----------------------------------------------------------------------------
# Experiments & Runs
# -----------------------------------------------------------------------------
class ExperimentCreateRequest(BaseModel):
    name: str | None = None
    preset: str | None = "quick"
    configs: list[str] | None = None
    models: list[str] | None = None
    k: int = 5
    verified_only: bool = False
    llm_judge: str = "mock"


class ExperimentRunResponse(BaseModel):
    id: int
    chunk_config: str
    model_id: str
    status: str
    stage: str
    progress: float
    message: str | None = None


class ExperimentResponse(BaseModel):
    id: str
    name: str
    preset: str | None
    status: str
    created_at: datetime.datetime | None
    started_at: datetime.datetime | None
    finished_at: datetime.datetime | None
    error: str | None
    verified_only: bool
    verified_questions_count: int
    unverified_questions_count: int
    has_unverified: bool
    runs: list[ExperimentRunResponse] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Results
# -----------------------------------------------------------------------------
class ResultSummaryItem(BaseModel):
    config: str
    model: str
    hit_at_k: float
    hit_ci_lower: float
    hit_ci_upper: float
    mrr: float
    mrr_ci_lower: float
    mrr_ci_upper: float
    precision_at_k: float
    precision_ci_lower: float
    precision_ci_upper: float
    recall_at_k: float
    recall_ci_lower: float
    recall_ci_upper: float
    context_precision: float
    context_precision_ci_lower: float
    context_precision_ci_upper: float
    context_recall: float
    context_recall_ci_lower: float
    context_recall_ci_upper: float
    truncation_rate: float
    mean_latency_ms: float
    chunk_count: int
    avg_tokens: float
    index_size_mb: float
    groundedness_score: float | None = None
    cost_usd: float | None = None


class ResultSummaryResponse(BaseModel):
    experiment_id: str
    unverified_included: bool = True
    has_unverified: bool = True
    verified_questions_count: int = 0
    unverified_questions_count: int = 0
    notice: str | None = None
    rows: list[ResultSummaryItem]


class ResultPerQueryItem(BaseModel):
    question_id: str
    doc_id: str
    config: str
    model: str
    hit_at_k: float
    reciprocal_rank: float
    precision_at_k: float
    recall_at_k: float
    context_precision: float
    context_recall: float
    all_evidence_hit: bool
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    retrieved_scores: list[float] = Field(default_factory=list)
    latency_ms: float


class ParetoPoint(BaseModel):
    config: str
    model: str
    hit_at_k: float
    mrr: float
    mean_latency_ms: float
    index_size_mb: float
    avg_tokens: float
    chunk_count: int


class HeatmapResponse(BaseModel):
    metric: str
    strategies: list[str]
    models: list[str]
    matrix: dict[str, dict[str, float]]


# -----------------------------------------------------------------------------
# Compare
# -----------------------------------------------------------------------------
class CompareRequest(BaseModel):
    experiment_id: str
    base_config: str
    base_model: str
    target_config: str
    target_model: str


class MetricDeltaItem(BaseModel):
    metric: str
    base_mean: float
    target_mean: float
    delta: float
    delta_ci_lower: float
    delta_ci_upper: float
    p_value: float
    statistically_significant: bool


class CompareResponse(BaseModel):
    experiment_id: str
    unverified_included: bool = True
    has_unverified: bool = True
    verified_questions_count: int = 0
    unverified_questions_count: int = 0
    base_label: str
    target_label: str
    metrics: list[MetricDeltaItem]
    win_loss_tie: dict[str, int]
    note: str | None = None


# -----------------------------------------------------------------------------
# Playground
# -----------------------------------------------------------------------------
class PlaygroundConfigItem(BaseModel):
    chunk_config: str
    model_id: str


class PlaygroundConfigResult(BaseModel):
    chunk_config: str
    model_id: str
    latency_ms: float = 0.0
    status: str = "ready"  # ready, building
    job_id: str | None = None
    retrieved_chunks: list[RetrievedChunkDetail] = Field(default_factory=list)
    gold_overlap: dict[str, Any] | None = None


class PlaygroundRequest(BaseModel):
    query: str
    chunk_config: str | None = None
    model_id: str | None = None
    configs: list[PlaygroundConfigItem] | None = None
    k: int = 5


class RetrievedChunkDetail(BaseModel):
    rank: int
    chunk_id: str
    doc_id: str
    score: float
    section: str | None
    token_count: int
    char_start: int
    char_end: int
    text: str
    truncated: bool


class PlaygroundResponse(BaseModel):
    query: str
    k: int
    configs: list[PlaygroundConfigResult] = Field(default_factory=list)
    matched_gold_question: QuestionSchema | None = None
    # Backward compatibility fields for single-config responses
    chunk_config: str | None = None
    model_id: str | None = None
    latency_ms: float | None = None
    retrieved_chunks: list[RetrievedChunkDetail] = Field(default_factory=list)
    gold_overlap: dict[str, Any] | None = None


# -----------------------------------------------------------------------------
# Decision Matrix
# -----------------------------------------------------------------------------
class DecisionMatrixWeights(BaseModel):
    hit_at_k: float = 0.25
    mrr: float = 0.20
    context_precision: float = 0.15
    context_recall: float = 0.15
    latency: float = 0.10
    index_size: float = 0.05
    cost: float = 0.10
    groundedness: float = 0.0


class DecisionMatrixRankItem(BaseModel):
    rank: int
    config: str
    model: str
    total_utility_score: float
    subscores: dict[str, float]
    raw_metrics: dict[str, float]


class DecisionMatrixRequest(BaseModel):
    experiment_id: str
    weights: DecisionMatrixWeights = Field(default_factory=DecisionMatrixWeights)


class DecisionMatrixPreset(BaseModel):
    id: str
    name: str
    description: str
    weights: DecisionMatrixWeights


# -----------------------------------------------------------------------------
# Settings
# -----------------------------------------------------------------------------
class SettingsSchema(BaseModel):
    llm_judge_provider: str = "mock"
    llm_judge_model: str = "mock-judge"
    openai_api_key_masked: str | None = None
    gemini_api_key_masked: str | None = None
    ollama_base_url: str = "http://localhost:11434"


class SettingsUpdateSchema(BaseModel):
    llm_judge_provider: str | None = None
    llm_judge_model: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str | None = None
