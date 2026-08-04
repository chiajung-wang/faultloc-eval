# ADR-0007: A local embedding model, pinned by revision

**Status:** Accepted · 2026-08-04 — *local vs hosted is settled; the specific local model is **provisional** pending measurement, see “The candidate set was stale” below*

## Context

Rung 2 embeds AST Chunks and ranks them against embedded issue text. Choosing the model settles two of the open questions in [`docs/PRD.md`](../PRD.md): which embedding model, hosted or local; and how the index is cached across the ~500 base commits.

Anthropic publishes no embeddings endpoint — the Claude API surface is Messages, Batches, Files, Models, and Token Counting. "Hosted" here therefore means a third-party provider (Voyage, OpenAI, Cohere), which is a different dependency from the one the project already carries for rungs 3 and 4.

Measured index volume, dev split, at code `234b566`:

| | Count |
|---|---|
| Distinct blobs | 32,667 |
| Chunks | 753,421 |
| Tokens, chunks as currently defined | 106,216,710 |
| Tokens, if bodies are indexed (issue 06) | 302,596,012 |

## Decision

A **local** model, run through `sentence-transformers`, pinned by identifier *and* revision:

| Field | Value |
|---|---|
| Model | `BAAI/bge-small-en-v1.5` |
| Revision | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` |
| Dimensions | 384 |
| Max sequence | 512 tokens |
| Licence | MIT |
| Query prefix | `Represent this sentence for searching relevant passages: ` |
| Document prefix | none |

Chunk embeddings are cached keyed by **blob SHA**, matching the tree cache in `RepoStore` and the token cache in `Bm25Rung`. A blob SHA is a content hash, so an entry can never go stale and is shared by every instance and repository holding that content. The cache stores the model identifier and revision alongside the vectors, so a cache built by a different model can never be read as if it matched.

## Rationale

**Reproducibility is the constraint that decides this.** Every entry in `RESULTS.md` claims a reader can regenerate the number from a commit, a dataset revision, and a split seed. A hosted model breaks that twice: reproduction requires someone else's API key, and the weights behind a stable model name can change with no revision to pin. That is precisely the failure ADR-0006 pins the dataset revision to prevent — an input that moves a number with nobody noticing.

**Cost does not decide it, but no longer argues against it.** At list prices a full dev-split index runs roughly $2 (OpenAI `text-embedding-3-small`) to $19 (`voyage-code-3`) as chunks are defined today, and $6 to $54 if issue 06 puts bodies back. Modest — but the test split adds ~50% more instances at M7, a chunk-definition change invalidates the blob cache wholesale rather than incrementally, and any second model for comparison doubles it again. Local is $0 across all of those.

**Why this model rather than a larger or a code-specialised one.**

*Its main branch has not moved since 2024-02-22.* `sentence-transformers/all-MiniLM-L6-v2`, the obvious alternative, moved on 2026-06-01 — a live demonstration that a model name is not provenance.

*384 dimensions.* 753,421 chunks × 384 × 4 bytes is 1.16 GB in float32. At 768 dimensions that doubles, and issue 03 has to write, store, and reload it every run.

*No `trust_remote_code`.* Both code-specialised candidates — `jinaai/jina-embeddings-v2-base-code` and `nomic-ai/nomic-embed-text-v1.5` — execute code fetched from the Hub at load time. A supply-chain dependency inside a benchmark whose entire claim is reproducibility is a poor trade for an unmeasured quality gain.

*33M parameters, CPU-viable.* The CI gate planned for M9 needs no GPU.

**No MTEB scores are cited here, deliberately.** This project measures Top-1 on its own instances with its own filter. A leaderboard average over unrelated retrieval tasks would be borrowed evidence for a number the project produces directly.

## Consequences

**Rung 2's cost column will read `$0.00`.** That weakens the priced-ladder story at exactly the rung it was meant to start biting. Accepted: rung 3 puts real money on the table, and a fabricated cost would be worse than a zero.

**The 512-token cap truncates the whole-file fallback chunks.** 5.5% of chunks are whole-file fallbacks and they carry most of the 106M-token corpus; each is represented by its first ~512 tokens. This should be made explicit — a length cap decided in issue 06 — rather than left to the tokenizer to do invisibly, because silent truncation looks identical to weak retrieval in every metric published.

*Amended 2026-08-04: this consequence is a property of the model chosen, not of the decision to run locally. See below.*

**The query prefix is load-bearing.** bge models are trained asymmetrically: queries carry the instruction above, documents carry none. Omitting it costs retrieval quality quietly, so it belongs in code with a test rather than in a comment.

**A third party can reproduce rung 2 with no API key**, which is the property this decision was made to buy.

## Revisit condition

If rung 2 fails to beat rung 1 *and* issue 06 shows that indexing bodies is what matters, a hosted model becomes worth measuring — because the plausible advantage is over body text, which the current chunk definition does not index at all. It would be published as an additional variant row with its cost, never as a replacement that quietly changes what the rung-2 number means.

**Select by criteria at the time, not by a name written here.** Hosted embedding models turn over every few months, and a model named in this ADR will be stale before the condition is met. The criteria:

1. **Long enough context** to hold a body-inclusive chunk without truncation — the constraint that makes hosted worth considering at all, since the local pick caps at 512 tokens
2. **A pinnable version identifier**, so the variant row's provenance is as reproducible as every other number in `RESULTS.md`
3. **Priced, with the price reported in the row** — a hosted rung that hides its cost defeats the ladder
4. **Evidence on code retrieval**, treated as a reason to *measure* rather than as the result

Criterion 4 needs stating plainly: this project measures its own Top-1 on its own instances. A vendor's benchmark claim decides which model is worth one run, never what the number is.

**The first draft of this ADR named `voyage-code-3` here, and that was wrong on its own terms.** It was chosen for code-specialisation, but Voyage's current material states that its general-purpose voyage-4 family outperforms the domain-specific models — so the stated reason had already stopped holding. `voyage-context-4` is the more interesting candidate today precisely because it is chunking-aware, which is this milestone's open question. Recorded rather than quietly edited away: a decision written from recall instead of a check is the failure mode this ADR series exists to prevent.

## The candidate set was stale (amended 2026-08-04)

The local-vs-hosted argument above stands: it rests on reproducibility, and no measurement changes it. **The choice of local model does not stand on the same evidence.**

`bge-small-en-v1.5` is a February 2024 model, and it was never compared against anything from 2025–2026. The current field, with revisions:

| Model | params | dim | context | licence | last moved |
|---|---|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | 33M | 384 | **512** | MIT | 2024-02-22 |
| `Qwen/Qwen3-Embedding-0.6B` | 596M | 1024 (MRL) | 32k | Apache-2.0 | 2026-04-20 |
| `BAAI/bge-m3` | 568M | 1024 | 8192 | MIT | 2024-07-03 |
| `Snowflake/snowflake-arctic-embed-m-v2.0` | 305M | 768 | 8192 | Apache-2.0 | 2025-04-24 |
| `google/embeddinggemma-300m` | 308M | 768 (MRL) | 2048 | Gemma, gated | 2025-09-25 |
| `jinaai/jina-embeddings-v3` | 572M | 1024 | 8192 | CC-BY-NC-4.0 | 2026-04-08 |

**The 512-token truncation recorded above as an accepted consequence is therefore not inherent** — every current option carries 2k–32k context. This ADR documented a stale pick's limitation as though it were a property of running locally.

The original reasoning is not worthless: 33M parameters against 596M is roughly 18× the compute over 753,421 chunks, on a laptop, re-run whenever the chunk definition changes. That constraint is real. It was also never measured, which is the actual defect — two decisions in this ADR were written to different standards of evidence, and only the revision pins were checked.

**Resolved by measurement, not by a second guess.** Issue 07 benchmarks the incumbent against `bge-m3` and `Qwen3-Embedding-0.6B` on throughput, index size, peak RAM, and truncation rate, and amends this ADR with the result — confirming the pin or replacing it. It is scheduled before issue 03, so nothing is built on an unmeasured pin.

Left on the record rather than silently corrected: an ADR that hides having been wrong is worth less than one that shows its own correction, and this series exists to catch exactly the failure it committed.

## Alternatives rejected

- **Voyage (`voyage-code-3` priced at $0.18/1M, with 200M free tokens covering the first index)** — rejected on reproducibility: no API key, no number. Note the code-specialisation argument is weaker than it looks; see the revisit condition above
- **OpenAI `text-embedding-3-small`** — cheapest hosted option at roughly $2 per dev-split index, but carries the same API-key and silent-reweighting exposure for a saving that is not the constraint
- **`BAAI/bge-base-en-v1.5`** — same family, 768 dimensions; doubles storage and compute for a gain this project has not measured and does not need to guess at
- **`jinaai/jina-embeddings-v2-base-code`** — code-trained with an 8192-token context that would fit the fallback chunks whole. Rejected for `trust_remote_code`; the strongest candidate to revisit if the condition above is met
- **`sentence-transformers/all-MiniLM-L6-v2`** — ubiquitous and fast, but weaker at the same dimensionality, and its recent branch movement is the argument against treating a model name as a pin
