# ADR-0009: Rung 4 starts from rung 3's payload and goes looking for what retrieval missed

**Status:** Accepted · 2026-08-10

## Context

[ADR-0003](0003-baseline-ladder.md) fixed rung 4 as *"a tool-using loop"* and said no more. M4 and two free measurements decide what the loop is for.

**Rung 3 established the first real gap in this ladder.** An LLM that reorders twenty candidates scores 74.2% Top-1 against rank fusion's 45.5%, and the intervals do not touch. The best of four cells reaches 79.1%.

**A reranker cannot pass the Candidate Set.** hit@20 is 88.9% on the dev split, so 27 Instances of 244 hold no Ground-Truth File in the list at all. `sphinx` shows the shape of it: all four rung-3 cells score exactly 63.6% there, which is exactly its own hit@20. Every model picks correctly on every sphinx Instance where the answer was retrievable.

So rung 4 is not "rank better". It is *go and find what retrieval missed*. Two free measurements then asked whether that is possible, and how the result could be read.

**Issue 01 measured the target.** `git grep` reaches a Ground-Truth File for **63.0%** of the 27 missed Instances, and **59.3%** within a 30-hit cap. So a tool-using Rung raises the ceiling from 88.9% to about **95.5%**.

| Pattern kind | reachable | within a 30-hit cap |
|---|---|---|
| dotted names | 44.4% | 37.0% |
| identifiers | 29.6% | 25.9% |
| traceback paths | 7.4% | 7.4% |
| **error strings** | **0.0%** | **0.0%** |

**Issue 02 measured the headroom, and corrected it upward.** The first paired comparison put `rerank` against `hybrid` at +28.7pp, p=1.6e-16. Its table showed 57 Instances that both rungs got wrong. Issue 01's 27 unreachable Instances sit inside that 57, which leaves about **30 Instances where a Ground-Truth File was inside the top 20 and both systems still failed to rank it first**.

| Headroom over the 79.1% baseline | Available |
|---|---|
| in-list ranking, 79.1% to the 88.9% ceiling | +9.8pp |
| out-of-list and grep-reachable | +6.6pp |
| total | **+16.4pp** |

Issue 02 also found that free rank fusion beats the paid reranker on **6 Instances**. Rung 3 does not strictly dominate the rung below it.

## Decision

### The agent starts warm

It receives the issue text and the top-20 union Candidate Set with Evidence Chunks. That payload is byte-identical to rung 3's prompt. It also receives the tools and a bounded loop.

Rung 4 replaces rung 3's single call. It does not chain onto rung 3's output.

### The tool roster stays at five, and `search_code` is `git grep`

[ADR-0002](0002-no-code-execution.md)'s five stand: `search_code`, `semantic_search`, `read_file(path, start, end)`, `file_outline`, `find_definition`.

`search_code` is a **literal** search over source files at `base_commit`, through the bare clones `RepoStore` already holds. It is not BM25 over the same AST Chunks. It returns at most 30 hits **and it reports the true match count**, so a truncated result drives a refinement rather than a biased slice.

*Corrected 2026-08-11. This paragraph first said "literal and regex". Literal is what issue 01 measured, and literal is what shipped. A bug report quotes text full of dots, brackets and asterisks, and reading that as a pattern finds matches the reporter never wrote. Offering a regex mode as well would add a failure the agent can only discover by spending a step on it.*

Every tool caps its output, and truncation is deterministic.

### `submit_ranking` carries the answer

A structured tool call, not free text. It is a terminal action rather than a sixth read-only tool, and it does not count against the tool-call cap.

Assembly runs in four steps. The Path Guardrail drops paths absent at `base_commit`. The agent's own order comes first, with candidates and accepted Off-List Paths interleaved as it ranked them. Every candidate the agent never mentioned appends behind, in Candidate Set order. Duplicates go.

### The Path Guardrail checks existence, and it never checks membership

An **Off-List Path** that exists is accepted, and the run counts it. That count is the measure of whether rung 4 earned its rung, because reaching past the list is the only route above 88.9%.

The guardrail rejects a path that is absent at `base_commit`, then asks the agent once more and names the rejected paths. If nothing valid survives, the prediction stamps `answered` on the fallback assembly and the run counts the event. That count is the catch rate.

