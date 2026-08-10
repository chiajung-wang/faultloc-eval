"""Rung 4's model client.

Three properties matter, and all three were learned the expensive way at rung 3.
The cost is read from the reply rather than computed. Retries reach the sites
that actually kill a run. And the cache key covers everything that determines an
answer, because the free replay that makes a six-hour run resumable rests on it.

No test here touches the network. The chat model is injected, as rung 2 injects
its encoder and rung 3 its client.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from openrouter.errors import OpenRouterError

from faultloc.agent_client import AgentCache, AgentClient, AgentReply, canonical_key
from faultloc.llm import MODELS


class Message:
    """Stands in for whatever the framework hands back."""

    def __init__(
        self,
        content: str = "ok",
        tool_calls: list | None = None,
        cost: float = 0.0002,
        finish_reason: str = "stop",
        reasoning: int = 12,
        fingerprint: str = "fp_abc_fp8_kvcache",
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.response_metadata = {
            "cost": cost,
            "finish_reason": finish_reason,
            "system_fingerprint": fingerprint,
        }
        self.usage_metadata = {
            "input_tokens": 100,
            "output_tokens": 40,
            "output_token_details": {"reasoning": reasoning},
        }


class Scripted:
    """A chat model that replays a list, and records what it was asked."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.seen: list[Any] = []

    def invoke(self, messages: Any) -> Any:
        self.seen.append(messages)
        nxt = self.replies.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


class Human:
    """A minimal message, so the key builder is exercised without the framework."""

    def __init__(self, content: str, type_: str = "human") -> None:
        self.content = content
        self.type = type_


def client(*replies: Any, **overrides: Any) -> AgentClient:
    fields: dict = {"model": MODELS["deepseek-on"], "chat": Scripted(*replies)}
    fields.update(overrides)
    return AgentClient(**fields)


def status_error(code: int) -> OpenRouterError:
    """Built the way the SDK builds one: the status comes from the raw response.

    Not by setting `.status_code` by hand. A fake whose shape differs from the
    real exception would test the fake.
    """
    return OpenRouterError(f"http {code}", httpx.Response(code))


class TestReadingTheReply:
    def test_cost_comes_from_the_reply_and_not_a_price_table(self) -> None:
        """ADR-0008's property. A price table can go stale while every number
        that cites it still looks correct."""
        reply = client(Message(cost=0.00073)).invoke([Human("hi")])

        assert reply.cost_usd == 0.00073

    def test_a_missing_cost_reads_as_zero_rather_than_raising(self) -> None:
        message = Message()
        message.response_metadata.pop("cost")

        assert client(message).invoke([Human("hi")]).cost_usd == 0.0

    def test_tool_calls_survive(self) -> None:
        call = {"name": "read_file", "args": {"path": "a.py"}, "id": "c1"}

        reply = client(Message(content="", tool_calls=[call])).invoke([Human("hi")])

        assert reply.tool_calls == (call,)

    def test_reasoning_tokens_are_read(self) -> None:
        assert client(Message(reasoning=903)).invoke([Human("hi")]).reasoning_tokens == 903

    def test_the_serve_fingerprint_is_kept(self) -> None:
        """`ChatOpenRouter` does not echo the upstream provider tag, so the
        fingerprint is the only evidence in the reply of which serve answered.
        ADR-0008's second amendment requires an entry to record the serve."""
        reply = client(Message(fingerprint="fp_9954_prod_fp8_kvcache")).invoke([Human("hi")])

        assert "fp8" in reply.fingerprint


