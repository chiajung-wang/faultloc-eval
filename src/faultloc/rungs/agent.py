"""Rung 4: a tool-using loop that can go looking for what retrieval missed.

The rung that ADR-0003 named before any of the ladder existed, and the first one
whose job is not to rank better.

**Why it exists at all.** The Candidate Set holds a Ground-Truth File in its top 20
for 88.9% of Instances, so 27 of 244 hold no correct answer anywhere in the list.
No reranker can ever be right on those, and `sphinx` proves it: all four rung-3
cells score exactly 63.6% there, which is exactly its own hit@20.

**Whether that is reachable was measured before this was built.** Issue 01 found
`git grep` reaches a Ground-Truth File for 59.3% of the missed Instances within a
30-hit cap, so a tool-using rung raises the ceiling from 88.9% to about 95.5%.

**It starts warm.** The issue text and the same twenty candidates with the same
Evidence Chunks that rung 3 receives, rendered by the same function. Only the loop
and the tools are new, which is what makes the delta attributable.

**It reports no Confidence.** ADR-0004 gives that job to the Calibrator at M7.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from faultloc.agent_answer import SUBMIT_RANKING_SCHEMA, Answer, Guardrail, assemble
from faultloc.agent_client import AgentCache, AgentClient
from faultloc.agent_graph import MAX_TOOL_CALLS, TIMEOUT_S, AgentLoop, stop_condition
from faultloc.agent_tools import READ_FILE_SCHEMA, Toolbox
from faultloc.dataset.models import Instance
from faultloc.llm import MODELS, Model
from faultloc.repos import RepoStore
from faultloc.rungs import Prediction, Rung, StopCondition
from faultloc.rungs.cross_encoder import TOP_K, EvidenceSource
from faultloc.rungs.hybrid import HybridRung
from faultloc.rungs.rerank import BudgetExceededError, render_candidates

#: Output budget per step. Rung 3 uses 16,000, sized after 4,000 truncated 37 of
#: its first 40 replies. At rung 4 truncation fires once per *step* rather than
#: once per Instance, so a step that runs out of budget costs the whole Instance
#: its next decision. Kept at rung 3's figure until the smoke run measures the
#: real agent prompt -- issue 04 names that as the number to replace.
MAX_TOKENS = 16000

#: ADR-0009's Evaluation Budget. Checked against spend already incurred, so a run
#: stops before it breaks the cap rather than reporting an overspend afterwards.
BUDGET_USD = 12.00

PROMPT = """\
A bug was reported against a Python repository. Below are {n} candidate source \
files, each with the snippet that a retriever matched against the report. \
Exactly one file is most likely the one that must change.

The retriever is often wrong, and sometimes the file that must change is not in \
the list at all. You have read-only tools. Use them to check a candidate, and to \
follow imports and calls to files the retriever never returned.

When you are ready, call {submit} with every candidate path in order, most likely \
first. Include any file you found with the tools, even if it was not in the list. \
Every path must exist in the repository at this commit.

You may make at most {calls} tool calls.

## Bug report

{issue}

## Candidates

