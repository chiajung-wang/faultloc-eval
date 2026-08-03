"""Tests for the scorer.

Every number the project publishes comes out of this module. A bug here does not
crash anything -- it produces a plausible wrong number that no downstream check
could detect, which is why the metric definitions are pinned case by case rather
than checked in aggregate.
"""

from __future__ import annotations

import pytest

from faultloc.dataset.models import Instance
from faultloc.rungs import Prediction, StopCondition
from faultloc.scoring import (
    OTHER_BUCKET,
    normalize_path,
    recall_at_k,
    score,
    score_instance,
    top_1_hit,
    wilson_interval,
)

SHA = "0" * 40


def instance(instance_id: str = "i-1", repo: str = "a/b", *truth: str) -> Instance:
    return Instance(
        instance_id=instance_id,
        repo=repo,
        base_commit=SHA,
        issue_text="t",
        ground_truth_files=truth or ("pkg/core.py",),
    )


def prediction(
    *ranked: str,
    instance_id: str = "i-1",
    stop_condition: str = StopCondition.ANSWERED,
    latency_s: float = 1.0,
    cost_usd: float = 0.0,
) -> Prediction:
    return Prediction(
        instance_id=instance_id,
        rung="bm25",
        ranked_files=ranked,
        stop_condition=stop_condition,
        latency_s=latency_s,
        cost_usd=cost_usd,
    )


class TestNormalizePath:
    @pytest.mark.parametrize(
        "written",
        [
            "pkg/core.py",
            "./pkg/core.py",
            "/pkg/core.py",
            "pkg//core.py",
            "pkg\\core.py",
            ".//pkg/core.py",
        ],
    )
    def test_cosmetic_differences_collapse(self, written: str) -> None:
        assert normalize_path(written) == "pkg/core.py"

    def test_case_is_preserved(self) -> None:
        """Folding case would turn a genuine miss into a false hit.

        These repositories are built on case-sensitive filesystems, so `Core.py`
        and `core.py` are different files. A scorer may never invent a hit.
        """
        assert normalize_path("pkg/Core.py") != normalize_path("pkg/core.py")

    def test_distinct_paths_stay_distinct(self) -> None:
        assert normalize_path("a/core.py") != normalize_path("b/core.py")


class TestTop1:
    def test_rank_one_in_the_truth_is_a_hit(self) -> None:
        assert top_1_hit(prediction("pkg/core.py", "pkg/util.py"), instance())

    def test_rank_two_is_not_a_hit(self) -> None:
        """Top-1 is the workflow number: only what a tool would actually show."""
        assert not top_1_hit(prediction("pkg/util.py", "pkg/core.py"), instance())

    def test_empty_prediction_is_not_a_hit(self) -> None:
        """An empty ranking only exists as `no_candidates` -- rung 1's contract
        forbids an `answered` result with nothing in it."""
        empty = prediction(stop_condition=StopCondition.NO_CANDIDATES)
        assert not top_1_hit(empty, instance())

    def test_any_ground_truth_file_at_rank_one_counts(self) -> None:
        target = instance("i-1", "a/b", "pkg/core.py", "pkg/util.py")
        assert top_1_hit(prediction("pkg/util.py"), target)

    def test_path_differences_do_not_cause_a_false_miss(self) -> None:
        assert top_1_hit(prediction("./pkg/core.py"), instance())


class TestRecallAtK:
    def test_single_file_found_within_k(self) -> None:
        assert recall_at_k(prediction("x.py", "pkg/core.py"), instance(), 3) == 1.0

    def test_single_file_outside_k(self) -> None:
        ranked = ("a.py", "b.py", "c.py", "pkg/core.py")
        assert recall_at_k(prediction(*ranked), instance(), 3) == 0.0

    def test_is_the_share_of_truth_found_not_all_or_nothing(self) -> None:
        """A two-file instance with one file found scores 0.5.

        Counting it as a whole miss would understate a rung that located half
        the answer; as a whole hit, overstate it.
        """
        target = instance("i-1", "a/b", "pkg/core.py", "pkg/util.py")
        assert recall_at_k(prediction("pkg/core.py", "z.py"), target, 3) == 0.5

    def test_all_files_found(self) -> None:
        target = instance("i-1", "a/b", "pkg/core.py", "pkg/util.py")
        assert recall_at_k(prediction("pkg/core.py", "pkg/util.py"), target, 3) == 1.0

    def test_boundary_at_k(self) -> None:
        """Position 3 counts for k=3; position 4 does not."""
        at_three = prediction("a.py", "b.py", "pkg/core.py")
        at_four = prediction("a.py", "b.py", "c.py", "pkg/core.py")

        assert recall_at_k(at_three, instance(), 3) == 1.0
        assert recall_at_k(at_four, instance(), 3) == 0.0

    def test_shorter_ranking_than_k_is_fine(self) -> None:
        assert recall_at_k(prediction("pkg/core.py"), instance(), 5) == 1.0

    def test_empty_prediction_scores_zero(self) -> None:
        empty = prediction(stop_condition=StopCondition.NO_CANDIDATES)
        assert recall_at_k(empty, instance(), 5) == 0.0


