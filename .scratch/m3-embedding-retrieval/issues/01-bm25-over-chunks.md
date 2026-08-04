# 01 — BM25 over AST Chunks: the ablation, first

Status: done

## Parent

[M3 PRD](../PRD.md)

## What to build

An AST Chunk extractor, a rule for scoring a *file* from its chunks, and a third rung — `bm25-chunks` — that runs the existing lexical matcher over chunks instead of whole files. End to end: `faultloc evaluate --rung bm25-chunks --split dev` prints the metrics and prepends an entry to `RESULTS.md`, exactly as rung 1 does.

No model calls. No embeddings. This slice changes **one** variable against rung 1 — the index unit — which is the entire reason it exists and is built before the embedding rung rather than after it.

An AST Chunk is defined in `CONTEXT.md`: one function or class, represented by its signature, docstring, and file path. Chunk text is derived from a blob, so it is cacheable by blob SHA the same way tokens already are — across the Verified Set the same content appears about 21 times.

Files that fail to parse (syntax errors, Python 2 fixtures, non-Python source the deny-list filter keeps) must still be retrievable. Decide and state the fallback — most likely a single whole-file chunk — because a ground-truth file absent from the candidate set is a silent accuracy ceiling that looks like a bad retriever.

**Chunk → file aggregation is decided here and reused unchanged by rung 2.** A file's score from its chunks — max, sum, or mean — changes every number downstream, and if the ablation and the embedding rung aggregated differently the comparison between them would be void. Pin it with a test and record which alternatives were rejected and why.

## Acceptance criteria

- [ ] AST Chunks extracted from a blob: one per function and class, carrying signature, docstring, and path
- [ ] Unparseable and non-Python source files still produce at least one retrievable chunk
- [ ] Chunk extraction cached by blob SHA, so identical content is parsed once per run
- [ ] Chunk → file aggregation rule implemented, unit-tested, and its rationale written down
- [ ] `faultloc evaluate --rung bm25-chunks --split dev` runs end to end and emits a `RESULTS.md` entry
- [ ] Deterministic: same Instance, same ranking, every run
- [ ] Returns `no_candidates` rather than an empty ranking when a repo yields no chunks
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

Reuse the rung-1 tokeniser unchanged. If it were retuned in the same slice, the ablation would move two variables again and lose its only purpose.

Report the corpus size change in the closing comment — chunks per instance against files per instance. A candidate set an order of magnitude larger changes what a Recall@5 number means, and the ratio explains the latency difference before anyone has to ask.

## Blocked by

None — can start immediately.

## Comments

**Closed 2026-08-04.** The ablation is negative: chunking on its own does not help, and on recall it clearly hurts.

```
                 bm25 (M1)      bm25-chunks      delta
Top-1            39.3%          37.3%            -2.0pp   CIs overlap heavily
Recall@3         59.3%          50.7%            -8.6pp
Recall@5         68.5%          59.0%            -9.5pp
Wall clock       1m 23s         2m 13s           +60%
```

Both code `234b566`, dev split, seed 20260803, same 244 instances. Entry in `RESULTS.md`.

The Top-1 intervals are 31.5–43.5 against 33.4–45.6 — overlapping, so **no difference in Top-1 has been shown**, in either direction. The recall drops are far larger and move together, which is the number worth reading.

### The confound this exposed, and it belongs to rung 2 as well

Recall falling means ground-truth files stopped being *retrievable at all*, not merely being ranked lower. That points at content, not segmentation — and reveals that "chunking" is really two changes, not one:

1. the index unit is a definition rather than a file
2. **the body is no longer indexed** — only signature, docstring, and path

The second is the one that will have done this. Issue reports quote identifiers from inside function bodies constantly: called functions, local names, string literals, error messages, traceback frames. Whole-file BM25 matched all of them. Chunk documents contain none of them.

Measured on a 40-instance sample: median 3,360 candidate files becomes median 11,888 chunks, a 3.5× document count — but each document is a fraction of the text. 5.5% of chunks are whole-file fallbacks (unparseable, non-Python, or definition-free modules); the rest are 80,434 functions and 13,874 classes.

`CONTEXT.md` defines an AST Chunk as signature + docstring + path, so this rung indexed exactly what rung 2 will embed. **The handicap is therefore inherited.** Embeddings will be asked to close a gap that starts ~9pp of recall below where rung 1 already stands, using documents from which the highest-signal lexical tokens have been removed.

Worth knowing before paying for an index. The cheap diagnostic — a chunks-with-bodies variant, one line of change to `Chunk.text`, no new infrastructure — separates "definitions are the wrong unit" from "dropping bodies threw away the signal". Recommended as a follow-up issue before issue 03 spends money.

### Sphinx got worse, not better

M1 predicted Sphinx as the clearest case for rung 2: 4.5% Top-1, truth at median rank 40 of 541 candidates, on the theory that its reports describe rendered output in vocabulary absent from the code.

Chunking took it from **4.5% to 0.0%** (CI 0.0–14.9). Zero of 22.

Consistent with the body-exclusion reading: whatever thin lexical hold Sphinx had was in the bodies. It also raises the stakes on the M1 hypothesis — if the vocabulary genuinely is not in the code at all, then embedding the signature and docstring will not find it either, and the Sphinx gap is a data property rather than a retrieval-method one.

Two other repos moved the other way and are not explained by this: `sympy` 36.1 → 50.0 and `pydata/xarray` 36.4 → 54.5, both up substantially. Small n, wide intervals, but the direction is opposite to the aggregate. Not chased here.

### Decisions

**`max` aggregation, implemented as an explicit loop rather than `max(scores, default=0.0)`.** BM25 emits negative scores for terms appearing in most of the corpus, and the `default=` form would clamp a file whose best chunk scored −1.0 up to 0.0, tying it with files that matched nothing at all. Pinned by `test_negative_scores_are_not_clamped`.

**Path tokens are added per file, never cached with the chunk.** One blob can be reachable at several paths, so a cache keyed by content hash would otherwise serve whichever path it saw first. Pinned by a test asserting no path token appears in the cache.

**Every file yields at least one chunk.** Unparseable source, non-Python source the filter keeps, and definition-free modules all fall back to a whole-file chunk — 5.5% of the corpus. A file with no chunks cannot be predicted, and that ceiling looks exactly like weak ranking in every metric published.

**The harness was not touched.** Loader, splits, scorer, and results log took the new rung unchanged, which is the first real test of ADR-0003's claim that the rung contract was fixed before rung 1 existed.

### A test that would have passed either way

The null-byte test was first written as `chunk_source("data = '\x00'")` asserting the whole-file fallback — but a module with no definitions falls back regardless, so it passed whether or not the `ValueError` was handled. Rewritten with a `def` in the source, so the fallback can only be reached through the exception path. Same failure mode as M1's `or True` assertion: a test that cannot fail occupies the slot a real one would fill.

### Commits

| Commit | What |
|---|---|
| `234b566` | `feat: add the BM25-over-chunks ablation rung` — chunker, aggregation, rung, CLI wiring, 31 tests |
