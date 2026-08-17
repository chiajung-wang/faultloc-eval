"""Rung 4's model client: a pinned route, a real cost, and three retry sites.

[ADR-0005](../../docs/adr/0005-langgraph.md)'s amendment settled the framework by
probe and then named two things the framework does not do. This module is those
two things.

**The cost is read, not computed.** `ChatOpenRouter` puts OpenRouter's own
per-request figure in `response_metadata["cost"]`, unasked. ADR-0008 treats that
as the property that keeps a published cost honest, because a price table in the
repository can go stale while every number that cites it still looks right.

**Retries reach three sites, not one.** `llm.py` learned them the expensive way,
and this module reuses its constants rather than restate them. A probe on
2026-08-10 measured how they arrive through the framework:

| Site | Arrives as |
|---|---|
| HTTP status | `OpenRouterError` subclass with `.status_code` |
| transport drop | `httpx.TransportError`, which does *not* subclass `OSError` |
| error inside a 200 body | the SDK parses bodies and raises typed errors |

The third row is inference rather than measurement. A 404 carrying a JSON body
raised `NotFoundResponseError`, so the SDK clearly inspects bodies. Nobody has
forced a 504-inside-a-200 through it.

**Truncation does not raise.** At `max_tokens=1` the reply came back with
`finish_reason="length"`, empty content, and a cost. So an exhausted output
budget is a value to count and not an exception to catch, exactly as at rung 3 --
and at rung 4 it can fire once per step rather than once per Instance.

**The cache is this project's own, and it is separate from rung 3's.** Rung 3
keys on one prompt string. An agent step carries a whole transcript, so the key
has to cover every message and the tool schemas as well. A shared directory
would make two different questions hash into one namespace, and the free replay
that makes a six-hour run resumable depends on that key being exactly right.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from openrouter.errors import OpenRouterError

from faultloc.llm import (
    BACKOFF_S,
    MAX_ATTEMPTS,
    MAX_BACKOFF_S,
    RETRYABLE,
    Model,
    api_key,
)

DEFAULT_AGENT_CACHE = Path("data/cache/agent")


@dataclass(frozen=True)
class AgentReply:
    """One step's reply: text, or tool calls, and what the step cost.

    A step produces one or the other. A reply with neither is the failure M4
    found four times at rung 3, where an empty answer degraded to the input
    ranking and the run looked healthy in every metric except the one saying how
    often the model answered.
    """

    text: str
    tool_calls: tuple[dict, ...]
    cost_usd: float
    finish_reason: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    #: The serve's own build string. `ChatOpenRouter` does not echo the upstream
    #: provider tag the way the raw API does, so this is the only evidence in the
    #: reply of *which* serve answered. ADR-0008's second amendment requires an
    #: entry to record the serve, and the pinned tag plus this string is how
    #: rung 4 satisfies it.
    fingerprint: str = ""

    @property
    def truncated(self) -> bool:
        """Ran out of output budget before answering."""
        return self.finish_reason == "length"

    @property
    def is_empty(self) -> bool:
        """Neither an answer nor a tool call.

        Counted separately from `truncated`, because four of rung 3's empty
        replies reported `finish=stop`, which no truncation check can see.
        """
        return not self.text.strip() and not self.tool_calls


class Chat(Protocol):
    """The one method this module needs, so a test can supply a fake."""

    def invoke(self, messages: Sequence[Any]) -> Any: ...


def canonical_key(messages: Sequence[Any], tools: Sequence[dict]) -> str:
    """A stable string for a transcript and the tools that were offered.

    Deterministic by construction, and written here rather than taken from the
    framework's own serializer. A library that changed its message dictionary
    between versions would silently invalidate every cached step, and the cost of
    that is a six-hour run paid for twice.

    The tool schemas are part of the key. The same transcript with a different
    tool surface is a different question, and answering it from cache would
    replay a decision the model never made about the tools it now has.
    """
    transcript = [
        {
            "type": getattr(message, "type", message.__class__.__name__),
            "content": getattr(message, "content", ""),
            "tool_calls": getattr(message, "tool_calls", []) or [],
            "tool_call_id": getattr(message, "tool_call_id", ""),
        }
        for message in messages
    ]
    return json.dumps({"messages": transcript, "tools": list(tools)}, sort_keys=True, default=str)


class AgentCache:
    """Replies keyed by everything that determines them.

    Separate from rung 3's `ResponseCache` on purpose. The two hold different
    payload shapes -- one carries text, the other can carry tool calls -- and a
    shared directory would let one rung's entry answer the other's question.
    """

    def __init__(self, root: Path = DEFAULT_AGENT_CACHE) -> None:
        self.root = Path(root)

    def get(self, model: Model, key: str, max_tokens: int) -> AgentReply | None:
        path = self._path(model, key, max_tokens)
        if not path.is_file():
            return None
        try:
            stored = json.loads(path.read_text())
            reply = stored["reply"]
            reply["tool_calls"] = tuple(reply["tool_calls"])
            return AgentReply(**reply)
        except (json.JSONDecodeError, KeyError, TypeError):
            # A half-written file from a killed run is a miss. It costs one call.
            # Raising would cost the run.
            return None

    def put(self, model: Model, key: str, max_tokens: int, reply: AgentReply) -> None:
        path = self._path(model, key, max_tokens)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": model.name,
            "provider": model.provider,
            "reasoning": model.reasoning,
            "max_tokens": max_tokens,
            "reply": asdict(reply),
        }
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(path)

    def _path(self, model: Model, key: str, max_tokens: int) -> Path:
        digest = hashlib.sha256(
            json.dumps(
                [model.name, model.provider, model.reasoning, max_tokens, key],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return self.root / digest[:2] / f"{digest}.json"


def _is_retryable(failed: BaseException) -> bool:
    """Busy, not broken.

    A 400, a 401 and a 404 fail identically on every attempt. Retrying them
    burns the rate limit the real calls depend on, and `llm.py` says so at
    length. Measured status codes: a bad model gives 400, a bad key 401, and an
    impossible provider pin 404.
    """
    if isinstance(failed, httpx.TransportError):
        return True
    if isinstance(failed, OpenRouterError):
        return getattr(failed, "status_code", None) in RETRYABLE
    return False


@dataclass
class AgentClient:
    """A pinned chat model with retries, a cost reader, and a cache.

    `chat` is injectable so tests make no network calls, which is the rule rung 2
    follows for its encoder and rung 3 for its client.
    """

    model: Model
    tools: tuple[dict, ...] = ()
    max_tokens: int = 16000
    #: Seconds to wait on one STEP. Deliberately far shorter than `llm.py`'s 900,
    #: which was sized for rung 3 where a single call does all the work and
    #: DeepInfra took over 300 seconds on one Instance.
    #:
    #: A rung-4 step is not that. Measured at `effort=low`: 26.9s per Instance,
    #: and the largest reply is 9,944 output tokens. So a step still unanswered at
    #: 300s is dead, not slow, and waiting 900 for it wastes eleven times the
    #: working case before the retry that would have fixed it.
    #:
    #: This matters because the waits multiply. Eight attempts at 900s is two
    #: hours of hanging before a run gives up, and a run that finally raised
    #: `ReadTimeout` after exhausting all eight is what set this number.
    timeout_s: float = 300.0
    cache: AgentCache | None = None
    chat: Chat | None = None

    #: Counted rather than absorbed. Each is a way a step can fail while still
    #: leaving the agent holding a ranking.
    calls: int = 0
    cache_hits: int = 0
    retries: int = 0
    truncated: int = 0
    empty: int = 0
    spent_usd: float = 0.0
    _client: Chat | None = field(default=None, repr=False)

    def invoke(self, messages: Sequence[Any]) -> AgentReply:
        """One step, from cache when this exact question was already paid for."""
        key = canonical_key(messages, self.tools)

        if self.cache is not None:
            hit = self.cache.get(self.model, key, self.max_tokens)
            if hit is not None:
                self.cache_hits += 1
                self._count(hit)
                return hit

        reply = self._send(messages)
        self.calls += 1
        self.spent_usd += reply.cost_usd
        self._count(reply)

        if self.cache is not None:
            self.cache.put(self.model, key, self.max_tokens, reply)
        return reply

    def _count(self, reply: AgentReply) -> None:
        self.truncated += reply.truncated
        self.empty += reply.is_empty

    def _send(self, messages: Sequence[Any]) -> AgentReply:
        """Retry while the provider is merely busy, then give up loudly.

        The call runs in a worker thread so a stalled step can be abandoned. The
        library's own `request_timeout` cannot do this: setting it to 10 produced
        no answer after 60 seconds, while the same call without it returns in
        1.3s. An abandoned thread is not killed, and that is acceptable here --
        it is blocked on a socket the process will close at exit, and the
        alternative is a run that hangs for hours.
        """
        client = self.chat or self._connect()

        for attempt in range(MAX_ATTEMPTS):
            try:
                return _reply_from(self._call_with_deadline(client, messages))
            # Caught broadly and then classified, rather than caught narrowly.
            # `_is_retryable` re-raises anything that is not a busy provider or a
            # dropped connection, so a bug still surfaces on the first attempt.
            except Exception as failed:
                last = attempt == MAX_ATTEMPTS - 1
                if last or not _is_retryable(failed):
                    raise
                self.retries += 1
                time.sleep(min(BACKOFF_S * 2**attempt, MAX_BACKOFF_S))

        raise AssertionError("unreachable: the final attempt either returns or raises")

    def _call_with_deadline(self, client: Chat, messages: Sequence[Any]) -> Any:
        """One call, abandoned if it outlives the step timeout.

        A test injects `chat` directly and every such call is instant, so the
        pool is only ever built for a real request.
        """
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(client.invoke, messages).result(timeout=self.timeout_s)
        except FuturesTimeout as expired:
            raise httpx.ReadTimeout(f"no reply after {self.timeout_s:.0f}s") from expired
        finally:
            # `wait=False` because a stalled call would otherwise block shutdown
            # for exactly as long as the timeout was meant to avoid.
            pool.shutdown(wait=False)

    def _connect(self) -> Chat:
        """Build the pinned chat model, once per client.

        Imported here rather than at module scope. `cli.py` imports every rung at
        module level, so a top-level framework import would break `faultloc
        --help` for anyone who installed without the extra.
        """
        if self._client is not None:
            return self._client

        try:
            from langchain_openrouter import ChatOpenRouter
        except ImportError as missing:  # pragma: no cover -- environment, not logic
            raise RuntimeError(
                "agent support is an optional extra; install it with `uv sync --extra agent`"
            ) from missing

        # The whole tag, suffix included, exactly as `llm.py` sends it. The
        # suffix is the quantization: `deepinfra/bf16` and `deepinfra` are
        # different serves, and ADR-0008's second amendment exists because a
        # model ID alone does not determine the number a run reports.
        chat = ChatOpenRouter(
            model=self.model.name,
            openrouter_provider={"only": [self.model.provider], "allow_fallbacks": False},
            reasoning=self.model.reasoning,
            max_tokens=self.max_tokens,
            openrouter_api_key=api_key(),
            # NO `request_timeout` HERE, and that is deliberate. Setting it is
            # what makes this client hang. Measured: `request_timeout=10` did not
            # return after 60 seconds, six times its own value, while the same
            # call without it answers in 1.3s and a raw urllib request to the same
            # endpoint answers in 1.7s. So the parameter does not bound a request,
            # it breaks one.
            #
            # This was added to fix a hang and caused a worse one. The original
            # 49-minute stall is real, and the bound now lives in `_send`, which
            # runs the call in a worker thread and abandons it. That works because
            # it needs nothing from the library.
            # `max_retries` defaults to 2, so the framework was retrying beneath
            # `_is_retryable`, which is the thing that decides what may be
            # retried. Two layers of retry means a 400 gets attempted three times
            # and the backoff is not the one this module reasons about.
            max_retries=0,
        )
        self._client = chat.bind_tools(self.tools) if self.tools else chat
        return self._client


def _reply_from(message: Any) -> AgentReply:
    """Pull an `AgentReply` out of whatever the framework returned.

    Every field is read from the reply. Nothing is computed from a price list,
    and nothing is inferred from the request.
    """
    metadata = getattr(message, "response_metadata", {}) or {}
    usage = getattr(message, "usage_metadata", {}) or {}
    output_details = usage.get("output_token_details", {}) or {}

    content = message.content if isinstance(message.content, str) else str(message.content)

    return AgentReply(
        text=content,
        tool_calls=tuple(getattr(message, "tool_calls", ()) or ()),
        cost_usd=float(metadata.get("cost", 0.0) or 0.0),
        finish_reason=str(metadata.get("finish_reason", "") or ""),
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        reasoning_tokens=int(output_details.get("reasoning", 0) or 0),
        fingerprint=str(metadata.get("system_fingerprint", "") or ""),
    )
