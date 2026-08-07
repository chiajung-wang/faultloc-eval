"""Model responses on disk, so a dead run does not have to be re-bought.

A dev-split cell is 244 sequential API calls over hours. Twice in one day a run
died most of the way through -- at instance 110 and at instance 40 -- and each
time everything spent was gone, because predictions lived only in a list in
memory. The ladder row is a ten-hour run.

With this, re-running a dead cell replays what it already paid for and calls the
API only for what is missing. Resume is a side effect of caching rather than a
feature of its own.

**This is not the response-committing that [ADR-0008](../../docs/adr/0008-llm-rerank.md)
rejected.** That proposal put responses in the repository to support a
`test_is_deterministic` claim the system cannot honour. This cache is local,
gitignored, and claims nothing: a rung-3 entry still says its variance is
unmeasured. It only avoids paying twice for the same question.

The key covers everything that changes the answer -- model, route, reasoning
setting, token budget, prompt -- because a plausible response with the wrong
provenance is worse than a crash. `EmbeddingIndex` refuses a mismatched index
for the same reason.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from faultloc.llm import Model, Response

DEFAULT_RESPONSE_CACHE = Path("data/cache/responses")


class ResponseCache:
    """Responses keyed by everything that determines them."""

    def __init__(self, root: Path = DEFAULT_RESPONSE_CACHE) -> None:
        self.root = Path(root)

    def get(self, model: Model, prompt: str, max_tokens: int) -> Response | None:
        """The stored response, or `None` if there is not one to trust.

        A corrupt entry -- a half-written file from a killed run -- is a miss.
        It costs one API call; raising would cost the run.
        """
        path = self._path(model, prompt, max_tokens)
        if not path.is_file():
            return None

        try:
            stored = json.loads(path.read_text())
            return Response(**stored["response"])
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def put(self, model: Model, prompt: str, max_tokens: int, response: Response) -> None:
        """Store a response, written-then-renamed so a kill cannot leave half.

        The key's components are stored alongside the response. They are not
        read back -- the hash already separates them -- but a cache nobody can
        inspect is a cache nobody can debug.
        """
        path = self._path(model, prompt, max_tokens)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": model.name,
            "provider": model.provider,
            "reasoning": model.reasoning,
            "max_tokens": max_tokens,
            "response": asdict(response),
        }

        # Per-process temp name: four cells run at once against this directory,
        # and a shared name lets one process rename another's partial file.
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(path)

    def _path(self, model: Model, prompt: str, max_tokens: int) -> Path:
        digest = hashlib.sha256(
            json.dumps(
                [model.name, model.provider, model.reasoning, max_tokens, prompt],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        # Sharded by the first two characters: one directory holding a thousand
        # files per cell is slow to list and unpleasant to inspect.
        return self.root / digest[:2] / f"{digest}.json"