class TestWilsonInterval:
    def test_brackets_the_estimate(self) -> None:
        low, high = wilson_interval(96, 244)
        assert low < 96 / 244 < high

    def test_stays_inside_zero_and_one(self) -> None:
        """The reason this is not the normal approximation.

        At 0% or 100% the textbook interval runs outside [0, 1] and collapses to
        zero width -- exactly where the small per-repo rows sit.
        """
        assert wilson_interval(0, 5) == pytest.approx((0.0, wilson_interval(0, 5)[1]))
        assert wilson_interval(5, 5)[1] <= 1.0
        assert wilson_interval(5, 5)[0] < 1.0

    def test_narrows_as_n_grows(self) -> None:
        small = wilson_interval(5, 10)
        large = wilson_interval(500, 1000)
        assert (large[1] - large[0]) < (small[1] - small[0])

    def test_empty_sample_is_not_an_error(self) -> None:
        assert wilson_interval(0, 0) == (0.0, 0.0)


class TestScoreInstance:
    def test_refuses_a_mismatched_pair(self) -> None:
        """A misaligned pair yields a plausible number about the wrong question."""
        with pytest.raises(ValueError, match="prediction is for"):
            score_instance(prediction("x.py", instance_id="other"), instance("i-1"))

    def test_carries_cost_latency_and_stop_condition(self) -> None:
        scored = score_instance(prediction("pkg/core.py", latency_s=2.5, cost_usd=0.01), instance())
        assert scored.latency_s == 2.5
        assert scored.cost_usd == 0.01
        assert scored.stop_condition == StopCondition.ANSWERED

    def test_no_candidates_scores_as_a_miss_and_keeps_its_reason(self) -> None:
        """A miss and a non-attempt score the same but must stay distinguishable."""
        scored = score_instance(prediction(stop_condition=StopCondition.NO_CANDIDATES), instance())
        assert not scored.hit_1
        assert scored.stop_condition == StopCondition.NO_CANDIDATES


class TestScore:
    def test_reports_overall_metrics(self) -> None:
        report = score(
            [
                prediction("pkg/core.py", instance_id="i-1"),
                prediction("wrong.py", instance_id="i-2"),
            ],
            [instance("i-1"), instance("i-2")],
            rung="bm25",
            split="dev",
        )

        assert report.overall.n == 2
        assert report.overall.top_1 == 0.5
        assert report.rung == "bm25"
        assert report.split == "dev"

    def test_pairs_by_id_not_by_position(self) -> None:
        """A reordered prediction list must not score the wrong pairs."""
        report = score(
            [
                prediction("pkg/core.py", instance_id="i-2"),
                prediction("pkg/core.py", instance_id="i-1"),
            ],
            [instance("i-1"), instance("i-2")],
            rung="bm25",
            split="dev",
        )
        assert report.overall.top_1 == 1.0

    def test_rejects_a_prediction_for_an_unknown_instance(self) -> None:
        with pytest.raises(ValueError, match="unknown instances"):
            score(
                [prediction("x.py", instance_id="ghost")],
                [instance("i-1")],
                rung="bm25",
                split="dev",
            )

    def test_breaks_down_by_repo(self) -> None:
        """ADR-0006 requires it: Django is 46% of the benchmark, so the
        aggregate is largely a Django number."""
        predictions = [prediction("pkg/core.py", instance_id=f"i-{n}") for n in range(6)]
        instances = [instance(f"i-{n}", "big/repo" if n < 3 else "other/repo") for n in range(6)]

        report = score(predictions, instances, rung="bm25", split="dev")

        assert set(report.by_repo) == {"big/repo", "other/repo"}
        assert report.by_repo["big/repo"].n == 3

    def test_small_repos_collapse_into_other(self) -> None:
        """A one-instance repo would show as a 0% or 100% row and be over-read."""
        predictions = [prediction("pkg/core.py", instance_id=f"i-{n}") for n in range(4)]
        instances = [
            instance("i-0", "big/repo"),
            instance("i-1", "big/repo"),
            instance("i-2", "big/repo"),
            instance("i-3", "tiny/repo"),
        ]

        report = score(predictions, instances, rung="bm25", split="dev")

        assert set(report.by_repo) == {"big/repo", OTHER_BUCKET}
        assert report.by_repo[OTHER_BUCKET].n == 1

    def test_counts_stop_conditions(self) -> None:
        report = score(
            [
                prediction("pkg/core.py", instance_id="i-1"),
                prediction(instance_id="i-2", stop_condition=StopCondition.NO_CANDIDATES),
            ],
            [instance("i-1"), instance("i-2")],
            rung="bm25",
            split="dev",
        )
        assert report.stop_conditions == {
            StopCondition.ANSWERED: 1,
            StopCondition.NO_CANDIDATES: 1,
        }

    def test_aggregates_cost_and_latency(self) -> None:
        report = score(
            [
                prediction("pkg/core.py", instance_id="i-1", latency_s=1.0, cost_usd=0.02),
                prediction("pkg/core.py", instance_id="i-2", latency_s=3.0, cost_usd=0.04),
            ],
            [instance("i-1"), instance("i-2")],
            rung="bm25",
            split="dev",
        )

        assert report.overall.cost_usd_total == pytest.approx(0.06)
        assert report.overall.cost_usd_per_instance == pytest.approx(0.03)
        assert report.overall.latency_s_total == pytest.approx(4.0)

    def test_empty_run_reports_zeroes_not_an_error(self) -> None:
        """An empty run is a result to report, not a crash."""
        report = score([], [], rung="bm25", split="dev")
        assert report.overall.n == 0
        assert report.overall.top_1 == 0.0
        assert report.overall.cost_usd_per_instance == 0.0
