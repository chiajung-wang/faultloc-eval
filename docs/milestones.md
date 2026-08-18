# Milestones

One line each. Slice only the current milestone into issues — see `.scratch/`.

This is deliberate. The predecessor project planned seven milestones in detail on day one. It died at three commits. Add detail only when a milestone becomes current.

| # | Milestone | Done when |
|---|---|---|
| M1 | BM25 baseline, end to end | A real Top-1 number on the Verified Set, printed by a CLI command |
| M2 | Instance Filter hardened + filter rate published | Drop reasons counted and reported. Unit tests cover the filter |
| M3 | Embedding retrieval over AST Chunks (rung 2) | Rung-2 delta over rung 1 reported at cost and latency, **with the BM25-over-chunks ablation that separates the two variables** |
| M4 | LLM rerank (rung 3) | Rung-3 delta reported. Cross-model comparison table published |
| **M5** | **Tool-using agent (rung 4)** | Rung-4 delta over rung 3 reported at cost and latency, with the zero-tool ablation that separates tools from scaffolding. Five read-only tools, stop conditions, path guardrail, budget caps |
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

**M4 closed 2026-08-07. Rung 3 is the first established result in this ladder.** An LLM reranking twenty candidates scores 74.2% Top-1 against fusion's 45.5%, and the intervals do not touch. Every earlier gap sat inside the ±6pp interval. This one does not.

The model did not produce it. Four configurations spanning an 11.8x price difference land within 6.6 points of each other, intervals overlapping almost entirely, and both reasoning ablations sit inside the interval. The pair was chosen 11.8x apart on price so that the measurement could show a difference if one existed. It did not.

**Rung 2.6 was inserted to protect rung 3's delta and instead became a null result of its own.** A cross-encoder scored 26.6%, below every free rung, so reading the issue and one candidate together is worse than rank fusion reading neither. It stays in the ladder.

M4 was the first milestone with a bill: $1.95 in published rows against $5.59 on the account. The difference bought a working client and three rejected providers, each rejected on measurement rather than reputation.

Carried into M5 so nobody forgets it: the remaining headroom is retrieval, not ranking. The candidate list holds the answer for 88.9% of instances and the best configuration reaches 79.1%. `sphinx` sits exactly on its own ceiling in all four configurations. An agent whose advantage is *searching harder* aims at the gap that is left; an agent that only reorders does not.

Also carried: rung 3 named 92 files that were never candidates, across the four configurations. That is the first sizing evidence for the Path Guardrail M5 must build, and the rate differs sharply by configuration.

**M5 closed 2026-08-18. Rung 4 is the best row in the ladder, and the tools are not what made it.**

The agent scores **88.1% Top-1 (83.5-91.6)**, above every other row. Its own Ablation, the same agent with the tool-call cap at zero, scores **84.0%**. Same model, route, reasoning, prompt, loop and answer format. The only difference is that the Ablation cannot open a file.

**The tools delta is +4.1pp at p=0.087, and it is not established.** Nineteen Instances won, nine lost, twenty-eight discordant. The delta against rung 3 is +13.9pp and decisively significant, and it is not the agent's achievement: six variables move at once, and the Ablation attributes about ten of those points to the loop and the answer format alone. ADR-0009 declared that Ablation before either cell ran, which is the only reason the two can be told apart.

**Rung 4 reached past the Candidate Set twice in 244 Instances.** That is its one structural advantage over any reranker, and the most direct explanation of the small delta. Both paths were surfaced by a tool rather than recalled from training data.

**Two tools of five carry the work.** `read_file` 811 calls and 121 Top-1 finds, `search_code` 618 and 81, `file_outline` 89 and 39, `find_definition` 10 and 1, and `semantic_search` **3 calls and 0**. ADR-0002 fixed five tools by name, and ADR-0009 named this outcome as the condition for revisiting that.

**The cap binds on 141 of 244 Instances**, median exactly 8, so 88.1% is a lower bound on what this design does with more room.

M5 cost about $11, and one planned comparison was dropped rather than bought: pinning rung 4 to bounded reasoning left M4's unbounded 79.1% cell unmatched, and re-running it cost seventeen times M4's measured figure.

Carried into M6 and M7: the Candidate Set is still the binding constraint. Issue 01 measured the reachable ceiling at 95.5% and rung 4 reached 88.1%, so the gap is retrieval that no amount of tool use recovered. M7's Calibrator also inherits a specific fact from M5 — free rank fusion beats the paid reranker on 6 Instances, so a system that can abstain has something real to work with.
