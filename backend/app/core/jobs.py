import collections
import csv
import datetime
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Generator

from app.core.chunkers import build_chunker
from app.core.embedders import load_models_config
from app.core.evaluation import (
    EvidenceLocator,
    Question,
    RelevanceMapper,
    load_questions,
)
from app.core.index import FaissIndexManager
from app.core.metrics import (
    compute_bootstrap_ci,
    evaluate_query_retrieval,
    evaluate_random_baseline,
)
from app.core.retrieval import RetrievalPipeline
from app.db.models import (
    ExperimentModel,
    ExperimentRunModel,
    ResultPerQueryModel,
    ResultSummaryModel,
)
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

CLEAN_DIR = Path("data/clean")
QUESTIONS_FILE = Path("data/eval/questions.json")
RESULTS_DIR = Path("results")

PRESET_CONFIGS = {
    "quick": {
        "configs": ["fixed_256_0", "sent_256_0", "semantic_default"],
        "models": ["minilm", "bge_small", "e5_small"],
        "k": 5,
    },
    "standard": {
        "configs": [
            "fixed_128_0", "fixed_256_0", "fixed_256_15", "fixed_512_0",
            "sent_128_0", "sent_256_0", "sent_256_1", "sent_512_0",
            "semantic_default"
        ],
        "models": ["minilm", "bge_small", "e5_small"],
        "k": 5,
    },
    "comprehensive": {
        "configs": [
            "fixed_128_0", "fixed_128_15", "fixed_256_0", "fixed_256_15", "fixed_512_0", "fixed_512_15",
            "sent_128_0", "sent_128_1", "sent_256_0", "sent_256_1", "sent_512_0", "sent_512_1",
            "semantic_default"
        ],
        "models": ["minilm", "bge_small", "e5_small"],
        "k": 5,
    },
}


