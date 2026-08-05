"""Tests for rung 2.6, the cross-encoder reranker.

The candidate supplier, the Evidence Chunk lookup and the scorer are all
stubbed, so nothing downloads weights, reads an index or touches the network.
What is under test is the composition -- that only the head is reordered, that
the pair text is what ADR-0008 says a candidate is shown as, and that a model
returning ties still produces one stable order.
"""

from __future__ import annotations

from collections.abc import Sequence

from faultloc.dataset.models import Instance
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.cross_encoder import CrossEncoderRung

INSTANCE = Instance(
    instance_id="acme__widget-1",
    repo="acme/widget",
    base_commit="a" * 40,
    issue_text="core is broken",
    ground_truth_files=("pkg/core.py",),
)


class StubCandidates:
    """A candidate supplier with a fixed ranking."""

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


class RecordingScorer:
    """Scores by a lookup table and remembers what it was asked."""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.pairs: list[tuple[str, str]] = []

    def __call__(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        self.pairs = list(pairs)
        return [self.scores.get(document.splitlines()[0], 0.0) for _query, document in pairs]


def rung(
    ranked: tuple[str, ...],
    scores: dict[str, float],
    *,
    evidence: dict[str, str] | None = None,
    top_k: int = 20,
) -> tuple[CrossEncoderRung, RecordingScorer]:
    scorer = RecordingScorer(scores)
    chunks = evidence if evidence is not None else {path: f"body of {path}" for path in ranked}
    return (
        CrossEncoderRung(
            candidates=StubCandidates(ranked),
            evidence=lambda instance, paths: {p: chunks.get(p, "") for p in paths},
            score=scorer,
            top_k=top_k,
        ),
        scorer,
    )


class TestReranking:
    def test_reorders_the_head_by_score(self) -> None:
        reranker, _ = rung(("a.py", "b.py", "c.py"), {"b.py": 9.0, "a.py": 1.0, "c.py": 5.0})
        assert reranker.predict(INSTANCE).ranked_files == ("b.py", "c.py", "a.py")

    def test_leaves_everything_past_k_alone(self) -> None:
        """The Candidate Set's hit@20 ceiling only transfers if the tail is
        preserved -- a rung that dropped it would score a different list from
        the one issue 01 measured."""
        reranker, _ = rung(
            ("a.py", "b.py", "c.py", "d.py"),
            {"b.py": 9.0, "a.py": 1.0},
            top_k=2,
        )
        assert reranker.predict(INSTANCE).ranked_files == ("b.py", "a.py", "c.py", "d.py")

    def test_scores_only_the_head(self) -> None:
        """K is the budget. Scoring the whole ranking would cost hours and
        measure a different list from the one issue 01 put a ceiling on."""
        reranker, scorer = rung(("a.py", "b.py", "c.py"), {}, top_k=2)
        reranker.predict(INSTANCE)
        assert len(scorer.pairs) == 2

    def test_ties_break_by_path(self) -> None:
        """Every rung in this project breaks ties by path. A model returning
        the same score for two candidates must not leave the order to whatever
        `sorted` saw first."""
        reranker, _ = rung(("b.py", "a.py"), {"a.py": 1.0, "b.py": 1.0})
        assert reranker.predict(INSTANCE).ranked_files == ("a.py", "b.py")

    def test_is_deterministic(self) -> None:
        reranker, _ = rung(("a.py", "b.py", "c.py"), {"c.py": 2.0, "a.py": 1.0})
        assert reranker.predict(INSTANCE).ranked_files == reranker.predict(INSTANCE).ranked_files

    def test_names_itself(self) -> None:
        reranker, _ = rung(("a.py",), {"a.py": 1.0})
        assert reranker.predict(INSTANCE).rung == "cross-encoder"


class TestPairText:
    def test_pairs_the_issue_with_path_and_evidence_chunk(self) -> None:
        """ADR-0008 fixes what a candidate is shown as: its path plus its
        Evidence Chunk. Rung 3 uses the same payload, so a difference here
        would make the 2.6-to-3 delta measure the payload, not the mechanism."""
        reranker, scorer = rung(("a.py",), {"a.py": 1.0}, evidence={"a.py": "def boom(): ..."})
        reranker.predict(INSTANCE)

        query, document = scorer.pairs[0]
        assert query == "core is broken"
        assert document == "a.py\ndef boom(): ..."

    def test_a_file_with_no_evidence_still_scores(self) -> None:
        """An unreadable blob must not drop a candidate: that would silently
        shrink the list the ceiling was measured on."""
        reranker, scorer = rung(("a.py", "b.py"), {}, evidence={"a.py": "x"})
        prediction = reranker.predict(INSTANCE)

        assert set(prediction.ranked_files) == {"a.py", "b.py"}
        assert scorer.pairs[1] == ("core is broken", "b.py")


class TestStopConditions:
    def test_no_candidates_is_not_reranked(self) -> None:
        reranker, scorer = rung((), {})
        prediction = reranker.predict(INSTANCE)

        assert prediction.stop_condition == StopCondition.NO_CANDIDATES
        assert prediction.ranked_files == ()
        assert scorer.pairs == []


class TestAccounting:
    def test_costs_nothing(self) -> None:
        """The rung's whole argument: a local model, priced at zero, sitting
        between fusion and a paid API."""
        reranker, _ = rung(("a.py",), {"a.py": 1.0})
        assert reranker.predict(INSTANCE).cost_usd == 0.0

    def test_latency_is_measured_end_to_end(self) -> None:
        reranker, _ = rung(("a.py",), {"a.py": 1.0})
        assert reranker.predict(INSTANCE).latency_s > 0
