# 02 — Persist per-instance predictions, and add the paired test

Status: done

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

- [x] Every evaluate run writes per-instance predictions to disk, and a reader can trace them to the `RESULTS.md` entry
- [x] A truncated run (`--limit`) writes predictions but still refuses a results entry, as it does now
- [x] McNemar over discordant Instances, with both discordant counts and the p-value reported
- [x] The paired comparison is reachable from the CLI for any two persisted runs
- [x] Wilson intervals stay on the per-row report, unchanged
- [x] Persisted predictions for every free rung, backfilled
- [x] Tests cover the McNemar arithmetic against hand-computed cases, including the zero-discordant case
- [x] `uv run pytest` and `uv run ruff check` clean

## Notes

**This blocks the publish issue, and that is the point.** The test split stays closed until M7, so n cannot grow past 244. A realistic rung-4 result of 78-82% is a delta of 4 to 8 percentage points against a ±6pp interval. Two overlapping marginal intervals would report "nothing established" for the most expensive milestone in this project, when the paired data may well establish it.

**Corrected on close.** An earlier version of this issue said rung 4's *entire* available delta is 6.6pp, and that a perfect agent would still publish an inconclusive row. Both claims were too pessimistic, and the first real paired comparison is what showed it. See the Comments.

**Choose the test now, before any rung-4 number exists.** ADR-0008 declared its ladder row in advance for the same reason. A test picked after seeing the numbers looks chosen to fit them.

Zero discordant Instances is a real case and it must not divide by zero. Two rungs that agree everywhere have no delta to test.

M3 is worth re-reading with this in place. Its conclusion was that embeddings and lexical retrieval are indistinguishable, and that conclusion rests on overlapping unpaired intervals. Do not restate M3's finding in this issue. Persist the predictions, and let a later reader ask the question with the right instrument.

## Blocked by

None - can start immediately.

## Comments

**Closed 2026-08-10.** `src/faultloc/predictions.py`, `scoring.compare`, `scoring.mcnemar_p_value`, `reporting.render_comparison`, and `faultloc compare`. Commits `0c733db` and `9823d66`. Cost $0.

### The persistence code moves no number

All seven free rungs re-ran from a clean tree and reproduced their published Top-1 exactly.

| Rung | Reproduced | Published |
|---|---|---|
| bm25 | 39.3% | 39.3% |
| bm25-chunks | 39.8% | 39.8% |
| bm25-chunks-bodies | 43.9% | 43.9% |
| embed | 43.0% | 43.0% |
| hybrid | 45.5% | 45.5% |
| cross-encoder | 26.6% | 26.6% |
| rerank | 74.2% | 74.2% |

`rerank` replayed 244 cached replies at **$0.00**, so the paid ladder row has per-instance Predictions without any spend. Seven files, 157 MB, all stamped `9823d66`.

### The first real paired comparison

`rerank` against `hybrid`, on the stored runs:

```
Top-1 delta   +28.7%   (rerank minus hybrid)
p-value       1.569e-16   (two-sided exact McNemar)
both right 105 · both wrong 57 · rerank only 76 · hybrid only 6
```

The 2x2 table reconstructs both published figures through an independent arithmetic path. 105+76 = 181, and 181/244 is 74.2%. 105+6 = 111, and 111/244 is 45.5%. (76-6)/244 is +28.7pp.

### Two things aggregates could not show

**Free fusion beats the LLM on 6 Instances.** Rung 3 does not strictly dominate rung 2.5. It loses six cases that cost $0.00 to get right, and a 45.5-against-74.2 comparison hides that completely. This matters to M7, because an escalation policy wants to know where a paid rung is worse than a free one.

**Rung 4's headroom is 16.4pp, not 6.6pp. This issue said 6.6pp and that was wrong.**

The 57 both-wrong Instances contain issue 01's 27 unreachable ones. That leaves about **30 Instances where a Ground-Truth File sat inside the top 20 and both systems still failed to rank it first**. Rung 4 can attack those as well as the reachable misses outside the list.

| Source of headroom over the 79.1% baseline | Available |
|---|---|
| in-list ranking, 79.1% to the 88.9% ceiling | +9.8pp |
| out-of-list and grep-reachable (issue 01) | +6.6pp |
| total | **+16.4pp** |

So a perfect rung 4 would be clearly significant rather than inconclusive. The paired test still earns its place, because a *realistic* 4-8pp gain does sit inside ±6pp. The weaker claim stands and the stronger one does not.

### The baseline costs money, and less than first thought

The paired test needs the baseline's per-instance Predictions, and M4 published only aggregates. The response cache holds 244 replies for `gpt-oss-high`, **4** for `deepseek-off`, and **none** for `deepseek-on`.

So whichever rung-3 cell rung 4 is pinned against must run again. At `deepseek-on` that is ~$0.49 and 178m. At `deepseek-off` it is **~$0.31 and 22m**. Recorded in issue 06 with its own criterion. Still open: whether rung 4 and its baseline both move to reasoning-off, which is a decision for ADR-0009.

### A defect this issue introduced and then fixed

`.gitignore` names the data subdirectories one at a time, so `data/predictions/` was not ignored. `code_version()` reads `git status --porcelain`, which counts untracked files, so the directory every run writes into would have stamped **every later run** `-dirty` and made it unpublishable. The first run would poison the second.

The `.gitignore` note about `RUN-COMMANDS.txt` already described this exact trap, one directory over. Fixed in `9823d66`.

A related self-inflicted error is worth recording. The first backfill was discarded because it stamped `-dirty`: a tracked issue file was edited while the run was in flight. A long run and a documentation edit cannot share a working tree.

### Tests

29 new tests. Every guarantee was verified by breaking the implementation and watching the right test fail: `trials == 0` returning 0.0, a one-sided p-value, `max` for `min` in the binomial tail, a flipped delta sign, a removed instance-set check, an always-empty predictions bullet, an inverted significance threshold, and a reversal rendered as a win.
