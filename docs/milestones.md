# Milestones

One line each. Slice only the current milestone into issues — see `.scratch/`.

This is deliberate. The predecessor project planned seven milestones in detail on day one. It died at three commits. Add detail only when a milestone becomes current.

| # | Milestone | Done when |
|---|---|---|
| M1 | BM25 baseline, end to end | A real Top-1 number on the Verified Set, printed by a CLI command |
| M2 | Instance Filter hardened + filter rate published | Drop reasons counted and reported. Unit tests cover the filter |
| M3 | Embedding retrieval over AST Chunks (rung 2) | Rung-2 delta over rung 1 reported at cost and latency, **with the BM25-over-chunks ablation that separates the two variables** |
| **M4** | **LLM rerank (rung 3)** | Rung-3 delta reported. Cross-model comparison table published |
| M5 | Tool-using agent (rung 4) | Five read-only tools, stop conditions, path guardrail, budget caps |
| M6 | Fresh Set mining | 150–300 post-cutoff instances, frozen, contamination gap measured |
| M7 | Calibrator + coverage curve | ECE, reliability diagram, accuracy-vs-coverage published |
| M8 | FastAPI service + replay gallery | `POST /localize` plus browsable stored runs |
| M9 | Deploy + CI gate | Container live on a public URL. GH Actions posts Top-1 delta per PR |

Dependencies to note: M6 can run in parallel with M3–M5 (independent data work). M7 requires M5. M9 requires M8.

**M1 and M2 closed 2026-08-03.** M1's harness work satisfied M2's done-when, so M2 never needed a milestone of its own. Unit tests cover the filter (`tests/test_filters.py`). `faultloc evaluate` counts the drop reasons per reason and prints them. [ADR-0001](adr/0001-ground-truth-file-set.md) and every `RESULTS.md` entry publish the measured Filter Rate.

One piece of filter work stays undone: running the filter over *raw* PR file lists, where test-stripping fires. Nobody can write that against real input until the Fresh Set miner exists, so it belongs to M6. M2 closed rather than padded.

Carried into M3 so nobody forgets it: rung 2 changes **two** things at once. Word matching becomes embeddings. Whole files become chunks. A rung-2 win is therefore unattributable on its own. BM25 over the same chunks isolates the two. It adds one row to the results table and needs no new infrastructure, so there is no excuse to skip it.

**M3 closed 2026-08-04. Rung 2 did not beat rung 1.** Embeddings scored 43.0% Top-1. The best lexical row scored 43.9%. The intervals overlap almost entirely. That cost a model, a 1.56 GB index, and 153 minutes of build time. ADR-0003 committed to publishing a null result as a finding. This is the first time that commitment cost anything.

The ablation earned its place immediately. It split what looked like one variable into three, and showed that **the only change that moved a number was free**. Chunking alone gained nothing and cost 7pp of Recall@5. Indexing function bodies recovered that and more. Embeddings on top added nothing measurable. A single `embed` over `bm25` delta would have credited the model with a gain that came from a change to what gets indexed.

One finding carries into M4. The aggregate is flat because embeddings **gain where lexical matching fails and lose where it works**. Gains: `sphinx` +9.1pp, `matplotlib` +11.8pp. Losses: `scikit-learn` −25pp, `astropy` −20pp. The two retrievers are complementary. Rung 3's job is therefore not to reorder rung 2's list, but to choose between two lists that are each right about different repositories.
