# 01 — BM25 over AST Chunks: the ablation, first

Status: ready-for-agent

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
