# ADR-0005: LangGraph for the agent loop

**Status:** Accepted · 2026-07-31

## Context

Rung 4 is a single agent with five read-only tools, running a bounded loop with explicit terminal states. The loop itself is small — dispatch, accumulate messages, check budget, decide to stop.

Options were a hand-written loop over a provider SDK, a hand-written loop over a multi-provider shim, or a graph framework.

## Decision

Python, LangChain, LangGraph.

## Rationale

The rung-4 design is already a state machine: explicit nodes, conditional edges, and five named terminal Stop Conditions. LangGraph expresses that shape directly rather than approximating it with control flow.

Multi-provider access survives via LangChain's `init_chat_model`, so the cross-model cost/accuracy comparison remains cheap and does not require a separate shim.

Observability attaches through the LangChain callback interface to Langfuse — a span per node, a trace per run — matching a pattern already proven in a prior project.

LangGraph is also named favourably in several of the target job descriptions.

## Consequences

**Explanatory debt, and it is real.** A framework-owned loop is a liability in an interview if the author cannot describe what it does underneath. The node/edge/state design must be explainable without reference to the framework: what the state object holds, where budget is checked, how a conditional edge selects a Stop Condition, what happens on tool error.

This ADR was accepted over a recommendation for a hand-written loop. The recommendation's argument was that owning the loop makes instrumentation and retry logic trivially controllable and maximally explainable. That argument is not wrong; it was outweighed by the state-machine fit and prior familiarity. The debt above is the price.

- Budget and tool-call caps are enforced in the graph state, checked before each dispatch — not delegated to the framework.
- Framework version churn is a maintenance risk; the dependency is pinned.

## Alternatives rejected

- **Hand-written loop over the provider SDK** — most explainable, fewest dependencies, but single-provider without extra work
- **LiteLLM plus a hand-written loop** — multi-provider and loop ownership together; rejected in favour of the state-machine fit
- **Agent frameworks with implicit control flow** — least explainable, and they couple the evaluation harness to someone else's abstractions
