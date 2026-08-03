# 03 — Freeze the dev/test split

Status: done

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

## Comments

**Closed 2026-08-03** in `c5fc458`. The split is frozen at `src/faultloc/data/splits/verified.json` and does not change again without its own ADR.

```
kept 490   dev 244   test 246   ci 50

repo                              dev  test  ci
astropy/astropy                    10    11   2
django/django                     113   113  23
matplotlib/matplotlib              17    17   4
mwaskom/seaborn                     1     1   0
pallets/flask                       0     1   0
psf/requests                        4     4   1
pydata/xarray                      11    11   2
pylint-dev/pylint                   4     4   1
pytest-dev/pytest                  10     9   2
scikit-learn/scikit-learn          16    16   3
sphinx-doc/sphinx                  22    22   5
sympy/sympy                        36    37   7
```

Every repo with two or more instances is on both sides. `pallets/flask` has one and lands wholly in test — the unavoidable exception, asserted by a test so it is not rediscovered later as a bug.

**Stored as package data, read with `importlib.resources`.** Verified to ship in a built wheel, so it resolves the same from a checkout or an installed package — this is what M9 deployment depends on. `load_splits` reads the file or fails; there is no recompute fallback, because a split that can be regenerated at runtime can silently differ between two runs whose numbers get compared.

**The RNG is seeded per repo (`f"{seed}:{repo}"`) and input is sorted before shuffling.** Neither the loader's iteration order nor a repo added later can move existing assignments. Tested by shuffling the input and demanding an identical split.

**The CI slice uses largest-remainder apportionment.** Proportional rounding does not sum back to 50. It matters because a uniform random 50 from dev would be ~46% Django, turning the CI gate into a Django gate.

The split file carries its own provenance — dataset ID, revision SHA, seed, counts. Without the instance universe recorded alongside it, a future reader cannot tell whether a missing ID means the split is stale or the filter changed.

Tests are deliberately in two groups: `TestBuildSplits` checks the algorithm, `TestCommittedSplit` checks the artifact in the repo. The algorithm can be correct while the committed file is stale or hand-edited, and the committed file is what every published number is scored against.
