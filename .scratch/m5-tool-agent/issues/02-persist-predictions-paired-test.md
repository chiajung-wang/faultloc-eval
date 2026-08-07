# 02 — Persist per-instance predictions, and add the paired test

Status: ready-for-agent

## Parent

[M5 PRD](../PRD.md)

## What to build

Two things, and both are free.

**Persist every run's per-instance predictions.** The evaluate command builds a list of `Prediction` objects, scores them, and drops them. Nothing survives a run except the aggregate `RESULTS.md` entry. So no rung can be compared to another one per Instance, and the failure taxonomy that later milestones need has no input.

Write them to disk beside the entry, keyed so a reader can find the run that produced them. One record per Instance: the ranked files, the Stop Condition, the cost, and the latency.

**Add a paired test for a rung-against-rung delta.** McNemar over the discordant Instances, which are the ones where exactly one of the two rungs was right at rank 1. Report the discordant counts both ways, and the p-value.

The report keeps its Wilson intervals. They are the right instrument for a single row's Top-1, and `CLAUDE.md` requires them. They are the wrong instrument for a delta between two rungs that ran on the same Instances. **State which test licenses which claim**, rather than print both and leave a reader to choose.

Backfill the free rungs. Rungs 1 through 2.6 cost nothing to re-run, so every one of them can have persisted predictions. Rung 3's ladder-row cell replays from the response cache. The other three rung-3 cells would cost money, so leave them.

Add a command that takes two persisted runs and prints the paired comparison.

## Acceptance criteria

- [ ] Every evaluate run writes per-instance predictions to disk, and a reader can trace them to the `RESULTS.md` entry
- [ ] A truncated run (`--limit`) writes predictions but still refuses a results entry, as it does now
- [ ] McNemar over discordant Instances, with both discordant counts and the p-value reported
- [ ] The paired comparison is reachable from the CLI for any two persisted runs
- [ ] Wilson intervals stay on the per-row report, unchanged
- [ ] Persisted predictions for every free rung, backfilled
- [ ] Tests cover the McNemar arithmetic against hand-computed cases, including the zero-discordant case
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

**This blocks the publish issue, and that is the point.** The test split stays closed until M7, so n cannot grow past 244. A realistic rung-4 result of 78-82% is a delta of 4 to 8 percentage points against a ±6pp interval. Two overlapping marginal intervals would report "nothing established" for the most expensive milestone in this project, when the paired data may well establish it.

**Choose the test now, before any rung-4 number exists.** ADR-0008 declared its ladder row in advance for the same reason. A test picked after seeing the numbers looks chosen to fit them.

Zero discordant Instances is a real case and it must not divide by zero. Two rungs that agree everywhere have no delta to test.

M3 is worth re-reading with this in place. Its conclusion was that embeddings and lexical retrieval are indistinguishable, and that conclusion rests on overlapping unpaired intervals. Do not restate M3's finding in this issue. Persist the predictions, and let a later reader ask the question with the right instrument.

## Blocked by

None - can start immediately.
