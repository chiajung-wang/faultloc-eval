# 03 — Freeze the dev/test split

Status: ready-for-agent

## Context

[ADR-0004](../../../docs/adr/0004-calibrated-confidence.md) makes split discipline mandatory: the calibrator is fit on dev, and the test set is evaluated once. The split must be fixed **before** any tuning happens, which means now, in M1.

## Decided: 50/50, stratified by repo, seed `20260803`

Applied to the instances that *survive* the Instance Filter, so this issue runs after 01 and 02.

Why an even split rather than a larger test set:

- **Dev carries three jobs** — tuning all four rungs, fitting the calibrator in M7, and hosting the CI slice. The calibrator is logistic regression over 5 features; at a ~40% Top-1 a 210-instance dev set yields roughly 85 positive events, against a 10–20-events-per-feature rule of thumb. Shrinking dev makes M7 unreliable.
- **Test is read once**, for two numbers: headline Top-1 and the Verified↔Fresh contamination gap. Neither needs to resolve a small delta.
- **Rung-to-rung deltas are measured on dev.** The ladder comparison table — the project's main deliverable — never touches test.
- **Cost, stated not hidden:** ~210 test instances give a 95% CI near ±6.6pp on a 40% Top-1. Top-1 is therefore always reported with its interval, never as a bare point estimate.

## Acceptance criteria

- Deterministic split with a committed seed, stratified by repo so no repo lands entirely in one side
- Split stored as a committed file of instance IDs, not recomputed at runtime
- A frozen 50-instance dev slice identified for the CI gate (M9), itself **stratified** — a uniform random 50 is ~46% Django and turns the gate into a Django gate
- Loading a split is a single function call and cannot be accidentally reshuffled

## Notes

Once committed, this file does not change. If it must change, that invalidates prior calibration numbers and the change gets its own ADR.

`pallets/flask` has 1 instance and `mwaskom/seaborn` has 2, so stratification cannot balance them. Assign by seed and report them inside an `other` bucket rather than as per-repo rows.
