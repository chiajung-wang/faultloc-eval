# 01 — Implement the Instance Filter

Status: ready-for-agent

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
