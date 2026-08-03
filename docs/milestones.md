# Milestones

One line each. Only the current milestone gets sliced into issues — see `.scratch/`.

Deliberate: the predecessor project to this one planned seven milestones in detail on day one and died at three commits. Detail is added only when a milestone becomes current.

| # | Milestone | Done when |
|---|---|---|
| **M1** | **BM25 baseline, end to end** | A real Top-1 number on the Verified Set, printed by a CLI command |
| M2 | Instance Filter hardened + filter rate published | Drop reasons counted and reported; filter is unit-tested |
| M3 | Embedding retrieval over AST Chunks (rung 2) | Rung-2 delta over rung 1 reported at cost and latency |
| M4 | LLM rerank (rung 3) | Rung-3 delta reported; cross-model comparison table |
| M5 | Tool-using agent (rung 4) | Five read-only tools, stop conditions, path guardrail, budget caps |
| M6 | Fresh Set mining | 150–300 post-cutoff instances, frozen, contamination gap measured |
| M7 | Calibrator + coverage curve | ECE, reliability diagram, accuracy-vs-coverage published |
| M8 | FastAPI service + replay gallery | `POST /localize` plus browsable stored runs |
| M9 | Deploy + CI gate | Container live on a public URL; GH Actions posts Top-1 delta per PR |

Dependencies to note: M6 can run in parallel with M3–M5 (independent data work). M7 requires M5. M9 requires M8.
