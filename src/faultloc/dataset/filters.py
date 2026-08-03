"""The Instance Filter — see docs/adr/0001-ground-truth-file-set.md.

Turns the raw file list of a fixing PR into a Ground-Truth File Set, or rejects
the instance. Every rejection carries a reason so the Filter Rate can be
reported per drop reason, which ADR-0001 requires.

This module is pure: no I/O, no network, no model calls. It is the component
where a silent bug would invalidate every number the project reports, so it is
built test-first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

MAX_SOURCE_FILES = 3

#: Path segments that mark a file as test code rather than source.
TEST_MARKERS = ("tests/", "test/", "testing/")

#: Filename prefixes/suffixes that mark test code.
TEST_FILE_PREFIX = "test_"
TEST_FILE_SUFFIX = "_test.py"

#: Extensions that are never source for this benchmark.
NON_SOURCE_SUFFIXES = (
    ".md",
    ".rst",
    ".txt",
    ".cfg",
    ".ini",
    ".toml",
    ".lock",
    ".json",
    ".yaml",
    ".yml",
)

#: Directory segments that are never source.
NON_SOURCE_DIRS = ("docs/", "doc/", ".github/", "examples/", "benchmarks/")


class DropReason:
    """Why an instance was rejected. Counted and published as the Filter Rate."""

    NO_SOURCE_FILES = "no_source_files"
    TOO_MANY_SOURCE_FILES = "too_many_source_files"


@dataclass(frozen=True)
class FilterResult:
    """Outcome of filtering one instance.

    ``files`` is the Ground-Truth File Set when the instance is kept, and
    ``None`` when it is dropped. Exactly one of ``files`` / ``drop_reason`` is
    set.
    """

    files: tuple[str, ...] | None
    drop_reason: str | None

    @property
    def kept(self) -> bool:
        return self.files is not None


def is_source_file(path: str) -> bool:
    """True if ``path`` counts as source for the Ground-Truth File Set.

    Excludes test files, documentation, and configuration. See ADR-0001 for why
    test files are treated as a consequence of a fix rather than its location.
    """
    raise NotImplementedError


def filter_ground_truth_files(
    changed_files: Sequence[str],
    max_source_files: int = MAX_SOURCE_FILES,
) -> FilterResult:
    """Apply the Instance Filter to the files a fixing PR modified.

    Keeps source files only, then drops the whole instance if more than
    ``max_source_files`` remain -- such a PR is a refactor, and "where is the
    bug" has no single answer for it.

    Returned file order matches input order, so results are deterministic.
    """
    raise NotImplementedError
