import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from app.db.session import Base


class ExperimentModel(Base):
    __tablename__ = "experiments"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    preset = Column(String, nullable=True)
    config_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="queued")  # queued, running, completed, cancelled, interrupted, failed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    verified_only = Column(Boolean, default=False)
    verified_questions_count = Column(Integer, default=0)
    unverified_questions_count = Column(Integer, default=0)
    has_unverified = Column(Boolean, default=True)

    runs = relationship("ExperimentRunModel", back_populates="experiment", cascade="all, delete-orphan")
    summaries = relationship("ResultSummaryModel", back_populates="experiment", cascade="all, delete-orphan")
    query_results = relationship("ResultPerQueryModel", back_populates="experiment", cascade="all, delete-orphan")


class ExperimentRunModel(Base):
    __tablename__ = "experiment_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(String, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_config = Column(String, nullable=False)
    model_id = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled
    stage = Column(String, default="pending")  # chunking, embedding, indexing, evaluating, done
    progress = Column(Float, default=0.0)
    message = Column(String, nullable=True)

    experiment = relationship("ExperimentModel", back_populates="runs")


class ResultSummaryModel(Base):
    __tablename__ = "result_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(String, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True)
    run_key = Column(String, nullable=False, index=True)
    config = Column(String, nullable=False)
    model = Column(String, nullable=False)
    hit_at_k = Column(Float, nullable=False)
    hit_ci_lower = Column(Float, nullable=False)
    hit_ci_upper = Column(Float, nullable=False)
    mrr = Column(Float, nullable=False)
    mrr_ci_lower = Column(Float, nullable=False)
    mrr_ci_upper = Column(Float, nullable=False)
    precision_at_k = Column(Float, nullable=False)
    precision_ci_lower = Column(Float, nullable=False)
    precision_ci_upper = Column(Float, nullable=False)
    recall_at_k = Column(Float, nullable=False)
    recall_ci_lower = Column(Float, nullable=False)
    recall_ci_upper = Column(Float, nullable=False)
    context_precision = Column(Float, nullable=False)
    context_precision_ci_lower = Column(Float, nullable=False)
    context_precision_ci_upper = Column(Float, nullable=False)
    context_recall = Column(Float, nullable=False)
    context_recall_ci_lower = Column(Float, nullable=False)
    context_recall_ci_upper = Column(Float, nullable=False)
    truncation_rate = Column(Float, nullable=False)
    mean_latency_ms = Column(Float, nullable=False)
    chunk_count = Column(Integer, nullable=False)
    avg_tokens = Column(Float, nullable=False)
    index_size_mb = Column(Float, nullable=False)
    groundedness_score = Column(Float, nullable=True)
    cost_usd = Column(Float, nullable=True)

    experiment = relationship("ExperimentModel", back_populates="summaries")


class ResultPerQueryModel(Base):
    __tablename__ = "result_per_queries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(String, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True)
    run_key = Column(String, nullable=False, index=True)
    question_id = Column(String, nullable=False, index=True)
    doc_id = Column(String, nullable=False)
    hit_at_k = Column(Float, nullable=False)
    reciprocal_rank = Column(Float, nullable=False)
    precision_at_k = Column(Float, nullable=False)
    recall_at_k = Column(Float, nullable=False)
    context_precision = Column(Float, nullable=False)
    context_recall = Column(Float, nullable=False)
    all_evidence_hit = Column(Boolean, default=False)
    retrieved_chunk_ids = Column(Text, default="[]")
    retrieved_scores = Column(Text, default="[]")
    latency_ms = Column(Float, default=0.0)

    experiment = relationship("ExperimentModel", back_populates="query_results")


class SettingModel(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
