# ADR-0007: A local embedding model, pinned by revision

**Status:** Accepted · 2026-08-04 · *measurement confirmed the model pin (issue 07). Issue 06 met the windowing condition the same day.*

## Context

Rung 2 embeds AST Chunks and ranks them against embedded issue text. The model choice settles two open questions in [`docs/PRD.md`](../PRD.md). First, which embedding model, hosted or local. Second, how the index caches across the ~500 base commits.

Anthropic publishes no embeddings endpoint. The Claude API surface is Messages, Batches, Files, Models, and Token Counting. "Hosted" here therefore means a third-party provider such as Voyage, OpenAI, or Cohere. That is a different dependency from the one the project already carries for rungs 3 and 4.

Measured index volume, dev split, at code `234b566`:

| | Count |
|---|---|
| Distinct blobs | 32,667 |
| Chunks | 753,421 |
| Tokens, chunks as currently defined | 106,216,710 |
| Tokens, if bodies are indexed (issue 06) | 302,596,012 |

*Updated 2026-08-04 after issue 06 landed. The chunk definition now windows at 2,048 characters and indexes bodies. The index this ADR sizes therefore holds **1,013,340 chunks at ~228M tokens**, which is +34.5% chunks over the row above. Windowing accounts for +19.0% of that at zero token cost. Bodies account for the rest. The 302.6M estimate was a crude upper bound that double-counted nested definitions. At 384 dimensions the index takes **1.56 GB** as float32, and a full build takes **~3.7 hours** at the throughput measured below.*

## Decision

A **local** model, run through `sentence-transformers`, pinned by identifier *and* revision:

