# M4 — LLM rerank (rung 3)

## Goal

A rung-3 number on the dev split, reported as a **delta over rung 2** at its cost and latency, plus a cross-model comparison table.

## What M3 changed about this milestone

[ADR-0003](../../docs/adr/0003-baseline-ladder.md) describes rung 3 as *"model reorders rung-2 candidates"*. M3's result makes that framing wrong.

Rung 2 did not beat rung 1 — 43.0% Top-1 against the best lexical row's 43.9%, intervals overlapping. But the aggregate is flat because the two retrievers **fail on different repositories**: embeddings gained on `sphinx` (+9.1pp), `matplotlib` (+11.8pp) and `requests` (+25pp), and lost on `scikit-learn` (−25pp), `astropy` (−20pp) and `pytest` (−10pp).

So reranking rung 2's list alone would inherit rung 2's misses on exactly the repositories where lexical retrieval already had the answer. **Rung 3 reranks the union of both retrievers**, and the question it answers is whether a model can choose between two retrievers that are each right about different things.

## The three things this milestone must resolve

**The ceiling.** A reranker can only reorder what retrieval handed it. The union's Recall@K is rung 3's hard upper bound, and it is free to measure. It also sets K, which sets the token count, which sets the bill.

**Determinism.** Every rung so far asserts `test_is_deterministic` — same instance, same ranking, every run. An LLM cannot guarantee that. Either responses are cached so a rerun is reproducible, or nondeterminism is accepted and variance is reported. This changes what a `RESULTS.md` entry means, so it is an ADR rather than a code decision.

**Real money.** This is the first rung with a non-zero cost. `Prediction.cost_usd` has existed since M1 for exactly this moment. Per the PRD the per-run budget is $0.50, 25 tool calls, 120 seconds.

## Done when

- `faultloc evaluate --rung rerank --split dev` runs end to end and emits a `RESULTS.md` entry with measured cost
- The rung-3 delta over rung 2 is reported at its price, including if that delta is zero
- A cross-model table compares at least two models on accuracy, cost, and latency
- The reranking design and its determinism decision are recorded in an ADR

## Out of scope

The tool-using agent (M5), the Fresh Set (M6), calibration (M7). Rung 3 sees a fixed candidate list and reorders it; it does not go looking for more.
