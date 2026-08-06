# ADR-0003: Build a measured ladder, not the top rung

**Status:** Accepted · 2026-07-31

## Context

The goal is a tool-using agent that localizes faults. The direct path is to build that agent. The alternative is to build a series of stronger systems and measure each one: lexical retrieval, dense retrieval, LLM rerank, then the agent.

## Decision

Four rungs, each evaluated independently on the same Instances, each reported with its accuracy, cost, and latency:

1. **BM25** — lexical, no LLM
2. **Embedding retrieval** — dense, over AST Chunks
3. **LLM rerank** — model reorders rung-2 candidates
4. **Agent** — tool-using loop

A rung's reported value is its **delta over the rung below**, priced.

*Amended 2026-08-05. Two rungs joined the ladder, numbered 2.5 (Hybrid — rank fusion of rungs 1 and 2) and 2.6 (Cross-encoder rerank). Decimals rather than renumbering, so every existing reference to "rung 3" and "rung 4" stays valid. This includes the M4 and M5 milestone definitions. See `CONTEXT.md`.*

*The delta rule above forced both insertions. Rung 2.5 arrived by accident and outscored both rungs it merges. A rung-3 delta over rung 2 would therefore have credited a paid system with a free gain. Rung 2.6 joined for the same reason, before anyone built it. A model that reads issue and candidate together is a different mechanism from one that reasons in natural language. Stack the two without measuring the middle, and rung 3's delta becomes unattributable.*

## Rationale

**The comparison is the deliverable.** "Agent reaches 0.51" is unanchored. "Agent 0.51 vs rerank 0.44 vs embeddings 0.38 vs BM25 0.29, at six times the cost and forty times the latency" is an engineering result. It also shows that the author knows when an agent is *not* worth deployment.

**It produces working output immediately.** Rung 1 needs no model and lands a real number on a real benchmark in roughly a day. Every rung afterwards reuses the same dataset loader, filter, and scorer, so the marginal cost per rung is low. Contrast the alternative, where nothing works until everything works.

**It survives a null result.** If the agent fails to beat retrieval, that is a publishable finding and the project still stands. Build only the agent, and a null result leaves nothing to show.

## Consequences

- The evaluation harness holds the loader, Instance Filter, scorer, and results log. Rung 1 builds it once. It is the project's most load-bearing code, so it gets tests first.
- The JD-relevant "agentic" rung arrives later in wall-clock terms. Accepted.
- Every rung must stay runnable as the code evolves, or the comparison table decays. CI evaluates every rung on a frozen dev slice to prevent this.

## Alternatives rejected

- **Jump straight to the agent** — fastest to the interesting part, but it produces an unanchored number and no fallback if the result is null
- **Multi-agent orchestrator** — the predecessor project's design. Most complex, least evidence, and the scope that killed it
- **Deterministic pipeline only** — cheap and predictable, but it drops the agentic tool use that most target roles ask for