**Tool-Reached** is logged for every predicted path: whether a tool call surfaced it during the run. It is a diagnostic and it never rejects a path.

### Three Budget scopes

| Scope | Caps |
|---|---|
| Instance Budget | 8 tool calls, 600s |
| Evaluation Budget | $12 |
| Milestone Budget | $20 |

The graph state enforces the Instance Budget and checks it before each dispatch. The Instance Budget holds no dollar cap.

The cap counts calls, not turns. Eight means eight tool results.

### The pin

`deepseek/deepseek-v4-pro`, the first-party `deepseek` route, reasoning at its default, which is on. Hub revision `b5968e9190ef`. The route serves **fp8**, measured 2026-08-07.

### Two cells, declared before either runs

| Cell | Tool-call cap | Estimated cost | Estimated wall clock |
|---|---|---|---|
| `agent` — the ladder row | 8 | ~$7.4 | ~6h |
| `agent-no-tools` — the Ablation | 0 | ~$0.60 | ~25m |

### Three comparisons, each with a different job

| Comparison | Against | What it licenses |
|---|---|---|
| attributable delta | `rerank-deepseek-on`, 79.1% | the causal claim. Same model, route and reasoning, so only the loop and the tools move. |
| deployment delta | `rerank-deepseek-off`, 75.0% at $0.31 and 22m | whether an agent is worth running at all |
| tools delta | `agent-no-tools` | separates tools from the scaffolding and the output format |

Every rung-against-rung delta uses the paired McNemar test from issue 02. The table keeps its Wilson intervals. Each report states which test licenses which claim.

### Tool errors split by cause

A model-caused error returns to the agent as a tool result and costs one call. An invalid regex, a path absent at `base_commit`, and a bad line range are all information. An infrastructure error raises and fails the Instance loudly.

Both classes are counted.

### The loop runs on LangGraph

[ADR-0005](0005-langgraph.md)'s amendment settled this by probe. This project keeps its own `ResponseCache`, and retries must reach three failure sites rather than one.

## Rationale

**Why warm rather than cold.** A cold start would mix a lost 88.9% of retrieval with whatever search gained. ADR-0003's delta rule could not read the result, and issue 02's paired test cannot separate two variables either.

**Why `git grep` rather than BM25.** BM25 over AST Chunks is the signal that already built half the Candidate Set, so it adds nothing the warm start did not run. Issue 01 then measured which pattern kinds reach an answer, and the reach is real: 59.3% within a cap.

**Why error strings must not be pasted into `search_code`.** Issue 01 found **zero of 27**. A report pastes a rendered message and the code holds the template, so the string appears in no source file. The identifiers inside a message are what carry the signal.

**Why 30 hits.** Issue 01 measured the cost of that cap at one Instance of 27. The constant is measured rather than chosen.

**Why reasoning stays on, and the argument is narrower than it looks.** M4 measured reasoning's effect on *single-turn reranking* at +4.1pp on this model, which sits inside the ±6pp interval. That null does not transfer to multi-turn planning, and this ADR does not claim that reasoning helps tool use in general, because nobody here has measured that.

What this repository did measure is hallucination. `rerank-deepseek-off` produced **43** Off-List Paths and `rerank-deepseek-on` produced **14**. M4 recorded that the two configurations which reason least hallucinate most, by roughly seven to one. Rung 4's product is naming files that were never candidates, and its done-when is a Path Guardrail. A three-times hallucination rate is a direct cost to both.

Tool calling on this exact route is measured rather than assumed. The [ADR-0005](0005-langgraph.md) probe returned `finish_reason="tool_calls"` with correctly parsed arguments.

**Why a structured `submit_ranking`.** Rung 3 lost 17 of 244 replies to unparseable content, and four of those returned empty with `finish=stop`, which no truncation check can see. The published 74.2% is depressed by a parsing failure rather than by the model.

**Why the guardrail cannot fail an Instance.** The assembly keeps the Candidate Set behind the agent's order, and every candidate exists at the commit, so the list is never empty. A fall back to fusion's order pulls rung 4's number **down**, because fusion scores 45.5%. It depresses, and it cannot inflate a score with a free rank-fusion result.

