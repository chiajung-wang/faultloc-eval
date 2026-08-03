# 04 — Check out repos at base commit and enumerate files

Status: done

## Context

Each Instance pins a `base_commit`. Retrieval must see the repository as it was at that commit, or the candidate file list is wrong.

Roughly 12 repos across ~500 distinct commits. Cloning per instance is wasteful; one bare clone per repo plus a worktree or archive per commit is not.

## Acceptance criteria

- One clone per repo, cached on disk under `data/repos/` (gitignored)
- Enumerating source files at a given `(repo, base_commit)` returns paths matching what the Instance Filter considers source
- Cache is content-addressed by commit SHA and survives process restarts
- No network access needed on a warm cache

## Notes

This is where the per-commit indexing cost noted in `docs/PRD.md` first appears. Solve it for file enumeration now; the same cache shape should serve rung-2 indexing later.

## Comments

**Closed 2026-08-03.** `src/faultloc/repos.py`, 18 tests.

**The most important result — every ground-truth file is reachable:**

```
instances 490
candidate files per instance: min 35  median 849  max 3619
ground-truth files NOT in candidate set: 0
```

`list_source_files` and the Ground-Truth File Set are filtered by the same `is_source_file`. Had they disagreed, some instances would have been unwinnable, and that would have surfaced as a weak retriever rather than as a bug — weeks of tuning a model against impossible questions. The accuracy ceiling is 100%, so every point below it is the rung's own fault, which is what the benchmark is supposed to measure.

**No worktrees at all.** A bare clone holds every commit's tree, so `git ls-tree` enumerates and `git cat-file` reads straight from the object store. Nothing is written to a working directory.

```
cold (building cache)   14.3s
warm                     5.1s
clones                  1.7 GB
listing cache           202 MB, 489 entries
```

489 entries for 490 instances: two instances share a base commit and the cache dedupes them for free. The per-instance worktree approach this replaces would have been roughly 25 GB.

**The cache key is the commit SHA alone.** A commit's tree is immutable, so an entry cannot go stale — there is no invalidation logic to get wrong. Asserted by a test that deletes the clone and still reads successfully. Entries are written to a temporary name and renamed, so an interrupted run cannot leave a half-written entry that a later read treats as complete.

**Each entry records the blob SHA of every file**, which is the shape M3 needs:

```
file-instances   927,014
distinct blobs    43,442
reuse factor        21.3x
```

The same file, byte-identical, appears an average of 21 times across the 490 instances. Keying rung-2 chunking and embedding on blob SHA therefore costs 43k units of work rather than 927k — measured now rather than assumed later.

**Two exception types**, because the fixes differ: `RepoUnavailableError` (never cloned) and `CommitUnavailableError` (clone present, commit absent — a force-push or fork-only PR would cause this). All 500 base commits were verified reachable from a plain bare clone before any of this was written, so the second path is defensive rather than observed.

Tests build a real two-commit git repository in a temporary directory rather than mocking `subprocess`. A mock would only assert that git is called the way the author already believes it should be called; if that belief is wrong, the mock is wrong identically and everything passes.

Known trade-off, deferred: 202 MB of cache buys about 9 seconds. It is justified by the blob SHAs rather than by the time saved. Gzip would cut it to roughly 40 MB for one line — worth doing when M3 starts.
