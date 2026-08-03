"""Tests for the frozen dev/test split.

Two things are tested here and they are different: that `build_splits` computes
a defensible split, and that the split actually committed to the repo is intact.
The second matters more -- the committed file is what every published number is
scored against, and it is never recomputed.
"""

from __future__ import annotations

import random

import pytest

from faultloc.dataset.models import Instance
from faultloc.dataset.splits import (
    CI_SLICE_SIZE,
    SPLIT_SEED,
    Splits,
    _largest_remainder,
    build_splits,
    load_splits,
)

SHA = "0" * 40


def make_instances(counts: dict[str, int]) -> list[Instance]:
    """One instance per id, `counts` instances per repo."""
    return [
        Instance(
            instance_id=f"{repo.replace('/', '__')}-{n:04d}",
            repo=repo,
            base_commit=SHA,
            issue_text="t",
            ground_truth_files=("a.py",),
        )
        for repo, total in counts.items()
        for n in range(total)
    ]


class TestBuildSplits:
    def test_is_deterministic(self) -> None:
        instances = make_instances({"a/one": 20, "b/two": 10})
        assert build_splits(instances) == build_splits(instances)

    def test_input_order_does_not_change_the_split(self) -> None:
        """The loader's iteration order must not reach the RNG.

        If it did, the split would change whenever the dataset library altered
        row order -- silently, and only visible as a shifted score.
        """
        instances = make_instances({"a/one": 20, "b/two": 10})
        shuffled = list(instances)
        random.Random(7).shuffle(shuffled)

        assert build_splits(instances) == build_splits(shuffled)

    def test_changing_the_seed_changes_the_split(self) -> None:
        instances = make_instances({"a/one": 20})
        assert build_splits(instances, seed=1) != build_splits(instances, seed=2)

    def test_dev_and_test_partition_the_input(self) -> None:
        instances = make_instances({"a/one": 20, "b/two": 11})
        splits = build_splits(instances)

        assert set(splits.dev) | set(splits.test) == {i.instance_id for i in instances}
        assert not set(splits.dev) & set(splits.test)
        assert splits.size == len(instances)

    def test_every_multi_instance_repo_appears_on_both_sides(self) -> None:
        instances = make_instances({"a/one": 20, "b/two": 11, "c/three": 2})
        splits = build_splits(instances)

        for repo in ("a__one", "b__two", "c__three"):
            assert any(i.startswith(repo) for i in splits.dev), repo
            assert any(i.startswith(repo) for i in splits.test), repo

    def test_single_instance_repo_lands_on_one_side(self) -> None:
        """Stratification cannot balance a repo with one instance.

        This is the documented exception, not a bug: such repos are reported
        inside an `other` bucket rather than as their own per-repo row.
        """
        instances = make_instances({"a/one": 20, "solo/repo": 1})
        splits = build_splits(instances)

        solo = [i for i in splits.dev + splits.test if i.startswith("solo")]
        assert len(solo) == 1

    def test_ci_slice_is_drawn_from_dev(self) -> None:
        instances = make_instances({"a/one": 200})
        splits = build_splits(instances)

        assert set(splits.ci_slice) <= set(splits.dev)
        assert len(splits.ci_slice) == CI_SLICE_SIZE

    def test_ci_slice_is_stratified_not_uniform(self) -> None:
        """A uniform sample of dev would be ~46% Django and gate on Django alone.

        The slice mirrors dev's repo proportions instead, so the CI signal
        reflects the whole benchmark.
        """
        instances = make_instances({"big/repo": 200, "small/repo": 40})
        splits = build_splits(instances)

        big = sum(1 for i in splits.ci_slice if i.startswith("big"))
        small = sum(1 for i in splits.ci_slice if i.startswith("small"))

        assert big + small == CI_SLICE_SIZE
        assert small >= 5  # roughly 1/6 of the slice, not zero

    def test_ci_slice_shrinks_when_dev_is_smaller_than_the_target(self) -> None:
        instances = make_instances({"a/one": 10})
        splits = build_splits(instances)
        assert len(splits.ci_slice) <= len(splits.dev)


class TestLargestRemainder:
    def test_allocates_exactly_the_target(self) -> None:
        assert sum(_largest_remainder({"a": 113, "b": 36, "c": 4}, 50).values()) == 50

    def test_is_proportional(self) -> None:
        allocated = _largest_remainder({"a": 90, "b": 10}, 50)
        assert allocated["a"] > allocated["b"]

    def test_never_allocates_more_than_a_group_holds(self) -> None:
        allocated = _largest_remainder({"a": 2, "b": 100}, 50)
        assert allocated["a"] <= 2

    def test_empty_pool_allocates_nothing(self) -> None:
        assert _largest_remainder({"a": 0}, 50) == {"a": 0}


class TestSplitsInvariants:
    def test_rejects_overlapping_sides(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            Splits(
                dev=("x",),
                test=("x",),
                ci_slice=(),
                seed=1,
                dataset="d",
                revision="r",
            )

    def test_rejects_a_ci_slice_outside_dev(self) -> None:
        with pytest.raises(ValueError, match="drawn from dev"):
            Splits(
                dev=("a",),
                test=("b",),
                ci_slice=("b",),
                seed=1,
                dataset="d",
                revision="r",
            )


class TestSelect:
    def test_returns_instances_in_split_order(self) -> None:
        instances = make_instances({"a/one": 4})
        splits = build_splits(instances)
        selected = splits.select(instances, "dev")

        assert tuple(i.instance_id for i in selected) == splits.dev

    def test_ignores_instances_outside_the_requested_side(self) -> None:
        instances = make_instances({"a/one": 4})
        splits = build_splits(instances)
        assert len(splits.select(instances, "test")) == len(splits.test)


class TestCommittedSplit:
    """Guards on the artifact itself, not on the code that produced it."""

    def test_loads(self) -> None:
        assert load_splits().size > 0

    def test_loading_twice_gives_the_same_split(self) -> None:
        """No RNG at load time. A split that can be recomputed can drift."""
        assert load_splits() == load_splits()

    def test_covers_the_whole_filtered_verified_set(self) -> None:
        """490 of 500 survive the Instance Filter -- see ADR-0001."""
        assert load_splits().size == 490

    def test_sides_are_disjoint_and_deduplicated(self) -> None:
        splits = load_splits()
        assert len(set(splits.dev)) == len(splits.dev)
        assert len(set(splits.test)) == len(splits.test)
        assert not set(splits.dev) & set(splits.test)

    def test_is_roughly_even(self) -> None:
        splits = load_splits()
        assert abs(len(splits.dev) - len(splits.test)) <= 2

    def test_ci_slice_is_the_configured_size(self) -> None:
        assert len(load_splits().ci_slice) == CI_SLICE_SIZE

    def test_records_the_seed_and_provenance(self) -> None:
        """A split is meaningless without the instance universe it came from."""
        splits = load_splits()
        assert splits.seed == SPLIT_SEED
        assert splits.dataset == "princeton-nlp/SWE-bench_Verified"
        assert splits.revision == "c104f840cc67f8b6eec6f759ebc8b2693d585d4a"
