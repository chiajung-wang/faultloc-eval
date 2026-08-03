"""Tests for the Verified Set loader.

No network. `load_verified_set` takes its row source as an argument precisely so
the pin and the counting can be tested against fixture rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from faultloc.dataset.filters import DropReason
from faultloc.dataset.verified import (
    DATASET_CONFIG,
    DATASET_ID,
    DATASET_REVISION,
    DATASET_SPLIT,
    LoadReport,
    load_verified_set,
    to_instance,
)

FIXTURES = Path(__file__).parent / "fixtures" / "patches"
SHA = "0" * 40


def row(instance_id: str, **overrides: Any) -> dict[str, Any]:
    """A dataset row built from a real gold patch fixture."""
    base = {
        "instance_id": instance_id,
        "repo": instance_id.rsplit("-", 1)[0].replace("__", "/"),
        "base_commit": SHA,
        "problem_statement": f"issue text for {instance_id}",
        "patch": (FIXTURES / f"{instance_id}.patch").read_text(),
        "test_patch": "diff --git a/tests/test_x.py b/tests/test_x.py\n",
        "hints_text": "SECRET_HINT the bug is in pylint/config/__init__.py",
        "difficulty": "15 min - 1 hour",
    }
    return base | overrides


class TestToInstance:
    def test_builds_an_instance_from_a_kept_row(self) -> None:
        instance = to_instance(row("sympy__sympy-22914"))
        assert instance is not None
        assert instance.instance_id == "sympy__sympy-22914"
        assert instance.repo == "sympy/sympy"
        assert instance.ground_truth_files == ("sympy/printing/pycode.py",)

    def test_applies_the_instance_filter(self) -> None:
        """setup.cfg is in the patch and must not reach the ground truth."""
        instance = to_instance(row("pylint-dev__pylint-4661"))
        assert instance is not None
        assert instance.ground_truth_files == ("pylint/config/__init__.py",)

    def test_returns_none_for_a_dropped_row(self) -> None:
        assert to_instance(row("django__django-11138")) is None

    def test_issue_text_comes_from_problem_statement(self) -> None:
        instance = to_instance(row("sympy__sympy-22914"))
        assert instance is not None
        assert instance.issue_text == "issue text for sympy__sympy-22914"

    def test_hints_text_never_reaches_the_instance(self) -> None:
        """`hints_text` is the issue's comment thread and leaks the answer.

        It is excluded at the loader rather than at the prompt so that no
        downstream component can reach it, and this test is what keeps that
        true when the Instance model grows a field.
        """
        instance = to_instance(row("pylint-dev__pylint-4661"))
        assert instance is not None
        assert "SECRET_HINT" not in instance.model_dump_json()

    def test_test_patch_never_reaches_the_ground_truth(self) -> None:
        instance = to_instance(row("sympy__sympy-22914"))
        assert instance is not None
        assert not any("test" in path for path in instance.ground_truth_files)


class TestLoadVerifiedSet:
    def test_requests_the_pinned_revision(self) -> None:
        """The pin is the thing most likely to rot silently.

        A dataset that updates under a published number makes that number
        irreproducible without anything failing, so the request itself is
        asserted rather than the data that comes back.
        """
        seen: list[tuple[str, str, str, str]] = []

        def spy(dataset_id: str, config: str, split: str, revision: str) -> list[Any]:
            seen.append((dataset_id, config, split, revision))
            return []

        load_verified_set(fetch=spy)

        assert seen == [(DATASET_ID, DATASET_CONFIG, DATASET_SPLIT, DATASET_REVISION)]

    def test_revision_is_a_full_sha(self) -> None:
        assert len(DATASET_REVISION) == 40
        assert DATASET_REVISION == "c104f840cc67f8b6eec6f759ebc8b2693d585d4a"

    def test_counts_drops_by_reason(self) -> None:
        rows = [
            row("sympy__sympy-22914"),
            row("pylint-dev__pylint-4661"),
            row("django__django-11138"),
            row("astropy__astropy-13398"),
        ]
        loaded = load_verified_set(fetch=lambda *_: rows)

        assert loaded.report.total == 4
        assert loaded.report.kept == 2
        assert loaded.report.drops == {DropReason.TOO_MANY_SOURCE_FILES: 2}
        assert len(loaded.instances) == 2

    def test_dropped_instances_are_absent_but_counted(self) -> None:
        rows = [row("django__django-11138")]
        loaded = load_verified_set(fetch=lambda *_: rows)

        assert loaded.instances == ()
        assert loaded.report.dropped == 1
        assert loaded.report.filter_rate == 1.0

    def test_empty_source_yields_an_empty_report(self) -> None:
        loaded = load_verified_set(fetch=lambda *_: [])
        assert loaded.instances == ()
        assert loaded.report.total == 0
        assert loaded.report.filter_rate == 0.0


class TestLoadReport:
    def test_filter_rate_is_the_dropped_share(self) -> None:
        assert LoadReport(total=500, kept=490).filter_rate == pytest.approx(0.02)

    def test_empty_set_reports_zero_not_nan(self) -> None:
        assert LoadReport(total=0, kept=0).filter_rate == 0.0
