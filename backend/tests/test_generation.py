"""
backend/tests/test_generation.py — Tests for GroundednessEvaluator and MockLLMProvider.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
import pytest

from app.core.generation import (
    GroundednessClaim,
    GroundednessJudge,
    GroundednessResult,
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

    def test_mock_answer_generation(self):
        judge = GroundednessJudge(provider=MockLLMProvider())
        context = ["A TCP segment consists of a header and data."]
        question = "What does a TCP segment consist of?"
        ans = judge.generate_answer(question, context)
        assert isinstance(ans, str)
        assert len(ans) > 0

    def test_unsupported_claim_parsing(self):
        class MixedJudgeProvider(MockLLMProvider):
            def complete(self, prompt: str, temperature: float = 0.0) -> str:
                return json.dumps({
                    "claims": [
                        {"claim": "TCP is a transport protocol.", "verdict": "supported", "reason": "In context."},
                        {"claim": "TCP was invented in 2025.", "verdict": "unsupported", "reason": "Not in context."},
                    ]
                })

        judge = GroundednessJudge(provider=MixedJudgeProvider())
        res = judge.evaluate_groundedness("TCP statement", ["TCP context"])
        assert res.total_count == 2
        assert res.supported_count == 1
        assert res.groundedness_score == 0.5
        assert res.claims[1].verdict == "unsupported"

    def test_json_markdown_block_stripping(self):
        class MarkdownJudgeProvider(MockLLMProvider):
            def complete(self, prompt: str, temperature: float = 0.0) -> str:
                return "```json\n{\"claims\": [{\"claim\": \"c1\", \"verdict\": \"supported\"}]}\n```"

        judge = GroundednessJudge(provider=MarkdownJudgeProvider())
        res = judge.evaluate_groundedness("Answer", ["Context"])
        assert res.total_count == 1
        assert res.supported_count == 1
        assert res.groundedness_score == 1.0

    def test_malformed_json_fallback(self):
        class MalformedJudgeProvider(MockLLMProvider):
            def complete(self, prompt: str, temperature: float = 0.0) -> str:
                return "Not a valid JSON response from model"

        judge = GroundednessJudge(provider=MalformedJudgeProvider())
        res = judge.evaluate_groundedness("Answer text", ["Context text"])
        assert res.total_count == 1
        assert res.claims[0].claim == "Answer text"
        assert res.claims[0].verdict == "supported"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_provider("non_existent_provider")
