# 06 — Chunks with bodies: which half of chunking cost the recall

Status: done

## Parent

[M3 PRD](../PRD.md)

## Why this exists

Issue 01 measured chunking alone and it lost: Top-1 39.3% → 37.3% with overlapping intervals, but Recall@3 −8.6pp and Recall@5 −9.5pp.

Recall falling that far means ground-truth files stopped being *retrievable at all* rather than being ranked lower. That is a property of the documents, not of the ordering — and it exposes that issue 01 changed **two** things while intending to change one:

1. the index unit became a definition rather than a file
2. the body stopped being indexed — a chunk is signature, docstring, and path

Only the second explains a recall collapse. Bug reports quote body tokens constantly: called functions, locals, string literals, error messages, traceback frames. Whole-file BM25 matched all of them; chunk documents contain none of them. On a 40-instance sample the corpus went from a median 3,360 files to 11,888 chunks — 3.5× the documents, a fraction of the text, and many functions have no docstring at all.

*(That probe also reported the whole-file fallback share as 5.5%. Measured over all 753,421 chunks it is 1.6%, carrying 55% of the text — see the section added below.)*

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

## Added 2026-08-04: window the fallback chunks, do not truncate them

[Issue 07](07-embedding-model-bakeoff.md) measured what the whole-file fallbacks cost, and it lands on this issue.

Fallbacks are **1.6% of chunks carrying 55% of the corpus text** (mean 16,296 characters against 191 for a function chunk). The pinned embedding model caps at 512 tokens, which would silently discard an estimated **63M of the 106M corpus tokens**. Buying context instead is not viable: `bge-m3` at 8192 tokens still drops 25.9% and takes 89 hours to index; `Qwen3-Embedding-0.6B` at 32k drops 3.1% and takes 487 hours, against 2.8 hours for the pinned model.

**So a long fallback chunk must be split into a sequence of windows rather than handed over whole and truncated.** Estimated cost: fallbacks carry ~58M tokens, so ~114,000 additional chunks — roughly +13% chunk count for 0% content loss, still inside three hours.

This is now a requirement of this issue, not a suggestion: [ADR-0007](../../../docs/adr/0007-embedding-model.md)'s model pin is explicitly conditional on it.

- [ ] Long chunks are split into windows sized to a stated token budget, not truncated
- [ ] Window size and any overlap are stated with their rationale, and are the same for the lexical and dense rungs
- [ ] The resulting chunk-count increase is reported against the current 753,421

## Notes

Nesting means a naive body-inclusive chunk double-counts: a class's body contains its methods, which are chunks in their own right. Decide whether an outer definition carries its nested definitions' text or is trimmed to its own statements, and say which — it changes the corpus size and the length normalisation, and rung 2 will inherit whatever is chosen.

Windowing interacts with the chunk→file aggregation rule from issue 01: a file whose fallback becomes twenty windows now has twenty chances to produce its `max`. Whether that biases long files is worth a sentence, since the rule is shared with rung 2 and cannot be tuned per rung.

Sphinx is the sharpest single reading. It went 4.5% → 0.0% under issue 01, and it is the repo M1 predicted rung 2 would rescue. If bodies bring it back above zero, the M1 hypothesis is still alive. If it stays at zero with the full text indexed, its vocabulary genuinely is not in the code, and that is a data property no retrieval method fixes.

## Blocked by

- [01 — BM25 over AST Chunks](01-bm25-over-chunks.md) — done

## Comments

**Closed 2026-08-04.** The question is answered, and decisively: **body exclusion was the cost, not the change of index unit.**

Four lexical rows, same 244 dev instances, same tokeniser, same aggregation rule, same seed:

| Row | Top-1 | Recall@3 | Recall@5 |
|---|---|---|---|
| `bm25` — whole file (M1) | 39.3% (33.4–45.6) | 59.3% | 68.5% |
| `bm25-chunks` — unwindowed, no bodies (issue 01) | 37.3% (31.5–43.5) | 50.7% | 59.0% |
| `bm25-chunks` — windowed, no bodies | 39.8% (33.8–46.0) | 52.0% | 61.3% |
| `bm25-chunks-bodies` — windowed, bodies | **43.9%** (37.8–50.1) | **60.3%** | 65.7% |

**Recall@3 goes 52.0 → 60.3, back to parity with whole-file search at 59.3.** That was the number issue 01 flagged as the readable one, and it recovers almost exactly. Recall@5 recovers most of the way (61.3 → 65.7 against 68.5). Top-1 reaches 43.9%, the best of any lexical row — though its interval overlaps every other row's, so on Top-1 alone nothing here is established.

