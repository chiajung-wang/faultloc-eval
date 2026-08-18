# 03 — Fresh Set loader and dataset provenance, proved by a free rung

Status: ready-for-agent

## Parent

[M6 PRD](../PRD.md)

## What to build

The path from the frozen artifact to a real `RESULTS.md` entry, proved end to end for **$0**.

`Instance` is already source-agnostic, so no rung changes. Three things do not exist:

- A loader for the frozen artifact, in the shape of `dataset/verified.py`.
- A way to select it. `evaluate` and `index` take `--split dev | test`, and the Fresh Set is neither. It is a different dataset with no split.
- Correct provenance. `evaluate` stamps every entry with `DATASET_ID` and `DATASET_REVISION` imported from `verified.py`, so a Fresh run today would publish a SWE-bench revision against Fresh numbers.

The Fresh Set's revision is the artifact's content hash from issue 02.

**The slice is complete when `faultloc evaluate --rung bm25` against the Fresh Set writes a correct `RESULTS.md` entry.** That single free run exercises the loader, the selection flag, provenance, the bare-clone checkout at post-2026 commits, the scorer, and the reporter. Every paid issue afterwards rides a path already known to work.

Report per-repo Top-1 as always, and the Filter Rate, and the repo mix. Issue 05 needs the mix.

## Acceptance criteria

- [ ] A loader reads the frozen artifact into Instances and reports its Filter Rate
- [ ] `evaluate` and `index` can select the Fresh Set, and the flag reads clearly against `--split`
- [ ] A `RESULTS.md` entry from a Fresh run names the Fresh Set and its content hash, never SWE-bench's revision
- [ ] `faultloc evaluate --rung bm25` on the Fresh Set writes a real entry from a clean tree
- [ ] Per-repo Top-1 and the repo mix are reported
- [ ] Rung 1 stays runnable without the `embed` extra
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

This is the tracer bullet. It costs nothing and it retires most of the plumbing risk before any money moves.

**A run's own `RESULTS.md` write dirties the tree for the next run.** Commit between runs. A dirty tree stamps `-dirty` on `code_version` and the entry is discarded.

## Blocked by

- [02 — `faultloc mine`](02-mine-and-freeze.md)
