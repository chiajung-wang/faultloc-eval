# 09 — Publish the Contamination estimate

Status: ready-for-agent

## Parent

[M6 PRD](../PRD.md)

## What to build

The milestone's finding, written where a reader meets it.

**The estimate is rung 4's reweighted drop, minus rung 2.5's drop across the same two sets.** Publish the two drops, the difference, its standard error, and the minimum detectable effect that issue 05 published in advance. Never publish one rung's drop as the estimate.

Every figure carries its effective sample size. Every accuracy figure carries cost and latency beside it, including where cost is $0.00.

What the write-up must state plainly:

- **django is absent from the control.** It is 46% of the anchor and 1 candidate in the window, because it runs on Trac. Only Mix Reweighting connects the two populations, and it costs most of the power.
- **The threshold rests on an unofficial cutoff.** If `deepseek/deepseek-v4-pro` trained past April 2026, the Fresh Set is contaminated and nothing in this milestone detects that. One month of margin is the whole defense.
- **The audit's agreement rate**, from issue 04, bounding how much of any drop belongs to set quality.
- **What Tool-Reached says on a set the model cannot have memorized.** That reading has no equivalent on the Verified Set.

Update `README.md`, `docs/milestones.md`, and `CONTEXT.md` where the measurement changed what a term means. Check every published figure against `RESULTS.md` **by string match, not by eye**. That has caught real errors here.

## Acceptance criteria

- [ ] The Contamination estimate is published with both drops, the difference, and its standard error
- [ ] The minimum detectable effect published in issue 05 appears beside the result
- [ ] Every reweighted figure carries its effective sample size
- [ ] Per-repo figures are published beside every aggregate
- [ ] django's absence, the unofficial cutoff, and the audit rate are all stated, not buried
- [ ] Every figure in `README.md` matches a `RESULTS.md` entry by string match
- [ ] `docs/milestones.md` records what M6 established and what it carries into M7
- [ ] Milestone spend is reported against the $12 Milestone Budget

## Notes

**A null is the likely outcome and it is publishable.** At 8.2pp detectable, this milestone rules out a large effect and cannot resolve a small one. That sentence belongs in the write-up, in those terms.

Rung 2 did not beat rung 1 and that sits in the README rather than buried. This follows the same rule.

**M6 carries one thing into M7 regardless of the result:** the per-instance Predictions from issue 07 are the test-split read that M7 must not repeat.

## Blocked by

- [04 — Hand-audit 30 Instances](04-audit-the-sample.md)
- [07 — Rung 4 across the Verified test split](07-rung4-verified-test.md)
- [08 — Rung 4 across the Fresh Set](08-rung4-fresh-set.md)
