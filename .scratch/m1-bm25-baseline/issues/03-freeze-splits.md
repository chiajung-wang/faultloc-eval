# 03 — Freeze the dev/test split

Status: ready-for-agent

## Context

[ADR-0004](../../../docs/adr/0004-calibrated-confidence.md) makes split discipline mandatory: the calibrator is fit on dev, and the test set is evaluated once. The split must be fixed **before** any tuning happens, which means now, in M1.

## Acceptance criteria

- Deterministic split with a committed seed, stratified by repo so no repo lands entirely in one side
- Split stored as a committed file of instance IDs, not recomputed at runtime
- A frozen 50-instance dev slice identified for the CI gate (M9)
- Loading a split is a single function call and cannot be accidentally reshuffled

## Notes

Once committed, this file does not change. If it must change, that invalidates prior calibration numbers and the change gets its own ADR.
