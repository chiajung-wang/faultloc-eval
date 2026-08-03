"""Read repository contents at a pinned commit, without checking anything out.

Each Instance pins a `base_commit`, and retrieval must see the repository as it
was then. The obvious approach -- a worktree per instance -- would materialise
roughly 500 checkouts and tens of gigabytes.

It is unnecessary. A bare clone already holds every commit's full tree, so
`git ls-tree` enumerates a commit's files and `git cat-file` reads them straight
out of the object store. Nothing is ever written to a working directory. The 12
repositories of the Verified Set come to about 1.7 GB in total.

Listings are cached to disk keyed by commit SHA, and each entry records the blob
SHA of every file. That is the shape rung 2 needs: most files are byte-identical
across the 499 distinct commits, so a blob SHA is the natural key for reusing a
chunk or an embedding instead of recomputing it per instance.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from faultloc.dataset.filters import is_source_file

DEFAULT_REPO_ROOT = Path("data/repos")
DEFAULT_CACHE_ROOT = Path("data/cache/trees")

#: `git ls-tree -r` emits `<mode> <type> <object>\t<path>`.
LS_TREE_FIELDS = 3


class RepoUnavailableError(RuntimeError):
    """A repository has not been cloned yet."""


class CommitUnavailableError(RuntimeError):
    """A commit is missing from the local clone.

    Distinct from a missing repository: this means the clone exists but does not
    contain the pinned commit, which a force-push or a fork-only PR can cause.
    """


@dataclass(frozen=True)
class RepoFile:
    """One file in a commit's tree.

    `blob` is git's content hash. Two paths with the same blob have byte-identical
    contents, in the same repository or a different one.
    """

    path: str
    blob: str


def repo_slug(repo: str) -> str:
    """`django/django` -> `django__django`, matching the instance_id prefix."""
    return repo.replace("/", "__")


class RepoStore:
    """Bare clones on disk, plus a listing cache keyed by commit SHA."""

    def __init__(
        self,
        root: Path = DEFAULT_REPO_ROOT,
        cache_root: Path = DEFAULT_CACHE_ROOT,
    ) -> None:
        self.root = Path(root)
        self.cache_root = Path(cache_root)

    def clone_path(self, repo: str) -> Path:
        return self.root / f"{repo_slug(repo)}.git"

    def has_clone(self, repo: str) -> bool:
        return self.clone_path(repo).is_dir()

    def ensure_clone(self, repo: str) -> Path:
        """Clone `repo` bare if it is not already on disk.

        The only method here that touches the network, and only on a cold cache.
        Bare rather than mirrored: a mirror also drags in pull-request refs and
        configures push refspecs, neither of which this project wants.
        """
        path = self.clone_path(repo)
        if path.is_dir():
            return path

        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--bare", "--quiet", f"https://github.com/{repo}", str(path)],
            check=True,
        )
        return path

    def has_commit(self, repo: str, commit: str) -> bool:
        if not self.has_clone(repo):
            return False
        result = subprocess.run(
            ["git", "-C", str(self.clone_path(repo)), "cat-file", "-e", f"{commit}^{{commit}}"],
            capture_output=True,
        )
        return result.returncode == 0

    def list_files(self, repo: str, commit: str) -> tuple[RepoFile, ...]:
        """Every file in the repository at `commit`, cached on disk.

        The cache key is the commit SHA alone: a commit's tree is immutable, so
        an entry can never go stale. That also makes it safe across process
        restarts and safe to share between instances pinned to the same commit.
        """
        cached = self._read_cache(repo, commit)
        if cached is not None:
            return cached

        files = self._ls_tree(repo, commit)
        self._write_cache(repo, commit, files)
        return files

    def list_source_files(self, repo: str, commit: str) -> tuple[RepoFile, ...]:
        """Candidate files for retrieval.

        Filtered with the same `is_source_file` that builds the Ground-Truth
        File Set. If the two disagreed, a ground-truth file could be absent from
        the candidate set and no prediction could ever be correct -- a silent
        ceiling on accuracy that would look like a bad retriever.
        """
        return tuple(f for f in self.list_files(repo, commit) if is_source_file(f.path))

    def read_blob(self, repo: str, blob: str) -> str:
        """Contents of a blob by its hash.

        Decoded with `errors="replace"`: these repositories contain fixtures
        that are deliberately not valid UTF-8, and a retriever should skip past
        mojibake rather than crash the run.
        """
        result = subprocess.run(
            ["git", "-C", str(self._require_clone(repo)), "cat-file", "blob", blob],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise CommitUnavailableError(f"blob {blob} not found in {repo}")
        return result.stdout.decode("utf-8", errors="replace")

    def read_blobs(self, repo: str, blobs: Sequence[str]) -> dict[str, str]:
        """Read many blobs in one `git cat-file --batch` process.

        A subprocess per file would be about 900,000 spawns across the Verified
        Set, which dominates everything else the rung does. One process reading
        a stream of hashes turns that into one spawn per instance.

        Missing hashes are omitted from the result rather than raising: a caller
        asking for a batch wants the batch, and can compare keys if it cares.
        """
        if not blobs:
            return {}

        result = subprocess.run(
            ["git", "-C", str(self._require_clone(repo)), "cat-file", "--batch"],
            input="\n".join(blobs).encode(),
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise CommitUnavailableError(f"batch read failed for {repo}")

        contents: dict[str, str] = {}
        buffer = result.stdout
        offset = 0
        while offset < len(buffer):
            newline = buffer.find(b"\n", offset)
            if newline == -1:
                break
            header = buffer[offset:newline].split()
            offset = newline + 1
            if len(header) != LS_TREE_FIELDS:  # "<sha> missing" is two fields
                continue
            sha, _kind, size = header
            length = int(size)
            contents[sha.decode()] = buffer[offset : offset + length].decode(
                "utf-8", errors="replace"
            )
            offset += length + 1  # git appends a newline after each payload
        return contents

    def read_file(self, repo: str, commit: str, path: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self._require_clone(repo)), "cat-file", "-p", f"{commit}:{path}"],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise CommitUnavailableError(f"{path} not found in {repo} at {commit}")
        return result.stdout.decode("utf-8", errors="replace")

    def _require_clone(self, repo: str) -> Path:
        path = self.clone_path(repo)
        if not path.is_dir():
            raise RepoUnavailableError(
                f"no clone for {repo} at {path}. Run RepoStore.ensure_clone({repo!r}) first."
            )
        return path

    def _ls_tree(self, repo: str, commit: str) -> tuple[RepoFile, ...]:
        result = subprocess.run(
            ["git", "-C", str(self._require_clone(repo)), "ls-tree", "-r", commit],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise CommitUnavailableError(f"commit {commit} not found in {repo}")

        files = []
        for line in result.stdout.decode("utf-8", errors="replace").splitlines():
            meta, _, path = line.partition("\t")
            fields = meta.split()
            if len(fields) != LS_TREE_FIELDS or not path:
                continue
            _mode, kind, blob = fields
            if kind == "blob":  # skip submodules, which have no readable content
                files.append(RepoFile(path=path, blob=blob))
        return tuple(files)

    def _cache_path(self, repo: str, commit: str) -> Path:
        return self.cache_root / repo_slug(repo) / f"{commit}.json"

    def _read_cache(self, repo: str, commit: str) -> tuple[RepoFile, ...] | None:
        path = self._cache_path(repo, commit)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text())
        return tuple(RepoFile(path=entry["path"], blob=entry["blob"]) for entry in payload)

    def _write_cache(self, repo: str, commit: str, files: tuple[RepoFile, ...]) -> None:
        path = self._cache_path(repo, commit)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [{"path": f.path, "blob": f.blob} for f in files]
        # Write then rename: an interrupted run must not leave a half-written
        # cache entry that later reads would treat as complete.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(path)
