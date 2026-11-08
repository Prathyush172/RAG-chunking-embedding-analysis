import torch  # Must be first on Windows to initialize OpenMP before faiss
import datetime
import io
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.db.models import (
    ExperimentModel,
    ResultSummaryModel,
    ResultPerQueryModel,
)

client = TestClient(app)


# =============================================================================
# 1. System Health
# =============================================================================
def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["device"] == "cpu"
    assert "corpus_hash" in data
    assert "questions_hash" in data
    assert len(data["corpus_hash"]) > 0


# =============================================================================
# 2. Corpus Endpoints (including line-index and start/end slicing)
# =============================================================================
def test_corpus_endpoints():
    res = client.get("/api/corpus/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 4
    doc_ids = {d["doc_id"] for d in docs}
    assert {"tcp", "dns", "dns_implementation", "http"}.issubset(doc_ids)

    # Full text
    res = client.get("/api/corpus/documents/tcp/text")
    assert res.status_code == 200
    assert "Transmission Control Protocol" in res.json()["text"]

    # Sliced text (?start=&end=)
    res_sliced = client.get("/api/corpus/documents/tcp/text?start=10&end=60")
    assert res_sliced.status_code == 200
    data_sliced = res_sliced.json()
    assert len(data_sliced["text"]) == 50
    assert data_sliced["start"] == 10
    assert data_sliced["end"] == 60

    # Line index for virtualized viewer
    res_line_idx = client.get("/api/corpus/documents/tcp/line-index")
    assert res_line_idx.status_code == 200
    line_data = res_line_idx.json()
    assert line_data["total_lines"] > 100
    assert line_data["line_offsets"][0] == 0
    assert len(line_data["line_offsets"]) == line_data["total_lines"]

    # 404 on missing doc
    res = client.get("/api/corpus/documents/nonexistent/text")
    assert res.status_code == 404
    err = res.json()
    assert "error" in err
    assert err["error"]["code"] == "HTTP_404"

    # Sections outline
    res = client.get("/api/corpus/documents/tcp/sections")
    assert res.status_code == 200
    secs = res.json()
    assert len(secs) > 0
    assert "title" in secs[0]

    # Search
    res = client.get("/api/corpus/search?q=sequence+number&doc_id=tcp&limit=5")
    assert res.status_code == 200
    matches = res.json()
    assert len(matches) > 0
    assert matches[0]["doc_id"] == "tcp"


# =============================================================================
# 3. Questions CRUD, Derived Section, Validation Errors & Review Flow
# =============================================================================
def test_questions_crud_and_validation():
    # 1. Validation error (422) on missing required fields
    bad_res = client.post("/api/questions", json={"question": "Incomplete?"})
    assert bad_res.status_code == 422
    err_envelope = bad_res.json()
    assert "error" in err_envelope
    assert err_envelope["error"]["code"] == "VALIDATION_ERROR"

    # 2. Create question with valid evidence quote from TCP RFC
    create_payload = {
        "id": "test-crud-tcp-01",
        "doc_id": "tcp",
        "question": "What is the role of the initial sequence number?",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "A connection is defined by a pair of sockets.  Connections can be\n   reused.",
            }
        ],
        "reference_answer": "TCP sockets identify connections and allow reuse across incarnations.",
        "type": "factual",
        "difficulty": "medium",
        "notes": "Test creation",
    }
    create_res = client.post("/api/questions", json=create_payload)
    assert create_res.status_code == 200
    created = create_res.json()
    assert created["id"] == "test-crud-tcp-01"
    # Derived section must be non-empty and reflect RFC structure
    assert "Initial Sequence Number" in created["section"] or "3.4.1" in created["section"]
    assert created["lexical_overlap_run"] >= 0
    assert created["verified"] is False

    # 3. Read single question
    get_res = client.get("/api/questions/test-crud-tcp-01")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == "test-crud-tcp-01"

    # 4. Update question
    put_res = client.put(
        "/api/questions/test-crud-tcp-01",
        json={"notes": "Updated note during test"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["notes"] == "Updated note during test"

    # 5. Delete question
    del_res = client.delete("/api/questions/test-crud-tcp-01")
    assert del_res.status_code == 200

    # Confirm 404 after deletion
    assert client.get("/api/questions/test-crud-tcp-01").status_code == 404


def test_questions_review_flow():
    # Create a temporary question for review test
    create_payload = {
        "id": "review-flow-test-01",
        "doc_id": "tcp",
        "question": "How are TCP connection socket pairs managed?",
        "evidence": [
            {
                "doc_id": "tcp",
                "quote": "A connection is defined by a pair of sockets.  Connections can be\n   reused.",
            }
        ],
        "reference_answer": "Sockets define connections and can be reused.",
        "type": "factual",
        "difficulty": "medium",
    }
    client.post("/api/questions", json=create_payload)

    # 1. Edit via review endpoint
    edit_res = client.post(
        "/api/questions/review-flow-test-01/review",
        json={
            "verdict": "edit",
            "notes": "Needs more technical depth",
            "reviewer": "Reviewer Alice",
        },
    )
    assert edit_res.status_code == 200
    edit_data = edit_res.json()
    assert edit_data["status"] == "edited"
    assert edit_data["question"]["verified"] is False
    assert edit_data["question"]["notes"] == "Needs more technical depth"

    # 2. Approve via review endpoint
    appr_res = client.post(
        "/api/questions/review-flow-test-01/review",
        json={
            "verdict": "approve",
            "reviewer": "Reviewer Alice",
            "notes": "Verified against RFC 9293 Section 3.4",
        },
    )
    assert appr_res.status_code == 200
    appr_data = appr_res.json()
    assert appr_data["status"] == "approved"
    assert appr_data["question"]["verified"] is True
    assert appr_data["question"]["reviewer"] == "Reviewer Alice"
    assert appr_data["question"]["verified_at"] is not None

    # Check review progress reflects 1 verified
    prog_res = client.get("/api/questions/review/progress")
    assert prog_res.status_code == 200
    assert prog_res.json()["verified"] >= 1

    # 3. Reject via review endpoint (moves question to rejected.json)
    rej_res = client.post(
        "/api/questions/review-flow-test-01/review",
        json={
            "verdict": "reject",
            "reviewer": "Reviewer Bob",
            "notes": "Redundant question",
        },
    )
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"

    # Confirm question is removed from main questions list
    assert client.get("/api/questions/review-flow-test-01").status_code == 404


# =============================================================================
# 4. Configs & Estimation
# =============================================================================
def test_configs_endpoints():
    res = client.get("/api/configs/presets")
    assert res.status_code == 200
    presets = res.json()
    preset_ids = [p["id"] for p in presets]
    assert "quick" in preset_ids
    assert "full" in preset_ids

    res = client.get("/api/configs/models")
    assert res.status_code == 200
    models = res.json()
    model_ids = [m["id"] for m in models]
    assert {"minilm", "bge_small", "e5_small"}.issubset(set(model_ids))

    res = client.get("/api/configs/chunkers")
    assert res.status_code == 200
    chunkers = res.json()
    c_ids = [c["id"] for c in chunkers]
    assert {"fixed", "sentence", "semantic"}.issubset(set(c_ids))

    est_req = {
        "chunk_configs": ["fixed_256_0", "sent_256_0"],
        "models": ["minilm", "bge_small"],
        "questions_count": 56,
        "k": 5,
    }
    res = client.post("/api/configs/estimate", json=est_req)
    assert res.status_code == 200
    data = res.json()
    assert data["total_combinations"] == 4
    assert data["total_estimated_sec"] > 0


# =============================================================================
# 5. Experiments Lifecycle & Error Handling
# =============================================================================
def test_experiment_lifecycle_and_cancellation():
    from unittest.mock import patch

    # 1. verified_only with 0 verified questions returns 409 Conflict
    q_stats = client.get("/api/questions/stats").json()
    if q_stats["verified"] == 0:
        res_conflict = client.post(
            "/api/experiments",
            json={"preset": "quick", "verified_only": True},
        )
        assert res_conflict.status_code == 409
        assert "Conflict" in res_conflict.json()["error"]["message"]

    with patch("app.api.experiments.job_runner.start_experiment") as mock_start, \
         patch("app.api.experiments.job_runner.cancel") as mock_cancel:

        # 2. Create custom experiment
        res = client.post(
            "/api/experiments",
            json={
                "name": "Synthetic Lifecycle Test",
                "configs": ["fixed_256_0"],
                "models": ["minilm"],
                "k": 3,
            },
        )
        assert res.status_code == 201
        exp_data = res.json()
        exp_id = exp_data["id"]
        assert exp_data["status"] in ("queued", "running")
        mock_start.assert_called_once()

        # 3. Cancel experiment
        cancel_res = client.post(f"/api/experiments/{exp_id}/cancel")
        assert cancel_res.status_code == 200
        assert "Cancellation requested" in cancel_res.json()["message"]
        mock_cancel.assert_called_once_with(exp_id)

        # Verify status persisted
        get_exp = client.get(f"/api/experiments/{exp_id}").json()
        assert get_exp["status"] == "cancelled"

        # 4. Resume experiment
        resume_res = client.post(f"/api/experiments/{exp_id}/resume")
        assert resume_res.status_code == 200
        assert resume_res.json()["status"] == "running"

        # 5. Clean up
        del_res = client.delete(f"/api/experiments/{exp_id}")
        assert del_res.status_code == 200


# =============================================================================
# 6. Seeded Results: Hand-Computed Pareto Frontier, Heatmap & Decision Matrix
# =============================================================================
@pytest.fixture(scope="module")
def seeded_experiment():
    """
    Seed a synthetic experiment with exactly known hand-computed numbers:
    - fixed_256_0__minilm:
        Hit@5 = 0.700, MRR = 0.500, Latency = 5.0ms, IndexSize = 10.0MB, CtxPrec = 0.400, CtxRec = 0.600
    - fixed_256_0__e5_small:
        Hit@5 = 0.800, MRR = 0.600, Latency = 10.0ms, IndexSize = 15.0MB, CtxPrec = 0.500, CtxRec = 0.700
    - sent_256_0__minilm:
        Hit@5 = 0.600, MRR = 0.400, Latency = 2.0ms, IndexSize = 8.0MB, CtxPrec = 0.350, CtxRec = 0.500
    """
    exp_id = "test_hand_seeded_exp_01"
    db = SessionLocal()
    try:
        # Clear existing seeded if any
        db.query(ResultPerQueryModel).filter(ResultPerQueryModel.experiment_id == exp_id).delete()
        db.query(ResultSummaryModel).filter(ResultSummaryModel.experiment_id == exp_id).delete()
        db.query(ExperimentModel).filter(ExperimentModel.id == exp_id).delete()
        db.commit()

        exp = ExperimentModel(
            id=exp_id,
            name="Hand Seeded Test Run",
            preset="custom",
            config_json=json.dumps({"preset": "custom", "configs": ["fixed_256_0", "sent_256_0"], "models": ["minilm", "e5_small"]}),
            status="completed",
            verified_only=False,
            verified_questions_count=5,
            unverified_questions_count=51,
            has_unverified=True,
        )
        db.add(exp)
        db.commit()

        summaries = [
            ResultSummaryModel(
                experiment_id=exp_id,
                run_key="fixed_256_0__minilm",
                config="fixed_256_0",
                model="minilm",
                hit_at_k=0.700, hit_ci_lower=0.65, hit_ci_upper=0.75,
                mrr=0.500, mrr_ci_lower=0.45, mrr_ci_upper=0.55,
                precision_at_k=0.15, precision_ci_lower=0.12, precision_ci_upper=0.18,
                recall_at_k=0.60, recall_ci_lower=0.55, recall_ci_upper=0.65,
                context_precision=0.400, context_precision_ci_lower=0.35, context_precision_ci_upper=0.45,
                context_recall=0.600, context_recall_ci_lower=0.55, context_recall_ci_upper=0.65,
                truncation_rate=0.05, mean_latency_ms=5.0, chunk_count=200, avg_tokens=220.0, index_size_mb=10.0,
            ),
            ResultSummaryModel(
                experiment_id=exp_id,
                run_key="fixed_256_0__e5_small",
                config="fixed_256_0",
                model="e5_small",
                hit_at_k=0.800, hit_ci_lower=0.75, hit_ci_upper=0.85,
                mrr=0.600, mrr_ci_lower=0.55, mrr_ci_upper=0.65,
                precision_at_k=0.18, precision_ci_lower=0.15, precision_ci_upper=0.21,
                recall_at_k=0.70, recall_ci_lower=0.65, recall_ci_upper=0.75,
                context_precision=0.500, context_precision_ci_lower=0.45, context_precision_ci_upper=0.55,
                context_recall=0.700, context_recall_ci_lower=0.65, context_recall_ci_upper=0.75,
                truncation_rate=0.01, mean_latency_ms=10.0, chunk_count=200, avg_tokens=220.0, index_size_mb=15.0,
            ),
            ResultSummaryModel(
                experiment_id=exp_id,
                run_key="sent_256_0__minilm",
                config="sent_256_0",
                model="minilm",
                hit_at_k=0.600, hit_ci_lower=0.55, hit_ci_upper=0.65,
                mrr=0.400, mrr_ci_lower=0.35, mrr_ci_upper=0.45,
                precision_at_k=0.12, precision_ci_lower=0.10, precision_ci_upper=0.14,
                recall_at_k=0.50, recall_ci_lower=0.45, recall_ci_upper=0.55,
                context_precision=0.350, context_precision_ci_lower=0.30, context_precision_ci_upper=0.40,
                context_recall=0.500, context_recall_ci_lower=0.45, context_recall_ci_upper=0.55,
                truncation_rate=0.02, mean_latency_ms=2.0, chunk_count=180, avg_tokens=210.0, index_size_mb=8.0,
            ),
        ]
        for s in summaries:
            db.add(s)

        # Seed 3 aligned queries for comparison
        for q_num in range(1, 4):
            qid = f"tcp-{q_num:02d}"
            # Run 1: fixed_256_0__minilm
            db.add(ResultPerQueryModel(
                experiment_id=exp_id,
                run_key="fixed_256_0__minilm",
                question_id=qid,
                doc_id="tcp",
                hit_at_k=1.0 if q_num <= 2 else 0.0,
                reciprocal_rank=1.0 / q_num,
                precision_at_k=0.2, recall_at_k=0.5,
                context_precision=0.5, context_recall=0.5,
                all_evidence_hit=True,
            ))
            # Run 2: fixed_256_0__e5_small
            db.add(ResultPerQueryModel(
                experiment_id=exp_id,
                run_key="fixed_256_0__e5_small",
                question_id=qid,
                doc_id="tcp",
                hit_at_k=1.0,
                reciprocal_rank=1.0,
                precision_at_k=0.2, recall_at_k=1.0,
                context_precision=1.0, context_recall=1.0,
                all_evidence_hit=True,
            ))
        db.commit()
    finally:
        db.close()
    return exp_id


def test_hand_computed_pareto_and_heatmap(seeded_experiment):
    exp_id = seeded_experiment

    # 1. Pareto Points Verification
    # Expected: 3 points with exact hand-computed values:
    # fixed_256_0__minilm: hit=0.7, lat=5.0
    # fixed_256_0__e5_small: hit=0.8, lat=10.0 (highest accuracy)
    # sent_256_0__minilm: hit=0.6, lat=2.0 (lowest latency)
    pareto_res = client.get(f"/api/results/{exp_id}/pareto")
    assert pareto_res.status_code == 200
    points = {f"{p['config']}__{p['model']}": p for p in pareto_res.json()}
    assert len(points) == 3
    assert points["fixed_256_0__minilm"]["hit_at_k"] == 0.700
    assert points["fixed_256_0__minilm"]["mean_latency_ms"] == 5.0
    assert points["fixed_256_0__e5_small"]["hit_at_k"] == 0.800
    assert points["sent_256_0__minilm"]["mean_latency_ms"] == 2.0

    # 2. Heatmap Values Verification
    # Expected:
    # matrix["fixed_256_0"]["minilm"] == 0.700
    # matrix["fixed_256_0"]["e5_small"] == 0.800
    # matrix["sent_256_0"]["minilm"] == 0.600
    hm_res = client.get(f"/api/results/{exp_id}/heatmap?metric=hit_at_k")
    assert hm_res.status_code == 200
    hm_data = hm_res.json()
    assert hm_data["matrix"]["fixed_256_0"]["minilm"] == 0.700
    assert hm_data["matrix"]["fixed_256_0"]["e5_small"] == 0.800
    assert hm_data["matrix"]["sent_256_0"]["minilm"] == 0.600


def test_compare_all_zero_differences(seeded_experiment):
    exp_id = seeded_experiment

    # Compare identical run against itself
    cmp_req = {
        "experiment_id": exp_id,
        "base_config": "fixed_256_0",
        "base_model": "minilm",
        "target_config": "fixed_256_0",
        "target_model": "minilm",
    }
    res = client.post("/api/compare", json=cmp_req)
    assert res.status_code == 200
    cmp_data = res.json()

    # Invariants for identical runs:
    # All metric deltas == 0.0, p_value == 1.0, statistically_significant == False
    for m in cmp_data["metrics"]:
        assert m["delta"] == 0.0
        assert m["p_value"] == 1.0
        assert m["statistically_significant"] is False

    # Note must explain the all-zero difference
    assert cmp_data["note"] is not None
    assert "p = 1.0" in cmp_data["note"]

    # unverified counts must be included
    assert cmp_data["unverified_included"] is True
    assert cmp_data["verified_questions_count"] == 5
    assert cmp_data["unverified_questions_count"] == 51


def test_decision_matrix_hand_computed_and_renormalization(seeded_experiment):
    exp_id = seeded_experiment

    # Test Presets
    presets_res = client.get("/api/decision-matrix/presets")
    assert presets_res.status_code == 200
    preset_names = [p["name"] for p in presets_res.json()]
    assert "Accuracy first" in preset_names
    assert "Low latency" in preset_names
    assert "Constrained hardware" in preset_names
    assert "Balanced" in preset_names

    # Hand-computed utility test:
    # Criteria: hit_at_k (50%), latency (50%). Groundedness set to 50% but missing in data.
    # Hand-computed normalization:
    # Min hit = 0.600, Max hit = 0.800
    # Min lat = 2.0ms, Max lat = 10.0ms
    #
    # 1. fixed_256_0__minilm:
    #    hit norm = (0.7 - 0.6) / (0.8 - 0.6) = 0.5000
    #    lat norm (inverted) = (10.0 - 5.0) / (10.0 - 2.0) = 5.0 / 8.0 = 0.6250
    #    Utility = 0.5 * 0.5000 + 0.5 * 0.6250 = 0.2500 + 0.3125 = 0.5625
    #
    # 2. fixed_256_0__e5_small:
    #    hit norm = (0.8 - 0.6) / (0.8 - 0.6) = 1.0000
    #    lat norm (inverted) = (10.0 - 10.0) / 8.0 = 0.0000
    #    Utility = 0.5 * 1.0 + 0.5 * 0.0 = 0.5000
    #
    # 3. sent_256_0__minilm:
    #    hit norm = 0.0000
    #    lat norm (inverted) = (10.0 - 2.0) / 8.0 = 1.0000
    #    Utility = 0.5 * 0.0 + 0.5 * 1.0 = 0.5000
    #
    # Hand-computed Winner: fixed_256_0__minilm (Utility = 0.5625)
    dm_req = {
        "experiment_id": exp_id,
        "weights": {
            "hit_at_k": 0.5,
            "mrr": 0.0,
            "context_precision": 0.0,
            "context_recall": 0.0,
            "latency": 0.5,
            "index_size": 0.0,
            "cost": 0.0,
            "groundedness": 0.5,  # Missing in data -> must be renormalised to 0
        },
    }
    dm_res = client.post("/api/decision-matrix", json=dm_req)
    assert dm_res.status_code == 200
    rankings = dm_res.json()
    assert len(rankings) == 3

    # Rank 1 must be fixed_256_0__minilm with score 0.5625
    assert rankings[0]["config"] == "fixed_256_0"
    assert rankings[0]["model"] == "minilm"
    assert rankings[0]["rank"] == 1
    assert abs(rankings[0]["total_utility_score"] - 0.5625) < 1e-3


def test_exports_latex_escaping_and_manifest(seeded_experiment):
    exp_id = seeded_experiment

    # LaTeX export: verify escaping of LaTeX reserved characters
    latex_res = client.get(f"/api/export/{exp_id}/summary?format=latex")
    assert latex_res.status_code == 200
    tex = latex_res.text
    assert r"\begin{table}" in tex
    # Underline in run_key/config must be escaped
    assert r"fixed\_256\_0" in tex
    assert r"minilm" in tex
    assert r"\%" in tex  # Truncation percent escaped

    # Methodology text must contain manifest values
    method_res = client.get(f"/api/export/{exp_id}/methodology")
    assert method_res.status_code == 200
    m_data = method_res.json()
    assert m_data["unverified_included"] is True
    assert m_data["verified_questions_count"] == 5
    assert m_data["unverified_questions_count"] == 51
    assert "5 human-verified, 51 unverified" in m_data["markdown"]


def test_settings_security():
    # Update settings with secret key
    put_res = client.put(
        "/api/settings",
        json={"openai_api_key": "sk-proj-super-secret-key-1234567890"},
    )
    assert put_res.status_code == 200

    # Get settings must NEVER expose the plaintext key
    get_res = client.get("/api/settings")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["openai_api_key_masked"] == "********"
    assert "sk-proj" not in json.dumps(data)


def test_playground_multi_config_query():
    # Test multi-config query format (up to 3 configs)
    req = {
        "query": "What is the socket pair connection rule in TCP?",
        "configs": [
            {"chunk_config": "fixed_256_0", "model_id": "minilm"},
        ],
        "k": 3,
    }
    res = client.post("/api/playground/query", json=req)
    assert res.status_code == 200
    data = res.json()
    assert len(data["configs"]) == 1
    assert data["configs"][0]["chunk_config"] == "fixed_256_0"
    assert data["configs"][0]["model_id"] == "minilm"
    assert data["configs"][0]["status"] in ("ready", "building")
    if data["configs"][0]["status"] == "ready":
        assert len(data["configs"][0]["retrieved_chunks"]) == 3
        assert "score" in data["configs"][0]["retrieved_chunks"][0]
        assert "truncated" in data["configs"][0]["retrieved_chunks"][0]
