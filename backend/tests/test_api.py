import torch  # Must be first on Windows to initialize OpenMP before faiss
import io
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["device"] == "cpu"
    assert "corpus_hash" in data
    assert "questions_hash" in data
    assert len(data["corpus_hash"]) > 0


def test_corpus_endpoints():
    # Documents list
    res = client.get("/api/corpus/documents")
    assert res.status_code == 200
    docs = res.json()
    assert len(docs) == 4
    doc_ids = {d["doc_id"] for d in docs}
    assert {"tcp", "dns", "dns_implementation", "http"}.issubset(doc_ids)

    # Specific doc text
    res = client.get("/api/corpus/documents/tcp/text")
    assert res.status_code == 200
    assert "Transmission Control Protocol" in res.json()["text"]

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


def test_questions_endpoints():
    # List questions
    res = client.get("/api/questions")
    assert res.status_code == 200
    qs = res.json()
    assert len(qs) == 56

    # Stats
    res = client.get("/api/questions/stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["total"] == 56
    assert stats["verified"] == 0
    assert stats["unverified"] == 56
    assert stats["by_doc"]["tcp"] == 14

    # Review progress
    res = client.get("/api/questions/review/progress")
    assert res.status_code == 200
    prog = res.json()
    assert prog["total"] == 56
    assert prog["verified"] == 0

    # Next unverified
    res = client.get("/api/questions/review/next")
    assert res.status_code == 200
    assert res.json() is not None

    # Validate questions
    res = client.post("/api/questions/validate")
    assert res.status_code == 200
    val = res.json()
    assert val["valid"] is True
    assert val["issue_count"] == 0

    # Export review sheet CSV
    res = client.get("/api/questions/export")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "lexical_overlap_run" in res.text


def test_configs_endpoints():
    # Presets
    res = client.get("/api/configs/presets")
    assert res.status_code == 200
    presets = res.json()
    preset_ids = [p["id"] for p in presets]
    assert "quick" in preset_ids
    assert "standard" in preset_ids
    assert "comprehensive" in preset_ids

    # Models
    res = client.get("/api/configs/models")
    assert res.status_code == 200
    models = res.json()
    model_ids = [m["id"] for m in models]
    assert {"minilm", "bge_small", "e5_small"}.issubset(set(model_ids))

    # Chunkers
    res = client.get("/api/configs/chunkers")
    assert res.status_code == 200
    chunkers = res.json()
    c_ids = [c["id"] for c in chunkers]
    assert {"fixed", "sentence", "semantic"}.issubset(set(c_ids))

    # Estimation
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


def test_experiments_and_verified_conflict():
    # verified_only=True should fail with 409 because 0 questions are verified
    res = client.post(
        "/api/experiments",
        json={"preset": "quick", "verified_only": True},
    )
    assert res.status_code == 409
    err = res.json()
    assert "error" in err
    assert "Conflict" in err["error"]["message"]

    # List experiments (should contain synced historical run from disk)
    res = client.get("/api/experiments")
    assert res.status_code == 200
    exps = res.json()
    assert len(exps) > 0
    exp_id = exps[0]["id"]

    # Get specific experiment
    res = client.get(f"/api/experiments/{exp_id}")
    assert res.status_code == 200
    assert res.json()["id"] == exp_id


def test_results_and_analytics():
    # List experiments to find completed one
    res = client.get("/api/experiments")
    assert res.status_code == 200
    exps = res.json()
    completed_exps = [e for e in exps if e["status"] == "completed"]
    assert len(completed_exps) > 0
    exp_id = completed_exps[0]["id"]

    # Summary
    res = client.get(f"/api/results/{exp_id}/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["experiment_id"] == exp_id
    assert len(summary["rows"]) > 0
    if summary["has_unverified"]:
        assert summary["notice"] is not None

    # Per Query
    res = client.get(f"/api/results/{exp_id}/per-query")
    assert res.status_code == 200
    pqs = res.json()
    assert len(pqs) > 0

    # Per Doc
    res = client.get(f"/api/results/{exp_id}/per-doc")
    assert res.status_code == 200
    per_doc = res.json()
    assert "tcp" in per_doc

    # Question Across Runs
    qid = pqs[0]["question_id"]
    res = client.get(f"/api/results/{exp_id}/questions/{qid}")
    assert res.status_code == 200
    q_inspect = res.json()
    assert q_inspect["question_id"] == qid
    assert len(q_inspect["runs"]) > 0

    # Pareto Points
    res = client.get(f"/api/results/{exp_id}/pareto")
    assert res.status_code == 200
    pareto = res.json()
    assert len(pareto) > 0
    assert "hit_at_k" in pareto[0]
    assert "mean_latency_ms" in pareto[0]

    # Heatmap
    res = client.get(f"/api/results/{exp_id}/heatmap?metric=hit_at_k")
    assert res.status_code == 200
    hm = res.json()
    assert hm["metric"] == "hit_at_k"
    assert len(hm["strategies"]) > 0
    assert len(hm["models"]) > 0


def test_compare_and_decision_matrix():
    res = client.get("/api/experiments")
    exps = res.json()
    completed_exps = [e for e in exps if e["status"] == "completed"]
    exp_id = completed_exps[0]["id"]

    # Compare two configs
    compare_req = {
        "experiment_id": exp_id,
        "base_config": "fixed_256_0",
        "base_model": "minilm",
        "target_config": "fixed_256_0",
        "target_model": "e5_small",
    }
    res = client.post("/api/compare", json=compare_req)
    assert res.status_code == 200
    cmp_data = res.json()
    assert cmp_data["base_label"] == "fixed_256_0__minilm"
    assert cmp_data["target_label"] == "fixed_256_0__e5_small"
    assert len(cmp_data["metrics"]) > 0
    assert "win_loss_tie" in cmp_data

    # Decision Matrix Presets
    res = client.get("/api/decision-matrix/presets")
    assert res.status_code == 200
    presets = res.json()
    assert len(presets) >= 4

    # Decision Matrix Computation
    dm_req = {
        "experiment_id": exp_id,
        "weights": {
            "hit_at_k": 0.3,
            "mrr": 0.2,
            "context_precision": 0.15,
            "context_recall": 0.15,
            "latency": 0.1,
            "index_size": 0.1,
            "cost": 0.0,
        },
    }
    res = client.post("/api/decision-matrix", json=dm_req)
    assert res.status_code == 200
    rankings = res.json()
    assert len(rankings) > 0
    assert rankings[0]["rank"] == 1
    assert "total_utility_score" in rankings[0]


def test_exports():
    res = client.get("/api/experiments")
    exps = res.json()
    completed_exps = [e for e in exps if e["status"] == "completed"]
    exp_id = completed_exps[0]["id"]

    # Markdown export
    res = client.get(f"/api/export/{exp_id}/summary?format=markdown")
    assert res.status_code == 200
    assert "text/markdown" in res.headers["content-type"]
    assert "| Config | Model |" in res.text

    # LaTeX export
    res = client.get(f"/api/export/{exp_id}/summary?format=latex")
    assert res.status_code == 200
    assert r"\begin{table}" in res.text

    # Manifest
    res = client.get(f"/api/export/{exp_id}/manifest")
    assert res.status_code == 200
    assert res.json()["run_id"] == exp_id

    # Methodology
    res = client.get(f"/api/export/{exp_id}/methodology")
    assert res.status_code == 200
    assert "Research Question" in res.json()["markdown"]


def test_settings_and_playground():
    # Get settings
    res = client.get("/api/settings")
    assert res.status_code == 200
    assert "llm_judge_provider" in res.json()

    # Update settings
    res = client.put("/api/settings", json={"llm_judge_provider": "gemini", "gemini_api_key": "ai-secret-key-12345"})
    assert res.status_code == 200
    data = res.json()
    assert data["llm_judge_provider"] == "gemini"
    assert data["gemini_api_key_masked"] == "ai-...2345"

    # Reset setting
    client.put("/api/settings", json={"llm_judge_provider": "mock"})

    # Playground query
    play_req = {
        "query": "How does TCP handle socket pair reuse?",
        "chunk_config": "fixed_256_0",
        "model_id": "minilm",
        "k": 3,
    }
    res = client.post("/api/playground/query", json=play_req)
    assert res.status_code == 200
    play_res = res.json()
    assert play_res["query"] == play_req["query"]
    assert len(play_res["retrieved_chunks"]) == 3
    assert play_res["latency_ms"] > 0
