# Results

Every number published anywhere in this repository traces to an entry below.
Entries are emitted by `faultloc evaluate`, never written by hand, so a figure
and its provenance cannot drift apart.

Top-1 is reported with a 95% Wilson interval. At these sample sizes a small
difference between two rungs or two repositories is not yet a result, and the
interval is what says so.

## 2026-08-07 · rerank · dev

| Metric | Value |
|---|---|
| Top-1 | 74.2% (95% CI 68.3%-79.3%) |
| Recall@3 | 81.8% |
| Recall@5 | 85.3% |
| Instances scored | 244 |
| Wall clock | 186m 24s |
| Cost | $0.39 ($0.0016/instance) |

**Per repo** — django 113 @ 73.5% · sympy 36 @ 63.9% · sphinx 22 @ 63.6% · matplotlib 17 @ 88.2% · scikit-learn 16 @ 93.8% · xarray 11 @ 72.7% · astropy 10 @ 80.0% · pytest 10 @ 70.0% · requests 4 @ 100.0% · pylint 4 @ 75.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `6fad58d` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung rerank --split dev`

**Read**: Degraded: 17 unparseable replies, 13 truncated replies, 6 off-list paths. Replayed 162 responses from cache; cost is what they cost to make.

## 2026-08-06 · rerank-deepseek-on · dev

| Metric | Value |
|---|---|
| Top-1 | 79.1% (95% CI 73.6%-83.7%) |
| Recall@3 | 83.9% |
| Recall@5 | 84.6% |
| Instances scored | 244 |
| Wall clock | 178m 24s |
| Cost | $0.49 ($0.0020/instance) |

**Per repo** — django 113 @ 80.5% · sympy 36 @ 72.2% · sphinx 22 @ 63.6% · matplotlib 17 @ 76.5% · scikit-learn 16 @ 93.8% · xarray 11 @ 90.9% · astropy 10 @ 90.0% · pytest 10 @ 80.0% · requests 4 @ 75.0% · pylint 4 @ 75.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `b46e55c` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung rerank-deepseek-on --split dev`

**Read**: Degraded: 3 truncated replies, 14 off-list paths.

## 2026-08-06 · rerank-deepseek-off · dev

| Metric | Value |
|---|---|
| Top-1 | 75.0% (95% CI 69.2%-80.0%) |
| Recall@3 | 82.8% |
| Recall@5 | 85.7% |
| Instances scored | 244 |
| Wall clock | 21m 44s |
| Cost | $0.31 ($0.0013/instance) |

**Per repo** — django 113 @ 75.2% · sympy 36 @ 66.7% · sphinx 22 @ 63.6% · matplotlib 17 @ 76.5% · scikit-learn 16 @ 93.8% · xarray 11 @ 90.9% · astropy 10 @ 90.0% · pytest 10 @ 90.0% · requests 4 @ 50.0% · pylint 4 @ 25.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `abc06ee` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung rerank-deepseek-off --split dev`

**Read**: Degraded: 1 unparseable replies, 43 off-list paths.

## 2026-08-06 · rerank-gpt-oss-low · dev

| Metric | Value |
|---|---|
| Top-1 | 72.5% (95% CI 66.6%-77.8%) |
| Recall@3 | 81.1% |
| Recall@5 | 83.3% |
| Instances scored | 244 |
| Wall clock | 9m 02s |
| Cost | $0.76 ($0.0031/instance) |

**Per repo** — django 113 @ 73.5% · sympy 36 @ 61.1% · sphinx 22 @ 63.6% · matplotlib 17 @ 70.6% · scikit-learn 16 @ 93.8% · xarray 11 @ 81.8% · astropy 10 @ 90.0% · pytest 10 @ 70.0% · requests 4 @ 50.0% · pylint 4 @ 75.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `72ed477` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung rerank-gpt-oss-low --split dev`

**Read**: Degraded: 29 off-list paths.

## 2026-08-05 · cross-encoder · dev

| Metric | Value |
|---|---|
| Top-1 | 26.6% (95% CI 21.5%-32.5%) |
| Recall@3 | 42.8% |
| Recall@5 | 52.6% |
| Instances scored | 244 |
| Wall clock | 61m 12s |
| Cost | $0.00 ($0.0000/instance) |

