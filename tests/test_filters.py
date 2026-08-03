"""Tests for the Instance Filter (ADR-0001).

These are written before the implementation on purpose. This filter decides
what every reported number is scored against -- a silent bug here invalidates
the whole results log, and nothing downstream would catch it.
"""

from __future__ import annotations

import pytest

from faultloc.dataset.filters import (
    DropReason,
    FilterResult,
    filter_ground_truth_files,
    is_source_file,
)


class TestIsSourceFile:
    @pytest.mark.parametrize(
        "path",
        [
            "django/db/models/query.py",
            "src/pandas/core/frame.py",
            "sympy/solvers/ode.py",
        ],
    )
    def test_python_source_is_source(self, path: str) -> None:
        assert is_source_file(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "tests/test_query.py",
            "django/db/tests/test_models.py",
            "pandas/core/test_frame.py",
            "sympy/solvers/ode_test.py",
        ],
    )
    def test_test_files_are_not_source(self, path: str) -> None:
        assert is_source_file(path) is False

    @pytest.mark.parametrize(
        "path",
        [
            "README.md",
            "docs/usage.rst",
            "doc/whatsnew.txt",
            "setup.cfg",
            "pyproject.toml",
            "uv.lock",
            ".github/workflows/ci.yml",
            "package.json",
        ],
    )
    def test_docs_and_config_are_not_source(self, path: str) -> None:
        assert is_source_file(path) is False

    @pytest.mark.parametrize(
        "path",
        [
            "pandas/_libs/tslib.pyx",
            "numpy/core/src/multiarray/item_selection.c",
            "src/multiarray/nditer.h",
            "sphinx/themes/basic/static/searchtools.js",
            "django/db/models/query.pyi",
        ],
    )
    def test_non_python_code_is_source(self, path: str) -> None:
        """The classifier is a deny-list, and that is load-bearing.

        Swapping to an allow-list of known code extensions would pass every
        other test in this file while silently emptying the Ground-Truth File
        Set for any fix that touches compiled or front-end sources. A dropped
        ground-truth file is indistinguishable from a wrong prediction once it
        reaches the scorer, so the deny-list is pinned here rather than left to
        a comment.
        """
        assert is_source_file(path) is True

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("./django/db/models/query.py", True),
            ("./tests/test_query.py", False),
            ("./docs/usage.rst", False),
        ],
    )
    def test_leading_dot_slash_does_not_change_the_verdict(
        self, path: str, expected: bool
    ) -> None:
        """Paths arrive from diff headers and may carry a `./` prefix."""
        assert is_source_file(path) is expected


class TestFilterGroundTruthFiles:
    def test_keeps_source_files_and_drops_the_rest(self) -> None:
        result = filter_ground_truth_files(
            [
                "django/db/models/query.py",
                "tests/test_query.py",
                "docs/releases/5.0.txt",
                "CHANGELOG.md",
            ]
        )
        assert result.kept
        assert result.files == ("django/db/models/query.py",)
        assert result.drop_reason is None

    def test_preserves_input_order(self) -> None:
        result = filter_ground_truth_files(
            ["b/second.py", "tests/test_x.py", "a/first.py"]
        )
        assert result.files == ("b/second.py", "a/first.py")

    def test_drops_instance_with_no_source_files(self) -> None:
        result = filter_ground_truth_files(["docs/usage.rst", "tests/test_x.py"])
        assert not result.kept
        assert result.files is None
        assert result.drop_reason == DropReason.NO_SOURCE_FILES

    def test_drops_instance_exceeding_the_cap(self) -> None:
        result = filter_ground_truth_files(
            ["a.py", "b.py", "c.py", "d.py"],
        )
        assert not result.kept
        assert result.drop_reason == DropReason.TOO_MANY_SOURCE_FILES

    def test_keeps_instance_exactly_at_the_cap(self) -> None:
        result = filter_ground_truth_files(["a.py", "b.py", "c.py"])
        assert result.kept
        assert result.files == ("a.py", "b.py", "c.py")

    def test_cap_is_configurable(self) -> None:
        result = filter_ground_truth_files(["a.py", "b.py"], max_source_files=1)
        assert not result.kept
        assert result.drop_reason == DropReason.TOO_MANY_SOURCE_FILES

    def test_empty_input_drops_with_no_source_files(self) -> None:
        result = filter_ground_truth_files([])
        assert not result.kept
        assert result.drop_reason == DropReason.NO_SOURCE_FILES

    def test_duplicate_paths_count_once_against_the_cap(self) -> None:
        """The cap counts distinct files, not diff entries.

        ADR-0001 drops an instance when a fix spans more than three source
        files. A path repeated in the input is still one location, so it must
        not push an otherwise-valid instance over the cap.
        """
        result = filter_ground_truth_files(["a.py", "a.py", "b.py", "c.py"])
        assert result.kept
        assert result.files == ("a.py", "b.py", "c.py")

    def test_duplicates_are_deduplicated_by_first_occurrence(self) -> None:
        result = filter_ground_truth_files(["b.py", "a.py", "b.py"])
        assert result.files == ("b.py", "a.py")


class TestFilterResultInvariant:
    """`files` and `drop_reason` are mutually exclusive and jointly exhaustive.

    Every consumer branches on one or the other. A result with both set, or
    neither, would make `kept` disagree with `drop_reason` and let a dropped
    instance be scored as if it had been kept.
    """

    def test_kept_result_carries_no_drop_reason(self) -> None:
        result = FilterResult(files=("a.py",), drop_reason=None)
        assert result.kept

    def test_dropped_result_carries_no_files(self) -> None:
        result = FilterResult(files=None, drop_reason=DropReason.NO_SOURCE_FILES)
        assert not result.kept

    def test_both_set_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            FilterResult(files=("a.py",), drop_reason=DropReason.NO_SOURCE_FILES)

    def test_neither_set_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            FilterResult(files=None, drop_reason=None)
