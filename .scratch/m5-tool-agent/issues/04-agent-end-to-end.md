# 04 — Rung 4 end to end, one tool, whole contract

Status: ready-for-agent

## Parent

[M5 PRD](../PRD.md)

## What to build

The agent, running end to end on a handful of Instances, with exactly **one** tool.

`faultloc evaluate --rung agent --split dev --limit 3` starts warm from the union Candidate Set, loops, calls `read_file`, submits a ranking, and returns a `Prediction` carrying real `cost_usd` and `latency_s`. It satisfies the `Rung` protocol, and the harness never learns which rung it holds.

One tool, and the whole contract. Four more tools arrive in issue 05 and inherit everything below.

**The graph.** [ADR-0005](../../../docs/adr/0005-langgraph.md) chose LangGraph, and its amendment confirmed the choice by measurement. Its Consequences section is explicit about what the graph state owns: *"The graph state enforces the budget and tool-call caps, and checks them before each dispatch. The framework never owns them."* A cap checked after a dispatch is a cap that already spent the money.

**The client.** ADR-0005's amendment settled two carve-outs. This project keeps its own `ResponseCache`, because a cache that crosses two cells in silence is worse than none. And retries must reach three failure sites, not one: the HTTP status, a 504 inside a 200 body, and a transport-level disconnect.

**Stop Conditions.** Every run ends in exactly one of the five, always logged. `budget_exceeded` fires on the tool-call cap at rung 4.

**The Path Guardrail.** Drop every path absent at `base_commit`. Ask the agent once more, and name the rejected paths. Then assemble: the agent's order first, unmentioned candidates behind in Candidate Set order, duplicates removed. A total failure cannot happen, so count the event and stamp `answered`.

**The tool contract, proven on `read_file`.** A model-caused error returns to the agent as a tool result and costs one call. An infrastructure error raises and fails the Instance loudly. Output is hard-capped, and truncation is deterministic. A test asserts byte-identical tool output across two runs.

**Counters, not silence.** Every path that still yields *a ranking* while having failed must be counted: unparseable or absent submissions, guardrail rejections, accepted Off-List Paths, cap-reached, and cache hits. M4 found three real bugs through these counters rather than through tests, and each one produced a healthy-looking run.

Start with `--limit 3`. That is roughly $0.09.

## Acceptance criteria

- [ ] `faultloc evaluate --rung agent --split dev --limit 3` runs end to end and prints metrics
- [ ] Warm start payload is byte-identical to rung 3's, so the delta stays attributable
- [ ] The graph state checks the Instance Budget before each dispatch, never after
- [ ] `submit_ranking` carries the answer, and it does not count against the tool-call cap
- [ ] Every run ends in exactly one logged Stop Condition
- [ ] Path Guardrail drops absent paths, retries once naming them, then assembles per the contract
- [ ] An accepted Off-List Path survives into the ranking, and Tool-Reached is logged for it
- [ ] `cost_usd` read from the response, never computed from a price list
- [ ] A model-caused tool error returns to the agent; an infrastructure error fails the Instance
- [ ] `read_file` output is hard-capped, and a test proves two runs produce byte-identical output
- [ ] A cache built by a different model, provider, reasoning setting or prompt is refused
- [ ] The Evaluation Budget stops a run before it exceeds the cap
- [ ] Every failure path that still yields a ranking is counted
- [ ] Tests make no network calls, and the model client is injectable as the encoder is at rung 2
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

**A truncated reply is the failure that looks like a null result.** M4's `MAX_TOKENS` was sized from a toy prompt at 4,000, and the real prompt truncated 37 of the first 40 replies. Each truncation degraded to the input ranking, so the run reproduced fusion's order while every metric looked healthy. A probe on 2026-08-07 reproduced it in one call: at 16 tokens the reply came back empty with `finish_reason="length"` and 16 reasoning tokens spent. **At rung 4 this fires per step, not once per Instance.** Size the output budget from the real prompt.

Four of rung 3's empty replies returned `finish=stop`, which no truncation check can see. Count an absent submission separately from a truncated one.

**Watch each test fail before trusting it.** Three near-vacuous tests shipped in this repo before being caught, and each passed with and without the fix it claimed to verify. Stash the change, watch the test go red, restore it.

`--limit` must keep refusing to write a results entry. A truncated run is scored on a different Instance set.

## Blocked by

- [03 — ADR-0009: rung 4's design, its budgets, and two cells declared in advance](03-agent-design-adr.md)