The reading issue 01 proposed was right: chunking was two changes, and only body exclusion explains a recall collapse. A token that was never indexed cannot be retrieved by any similarity function, and rung 2 would have inherited the same handicap had this not run first.

### Windowing on its own is worth little

`bm25-chunks` unwindowed → windowed is +2.5pp Top-1 and +2.3pp Recall@5, both well inside the intervals. That is a fair result to report: windowing was not adopted to raise the lexical number, it was adopted because the pinned embedding model truncates at 512 tokens and 1.6% of chunks carry 55% of the corpus (ADR-0007). It costs nothing lexically and buys the dense rung its content back.

Recorded so the rung-2 write-up cannot credit windowing with the body gain.

### Sphinx, and the M1 hypothesis

M1 predicted Sphinx as the clearest case for rung 2, on the theory that its reports describe rendered output in vocabulary absent from the code. Issue 01 dropped it to 0.0%.

**0.0% → 9.1% (windowing) → 18.2% (bodies)**, against rung 1's 4.5%. Four times the rung-1 number, with no model involved.

So the M1 hypothesis is wrong in an informative way. Sphinx's vocabulary *is* in the code — it is in the function bodies, not the signatures and docstrings. The whole-file baseline was already finding it; chunking without bodies threw it away, and restoring bodies more than recovers it. That weakens the case for Sphinx being the sharpest test of embeddings, and it is left on the record rather than edited away.

Django, the largest slice, moves the same way: 38.9 (rung 1) → 31.9 → 36.3 → **40.7**.

### Corpus size

Measured over all 32,667 distinct blobs in the dev split:

| Chunk definition | Chunks | Tokens (~chars/4) | Longest chunk |
|---|---|---|---|
| unwindowed, no bodies (issue 01) | 753,421 | 106,216,710 | 16,296+ chars |
| **windowed**, no bodies | 896,806 | 106,216,710 | 2,048 chars |
| **windowed, with bodies** | 1,013,340 | 228,019,345 | 2,048 chars |

**Windowing costs +19.0% chunks and zero tokens** — it redistributes text rather than adding or losing any, which is the whole claim, now measured rather than argued. The estimate in ADR-0007 was +13%; the real figure is +19%, because more chunks than just the whole-file fallbacks exceed 2,048 characters.

Bodies bring the total to 1,013,340 chunks, **+34.5% over issue 01's corpus**, at 228M tokens. An earlier estimate put the body-inclusive corpus at 302.6M tokens; that was a crude upper bound that double-counted nested definitions, and excluding them brings it down by a quarter.

For issue 03 this sets the index: 1,013,340 × 384 dimensions × 4 bytes = **1.56 GB** float32, and at the 75.7 chunks/s measured in issue 07 a full build is **~3.7 hours** rather than 2.8.

### Decisions

**Nested definitions are excluded from an enclosing definition's body.** A class body contains its methods, and each method is already a chunk. Left whole, a class would index every method's text a second time — inflating the corpus and making the class chunk match anything any of its methods matches, which is exactly what chunking exists to prevent. Pinned by `test_a_class_does_not_carry_its_methods_text`.

**Windows carry no signature or docstring.** Both are already inside the split text; repeating them on each window would index them once per window and bias long definitions.

**No overlap between windows.** Aggregation takes a file's best chunk, so a query matching across a boundary still scores in both windows and the file's rank is unaffected. Overlap would inflate the corpus to buy back what the aggregation rule already covers.

**A single line longer than the budget is hard-split.** Minified and generated files exist, and one unbounded chunk is the document shape windowing is here to prevent.

**Module-level code is still unindexed** when a file also defines functions. Bodies do not fix it, and it stays a stated cost of chunking rather than a silent one — pinned by a test.

### The provenance guard fired twice

**First:** a script written after the commit but before the run made the tree dirty, so the entry carried `-dirty` and the run was discarded and redone. Exactly what M1's issue 07 built the check for.

**Second, and more interesting:** running two evaluations back-to-back cannot produce two clean entries, because **the first run's own `RESULTS.md` write dirties the tree for the second**. The check tests the working tree, and cannot distinguish "source changed" from "output file changed" — but a modified `RESULTS.md` genuinely cannot change a number, so this is a false positive.

Not fixed, and not filed. The workaround is one `git commit` between runs, the false positive is visible rather than misleading, and excluding the results log from the check would touch the provenance guarantee — a poor trade for four minutes. Recorded here so the next person to hit it knows it is understood rather than unnoticed.
