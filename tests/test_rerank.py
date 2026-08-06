"""Tests for rung 3, the LLM reranker.

The candidate supplier, the Evidence Chunk lookup and the model call are all
stubbed, so nothing reaches the network and nothing spends money. What is under
test is the composition, the parsing, and above all the failure paths -- a
rung that quietly degraded to its input would score exactly like rung 2.5 and
read as a null result rather than a broken run.
"""

from __future__ import annotations

import pytest

from faultloc.dataset.models import Instance
from faultloc.llm import Response
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.rerank import BudgetExceededError, LlmRerankRung

INSTANCE = Instance(
    instance_id="acme__widget-1",
    repo="acme/widget",
    base_commit="a" * 40,
    issue_text="core is broken",
    ground_truth_files=("pkg/core.py",),
)


class StubCandidates:
    name = "stub-candidates"

    def __init__(self, ranked: tuple[str, ...]) -> None:
        self.ranked = ranked

    def predict(self, instance: Instance) -> Prediction:
        stop = StopCondition.ANSWERED if self.ranked else StopCondition.NO_CANDIDATES
        return Prediction(
            instance_id=instance.instance_id,
            rung=self.name,
            ranked_files=self.ranked,
            stop_condition=stop,
            latency_s=0.01,
        )


def reply(text: str, *, cost: float = 0.001, finish: str = "stop") -> Response:
    return Response(
        text=text,
        cost_usd=cost,
        finish_reason=finish,
        provider="stub",
        output_tokens=10,
        reasoning_tokens=0,
    )


def rung(
    ranked: tuple[str, ...],
    responses: list[Response] | Response,
    *,
    budget: float = 1.50,
    top_k: int = 20,
) -> LlmRerankRung:
    queue = responses if isinstance(responses, list) else [responses]
    calls = iter(queue)
    return LlmRerankRung(
        candidates=StubCandidates(ranked),
        evidence=lambda instance, paths: {p: f"body of {p}" for p in paths},
        call=lambda prompt: next(calls),
        budget_usd=budget,
        top_k=top_k,
    )


class TestReranking:
    def test_reorders_by_the_order_the_model_lists(self) -> None:
        r = rung(("a.py", "b.py", "c.py"), reply("c.py\na.py\nb.py"))
        assert r.predict(INSTANCE).ranked_files == ("c.py", "a.py", "b.py")

    def test_leaves_everything_past_k_alone(self) -> None:
        """The Candidate Set's hit@20 ceiling only transfers if the tail is
        preserved -- otherwise rung 3 is scored on a different list from the
        one issue 01 measured."""
        r = rung(("a.py", "b.py", "c.py", "d.py"), reply("b.py\na.py"), top_k=2)
        assert r.predict(INSTANCE).ranked_files == ("b.py", "a.py", "c.py", "d.py")

    def test_candidates_the_model_omitted_keep_their_input_order_at_the_back(self) -> None:
        """A model that lists three of twenty has not ranked the other
        seventeen. Dropping them would shrink the list; reordering them would
        invent a judgement the model never made."""
        r = rung(("a.py", "b.py", "c.py"), reply("c.py"))
        assert r.predict(INSTANCE).ranked_files == ("c.py", "a.py", "b.py")

    def test_names_itself(self) -> None:
        assert rung(("a.py",), reply("a.py")).predict(INSTANCE).rung == "rerank"


class TestHallucinationAndMalformedReplies:
    def test_paths_that_were_never_candidates_are_ignored_and_counted(self) -> None:
        """CONTEXT.md's Path Guardrail is M5's version of this. The counting
        starts here, because a model naming files that do not exist is the
        first evidence for how big that problem is."""
        r = rung(("a.py", "b.py"), reply("pkg/invented.py\nb.py\na.py"))
        prediction = r.predict(INSTANCE)

        assert prediction.ranked_files == ("b.py", "a.py")
        assert r.off_list == 1

    def test_a_repeated_path_is_not_counted_as_off_list(self) -> None:
        """A model listing the same file twice has been sloppy, not
        hallucinatory. Counting it as an invented path would inflate the
        evidence M5's Path Guardrail is meant to be sized against."""
        r = rung(("a.py", "b.py"), reply("b.py\nb.py\na.py"))
        prediction = r.predict(INSTANCE)

        assert prediction.ranked_files == ("b.py", "a.py")
        assert r.off_list == 0

    def test_an_unparseable_reply_degrades_to_the_input_ranking_and_is_counted(self) -> None:
        r = rung(("a.py", "b.py"), reply("I cannot help with that."))
        prediction = r.predict(INSTANCE)

        assert prediction.ranked_files == ("a.py", "b.py")
        assert r.unparseable == 1

    def test_a_truncated_reply_is_counted_even_when_it_parses(self) -> None:
        """The failure that would masquerade as a null result. An answer cut
        off by the token budget still yields *some* ranking, so without this
        count a run that truncated everywhere would look like rung 2.5 and be
        read as 'the model did not help'."""
        r = rung(("a.py", "b.py"), reply("b.py\na", finish="length"))
        r.predict(INSTANCE)

        assert r.truncated == 1

    def test_degrading_still_reports_what_the_call_cost(self) -> None:
        """A wasted call is still a paid call. Reporting it as free would make
        the priced ladder understate exactly the runs that went wrong."""
        r = rung(("a.py",), reply("nonsense", cost=0.004))
        assert r.predict(INSTANCE).cost_usd == pytest.approx(0.004)


