"""
backend/tests/test_cli.py — Tests for CLI operations: validate, export/import review, and error conditions.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from app.cli import (
    cmd_export_review,
    cmd_import_review,
    cmd_validate_questions,
)
from app.core.evaluation import Question, load_questions, save_questions


class TestCliReviewRoundTrip:
    def test_export_and_import_review_round_trip(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            test_questions_file = tmp_path / "questions.json"
            test_results_dir = tmp_path / "results"
            test_results_dir.mkdir(parents=True, exist_ok=True)

            # Create synthetic questions
            q1 = Question(
                id="syn-01",
                question="What is SYN?",
                doc_id="tcp",
                section="3.5",
                evidence=[],
                reference_answer="Synchronization segment.",
                type="definition",
                difficulty="easy",
                verified=False,
            )
            q2 = Question(
                id="syn-02",
                question="What is FIN?",
                doc_id="tcp",
                section="3.6",
                evidence=[],
                reference_answer="Finish segment.",
                type="definition",
                difficulty="easy",
                verified=False,
            )
            save_questions([q1, q2], test_questions_file)

            # Monkeypatch paths
            monkeypatch.setattr("app.cli.QUESTIONS_FILE", test_questions_file)
            monkeypatch.setattr("app.cli.RESULTS_DIR", test_results_dir)

            # 1. Export review
            cmd_export_review(argparse.Namespace())
            review_csv = test_results_dir / "review_sheet.csv"
            assert review_csv.exists()

            # Read exported review sheet and fill verdicts
            rows = []
            with open(review_csv, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if r["id"] == "syn-01":
                        r["verdict"] = "approve"
                        r["reviewer"] = "Alice"
                    elif r["id"] == "syn-02":
                        r["verdict"] = "reject"
                    rows.append(r)

            with open(review_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

            # 2. Import review
            cmd_import_review(argparse.Namespace(csv_file=str(review_csv)))

            # 3. Reload questions
            updated = load_questions(test_questions_file)
            assert len(updated) == 1
            assert updated[0].id == "syn-01"
            assert updated[0].verified is True
            assert updated[0].reviewer == "Alice"
            assert updated[0].reviewed_at is not None

    def test_validate_questions_cli(self, capsys):
        """CLI validate-questions executes cleanly across dataset."""
        cmd_validate_questions(argparse.Namespace())
        captured = capsys.readouterr()
        assert "[PASS]" in captured.out
        assert "VALIDATING EVALUATION QUESTIONS" in captured.out

    def test_verified_only_fails_when_zero_verified(self):
        """CLI run --verified-only must fail if 0 questions are verified."""
        import os
        repo_root = Path(__file__).resolve().parents[2]
        env = dict(os.environ)
        env["PYTHONPATH"] = f"{repo_root};{repo_root / 'backend'}"
        res = subprocess.run(
            [sys.executable, "-m", "app.cli", "run", "--preset", "quick", "--verified-only"],
            capture_output=True,
            text=True,
            cwd=str(repo_root / "backend"),
            env=env,
        )
        assert res.returncode != 0
        assert "0 questions are verified" in res.stdout or "0 questions are verified" in res.stderr
