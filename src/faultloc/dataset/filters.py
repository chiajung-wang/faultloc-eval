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

    def __post_init__(self) -> None:
        if (self.files is None) == (self.drop_reason is None):
            raise ValueError(
                "exactly one of files / drop_reason must be set, "
                f"got files={self.files!r} drop_reason={self.drop_reason!r}"
            )

    @property
    def kept(self) -> bool:
        return self.files is not None


def _is_test_file(path: str) -> bool:
    """True if ``path`` is test code, by directory or by filename."""
    segments = path.split("/")
    if any(f"{segment}/" in TEST_MARKERS for segment in segments[:-1]):
        return True

    filename = segments[-1]
    return filename.startswith(TEST_FILE_PREFIX) or filename.endswith(TEST_FILE_SUFFIX)


def is_source_file(path: str) -> bool:
    """True if ``path`` counts as source for the Ground-Truth File Set.

    Excludes test files, documentation, and configuration. See ADR-0001 for why
    test files are treated as a consequence of a fix rather than its location.

    Deliberately a deny-list: anything not recognised as test, doc, or config is
    source. An allow-list of known code extensions would silently drop the
    ``.pyx``, ``.c``, and ``.js`` files that real fixes touch, and a dropped
    ground-truth file is indistinguishable from a wrong prediction downstream.
    """
    if _is_test_file(path):
        return False

    segments = path.split("/")
    if any(f"{segment}/" in NON_SOURCE_DIRS for segment in segments[:-1]):
        return False

    return not path.endswith(NON_SOURCE_SUFFIXES)


def filter_ground_truth_files(
    changed_files: Sequence[str],
    max_source_files: int = MAX_SOURCE_FILES,
) -> FilterResult:
    """Apply the Instance Filter to the files a fixing PR modified.

    Keeps source files only, then drops the whole instance if more than
    ``max_source_files`` remain -- such a PR is a refactor, and "where is the
    bug" has no single answer for it.

    Duplicate paths collapse to their first occurrence: the cap counts distinct
    source files, and one file listed twice is still one location.

    Returned file order matches input order, so results are deterministic.
    """
    source_files = tuple(dict.fromkeys(path for path in changed_files if is_source_file(path)))

    if not source_files:
        return FilterResult(files=None, drop_reason=DropReason.NO_SOURCE_FILES)

    if len(source_files) > max_source_files:
        return FilterResult(files=None, drop_reason=DropReason.TOO_MANY_SOURCE_FILES)

    return FilterResult(files=source_files, drop_reason=None)
