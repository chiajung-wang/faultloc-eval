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

#: A dev-split run is 244 sequential calls. Without retries a single transient
#: rate limit anywhere in it destroys the whole run and everything spent on it,
#: which is what happened on M4's first full attempt: $2.25 for zero completed
#: runs. Five attempts covers a provider quota window; more would mean the
#: provider is down rather than busy.
MAX_ATTEMPTS = 5

#: Doubling from one second: 1, 2, 4, 8. Constant retries against a rate limit
#: are just the same burst again, so the wait has to grow for the window to
#: clear.
BACKOFF_S = 1.0

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
#: gpt-oss routes to Cerebras, measured at 722 tok/s against DeepInfra's 40 --
#: 18x, which is the difference between a 40-minute run and a seven-hour one.
#: Precision is not the trade it looks like: `gpt-oss-120b` ships *natively* in
#: MXFP4, so every 16-bit endpoint is upcasting already-4-bit weights, and the
#: fp4 endpoints measured slower than bf16 anyway. Speed here is hardware.
MODELS = {
    "gpt-oss-low": Model(
        label="gpt-oss-low",
        name="openai/gpt-oss-120b",
        provider="cerebras/fp16",
        reasoning={"effort": "low"},
    ),
    "gpt-oss-high": Model(
        label="gpt-oss-high",
        name="openai/gpt-oss-120b",
        provider="cerebras/fp16",
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
    return BACKOFF_S * 2**attempt


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
