"""Rung 4 end to end, with a scripted model and a real bare clone.

The two properties that decide whether M5's number means anything are asserted
here. The warm start must match rung 3's payload byte for byte, or the delta stops
being attributable. And every failure that still yields a ranking must be counted,
or a broken run publishes as a null result.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import Fixture

from faultloc.agent_answer import SUBMIT_RANKING_SCHEMA
from faultloc.agent_client import AgentClient
from faultloc.agent_tools import READ_FILE_SCHEMA
from faultloc.dataset.models import Instance
from faultloc.llm import MODELS
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.agent import AgentRung
from faultloc.rungs.rerank import LlmRerankRung, render_candidates

CANDIDATES = ("pkg/core.py", "pkg/util.py")


class Reply:
    def __init__(
        self, content: str = "", tool_calls: list | None = None, cost: float = 0.001
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.response_metadata = {"cost": cost, "finish_reason": "stop"}
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 5}


class Scripted:
    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.prompts: list[Any] = []

    def invoke(self, messages: Any) -> Any:
        self.prompts.append(messages)
        return self.replies.pop(0)


class FixedCandidates:
    """Stands in for the Hybrid rung, so no index is needed."""

    name = "hybrid"

    def __init__(self, *paths: str) -> None:
        self.paths = paths

    def predict(self, instance: Instance) -> Prediction:
        if not self.paths:
            return Prediction(
                instance_id=instance.instance_id,
                rung=self.name,
                ranked_files=(),
                stop_condition=StopCondition.NO_CANDIDATES,
                latency_s=0.0,
            )
        return Prediction(
            instance_id=instance.instance_id,
            rung=self.name,
            ranked_files=self.paths,
            stop_condition=StopCondition.ANSWERED,
            latency_s=0.0,
        )


def evidence(_instance: Instance, head: Any) -> dict[str, str]:
    return {path: f"snippet for {path}" for path in head}


def instance(repo: Fixture) -> Instance:
    return Instance(
        instance_id="acme__widget-1",
        repo=repo.repo,
        base_commit=repo.first,
        issue_text="TypeError in pkg.core.first",
        ground_truth_files=("pkg/core.py",),
    )


def submit(*paths: str) -> dict:
    return {"name": "submit_ranking", "args": {"paths": list(paths)}, "id": "s1"}


def rung(
    repo: Fixture, *replies: Any, candidates: tuple = CANDIDATES, **overrides: Any
) -> AgentRung:
    return AgentRung(
        store=repo.store,
        candidates=FixedCandidates(*candidates),
        evidence=evidence,
        client=AgentClient(model=MODELS["deepseek-on"], chat=Scripted(*replies)),
        **overrides,
    )


class TestEndToEnd:
    def test_produces_a_prediction(self, repo: Fixture) -> None:
        engine = rung(repo, Reply(tool_calls=[submit("pkg/util.py", "pkg/core.py")]))

        prediction = engine.predict(instance(repo))

        assert prediction.rung == "agent"
        assert prediction.ranked_files == ("pkg/util.py", "pkg/core.py")
        assert prediction.stop_condition == StopCondition.ANSWERED

    def test_cost_is_this_instance_only_and_not_the_running_total(self, repo: Fixture) -> None:
        """Two Instances, because one cannot tell the two apart.

        After a single Instance the client's cumulative `spent_usd` and this
        Instance's own cost are the same number. Only the second Instance
        separates them, and a break test proved the one-Instance version of this
        test could not see the difference.
        """
        engine = rung(
            repo,
            Reply(tool_calls=[submit("pkg/core.py")], cost=0.002),
            Reply(tool_calls=[submit("pkg/util.py")], cost=0.003),
        )

        first = engine.predict(instance(repo))
        second = engine.predict(instance(repo))

        assert first.cost_usd == pytest.approx(0.002)
        assert second.cost_usd == pytest.approx(0.003)
        assert engine.spent_usd == pytest.approx(0.005)

    def test_reports_no_confidence(self, repo: Fixture) -> None:
        """ADR-0004 gives that job to the Calibrator at M7."""
        engine = rung(repo, Reply(tool_calls=[submit("pkg/core.py")]))

        assert engine.predict(instance(repo)).confidence is None

    def test_an_empty_candidate_set_never_calls_the_model(self, repo: Fixture) -> None:
        engine = rung(repo, candidates=())

        prediction = engine.predict(instance(repo))

        assert prediction.stop_condition == StopCondition.NO_CANDIDATES
        assert prediction.ranked_files == ()
        assert engine.no_candidates == 1


class TestTheWarmStart:
    def test_the_candidate_block_is_byte_identical_to_rung_3s(self, repo: Fixture) -> None:
        """The property the attributable delta rests on.

        Both rungs render the Candidate Set with the same function, so they cannot
        drift apart about what a candidate looks like. The instructions around the
        block differ on purpose, and ADR-0009 declares that as a confound the
        zero-tool cell prices.
        """
        engine = rung(repo, Reply(tool_calls=[submit("pkg/core.py")]))
        engine.predict(instance(repo))

        sent = str(engine.client.chat.prompts[0][0].content)
        shared = render_candidates(evidence(instance(repo), CANDIDATES), CANDIDATES)

        assert shared in sent

    def test_uses_the_same_renderer_as_rung_3(self, repo: Fixture) -> None:
        """Not merely the same output today. The same function, so a change to
        one rung's payload cannot silently leave the other behind."""
        reranker = LlmRerankRung(candidates=FixedCandidates(*CANDIDATES), evidence=evidence)
        shared = render_candidates(evidence(instance(repo), CANDIDATES), CANDIDATES)

        assert shared in reranker._prompt(instance(repo), CANDIDATES)

    def test_tells_the_agent_how_many_calls_it_has(self, repo: Fixture) -> None:
        engine = rung(repo, Reply(tool_calls=[submit("pkg/core.py")]), max_tool_calls=3)
        engine.predict(instance(repo))

        assert "at most 3 tool calls" in str(engine.client.chat.prompts[0][0].content)

    def test_invites_paths_that_were_never_candidates(self, repo: Fixture) -> None:
        """Without the invitation the agent has no reason to report the one thing
        rung 4 adds over rung 3."""
        engine = rung(repo, Reply(tool_calls=[submit("pkg/core.py")]))
        engine.predict(instance(repo))

        assert "not in the list" in str(engine.client.chat.prompts[0][0].content)


