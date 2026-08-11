"""Rung 4's loop.

Every terminal path is driven by a scripted model, so no test touches the
network. What is asserted here is the thing ADR-0005 says the author must be able
to explain: where the budget is checked, how an edge selects a Stop Condition,
and what happens on a tool error.
"""

from __future__ import annotations

import itertools
from typing import Any

import pytest

from faultloc.agent_client import AgentClient
from faultloc.agent_graph import SUBMIT, AgentLoop, stop_condition, submitted_paths
from faultloc.agent_tools import ToolError, ToolResult
from faultloc.llm import MODELS
from faultloc.rungs import StopCondition

CANDIDATES = ("pkg/core.py", "pkg/util.py")


class Reply:
    """A model reply, in the shape `AgentClient` reads."""

    def __init__(self, content: str = "", tool_calls: list | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.response_metadata = {"cost": 0.0001, "finish_reason": "stop"}
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 5}


class Scripted:
    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls = 0

    def invoke(self, messages: Any) -> Any:
        self.calls += 1
        if not self.replies:
            raise AssertionError("the loop asked for more replies than the script holds")
        nxt = self.replies.pop(0)
        return nxt


def read(path: str = "pkg/core.py", **_: Any) -> ToolResult:
    return ToolResult(f"contents of {path}", paths=(path,))


_ids = itertools.count()


def call(name: str, **args: Any) -> dict:
    """A tool call with a UNIQUE id.

    Ids were derived from the tool name, so two `submit_ranking` calls in one
    transcript shared one id. That is not merely unrealistic -- it hid a real bug,
    because a dangling-call check keyed by id collapsed the two into the last one
    and then exempted it. A real provider issues a fresh id per call.
    """
    return {"name": name, "args": args, "id": f"c{next(_ids)}"}


def loop(*replies: Any, tools: dict | None = None, **overrides: Any) -> AgentLoop:
    client = AgentClient(model=MODELS["deepseek-on"], chat=Scripted(*replies))
    return AgentLoop(
        client=client, tools=tools if tools is not None else {"read_file": read}, **overrides
    )


class TestTerminalStates:
    def test_an_answer_ends_the_run(self) -> None:
        engine = loop(Reply(tool_calls=[call(SUBMIT, paths=["pkg/util.py"])]))

        state = engine.run("find it", CANDIDATES)

        assert stop_condition(state) == StopCondition.ANSWERED
        assert submitted_paths(state) == ("pkg/util.py",)

    def test_an_empty_candidate_set_never_calls_the_model(self) -> None:
        """`no_candidates` is separate from an empty ranking on purpose. "I had
        nothing to search" and "I searched and found nothing" are different
        failures, and one must not hide inside the other's score."""
        engine = loop()  # no replies at all: asking for one would raise

        state = engine.run("find it", ())

        assert stop_condition(state) == StopCondition.NO_CANDIDATES
        assert engine.client.calls == 0

    def test_the_clock_is_read_before_the_dispatch(self) -> None:
        """The order is the whole point. A run that has already overrun must not
        pay for one more call to discover it."""
        engine = loop(Reply(content="never reached"), timeout_s=-1.0)

        state = engine.run("find it", CANDIDATES)

        assert stop_condition(state) == StopCondition.TIMEOUT
        assert engine.client.calls == 0

    def test_spending_the_tool_budget_and_still_searching_is_budget_exceeded(self) -> None:
        """The agent gets its last chance, ignores it, and asks for tools again."""
        engine = loop(
            *[Reply(tool_calls=[call("read_file", path="a.py")]) for _ in range(4)],
            max_tool_calls=2,
        )

        state = engine.run("find it", CANDIDATES)

        assert stop_condition(state) == StopCondition.BUDGET_EXCEEDED
        assert state["tool_calls_used"] == 2

    def test_saying_nothing_usable_twice_falls_back_and_is_counted(self) -> None:
        """Not a Stop Condition of its own. ADR-0009 keeps the enum at five, and
        the assembly puts the Candidate Set behind whatever the agent said -- so
        this scores like the rung below and must never be silent."""
        engine = loop(Reply(content="I am thinking"), Reply(content="still thinking"))

        state = engine.run("find it", CANDIDATES)

        assert stop_condition(state) == StopCondition.ANSWERED
        assert submitted_paths(state) == ()
        assert engine.no_answer == 1


