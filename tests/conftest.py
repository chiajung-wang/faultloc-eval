"""Shared fixtures.

The git fixture builds a real repository rather than mocking `subprocess`. The
modules under test exist to drive git correctly, and a mock would only assert
that git is called the way the author already believes it should be.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from faultloc.repos import RepoStore


@dataclass(frozen=True)
class Fixture:
    """A bare clone with two commits, mirroring the real `data/repos/` layout."""

    store: RepoStore
    first: str
    second: str

    repo: str = "acme/widget"


def git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, text=True)
    return result.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Fixture:
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
