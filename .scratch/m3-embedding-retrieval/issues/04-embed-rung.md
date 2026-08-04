# 04 — Rung 2: embedding retrieval end to end

Status: done

## Parent

[M3 PRD](../PRD.md)

## What to build

The rung itself. Embed the issue text, rank AST Chunks by similarity against the cached index, aggregate chunks to files with the rule fixed in issue 01, and return a `Prediction` carrying **real** `cost_usd` and `latency_s`.

End to end: `faultloc evaluate --rung embed --split dev` prints the metrics and prepends a `RESULTS.md` entry, unchanged in format from rung 1's.

The rung reads the index; it does not build it. A missing or incomplete index is a clear error telling the user to run `faultloc index`, not a silent slow path that quietly spends money mid-evaluation.

Cost accounting starts mattering here. Rung 1 reported `$0.00` and the field existed anyway (`Prediction.cost_usd`, `rungs/__init__.py`) precisely so this rung would have nothing to retrofit. Query-embedding cost is per instance; index cost is amortised — state in the closing comment which of the two the reported per-instance figure includes, because the two answer different questions and a reader cannot tell them apart from a single number.

## Acceptance criteria

- [ ] `faultloc evaluate --rung embed --split dev` runs end to end and emits a `RESULTS.md` entry
- [ ] Ranked files produced by aggregating chunk scores with the rule from issue 01, unmodified
- [ ] `latency_s` and `cost_usd` are measured per instance, not zeros or constants
- [ ] Deterministic: same Instance, same ranking, every run
- [ ] Missing or stale index fails loudly with the command to fix it
- [ ] `no_candidates` returned when the instance's repo yields no indexed chunks
- [ ] The harness is untouched — scorer, loader, splits, and results log take this rung without modification
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

If the harness needs changing to accept this rung, that is worth a line in the closing comment: ADR-0003 claims the rung contract was fixed before the first rung existed, and this is the first real test of that claim.

Same dev split, same frozen seed. The test split stays untouched until M7.

## Blocked by

- [03 — Blob-keyed embedding index](03-embedding-index.md)

## Comments

**Closed 2026-08-04. Rung 2 does not beat rung 1.** ADR-0003 committed to publishing that outcome, and this is the first time it has cost anything.

| Row | Top-1 | Recall@3 | Recall@5 | query wall clock |
|---|---|---|---|---|
| `bm25` whole file | 39.3% (33.4–45.6) | 59.3% | 68.5% | 1m23s |
| `bm25-chunks` windowed | 39.8% (33.8–46.0) | 52.0% | 61.3% | 2m47s |
| `bm25-chunks-bodies` | **43.9%** (37.8–50.1) | 60.3% | 65.7% | 3m38s |
| **`embed`** | 43.0% (37.0–49.3) | 57.9% | **67.8%** | **35s** |

Embeddings land a point below the best lexical row on Top-1 and 2.4pp below it on Recall@3, with intervals that overlap almost entirely. Nothing separates them. The honest statement is that **dense retrieval matched lexical retrieval here and did not exceed it** — after a model, a 1.56 GB index, and 153 minutes of build time.

### The aggregate hides a real redistribution

Per repo, against the best lexical row:

| Repo | n | `bm25-chunks-bodies` | `embed` | Δ |
|---|---|---|---|---|
| sphinx | 22 | 18.2% | **27.3%** | +9.1 |
| matplotlib | 17 | 29.4% | **41.2%** | +11.8 |
| requests | 4 | 0.0% | 25.0% | +25.0 |
| xarray | 11 | 45.5% | 54.5% | +9.0 |
| django | 113 | 40.7% | 41.6% | +0.9 |
| sympy | 36 | 44.4% | 41.7% | −2.7 |
| pytest | 10 | 70.0% | 60.0% | −10.0 |
| astropy | 10 | 80.0% | 60.0% | −20.0 |
| pylint | 4 | 50.0% | 25.0% | −25.0 |
| scikit-learn | 16 | 81.2% | **56.2%** | −25.0 |

**Embeddings help precisely where lexical matching fails, and hurt where it already works.** Sphinx and matplotlib — prose-heavy reports about rendered output — gain most. scikit-learn and astropy, where reports quote identifiers directly and BM25 was already at 80%, lose most. The aggregate is flat because the two effects cancel.

That is a more useful finding than a win would have been. It says the two methods are complementary rather than one dominating, which is the case for rung 3 reranking a *union* of candidates rather than reordering rung 2's alone. Small per-repo counts, so treat the individual deltas as direction rather than magnitude.

### Sphinx, finally

Rung 1: 4.5%. Chunked without bodies: 0.0%. With bodies: 18.2%. Embedded: **27.3%** — six times rung 1.

M1 predicted Sphinx as the sharpest test of whether embeddings earn their cost. Issue 06 partly overturned that by showing its vocabulary is in the code after all, just in the bodies. Both turn out to matter: bodies got it to 18%, embeddings took it to 27%. The M1 prediction was right about the repo and wrong about the mechanism.

### Which cost figure the entry reports

Per issue 04's brief: **the `RESULTS.md` figure is the per-query cost, and it is `$0.00`** — the model runs locally, so answering one question spends nothing.

That number is honest and also incomplete on its own. The index cost 153 minutes to build, amortised over 244 instances = **37.6 s/instance**, which dwarfs the 0.14 s/instance query time. A reader comparing the 35s wall clock against rung 1's 1m23s would conclude rung 2 is faster, and for repeated evaluation over a stable index it is. For one pass it is roughly 30× slower end to end. Both are true and they answer different questions, which is exactly why they are reported separately rather than summed.

### The harness took it untouched

ADR-0003 claimed the rung contract was fixed before rung 1 existed, so later rungs would swap in without harness changes. This is the first rung with a model in it, and the claim held: **scorer, loader, splits, results log, and the `Rung` protocol required no modification.** The only edit outside the new module was three lines registering the rung in the CLI.

### Decisions

**Cost is `0.0` per prediction, not a fabricated share of the index build.** Splitting an amortised one-off across instances would produce a per-instance figure that changes when the split size changes, which is worse than a zero with an explanation.

**The encoder loads on first use.** Constructing the rung imports no torch, so `--rung bm25` stays runnable without the optional extra even though both live behind one CLI. Pinned by a test.

**The query prefix lives on `ModelSpec` and is applied by the rung.** bge is trained asymmetrically — instruction on the query, none on the document — and omitting it costs quality with no error. A test asserts the encoder actually receives the prefixed text.

**Similarity is a plain dot product**, because vectors are unit-normalised at write time. Nothing in the rung re-normalises, so a future change that stored unnormalised vectors surfaces as a wrong number rather than a quietly different metric.

**Query vectors are cached by issue text.** It earns nothing today — each instance is scored once — and exists because rung 3 will re-score the same issue against reordered candidates.
