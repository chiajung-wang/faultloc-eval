# M5 — decisions settled in grilling, 2026-08-07

Session paused after Q6. The open questions live in the task list, Q7 through Q17.
This file holds only what the session settled. Nothing here is an issue yet.

## 1. The agent starts warm

The agent receives the issue text and the top-20 union Candidate Set with Evidence
Chunks. That payload is byte-identical to rung 3's prompt. The agent also receives
the tools and a loop.

One variable moves against rung 3: the loop and the tools. Rung 4 replaces rung 3's
single call. It does not chain onto rung 3's output.

Rejected: a cold start with tools only. Its delta mixes lost retrieval with gained
search, so ADR-0003's delta rule could not read it.

## 2. The Path Guardrail checks existence, and it never checks membership

An Off-List Path is a path that the Candidate Set does not hold. Rung 3 discards
one. Rung 4 keeps one that exists, because a reach past the list is the thing
rung 4 adds. The guardrail rejects only a path that is absent at `base_commit`.

The run counts accepted Off-List Paths. That count is the measure of whether rung 4
earned its rung.

The run also logs Tool-Reached: whether a tool call surfaced the path during the run
that named it. The Verified Set predates the training cutoff, so a model can name a
real path from memory. The flag is a diagnostic. It never rejects a path.

`CONTEXT.md` now carries all three terms.

## 3. `search_code` is `git grep`

Literal and regex search over source files at `base_commit`, through the bare clones
that `RepoStore` already holds. It returns at most N hits, and it reports the true
match count. A truncated result therefore drives a refinement, and it does not become
a silently biased slice.

Rejected: BM25 over the same AST Chunks. That is the signal that already built half
the Candidate Set.

## 4. Per-instance predictions are persisted, and rung deltas use a paired test

Each run writes its per-instance predictions to disk. `cli.py` builds the list today
and then drops it, so no paired test of any two rungs is possible.

Rung-vs-rung deltas use McNemar over the discordant instances. The table keeps its
Wilson intervals. Each report says which test licenses which claim.

The reason: rung 3 and rung 4 run on the same 244 Instances, and the test split stays
closed until M7, so n cannot grow. A realistic rung-4 result of 78-82% is a delta of
4-8pp against a +/-6pp interval. Unpaired intervals would report "nothing established"
for the most expensive milestone so far. Paired data has far more power.

The test is chosen before the numbers exist. That order is deliberate, and it matches
ADR-0008 declaring its ladder row in advance.

Persistence also unlocks subset re-scoring, per-repo breakdowns, and the failure
taxonomy, all without a re-run.

## 5. The run stays sequential, and it publishes one cell

No worker pool. One cell, no route hunt.

Sequential survives decision 8, which corrected the latency estimate from 24 hours to
about 6. **"One cell" does not survive decision 12.** M5 publishes two.

## 6. Rung 4 pins to `deepseek-on`

`deepseek/deepseek-v4-pro`, first-party `deepseek` route, `reasoning=None`, which is
default-on. Declared before any number exists.

The matched rung-3 baseline already exists: `rerank-deepseek-on`, 79.1% (73.6-83.7),
$0.49, 178m. Same model, same route, same reasoning setting. The delta is therefore
attributable for no extra money, and rung 4 must clear the best cell M4 ran.

Reasoning stays on because the agent plans over many turns. M4 measured its reasoning
null result on single-turn reranking only. That null does not transfer to planning,
and this project does not carry an unverified result across tasks.

Cerebras is not available. `llm.py` records it as rejected on measurement: it enforces
an 8,192-token completion cap while it advertises 40,960, and it truncated a third of
replies.

## 7. The loop runs on LangGraph, and ADR-0005 stands

A probe settled it, and it cost $0.00024. Both objections to the framework failed.

`ChatOpenRouter` surfaces OpenRouter's real per-request cost at
`response_metadata["cost"]`, with `cost_details` that splits the upstream prompt cost
from the completion cost. Nothing must ask for it. ADR-0008's property holds: the run
reads the cost and it never computes one from a price table.

`bind_tools` works on the pinned first-party `deepseek` route. The reply carried
`finish_reason="tool_calls"` and correctly parsed arguments. Provider pinning is also
first-class, through `openrouter_provider={"only": [...], "allow_fallbacks": False}`.

Two consequences that the ADR amendment must state rather than discover:

- **This project keeps its own `ResponseCache`.** It keys on model, provider,
  reasoning, `max_tokens` and prompt, and it refuses a cache that a different model
  built. That is issue 03's acceptance criterion. LangChain's `cache` field takes a
  `BaseCache`, and its keying is not the same. A cache that crosses two cells in
  silence is worse than no cache.
- **`max_retries` watches one failure site.** `llm.py` watches three: the HTTP status,
  a 504 inside a 200 body, and a transport-level disconnect. Commit `f437e38` was
  necessary for the third one, and issue 03 lists it as still open.

Three external facts read off documentation in this session were all wrong, and the
probe overturned each one. Probe, and do not read.

