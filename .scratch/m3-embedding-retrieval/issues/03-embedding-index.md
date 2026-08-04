# 03 — Blob-keyed embedding index

Status: done

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
- [02 — Pick the embedding model](02-embedding-model-adr.md) — settles local vs hosted
- [07 — Local embedding model bake-off](07-embedding-model-bakeoff.md) — settles **which** local model

Issue 06 was added after 01 measured a 9pp recall drop from chunking. It decides whether an AST Chunk should carry its body, which is the content this issue pays to embed. Building the index first would spend real money on documents already known to be missing the tokens reports quote most.

Issue 07 was added after ADR-0007's model pin turned out to rest on a stale candidate set. It decides the model, its context limit, and therefore this index's dimensions, disk size, and build time — every parameter this issue is built around.

## Comments

**Closed 2026-08-04.** `faultloc index --split dev` built the whole dev-split index at code `a1298ec`.

```
blobs       32,667 (31,623 embedded, 1,044 reused)
chunks      983,357 embedded
index size  1.56 GB
wall clock  153.2m
cost        $0.00
```

### The estimates held

The Notes asked for the actual distinct-blob count against ADR-0007's figure, because that estimate drove the cost decision. **32,667 — exact.** Index size 1.56 GB against an estimated 1.56 GB. Build time 153 minutes against ~3.7 hours estimated from issue 07's throughput, so the estimate was conservative by about a third, which is the direction an estimate should err.

Chunks embedded is 983,357 rather than the corpus's 1,013,340 because 29,983 belonged to the 1,044 blobs the earlier smoke run had already written. The two sum exactly, which is the arithmetic check that the reuse path skipped work rather than losing it.

### Resumability was exercised, not just tested

Those 1,044 reused blobs were written by a two-instance smoke run before the full build started. So the resume path ran for real on a 2.5-hour job, not only in a unit test — the full build picked up what existed and embedded the rest.

### Throughput fell and then recovered

Measured from the index growing on disk, in blobs per second: 3.3 → 2.2 → 1.4 → 1.7 → 2.1. Because every chunk is exactly 1,536 bytes on disk, the bytes-per-blob figure gives chunks per blob directly, and it moved the opposite way — 26.3 → 33.8 → ~41 → ~34. The rate tracks file size, not any degradation: the middle of the run hit a stretch of unusually large Django files.

One avoidable inefficiency, left alone: batches are 256 texts with no length sorting, and `sentence-transformers` pads every sequence in a batch to the longest in it. A single 512-token window among 255 short function chunks makes all 256 compute at 512. Sorting by length before batching would recover some of it. Not pursued because the build is a one-off and the real per-query cost is what rung 2 reports.

### A counting bug in a published figure

The first run reported **32,686 blobs against 32,667 files on disk.** One blob can be reachable at several paths in the same commit, and each path added it to the wanted list again.

The index was never wrong — it is keyed by content, and `read_blobs` returns a dict — but the reported number was, and reported numbers are half of what this project ships. Fixed in `e8af1e2`.

The test for it is worth noting. The first version passed with *and* without the fix: on the fresh path `read_blobs` collapses the duplicate on its own, so the miscount only appears on the reused path. Rewritten to build twice, then verified failing before the fix and passing after — rather than assumed, which is the mistake M1 made once with an `or True` assertion.
