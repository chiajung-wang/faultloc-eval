"""Tests for the fusion rung.

Both constituent rungs are stubbed, so nothing loads a model or reads an
index. What is under test is the composition -- that fusion happens, that
costs add, and that an empty result from one retriever is not mistaken for a
broken pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

from faultloc.dataset.models import Instance
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.hybrid import HybridRung

INSTANCE = Instance(
    instance_id="acme__widget-1",
    repo="acme/widget",
    base_commit="a" * 40,
    issue_text="core is broken",
    ground_truth_files=("pkg/core.py",),
)


@dataclass
class StubRung:
    """A retriever with a fixed answer."""

    name: str
    ranked: tuple[str, ...]
    cost_usd: float = 0.0

    def predict(self, instance: Instance) -> Prediction:
        stop = StopCondition.ANSWERED if self.ranked else StopCondition.NO_CANDIDATES
        return Prediction(
            instance_id=instance.instance_id,
            rung=self.name,
            ranked_files=self.ranked,
            stop_condition=stop,
            latency_s=0.01,
            cost_usd=self.cost_usd,
        )


def hybrid(lexical: tuple[str, ...], dense: tuple[str, ...], **kwargs) -> HybridRung:
    return HybridRung(
        lexical=StubRung("lexical", lexical, **kwargs),
        dense=StubRung("dense", dense, **kwargs),
    )


class TestFusion:
    def test_agreement_outranks_a_single_first_place(self) -> None:
        """The reason this rung exists: the two retrievers are confidently
        wrong on different repositories, so what they agree on is the better
        bet than what either alone is sure of."""
        prediction = hybrid(("a.py", "b.py"), ("c.py", "b.py")).predict(INSTANCE)
        assert prediction.ranked_files[0] == "b.py"

    def test_keeps_every_candidate_from_both(self) -> None:
        prediction = hybrid(("a.py",), ("b.py",)).predict(INSTANCE)
        assert set(prediction.ranked_files) == {"a.py", "b.py"}

    def test_emits_no_path_twice(self) -> None:
        """`Prediction` rejects duplicates, so this asserts fusion ran at all."""
        ranked = hybrid(("a.py", "b.py"), ("b.py", "a.py")).predict(INSTANCE).ranked_files
        assert len(set(ranked)) == len(ranked)

    def test_is_deterministic(self) -> None:
        rung = hybrid(("a.py", "c.py"), ("c.py", "b.py"))
        assert rung.predict(INSTANCE).ranked_files == rung.predict(INSTANCE).ranked_files

    def test_names_itself(self) -> None:
        assert hybrid(("a.py",), ("b.py",)).predict(INSTANCE).rung == "hybrid"


class TestStopConditions:
    def test_one_empty_retriever_still_answers(self) -> None:
        """An empty list from one retriever is a result, not a failure. Calling
        it `no_candidates` would hide a working retriever behind a silent one."""
        prediction = hybrid((), ("b.py",)).predict(INSTANCE)

        assert prediction.stop_condition == StopCondition.ANSWERED
        assert prediction.ranked_files == ("b.py",)

    def test_both_empty_is_no_candidates(self) -> None:
        prediction = hybrid((), ()).predict(INSTANCE)

        assert prediction.stop_condition == StopCondition.NO_CANDIDATES
        assert prediction.ranked_files == ()


class TestAccounting:
    def test_cost_is_the_sum_of_its_parts(self) -> None:
        """Zero today. The field adds rather than hard-codes so a priced
        retriever underneath cannot be silently reported as free."""
        prediction = hybrid(("a.py",), ("b.py",), cost_usd=0.25).predict(INSTANCE)
        assert prediction.cost_usd == 0.50

    def test_latency_is_measured_end_to_end(self) -> None:
        """Running both retrievers is strictly slower than either, and a reader
        comparing rungs is comparing end-to-end time."""
        assert hybrid(("a.py",), ("b.py",)).predict(INSTANCE).latency_s > 0
