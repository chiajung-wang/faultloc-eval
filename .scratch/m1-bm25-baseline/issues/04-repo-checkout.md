# 04 — Check out repos at base commit and enumerate files

Status: ready-for-agent

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
