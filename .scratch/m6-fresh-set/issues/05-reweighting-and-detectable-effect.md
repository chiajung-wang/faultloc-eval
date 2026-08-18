# 05 — Mix Reweighting, effective n, and the minimum detectable effect

Status: ready-for-agent

## Parent

[M6 PRD](../PRD.md)

## What to build

The estimator that every Fresh number is read through, and the bound that gets published **before** any money is spent.

**Mix Reweighting.** Compute the Verified aggregate as a per-repo average, weighted by the Fresh Set's measured repo proportions. The two sets have opposite shapes: django is 46% of the Verified Set and near zero in the Fresh Set, and post-cutoff activity concentrates in repos holding 4 to 17 Verified dev Instances each. Rung 4's per-repo Top-1 spans 75.0% to 100%, so an unweighted comparison moves the headline by repo mix alone.

**Effective sample size travels with every reweighted figure.** Reweighting puts 91% of the weight on thin repos, and the Wilson interval must be computed against the effective n rather than the raw count. Planning figures, using the estimated mix:

| design | effective n | detectable drop | detectable drop-minus-drop |
|---|---|---|---|
| dev split, reweighted | 66 | 7.5pp | 10.6pp |
| full Verified, reweighted | 141 | 5.8pp | **8.2pp** |

Recompute these against the **real** mix once issue 03 reports it. The numbers above come from an estimate of 398 candidates at a 75% keep rate.

**The Contamination estimate is a difference of two drops.** Rung 4's reweighted drop, minus rung 2.5's drop across the same two sets. Report the standard error of that difference, and never report one rung's drop as the estimate.

**Publish the minimum detectable effect before issues 07 and 08 run.** A null that nobody bounded in advance is not a finding.

## Acceptance criteria

- [ ] A reweighted aggregate is computed from per-repo rates and Fresh repo proportions
- [ ] Every reweighted figure reports its effective sample size
- [ ] Wilson intervals on reweighted figures use effective n, not raw count
- [ ] The difference-of-two-drops estimator is implemented, with its standard error
- [ ] The minimum detectable effect is computed from the real Fresh mix and published before any paid run
- [ ] The weights are published, so a reader can recompute the aggregate
- [ ] Unit tests cover the weighting and the interval against hand-worked cases
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

**A larger Fresh Set cannot buy power here.** At n=1000 the detectable effect is still 9.6pp. The Verified side is the constraint. Inverse-variance weighting was checked during planning and returns the same 3.8pp standard error, so no weighting scheme escapes it. Do not reopen this.

Recall@k still has no interval in this project. Report it as direction, never as magnitude.

## Blocked by

- [03 — Fresh Set loader and dataset provenance](03-fresh-loader-and-provenance.md)
