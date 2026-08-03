# 05 — BM25 rung

Status: done

## Context

Rung 1 of the ladder. Lexical retrieval over file contents, no model calls.

**Index unit: the whole file.** One document per source file at the instance's `base_commit`. Chunking belongs to rung 2 (locked design decision #6), and rung 1 exists to establish the floor — the crudest thing that works — so the deltas above it mean something.

Known effect, expected and not a bug: file lengths in these repos are very uneven, and Django's are among the longest. BM25's length normalisation is a generic average-based correction, not one tuned for source code, so it can both under-penalise long files that match everything by vocabulary alone and over-penalise the large core module that genuinely is the answer. A weaker Django result at rung 1 is the predicted outcome, not a defect to chase.

Issue text frequently quotes identifiers, file paths, and stack traces, so lexical matching is a genuinely strong baseline here — that is the point. If later rungs struggle to beat it, that is a finding worth reporting, not a bug.

## Acceptance criteria

- Given an Instance, returns a ranked list of file paths
- Tokenisation splits identifiers sensibly (snake_case, CamelCase, dotted paths)
- Deterministic: same Instance, same ranking, every run
- Returns `no_candidates` rather than an empty list silently
- Exposes a `Prediction` shape that later rungs also produce

## Notes

Keep the rung interface narrow — later rungs must be swappable behind it without touching the harness.

## Comments

**Closed 2026-08-03.** First real numbers, measured on the dev split with an inline script — **not yet reproducible by command**. `faultloc evaluate` is still a stub and `RESULTS.md` does not exist; both are issue 07's job, and the entry must be emitted by the CLI rather than transcribed from here.

```
DEV  n=244
  Top-1     39.3%  (96/244)
  Recall@3  59.3%
  Recall@5  68.5%
  latency   median 0.29s   total 80s
  cost      $0.00
```

### The Django prediction above was wrong

This issue predicted Django would underperform because of BM25's crude length normalisation. Measurement says otherwise:

| repo | median rank of truth | median candidates |
|---|---|---|
| django/django | 3 | 3,516 |
| scikit-learn/scikit-learn | 1 | 388 |
| sphinx-doc/sphinx | 40 | 541 |

Django finds the answer at rank 3 out of 3,516 candidates — strong retrieval on the largest haystack in the set, and its 38.9% Top-1 sits at the average rather than below it.

**`sphinx-doc/sphinx` is the real outlier at 4.5%**, with the truth at median rank 40 out of only 541 candidates — by far the worst ratio. Plausible cause: Sphinx is a documentation tool, so its reports describe *rendered output* in vocabulary that never appears in the code producing it. That is the exact gap lexical matching cannot cross, which makes Sphinx the sharpest single test of whether rung 2's embeddings earn their cost in M3.

The prediction is left in place above rather than edited away. A written prediction that measurement overturned is better evidence than one that happened to be right.

### Two bugs the tests caught

**Snake_case compounds were silently lost.** The word regex treated `_` as a separator, so `separability_matrix` split into two words before the compound-preserving branch ever saw it — discarding the rarest and highest-value token available. Fixed by keeping `_` inside a word while leaving `.` and `/` as separators.

**BM25 is mathematically degenerate on a tiny corpus.** A test asserting the right file ranks first in the two-file fixture failed. BM25's IDF term is `log(N - n + 0.5) - log(n + 0.5)`, which is exactly zero when a term appears in half the documents, so every discriminating term scored zero. The code was correct; the test was measuring the toy. It was deleted and the reason recorded in the module docstring — ranking quality belongs to the scorer on real instances.

### Design notes

`Prediction` rejects an `answered` result with no files, and rejects duplicate paths — a repeat would inflate Recall@k without finding anything new. `no_candidates` stays distinct from an empty ranking: "nothing to search" and "searched, found nothing" are different failures and collapsing them hides the first inside the second's score.

Ties break by path. Without it, equal-scoring files would order by however git enumerated them and determinism would hold only by luck.

Tokenisation keeps the compound identifier *alongside* its parts. The parts let prose match code at all; the compound is far rarer, so an exact quote outranks a coincidental part match.

`RepoStore.read_blobs` was added here: one subprocess per file would have been roughly 900,000 spawns across the set. Combined with the blob-SHA token cache from issue 04 — 21× content reuse — the whole dev split runs in 80 seconds.
