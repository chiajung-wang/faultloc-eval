# 07 — Measure before pinning: local embedding model bake-off

Status: done

## Parent

[M3 PRD](../PRD.md)

## Why this exists

[ADR-0007](../../../docs/adr/0007-embedding-model.md) pinned `BAAI/bge-small-en-v1.5` on reasoning that was sound about *hosted vs local* and unexamined about *which local model*. The candidate set was never compared against anything from 2025–2026 — bge-small is a February 2024 model — and the omission produced a documented "accepted consequence" that is not actually inherent:

> **The 512-token cap truncates the whole-file fallback chunks.**

That is a limitation of a 2024 model, not of local embedding. Every serious 2026 option carries 2k–32k context. The ADR recorded a stale pick's constraint as though it were a property of the decision.

The fix is not to swap the pin from recall a second time. It is to measure the one number that actually decides it — **throughput on this hardware** — because the real trade is long context against the compute to embed 753,421 chunks on a laptop, re-run whenever the chunk definition changes.

## What to build

A benchmark script and a written result. Not production code — it runs once, informs an ADR amendment, and can live under `.scratch/` or `scripts/`.

### Models

| Model | Revision | Role |
|---|---|---|
| `BAAI/bge-small-en-v1.5` | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` | Incumbent — the floor to beat |
| `BAAI/bge-m3` | `5617a9f61b028005a4858fdac845db406aefb181` | Long context (8192), MIT, different architecture at similar size to Qwen |
| `Qwen/Qwen3-Embedding-0.6B` | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | Current generation: 32k context, Apache-2.0, code-retrieval training, MRL |

Pin every model by revision, not by name. `sentence-transformers/all-MiniLM-L6-v2` moved its main branch on 2026-06-01 while bge-small has not moved since 2024-02-22 — a model name is not provenance, and that is half of what ADR-0007 is about.

Excluded, and the reasons belong in the write-up: `google/embeddinggemma-300m` is a gated download needing HF auth, which is friction inside M9's CI gate; `jinaai/jina-embeddings-v3` is CC-BY-NC-4.0; `nomic-embed-text-v2-moe` caps at 512 context and so does not address the problem that prompted this; `snowflake-arctic-embed-m-v2.0` spends capacity on multilingual for an English-and-Python workload.

### Measurements

**Throughput** — chunks/sec on real chunk text drawn from the dev split, sampled across repositories and deliberately including whole-file fallback chunks, which are a small share of chunks but carry most of the tokens. Extrapolate to all 753,421. Report the hardware and whether MPS, CUDA, or CPU was used; a number without the device is meaningless.

**Index size on disk** — dimensions × 4 bytes × 753,421. 1.16 GB at 384d, 3.09 GB at 1024d. Note where MRL can cut it without re-embedding.

**Peak RAM and cold download size** — both bound whether M9's CI gate can run this at all.

**Truncation** — the share of chunks exceeding each model's context limit, and the share of the corpus's 106,216,710 tokens discarded as a result. This needs no embedding at all: tokenize and count. It is the cheapest measurement here and the one that decides whether long context is worth paying for.

### Explicitly not measured

**Retrieval quality.** Ranking these three on a micro-benchmark would be borrowed evidence — the failure ADR-0007 names directly. Quality means Top-1 on this project's own instances, which is issue 04's job. This issue answers *"which of these can we afford to run?"*, so that feasibility narrows the field before the expensive question is asked.

## Acceptance criteria

- [ ] All three models benchmarked on the same sampled chunks, on the same machine, each pinned by revision
- [ ] Throughput reported as chunks/sec plus extrapolated wall-clock for the full 753,421-chunk index, with the device stated
- [ ] Index size, peak RAM, and cold download size reported per model
- [ ] Truncation reported per model: share of chunks over the limit, and share of the 106M corpus tokens dropped
- [ ] A recommendation with its reasoning, and ADR-0007 amended — either confirming the pin with measurements behind it, or changing it
- [ ] The amendment records that the original candidate set was stale, rather than editing the history away
- [ ] `uv run ruff check` clean; new dependencies (`sentence-transformers`, `torch`) declared in `pyproject.toml`

## Notes

If bge-small wins on feasibility and the truncation loss turns out small, the ADR stands and this issue cost an hour. That is a good outcome, not a wasted one — it converts a recollection into a measurement.

The three models differ in query-prefix convention: bge wants `Represent this sentence for searching relevant passages: ` on queries only, Qwen3 uses an instruct-style prompt. Prefixes do not move throughput but they are load-bearing for issue 04, so record whichever convention the winning model needs.

Watch for a confound: the first run of any model includes its download. Time a warm run, or state clearly that the figure includes a cold start.

## Blocked by

- [01 — BM25 over AST Chunks](01-bm25-over-chunks.md) — done; supplies the chunker the sample is drawn from

## Comments

**Closed 2026-08-04.** The pin holds — but for a different reason than ADR-0007 originally gave, and conditional on a change to issue 06.

Apple M5, 25.7 GB RAM, MPS, `sentence-transformers` 5.6.1. 25,000 chunks reservoir-sampled uniformly from all 753,421; identical harness, order, and token-budgeted batching for every model. Raw results in `data/bench/results.jsonl`.

| Model | ctx | chunks/s | full index | index | peak RSS | download | corpus tokens dropped |
|---|---|---|---|---|---|---|---|
| `bge-small-en-v1.5` | 512 | **75.7** | **2.8 h** | 1.16 GB | 0.69 GB | 0.27 GB | **59.3%** |
| `bge-m3` | 8192 | 2.3 | 89.5 h | 3.09 GB | 2.53 GB | 4.84 GB | 25.9% |
| `Qwen3-Embedding-0.6B` | 32768 | 0.4 | **487 h** | 3.09 GB | 1.60 GB | 2.42 GB | 3.1% |

### The trade is monotonic and far steeper than expected

Every token of recovered context costs roughly two orders of magnitude of throughput. 487 hours is twenty days for a single index, on a corpus that rebuilds whenever the chunk definition changes. The premise behind this issue — that a 2026 long-context model would remove the truncation problem — is false on this hardware. It removes the truncation and replaces it with a wall.

### The measurement reframed the question

All three rows are dominated by the same 1.6% of chunks. `bge-m3` at 8192 tokens still discards a quarter of the corpus, which means the fallback tail runs far past 8192. The problem was never the model's context window. **It is that a whole file is being handed to a sentence encoder as a single document.**

Windowing a fallback into a sequence of 512-token pieces recovers the text that truncation discards, at the small model's speed: fallbacks carry ~58M tokens, so ~114,000 extra chunks — **+13% chunk count for 0% content loss**, still under three hours. `Qwen3-Embedding-0.6B` buys a 3.1% loss for 487 hours.

**So the pin holds, conditional on issue 06 windowing rather than truncating.** Without that change, `bge-small` means discarding 59% of the corpus, which no published accuracy number could survive being asked about.

### A figure this corrected

The whole-file fallback share was quoted as **5.5%** in ADR-0007 and issues 01, 02, and this one. That came from a 40-instance probe. Measured over all 753,421 chunks by uniform reservoir sample:

| kind | count | share of chunks | share of text | mean chars |
|---|---|---|---|---|
| function | 22,041 | 88.2% | 35.7% | 191 |
| class | 2,557 | 10.2% | 8.8% | 407 |
| **file** (fallback) | 402 | **1.6%** | **55.4%** | **16,296** |

The claim built on it survives and is now measured rather than inferred — fallbacks do carry the majority of the corpus — but the share is 1.6%, not 5.5%, and the skew is far sharper: 85× the mean size of a function chunk. Corrected everywhere it appeared.

### Caveats stated so they cannot flatter the result

**75.7 chunks/s is a floor, not a ceiling.** It measures a naive per-batch `encode()` loop with an MPS round-trip per batch. A real indexer batching more aggressively will beat it, so issue 03 must not treat 2.8 hours as the achievable index time. The comparison is still sound — all three ran the identical harness, and a 190× gap cannot be reversed by harness overhead.

**Truncation percentages ride on 402 sampled chunks.** Those carry 55% of the sampled text, so the estimate is noisy in a way a bare percentage hides. The sample's own extrapolated corpus size, 89.0M tokens, differs ~16% from the exact 106.2M measured over every blob — that gap is the sampling error on this statistic, and the truncation figures should be read with the same width.

**Retrieval quality was deliberately not measured**, as the issue specified. These numbers say which models are affordable, not which retrieves best. That question is Top-1 on this project's own instances, and it belongs to issue 04.

### Two bugs worth recording

**The first benchmark run measured nothing.** A `for spec in "model revision"` loop with `set -- $spec` silently passed each pair as one argument — zsh does not word-split unquoted parameter expansions the way bash does. All three models failed identically with `Repo id must use alphanumeric chars`, which at least made the failure loud rather than subtly wrong.

**Fixed-size batching would have made the comparison meaningless.** A batch of 32 whole-file chunks is ~1M tokens on a 32k-context model — enough to exhaust memory — while a batch small enough to be safe there would throttle the 512-token model and understate it. Batches are built to an 8192-token budget instead, which is both memory-safe and the policy a real indexer would use.
