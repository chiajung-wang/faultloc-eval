# 03 — Blob-keyed embedding index

Status: ready-for-agent

## Parent

[M3 PRD](../PRD.md)

## What to build

A command that builds and caches chunk embeddings for a split — `faultloc index --split dev` — reporting how many chunks it embedded, how many it reused, what it cost, and how long it took.

Separate from the rung on purpose. Indexing every distinct blob in the split is a long, costed, interruptible job; a rung that rebuilt its index inside the prediction loop is the same bug found and fixed in M1 issue 07, where a per-instance rung discarded the blob-keyed token cache and turned eighty seconds into half an hour.

Keyed by blob SHA, matching `RepoStore`'s existing tree cache. A blob SHA is a content hash, so an entry can never go stale, is safe across process restarts, and is shared by every instance and repository containing that content.

Resumable. An interrupted build must not lose completed work, and must not leave a half-written entry that a later read treats as complete — `RepoStore._write_cache` already establishes the write-then-rename pattern for this.

Cost is measured and returned, not estimated. If the chosen model is hosted, this command is where real dollars first appear in the project, and the figure it reports is what the rung-2 cost column is built from.

## Acceptance criteria

- [ ] `faultloc index --split dev` embeds every chunk needed by the split and caches vectors keyed by blob SHA
- [ ] Re-running is near-free: reports reused vs newly embedded counts
- [ ] Resumable — an interrupted run loses no completed work and writes no partial entries
- [ ] Reports chunk count, distinct-blob count, wall-clock, and cost in dollars
- [ ] Model identifier and revision stored alongside the vectors, so a cache built by a different model can never be read as if it matched
- [ ] `uv run pytest` and `uv run ruff check` clean; tests do not call a hosted API

## Notes

Store enough to detect a mismatch, not just to serve a lookup. Vectors from two different models are indistinguishable once written, and silently mixing them would produce a plausible-looking number with no valid provenance.

Report the actual distinct-blob count against the estimate made in ADR-0007. If they differ materially, say so — the estimate drove the cost decision.

## Blocked by

- [01 — BM25 over AST Chunks](01-bm25-over-chunks.md) — supplies the chunker
- [06 — Chunks with bodies](06-chunks-with-bodies.md) — settles **what** gets embedded
- [02 — Pick the embedding model](02-embedding-model-adr.md) — supplies the model

Issue 06 was added after 01 measured a 9pp recall drop from chunking. It decides whether an AST Chunk should carry its body, which is the content this issue pays to embed. Building the index first would spend real money on documents already known to be missing the tokens reports quote most.
