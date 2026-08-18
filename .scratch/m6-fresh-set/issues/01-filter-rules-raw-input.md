# 01 — Instance Filter: two rules for raw input, and the raw Filter Rate

Status: ready-for-agent

## Parent

[M6 PRD](../PRD.md)

## What to build

Two rules in the Instance Filter, and the first Filter Rate ever measured over raw pull request file lists.

[ADR-0001](../../../docs/adr/0001-ground-truth-file-set.md)'s 2026-08-18 amendment states both rules. The filter drops a file whose basename holds no extension. It also drops test infrastructure: a basename containing `_testing`, and `conftest.py`.

The filter stays a deny-list. ADR-0001 chose that so a `.pyx`, `.c` or `.js` fix is never dropped in silence, and this issue does not reverse it.

**The rules must be inert on the Verified Set, and a test must prove it.** A sampling script measured 0 of 490 Instances holding either kind of file. Assert that in the test suite, so a later widening of either rule cannot quietly change what every published number means.

Also report the Filter Rate over raw input. The Verified Set separates `patch` from `test_patch`, so test-stripping fired zero times there. A raw pull request file list mixes both, and a 56-PR sample fired test-stripping on 38 of them. The counter must break the rate down per drop reason, as ADR-0001 requires, and the new rules need reasons of their own rather than folding into `no_source_files`.

## Acceptance criteria

- [ ] `filter_ground_truth_files` drops a file whose basename holds no extension
- [ ] It drops a basename containing `_testing`, and `conftest.py`
- [ ] A test asserts that both rules change 0 of the 490 Verified Instances
- [ ] Each new rule carries its own drop reason, counted and reported separately
- [ ] Unit tests cover raw pull request file lists that mix source, tests, docs, and extensionless files
- [ ] The module stays pure: no I/O, no network, no model calls
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

This runs first because the frozen Fresh Set bakes in whatever the filter says. A rule that lands after the freeze invalidates the artifact, and issue 08 spends money against it.

**Watch each test fail before you make it pass.** Three near-vacuous tests shipped in this repo before being caught. The inertness test is the one at risk: it passes trivially if the rule never fires anywhere, which is also what a broken rule looks like.

## Blocked by

None - can start immediately.
