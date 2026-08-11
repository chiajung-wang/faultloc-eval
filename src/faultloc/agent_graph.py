"""Rung 4's loop: six nodes and five ways to stop.

[ADR-0005](../../docs/adr/0005-langgraph.md) chose LangGraph because rung 4 is
already a state machine, and its Consequences name the debt that choice carries:
the author must be able to describe the node, edge and state design without
reference to the framework. Here is that description.

**The state holds five things that matter.** The transcript, the Candidate Set the
run started from, how many tool calls have been spent, whether the agent has
already been told to finish, and the deadline. Everything else is derived.

**The loop is `think`, then maybe `act`, then `think` again.** `think` dispatches
one model call. `act` runs whatever tools that call asked for and appends their
results. Nothing else happens.

**The budget is checked at the top of `think`, before the dispatch.** The state
owns it, not the framework. A cap checked after a dispatch is a cap that already
spent the money, and ADR-0005 says so in as many words.

**A conditional edge out of `think` selects the terminal state.** It asks four
questions in order: has the clock run out, did the agent submit an answer, did it
ask for tools it can still afford, and has it already had its last chance. Each
answer leads to exactly one of the five Stop Conditions, or back into the loop.

**The agent gets one last chance and no more.** When the tool budget is spent, or
when a reply arrives with neither an answer nor a tool call, the loop appends one
message telling the agent to answer now. If the next reply still does not answer,
the run stops. Without that single flag the loop could ask forever.

**A submission goes to `check`, not straight out.** The Path Guardrail runs inside
the loop, because rejecting a path is only useful if the agent can then name a
different one. It gets one retry, for the same reason the last chance does.

The three nodes above the loop are `begin`, which refuses an Instance with nothing
to rank, `nudge`, and `finish`. Each exists because a conditional edge decides and
cannot write: every outcome that has to record something needs a node of its own.

`agent_answer.py` holds the guardrail itself and the assembly. This module decides
*when* they run.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from faultloc.agent_answer import REJECTED_PATHS, Guardrail
from faultloc.agent_client import AgentClient
from faultloc.agent_tools import ToolResult
from faultloc.rungs import StopCondition

#: Tool calls one Instance may spend. ADR-0009's Instance Budget. The cap counts
#: calls rather than turns, so eight means eight tool results, and a model that
#: batches three calls into one turn is charged three.
MAX_TOOL_CALLS = 8

#: Wall clock for one Instance. A backstop against a hang, not a control: on the
#: pinned route a tool step is 4 to 8 seconds and a full answer about 44, so a
#: budget of eight steps finishes far inside this. The PRD's original 120s would
#: have fired on ordinary variance instead.
TIMEOUT_S = 600.0

#: The name the model calls to answer. A terminal action, not a sixth read-only
#: tool, and it does not count against the tool-call cap -- otherwise the agent
#: would silently get seven search calls instead of eight.
SUBMIT = "submit_ranking"

#: The answer to a tool call the Instance Budget refused to run. It keeps the
#: transcript valid and tells the agent why nothing came back.
BUDGET_SPENT = "Not run: the tool-call budget for this instance is spent. Answer now."

FINISH_NOW = (
    "Stop searching and answer now. Call {submit} with every candidate path, most likely first."
)


class AgentState(TypedDict):
    """What the loop carries between nodes."""

    messages: Annotated[list, add_messages]
    candidates: tuple[str, ...]
    tool_calls_used: int
    nudged: bool
    stop: str
    ranking: tuple[str, ...]
    deadline: float
    #: The guardrail gets to reject once and ask again. Without the flag an agent
    #: that keeps naming files that do not exist would loop forever.
    guardrail_retried: bool
    #: Set by `check` for one hop, so the edge out of it can route without
    #: reading `stop`. `stop` names a Stop Condition, and a retry is not one.
    retry_now: bool


@dataclass
class AgentLoop:
    """The graph, plus the counters a run has to publish.

    Every counter here names a way the loop can finish while leaving the agent
    holding the ranking it was handed. M4 found three real bugs through counters
    like these rather than through tests, and each one produced a run that looked
    healthy in every metric except the one saying how often the model answered.
    """

    client: AgentClient
    tools: dict[str, Any]
    guardrail: Guardrail | None = None
    max_tool_calls: int = MAX_TOOL_CALLS
    timeout_s: float = TIMEOUT_S

    #: Counted, never absorbed.
    tool_calls: int = 0
    tool_rejected: int = 0
    tool_truncated: int = 0
    nudges: int = 0
    unknown_tools: int = 0
    #: Had its last chance and submitted nothing. Falls back to the Candidate Set
    #: order, which scores like the rung below, so it must never be silent.
    no_answer: int = 0
    #: Times the guardrail rejected a submission and asked again.
    guardrail_retries: int = 0
    #: Every path named that does not exist at `base_commit`. The catch rate
    #: CONTEXT.md promises, kept as paths rather than a count so the entry can
    #: show what a hallucinated path actually looks like.
    hallucinated: list[str] = field(default_factory=list)
    surfaced: set[str] = field(default_factory=set)
    calls_per_instance: list[int] = field(default_factory=list)
    #: What the Instance just run cost to *produce*, cached replies included.
    #: Distinct from `AgentClient.spent_usd`, which counts money leaving the
    #: account now and is cumulative across the whole run. A Prediction states
    #: what a reader would pay to reproduce it, so a replayed step still counts.
    run_cost_usd: float = 0.0

    def run(self, prompt: str, candidates: Sequence[str]) -> AgentState:
        """One Instance, from the warm-start prompt to a Stop Condition."""
        graph = self._build()
        self.run_cost_usd = 0.0
        state: AgentState = {
            "messages": [HumanMessage(content=prompt)],
            "candidates": tuple(candidates),
            "tool_calls_used": 0,
            "nudged": False,
            "stop": "",
            "ranking": (),
            "deadline": time.monotonic() + self.timeout_s,
            "guardrail_retried": False,
            "retry_now": False,
        }
        # `recursion_limit` is the framework's own guard, and it is not the
        # budget. Two graph steps per tool call, plus the nudge and the final
        # answer, with room to spare so the Instance Budget is what actually
        # stops the loop.
        final = graph.invoke(state, {"recursion_limit": 4 * self.max_tool_calls + 12})
        self.calls_per_instance.append(final["tool_calls_used"])
        return final  # type: ignore[return-value]

    def _build(self):
        graph = StateGraph(AgentState)
        graph.add_node("begin", self._begin)
        graph.add_node("think", self._think)
        graph.add_node("act", self._act)
        graph.add_node("nudge", self._nudge)
        graph.add_node("finish", self._finish)
        graph.add_node("check", self._check)

        graph.add_edge(START, "begin")
        graph.add_conditional_edges(
            "begin", lambda s: END if s["stop"] else "think", {END: END, "think": "think"}
        )
        graph.add_conditional_edges(
            "think",
            self._route,
            {"check": "check", "act": "act", "nudge": "nudge", "finish": "finish", END: END},
        )
        graph.add_conditional_edges(
            "check",
            lambda s: "think" if s["retry_now"] else END,
            {"think": "think", END: END},
        )
        graph.add_edge("act", "think")
        graph.add_edge("nudge", "think")
        graph.add_edge("finish", END)
        return graph.compile()

    def _begin(self, state: AgentState) -> dict:
        """Refuse an Instance with nothing to rank.

        `no_candidates` is separate from an empty ranking on purpose. "I had
        nothing to search" and "I searched and found nothing worth ranking" are
        different failures, and collapsing them hides the first inside the
        second's score.
        """
        if not state["candidates"]:
            return {"stop": StopCondition.NO_CANDIDATES}
        return {}

    def _think(self, state: AgentState) -> dict:
        """One model call, with the budget checked first.

        The order is the whole point. The clock is read before the dispatch, so a
        run that has already overrun does not pay for one more call to discover
        it.
        """
        if time.monotonic() > state["deadline"]:
            return {"stop": StopCondition.TIMEOUT}

        reply = self.client.invoke(state["messages"])
        self.run_cost_usd += reply.cost_usd
        return {"messages": [AIMessage(content=reply.text, tool_calls=list(reply.tool_calls))]}

    def _route(self, state: AgentState) -> str:
        """Which way out of `think`. This function decides, and changes nothing.

        A conditional edge cannot write to the state, so every outcome that has to
        record something is a node. `nudge` appends the last-chance message.
        `finish` sets the Stop Condition. Getting that wrong is how a first draft
        of this file both failed to nudge and never set `budget_exceeded`.

        Four questions in order, and the order matters. A run that has overrun
        reports `timeout` even when the reply that arrived was a good answer,
        because that answer cost more than the Instance was allowed to spend.
        """
        if state["stop"]:
            return END

        calls = list(getattr(state["messages"][-1], "tool_calls", ()) or ())

        if any(c.get("name") == SUBMIT for c in calls):
            return "check"

        searches = [c for c in calls if c.get("name") != SUBMIT]
        if searches and state["tool_calls_used"] < self.max_tool_calls:
            return "act"

        return "nudge" if not state["nudged"] else "finish"

    def _nudge(self, state: AgentState) -> dict:
        """One message telling the agent to answer, and a flag so it is the last.

        Reached when the tool budget is spent, or when a reply carried neither an
        answer nor a tool call. Without the flag this loop could ask forever.

        **It must answer any tool call it is about to refuse.** This node is reached
        precisely when the budget is already spent, so `act` never runs and nothing
        else will reply to the call the agent just made. Leaving it unanswered is a
        400 from the provider: "insufficient tool messages following tool_calls
        message". That is how the second three-Instance run died, at the ninth call
        of an eight-call budget.
        """
        self.nudges += 1
        refused = [
            ToolMessage(content=BUDGET_SPENT, tool_call_id=call.get("id", ""))
            for call in getattr(state["messages"][-1], "tool_calls", ()) or ()
            if call.get("name") != SUBMIT
        ]
        return {
            "messages": [*refused, HumanMessage(content=FINISH_NOW.format(submit=SUBMIT))],
            "nudged": True,
        }

    def _check(self, state: AgentState) -> dict:
        """The Path Guardrail. Existence only, and never membership.

        A path the Candidate Set does not hold is kept if it exists, because
        reaching past the list is the only thing rung 4 adds over rung 3. Issue 01
        measured the stakes: of 6 Off-List Paths recovered from a cached rung-3
        cell, 5 existed. Rejecting them as hallucinations would have discarded
        five real files.

        An absent path buys one retry, quoted back so the agent knows which ones.
        After that the survivors stand, and the run keeps going with whatever is
        left. It cannot fail the Instance, because the assembly puts the Candidate
        Set behind the agent's order and every candidate exists by construction.
        """
        submitted = submitted_paths(state)

        if self.guardrail is None:
            return {"ranking": submitted, "retry_now": False}

        kept, absent = self.guardrail.split(submitted)
        self.hallucinated.extend(absent)

        if absent and not state["guardrail_retried"]:
            self.guardrail_retries += 1
            # The submission is a tool call, so it needs a tool result before the
            # transcript can be sent again. Same 400 as a clipped batch, reached by
            # a different path.
            return {
                "messages": [
                    ToolMessage(
                        content=REJECTED_PATHS.format(paths=", ".join(absent), submit=SUBMIT),
                        tool_call_id=_submit_call_id(state),
                    )
                ],
                "guardrail_retried": True,
                "retry_now": True,
            }

        return {"ranking": kept, "retry_now": False}

    def _finish(self, state: AgentState) -> dict:
        """The agent had its last chance and still did not answer.

        Two different failures end here, and they get different Stop Conditions.
        An agent still asking for tools it cannot afford hit the Instance Budget.
        An agent that simply said nothing usable did not, so the run stays
        `answered` and falls back to the Candidate Set order -- counted, because a
        silent fallback scores like the rung below and reads as a null result.
        """
        calls = list(getattr(state["messages"][-1], "tool_calls", ()) or ())
        if any(c.get("name") != SUBMIT for c in calls):
            return {"stop": StopCondition.BUDGET_EXCEEDED}

        self.no_answer += 1
        return {}

    def _act(self, state: AgentState) -> dict:
        """Run the tools the last reply asked for, and append their results.

        Each call is charged, including one that the agent got wrong. A rejected
        call spent a step and taught the agent something, which is exactly what
        the Instance Budget is measuring.

        This node never sees a `submit_ranking` call. `_route` ends the run as
        soon as one appears, so a submission costs no tool call -- by routing
        rather than by a check here. An earlier draft carried that check anyway,
        and a break test proved it unreachable.
        """
        last = state["messages"][-1]
        results = []
        spent = 0

        for call in getattr(last, "tool_calls", ()) or ():
            # EVERY call gets a result, including one the cap refuses to run. An
            # OpenAI-compatible API rejects an assistant message whose tool calls
            # have no matching tool results, and a clipped batch left exactly that
            # dangling. It arrived as a 400 on the second Instance of the first
            # real run, and the fake client in the tests could not see it.
            if state["tool_calls_used"] + spent >= self.max_tool_calls:
                results.append(ToolMessage(content=BUDGET_SPENT, tool_call_id=call.get("id", "")))
                continue

            spent += 1
            results.append(
                ToolMessage(content=self._dispatch(call), tool_call_id=call.get("id", ""))
            )

        return {"messages": results, "tool_calls_used": state["tool_calls_used"] + spent}

    def _dispatch(self, call: dict) -> str:
        """One tool call, counted, with an unknown name reported to the agent."""
        self.tool_calls += 1
        name = call.get("name", "")
        tool = self.tools.get(name)

        if tool is None:
            self.unknown_tools += 1
            return f"No tool named `{name}`. Available: {', '.join(sorted(self.tools))}."

        result = tool(**(call.get("args") or {}))
        if not isinstance(result, ToolResult):  # pragma: no cover -- guards a wiring mistake
            raise TypeError(f"tool {name} returned {type(result).__name__}, not ToolResult")

        self.tool_rejected += result.rejected
        self.tool_truncated += result.truncated
        self.surfaced.update(result.paths)
        return result.text


def submitted_paths(state: AgentState) -> tuple[str, ...]:
    """The paths the agent asked to publish, in the order it gave them.

    Unchecked. Issue 05's Path Guardrail decides which of them exist, and the
    assembly decides where they sit.
    """
    for message in reversed(state["messages"]):
        for call in getattr(message, "tool_calls", ()) or ():
            if call.get("name") == SUBMIT:
                paths = (call.get("args") or {}).get("paths") or []
                return tuple(str(p) for p in paths)
    return ()


def _submit_call_id(state: AgentState) -> str:
    """The id of the most recent `submit_ranking` call, so a reply can answer it."""
    for message in reversed(state["messages"]):
        for call in getattr(message, "tool_calls", ()) or ():
            if call.get("name") == SUBMIT:
                return str(call.get("id", ""))
    return ""


def stop_condition(state: AgentState) -> str:
    """The one terminal state this run ended in.

    `answered` is the default rather than a special case. Every path that reaches
    the end of the loop without a clock or candidate failure has *a* ranking,
    because the assembly keeps the Candidate Set behind whatever the agent said.
    A run that failed to answer is counted, not given a state of its own.
    """
    return state["stop"] or StopCondition.ANSWERED
