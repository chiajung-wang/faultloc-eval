# Results

Every number published anywhere in this repository traces to an entry below.
Entries are emitted by `faultloc evaluate`, never written by hand, so a figure
and its provenance cannot drift apart.

Top-1 is reported with a 95% Wilson interval. At these sample sizes a small
difference between two rungs or two repositories is not yet a result, and the
interval is what says so.

## 2026-08-04 · bm25-chunks · dev

| Metric | Value |
|---|---|
| Top-1 | 37.3% (95% CI 31.5%-43.5%) |
| Recall@3 | 50.7% |
| Recall@5 | 59.0% |
| Instances scored | 244 |
| Wall clock | 2m 13s |
| Cost | $0.00 ($0.0000/instance) |

**Per repo** — django 113 @ 31.9% · sympy 36 @ 50.0% · sphinx 22 @ 0.0% · matplotlib 17 @ 23.5% · scikit-learn 16 @ 75.0% · xarray 11 @ 54.5% · astropy 10 @ 80.0% · pytest 10 @ 50.0% · requests 4 @ 0.0% · pylint 4 @ 25.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `234b566` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung bm25-chunks --split dev`

**Read**: Ablation: chunking alone, no model. Compare against bm25 whole-file at 39.3%.

## 2026-08-03 · bm25 · dev

| Metric | Value |
|---|---|
| Top-1 | 39.3% (95% CI 33.4%-45.6%) |
| Recall@3 | 59.3% |
| Recall@5 | 68.5% |
| Instances scored | 244 |
| Wall clock | 1m 23s |
| Cost | $0.00 ($0.0000/instance) |

**Per repo** — django 113 @ 38.9% · sympy 36 @ 36.1% · sphinx 22 @ 4.5% · matplotlib 17 @ 23.5% · scikit-learn 16 @ 81.2% · xarray 11 @ 36.4% · astropy 10 @ 70.0% · pytest 10 @ 70.0% · requests 4 @ 25.0% · pylint 4 @ 25.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `70b01bb` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung bm25 --split dev`

**Read**: BM25 over whole files is a strong floor at 39.3%. sphinx-doc/sphinx is the outlier at 4.5% (CI 0.8-21.8), non-overlapping with scikit-learn at 81.2% -- its reports describe rendered output in vocabulary absent from the code, which is the gap rung 2 must close to justify its cost.
