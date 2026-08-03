# 06 — Scorer

Status: done

## Context

Turns Predictions plus Ground-Truth File Sets into the metrics locked in the design: Top-1, Recall@3, Recall@5.

Like the Instance Filter, this is a pure function whose silent failure would invalidate every number the project publishes. Test it first.

## Acceptance criteria

- Top-1: the rank-1 path is in the Ground-Truth File Set
- Recall@k: proportion of ground-truth files appearing in the top k
- Path comparison is normalised — no false negatives from leading `./` or separator differences
- Unit-tested including the multi-file ground-truth case and the empty-prediction case
- Aggregation reports per-repo breakdown alongside the overall figure

## Notes

Cost and latency fields exist in the output shape from the start, even though rung 1 has no model cost. Later rungs fill them without a schema change.

## Comments

**Closed 2026-08-03.** `src/faultloc/scoring.py`, 35 tests. Dev split scored through the real scorer:

```
rung bm25  split dev  n=244
  Top-1     39.3%  (95% CI 33.4%-45.6%)
  Recall@3  59.3%
  Recall@5  68.5%
  latency   median 0.29s  total 80s
  cost      $0.00 total
  stops     {'answered': 244}
```

Identical to the inline arithmetic used during issue 05 — two independent implementations agreeing, the same cross-check the loader got in issue 02.

### The confidence intervals changed what can be claimed

| repo | n | Top-1 | 95% CI |
|---|---|---|---|
| django/django | 113 | 38.9% | 30.5–48.2% |
| sympy/sympy | 36 | 36.1% | 22.5–52.4% |
| sphinx-doc/sphinx | 22 | 4.5% | 0.8–21.8% |
| matplotlib/matplotlib | 17 | 23.5% | 9.6–47.3% |
| scikit-learn/scikit-learn | 16 | 81.2% | 57.0–93.4% |
| pydata/xarray | 11 | 36.4% | 15.2–64.6% |
| astropy/astropy | 10 | 70.0% | 39.7–89.2% |
| pytest-dev/pytest | 10 | 70.0% | 39.7–89.2% |
| psf/requests | 4 | 25.0% | 4.6–69.9% |
| pylint-dev/pylint | 4 | 25.0% | 4.6–69.9% |
| other | 1 | 100.0% | 20.7–100.0% |

Sphinx and scikit-learn do not overlap at all, so that gap is real. Django and sympy overlap almost entirely, so **"Django outperforms sympy" is not a finding** — it is the sample. Without the intervals that sentence would have been written.

The `other` row is a single instance reading 100% with an interval of 20.7–100%. That row alone justifies the bucket: a bare 100% invites exactly the over-reading the interval forbids.

### Decisions

**Wilson score interval rather than the normal approximation.** The textbook formula produces bounds outside [0, 1] and collapses to zero width at 0% and 100% — precisely where the small per-repo rows sit. Sphinx and `other` would both have been reported as certainties.

**`normalize_path` does not lowercase.** It collapses `./`, a leading `/`, backslashes, and doubled slashes. Folding case would convert a genuine miss into a false hit, and inventing a hit is the one error a scorer must never make — every published number would be wrong with nothing detectable.

**Recall@k is fractional.** A two-file instance with one file found scores 0.5; rounding either way mis-states a rung that located half the answer.

**Predictions pair to instances by `instance_id`, never by list position**, and a prediction naming an unknown instance is rejected. Positional pairing would silently score a reordered list against the wrong answers and produce a plausible number about a different question.

**Repos with fewer than three instances collapse into `other`**, per the note in issue 03.

### Two test failures worth recording

Both were the test helper's fault, not the code's. `prediction()` with no files defaulted to `answered`, and `Prediction.__post_init__` from issue 05 rejected it — an empty ranking exists only as `no_candidates`. An invariant written in one issue caught a mistake made in another issue's tests, which is the entire argument for enforcing invariants rather than documenting them.
