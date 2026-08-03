"""Tests for the Instance Filter (ADR-0001).

These are written before the implementation on purpose. This filter decides
what every reported number is scored against -- a silent bug here invalidates
the whole results log, and nothing downstream would catch it.
"""

from __future__ import annotations

import pytest

from faultloc.dataset.filters import (
    DropReason,
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
