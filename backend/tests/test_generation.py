"""
backend/tests/test_generation.py — Tests for GroundednessEvaluator and MockLLMProvider.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from app.core.generation import (
    GroundednessJudge,
    LLMDiskCache,
    MockLLMProvider,
    get_llm_provider,
)


class TestGroundednessMock:
    def test_mock_provider_creation(self):
        provider = get_llm_provider("mock")
        assert isinstance(provider, MockLLMProvider)
        assert provider.name == "mock"

    def test_mock_groundedness_evaluation(self):
        judge = GroundednessJudge(provider=MockLLMProvider())
        context = ["TCP uses a 16-bit checksum to detect corrupted segments."]
        answer = "TCP includes a 16-bit checksum for error detection."

        res = judge.evaluate_groundedness(answer, context)
        assert res.total_count == 2
        assert res.supported_count == 2
        assert res.groundedness_score == 1.0
        assert len(res.claims) == 2
        assert res.claims[0].verdict == "supported"

    def test_llm_disk_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = LLMDiskCache(cache_dir=Path(tmpdir))
            prompt = "What is TCP?"
            assert cache.get(prompt, "mock", "test-model") is None

            cache.set(prompt, "mock", "test-model", "TCP is a transport protocol.")
            cached = cache.get(prompt, "mock", "test-model")
            assert cached == "TCP is a transport protocol."
