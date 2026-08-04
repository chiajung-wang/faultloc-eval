# 07 — Measure before pinning: local embedding model bake-off

Status: ready-for-agent

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

**Throughput** — chunks/sec on real chunk text drawn from the dev split, sampled across repositories and deliberately including whole-file fallback chunks, which are 5.5% of chunks but carry most of the tokens. Extrapolate to all 753,421. Report the hardware and whether MPS, CUDA, or CPU was used; a number without the device is meaningless.

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
