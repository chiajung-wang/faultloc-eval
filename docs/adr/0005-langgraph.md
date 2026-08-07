# ADR-0005: LangGraph for the agent loop

**Status:** Accepted · 2026-07-31

## Context

Rung 4 is a single agent with five read-only tools. It runs a bounded loop with explicit terminal states. The loop itself is small — dispatch, accumulate messages, check budget, decide to stop.

Options were a hand-written loop over a provider SDK, a hand-written loop over a multi-provider shim, or a graph framework.

## Decision

Python, LangChain, LangGraph.

## Rationale

The rung-4 design is already a state machine: explicit nodes, conditional edges, and five named terminal Stop Conditions. LangGraph expresses that shape directly rather than approximating it with control flow.

Multi-provider access survives via LangChain's `init_chat_model`, so the cross-model cost/accuracy comparison remains cheap and does not require a separate shim.

Observability attaches to Langfuse through the LangChain callback interface. It gives a span per node and a trace per run. A prior project already proved this pattern.

Several target job descriptions also name LangGraph favorably.

## Consequences

**Explanatory debt, and it is real.** A framework-owned loop is a liability in an interview if the author cannot describe what it does underneath. The author must explain the node, edge, and state design without reference to the framework. That means four things: what the state object holds, where the loop checks the budget, how a conditional edge selects a Stop Condition, and what happens on a tool error.

This ADR won over a recommendation for a hand-written loop. That recommendation argued that a loop you own gives you full control over instrumentation and retry logic, and maximum explainability. The argument is not wrong. The state-machine fit and prior familiarity outweighed it. The debt above is the price.

- The graph state enforces the budget and tool-call caps, and checks them before each dispatch. The framework never owns them.
- Framework version churn is a maintenance risk, so the dependency stays pinned.

## Alternatives rejected

- **Hand-written loop over the provider SDK** — most explainable, fewest dependencies, but single-provider without extra work
- **LiteLLM plus a hand-written loop** — multi-provider access and loop ownership together. Rejected in favor of the state-machine fit
- **Agent frameworks with implicit control flow** — least explainable, and they couple the evaluation harness to someone else's abstractions
