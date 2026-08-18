# 08 — Rung 4 across the Fresh Set

Status: ready-for-agent

## Parent

[M6 PRD](../PRD.md)

## What to build

Rung 4 on post-cutoff Instances, at about **$6.3**. The number this milestone exists to produce.

Same configuration as issue 07 and as the published dev row. Model, route, reasoning effort, prompt, tools, Instance Budget, and answer format all hold. The dataset is the only variable, which is the whole point.

Report everything the dev row reports, and two things that carry extra weight here:

- **Off-List Paths accepted, and Tool-Reached.** On the Verified Set a model can name a real path from memory, and Tool-Reached separates search from recall. **On a post-cutoff set it cannot recall.** So the Tool-Reached split on this run is the first clean reading of that flag the project has ever taken, and it is worth more than its cost.
- **The share of Instances whose issue text names a Ground-Truth File.** 26.1% of Verified Instances do. The rate is published for both sets. It is not corrected for, because the stratum is worth only 4.7pp and a 15pp rate difference biases the aggregate by under 1pp.

## Acceptance criteria

- [ ] Rung 4 runs across the Fresh Set and writes a `RESULTS.md` entry
- [ ] Per-instance Predictions are persisted
- [ ] Per-repo Top-1, cost, latency, Stop Conditions, and tool counts are reported
- [ ] Off-List Paths accepted and Tool-Reached are reported and read against the Verified rows
- [ ] The issue-text naming rate is reported for the Fresh Set
- [ ] The configuration matches issue 07 exactly, and the entry records that
- [ ] Total milestone spend is checked against the $12 Milestone Budget
- [ ] The run starts from a clean tree

## Notes

**Read this row against the Fresh Set's own hit@20 from issue 06**, never against the Verified ceiling. A reranking or reaching system is bounded by the list it receives, and the two sets do not share one.

## Blocked by

- [06 — Two index builds, and rung 2.5's drop](06-indexes-and-hybrid-drop.md)
- [07 — Rung 4 across the Verified test split](07-rung4-verified-test.md)
