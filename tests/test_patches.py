"""Tests for diff parsing, against real SWE-bench gold patches.

The fixtures under `tests/fixtures/patches/` are verbatim `patch` fields from
the pinned dataset revision, chosen to cover the shapes that actually occur:
a single-file fix, a fix mixing source with config, a fix spanning enough files
to be dropped, and the one patch in all 500 that adds a new file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faultloc.dataset.patches import changed_files

FIXTURES = Path(__file__).parent / "fixtures" / "patches"


def read_patch(instance_id: str) -> str:
    return (FIXTURES / f"{instance_id}.patch").read_text()


class TestChangedFilesOnRealPatches:
    def test_single_file_fix(self) -> None:
        assert changed_files(read_patch("sympy__sympy-22914")) == ("sympy/printing/pycode.py",)

    def test_source_mixed_with_config(self) -> None:
        """Config files are reported here and rejected later, not skipped now.

        Parsing and classification are separate concerns: this function must
        report the diff faithfully so the Instance Filter -- and only the
        Instance Filter -- decides what counts as source.
        """
        assert changed_files(read_patch("pylint-dev__pylint-4661")) == (
            "pylint/config/__init__.py",
            "setup.cfg",
        )

    def test_multi_file_fix_preserves_diff_order(self) -> None:
        assert changed_files(read_patch("django__django-11138")) == (
            "django/db/backends/mysql/operations.py",
            "django/db/backends/oracle/operations.py",
            "django/db/backends/sqlite3/base.py",
            "django/db/backends/sqlite3/operations.py",
        )

    def test_added_file_is_reported(self) -> None:
        """A `new file mode` entry has no pre-image, only a post-image path."""
        files = changed_files(read_patch("astropy__astropy-13398"))
        assert "astropy/coordinates/builtin_frames/itrs_observed_transforms.py" in files
        assert len(files) == 4


class TestChangedFilesEdgeCases:
    def test_empty_patch_yields_no_files(self) -> None:
        assert changed_files("") == ()

    def test_post_image_path_is_returned(self) -> None:
        """On a rename the fix lives at the new path, so the `b/` side wins."""
        patch = "diff --git a/old/name.py b/new/name.py\nrename from old/name.py\n"
        assert changed_files(patch) == ("new/name.py",)

    def test_path_containing_spaces(self) -> None:
        patch = "diff --git a/dir/my file.py b/dir/my file.py\n"
        assert changed_files(patch) == ("dir/my file.py",)

    def test_duplicates_are_preserved(self) -> None:
        """De-duplication belongs to the Instance Filter, not to the parser."""
        patch = "diff --git a/a.py b/a.py\ndiff --git a/a.py b/a.py\n"
        assert changed_files(patch) == ("a.py", "a.py")

    @pytest.mark.parametrize(
        "line",
        [
            "--- a/not/a/header.py",
            "+++ b/not/a/header.py",
            "index 1234567..89abcde 100644",
        ],
    )
    def test_other_diff_lines_are_not_headers(self, line: str) -> None:
        assert changed_files(f"{line}\n") == ()
