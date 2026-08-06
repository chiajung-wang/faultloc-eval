"""Rung 3: an LLM reorders the Candidate Set in natural language.

The first rung that spends money, and the first whose number a reader cannot
regenerate from a commit alone.

Issue 01 sharpened what it is for. The Candidate Set holds a ground-truth file
in its top 20 for 88.9% of instances and the best free rung picks one 45.5% of
the time, so the gap is in *choosing*, not in retrieval. Rung 2.6 then measured
that reading the issue and one candidate together -- a cross-encoder -- is
worse than free rank fusion. What is left to test is whether reasoning over the
whole list at once, in language, does better.

The payload is ADR-0008's and identical to rung 2.6's: each candidate is its
path plus its Evidence Chunk. Only the mechanism differs, which is the whole
point of the two rungs sitting next to each other.

**Every failure path is counted rather than absorbed.** A model that returns
nothing, or truncates, or names files that were never candidates, still leaves
this rung with *a* ranking -- the one it was given. That degrades silently into
fusion's order, which would publish as "the model did not help" when in fact
the model never answered.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from faultloc.dataset.models import Instance
from faultloc.llm import MODELS, Model, Response
from faultloc.llm import call as call_openrouter
from faultloc.repos import RepoStore
from faultloc.rungs import Prediction, Rung, StopCondition
from faultloc.rungs.cross_encoder import TOP_K, EvidenceSource
from faultloc.rungs.hybrid import HybridRung

#: Output budget per call, sized from measurement rather than from a guess at a
#: trivial prompt. On the real prompt, measured maxima are 8,192 for gpt-oss at
#: high effort, 3,723 for DeepSeek reasoning, and 229 with reasoning disabled.
#:
#: The first value here was 4,000, chosen after a *toy* prompt showed 50 tokens
#: was too few. On the real one that truncated 37 of the ladder row's first 40
#: replies -- and because a truncated reply degrades to the input ranking, the
#: run was quietly reproducing fusion's order while looking like it worked.
#: Roughly double the observed maximum, so ordinary variance cannot reach it.
MAX_TOKENS = 16000

#: ADR-0008's per-run cap, raised from $1.50 when gpt-oss moved to Cerebras:
#: 10x the speed costs 5x the tokens' price, putting that cell near $1.29 on a
#: single-call estimate. A cap that the expected cost sits just under is a cap
#: that aborts on ordinary variance. Checked against spend already incurred, so
#: the run stops rather than reporting an overspend once it is too late.
BUDGET_USD = 2.00

PROMPT = """\
A bug was reported against a Python repository. Below are {n} candidate source \
files, each with the snippet that a retriever matched against the report. \
Exactly one of them is most likely the file that must change.

Rank all {n} candidates from most to least likely. Reply with the file paths \
only, one per line, most likely first. No numbering, no commentary, no paths \
that are not in the list.

## Bug report

{issue}

## Candidates

{candidates}
"""


class BudgetExceededError(RuntimeError):
    """The run has spent its cap. Raised rather than returned.

    A partial run is not the benchmark -- it is scored on a different instance
    set, exactly what `--limit` refuses to publish for. Stopping loudly is the
    only outcome that cannot end up in `RESULTS.md` looking comparable.
    """


class LlmRerankRung:
    """An LLM reorders the top K, with everything below left as fusion had it."""

    name = "rerank"

    def __init__(
        self,
        store: RepoStore | None = None,
        *,
        candidates: Rung | None = None,
        evidence: EvidenceSource | None = None,
        call: Callable[[str], Response] | None = None,
        model: Model = MODELS["gpt-oss-high"],
        budget_usd: float = BUDGET_USD,
        top_k: int = TOP_K,
    ) -> None:
        self.candidates = candidates or HybridRung(store)
        self.evidence = evidence or self.candidates.lexical.evidence
        self.model = model
        self.budget_usd = budget_usd
        self.top_k = top_k
        self._call = call or (lambda prompt: call_openrouter(model, prompt, max_tokens=MAX_TOKENS))

        #: Counted, not absorbed. Each is a way the rung can look like a null
        #: result while actually having failed.
        self.spent_usd = 0.0
        self.calls = 0
        self.unparseable = 0
        self.truncated = 0
        self.off_list = 0

    def predict(self, instance: Instance) -> Prediction:
        started = time.perf_counter()
        self._refuse_if_the_next_call_would_break_the_cap()

        base = self.candidates.predict(instance)
        if not base.ranked_files:
            return self._prediction(instance, (), StopCondition.NO_CANDIDATES, started, 0.0)

        head = base.ranked_files[: self.top_k]
        tail = base.ranked_files[self.top_k :]

        response = self._call(self._prompt(instance, head))
        self.spent_usd += response.cost_usd
        self.calls += 1

        if response.truncated:
            self.truncated += 1

        ordered = self._parse(response.text, head)
        if not ordered:
            self.unparseable += 1
            ordered = head

        return self._prediction(
            instance,
            tuple(ordered) + tail,
            StopCondition.ANSWERED,
            started,
            response.cost_usd,
        )

    def _refuse_if_the_next_call_would_break_the_cap(self) -> None:
        """Stop *before* exceeding, not after.

        A cap checked as `spent >= budget` always overshoots by one call, which
        on the expensive cell is most of a dollar. The next call is priced at
        the mean of the calls so far -- the only estimate available, and good
        enough because every instance sends a prompt of the same shape.
        """
        if not self.calls:
            return
        projected = self.spent_usd + self.spent_usd / self.calls
        if projected > self.budget_usd:
            raise BudgetExceededError(
                f"spent ${self.spent_usd:.2f} over {self.calls} calls; the next would reach "
                f"${projected:.2f} against a ${self.budget_usd:.2f} cap. Run stopped."
            )

    def _prompt(self, instance: Instance, head: Sequence[str]) -> str:
        chunks = self.evidence(instance, head)
        rendered = "\n\n".join(
            f"### {path}\n{chunks.get(path) or '(no snippet available)'}" for path in head
        )
        return PROMPT.format(n=len(head), issue=instance.issue_text, candidates=rendered)

    def _parse(self, text: str, head: Sequence[str]) -> list[str]:
        """The model's order, restricted to real candidates and completed.

        Matching is by exact line rather than by substring search: a reply
        mentioning `pkg/core.py` inside a sentence has not ranked it, and
        treating prose as a ranking would manufacture an answer the model did
        not give. Candidates the model left out keep their input order at the
        back -- dropping them would shrink the list the ceiling was measured
        on, and reordering them would invent a judgement.
        """
        wanted = set(head)
        ordered: list[str] = []
        for line in text.splitlines():
            candidate = line.strip().strip("`").lstrip("-*0123456789. ").strip()
            if not candidate:
                continue
            if candidate in wanted:
                if candidate not in ordered:
                    ordered.append(candidate)
            elif "/" in candidate or candidate.endswith(".py"):
                # Looks like a path and was never a candidate. Prose lines are
                # left alone: counting them would measure the model's manners
                # rather than its hallucinations.
                self.off_list += 1

        if not ordered:
            return []
        return ordered + [path for path in head if path not in ordered]

    def _prediction(
        self,
        instance: Instance,
        paths: tuple[str, ...],
        stop_condition: str,
        started: float,
        cost_usd: float,
    ) -> Prediction:
        return Prediction(
            instance_id=instance.instance_id,
            rung=self.name,
            ranked_files=paths,
            stop_condition=stop_condition,
            latency_s=time.perf_counter() - started,
            cost_usd=cost_usd,
        )
