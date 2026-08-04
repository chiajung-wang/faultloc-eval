# 02 — Pick the embedding model, record ADR-0007

Status: done

## Parent

[M3 PRD](../PRD.md)

## What to build

A decision, priced, written as `docs/adr/0007-embedding-model.md`, plus whatever pinning the choice implies (model identifier, revision, dimensionality, normalisation) so a reader can regenerate the index from the same inputs.

Two open questions from `docs/PRD.md` are settled here:

**Local or hosted.** A local sentence-transformers model costs nothing per run, keeps every number reproducible offline, and makes the cost column honestly `$0.00` at rung 2 — which weakens the ladder's cost story precisely where it was supposed to start biting. A hosted code-specialised model is likely stronger on identifier-dense text, but prices every full-corpus index, pins the project to an API whose weights can change under a stable name, and puts a paid dependency in the CI gate planned for M9.

**Index-cache strategy across ~500 base commits and ~12 repos.** Blob SHA is a content hash, so a chunk embedding keyed by it is never wrong and is shared across every instance and repository holding that content. Confirm this is the key, and state the expected distinct-blob count and what a cold build costs in dollars and wall-clock at the chosen model.

The ADR must state the rejected option and the condition under which the decision would be revisited.

## Acceptance criteria

- [ ] `docs/adr/0007-embedding-model.md` written in the existing ADR format, with rationale and rejected alternatives
- [ ] Model pinned by identifier *and* revision; embedding dimensionality and any normalisation stated
- [ ] Cold-index cost estimated in dollars and wall-clock, with the distinct-blob count it assumes
- [ ] Cache key stated, with the reason it cannot go stale
- [ ] Reproducibility consequence stated explicitly — whether a third party can regenerate the numbers without an API key
- [ ] `CONTEXT.md` updated if the decision introduces or renames domain language

## Notes

HITL because it spends the user's money and constrains M9's CI gate. It is unblocked, so it can be decided while issue 01 runs.

A hosted model chosen here does not have to be the only one measured — but any comparison of two embedding models is a rung-2 variant row, not a replacement for the ablation in issue 01.

## Blocked by

None — can start immediately, in parallel with issue 01.

## Comments

**Closed 2026-08-04.** Decision: **local**, `BAAI/bge-small-en-v1.5` @ `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, 384 dimensions, MIT. Recorded in [ADR-0007](../../../docs/adr/0007-embedding-model.md).

### The issue's framing was wrong on one point

This issue said "hosted" as if it were a first-party option. **Anthropic publishes no embeddings endpoint** — the API surface is Messages, Batches, Files, Models, and Token Counting. Hosted here means a third party (Voyage, OpenAI, Cohere), which is a different dependency from the one rungs 3 and 4 already carry. Corrected in the ADR.

### Measured, not estimated

Index volume over the whole dev split at code `234b566`:

```
distinct blobs:  32,667
chunks:          753,421
tokens now:      106,216,710
tokens w/bodies: 302,596,012
```

~141 tokens per chunk on average, and the distribution is heavily skewed: 5.5% of chunks are whole-file fallbacks and they carry most of the tokens.

The first estimate made during this discussion was ~7M tokens — **wrong by 15×**, because it assumed a chunk was a signature plus a docstring and forgot that the fallback chunks contain entire files. The measurement changed the shape of the cost argument (a full re-index runs $19 at `voyage-code-3`, not $1.26), though not the conclusion.

### Cost did not decide it

| Model | $/1M | 106M (as-is) | 303M (with bodies) |
|---|---|---|---|
| `voyage-code-3` | $0.18 | $19.12 | $54.47 |
| OpenAI `text-embedding-3-small` | $0.02 | $2.12 | $6.05 |
| local | — | $0 | $0 |

Modest either way. Three multipliers keep it from being negligible: the test split adds ~50% more instances at M7, a chunk-definition change invalidates the blob cache wholesale rather than incrementally, and a second model for comparison doubles it again.

**Reproducibility decided it.** Every `RESULTS.md` entry claims a reader can regenerate the number from a commit, a dataset revision, and a seed. A hosted model breaks that twice — reproduction needs someone else's API key, and weights can change under a stable name with no revision to pin.

### Why pinning a revision, not just a name

`sentence-transformers/all-MiniLM-L6-v2` — the obvious alternative — had its main branch move on **2026-06-01**. `BAAI/bge-small-en-v1.5` has not moved since 2024-02-22. A model name is not provenance, and this is the live demonstration of it.

### Two consequences that will bite if not written down

**The 512-token cap silently truncates the fallback chunks.** They carry most of the corpus, and each will be represented by its first ~512 tokens. Issue 06 should cap fallback length explicitly rather than let the tokenizer do it invisibly — silent truncation is indistinguishable from weak retrieval in every metric published.

**bge is asymmetric.** Queries need the prefix `Represent this sentence for searching relevant passages: `; documents get none. Omitting it costs retrieval quality quietly, so it belongs in code with a test, not in a comment.

### What was rejected, and a correction to how it was written

Hosted was rejected on reproducibility, not price. The plausible hosted advantage is over *body* text, which the current chunk definition does not index — so issue 06 is a prerequisite for the comparison being meaningful at all.

**The first draft of ADR-0007 named `voyage-code-3` as the model to revisit, and that was written from recall rather than a check.** Voyage's current material states its general-purpose voyage-4 family outperforms the domain-specific models, so the code-specialisation reason had already stopped holding; `voyage-context-4` — chunking-aware, which is this milestone's live question — is the more interesting candidate today. The ADR now names **selection criteria** instead of a model, because hosted models turn over faster than a conditional revisit that is months away.

Left on the record rather than edited away, for the same reason issue 05's Django prediction was: a decision written from memory instead of a check is exactly what this ADR series exists to catch.