**Why three comparisons rather than one.** The ladder's published rung-3 row moves to `deepseek-off` on cost-effectiveness grounds, and rung 4 is pinned to `deepseek-on`. Reporting a single delta across those two would move reasoning and the loop and the tools together. The attributable delta holds reasoning fixed. The deployment delta answers the question a reader actually has, and 26x on price is the number it has to justify.

**Why the Instance Budget holds no dollar cap.** Eight tool calls, each with a capped result, cannot reach $0.05. A tunable cap under a structural bound could only fire on a bug, and it would hide that bug.

## Consequences

**A declared confound.** Rung 3 parsed text and rung 4 does not, so part of rung 4's delta is a better output format. The zero-tool cell prices it. Stated here rather than discovered later.

**The baseline must be bought.** The paired test needs per-instance Predictions and M4 published only aggregates. The response cache holds no replies for `deepseek-on`, so that cell runs again at about **$0.49 and 178m**. Total M5 spend is about **$8.5** against a $12 Evaluation Budget and a $20 Milestone Budget.

**A prompt-changing fix costs a full re-run.** It invalidates the response cache, and completed Instances replay free only while their prompts stay byte-identical. The Milestone Budget holds room for exactly one.

**Determinism becomes a contract on every tool.** Sorted output, no timestamps, no absolute paths that leak `data/repos/`, deterministic truncation, and a stable serialization format. A resumed run replays from cache only while each step's prompt is byte-identical, so a tool that orders differently on two runs makes a six-hour run pay twice.

**[ADR-0005](0005-langgraph.md)'s explanatory debt is due at this milestone.** Its Consequences name four questions. This ADR answers the tool-error one.

**Rung 4 reports no Confidence.** [ADR-0004](0004-calibrated-confidence.md) gives that job to the Calibrator at M7.

**One finding is carried out of M5's scope.** Free rank fusion beats the paid reranker on 6 Instances. That belongs to M7's escalation design, and it is recorded here so it is not lost.

## Revisit condition

**If most Instances reach the cap of 8 tool calls**, the cap produced the number rather than the agent. The entry reports the distribution of tool-call counts, and that is the condition to raise it.

**If the per-tool contribution log shows `semantic_search` never surfaced a path that reached an answer**, it does not earn its slot, and ADR-0002's roster takes a recorded correction. It survives now on one named mechanism: `sphinx` has a hit@20 of 63.6%, its reports describe rendered output, and issue 01 found it reachable in only 50% of its 8 missed Instances.

**If rung 4 fails to beat `deepseek-off` at $0.31 and 22m**, then an agent is not worth deploying for this task at this price, and that is the finding. ADR-0003 publishes a null result rather than bury it.

**If the truncation rate on tool output is high**, the 30-hit cap is binding on the agent rather than on the measurement, and it needs re-measuring against a larger cap.

## Alternatives rejected

- **Cold start, tools only** — measures agentic search purely, and its delta mixes lost retrieval with gained search, so no test can attribute it
- **Chaining onto rung 3's output** — cheapest prompt, and rung 4's number would then depend on a nondeterministic rung 3 run underneath it
- **BM25 as `search_code`** — reuses rung 1 and adds no signal the warm start did not already run
- **A four-tool roster without `semantic_search`** — sharper selection at a cap of 8, and it drops the only tool with a named mechanism for `sphinx`. Kept as a contribution log rather than an assertion
- **Free-text ranking, as rung 3 parsed it** — holds the output format fixed between the two rungs, and preserves a known 7% failure rate that is a serving quirk rather than a result
- **A sixth Stop Condition for total guardrail failure** — requires discarding a Candidate Set that holds the answer 88.9% of the time, so it scores 0 on a scorable Instance
- **A per-instance dollar cap** — redundant under a structural bound of $0.05
- **Reasoning disabled, as the ladder's rung-3 row now uses** — 8x faster and about 20% cheaper, and it triples the Off-List Path rate on the rung whose product is Off-List Paths
- **Concurrency** — turns a six-hour run into about one hour, and it makes the spend counter racy and the wall-clock column mean something different from every entry before it. The response cache makes patience cheap, because an interrupted run resumes
- **A deferred zero-tool ablation, bought only if the main result is ambiguous** — saves $0.60 and costs the ability to say the ablation was planned rather than chosen after seeing the number