## 8. The tool-call cap binds, and nothing else does

The Instance Budget is **8 tool calls**. Wall clock is **600s**, and it exists to catch a
hang. The per-instance dollar cap is dropped.

The graph state enforces both, and it checks them before each dispatch. ADR-0005 fixed
that placement, and the framework never owns a cap.

An earlier estimate of 24 hours was wrong. It assumed that every step costs the 43.8s
that `rerank-deepseek-on` measured, and that figure came from a step which emits a full
20-path reordering. Latency follows output tokens. The probe's tool-selection step emitted
95 output tokens, so a tool step costs 4 to 8 seconds.

| | per Instance | 244, sequential |
|---|---|---|
| 8 tool steps | ~50s | |
| final ranking step | ~44s | |
| **total** | **~90s, ~$0.030** | **~6h, ~$7.4** |

The probe confirmed the input price against the live account. 320 tokens billed
$0.0001392, and 320 at $0.435 per 1M is $0.0001392.

The PRD's three caps do not survive. 120s against a ~90s mean fires on variance rather
than by design, and it confuses "the agent gave up" with "the route was slow". $0.50
against ~$0.030 has 16 times the headroom, so it can never fire.

**Rider.** The entry must report the distribution of tool-call counts, and how often the
cap of 8 was reached. A cap of 8 cannot answer how many steps the agent wants, which was
the one virtue of the PRD's 25. If most Instances reach 8, the cap produced the number.
That is the condition to raise it.

## 9. All five tools stay, and the roster becomes a measurement

ADR-0002's five stand. `search_code` is `git grep`. The other four do not change.

The run logs, for each tool, how many times it was called, and how often a call surfaced
a path that reached the final answer. Q2's Tool-Reached already maps a path to a tool, so
this costs almost nothing and it gives M5 a second finding.

`semantic_search` survives on one named mechanism. `sphinx` has a hit@20 of 63.6%, and
all four rung-3 cells sit exactly on it. Its reports describe rendered output, so
`git grep` should fail there: nothing can grep a term that the code does not contain. The
expected size is small, at 22 of 244 Instances and roughly 3.3pp.

## 10. The agent submits its ranking through a tool

A structured `submit_ranking(paths)` call carries the final answer. Free text does not.

Assembly runs in four steps.

1. Drop every path that is absent at `base_commit`.
2. Keep the agent's own order first, with candidates and accepted Off-List Paths
   interleaved as the agent ranked them.
3. Append every candidate that the agent never mentioned, in Candidate Set order.
4. Remove duplicates.

Top-1 and Recall@3 and Recall@5 all read positions inside 5, so list length past 5 changes
no published metric. No truncation constant is necessary.

Rung 3 lost 17 of 244 replies to unparseable content, and four of those returned empty with
`finish=stop`, which no truncation check can see. A structured call removes that whole class.

**Declared confound.** Rung 3 parsed text and rung 4 does not, so part of rung 4's delta is
a better output format. Decision 12 measures it.

`submit_ranking` is a terminal action rather than a sixth read-only tool, and it does not
count against the cap of 8.

## 11. The guardrail retries once, and it never fails the Instance

The guardrail drops absent paths. It then asks the agent one more time, and it names the
rejected paths. If no agent-named path survives, the prediction stamps `answered` on the
fallback assembly, and the run counts the event. That count is the catch rate.

No sixth Stop Condition. Decision 10's assembly keeps the Candidate Set behind the agent's
order, and every candidate exists at the commit, so the list is never empty.

A fall back to fusion's order pulls rung 4's number **down**, because fusion scores 45.5%
against rung 4's target near 79%. It depresses, exactly as rung 3's 7% did. It cannot
inflate a score with a free rank-fusion result.

`CONTEXT.md` now carries this. Its "then fails" clause is gone.

## 12. M5 buys the zero-tool ablation

The same agent, the same prompt, the same model and route, with the tool-call cap at 0. It
must call `submit_ranking` at once. One call per Instance, so roughly **$0.60** against the
main cell's ~$7.4.

This supersedes decision 5's "one cell". M5 publishes two rung-4 cells.

Three variables would otherwise move together: the scaffolding, the tools, and the output
format. How to read the cell:

| Zero-tool cell | Meaning |
|---|---|
| near 79.1% | Scaffolding and format are neutral. The whole delta is tools. |
| above 79.1% | The parsing fix bought points, and tools would take the credit. |
| below 79.1% | Tool instructions degraded a pure ranking task. |

**Two deltas get published.** The ladder delta against `rerank-deepseek-on` at 79.1%, as
ADR-0003 requires. The tools delta against the zero-tool cell, which is the attributable
one. The entry says which licenses which claim.

Declared in advance, before any rung-4 number exists.

## 13. The budget is $12 per evaluation and $20 for the milestone

$12 clears the ~$7.4 main cell with 60% headroom. ADR-0008 learned that a cap which the
expected cost sits just under aborts on ordinary variance, and this run takes six hours.
$20 leaves room for one full re-run.

