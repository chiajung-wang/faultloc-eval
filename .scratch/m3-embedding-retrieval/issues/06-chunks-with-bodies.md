# 06 — Chunks with bodies: which half of chunking cost the recall

Status: ready-for-agent

## Parent

[M3 PRD](../PRD.md)

## Why this exists

Issue 01 measured chunking alone and it lost: Top-1 39.3% → 37.3% with overlapping intervals, but Recall@3 −8.6pp and Recall@5 −9.5pp.

Recall falling that far means ground-truth files stopped being *retrievable at all* rather than being ranked lower. That is a property of the documents, not of the ordering — and it exposes that issue 01 changed **two** things while intending to change one:

1. the index unit became a definition rather than a file
2. the body stopped being indexed — a chunk is signature, docstring, and path

Only the second explains a recall collapse. Bug reports quote body tokens constantly: called functions, locals, string literals, error messages, traceback frames. Whole-file BM25 matched all of them; chunk documents contain none of them. On a 40-instance sample the corpus went from a median 3,360 files to 11,888 chunks — 3.5× the documents, a fraction of the text, and many functions have no docstring at all.

This is not a defect in issue 01's implementation. `CONTEXT.md` defines an AST Chunk as signature + docstring + path, so it indexed exactly what rung 2 is specified to embed. **That is the problem.** Rung 2 inherits the same corpus and starts ~9pp of recall below rung 1, and no similarity function retrieves a token that was never indexed.

Resolving it costs one line and two minutes. Issue 03 costs money and hours. This runs first.

## What to build

A variant of the chunk document that includes the definition's body, run end to end as its own row, so the two explanations can be told apart.

Mechanically small — `Chunk` already carries a `content` field used by the whole-file fallback, and `Chunk.text` already joins the non-empty parts. No new infrastructure, no new rung class if a flag on the existing one is cleaner. What must not change is the tokeniser, the aggregation rule, the candidate set, or the split.

Report it as a fourth row against the existing three. Then read it:

- **recall recovers** → the unit was never the problem and body exclusion was. `CONTEXT.md`'s AST Chunk definition is wrong for retrieval and rung 2's index must change before issue 03 builds it.
- **recall stays down** → splitting files into definitions is genuinely worse for this task, which is a larger finding and changes what rung 2 is for.

Whichever it is, record it in an ADR or in the `CONTEXT.md` definition, because issue 03 reads that definition to decide what to embed.

## Acceptance criteria

- [ ] Chunk documents can include the definition body, without duplicating the chunker
- [ ] Runs end to end on the dev split and emits its own `RESULTS.md` entry
- [ ] Tokeniser, aggregation rule, candidate set, split, and seed identical to issue 01's run — one variable moves
- [ ] Recall@3 and Recall@5 reported against both `bm25` and `bm25-chunks`, not Top-1 alone: Top-1's intervals are too wide at n=244 to settle this
- [ ] Corpus size reported — documents and their approximate token volume against issue 01's 11,888 chunks
- [ ] The conclusion written where issue 03 will read it: `CONTEXT.md`'s AST Chunk definition, amended if the evidence says so
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

Nesting means a naive body-inclusive chunk double-counts: a class's body contains its methods, which are chunks in their own right. Decide whether an outer definition carries its nested definitions' text or is trimmed to its own statements, and say which — it changes the corpus size and the length normalisation, and rung 2 will inherit whatever is chosen.

Sphinx is the sharpest single reading. It went 4.5% → 0.0% under issue 01, and it is the repo M1 predicted rung 2 would rescue. If bodies bring it back above zero, the M1 hypothesis is still alive. If it stays at zero with the full text indexed, its vocabulary genuinely is not in the code, and that is a data property no retrieval method fixes.

## Blocked by

- [01 — BM25 over AST Chunks](01-bm25-over-chunks.md) — done
