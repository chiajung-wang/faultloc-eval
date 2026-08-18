"""Tests for reading repository contents at a pinned commit.

These build a real git repository in a temporary directory rather than mocking
subprocess. The whole point of this module is that it drives git correctly, and
a mock would only assert that we call git the way we already think we do.

Two commits are created so that "the same path has different contents at
different commits" -- the property the entire per-commit design exists for --
can actually be asserted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import Fixture

from faultloc.repos import (
    CommitUnavailableError,
    RepoStore,
    RepoUnavailableError,
    repo_slug,
)


class TestRepoSlug:
    def test_matches_the_instance_id_prefix(self) -> None:
        assert repo_slug("django/django") == "django__django"
        assert repo_slug("scikit-learn/scikit-learn") == "scikit-learn__scikit-learn"


class TestListFiles:
    def test_lists_every_file_at_a_commit(self, repo: Fixture) -> None:
        paths = {f.path for f in repo.store.list_files("acme/widget", repo.first)}
        assert paths == {"pkg/core.py", "pkg/util.py", "tests/test_core.py", "README.md"}

    def test_different_commits_give_different_trees(self, repo: Fixture) -> None:
        """The reason the whole design is per-commit rather than per-repo."""
        first = {f.path for f in repo.store.list_files("acme/widget", repo.first)}
        second = {f.path for f in repo.store.list_files("acme/widget", repo.second)}

        assert "pkg/added.py" not in first
        assert "pkg/added.py" in second

    def test_records_blob_shas(self, repo: Fixture) -> None:
        files = repo.store.list_files("acme/widget", repo.first)
        assert all(len(f.blob) == 40 for f in files)

    def test_unchanged_files_share_a_blob_across_commits(self, repo: Fixture) -> None:
        """This is what makes rung-2 index reuse possible.

        Most files are byte-identical across the 499 distinct base commits, so
        keying work on the blob SHA lets a chunk or embedding be computed once
        instead of once per instance.
        """

        def blob_of(commit: str, path: str) -> str:
            return next(
                f.blob for f in repo.store.list_files("acme/widget", commit) if f.path == path
            )

        assert blob_of(repo.first, "pkg/util.py") == blob_of(repo.second, "pkg/util.py")
        assert blob_of(repo.first, "pkg/core.py") != blob_of(repo.second, "pkg/core.py")


class TestListSourceFiles:
    def test_uses_the_same_rule_as_the_ground_truth(self, repo: Fixture) -> None:
        """Candidates and ground truth must agree on what counts as source.

        If they disagreed, a ground-truth file could be missing from the
        candidate set, making a correct prediction impossible -- a silent
        ceiling on accuracy that would read as a bad retriever.
        """
        paths = {f.path for f in repo.store.list_source_files("acme/widget", repo.first)}
        assert paths == {"pkg/core.py", "pkg/util.py"}


class TestReading:
    def test_reads_a_file_at_a_commit(self, repo: Fixture) -> None:
        assert (
            repo.store.read_file("acme/widget", repo.first, "pkg/core.py") == "def first(): ...\n"
        )

    def test_the_same_path_reads_differently_at_another_commit(self, repo: Fixture) -> None:
        assert (
            repo.store.read_file("acme/widget", repo.second, "pkg/core.py") == "def second(): ...\n"
        )

    def test_reads_a_blob_by_hash(self, repo: Fixture) -> None:
        files = repo.store.list_files("acme/widget", repo.first)
        blob = next(f.blob for f in files if f.path == "pkg/util.py")
        assert repo.store.read_blob("acme/widget", blob) == "SHARED = 1\n"

    def test_missing_path_raises(self, repo: Fixture) -> None:
        with pytest.raises(CommitUnavailableError):
            repo.store.read_file("acme/widget", repo.first, "pkg/added.py")


class TestCache:
    def test_survives_a_new_store_instance(self, repo: Fixture, tmp_path: Path) -> None:
        """ "Survives process restarts" means the cache is on disk, not in memory."""
        expected = repo.store.list_files("acme/widget", repo.first)

        fresh = RepoStore(root=tmp_path / "repos", cache_root=tmp_path / "cache")
        assert fresh.list_files("acme/widget", repo.first) == expected

    def test_is_keyed_by_commit_sha(self, repo: Fixture, tmp_path: Path) -> None:
        repo.store.list_files("acme/widget", repo.first)
        repo.store.list_files("acme/widget", repo.second)

        entries = sorted(p.name for p in (tmp_path / "cache" / "acme__widget").glob("*.json"))
        assert entries == sorted([f"{repo.first}.json", f"{repo.second}.json"])

    def test_a_warm_cache_needs_no_repository(self, repo: Fixture, tmp_path: Path) -> None:
        """A commit's tree is immutable, so a cache entry can never go stale.

        Proven by deleting the clone: a warm read must still succeed.
        """
        expected = repo.store.list_files("acme/widget", repo.first)

        for path in sorted((tmp_path / "repos").rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        (tmp_path / "repos" / "acme__widget.git").mkdir(parents=True)

        assert repo.store.list_files("acme/widget", repo.first) == expected

    def test_does_not_leave_partial_entries(self, repo: Fixture, tmp_path: Path) -> None:
        repo.store.list_files("acme/widget", repo.first)
        assert not list((tmp_path / "cache").rglob("*.tmp"))


class TestMissingThings:
    def test_missing_clone_raises_with_a_usable_message(self, tmp_path: Path) -> None:
        store = RepoStore(root=tmp_path / "none", cache_root=tmp_path / "cache")
        with pytest.raises(RepoUnavailableError, match="ensure_clone"):
            store.list_files("acme/widget", "0" * 40)

    def test_missing_commit_raises(self, repo: Fixture) -> None:
        with pytest.raises(CommitUnavailableError):
            repo.store.list_files("acme/widget", "0" * 40)

    def test_has_commit_reports_presence(self, repo: Fixture) -> None:
        assert repo.store.has_commit("acme/widget", repo.first)
        assert not repo.store.has_commit("acme/widget", "0" * 40)

    def test_has_clone_reports_presence(self, repo: Fixture) -> None:
        assert repo.store.has_clone("acme/widget")
        assert not repo.store.has_clone("nobody/nothing")


class TestGrep:
    def test_finds_a_file_by_its_contents(self, repo: Fixture) -> None:
        assert repo.store.grep("acme/widget", repo.first, "def first") == ("pkg/core.py",)

    def test_searches_the_commit_it_is_given(self, repo: Fixture) -> None:
        """`pkg/core.py` says `def first` at one commit and `def second` at the next.

        A grep against the clone's default branch would answer for whichever
        commit that happens to be, and every Instance pins its own.
        """
        assert repo.store.grep("acme/widget", repo.first, "def second") == ()
        assert repo.store.grep("acme/widget", repo.second, "def second") == ("pkg/core.py",)

    def test_drops_non_source_files_from_the_matches(self, repo: Fixture) -> None:
        """`tests/test_core.py` also contains `first`, and it is not an answer.

        Filtered by the same `is_source_file` that builds the Ground-Truth File
        Set. If the two disagreed, a tool could offer a file that no prediction
        is ever scored against.
        """
        assert repo.store.grep("acme/widget", repo.first, "first") == ("pkg/core.py",)

    def test_searches_for_a_literal_string_and_not_a_pattern(self, repo: Fixture) -> None:
        """`f...t` is a regex that matches `first`, and a string that matches nothing.

        Bug reports quote error text full of dots, brackets and asterisks. Read
        as a regex, that text finds matches the reporter never wrote.
        """
        assert repo.store.grep("acme/widget", repo.first, "f...t") == ()
        assert repo.store.grep("acme/widget", repo.first, "def first(): ...") == ("pkg/core.py",)

    def test_does_not_reorder_what_the_search_returned(self, repo: Fixture) -> None:
        """A caller that truncates has to truncate the order the search produced.

        This catches a reordering, and it cannot catch a *sort*. Git walks a tree
        in byte order of the full path, which for these fixtures is the same
        order `sorted()` gives. So the test states the weaker guarantee it can
        actually hold: the method returns git's order and does not rearrange it.
        """
        assert repo.store.grep("acme/widget", repo.second, "E") == ("pkg/added.py", "pkg/util.py")

    def test_no_match_is_an_answer_and_not_a_failure(self, repo: Fixture) -> None:
        """git grep exits 1 when nothing matches, and that must not raise."""
        assert repo.store.grep("acme/widget", repo.first, "nothing here") == ()

    def test_a_missing_commit_raises(self, repo: Fixture) -> None:
        with pytest.raises(CommitUnavailableError):
            repo.store.grep("acme/widget", "0" * 40, "first")

    def test_a_missing_clone_raises(self, tmp_path: Path) -> None:
        store = RepoStore(root=tmp_path / "none", cache_root=tmp_path / "cache")
        with pytest.raises(RepoUnavailableError, match="ensure_clone"):
            store.grep("acme/widget", "0" * 40, "first")