**Every tool result carries a hard cap.** That is what turns the estimate into a bound.
Tool-result size is the weakest term: at 800 tokens per result the cell costs $7.4, and at
3,000 it costs about $13. The term is enforceable, because `read_file(path, start, end)`
bounds itself and decision 3 already caps grep hits. The entry reports the truncation rate.

The real risk is not the token price. **A fix that changes the prompt invalidates the
cache.** Completed Instances replay free only while their prompts stay byte-identical.

M4's setup rule carries forward with both conditions intact. Spend charges to setup only
when it produced no publishable number, **and** when what it produced now sits in the
repository as code or as a decision.

## 14. M5's done-when names the number first

Amend the M5 row in `docs/milestones.md` to:

> Rung-4 delta over rung 3 reported at cost and latency, with the zero-tool ablation that
> separates tools from scaffolding. Five read-only tools, stop conditions, path guardrail,
> budget caps.

Reported, and not positive. ADR-0003 publishes a null result as a finding, and M3 already
paid that price. A flat delta closes M5.

Prediction persistence and the paired test stay out of the line. They become an issue that
**blocks** the delta issue, so the tracker enforces them and the line stays short.

## 15. Three Budget scopes, and one gloss corrected

`CONTEXT.md` now names the Instance Budget, the Evaluation Budget and the Milestone Budget.

The logged value `budget_exceeded` stays. A tool-call cap is a budget of calls. A rename
would make entries before and after M5 name one state two ways. Its gloss now says so.

The Instance Budget holds no dollar cap, and `CONTEXT.md` says why. Eight tool calls, each
with a capped result, cannot reach $0.05. A tunable cap under a structural bound could only
fire on a bug, and it would hide it.

Still to apply outside `CONTEXT.md`: replace loose uses of "run" in `docs/PRD.md`,
ADR-0008, and the code. `rerank.py`'s `BUDGET_USD` is an Evaluation Budget.

## 16. The free pre-work is a grep-reachability probe

For every dev-split Instance where the Candidate Set's hit@20 fails, which is roughly 27 of
244, check offline whether `git grep` can reach the ground-truth file from issue-text
tokens. Report the share reachable, and which token classes found it.

Those 27 Instances **are** rung 4's target. No reranker can be right on them. The probe
estimates the reachable headroom, and it tests decision 3. If the ground-truth file shares
no greppable token with the issue, rung 4's premise is in trouble before a dollar is spent.

Without it, a flat rung-4 result cannot be attributed between "the agent is bad" and "the
target was unreachable".

The original plan, a retrospective split of M4's 92 Off-List Paths, is dropped. The cache
holds one cell, `gpt-oss-high`, which produced only 6 of the 92. The informative cells are
absent. The cache stores no prompt. Recovering all 92 costs about $1.56. And the guardrail
catch rate it would size is a number that rung 4 produces itself. The 6 cached paths get an
existence check as a footnote.

## 17. Tool errors split by cause, and determinism is a contract

**Model-caused and recoverable** — an invalid regex, a path absent at `base_commit`, a bad
line range. These return to the agent as a tool result, and each costs one call. They are
information. A message that a path does not exist teaches the guardrail's lesson early.

**Infrastructure and not recoverable** — `RepoUnavailableError` and `CommitUnavailableError`
in `repos.py:37-46`. These raise and they fail the Instance loudly. As empty results they
would read as "the agent searched and found nothing" across every affected Instance.

Both classes are counted.

**The cap counts calls, not steps.** Eight means eight tool results. Batched calls in one
turn cost less than the same calls spread over turns, so batching stays available.

**Determinism is a contract on every tool.** Sorted output, no timestamps, no absolute paths
that leak `data/repos/`, deterministic truncation, and a stable serialization format. A test
asserts byte-identical tool output across two runs. Without it the replay stops working in
silence, and the next long run pays twice. Watch that test fail before trusting it.

## Corrections this session produced

**ADR-0008's second amendment lists the first-party `deepseek` route's quantization as
"unknown". It is fp8.** The probe's `system_fingerprint` reads
`fp_9954b31ca7_prod0820_fp8_kvcache_20260402`. Amend that table.

## Facts the session established, for whoever resumes

- `pyproject.toml` holds no `langchain` and no `langgraph`. ADR-0005 is Accepted and
  unexecuted. See task Q7.
- `scoring.py:188` computes `latency_s_median` and then discards it. `RESULTS.md`
  logs wall clock alone, so the README's latency column is a hand division of
  186m by 244.
- `HybridRung` fuses `Bm25ChunksRung` with `EmbedRung`, so warm start loads the
  1.5 GB index whatever the tool roster is.
- `data/cache/responses` holds 248 entries for the gpt-oss-high cell. An agent run
  replays from that cache for free, because the step-k prompt encodes the whole
  trajectory and tool results are fixed at a pinned commit.
- `rerank-deepseek-on` costs $0.0020 and takes 43.8s per instance at one call. The
  cost is input-dominated: 4,886 tokens at $0.435 per 1M is $0.0021.