class TestFailureShapes:
    def test_truncation_is_a_value_and_not_an_exception(self) -> None:
        """Measured: at max_tokens=1 the reply returns finish_reason='length',
        empty content, and a cost. At rung 4 this can fire once per step."""
        reply = client(Message(content="", finish_reason="length")).invoke([Human("hi")])

        assert reply.truncated
        assert reply.is_empty

    def test_an_empty_reply_with_a_normal_finish_is_still_empty(self) -> None:
        """Four of rung 3's empty replies reported finish=stop, which no
        truncation check can see. Counted separately for that reason."""
        reply = client(Message(content="   ", finish_reason="stop")).invoke([Human("hi")])

        assert reply.is_empty
        assert not reply.truncated

    def test_a_reply_with_tool_calls_is_not_empty(self) -> None:
        call = {"name": "read_file", "args": {}, "id": "c1"}

        reply = client(Message(content="", tool_calls=[call])).invoke([Human("hi")])

        assert not reply.is_empty

    def test_counts_truncated_and_empty_replies(self) -> None:
        engine = client(
            Message(content="", finish_reason="length"),
            Message(content="fine"),
        )
        engine.invoke([Human("a")])
        engine.invoke([Human("b")])

        assert (engine.truncated, engine.empty) == (1, 1)


class TestRetries:
    @pytest.fixture(autouse=True)
    def _never_really_sleep(self, monkeypatch) -> None:
        """No test in this class may wait.

        Not a convenience. The backoff is 2s doubling to a 120s ceiling, so a
        regression that retries something it should not takes about four minutes
        per case. A suite that hangs on a regression is nearly as bad as one that
        passes on it, and this fixture is what makes the failure arrive fast.
        """
        monkeypatch.setattr("faultloc.agent_client.time.sleep", lambda _s: None)

    @pytest.mark.parametrize("code", [408, 429, 500, 502, 503, 504])
    def test_retries_a_provider_that_is_merely_busy(self, code: int) -> None:
        engine = client(status_error(code), Message(content="second try"))

        assert engine.invoke([Human("hi")]).text == "second try"
        assert engine.retries == 1

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 422])
    def test_never_retries_a_request_that_will_always_fail(self, code: int) -> None:
        """Measured status codes: a bad model gives 400, a bad key 401, an
        impossible provider pin 404. Retrying those burns the rate limit that
        the calls still to come depend on."""
        engine = client(status_error(code), Message(content="never reached"))

        with pytest.raises(OpenRouterError):
            engine.invoke([Human("hi")])
        assert engine.retries == 0

    def test_retries_a_dropped_connection(self) -> None:
        """`httpx.TransportError` does not subclass `OSError`, so it needs its
        own catch. Two of rung 3's four crashes arrived this way."""
        engine = client(httpx.ConnectError("dropped"), Message(content="recovered"))

        assert engine.invoke([Human("hi")]).text == "recovered"

    def test_gives_up_loudly_rather_than_forever(self) -> None:
        engine = client(*[status_error(429) for _ in range(8)])

        with pytest.raises(OpenRouterError):
            engine.invoke([Human("hi")])

    def test_a_programming_error_is_not_retried(self) -> None:
        """A TypeError is a bug, not a busy provider. Eight attempts and four
        minutes of backoff would hide it."""
        engine = client(TypeError("bug"))

        with pytest.raises(TypeError):
            engine.invoke([Human("hi")])
        assert engine.retries == 0


class TestCanonicalKey:
    def test_is_deterministic_for_the_same_transcript(self) -> None:
        messages = [Human("first"), Human("second")]

        assert canonical_key(messages, []) == canonical_key(messages, [])

    def test_a_different_transcript_is_a_different_key(self) -> None:
        assert canonical_key([Human("a")], []) != canonical_key([Human("b")], [])

    def test_transcript_order_changes_the_key(self) -> None:
        """A step's question is the whole history, not a set of messages."""
        a, b = Human("a"), Human("b")

        assert canonical_key([a, b], []) != canonical_key([b, a], [])

    def test_the_tool_surface_is_part_of_the_key(self) -> None:
        """The same transcript with different tools is a different question.

        Answering it from cache would replay a decision the model never made
        about the tools it now has. Issue 05 adds four tools to this exact
        transcript shape.
        """
        one = [{"name": "read_file"}]
        two = [{"name": "read_file"}, {"name": "search_code"}]

        assert canonical_key([Human("a")], one) != canonical_key([Human("a")], two)


