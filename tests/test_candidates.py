"""Tests for candidate-list fusion.

The merge rule decides what lands inside the top K, and the top K is the hard
ceiling on any reranker's Top-1. So these check the ordering properties the
choice was made for, not just that a list comes out.
"""

from __future__ import annotations

from faultloc.candidates import hit_at_k, interleave, reciprocal_rank_fusion


class TestReciprocalRankFusion:
    def test_agreement_beats_a_single_strong_vote(self) -> None:
        """The property the rule was chosen for. `b` is second on both lists;
        `a` and `c` are first on one and absent from the other. When the two
        retrievers disagree by repository, the path they both like is the
        better bet."""
        merged = reciprocal_rank_fusion([["a", "b"], ["c", "b"]])
        assert merged[0] == "b"

    def test_keeps_everything_from_both_lists(self) -> None:
        merged = reciprocal_rank_fusion([["a", "b"], ["c", "d"]])
        assert set(merged) == {"a", "b", "c", "d"}

    def test_emits_no_path_twice(self) -> None:
        """A repeat would waste a candidate slot and inflate the ceiling."""
        merged = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])
        assert len(merged) == len(set(merged))

    def test_preserves_order_of_a_single_list(self) -> None:
        assert reciprocal_rank_fusion([["a", "b", "c"]]) == ("a", "b", "c")

    def test_ties_break_by_path(self) -> None:
        """Identical lists score every path equally. Without the tiebreak the
        order would follow dictionary insertion."""
        merged = reciprocal_rank_fusion([["b", "a"], ["a", "b"]])
        assert merged == tuple(sorted(merged))

    def test_is_deterministic(self) -> None:
        lists = [["a", "c", "b"], ["b", "a", "d"]]
        assert reciprocal_rank_fusion(lists) == reciprocal_rank_fusion(lists)

    def test_damping_flattens_the_top_ranks(self) -> None:
        """With damping the gap between rank 1 and rank 2 is small, so two
        second-place votes outweigh one first place. Without it they would not,
        which is the whole reason the constant exists."""
        with_damping = reciprocal_rank_fusion([["a", "b"], ["c", "b"]], damping=60)
        without = reciprocal_rank_fusion([["a", "b"], ["c", "b"]], damping=0)

        assert with_damping[0] == "b"
        assert without[0] != "b"

    def test_handles_empty_input(self) -> None:
        assert reciprocal_rank_fusion([]) == ()
        assert reciprocal_rank_fusion([[], []]) == ()


class TestInterleave:
    def test_takes_one_from_each_in_turn(self) -> None:
        assert interleave([["a", "b"], ["c", "d"]]) == ("a", "c", "b", "d")

    def test_skips_repeats(self) -> None:
        assert interleave([["a", "b"], ["a", "c"]]) == ("a", "b", "c")

    def test_guarantees_each_lists_top_item_is_near_the_front(self) -> None:
        """The property interleaving has and fusion does not: both retrievers'
        first choice appears immediately, whether or not the other agrees."""
        merged = interleave([["a", "x", "y"], ["b", "x", "y"]])
        assert set(merged[:2]) == {"a", "b"}

    def test_handles_lists_of_different_lengths(self) -> None:
        assert interleave([["a"], ["b", "c", "d"]]) == ("a", "b", "c", "d")

    def test_handles_empty_input(self) -> None:
        assert interleave([]) == ()


class TestHitAtK:
    def test_true_when_any_truth_file_is_in_range(self) -> None:
        assert hit_at_k(["a", "b", "c"], ["c"], 3)

    def test_false_when_truth_falls_outside_k(self) -> None:
        assert not hit_at_k(["a", "b", "c"], ["c"], 2)

    def test_one_of_several_truth_files_is_enough(self) -> None:
        """This bounds Top-1, not Recall@k. The reranker picks one path, so one
        correct path in the list is all it needs to be able to win."""
        assert hit_at_k(["a", "b"], ["b", "z"], 2)

    def test_false_for_an_empty_ranking(self) -> None:
        assert not hit_at_k([], ["a"], 5)