**Per repo** — django 113 @ 26.5% · sympy 36 @ 30.6% · sphinx 22 @ 18.2% · matplotlib 17 @ 52.9% · scikit-learn 16 @ 18.8% · xarray 11 @ 18.2% · astropy 10 @ 20.0% · pytest 10 @ 10.0% · requests 4 @ 50.0% · pylint 4 @ 25.0% · other 1 @ 0.0%

**Stop conditions** — answered 244

**Provenance**
- code `89da23c` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung cross-encoder --split dev`

**Read**: _(not recorded)_

## 2026-08-05 · hybrid · dev

| Metric | Value |
|---|---|
| Top-1 | 45.5% (95% CI 39.4%-51.8%) |
| Recall@3 | 65.2% |
| Recall@5 | 73.1% |
| Instances scored | 244 |
| Wall clock | 4m 10s |
| Cost | $0.00 ($0.0000/instance) |

**Per repo** — django 113 @ 41.6% · sympy 36 @ 41.7% · sphinx 22 @ 36.4% · matplotlib 17 @ 47.1% · scikit-learn 16 @ 68.8% · xarray 11 @ 45.5% · astropy 10 @ 80.0% · pytest 10 @ 60.0% · requests 4 @ 25.0% · pylint 4 @ 25.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `0f3389b` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung hybrid --split dev`

**Read**: Rank fusion of the lexical and dense rungs, no model. The comparison point rung 3 must beat.

## 2026-08-04 · embed · dev

| Metric | Value |
|---|---|
| Top-1 | 43.0% (95% CI 37.0%-49.3%) |
| Recall@3 | 57.9% |
| Recall@5 | 67.8% |
| Instances scored | 244 |
| Wall clock | 35s |
| Cost | $0.00 ($0.0000/instance) |

**Per repo** — django 113 @ 41.6% · sympy 36 @ 41.7% · sphinx 22 @ 27.3% · matplotlib 17 @ 41.2% · scikit-learn 16 @ 56.2% · xarray 11 @ 54.5% · astropy 10 @ 60.0% · pytest 10 @ 60.0% · requests 4 @ 25.0% · pylint 4 @ 25.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `e8af1e2` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung embed --split dev`

**Read**: Rung 2: dense retrieval over AST Chunks, bge-small-en-v1.5. Index built separately by faultloc index; the cost here is per-query only.

## 2026-08-04 · bm25-chunks-bodies · dev

| Metric | Value |
|---|---|
| Top-1 | 43.9% (95% CI 37.8%-50.1%) |
| Recall@3 | 60.3% |
| Recall@5 | 65.7% |
| Instances scored | 244 |
| Wall clock | 3m 42s |
| Cost | $0.00 ($0.0000/instance) |

**Per repo** — django 113 @ 40.7% · sympy 36 @ 44.4% · sphinx 22 @ 18.2% · matplotlib 17 @ 29.4% · scikit-learn 16 @ 81.2% · xarray 11 @ 45.5% · astropy 10 @ 80.0% · pytest 10 @ 70.0% · requests 4 @ 0.0% · pylint 4 @ 50.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `8d3af9e` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung bm25-chunks-bodies --split dev`

**Read**: Issue 06: bodies indexed. Isolates body exclusion from the change of index unit. Recall recovers, so bodies were the cost, not the unit.

## 2026-08-04 · bm25-chunks · dev

| Metric | Value |
|---|---|
| Top-1 | 39.8% (95% CI 33.8%-46.0%) |
| Recall@3 | 52.0% |
| Recall@5 | 61.3% |
| Instances scored | 244 |
| Wall clock | 2m 47s |
| Cost | $0.00 ($0.0000/instance) |

**Per repo** — django 113 @ 36.3% · sympy 36 @ 50.0% · sphinx 22 @ 9.1% · matplotlib 17 @ 23.5% · scikit-learn 16 @ 81.2% · xarray 11 @ 45.5% · astropy 10 @ 70.0% · pytest 10 @ 50.0% · requests 4 @ 0.0% · pylint 4 @ 25.0% · other 1 @ 100.0%

**Stop conditions** — answered 244

**Provenance**
- code `903e797` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
- Reproduce: `faultloc evaluate --rung bm25-chunks --split dev`

**Read**: Chunk definition v2: windowed at 2048 chars. Supersedes the earlier bm25-chunks row, which used unwindowed chunks.

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