| Field | Value |
|---|---|
| Model | `BAAI/bge-small-en-v1.5` |
| Revision | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` |
| Dimensions | 384 |
| Max sequence | 512 tokens |
| License | MIT |
| Query prefix | `Represent this sentence for searching relevant passages: ` |
| Document prefix | none |

The cache keys chunk embeddings by **blob SHA**. This matches the tree cache in `RepoStore` and the token cache in `Bm25Rung`. A blob SHA is a content hash, so an entry can never go stale. Every instance and every repository that holds that content shares the entry. The cache stores the model identifier and revision beside the vectors. A cache built by a different model can therefore never pass as a match.

## Rationale

**Reproducibility is the constraint that decides this.** Every entry in `RESULTS.md` claims a reader can regenerate the number from a commit, a dataset revision, and a split seed. A hosted model breaks that twice. Reproduction needs someone else's API key. Also, the weights behind a stable model name can change with no revision to pin. ADR-0006 pins the dataset revision to prevent exactly that failure: an input that moves a number while nobody notices.

> **Amended 2026-08-05 — this paragraph conflates two independent things, and the error excluded a real option.**
>
> *Hosted* and *proprietary* are different axes. Reproducibility comes from **execution**. Auditability comes from **weights**.
>
> The second half of the argument above concerns weights that change under a stable name. It applies only to **proprietary** hosting. An inference provider can serve an open-weights model pinned to a published revision, and that model does not have the problem. The artifact is public, and a third party with the hardware can verify it. The first half, the need for an API key, still applies.
>
> So this ADR rejected "hosted" as a category with an argument that defeats only part of it. **Nobody considered open-weights hosted embeddings.** That matters more than a wording fix. Issue 07's central finding was a *throughput* wall. `Qwen3-Embedding-0.6B` scored a 3.1% truncation loss against `bge-small`'s 59%, and 487 hours of local indexing rejected it. **Those 487 hours are a property of local execution, not of the model.** Served, the same auditable weights would have been practical.
>
> The decision is not reversed here — `bge-small` is measured, built, and the numbers stand — but the reasoning behind it was narrower than stated, and the revisit condition below now has a concrete target rather than a category.

**Cost does not decide it, but no longer argues against it.** At list prices, a full dev-split index costs roughly $2 (OpenAI `text-embedding-3-small`) to $19 (`voyage-code-3`) under today's chunk definition. It costs $6 to $54 if issue 06 puts bodies back. Those figures are modest, but three things multiply them. The test split adds ~50% more instances at M7. A chunk-definition change invalidates the blob cache wholesale rather than incrementally. Any second model for comparison doubles the cost again. Local costs $0 in every one of those cases.

**Why this model rather than a larger or a code-specialized one.**

*Its main branch has not moved since 2024-02-22.* `sentence-transformers/all-MiniLM-L6-v2`, the obvious alternative, moved on 2026-06-01. That is a live demonstration that a model name is not provenance.

*384 dimensions.* 753,421 chunks × 384 × 4 bytes is 1.16 GB in float32. At 768 dimensions that doubles, and issue 03 must write, store, and reload it every run.

*No `trust_remote_code`.* Both code-specialized candidates execute code fetched from the Hub at load time: `jinaai/jina-embeddings-v2-base-code` and `nomic-ai/nomic-embed-text-v1.5`. This benchmark claims reproducibility above all else. A supply-chain dependency inside it is a poor trade for an unmeasured quality gain.

*33M parameters, CPU-viable.* The CI gate planned for M9 needs no GPU.

**This ADR cites no MTEB scores, deliberately.** This project measures Top-1 on its own instances with its own filter. A leaderboard average over unrelated retrieval tasks would borrow evidence for a number the project produces directly.

## Consequences

**Rung 2's cost column will read `$0.00`.** That weakens the priced-ladder story at the exact rung where it was meant to start biting. Accepted. Rung 3 puts real money on the table, and a fabricated cost would be worse than a zero.

**The 512-token cap truncates the whole-file fallback chunks.** Whole-file fallbacks are **1.6%** of chunks but carry **55%** of the corpus text. Their mean length is 16,296 characters against 191 for a function chunk. At a 512-token limit, 3.55% of chunks run over, and the index discards an estimated **63M of the 106M corpus tokens**. Issue 06 must decide this length policy explicitly rather than leave it to the tokenizer. Silent truncation looks identical to weak retrieval in every metric this project publishes.

*Amended 2026-08-04, twice. A 40-instance probe produced the 5.5% fallback share originally written here. Measured over all 753,421 chunks, the share is 1.6%, and the skew is sharper than the text described. Issue 07 then measured the truncation loss at 59% of corpus tokens. That runs far past what "accepted consequence" covered, and it is why the answer is to reshape the chunks rather than to accept the loss. See below.*

**The query prefix is load-bearing.** bge models train asymmetrically. Queries carry the instruction above. Documents carry none. Drop the prefix and retrieval quality falls quietly, so it belongs in code with a test rather than in a comment.

**A third party can reproduce rung 2 with no API key.** That is the property this decision bought.

## Revisit condition

A hosted model becomes worth a measurement if two things hold: rung 2 fails to beat rung 1, *and* issue 06 shows that body indexing is what matters. The plausible advantage sits over body text, which the current chunk definition does not index at all. Publish such a model as an extra variant row with its cost. Never publish it as a replacement that quietly changes what the rung-2 number means.

**Select by criteria at the time, not by a name written here.** Hosted embedding models turn over every few months. A model named in this ADR will be stale before the condition is met. The criteria:

1. **Long enough context** to hold a body-inclusive chunk without truncation. Issue 07's measurement weakens this criterion. A window over a long chunk recovers the same text locally, so hosted context helps only when the model needs the *unwindowed* document
2. **A pinnable version identifier**, so the variant row's provenance matches every other number in `RESULTS.md`
3. **Priced, with the price reported in the row** — a hosted rung that hides its cost defeats the ladder
4. **Evidence on code retrieval**, read as a reason to *measure* rather than as the result

**Prefer open weights, served.** The amendment above names the cell the original reasoning skipped. Public, revision-pinnable weights remove criterion 2's exposure entirely. Hosted execution removes the throughput wall that decided against every strong model in issue 07's bake-off. The cheapest concrete revisit is `Qwen3-Embedding-0.6B`. This ADR already measured it at a 3.1% truncation loss against `bge-small`'s 59%, and rejected it only on 487 hours of local indexing.

Criterion 4 needs a plain statement. This project measures its own Top-1 on its own instances. A vendor's benchmark claim decides which model is worth one run. It never decides what the number is.

**The first draft of this ADR named `voyage-code-3` here, and that was wrong on its own terms.** The draft chose it for code specialization. But Voyage's current material states that its general-purpose voyage-4 family outperforms the domain-specific models, so the stated reason had already stopped holding. `voyage-context-4` is the more interesting candidate today, because it is chunking-aware, and chunking is this milestone's open question. This record stays rather than disappear into a quiet edit. A decision written from recall instead of a check is the failure mode this ADR series exists to prevent.

## The candidate set was stale (amended 2026-08-04)

The local-vs-hosted argument above stands: it rests on reproducibility, and no measurement changes it. **The choice of local model does not stand on the same evidence.**

`bge-small-en-v1.5` is a February 2024 model, and it was never compared against anything from 2025–2026. The current field, with revisions:

| Model | params | dim | context | license | last moved |
|---|---|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | 33M | 384 | **512** | MIT | 2024-02-22 |
| `Qwen/Qwen3-Embedding-0.6B` | 596M | 1024 (MRL) | 32k | Apache-2.0 | 2026-04-20 |
| `BAAI/bge-m3` | 568M | 1024 | 8192 | MIT | 2024-07-03 |
| `Snowflake/snowflake-arctic-embed-m-v2.0` | 305M | 768 | 8192 | Apache-2.0 | 2025-04-24 |
| `google/embeddinggemma-300m` | 308M | 768 (MRL) | 2048 | Gemma, gated | 2025-09-25 |
| `jinaai/jina-embeddings-v3` | 572M | 1024 | 8192 | CC-BY-NC-4.0 | 2026-04-08 |

**The 512-token truncation recorded above as an accepted consequence is therefore not inherent.** Every current option carries 2k–32k context. This ADR documented a stale pick's limitation as though local execution caused it.

The original reasoning is not worthless. 33M parameters against 596M is roughly 18× the compute over 753,421 chunks, on a laptop, re-run whenever the chunk definition changes. That constraint is real. Nobody measured it, and that is the actual defect. This ADR wrote two decisions to different standards of evidence, and checked only the revision pins.

**Measurement resolved this, not a second guess.** Issue 07 benchmarked the incumbent against `bge-m3` and `Qwen3-Embedding-0.6B` on throughput, index size, peak RAM, and truncation. Raw results: [`data/bench/results.jsonl`](../../data/bench/results.jsonl).

This record stays rather than disappear into a silent correction. An ADR that hides its own error is worth less than one that shows its correction. This series exists to catch the exact failure it committed.

## Measured (2026-08-04) — the pin holds, for a different reason

Apple M5, 25.7 GB RAM, MPS, `sentence-transformers` 5.6.1. The benchmark reservoir-sampled 25,000 chunks uniformly from all 753,421 in the dev-split index. Every model ran the identical harness, order, and token-budgeted batching.

| Model | ctx | chunks/s | **full index** | index size | peak RSS | download | corpus tokens dropped |
|---|---|---|---|---|---|---|---|
| `bge-small-en-v1.5` | 512 | **75.7** | **2.8 h** | 1.16 GB | 0.69 GB | 0.27 GB | **59.3%** |
| `bge-m3` | 8192 | 2.3 | 89.5 h | 3.09 GB | 2.53 GB | 4.84 GB | 25.9% |
| `Qwen3-Embedding-0.6B` | 32768 | 0.4 | **487 h** | 3.09 GB | 1.60 GB | 2.42 GB | 3.1% |

The trade is monotonic and brutal. Every token of context recovered costs roughly two orders of magnitude of throughput. 487 hours is twenty days for one index, on a corpus that must be rebuilt whenever the chunk definition changes. Long context does not rescue this.

**But the measurement reframes the question.** The same 1.6% of chunks dominates all three rows. `bge-m3` at 8192 tokens still discards a quarter of the corpus, so the fallback chunks' tail runs far past even that. The model's context window is not the problem. The problem is that a whole file goes to a sentence encoder as one document.

**The fix is to reshape the chunk, not to buy context.** Split each fallback into a sequence of windows sized to the model's limit. That preserves the text truncation would discard, and it runs at the small model's speed. Estimated: fallbacks carry ~58M tokens, which at 512 tokens per window gives ~114,000 additional chunks. That is roughly **+13% chunk count for 0% content loss**, still inside three hours. Against that, `Qwen3-Embedding-0.6B` buys a 3.1% loss for 487 hours.

**Decision: the pin holds** — `BAAI/bge-small-en-v1.5` at the revision above. The reasoning is now measured rather than assumed. One condition applies: **issue 06 must window the fallback chunks instead of letting the tokenizer truncate them.** Without that, the pin discards 59% of the corpus, and no accuracy number survives that question.

*Condition met 2026-08-04.* Issue 06 landed windowing at 2,048 characters, measured at +19.0% chunks for zero token loss, and no chunk exceeded the budget. The pin is now unconditional. Note that the index it sizes grew. With bodies included it holds 1,013,340 chunks, so **1.56 GB and ~3.7 hours**, not 1.16 GB and 2.8.

**One caveat, stated so it cannot flatter the result.** 75.7 chunks/s is a floor, not the model's ceiling. It comes from a naive per-batch `encode()` loop with an MPS round-trip per batch. A real indexer that batches more aggressively will beat it. The comparison still holds, because all three models ran the identical harness, and the 190× gap between fastest and slowest is far too large for implementation overhead to reverse. Issue 03 must not treat 2.8 hours as the achievable index time. It is an upper bound.

## Alternatives rejected

- **Voyage (`voyage-code-3` priced at $0.18/1M, with 200M free tokens covering the first index)** — rejected on reproducibility. No API key, no number. The code-specialization argument is also weaker than it looks. See the revisit condition above
- **OpenAI `text-embedding-3-small`** — cheapest hosted option at roughly $2 per dev-split index. It carries the same API-key and silent-reweighting exposure, for a saving that is not the constraint
- **`BAAI/bge-base-en-v1.5`** — same family, 768 dimensions. It doubles storage and compute for a gain this project has not measured and need not guess at
- **`jinaai/jina-embeddings-v2-base-code`** — code-trained, with an 8192-token context that would hold the fallback chunks whole. Rejected for `trust_remote_code`. It is the strongest candidate to revisit once the condition above is met
- **`sentence-transformers/all-MiniLM-L6-v2`** — common and fast, but weaker at the same dimensionality. Its recent branch movement is the argument against a model name as a pin
