# M3 — Embedding retrieval over AST Chunks (rung 2)

## Goal

A rung-2 number on the dev split, reported as a **delta over rung 1** at its cost and latency, alongside the ablation that says which half of the change earned it.

## Why the ablation is the milestone, not a footnote

Rung 2 changes **two** things at once:

1. the matching function — word overlap → embedding similarity
2. the index unit — whole files → AST Chunks

A win measured against rung 1 is therefore unattributable. It could be entirely a chunking effect, achievable with no model and no cost at all, and reporting it as "embeddings beat BM25" would be an overclaim of exactly the kind this project exists not to make.

Running BM25 over the same chunks isolates the two. It needs no new infrastructure beyond the chunker rung 2 already requires, so it is built **first** — issue 01 — and the embedding rung inherits its chunker and its chunk→file aggregation rule already tested. Sequenced the other way, the ablation becomes optional cleanup at the exact moment the interesting number already exists.

Three rows, same instances, same scorer:

| Row | Matching | Index unit | Isolates |
|---|---|---|---|
| bm25 (M1) | lexical | whole file | — |
| bm25-chunks | lexical | AST Chunk | chunking alone |
| bm25-chunks + bodies | lexical | AST Chunk + body | body exclusion, within chunking |
| embed | dense | AST Chunk | embeddings, given chunking |

The fourth row was added after the second was measured. Chunking alone cost 8.6pp of Recall@3 and 9.5pp of Recall@5, and a recall drop that size means files stopped being retrievable rather than being ranked lower — a content effect. It exposed that "chunking" is itself two changes: the unit shrinks to a definition, *and* the body stops being indexed. Issue 06 separates them, and it runs before anything is paid to embed, because `CONTEXT.md`'s AST Chunk definition is what rung 2 would index.

## Done when

- `faultloc evaluate --rung bm25-chunks --split dev` and `--rung embed --split dev` both run end to end and emit their own `RESULTS.md` entries
- Rung 2's cost and latency are real measured figures, not zeros
- The README ladder table carries all three rows with deltas and overlapping-interval caveats where they apply
- The embedding model choice and index-cache strategy are recorded in an ADR

## The open question this milestone answers

`sphinx-doc/sphinx` scores 4.5% Top-1 at rung 1, truth at median rank 40 of only 541 candidates — the worst ratio in the set. Its reports describe *rendered output* in vocabulary absent from the code producing it, which is precisely the gap lexical matching cannot cross. If embeddings earn their cost anywhere, it is there. If Sphinx does not move, that is the finding.

## Out of scope

LLM reranking (M4), the agent (M5), the Fresh Set (M6), calibration (M7). No model is asked to *reason* about a candidate at this rung — only to embed it.
