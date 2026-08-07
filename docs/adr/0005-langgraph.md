# ADR-0005: LangGraph for the agent loop

**Status:** Accepted · 2026-07-31 · *amended 2026-08-07: this ADR sat unexecuted through M4, and a probe reopened it and confirmed it. The framework does not replace this project's response cache or its retry logic. See the [amendment](#amended-2026-08-07--a-probe-confirmed-this-decision-and-it-named-two-things-the-framework-does-not-do).*

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

## Amended 2026-08-07 — a probe confirmed this decision, and it named two things the framework does not do

**This ADR sat unexecuted through M4.** `pyproject.toml` holds no `langchain` and no
`langgraph`. Rung 3 shipped on `src/faultloc/llm.py`, which is 306 lines of hand-rolled
`urllib` against OpenRouter. That client went further than this ADR anticipated. It pins the
upstream provider, it reads the cost from each response, it extracts reasoning tokens, and it
retries at three separate failure sites.

M5 therefore reopened the decision. A hand-written loop on the existing client was the
alternative, and it had a specific argument: a framework that hides routing threatens the
pins that ADR-0008 says make a published number mean anything.

**Three facts settled it, and a session read all three off documentation and got all three
wrong.** A probe cost $0.00024 and overturned them, on `langchain-openrouter` 0.2.7 and
`langchain-core` 1.5.3.

| Read from documentation | Measured |
|---|---|
| Provider pinning is not first-class | `openrouter_provider={"only": [...], "allow_fallbacks": False}` |
| Per-request cost is not surfaced | `response_metadata["cost"]`, plus `cost_details` that splits the upstream prompt cost from the completion cost |
| Tool calling on the pinned route is unverified | `bind_tools` returned `finish_reason="tool_calls"` with correct arguments |

Nothing asks for the cost. The client already requests it. So ADR-0008's property survives
under the framework: the run **reads** a cost and it never computes one from a price list.

**Decision: rung 4 runs on LangGraph, as this ADR decided.** The record of the reopening
stays, because the objection was reasonable and only a measurement answered it.

### Two things the framework does not do

**This project keeps its own `ResponseCache`.** It keys on the model, the provider, the
reasoning setting, `max_tokens` and the prompt. It refuses a cache that a different model
built, which is issue 03's acceptance criterion. LangChain's `cache` field takes a
`BaseCache`, and its keying is not the same. A cache that crosses two cells in silence is
worse than no cache. Rung 4 also needs the cache for a second reason: a step's prompt holds
the whole trajectory, so a killed run resumes for nothing.

**`max_retries` watches one failure site.** `llm.py` watches three. The HTTP status arrives
first. A 504 inside a 200 body arrives second, and commit `f437e38` was necessary for the
third, which is a transport-level disconnect. Issue 03 lists that third one as still open.
Rung 4 must reach the same three sites, and a single retry count does not.

### Consequences

**Two clients live in this repository, and that is deliberate.** Rung 4 uses LangGraph.
Rung 3 stays on `llm.py`. A port would put four published numbers at risk to tidy up a
seam, and the seam costs nothing.

**The explanatory debt in the Consequences section above is now due.** M5 is the milestone
that must answer the four questions named there: what the state object holds, where the
loop checks the Budget, how a conditional edge selects a Stop Condition, and what happens
on a tool error. M5's design fixes the last one already. A model-caused error returns to the
agent as a tool result. An infrastructure error raises and fails the Instance loudly.

**Read nothing off documentation again.** This amendment exists because three documented
facts were wrong at once. `CLAUDE.md` opens with that rule. A probe costs a fraction of a
cent, and it is the only thing that settled any of this.
