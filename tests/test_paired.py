"""The paired comparison between two rungs.

M5 cannot report a result without this. Issue 01 measured rung 4's whole
available delta over rung 3 at about 6.6 points, and the Wilson interval at
n=244 is ±6pp, so two marginal intervals would call a perfect agent
inconclusive. A silent bug here would therefore produce a plausible p-value for
the most expensive milestone in the project.
"""

from __future__ import annotations

import pytest

from faultloc.dataset.models import Instance
from faultloc.rungs import Prediction, StopCondition
from faultloc.scoring import compare, mcnemar_p_value


def instance(number: int, truth: str = "pkg/right.py") -> Instance:
    return Instance(
        instance_id=f"acme__widget-{number}",
        repo="acme/widget",
        base_commit="a" * 40,
        issue_text="something is broken",
        ground_truth_files=(truth,),
    )


def prediction(number: int, top: str, rung: str = "r") -> Prediction:
    return Prediction(
        instance_id=f"acme__widget-{number}",
        rung=rung,
        ranked_files=(top,),
        stop_condition=StopCondition.ANSWERED,
        latency_s=0.1,
    )


RIGHT = "pkg/right.py"
WRONG = "pkg/wrong.py"


class TestMcnemarPValue:
    def test_no_discordant_instances_is_untestable(self) -> None:
        """Two rungs that agree everywhere have no evidence between them."""
        assert mcnemar_p_value(0, 0) == 1.0

    def test_a_one_sided_sweep_is_decisive(self) -> None:
        """16 wins and no losses is the case issue 01 says rung 4 could reach.

        The published Top-1 figures either side of that gap would sit inside each
        other's Wilson intervals. This is the number that says the difference is
        real anyway.
        """
        assert mcnemar_p_value(0, 16) < 0.001

    def test_an_even_split_establishes_nothing(self) -> None:
        """7 against 7 is a coin flip, and the test must say so.

        This is the outcome that keeps the test honest. A paired test removes a
        measurement problem. It does not manufacture a win.
        """
        assert mcnemar_p_value(7, 7) == 1.0

    def test_is_symmetric_in_its_arguments(self) -> None:
        assert mcnemar_p_value(3, 11) == mcnemar_p_value(11, 3)

    def test_matches_the_binomial_by_hand(self) -> None:
        """One discordant Instance cannot be significant, whichever way it fell.

        Two-sided exact binomial at n=1: both tails, so p = 1.0. At n=6 with a
        5-1 split the tail is (C(6,0) + C(6,1)) / 2**6 = 7/64, doubled = 7/32.
        """
        assert mcnemar_p_value(0, 1) == 1.0
        assert mcnemar_p_value(1, 5) == pytest.approx(7 / 32)

    def test_a_small_gap_in_a_large_discordant_set_is_not_significant(self) -> None:
        assert mcnemar_p_value(18, 22) > 0.05


class TestCompare:
    def test_counts_the_four_cells(self) -> None:
        instances = [instance(n) for n in range(4)]
        a = [
            prediction(0, RIGHT),  # both right
            prediction(1, WRONG),  # both wrong
            prediction(2, RIGHT),  # a only
            prediction(3, WRONG),  # b only
        ]
        b = [
            prediction(0, RIGHT),
            prediction(1, WRONG),
            prediction(2, WRONG),
            prediction(3, RIGHT),
        ]

        result = compare(a, b, instances, a="lhs", b="rhs")

        assert (result.both_hit, result.both_miss) == (1, 1)
        assert (result.a_only, result.b_only) == (1, 1)
        assert result.n == 4
        assert result.discordant == 2

    def test_delta_is_b_minus_a(self) -> None:
        """The ladder credits a rung against the rung below, so direction matters."""
        instances = [instance(n) for n in range(4)]
        a = [prediction(n, WRONG) for n in range(4)]
        b = [prediction(n, RIGHT if n < 3 else WRONG) for n in range(4)]

        result = compare(a, b, instances, a="below", b="above")

        assert result.b_only == 3
        assert result.top_1_delta == pytest.approx(0.75)

    def test_delta_is_negative_when_the_upper_rung_loses(self) -> None:
        instances = [instance(n) for n in range(2)]
        a = [prediction(n, RIGHT) for n in range(2)]
        b = [prediction(n, WRONG) for n in range(2)]

        result = compare(a, b, instances, a="below", b="above")

        assert result.top_1_delta == pytest.approx(-1.0)

    def test_pairs_by_instance_id_and_not_by_position(self) -> None:
        """A reordered run must not be scored against the wrong Instances.

        `score` already pairs by id. A paired test that paired by position would
        produce a p-value about nothing, and no downstream check could see it.
        """
        instances = [instance(n) for n in range(3)]
        a = [prediction(0, RIGHT), prediction(1, WRONG), prediction(2, WRONG)]
        b = [prediction(2, WRONG), prediction(0, RIGHT), prediction(1, WRONG)]

        result = compare(a, b, instances, a="lhs", b="rhs")

        assert result.both_hit == 1
        assert result.both_miss == 2
        assert result.discordant == 0

    def test_refuses_two_runs_over_different_instance_sets(self) -> None:
        """The whole point. Comparing two benchmarks is worse than not comparing."""
        instances = [instance(n) for n in range(3)]
        a = [prediction(0, RIGHT), prediction(1, RIGHT)]
        b = [prediction(1, RIGHT), prediction(2, RIGHT)]

        with pytest.raises(ValueError, match="different Instances"):
            compare(a, b, instances, a="lhs", b="rhs")

    def test_refuses_an_empty_comparison(self) -> None:
        with pytest.raises(ValueError, match="share no Instances"):
            compare([], [], [instance(0)], a="lhs", b="rhs")

    def test_refuses_a_prediction_for_an_unknown_instance(self) -> None:
        with pytest.raises(ValueError, match="unknown instances"):
            compare([prediction(9, RIGHT)], [prediction(9, RIGHT)], [instance(0)], a="l", b="r")

    def test_a_multi_file_instance_is_a_hit_on_any_ground_truth_file(self) -> None:
        """Top-1 asks whether the rank-1 path is *in* the Ground-Truth File Set."""
        multi = Instance(
            instance_id="acme__widget-0",
            repo="acme/widget",
            base_commit="a" * 40,
            issue_text="broken",
            ground_truth_files=("pkg/first.py", "pkg/second.py"),
        )

        result = compare(
            [prediction(0, "pkg/first.py")],
            [prediction(0, "pkg/second.py")],
            [multi],
            a="lhs",
            b="rhs",
        )

        assert result.both_hit == 1
