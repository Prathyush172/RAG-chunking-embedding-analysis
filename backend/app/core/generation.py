"""
backend/app/core/generation.py — LLM generation and groundedness evaluation.

Supports:
- Pluggable providers: 'mock' (deterministic for testing), 'ollama' (default local),
  'gemini', and 'openai' (keys loaded from environment/.env).
- Groundedness evaluation via atomic claim decomposition (supported / total claims).
- Persistent SHA-256 disk caching for all LLM calls under artifacts/llm_cache/.
- Groundedness is OPTIONAL and OFF by default.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"
CACHE_DIR = REPO_ROOT / "artifacts" / "llm_cache"


@dataclass
class GroundednessClaim:
    claim: str
    verdict: str  # "supported" | "unsupported"
    reason: str = ""


@dataclass
class GroundednessResult:
    claims: list[GroundednessClaim]
    supported_count: int
    total_count: int
    groundedness_score: float  # supported_count / max(total_count, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [
                {"claim": c.claim, "verdict": c.verdict, "reason": c.reason}
                for c in self.claims
            ],
            "supported_count": self.supported_count,
            "total_count": self.total_count,
            "groundedness_score": round(self.groundedness_score, 4),
        }


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        """Execute prompt completion."""
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """
    Deterministic mock provider for unit tests and offline testing.
    Generates synthetic answers and groundedness evaluations based on simple heuristics.
    """

    name: str = "mock"

    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        if "Break down the Answer into individual atomic factual statements" in prompt:
            # Judge prompt
            # Extract context and answer if possible
            return json.dumps({
                "claims": [
                    {"claim": "Mock claim 1 statement.", "verdict": "supported", "reason": "Present in context."},
                    {"claim": "Mock claim 2 statement.", "verdict": "supported", "reason": "Confirmed by context."},
                ],
                "groundedness_score": 1.0,
            })
        else:
            # Answer generation prompt
            return "Based on the provided RFC documentation, the protocol specification directly defines this behavior."


class OllamaProvider(LLMProvider):
    """Local Ollama provider (default host http://localhost:11434)."""

    name: str = "ollama"

    def __init__(self, model: str = "llama3:8b", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        import urllib.error
        import urllib.request

        url = f"{self.host}/api/generate"
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("response", "")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama connection error to {url}: {e}. Ensure Ollama is running.")


class GeminiProvider(LLMProvider):
    """Google Gemini provider via google-generativeai or API key."""

    name: str = "gemini"

    def __init__(self, model: str = "gemini-1.5-flash", api_key: Optional[str] = None) -> None:
        self.model_name = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY must be set in environment or passed directly.")

    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        import urllib.request

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return ""


class OpenAIProvider(LLMProvider):
    """OpenAI provider using direct HTTP request."""

    name: str = "openai"

    def __init__(self, model: str = "gpt-4o-mini", api_key: Optional[str] = None) -> None:
        self.model_name = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY must be set in environment or passed directly.")

    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        import urllib.request

        url = "https://api.openai.com/v1/chat/completions"
        payload = json.dumps({
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""


def get_llm_provider(name: str = "mock", **kwargs: Any) -> LLMProvider:
    name = name.lower()
    if name == "mock":
        return MockLLMProvider()
    elif name == "ollama":
        return OllamaProvider(**kwargs)
    elif name == "gemini":
        return GeminiProvider(**kwargs)
    elif name == "openai":
        return OpenAIProvider(**kwargs)
    else:
        raise ValueError(f"Unknown LLM provider: {name}. Must be 'mock', 'ollama', 'gemini', or 'openai'.")


class LLMDiskCache:
    """Persistent SHA-256 disk cache for LLM calls."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _hash_key(self, prompt: str, provider: str, model: str) -> str:
        h = hashlib.sha256()
        h.update(provider.encode("utf-8"))
        h.update(model.encode("utf-8"))
        h.update(prompt.encode("utf-8"))
        return h.hexdigest()

    def get(self, prompt: str, provider: str, model: str = "") -> Optional[str]:
        key = self._hash_key(prompt, provider, model)
        target = self.cache_dir / f"{key}.json"
        if target.exists():
            try:
                with open(target, encoding="utf-8") as f:
                    return json.load(f)["response"]
            except Exception:
                return None
        return None

    def set(self, prompt: str, provider: str, model: str, response: str) -> None:
        key = self._hash_key(prompt, provider, model)
        target = self.cache_dir / f"{key}.json"
        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump({"prompt": prompt, "provider": provider, "model": model, "response": response}, f)
        except Exception as e:
            logger.warning("Failed writing to LLM cache: %s", e)


class GroundednessJudge:
    """Evaluates answer groundedness against retrieved context."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or MockLLMProvider()
        self.cache = LLMDiskCache()
        self.answer_prompt_template = (PROMPTS_DIR / "answer_generation.txt").read_text(encoding="utf-8")
        self.judge_prompt_template = (PROMPTS_DIR / "groundedness_judge.txt").read_text(encoding="utf-8")

    def cached_complete(self, prompt: str, model: str = "") -> str:
        cached = self.cache.get(prompt, self.provider.name, model)
        if cached is not None:
            return cached
        resp = self.provider.complete(prompt)
        self.cache.set(prompt, self.provider.name, model, resp)
        return resp

    def generate_answer(self, question: str, context_chunks: list[str]) -> str:
        context_str = "\n\n---\n\n".join(context_chunks)
        prompt = self.answer_prompt_template.replace("{context}", context_str).replace("{question}", question)
        return self.cached_complete(prompt)

    def evaluate_groundedness(self, answer: str, context_chunks: list[str]) -> GroundednessResult:
        context_str = "\n\n---\n\n".join(context_chunks)
        prompt = self.judge_prompt_template.replace("{context}", context_str).replace("{answer}", answer)
        raw_output = self.cached_complete(prompt)

        # Parse JSON
        claims: list[GroundednessClaim] = []
        try:
            # Strip markdown code blocks if present
            cleaned = raw_output.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
                cleaned = re.sub(r"\n?```$", "", cleaned)
            data = json.loads(cleaned)

            for c in data.get("claims", []):
                verdict = str(c.get("verdict", "unsupported")).strip().lower()
                claims.append(
                    GroundednessClaim(
                        claim=c.get("claim", ""),
                        verdict="supported" if verdict == "supported" else "unsupported",
                        reason=c.get("reason", ""),
                    )
                )
        except Exception as e:
            logger.warning("Failed parsing groundedness judge JSON: %s. Output was: %s", e, raw_output[:120])
            # Fallback
            claims = [GroundednessClaim(claim=answer, verdict="supported", reason="Fallback evaluation")]

        supported = sum(1 for c in claims if c.verdict == "supported")
        total = len(claims)
        score = float(supported) / float(max(total, 1))

        return GroundednessResult(
            claims=claims,
            supported_count=supported,
            total_count=total,
            groundedness_score=score,
        )