class TestBudget:
    def test_stops_the_run_rather_than_reporting_the_overspend_afterwards(self) -> None:
        r = rung(("a.py",), [reply("a.py", cost=0.9), reply("a.py", cost=0.9)], budget=1.50)
        r.predict(INSTANCE)

        with pytest.raises(BudgetExceededError):
            r.predict(INSTANCE)

    def test_the_cap_counts_spend_that_already_happened(self) -> None:
        r = rung(("a.py",), [reply("a.py", cost=2.0)], budget=1.50)
        r.predict(INSTANCE)
        assert r.spent_usd == pytest.approx(2.0)


class TestAccounting:
    def test_cost_is_read_from_the_response(self) -> None:
        r = rung(("a.py", "b.py"), reply("b.py\na.py", cost=0.0037))
        assert r.predict(INSTANCE).cost_usd == pytest.approx(0.0037)

    def test_latency_is_measured_end_to_end(self) -> None:
        assert rung(("a.py",), reply("a.py")).predict(INSTANCE).latency_s > 0

    def test_no_candidates_is_not_sent_to_the_model(self) -> None:
        r = rung((), [])
        prediction = r.predict(INSTANCE)

        assert prediction.stop_condition == StopCondition.NO_CANDIDATES
        assert prediction.cost_usd == 0.0


class TestPrompt:
    def test_the_prompt_carries_the_issue_and_every_candidate_with_its_evidence(self) -> None:
        seen: list[str] = []
        r = LlmRerankRung(
            candidates=StubCandidates(("a.py", "b.py")),
            evidence=lambda instance, paths: {p: f"def {p[0]}(): ..." for p in paths},
            call=lambda prompt: seen.append(prompt) or reply("a.py\nb.py"),
        )
        r.predict(INSTANCE)

        prompt = seen[0]
        assert "core is broken" in prompt
        assert "a.py" in prompt and "def a(): ..." in prompt
        assert "b.py" in prompt and "def b(): ..." in prompt


class TestResponseCache:
    """Resume, so a run that dies at 90% does not re-buy the first 90%."""

    def test_a_cached_instance_is_not_asked_again(self, tmp_path) -> None:
        from faultloc.response_cache import ResponseCache

        calls: list[str] = []

        def build() -> LlmRerankRung:
            return LlmRerankRung(
                candidates=StubCandidates(("a.py", "b.py")),
                evidence=lambda instance, paths: {p: "body" for p in paths},
                call=lambda prompt: calls.append(prompt) or reply("b.py\na.py"),
                cache=ResponseCache(tmp_path),
            )

        build().predict(INSTANCE)
        second = build()
        prediction = second.predict(INSTANCE)

        assert len(calls) == 1
        assert prediction.ranked_files == ("b.py", "a.py")
        assert second.cache_hits == 1

    def test_a_cached_hit_costs_the_budget_nothing(self, tmp_path) -> None:
        """The money was spent on the first run. Counting it again would abort
        a resume against a cap that has not actually been reached."""
        from faultloc.response_cache import ResponseCache

        def build() -> LlmRerankRung:
            return LlmRerankRung(
                candidates=StubCandidates(("a.py",)),
                evidence=lambda instance, paths: {p: "body" for p in paths},
                call=lambda prompt: reply("a.py", cost=0.9),
                cache=ResponseCache(tmp_path),
                budget_usd=1.0,
            )

        build().predict(INSTANCE)
        resumed = build()
        resumed.predict(INSTANCE)

        assert resumed.spent_usd == 0.0

    def test_a_cached_hit_still_reports_what_it_cost_to_produce(self, tmp_path) -> None:
        """The entry states what the number cost to make. A reader reproducing
        it pays that, whether or not this machine had it cached."""
        from faultloc.response_cache import ResponseCache

        def build() -> LlmRerankRung:
            return LlmRerankRung(
                candidates=StubCandidates(("a.py",)),
                evidence=lambda instance, paths: {p: "body" for p in paths},
                call=lambda prompt: reply("a.py", cost=0.0042),
                cache=ResponseCache(tmp_path),
            )

        build().predict(INSTANCE)
        prediction = build().predict(INSTANCE)

        assert prediction.cost_usd == pytest.approx(0.0042)

    def test_no_cache_means_no_caching(self) -> None:
        """Default off, so a test that forgets to pass one cannot quietly write
        into the real cache directory."""
        calls: list[str] = []
        rung = LlmRerankRung(
            candidates=StubCandidates(("a.py",)),
            evidence=lambda instance, paths: {p: "body" for p in paths},
            call=lambda prompt: calls.append(prompt) or reply("a.py"),
        )
        rung.predict(INSTANCE)
        rung.predict(INSTANCE)

        assert len(calls) == 2
        assert rung.cache_hits == 0
