# ADR-0003: Build a measured ladder, not the top rung

**Status:** Accepted · 2026-07-31

## Context

The goal is a tool-using agent that localizes faults. The direct path is to build that agent. The alternative is to build progressively stronger systems — lexical retrieval, dense retrieval, LLM reranking, then the agent — and measure each.

## Decision

Four rungs, each evaluated independently on the same Instances, each reported with its accuracy, cost, and latency:

1. **BM25** — lexical, no LLM
2. **Embedding retrieval** — dense, over AST Chunks
3. **LLM rerank** — model reorders rung-2 candidates
4. **Agent** — tool-using loop

A rung's reported value is its **delta over the rung below**, priced.

## Rationale

**The comparison is the deliverable.** "Agent reaches 0.51" is unanchored. "Agent 0.51 vs rerank 0.44 vs embeddings 0.38 vs BM25 0.29, at six times the cost and forty times the latency" is an engineering result — and it demonstrates knowing when an agent is *not* worth deploying.

**It produces working output immediately.** Rung 1 requires no model and lands a real number on a real benchmark in roughly a day. Every rung afterwards reuses the same dataset loader, filter, and scorer, so marginal cost per rung is low. Contrast the alternative, where nothing works until everything works.

**It survives a null result.** If the agent fails to beat retrieval, that is a publishable finding and the project still stands. Building only the agent means a null result leaves nothing to show.

## Consequences

- The evaluation harness — loader, Instance Filter, scorer, results log — is built once, at rung 1, and is the project's most load-bearing code. It gets tests first.
- Reaching the JD-relevant "agentic" rung takes longer in wall-clock terms. Accepted.
- Every rung must be kept runnable as the code evolves, or the comparison table decays. Rungs are evaluated in CI on a frozen dev slice to prevent this.

## Alternatives rejected

- **Jump straight to the agent** — fastest to the interesting part, but produces an unanchored number and no fallback if the result is null
- **Multi-agent orchestrator** — the predecessor project's design; most complex, least evidence, and the scope that killed it
- **Deterministic pipeline only** — cheap and predictable, but drops the agentic tool use that most target roles explicitly ask for
