# Milestones

One line each. Only the current milestone gets sliced into issues — see `.scratch/`.

Deliberate: the predecessor project to this one planned seven milestones in detail on day one and died at three commits. Detail is added only when a milestone becomes current.

| # | Milestone | Done when |
|---|---|---|
| M1 | BM25 baseline, end to end | A real Top-1 number on the Verified Set, printed by a CLI command |
| M2 | Instance Filter hardened + filter rate published | Drop reasons counted and reported; filter is unit-tested |
| M3 | Embedding retrieval over AST Chunks (rung 2) | Rung-2 delta over rung 1 reported at cost and latency, **with the BM25-over-chunks ablation that separates the two variables** |
| **M4** | **LLM rerank (rung 3)** | Rung-3 delta reported; cross-model comparison table |
| M5 | Tool-using agent (rung 4) | Five read-only tools, stop conditions, path guardrail, budget caps |
| M6 | Fresh Set mining | 150–300 post-cutoff instances, frozen, contamination gap measured |
| M7 | Calibrator + coverage curve | ECE, reliability diagram, accuracy-vs-coverage published |
| M8 | FastAPI service + replay gallery | `POST /localize` plus browsable stored runs |
| M9 | Deploy + CI gate | Container live on a public URL; GH Actions posts Top-1 delta per PR |

Dependencies to note: M6 can run in parallel with M3–M5 (independent data work). M7 requires M5. M9 requires M8.

**M1 and M2 closed 2026-08-03.** M2's done-when was satisfied by M1's harness work rather than by a milestone of its own: the filter is unit-tested (`tests/test_filters.py`), its drop reasons are counted per reason and printed by `faultloc evaluate`, and the measured Filter Rate is published in both [ADR-0001](adr/0001-ground-truth-file-set.md) and every `RESULTS.md` entry. The one piece of filter work still genuinely undone — running the filter over *raw* PR file lists, where test-stripping actually fires — cannot be written against real input until the Fresh Set miner exists, so it belongs to M6. M2 was closed rather than padded.

Carried into M3 so it is not forgotten: rung 2 changes **two** things at once — word matching → embeddings, and whole files → chunks. A rung-2 win is therefore unattributable on its own. Running BM25 over the same chunks isolates the two. It is one extra row in the results table and needs no new infrastructure, so there is no excuse for skipping it.

**M3 closed 2026-08-04. Rung 2 did not beat rung 1.** Embeddings scored 43.0% Top-1 against the best lexical row's 43.9%, with intervals overlapping almost entirely — after a model, a 1.56 GB index, and 153 minutes of build time. ADR-0003 committed to publishing a null result as a finding, and this is the first time that commitment cost anything.

The ablation earned its place immediately: it split what looked like one variable into three, and showed that **the only change that moved a number was free**. Chunking alone gained nothing and cost 7pp of Recall@5; indexing function bodies recovered it and more; embeddings on top added nothing measurable. Reporting `embed` over `bm25` as a single delta would have credited the model with a gain that came from changing what gets indexed.

The finding worth carrying into M4: the aggregate is flat because embeddings **gain where lexical matching fails and lose where it works** — `sphinx` +9.1pp, `matplotlib` +11.8pp against `scikit-learn` −25pp, `astropy` −20pp. The two retrievers are complementary. So rung 3's job is not to reorder rung 2's list but to choose between two lists that are each right about different repositories.