{candidates}
"""


class AgentRung:
    """A bounded loop with read-only tools, warm-started from the Candidate Set."""

    name = "agent"

    def __init__(
        self,
        store: RepoStore | None = None,
        *,
        candidates: Rung | None = None,
        evidence: EvidenceSource | None = None,
        model: Model = MODELS["deepseek-on"],
        client: AgentClient | None = None,
        cache: AgentCache | None = None,
        budget_usd: float = BUDGET_USD,
        top_k: int = TOP_K,
        max_tool_calls: int = MAX_TOOL_CALLS,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self.store = store or RepoStore()
        self.candidates = candidates or HybridRung(self.store)
        self.evidence = evidence or self.candidates.lexical.evidence
        self.model = model
        self.budget_usd = budget_usd
        self.top_k = top_k
        self.max_tool_calls = max_tool_calls
        self.timeout_s = timeout_s

        # No read-only tools at a cap of zero. ADR-0009's zero-tool cell must call
        # `submit_ranking` at once, and offering tools it cannot afford would spend
        # a step on a refusal and measure the refusal rather than the scaffolding.
        self.schemas = (
            (READ_FILE_SCHEMA, SUBMIT_RANKING_SCHEMA)
            if max_tool_calls
            else (SUBMIT_RANKING_SCHEMA,)
        )

        self.client = client or AgentClient(
            model=model, tools=self.schemas, max_tokens=MAX_TOKENS, cache=cache
        )

        #: Counted across the run, and every one of them names a way this rung can
        #: finish while holding the ranking it was handed.
        self.no_candidates = 0
        self.fell_back = 0
        self.off_list: list[str] = []
        self.hallucinated: list[str] = []
        self.recalled: list[str] = []
        self.calls_per_instance: list[int] = []
        self.guardrail_retries = 0
        self.unparseable = 0
        #: Tool names the model invented. Measured on the very first real call:
        #: the agent asked for `search_content` with `directory` and `fileTypes`
        #: arguments, none of which exist. It costs a step, so an invented name
        #: quietly shrinks the Instance Budget and has to be visible.
        self.unknown_tools = 0

    @property
    def spent_usd(self) -> float:
        return self.client.spent_usd

    @property
    def cache_hits(self) -> int:
        return self.client.cache_hits

    @property
    def truncated(self) -> int:
        """Steps that ran out of output budget, read from the client.

        A property rather than an accumulator. The client's own counter is already
        cumulative across the run, so adding it once per Instance would count the
        first Instance's truncations again on every Instance after it.
        """
        return self.client.truncated

    def predict(self, instance: Instance) -> Prediction:
        started = time.perf_counter()
        self._refuse_if_the_next_instance_would_break_the_cap()

        base = self.candidates.predict(instance)
        head = base.ranked_files[: self.top_k]
        if not head:
            self.no_candidates += 1
            return self._prediction(instance, (), StopCondition.NO_CANDIDATES, started, 0.0)

        loop = AgentLoop(
            client=self.client,
            tools={"read_file": Toolbox(self.store, instance).read_file},
            guardrail=Guardrail(self.store, instance),
            max_tool_calls=self.max_tool_calls,
            timeout_s=self.timeout_s,
        )
        state = loop.run(self._prompt(instance, head), head)
        answer = assemble(state["ranking"], base.ranked_files, loop.hallucinated)

        self._absorb(loop, answer)
        return self._prediction(
            instance,
            answer.ranking,
            stop_condition(state),
            started,
            loop.run_cost_usd,
        )

    def _absorb(self, loop: AgentLoop, answer: Answer) -> None:
        """Fold one Instance's counters into the run's.

        `recalled` is the Tool-Reached measurement. A predicted path that no tool
        ever surfaced was named from memory, and the Verified Set predates the
        training cutoff, so that is the difference between localization and
        recall.
        """
        self.off_list.extend(answer.off_list)
        self.hallucinated.extend(answer.hallucinated)
        self.fell_back += answer.fell_back
        self.unparseable += answer.fell_back
        self.guardrail_retries += loop.guardrail_retries
        self.unknown_tools += loop.unknown_tools
        self.calls_per_instance.extend(loop.calls_per_instance)
        self.recalled.extend(p for p in answer.off_list if p not in loop.surfaced)

    def _prompt(self, instance: Instance, head: Sequence[str]) -> str:
        """The warm start.

        The candidate block comes from rung 3's own renderer, so the two rungs
        cannot drift apart about what a candidate looks like. The instructions
        around it differ, and ADR-0009 declares that as a confound the zero-tool
        cell prices.
        """
        return PROMPT.format(
            n=len(head),
            submit=SUBMIT_RANKING_SCHEMA["function"]["name"],
            calls=self.max_tool_calls,
            issue=instance.issue_text,
            candidates=render_candidates(self.evidence(instance, head), head),
        )

    def _refuse_if_the_next_instance_would_break_the_cap(self) -> None:
        """Stop before spending, not after.

        A partial run is not the benchmark. It is scored on a different Instance
        set, which is exactly what `--limit` refuses to publish.
        """
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceededError(f"spent ${self.spent_usd:.2f} of ${self.budget_usd:.2f}")

    def _prediction(
        self,
        instance: Instance,
        paths: tuple[str, ...],
        stop: str,
        started: float,
        cost_usd: float,
    ) -> Prediction:
        return Prediction(
            instance_id=instance.instance_id,
            rung=self.name,
            ranked_files=paths,
            stop_condition=stop,
            latency_s=time.perf_counter() - started,
            cost_usd=cost_usd,
        )