class TestTheZeroToolCell:
    def test_offers_no_read_tools_at_a_cap_of_zero(self, repo: Fixture) -> None:
        """ADR-0009's Ablation must answer at once. Offering a tool it cannot
        afford would spend a step on a refusal and measure the refusal."""
        engine = rung(repo, Reply(tool_calls=[submit("pkg/core.py")]), max_tool_calls=0)

        assert engine.schemas == (SUBMIT_RANKING_SCHEMA,)

    def test_offers_both_when_tools_are_allowed(self, repo: Fixture) -> None:
        engine = rung(repo, Reply(tool_calls=[submit("pkg/core.py")]), max_tool_calls=8)

        assert engine.schemas == (READ_FILE_SCHEMA, SUBMIT_RANKING_SCHEMA)

    def test_still_answers_with_no_tools(self, repo: Fixture) -> None:
        engine = rung(repo, Reply(tool_calls=[submit("pkg/util.py")]), max_tool_calls=0)

        prediction = engine.predict(instance(repo))

        assert prediction.ranked_files[0] == "pkg/util.py"


class TestCounters:
    def test_counts_an_off_list_path_that_exists(self, repo: Fixture) -> None:
        """The measure of whether rung 4 earned its rung."""
        engine = rung(repo, Reply(tool_calls=[submit("tests/test_core.py")]))

        engine.predict(instance(repo))

        assert engine.off_list == ["tests/test_core.py"]
        assert engine.hallucinated == []

    def test_counts_a_hallucinated_path(self, repo: Fixture) -> None:
        engine = rung(
            repo,
            Reply(tool_calls=[submit("pkg/ghost.py")]),
            Reply(tool_calls=[submit("pkg/core.py")]),
        )

        engine.predict(instance(repo))

        assert engine.hallucinated == ["pkg/ghost.py"]
        assert engine.guardrail_retries == 1

    def test_counts_a_fallback_when_the_agent_never_answers(self, repo: Fixture) -> None:
        """It scores like the rung below, so it must never be silent."""
        engine = rung(repo, Reply(content="thinking"), Reply(content="still thinking"))

        prediction = engine.predict(instance(repo))

        assert engine.fell_back == 1
        assert engine.unparseable == 1
        assert prediction.ranked_files == CANDIDATES

    def test_records_tool_reached_for_a_path_no_tool_surfaced(self, repo: Fixture) -> None:
        """A real path named from memory passes the guardrail and is not
        localization. The Verified Set predates the training cutoff."""
        engine = rung(repo, Reply(tool_calls=[submit("tests/test_core.py")]))

        engine.predict(instance(repo))

        assert engine.recalled == ["tests/test_core.py"]

    def test_does_not_record_tool_reached_for_a_path_a_tool_found(self, repo: Fixture) -> None:
        engine = rung(
            repo,
            Reply(
                tool_calls=[
                    {"name": "read_file", "args": {"path": "tests/test_core.py"}, "id": "r1"}
                ]
            ),
            Reply(tool_calls=[submit("tests/test_core.py")]),
        )

        engine.predict(instance(repo))

        assert engine.off_list == ["tests/test_core.py"]
        assert engine.recalled == []

    def test_records_the_call_count_per_instance(self, repo: Fixture) -> None:
        engine = rung(
            repo,
            Reply(tool_calls=[{"name": "read_file", "args": {"path": "pkg/core.py"}, "id": "r1"}]),
            Reply(tool_calls=[submit("pkg/core.py")]),
        )

        engine.predict(instance(repo))

        assert engine.calls_per_instance == [1]

    def test_truncation_is_read_and_not_accumulated(self, repo: Fixture) -> None:
        """The client's counter is already cumulative across the run. Adding it
        once per Instance would count the first Instance again on every one after.
        """
        engine = rung(repo, Reply(tool_calls=[submit("pkg/core.py")]))
        engine.predict(instance(repo))

        assert engine.truncated == engine.client.truncated


class TestTheEvaluationBudget:
    def test_stops_before_the_next_instance_breaks_the_cap(self, repo: Fixture) -> None:
        from faultloc.rungs.rerank import BudgetExceededError

        engine = rung(repo, Reply(tool_calls=[submit("pkg/core.py")]), budget_usd=0.0001)
        engine.client.spent_usd = 1.0

        with pytest.raises(BudgetExceededError):
            engine.predict(instance(repo))

    def test_counts_a_tool_the_model_invented(self, repo: Fixture) -> None:
        """Measured on the first real call: the agent asked for `search_content`
        with `directory` and `fileTypes` arguments, none of which exist.

        It costs a step, so an invented name quietly shrinks the Instance Budget.
        The first smoke run reported `degraded 0/0/0` while this had happened.
        """
        engine = rung(
            repo,
            Reply(tool_calls=[{"name": "search_content", "args": {"pattern": "x"}, "id": "u1"}]),
            Reply(tool_calls=[submit("pkg/core.py")]),
        )

        engine.predict(instance(repo))

        assert engine.unknown_tools == 1
