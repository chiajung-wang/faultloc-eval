# 07 — Rung 4 across the Verified test split

Status: ready-for-agent

## Parent

[M6 PRD](../PRD.md)

## What to build

Rung 4's per-repo accuracy on the half of the Verified Set that nobody has read, at about **$5.2**.

This is what buys the milestone its statistical power. Reweighting to the Fresh mix collapses the dev split's effective n to 66, which resolves only a 10.6pp effect. Adding the test split lifts effective n to 141 and the detectable difference to **8.2pp**.

**Persist per-instance Predictions.** M7's coverage curve consumes this same artifact rather than running rung 4 again, which is how [ADR-0004](../../../docs/adr/0004-calibrated-confidence.md)'s single read of the test split stays single. The Calibrator sits on top of rung 4 and does not change it, so nothing is tuned against test in between.

Nothing about rung 4 changes. Same model, route, reasoning effort, prompt, tools, Instance Budget, and answer format as the published dev row. A single altered token invalidates the response cache and costs a re-run the budget does not hold.

## Acceptance criteria

- [ ] Rung 4 runs across the Verified test split and writes a `RESULTS.md` entry
- [ ] Per-instance Predictions are persisted for M7
- [ ] Per-repo Top-1, cost, latency, Stop Conditions, and tool counts are reported
- [ ] The configuration matches the published dev row exactly, and the entry records that
- [ ] Actual cost is compared against the $5.2 estimate before issue 08 starts
- [ ] The run starts from a clean tree

## Notes

**The budget is $12 and it holds no re-run.** This run and issue 08 come to about $11.5. Check the actual cost against the estimate the moment this finishes, because issue 08 is the larger of the two and it is still a decision at that point.

Smoke-test with `--limit` first. It refuses to write an entry, which is what you want, and 10 Instances cost about $0.21 of the $0.50 margin.

## Blocked by

- [05 — Mix Reweighting and the minimum detectable effect](05-reweighting-and-detectable-effect.md)
- [06 — Two index builds, and rung 2.5's drop](06-indexes-and-hybrid-drop.md)
