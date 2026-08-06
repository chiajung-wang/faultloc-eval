"""Calling OpenRouter, pinned to one upstream serve.

**Deliberately not LangChain**, against [ADR-0005](../../docs/adr/0005-langgraph.md)'s
default. `langchain-openrouter` 0.2.7 accepts a `reasoning` argument and does
not forward it: `{"enabled": False}` still produced 164, 136 and 120 reasoning
tokens across three calls where the same request over HTTP produced 0. Rung 3's
whole ablation is that flag, so building on a client that drops it would compare
a model against itself and publish the result. The same client reports
`model_provider` as `"openrouter"` rather than the upstream serve, which
ADR-0008 requires in the entry.

One `urllib` call needs no dependency at all. M5's agent can revisit LangChain
on its own merits, where tool-calling is the thing being bought.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from faultloc.env import load_env

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

#: A dev-split run is 244 sequential calls, so one unrecovered rate limit
#: anywhere in it destroys the run and everything spent on it. That has now
#: happened twice: $2.25 on M4's first attempt with no retry at all, and $0.63
#: at instance 110 with five attempts and fifteen seconds of total backoff.
#:
#: Eight attempts at 2s doubling waits about four minutes in total. That rides
#: out a burst; it does not ride out a saturated shared pool, which is what
#: OpenRouter's Groq capacity turned out to be -- still limited thirty minutes
#: later. No amount of patience fixes that, and pretending otherwise would just
#: fail slower. Route choice is the answer there, not backoff.
MAX_ATTEMPTS = 8

#: Doubling from two seconds: 2, 4, 8, 16, 32, 64, 120. Constant retries
#: against a rate limit are the same burst again, so the wait has to grow.
BACKOFF_S = 2.0

#: Ceiling on one wait. Past two minutes the provider is not busy, it is out,
#: and a run that sits blocked for longer should fail loudly instead.
MAX_BACKOFF_S = 120.0

#: Busy, not broken. Everything else -- a malformed request, an unknown model,
#: a provider policy rejection -- fails identically on every attempt, and
#: retrying it burns the rate limit that the real calls need.
RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})


class MissingKeyError(RuntimeError):
    """No API key. Named separately so the failure reads as setup, not a bug."""


def api_key() -> str:
    """The OpenRouter key, from the environment or from `.env`."""
    load_env()
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise MissingKeyError(
            "OPENROUTER_API_KEY is not set; copy .env.sample to .env and fill it in"
        )
    return key


@dataclass(frozen=True)
class Model:
    """One rung-3 configuration, pinned three ways.

    ADR-0007 pinned rung 2's encoder by name *and* revision because a name is
    not provenance. ADR-0008's second amendment adds a third: the same model ID
    is served by providers at different quantizations, so the **route** decides
    the weights. `provider` is the endpoint `tag` from
    `/api/v1/models/{id}/endpoints`, not its display name.
    """

    label: str
    name: str
    provider: str
    #: OpenRouter's `reasoning` field, verbatim. `None` leaves the model's own
    #: default, which is not the same as off for either model here.
    reasoning: dict | None


#: The four cells of ADR-0008, as amended. gpt-oss has no way to disable
#: reasoning, only to ask for less of it, so its ablation is low-against-high
#: while DeepSeek's is off-against-on. Each pair moves one variable; the two
#: pairs are not comparable to each other, and the ADR says so.
#:
#: gpt-oss routes to Groq. Cerebras was faster still -- 722 tok/s against 198 --
#: but **enforces an 8,192-token completion limit while advertising 40,960**,
#: and high effort needs 7,300-8,200 tokens on this prompt. It therefore
#: truncated a third of replies, and a truncated reply degrades to the input
#: ranking, which would have published as "the model did not help" when the
#: model never answered. Speed is worthless if the answer is cut off.
#:
#: Precision is not the trade it looks like: `gpt-oss-120b` ships *natively* in
#: MXFP4, so every 16-bit endpoint is upcasting already-4-bit weights. Groq
#: reporting `unknown` quantization costs less than it appears to.
MODELS = {
    "gpt-oss-low": Model(
        label="gpt-oss-low",
        name="openai/gpt-oss-120b",
        provider="deepinfra/bf16",
        reasoning={"effort": "low"},
    ),
    "gpt-oss-high": Model(
        label="gpt-oss-high",
        name="openai/gpt-oss-120b",
        provider="deepinfra/bf16",
        reasoning={"effort": "high"},
    ),
    "deepseek-off": Model(
        label="deepseek-off",
        name="deepseek/deepseek-v4-pro",
        provider="deepseek",
        reasoning={"enabled": False},
    ),
    "deepseek-on": Model(
        label="deepseek-on",
        name="deepseek/deepseek-v4-pro",
        provider="deepseek",
        reasoning=None,
    ),
}


@dataclass(frozen=True)
class Response:
    """What one call returned, including what it cost and who served it."""

    text: str
    cost_usd: float
    finish_reason: str
    provider: str
    output_tokens: int
    reasoning_tokens: int

    @property
    def truncated(self) -> bool:
        """Ran out of output budget before answering.

        The failure that matters most here. An empty or cut-off answer degrades
        to the input ranking, which *is* fusion's order, so a run that truncated
        everywhere would score exactly like rung 2.5 and read as "the model did
        not help" when the model never answered. Measured: at max_tokens=50,
        gpt-oss-120b spent 45 tokens reasoning and returned empty content.
        """
        return self.finish_reason == "length"


def _send(request: urllib.request.Request, *, timeout: float) -> dict:
    """One request, retried while the provider is merely busy.

    Retries only the statuses that mean *try again*. A 400 or a 404 fails the
    same way every time -- retrying those would burn the rate limit that the
    calls still to come depend on.
    """
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as raw:
                return json.load(raw)
        except urllib.error.HTTPError as failed:
            last = attempt == MAX_ATTEMPTS - 1
            if failed.code not in RETRYABLE or last:
                # The body carries the reason; the status line does not. A 404
                # here usually means the account's provider policy excludes
                # every serve of this model, which reads nothing like
                # "Not Found".
                raise RuntimeError(f"openrouter {failed.code}: {_reason(failed)}") from failed
            time.sleep(_wait(failed, attempt))

    raise AssertionError("unreachable: the final attempt either returns or raises")


def _wait(failed: urllib.error.HTTPError, attempt: int) -> float:
    """How long before trying again.

    `Retry-After` wins when the provider sends one: it knows when its window
    resets, and guessing shorter wastes an attempt.
    """
    header = failed.headers.get("Retry-After") if failed.headers else None
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    return min(BACKOFF_S * 2**attempt, MAX_BACKOFF_S)


def _reason(failed: urllib.error.HTTPError) -> str:
    """The API's own explanation, or the raw body if it is not JSON."""
    body = failed.read().decode(errors="replace")
    try:
        error = json.loads(body).get("error", {})
    except json.JSONDecodeError:
        return body[:400]

    message = error.get("message", body[:200])
    allowed = (error.get("metadata") or {}).get("available_providers")
    if allowed:
        return f"{message} (model is served by: {', '.join(allowed)})"
    return message


def call(model: Model, prompt: str, *, max_tokens: int, timeout: float = 180.0) -> Response:
    """One chat completion, pinned to `model`'s route.

    `allow_fallbacks` is false rather than a fallback order: a silent reroute
    mid-run would mix two serves inside one published number, which is worse
    than a failed run.
    """
    key = api_key()

    body = {
        "model": model.name,
        "provider": {"only": [model.provider], "allow_fallbacks": False},
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        # Asks OpenRouter to price the call. Cost is then *read* rather than
        # computed from a price list, so a price change cannot silently
        # invalidate a published figure.
        "usage": {"include": True},
    }
    if model.reasoning is not None:
        body["reasoning"] = model.reasoning

    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    payload = _send(request, timeout=timeout)

    if "error" in payload:
        raise RuntimeError(f"openrouter: {payload['error']}")

    choice = payload["choices"][0]
    usage = payload.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}

    return Response(
        text=choice["message"].get("content") or "",
        cost_usd=float(usage.get("cost") or 0.0),
        finish_reason=choice.get("finish_reason") or "",
        provider=payload.get("provider") or "",
        output_tokens=int(usage.get("completion_tokens") or 0),
        reasoning_tokens=int(details.get("reasoning_tokens") or 0),
    )
