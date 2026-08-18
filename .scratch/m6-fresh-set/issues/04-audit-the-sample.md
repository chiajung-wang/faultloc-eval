# 04 — Hand-audit 30 Instances, publish the agreement rate

Status: ready-for-human

## Parent

[M6 PRD](../PRD.md)

## What to build

A hand audit of about 30 Fresh Instances, and the agreement rate it produces.

SWE-bench Verified paid human annotators to confirm that each issue specifies a real, solvable problem. The Fresh Set has nobody. [ADR-0006](../../../docs/adr/0006-datasets.md) promised this audit, and [ADR-0010](../../../docs/adr/0010-fresh-set-mining.md) makes it the only thing standing between structural criteria and an unvalidated benchmark.

Sample at random from the frozen set, stratified by repo. For each Instance, answer three questions:

1. Does the issue describe a defect, rather than a feature request or a cleanup?
2. Does the issue text specify the problem well enough that a reader could localize it?
3. Is the Ground-Truth File Set where a fix for *this* issue belongs?

Record every judgement, not a summary. Publish the agreement rate beside every Fresh number, in the same place the Filter Rate appears.

A rejected Instance is **not** removed from the frozen set. Removing it after the fact makes the artifact depend on a human pass that nobody can reproduce. Count it and report it.

## Acceptance criteria

- [ ] About 30 Instances sampled at random, stratified by repo, with the seed recorded
- [ ] Each carries a recorded judgement against all three questions
- [ ] The agreement rate is published, per question
- [ ] No Instance is removed from the frozen set as a result
- [ ] The audit's findings are written where a reader of a Fresh number will meet them

## Notes

This is `ready-for-human` because it is the one part of the milestone that an agent judging its own benchmark cannot do honestly.

**A low agreement rate is a finding, not a failure.** It bounds how much of any measured drop belongs to set quality rather than to Contamination, and the report must say so rather than bury it.

## Blocked by

- [02 — `faultloc mine`](02-mine-and-freeze.md)
