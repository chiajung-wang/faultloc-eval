"""Tests for the LLM response cache.

The cache exists so a run that dies at 90% does not have to re-pay for the
first 90%. That happened twice in one day -- at instance 110 and at instance
40 -- and the ladder row is a ten-hour run.

What it must never do is serve a response produced by a *different* question.
`EmbeddingIndex` refuses to read an index built by another model for the same
reason: a plausible answer with the wrong provenance is worse than a crash.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from faultloc.llm import MODELS, Response
from faultloc.response_cache import ResponseCache

MODEL = MODELS["gpt-oss-high"]


def response(text: str = "a.py", cost: float = 0.004) -> Response:
    return Response(
        text=text,
        cost_usd=cost,
        finish_reason="stop",
        provider="DeepInfra",
        output_tokens=120,
        reasoning_tokens=90,
    )


class TestRoundTrip:
    def test_what_goes_in_comes_back(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path)
        cache.put(MODEL, "prompt", 16000, response())

        assert cache.get(MODEL, "prompt", 16000) == response()

    def test_a_miss_is_none_not_an_error(self, tmp_path: Path) -> None:
        assert ResponseCache(tmp_path).get(MODEL, "prompt", 16000) is None

    def test_survives_a_new_cache_object(self, tmp_path: Path) -> None:
        """The whole point: a later process must find what an earlier one
        stored, or resuming buys nothing."""
        ResponseCache(tmp_path).put(MODEL, "prompt", 16000, response())

        assert ResponseCache(tmp_path).get(MODEL, "prompt", 16000) is not None


class TestKeying:
    def test_a_different_prompt_misses(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path)
        cache.put(MODEL, "prompt", 16000, response())

        assert cache.get(MODEL, "other prompt", 16000) is None

    def test_a_different_model_misses(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path)
        cache.put(MODEL, "prompt", 16000, response())

        assert cache.get(MODELS["deepseek-on"], "prompt", 16000) is None

    def test_a_different_reasoning_setting_misses(self, tmp_path: Path) -> None:
        """low and high effort are the two halves of an ablation. Serving one
        from the other's cache would compare a model against itself and
        publish the result."""
        cache = ResponseCache(tmp_path)
        cache.put(MODEL, "prompt", 16000, response())

        assert cache.get(MODELS["gpt-oss-low"], "prompt", 16000) is None

    def test_a_different_route_misses(self, tmp_path: Path) -> None:
        """ADR-0008's second amendment: the serve decides the weights, so a
        response from another provider answers a different question."""
        cache = ResponseCache(tmp_path)
        cache.put(MODEL, "prompt", 16000, response())

        assert cache.get(replace(MODEL, provider="groq"), "prompt", 16000) is None

    def test_a_different_token_budget_misses(self, tmp_path: Path) -> None:
        """A reply truncated at 4,000 tokens is not the reply the same prompt
        gives at 16,000 -- that difference cost a run today."""
        cache = ResponseCache(tmp_path)
        cache.put(MODEL, "prompt", 4000, response())

        assert cache.get(MODEL, "prompt", 16000) is None


class TestRobustness:
    def test_a_corrupt_entry_is_a_miss_rather_than_a_crash(self, tmp_path: Path) -> None:
        """A half-written entry from a killed run must cost one API call, not
        the whole run."""
        cache = ResponseCache(tmp_path)
        cache.put(MODEL, "prompt", 16000, response())
        next(tmp_path.rglob("*.json")).write_text("{not json")

        assert cache.get(MODEL, "prompt", 16000) is None

    def test_writes_leave_no_temp_files_behind(self, tmp_path: Path) -> None:
        cache = ResponseCache(tmp_path)
        cache.put(MODEL, "prompt", 16000, response())

        assert list(tmp_path.rglob("*.tmp")) == []