class TestCache:
    def test_a_second_identical_step_is_free(self, tmp_path: Path) -> None:
        engine = client(Message(content="paid for once"), cache=AgentCache(tmp_path))

        first = engine.invoke([Human("hi")])
        second = engine.invoke([Human("hi")])

        assert first == second
        assert (engine.calls, engine.cache_hits) == (1, 1)

    def test_a_replayed_step_costs_no_new_money(self, tmp_path: Path) -> None:
        """`spent_usd` counts money leaving the account now, so a resumed run is
        not aborted by a cap it already cleared once."""
        engine = client(Message(cost=0.005), cache=AgentCache(tmp_path))
        engine.invoke([Human("hi")])
        engine.invoke([Human("hi")])

        assert engine.spent_usd == pytest.approx(0.005)

    def test_tool_calls_come_back_as_a_tuple(self, tmp_path: Path) -> None:
        """JSON has no tuples, and `AgentReply` is frozen. A list would compare
        unequal to the reply that was stored."""
        call = {"name": "read_file", "args": {"path": "a.py"}, "id": "c1"}
        engine = client(Message(content="", tool_calls=[call]), cache=AgentCache(tmp_path))
        engine.invoke([Human("hi")])

        replayed = AgentCache(tmp_path).get(
            MODELS["deepseek-on"], canonical_key([Human("hi")], ()), 16000
        )

        assert replayed is not None
        assert isinstance(replayed.tool_calls, tuple)

    def test_a_cache_built_by_another_model_is_refused(self, tmp_path: Path) -> None:
        """The `EmbeddingIndex` guard, one layer up. A cache that crosses two
        cells in silence is worse than no cache."""
        cache = AgentCache(tmp_path)
        cache.put(
            MODELS["deepseek-on"], "same key", 16000, AgentReply("a", (), 0.1, "stop", 1, 1, 1)
        )

        assert cache.get(MODELS["deepseek-off"], "same key", 16000) is None
        assert cache.get(MODELS["gpt-oss-high"], "same key", 16000) is None

    def test_a_cache_built_at_another_token_budget_is_refused(self, tmp_path: Path) -> None:
        """Rung 3's MAX_TOKENS moved from 4,000 to 16,000 after truncation, and
        every reply before that move answered a different question."""
        cache = AgentCache(tmp_path)
        cache.put(MODELS["deepseek-on"], "k", 4000, AgentReply("a", (), 0.1, "stop", 1, 1, 1))

        assert cache.get(MODELS["deepseek-on"], "k", 16000) is None

    def test_a_half_written_entry_is_a_miss_and_not_a_crash(self, tmp_path: Path) -> None:
        cache = AgentCache(tmp_path)
        cache.put(MODELS["deepseek-on"], "k", 16000, AgentReply("a", (), 0.1, "stop", 1, 1, 1))
        corrupt = next(tmp_path.rglob("*.json"))
        corrupt.write_text('{"reply": {"text"')

        assert cache.get(MODELS["deepseek-on"], "k", 16000) is None

    def test_leaves_no_temporary_file_behind(self, tmp_path: Path) -> None:
        cache = AgentCache(tmp_path)
        cache.put(MODELS["deepseek-on"], "k", 16000, AgentReply("a", (), 0.1, "stop", 1, 1, 1))

        assert not list(tmp_path.rglob("*.tmp"))

    def test_no_cache_means_every_step_is_paid_for(self) -> None:
        """Off unless one is handed in, so a test that forgets one cannot write
        into the real cache directory."""
        engine = client(Message(), Message())
        engine.invoke([Human("hi")])
        engine.invoke([Human("hi")])

        assert (engine.calls, engine.cache_hits) == (2, 0)
