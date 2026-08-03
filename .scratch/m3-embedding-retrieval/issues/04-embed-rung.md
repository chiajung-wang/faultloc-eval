# 04 — Rung 2: embedding retrieval end to end

Status: ready-for-agent

## Parent

[M3 PRD](../PRD.md)

## What to build

The rung itself. Embed the issue text, rank AST Chunks by similarity against the cached index, aggregate chunks to files with the rule fixed in issue 01, and return a `Prediction` carrying **real** `cost_usd` and `latency_s`.

End to end: `faultloc evaluate --rung embed --split dev` prints the metrics and prepends a `RESULTS.md` entry, unchanged in format from rung 1's.

The rung reads the index; it does not build it. A missing or incomplete index is a clear error telling the user to run `faultloc index`, not a silent slow path that quietly spends money mid-evaluation.

Cost accounting starts mattering here. Rung 1 reported `$0.00` and the field existed anyway (`Prediction.cost_usd`, `rungs/__init__.py`) precisely so this rung would have nothing to retrofit. Query-embedding cost is per instance; index cost is amortised — state in the closing comment which of the two the reported per-instance figure includes, because the two answer different questions and a reader cannot tell them apart from a single number.

## Acceptance criteria

- [ ] `faultloc evaluate --rung embed --split dev` runs end to end and emits a `RESULTS.md` entry
- [ ] Ranked files produced by aggregating chunk scores with the rule from issue 01, unmodified
- [ ] `latency_s` and `cost_usd` are measured per instance, not zeros or constants
- [ ] Deterministic: same Instance, same ranking, every run
- [ ] Missing or stale index fails loudly with the command to fix it
- [ ] `no_candidates` returned when the instance's repo yields no indexed chunks
- [ ] The harness is untouched — scorer, loader, splits, and results log take this rung without modification
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

If the harness needs changing to accept this rung, that is worth a line in the closing comment: ADR-0003 claims the rung contract was fixed before the first rung existed, and this is the first real test of that claim.

Same dev split, same frozen seed. The test split stays untouched until M7.

## Blocked by

- [03 — Blob-keyed embedding index](03-embedding-index.md)
