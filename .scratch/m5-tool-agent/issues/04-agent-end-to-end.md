# 04 — Rung 4 end to end, one tool, whole contract

Status: done

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

- [x] `faultloc evaluate --rung agent --split dev --limit 3` runs end to end and prints metrics
- [x] Warm start payload is byte-identical to rung 3's, so the delta stays attributable
- [x] The graph state checks the Instance Budget before each dispatch, never after
- [x] `submit_ranking` carries the answer, and it does not count against the tool-call cap
- [x] Every run ends in exactly one logged Stop Condition
- [x] Path Guardrail drops absent paths, retries once naming them, then assembles per the contract
- [x] An accepted Off-List Path survives into the ranking, and Tool-Reached is logged for it
- [x] `cost_usd` read from the response, never computed from a price list
- [x] A model-caused tool error returns to the agent; an infrastructure error fails the Instance
- [x] `read_file` output is hard-capped, and a test proves two runs produce byte-identical output
- [x] A cache built by a different model, provider, reasoning setting or prompt is refused
- [x] The Evaluation Budget stops a run before it exceeds the cap
- [x] Every failure path that still yields a ranking is counted
- [x] Tests make no network calls, and the model client is injectable as the encoder is at rung 2
- [x] `uv run pytest` and `uv run ruff check` clean

## Notes

**A truncated reply is the failure that looks like a null result.** M4's `MAX_TOKENS` was sized from a toy prompt at 4,000, and the real prompt truncated 37 of the first 40 replies. Each truncation degraded to the input ranking, so the run reproduced fusion's order while every metric looked healthy. A probe on 2026-08-07 reproduced it in one call: at 16 tokens the reply came back empty with `finish_reason="length"` and 16 reasoning tokens spent. **At rung 4 this fires per step, not once per Instance.** Size the output budget from the real prompt.

Four of rung 3's empty replies returned `finish=stop`, which no truncation check can see. Count an absent submission separately from a truncated one.

**Watch each test fail before trusting it.** Three near-vacuous tests shipped in this repo before being caught, and each passed with and without the fix it claimed to verify. Stash the change, watch the test go red, restore it.

`--limit` must keep refusing to write a results entry. A truncated run is scored on a different Instance set.

## Blocked by

- [03 — ADR-0009: rung 4's design, its budgets, and two cells declared in advance](03-agent-design-adr.md)

## Comments

**Closed 2026-08-11.** Nine commits, `48a805c` through `c6174fb`. 576 tests pass, `ruff check` and `ruff format` clean. Total spend about **$0.09**.

Five modules: `agent_client.py`, `agent_tools.py`, `agent_graph.py`, `agent_answer.py`, `rungs/agent.py`. Both cells registered — `agent` and `agent-no-tools` — because ADR-0009 declared both before either had a number.

### What the smoke run measured

`--limit 3` at `c6174fb`: 3 of 3 answered, no degrades, 24 steps in total.

| | Estimated in ADR-0009 | Measured |
|---|---|---|
| cost per Instance | ~$0.030 | **$0.0122** |
| full cell | ~$7.4 | **~$3.0** |
| wall clock, full cell | ~6h | **~4h** |
| max output tokens | unknown | 2,487 |
| truncation | the risk to watch | **0 of 24 steps** |

**`MAX_TOKENS` stays at 16,000, and now on measurement rather than inheritance.** Observed maximum output is 2,487 tokens, so the headroom is 6.4x. It is a cap and not a reservation, so a generous value costs nothing.

**Cost is about four times below the list input price**, despite input tokens running *higher* than estimated: median 13,123 against ~7,700 assumed. Prompt caching on the growing transcript is the likely reason. **Inferred, not verified** — `AgentReply` does not capture `input_token_details.cache_read`. Confirm before anyone cites it.

### The finding that matters most

**All three Instances reached the tool-call cap of 8.** That is ADR-0009's stated revisit condition firing on the first run. At n=3 read it as direction and not magnitude, but if it holds at scale then the published number belongs to the cap rather than to the agent, and issue 06 has to say so.

### Three real bugs, none caught by any test

**An invented tool name reported as nothing.** The agent asked for `search_content` with `directory` and `fileTypes` arguments. It cost a step, and the run printed `degraded 0/0/0`. `AgentLoop` had counted it all along; the rung never absorbed the counter and the note never printed it.

**Three separate dangling-tool-call paths**, every one rejected by the provider with *"insufficient tool messages following tool_calls message"*. A batch clipped at the cap dropped the calls it refused. The guardrail retry re-sent a transcript whose rejected submission had no answer. And the nudge refused a call without answering it — which is the one that actually killed both three-Instance runs, because that node is reached exactly when `act` will not run.

### Method lessons worth more than the code

**Read the error body before theorising.** Two fixes were aimed at inferred causes. One diagnostic run printed the provider's own sentence and named the real one immediately.

**An invariant asserted over hand-picked cases is not an invariant.** The dangling-call test covered a clipped batch and a guardrail retry, and the bug lived in neither. It now runs over all seven paths the loop has.

**The break harness found four things inspection did not.** Dead code in `_act` that could never run. A test that passed for the wrong reason. A test that could not fail, because one Instance cannot separate cumulative spend from per-Instance cost. And two flaws in the tests themselves: `dangling()` exempted every submission instead of only the terminal one, and the `call` helper derived ids from the tool name, so two submissions shared one id and collapsed the check.

**Three shell mistakes made a verification silently print nothing or hang.** A backtick, an unrecognised pytest flag, and reading `tail`'s exit code instead of the harness's. The harness is a file now, it asserts each patch applied, and its exit code is read directly. 35 breaks, none uncaught.

### Carried into issue 05

The tool contract is proven on `read_file` and the four remaining tools inherit it: errors split by cause, output capped on lines and characters, deterministic serialization, and `ToolResult.paths` feeding Tool-Reached. `search_code` should also read issue 01's finding that error strings reach nothing.
