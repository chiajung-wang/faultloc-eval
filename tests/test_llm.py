"""Tests for the OpenRouter client.

Nothing here reaches the network: `urlopen` is monkeypatched, and so is the
sleep, so backoff is asserted rather than waited for.

The retry behaviour is the point. A rung-3 run is 244 sequential calls, so a
single transient 429 anywhere in it destroys the whole run and everything spent
on it -- which is exactly what happened on M4's first full attempt, at a cost of
$2.25 for zero completed runs.
"""

from __future__ import annotations

import http.client
import io
import json
import urllib.error

import pytest

from faultloc import llm

MODEL = llm.MODELS["gpt-oss-high"]


def http_error(code: int, message: str = "rate limited", retry_after: str | None = None):
    headers = {"Retry-After": retry_after} if retry_after else {}
    body = json.dumps({"error": {"message": message}}).encode()
    return urllib.error.HTTPError(llm.ENDPOINT, code, message, headers, io.BytesIO(body))


def ok_response(text: str = "a.py", cost: float = 0.001):
    payload = {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {
            "cost": cost,
            "completion_tokens": 12,
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
        "provider": "Cerebras",
    }

    class Fake(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return Fake(json.dumps(payload).encode())


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch):
    """Replaces `urlopen` with a scripted sequence and records sleeps."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    slept: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", slept.append)

    def install(*results):
        remaining = list(results)
        calls: list[dict] = []

        def fake_urlopen(request, timeout=None):
            calls.append(json.loads(request.data))
            outcome = remaining.pop(0)
            # Any exception, not just HTTPError: transport failures arrive as
            # TimeoutError and friends, and a fixture that only raised status
            # errors could not express them.
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        # Via monkeypatch so the real `urlopen` is restored afterwards. A bare
        # assignment here would leak into every test that runs later.
        monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
        return calls

    install.slept = slept  # type: ignore[attr-defined]
    return install


class TestRetry:
    def test_retries_a_429_and_succeeds(self, no_network) -> None:
        calls = no_network(http_error(429), ok_response())
        response = llm.call(MODEL, "prompt", max_tokens=100)

        assert response.text == "a.py"
        assert len(calls) == 2

    def test_retries_a_server_error(self, no_network) -> None:
        calls = no_network(http_error(503, "upstream unavailable"), ok_response())
        llm.call(MODEL, "prompt", max_tokens=100)

        assert len(calls) == 2

    def test_does_not_retry_a_bad_request(self, no_network) -> None:
        """A 400 is our bug and will fail identically every time. Retrying it
        four more times burns the rate limit to no purpose."""
        calls = no_network(http_error(400, "malformed"))

        with pytest.raises(RuntimeError, match="400"):
            llm.call(MODEL, "prompt", max_tokens=100)

        assert len(calls) == 1

    def test_gives_up_after_the_last_attempt_and_says_why(self, no_network) -> None:
        errors = [http_error(429) for _ in range(llm.MAX_ATTEMPTS)]
        calls = no_network(*errors)

        with pytest.raises(RuntimeError, match="429"):
            llm.call(MODEL, "prompt", max_tokens=100)

        assert len(calls) == llm.MAX_ATTEMPTS

    def test_backs_off_further_each_time(self, no_network) -> None:
        """Constant retries against a rate limit are just the same burst again.
        Each wait has to grow or the limit never gets a chance to clear."""
        no_network(http_error(429), http_error(429), ok_response())
        llm.call(MODEL, "prompt", max_tokens=100)

        waits = no_network.slept
        assert len(waits) == 2
        assert waits[1] > waits[0]

    def test_honours_retry_after_when_the_provider_sends_one(self, no_network) -> None:
        """The provider knows when its window resets; guessing shorter just
        wastes an attempt."""
        no_network(http_error(429, retry_after="30"), ok_response())
        llm.call(MODEL, "prompt", max_tokens=100)

        assert no_network.slept == [30.0]


class TestRequest:
    def test_pins_the_route_and_disables_fallbacks(self, no_network) -> None:
        """ADR-0008's second amendment: the serve decides the weights, so an
        unpinned call names a model that does not determine the number."""
        calls = no_network(ok_response())
        llm.call(MODEL, "prompt", max_tokens=100)

        sent = calls[0]
        assert sent["provider"] == {"only": [MODEL.provider], "allow_fallbacks": False}
        assert sent["usage"] == {"include": True}
        assert sent["reasoning"] == MODEL.reasoning

    def test_reads_cost_and_provider_from_the_response(self, no_network) -> None:
        no_network(ok_response(cost=0.0042))
        response = llm.call(MODEL, "prompt", max_tokens=100)

        assert response.cost_usd == pytest.approx(0.0042)
        assert response.provider == "Cerebras"
        assert response.reasoning_tokens == 5


class TestBackoffCeiling:
    def test_a_single_wait_is_capped(self, no_network) -> None:
        """Past two minutes the provider is not busy, it is out. A run that
        sits blocked longer than that should fail loudly rather than stall."""
        errors = [http_error(429) for _ in range(llm.MAX_ATTEMPTS - 1)]
        no_network(*errors, ok_response())
        llm.call(MODEL, "prompt", max_tokens=100)

        assert max(no_network.slept) <= llm.MAX_BACKOFF_S

    def test_patience_grew_after_a_run_died_at_instance_110(self, no_network) -> None:
        """Five attempts over fifteen seconds lost a run and $0.63. The total
        wait now spans minutes, which rides out a burst."""
        errors = [http_error(429) for _ in range(llm.MAX_ATTEMPTS - 1)]
        no_network(*errors, ok_response())
        llm.call(MODEL, "prompt", max_tokens=100)

        assert sum(no_network.slept) > 120


def error_body(code: int, message: str = "Provider timed out"):
    """A 200 response whose *payload* carries the error.

    OpenRouter does this: HTTP 200, `{"error": {"code": 504}}` in the body.
    A retry that only watches the status line never sees it.
    """
    payload = {"error": {"message": message, "code": code}}

    class Fake(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return Fake(json.dumps(payload).encode())


class TestBodyLevelErrors:
    def test_a_504_in_the_body_is_retried_like_one_in_the_status_line(self, no_network) -> None:
        """This killed the ladder row after the patient backoff was built --
        the retry never ran, because the error never reached it."""
        calls = no_network(error_body(504), ok_response())
        response = llm.call(MODEL, "prompt", max_tokens=100)

        assert response.text == "a.py"
        assert len(calls) == 2

    def test_a_non_retryable_code_in_the_body_still_raises_at_once(self, no_network) -> None:
        calls = no_network(error_body(400, "malformed request"))

        with pytest.raises(RuntimeError, match="400"):
            llm.call(MODEL, "prompt", max_tokens=100)

        assert len(calls) == 1

    def test_it_gives_up_after_the_last_attempt(self, no_network) -> None:
        errors = [error_body(504) for _ in range(llm.MAX_ATTEMPTS)]
        calls = no_network(*errors)

        with pytest.raises(RuntimeError, match="504"):
            llm.call(MODEL, "prompt", max_tokens=100)

        assert len(calls) == llm.MAX_ATTEMPTS


class TestTimeout:
    def test_the_default_clears_a_slow_route(self) -> None:
        """DeepInfra took over 300s on one instance against a 180s default.
        It averages 154s, so the tail runs well past twice the mean."""
        assert llm.DEFAULT_TIMEOUT_S >= 600


class TestTransportFailures:
    """The third place a failure arrives, after the status line and the body.

    A dropped connection or a read timeout produces no response to inspect at
    all, and raises something that is not an HTTPError. The ladder row's log
    showed two `openrouter 503`s against four crashes: the other two were
    these, killing a 244-call run without retrying once.
    """

    def test_a_read_timeout_is_retried(self, no_network) -> None:
        calls = no_network(TimeoutError("The read operation timed out"), ok_response())
        assert llm.call(MODEL, "prompt", max_tokens=100).text == "a.py"
        assert len(calls) == 2

    def test_a_server_hangup_is_retried(self, no_network) -> None:
        calls = no_network(http.client.IncompleteRead(b"451 bytes"), ok_response())
        assert llm.call(MODEL, "prompt", max_tokens=100).text == "a.py"
        assert len(calls) == 2

    def test_a_refused_connection_is_retried(self, no_network) -> None:
        calls = no_network(urllib.error.URLError("connection refused"), ok_response())
        assert llm.call(MODEL, "prompt", max_tokens=100).text == "a.py"
        assert len(calls) == 2

    def test_it_still_gives_up_rather_than_hanging_forever(self, no_network) -> None:
        calls = no_network(*[TimeoutError("timed out") for _ in range(llm.MAX_ATTEMPTS)])

        with pytest.raises(RuntimeError, match="timed out"):
            llm.call(MODEL, "prompt", max_tokens=100)

        assert len(calls) == llm.MAX_ATTEMPTS

    def test_a_status_error_is_still_handled_as_a_status_error(self, no_network) -> None:
        """HTTPError subclasses URLError. If the transport catch is ordered
        first it swallows every status code, and a 400 would be retried eight
        times instead of raising at once."""
        calls = no_network(http_error(400, "malformed"))

        with pytest.raises(RuntimeError, match="400"):
            llm.call(MODEL, "prompt", max_tokens=100)

        assert len(calls) == 1
