# 01 — Implement the Instance Filter

Status: done

## Context

`src/faultloc/dataset/filters.py` has the contract and docstrings; `tests/test_filters.py` has the tests. Both are written. The implementation raises `NotImplementedError`.

Rules are specified in [ADR-0001](../../../docs/adr/0001-ground-truth-file-set.md).

## Acceptance criteria

- `is_source_file` and `filter_ground_truth_files` implemented
- `uv run pytest` passes with no changes to the test file
- Module stays pure — no I/O, no network, no model calls
- `uv run ruff check` clean

## Notes

If a test looks wrong, say so rather than editing it to pass. The tests encode ADR-0001; changing them changes the benchmark's definition.

## Comments

**Closed 2026-08-03.** 36 tests pass, `ruff check` clean, no test edits made to satisfy the implementation.

Commits on `m1-bm25-baseline`:

| Commit | What |
|---|---|
| `00f2d92` | `feat: implement the instance filter` — the two functions, deny-list design |
| `892930b` | `docs: record measured filter rate in ADR-0001` — validation over all 500 gold patches |
| `e54a707` | `test: pin the deny-list and path-prefix behaviour` — no behaviour change |
| `04c38da` | `fix: dedupe paths and enforce the FilterResult invariant` — two gaps the original tests left undefined |

The classifier is a **deny-list**: anything not recognised as test, doc, or config counts as source. An allow-list of known code extensions would have passed every original test while silently dropping the `.pyx`, `.c`, and `.js` files real fixes touch, and a dropped ground-truth file is indistinguishable from a wrong prediction downstream. Pinned by `test_non_python_code_is_source` rather than left to a comment.

Two behaviours the original tests left undefined, decided here: duplicate paths collapse to first occurrence (the cap counts distinct files, not diff entries), and `FilterResult` now rejects having both or neither of `files`/`drop_reason` set.

Measured over all 500 real gold patches: **490 kept, 10 dropped, every drop from the >3-file cap and none from non-source stripping** — SWE-bench splits `patch` from `test_patch` upstream, so no test file ever reaches the filter. Recorded in ADR-0001 so the published Filter Rate is not credited to rules that did no work on this dataset.