class TestTheBudget:
    def test_charges_each_call_and_not_each_turn(self) -> None:
        """Eight means eight tool results. A model that batches three calls into
        one turn is charged three, because three results enter the transcript."""
        batched = Reply(
            tool_calls=[
                call("read_file", path="a.py"),
                {"name": "read_file", "args": {"path": "b.py"}, "id": "c2"},
            ]
        )
        engine = loop(batched, Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]))

        state = engine.run("find it", CANDIDATES)

        assert state["tool_calls_used"] == 2

    def test_stops_dispatching_partway_through_a_batch_that_overruns(self) -> None:
        """A batch cannot spend more than the budget holds. The cap is a cap."""
        over = Reply(tool_calls=[call("read_file", path=f"{n}.py") for n in range(5)])
        engine = loop(
            over, Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]), max_tool_calls=2
        )

        state = engine.run("find it", CANDIDATES)

        assert state["tool_calls_used"] == 2
        assert engine.tool_calls == 2

    def test_a_rejected_call_still_costs_a_step(self) -> None:
        """It spent a step and taught the agent something, which is what the
        Instance Budget measures."""
        engine = loop(
            Reply(tool_calls=[call("read_file", path="invented.py")]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
            tools={"read_file": lambda **_: ToolResult("no such file", rejected=True)},
        )

        state = engine.run("find it", CANDIDATES)

        assert state["tool_calls_used"] == 1
        assert engine.tool_rejected == 1

    def test_submitting_does_not_cost_a_tool_call(self) -> None:
        """`submit_ranking` is a terminal action, not a sixth read-only tool.

        Free by routing, not by a check in the dispatcher: `_route` ends the run
        as soon as a submission appears, so the dispatcher never sees one. A break
        test established that, after this test first passed for the wrong reason.
        """
        engine = loop(Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]))

        state = engine.run("find it", CANDIDATES)

        assert state["tool_calls_used"] == 0
        assert engine.tool_calls == 0

    def test_a_submission_wins_a_turn_that_also_asks_for_tools(self) -> None:
        """A model can ask to read a file and answer in the same turn.

        The answer wins and the searches are dropped, because the agent answered.
        Documented here because it is a real consequence of the routing order
        rather than a decision anyone made explicitly.
        """
        mixed = Reply(
            tool_calls=[
                call("read_file", path="pkg/core.py"),
                {"name": SUBMIT, "args": {"paths": ["pkg/util.py"]}, "id": "c9"},
            ]
        )
        engine = loop(mixed)

        state = engine.run("find it", CANDIDATES)

        assert stop_condition(state) == StopCondition.ANSWERED
        assert submitted_paths(state) == ("pkg/util.py",)
        assert engine.tool_calls == 0

    def test_records_the_call_count_for_every_instance(self) -> None:
        """ADR-0009's revisit condition. If most Instances reach the cap, the cap
        produced the number rather than the agent."""
        engine = loop(
            Reply(tool_calls=[call("read_file", path="a.py")]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
        )
        engine.run("find it", CANDIDATES)

        assert engine.calls_per_instance == [1]


class TestTools:
    def test_a_tool_result_reaches_the_next_turn(self) -> None:
        engine = loop(
            Reply(tool_calls=[call("read_file", path="pkg/core.py")]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
        )

        state = engine.run("find it", CANDIDATES)
        transcript = " ".join(str(m.content) for m in state["messages"])

        assert "contents of pkg/core.py" in transcript

    def test_records_which_paths_a_tool_surfaced(self) -> None:
        """Feeds Tool-Reached, which separates a path the agent found from one it
        recalled. The Verified Set predates the training cutoff."""
        engine = loop(
            Reply(tool_calls=[call("read_file", path="pkg/util.py")]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/util.py"])]),
        )
        engine.run("find it", CANDIDATES)

        assert engine.surfaced == {"pkg/util.py"}

    def test_an_unknown_tool_name_is_reported_to_the_agent(self) -> None:
        """A model-caused mistake it can correct on its next call."""
        engine = loop(
            Reply(tool_calls=[call("grep_everything", q="x")]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
        )

        state = engine.run("find it", CANDIDATES)
        transcript = " ".join(str(m.content) for m in state["messages"])

        assert engine.unknown_tools == 1
        assert "No tool named `grep_everything`" in transcript
        assert stop_condition(state) == StopCondition.ANSWERED

    def test_an_infrastructure_error_ends_the_instance_loudly(self) -> None:
        """It must not arrive as an empty result. Across 244 Instances that would
        read as a thorough search that found nothing."""

        def broken(**_: Any) -> ToolResult:
            raise ToolError("clone is missing")

        engine = loop(
            Reply(tool_calls=[call("read_file", path="a.py")]), tools={"read_file": broken}
        )

        with pytest.raises(ToolError):
            engine.run("find it", CANDIDATES)


class TestTheLastChance:
    def test_a_spent_budget_gets_one_message_telling_it_to_answer(self) -> None:
        engine = loop(
            Reply(tool_calls=[call("read_file", path="a.py")]),
            Reply(tool_calls=[call("read_file", path="b.py")]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
            max_tool_calls=1,
        )

        state = engine.run("find it", CANDIDATES)

        assert engine.nudges == 1
        assert stop_condition(state) == StopCondition.ANSWERED
        assert submitted_paths(state) == ("pkg/core.py",)

    def test_the_last_chance_is_offered_exactly_once(self) -> None:
        """Without the flag the loop could ask forever."""
        engine = loop(
            Reply(content="thinking"),
            Reply(content="still thinking"),
            Reply(content="never asked for"),
        )

        engine.run("find it", CANDIDATES)

        assert engine.nudges == 1


class TestSubmittedPaths:
    def test_reads_the_most_recent_submission(self) -> None:
        engine = loop(
            Reply(tool_calls=[call("read_file", path="a.py")]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/util.py", "pkg/core.py"])]),
        )

        state = engine.run("find it", CANDIDATES)

        assert submitted_paths(state) == ("pkg/util.py", "pkg/core.py")

    def test_a_submission_with_no_paths_is_empty_and_not_an_error(self) -> None:
        """Unchecked here. Issue 05's guardrail and assembly decide what survives."""
        engine = loop(Reply(tool_calls=[call(SUBMIT, paths=[])]))

        assert submitted_paths(engine.run("find it", CANDIDATES)) == ()


class FakeRail:
    """A guardrail whose idea of existence is a fixed set."""

    def __init__(self, *present: str) -> None:
        self.present = set(present)

    def split(self, paths):
        kept = tuple(p for p in paths if p in self.present)
        absent = tuple(p for p in paths if p not in self.present)
        return kept, absent


class TestTheGuardrailInsideTheLoop:
    def test_a_valid_submission_passes_straight_through(self) -> None:
        engine = loop(
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
            guardrail=FakeRail("pkg/core.py"),
        )

        state = engine.run("find it", CANDIDATES)

        assert state["ranking"] == ("pkg/core.py",)
        assert engine.guardrail_retries == 0

    def test_an_absent_path_buys_one_retry_that_names_it(self) -> None:
        """Rejecting a path is only useful if the agent can then name another,
        which is why the guardrail runs inside the loop rather than after it."""
        engine = loop(
            Reply(tool_calls=[call(SUBMIT, paths=["ghost.py"])]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
            guardrail=FakeRail("pkg/core.py"),
        )

        state = engine.run("find it", CANDIDATES)
        transcript = " ".join(str(m.content) for m in state["messages"])

        assert engine.guardrail_retries == 1
        assert "ghost.py" in transcript
        assert state["ranking"] == ("pkg/core.py",)
        assert engine.hallucinated == ["ghost.py"]

    def test_the_retry_is_offered_exactly_once(self) -> None:
        """An agent that keeps naming files that do not exist would loop forever."""
        engine = loop(
            Reply(tool_calls=[call(SUBMIT, paths=["ghost.py"])]),
            Reply(tool_calls=[call(SUBMIT, paths=["phantom.py"])]),
            guardrail=FakeRail("pkg/core.py"),
        )

        state = engine.run("find it", CANDIDATES)

        assert engine.guardrail_retries == 1
        assert state["ranking"] == ()
        assert engine.hallucinated == ["ghost.py", "phantom.py"]

    def test_a_partly_valid_submission_keeps_the_survivors_and_still_retries(self) -> None:
        engine = loop(
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py", "ghost.py"])]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py", "pkg/util.py"])]),
            guardrail=FakeRail("pkg/core.py", "pkg/util.py"),
        )

        state = engine.run("find it", CANDIDATES)

        assert engine.guardrail_retries == 1
        assert state["ranking"] == ("pkg/core.py", "pkg/util.py")

    def test_an_off_list_path_that_exists_survives_the_guardrail(self) -> None:
        """The only route above the Candidate Set's 88.9% ceiling."""
        engine = loop(
            Reply(tool_calls=[call(SUBMIT, paths=["src/found.py"])]),
            guardrail=FakeRail("src/found.py"),
        )

        state = engine.run("find it", CANDIDATES)

        assert state["ranking"] == ("src/found.py",)
        assert engine.hallucinated == []

    def test_the_guardrail_never_fails_the_instance(self) -> None:
        """Every path rejected, and the run still ends `answered`.

        The assembly puts the Candidate Set behind the agent's order and every
        candidate exists by construction, so there is nothing for a terminal
        guardrail state to fire on. ADR-0009 keeps the enum at five.
        """
        engine = loop(
            Reply(tool_calls=[call(SUBMIT, paths=["ghost.py"])]),
            Reply(tool_calls=[call(SUBMIT, paths=["phantom.py"])]),
            guardrail=FakeRail("pkg/core.py"),
        )

        state = engine.run("find it", CANDIDATES)

        assert stop_condition(state) == StopCondition.ANSWERED

    def test_a_retry_does_not_spend_a_tool_call(self) -> None:
        """The guardrail's retry is not a search. Charging it would take a step
        away from the Instance Budget for a mistake the agent is fixing."""
        engine = loop(
            Reply(tool_calls=[call(SUBMIT, paths=["ghost.py"])]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
            guardrail=FakeRail("pkg/core.py"),
        )

        state = engine.run("find it", CANDIDATES)

        assert state["tool_calls_used"] == 0


class TestTheTranscriptStaysValid:
    """Every tool call the loop sends again must already have an answer.

    An OpenAI-compatible API rejects an assistant message whose tool calls have no
    matching tool results, with a 400 that no retry can fix. This arrived on the
    second Instance of the first real run, and none of the tests above could see
    it: the scripted client accepts any shape.

    The last `submit_ranking` is exempt. The run ends on it, so that transcript is
    never sent anywhere.
    """

    @staticmethod
    def dangling(state) -> set[str]:
        """Unanswered tool calls, exempting only the ones in the FINAL message.

        The exemption has to be that narrow. An earlier version exempted every
        `submit_ranking` call, which hid a real bug: the guardrail retry re-sent a
        transcript whose rejected submission had no answer, and the test could not
        see it because the exemption covered that call too.
        """
        from langchain_core.messages import AIMessage, ToolMessage

        asked: dict[str, int] = {}
        answered: set[str] = set()
        for position, message in enumerate(state["messages"]):
            if isinstance(message, AIMessage):
                for tc in message.tool_calls or []:
                    asked[tc["id"]] = position
            if isinstance(message, ToolMessage):
                answered.add(message.tool_call_id)

        final = len(state["messages"]) - 1
        return {i for i, position in asked.items() if i not in answered and position != final}

    def test_a_clipped_batch_answers_every_call_it_refused(self) -> None:
        over = Reply(tool_calls=[call("read_file", path=f"{n}.py") for n in range(5)])
        engine = loop(
            over, Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]), max_tool_calls=2
        )

        state = engine.run("find it", CANDIDATES)

        assert self.dangling(state) == set()
        assert state["tool_calls_used"] == 2

    def test_a_refused_call_says_why_and_costs_nothing(self) -> None:
        over = Reply(tool_calls=[call("read_file", path=f"{n}.py") for n in range(3)])
        engine = loop(
            over, Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]), max_tool_calls=1
        )

        state = engine.run("find it", CANDIDATES)
        transcript = " ".join(str(m.content) for m in state["messages"])

        assert "budget for this instance is spent" in transcript
        assert engine.tool_calls == 1

    def test_a_guardrail_retry_answers_the_submission_it_rejected(self) -> None:
        engine = loop(
            Reply(tool_calls=[call(SUBMIT, paths=["ghost.py"])]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
            guardrail=FakeRail("pkg/core.py"),
        )

        state = engine.run("find it", CANDIDATES)

        assert self.dangling(state) == set()

    def test_an_ordinary_run_leaves_nothing_dangling(self) -> None:
        engine = loop(
            Reply(tool_calls=[call("read_file", path="pkg/core.py")]),
            Reply(tool_calls=[call(SUBMIT, paths=["pkg/core.py"])]),
        )

        assert self.dangling(engine.run("find it", CANDIDATES)) == set()
