"""Tests for reading repository contents at a pinned commit.

These build a real git repository in a temporary directory rather than mocking
subprocess. The whole point of this module is that it drives git correctly, and
a mock would only assert that we call git the way we already think we do.

Two commits are created so that "the same path has different contents at
different commits" -- the property the entire per-commit design exists for --
can actually be asserted.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from faultloc.repos import (
    CommitUnavailableError,
    RepoStore,
    RepoUnavailableError,
    repo_slug,
)


@dataclass(frozen=True)
class Fixture:
    store: RepoStore
    first: str
    second: str


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Fixture:
    """A bare clone with two commits, mirroring the real layout."""
    work = tmp_path / "work"
    work.mkdir()
    git("init", "-q", "-b", "main", cwd=work)
    git("config", "user.email", "t@example.com", cwd=work)
    git("config", "user.name", "Test", cwd=work)

    (work / "pkg").mkdir()
    (work / "pkg" / "core.py").write_text("def first(): ...\n")
    (work / "pkg" / "util.py").write_text("SHARED = 1\n")
    (work / "tests").mkdir()
    (work / "tests" / "test_core.py").write_text("def test_first(): ...\n")
    (work / "README.md").write_text("# docs\n")
    git("add", "-A", cwd=work)
    git("commit", "-qm", "first", cwd=work)
    first = git("rev-parse", "HEAD", cwd=work)

    (work / "pkg" / "core.py").write_text("def second(): ...\n")
    (work / "pkg" / "added.py").write_text("NEW = True\n")
    git("add", "-A", cwd=work)
    git("commit", "-qm", "second", cwd=work)
    second = git("rev-parse", "HEAD", cwd=work)

    root = tmp_path / "repos"
    root.mkdir()
    subprocess.run(
        ["git", "clone", "--bare", "-q", str(work), str(root / "acme__widget.git")],
        check=True,
    )

    return Fixture(
        store=RepoStore(root=root, cache_root=tmp_path / "cache"),
        first=first,
        second=second,
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