class ExperimentJobRunner:
    """
    Manages background thread execution, cancellation, live event streaming,
    and log tailing for experiment runs.
    """

    def __init__(self) -> None:
        self._cancel_flags: dict[str, threading.Event] = {}
        self._event_queues: dict[str, list[queue.Queue]] = collections.defaultdict(list)
        self._logs: dict[str, collections.deque] = collections.defaultdict(lambda: collections.deque(maxlen=1000))
        self._lock = threading.Lock()
        self._active_threads: dict[str, threading.Thread] = {}

    def log(self, experiment_id: str, message: str) -> None:
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        with self._lock:
            self._logs[experiment_id].append(formatted)
        logger.info("[Exp %s] %s", experiment_id, message)

    def get_logs(self, experiment_id: str, tail: int = 100) -> list[str]:
        with self._lock:
            dq = self._logs[experiment_id]
            lines = list(dq)
            return lines[-tail:] if tail < len(lines) else lines

    def emit_event(self, experiment_id: str, data: dict[str, Any]) -> None:
        self.log(experiment_id, f"Event: {data.get('stage')} - {data.get('message')}")
        with self._lock:
            dead_queues = []
            for q in self._event_queues[experiment_id]:
                try:
                    q.put_nowait(data)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                self._event_queues[experiment_id].remove(dq)

    def subscribe_events(self, experiment_id: str) -> Generator[str, None, None]:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._event_queues[experiment_id].append(q)

        try:
            while True:
                try:
                    data = q.get(timeout=2.0)
                    yield f"data: {json.dumps(data)}\n\n"
                    if data.get("stage") in ("done", "cancelled", "failed", "interrupted"):
                        break
                except queue.Empty:
                    # Keep-alive heartbeat
                    yield ": ping\n\n"
        finally:
            with self._lock:
                if q in self._event_queues[experiment_id]:
                    self._event_queues[experiment_id].remove(q)

    def is_cancelled(self, experiment_id: str) -> bool:
        flag = self._cancel_flags.get(experiment_id)
        return flag.is_set() if flag else False

    def cancel(self, experiment_id: str) -> bool:
        with self._lock:
            if experiment_id in self._cancel_flags:
                self._cancel_flags[experiment_id].set()
                self.log(experiment_id, "Cancellation requested by user.")
                return True
            return False

    def start_experiment(
        self,
        experiment_id: str,
        preset: str | None,
        configs: list[str] | None,
        models: list[str] | None,
        k: int = 5,
        verified_only: bool = False,
        resume: bool = False,
    ) -> None:
        with self._lock:
            self._cancel_flags[experiment_id] = threading.Event()
            t = threading.Thread(
                target=self._run_experiment_thread,
                args=(experiment_id, preset, configs, models, k, verified_only, resume),
                daemon=True,
            )
            self._active_threads[experiment_id] = t
            t.start()

    def _run_experiment_thread(
        self,
        experiment_id: str,
        preset: str | None,
        custom_configs: list[str] | None,
        custom_models: list[str] | None,
        k: int,
        verified_only: bool,
        resume: bool,
    ) -> None:
        start_time = time.time()
        db = SessionLocal()
        exp = db.query(ExperimentModel).filter(ExperimentModel.id == experiment_id).first()
        if not exp:
            db.close()
            return

        try:
            exp.status = "running"
            exp.started_at = datetime.datetime.utcnow()
            db.commit()

            self.log(experiment_id, f"Experiment {experiment_id} started (resume={resume}).")

            # Determine configs and models
            if preset and preset in PRESET_CONFIGS:
                cfg_list = PRESET_CONFIGS[preset]["configs"]
                model_list = PRESET_CONFIGS[preset]["models"]
                k_val = PRESET_CONFIGS[preset]["k"]
            else:
                cfg_list = custom_configs or ["fixed_256_0"]
                model_list = custom_models or ["minilm"]
                k_val = k

            # Load questions
            all_questions = load_questions(QUESTIONS_FILE)
            if verified_only:
                questions = [q for q in all_questions if q.verified]
            else:
                questions = all_questions

            unverified_count = sum(1 for q in questions if not q.verified)
            has_unverified = unverified_count > 0

            exp.verified_questions_count = len(questions) - unverified_count
            exp.unverified_questions_count = unverified_count
            exp.has_unverified = has_unverified
            db.commit()

            # Pre-populate experiment runs in DB if not resuming
            total_steps = len(cfg_list) * len(model_list) + 1  # +1 for random baseline
            run_keys_completed = set()

            if resume:
                existing_summaries = db.query(ResultSummaryModel).filter(ResultSummaryModel.experiment_id == experiment_id).all()
                for s in existing_summaries:
                    run_keys_completed.add(s.run_key)
                self.log(experiment_id, f"Resuming: found {len(run_keys_completed)} completed runs to skip.")
            else:
                # Clear previous runs/summaries if any
                db.query(ResultSummaryModel).filter(ResultSummaryModel.experiment_id == experiment_id).delete()
                db.query(ResultPerQueryModel).filter(ResultPerQueryModel.experiment_id == experiment_id).delete()
                db.query(ExperimentRunModel).filter(ExperimentRunModel.experiment_id == experiment_id).delete()
                db.commit()

                for c_name in cfg_list:
                    for m_name in model_list:
                        db.add(ExperimentRunModel(
                            experiment_id=experiment_id,
                            chunk_config=c_name,
                            model_id=m_name,
                            status="pending",
                            stage="pending",
                            progress=0.0,
                        ))
                db.commit()

            run_dir = RESULTS_DIR / experiment_id
            run_dir.mkdir(parents=True, exist_ok=True)

            relevance_mapper = RelevanceMapper()
            step_idx = 0

            summary_rows: list[dict[str, Any]] = []
            per_query_rows: list[dict[str, Any]] = []

            # Execute configurations
            for c_name in cfg_list:
                for m_name in model_list:
                    run_key = f"{c_name}__{m_name}"
                    step_idx += 1

                    if self.is_cancelled(experiment_id):
                        self.log(experiment_id, "Experiment cancelled during run loop.")
                        exp.status = "cancelled"
                        db.commit()
                        self.emit_event(experiment_id, {
                            "stage": "cancelled",
                            "current_step": step_idx,
                            "total_steps": total_steps,
                            "current_config": c_name,
                            "current_model": m_name,
                            "message": "Cancelled by user",
                            "elapsed_sec": time.time() - start_time,
                        })
                        return

                    if resume and run_key in run_keys_completed:
                        self.log(experiment_id, f"Skipping already completed run: {run_key}")
                        continue

                    self.emit_event(experiment_id, {
                        "stage": "evaluating",
                        "current_step": step_idx,
                        "total_steps": total_steps,
                        "current_config": c_name,
                        "current_model": m_name,
                        "message": f"Evaluating {c_name} with {m_name}",
                        "elapsed_sec": time.time() - start_time,
                    })

                    # Update run status in DB
                    run_rec = db.query(ExperimentRunModel).filter(
                        ExperimentRunModel.experiment_id == experiment_id,
                        ExperimentRunModel.chunk_config == c_name,
                        ExperimentRunModel.model_id == m_name,
                    ).first()
                    if run_rec:
                        run_rec.status = "running"
                        run_rec.stage = "evaluating"
                        db.commit()

                    pipeline = RetrievalPipeline(
                        chunk_config=c_name,
                        embedding_model=m_name,
                        clean_dir=CLEAN_DIR,
                    )
                    artifacts = pipeline.prepare()

                    query_texts = [q.question for q in questions]
                    t_eval_start = time.perf_counter()
                    batch_res = pipeline.retrieve_batch(query_texts, k=k_val)
                    t_eval_end = time.perf_counter()
                    mean_latency_ms = ((t_eval_end - t_eval_start) / max(len(questions), 1)) * 1000.0

                    q_results = []
                    for q, (chunks, scores) in zip(questions, batch_res):
                        eval_res = evaluate_query_retrieval(
                            question=q,
                            retrieved_chunks=chunks,
                            retrieved_scores=scores,
                            all_chunks_in_index=artifacts.chunks,
                            relevance_mapper=relevance_mapper,
                            k=k_val,
                            config_label=c_name,
                        )
                        eval_res.latency_ms = mean_latency_ms
                        q_results.append(eval_res)

                        pq_model = ResultPerQueryModel(
                            experiment_id=experiment_id,
                            run_key=run_key,
                            question_id=q.id,
                            doc_id=q.doc_id,
                            hit_at_k=eval_res.hit_at_k,
                            reciprocal_rank=eval_res.reciprocal_rank,
                            precision_at_k=eval_res.precision_at_k,
                            recall_at_k=eval_res.recall_at_k,
                            context_precision=eval_res.context_precision,
                            context_recall=eval_res.context_recall,
                            all_evidence_hit=eval_res.all_evidence_hit,
                            retrieved_chunk_ids=json.dumps([c.chunk_id for c in chunks]),
                            retrieved_scores=json.dumps(scores),
                            latency_ms=mean_latency_ms,
                        )
                        db.add(pq_model)

                        q_row = eval_res.to_dict()
                        q_row["config"] = c_name
                        q_row["model"] = m_name
                        q_row["run_id"] = experiment_id
                        q_row["unverified_question"] = not q.verified
                        per_query_rows.append(q_row)

                    hit_mean, hit_lo, hit_hi = compute_bootstrap_ci([r.hit_at_k for r in q_results])
                    mrr_mean, mrr_lo, mrr_hi = compute_bootstrap_ci([r.reciprocal_rank for r in q_results])
                    p_mean, p_lo, p_hi = compute_bootstrap_ci([r.precision_at_k for r in q_results])
                    r_mean, r_lo, r_hi = compute_bootstrap_ci([r.recall_at_k for r in q_results])
                    cp_mean, cp_lo, cp_hi = compute_bootstrap_ci([r.context_precision for r in q_results])
                    cr_mean, cr_lo, cr_hi = compute_bootstrap_ci([r.context_recall for r in q_results])

                    summary_rec = ResultSummaryModel(
                        experiment_id=experiment_id,
                        run_key=run_key,
                        config=c_name,
                        model=m_name,
                        hit_at_k=hit_mean,
                        hit_ci_lower=hit_lo,
                        hit_ci_upper=hit_hi,
                        mrr=mrr_mean,
                        mrr_ci_lower=mrr_lo,
                        mrr_ci_upper=mrr_hi,
                        precision_at_k=p_mean,
                        precision_ci_lower=p_lo,
                        precision_ci_upper=p_hi,
                        recall_at_k=r_mean,
                        recall_ci_lower=r_lo,
                        recall_ci_upper=r_hi,
                        context_precision=cp_mean,
                        context_precision_ci_lower=cp_lo,
                        context_precision_ci_upper=cp_hi,
                        context_recall=cr_mean,
                        context_recall_ci_lower=cr_lo,
                        context_recall_ci_upper=cr_hi,
                        truncation_rate=artifacts.truncation_rate,
                        mean_latency_ms=mean_latency_ms,
                        chunk_count=len(artifacts.chunks),
                        avg_tokens=artifacts.avg_tokens_per_chunk,
                        index_size_mb=artifacts.index_size_bytes / (1024 * 1024),
                    )
                    db.add(summary_rec)

                    if run_rec:
                        run_rec.status = "completed"
                        run_rec.stage = "done"
                        run_rec.progress = 1.0
                    db.commit()

                    summary_rows.append({
                        "config": c_name,
                        "model": m_name,
                        "hit_at_k": hit_mean,
                        "hit_ci_lower": hit_lo,
                        "hit_ci_upper": hit_hi,
                        "mrr": mrr_mean,
                        "mrr_ci_lower": mrr_lo,
                        "mrr_ci_upper": mrr_hi,
                        "precision_at_k": p_mean,
                        "precision_ci_lower": p_lo,
                        "precision_ci_upper": p_hi,
                        "recall_at_k": r_mean,
                        "recall_ci_lower": r_lo,
                        "recall_ci_upper": r_hi,
                        "context_precision": cp_mean,
                        "context_precision_ci_lower": cp_lo,
                        "context_precision_ci_upper": cp_hi,
                        "context_recall": cr_mean,
                        "context_recall_ci_lower": cr_lo,
                        "context_recall_ci_upper": cr_hi,
                        "truncation_rate": artifacts.truncation_rate,
                        "mean_latency_ms": mean_latency_ms,
                        "chunk_count": len(artifacts.chunks),
                        "avg_tokens": artifacts.avg_tokens_per_chunk,
                        "index_size_mb": artifacts.index_size_bytes / (1024 * 1024),
                    })

            # Random baseline
            rand_label = "random_baseline (mean of 100 draws)"
            step_idx += 1
            self.emit_event(experiment_id, {
                "stage": "evaluating",
                "current_step": step_idx,
                "total_steps": total_steps,
                "current_config": "random_baseline",
                "current_model": "none",
                "message": "Computing random retrieval baseline (100 draws)",
                "elapsed_sec": time.time() - start_time,
            })

            rand_pipeline = RetrievalPipeline(chunk_config="fixed_256_0", embedding_model="minilm", clean_dir=CLEAN_DIR)
            rand_artifacts = rand_pipeline.prepare()
            rand_results = evaluate_random_baseline(
                questions=questions,
                all_chunks=rand_artifacts.chunks,
                relevance_mapper=relevance_mapper,
                k=k_val,
                num_draws=100,
                config_label=rand_label,
            )

            for r in rand_results:
                q_row = r.to_dict()
                q_row["config"] = rand_label
                q_row["model"] = "none"
                q_row["run_id"] = experiment_id
                q_row["unverified_question"] = not questions[0].verified
                per_query_rows.append(q_row)

            r_hit_mean, r_hit_lo, r_hit_hi = compute_bootstrap_ci([r.hit_at_k for r in rand_results])
            r_mrr_mean, r_mrr_lo, r_mrr_hi = compute_bootstrap_ci([r.mrr for r in rand_results])
            r_p_mean, r_p_lo, r_p_hi = compute_bootstrap_ci([r.precision_at_k for r in rand_results])
            r_r_mean, r_r_lo, r_r_hi = compute_bootstrap_ci([r.recall_at_k for r in rand_results])
            r_cp_mean, r_cp_lo, r_cp_hi = compute_bootstrap_ci([r.context_precision for r in rand_results])
            r_cr_mean, r_cr_lo, r_cr_hi = compute_bootstrap_ci([r.context_recall for r in rand_results])

            db.add(ResultSummaryModel(
                experiment_id=experiment_id,
                run_key=f"{rand_label}__none",
                config=rand_label,
                model="none",
                hit_at_k=r_hit_mean,
                hit_ci_lower=r_hit_lo,
                hit_ci_upper=r_hit_hi,
                mrr=r_mrr_mean,
                mrr_ci_lower=r_mrr_lo,
                mrr_ci_upper=r_mrr_hi,
                precision_at_k=r_p_mean,
                precision_ci_lower=r_p_lo,
                precision_ci_upper=r_p_hi,
                recall_at_k=r_r_mean,
                recall_ci_lower=r_r_lo,
                recall_ci_upper=r_r_hi,
                context_precision=r_cp_mean,
                context_precision_ci_lower=r_cp_lo,
                context_precision_ci_upper=r_cp_hi,
                context_recall=r_cr_mean,
                context_recall_ci_lower=r_cr_lo,
                context_recall_ci_upper=r_cr_hi,
                truncation_rate=0.0,
                mean_latency_ms=0.1,
                chunk_count=len(rand_artifacts.chunks),
                avg_tokens=0.0,
                index_size_mb=0.0,
            ))

            summary_rows.append({
                "config": rand_label,
                "model": "none",
                "hit_at_k": r_hit_mean,
                "hit_ci_lower": r_hit_lo,
                "hit_ci_upper": r_hit_hi,
                "mrr": r_mrr_mean,
                "mrr_ci_lower": r_mrr_lo,
                "mrr_ci_upper": r_mrr_hi,
                "precision_at_k": r_p_mean,
                "precision_ci_lower": r_p_lo,
                "precision_ci_upper": r_p_hi,
                "recall_at_k": r_r_mean,
                "recall_ci_lower": r_r_lo,
                "recall_ci_upper": r_r_hi,
                "context_precision": r_cp_mean,
                "context_precision_ci_lower": r_cp_lo,
                "context_precision_ci_upper": r_cp_hi,
                "context_recall": r_cr_mean,
                "context_recall_ci_lower": r_cr_lo,
                "context_recall_ci_upper": r_cr_hi,
                "truncation_rate": 0.0,
                "mean_latency_ms": 0.1,
                "chunk_count": len(rand_artifacts.chunks),
                "avg_tokens": 0.0,
                "index_size_mb": 0.0,
            })

            # Save on disk
            if per_query_rows:
                with open(run_dir / "per_query.csv", "w", newline="", encoding="utf-8") as f:
                    if has_unverified:
                        f.write("# NOTICE: UNVERIFIED QUESTIONS INCLUDED IN THIS RUN\n")
                    writer = csv.DictWriter(f, fieldnames=list(per_query_rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(per_query_rows)

            if summary_rows:
                with open(run_dir / "summary.csv", "w", newline="", encoding="utf-8") as f:
                    if has_unverified:
                        f.write("# NOTICE: UNVERIFIED QUESTIONS INCLUDED IN THIS RUN\n")
                    writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(summary_rows)

            manifest = {
                "run_id": experiment_id,
                "preset": preset,
                "k": k_val,
                "unverified_questions_included": has_unverified,
                "verified_questions_count": len(questions) - unverified_count,
                "unverified_questions_count": unverified_count,
                "device": "cpu",
                "timestamp_utc": datetime.datetime.utcnow().isoformat(),
                "completed_runs": len(summary_rows),
            }
            with open(run_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            exp.status = "completed"
            exp.finished_at = datetime.datetime.utcnow()
            db.commit()

            self.emit_event(experiment_id, {
                "stage": "done",
                "current_step": total_steps,
                "total_steps": total_steps,
                "current_config": "done",
                "current_model": "done",
                "message": "Experiment completed successfully",
                "elapsed_sec": time.time() - start_time,
            })
            self.log(experiment_id, f"Experiment completed in {time.time() - start_time:.2f}s.")

        except Exception as e:
            logger.exception("Experiment error: %s", e)
            exp.status = "failed"
            exp.error = str(e)
            exp.finished_at = datetime.datetime.utcnow()
            db.commit()
            self.emit_event(experiment_id, {
                "stage": "failed",
                "current_step": 0,
                "total_steps": 0,
                "current_config": "error",
                "current_model": "error",
                "message": f"Error: {e}",
                "elapsed_sec": time.time() - start_time,
            })
            self.log(experiment_id, f"Experiment failed with error: {e}")
        finally:
            db.close()
            with self._lock:
                self._active_threads.pop(experiment_id, None)


# Global job runner instance
job_runner = ExperimentJobRunner()
