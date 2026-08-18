# 06 — Publish the rung-4 delta, the zero-tool ablation, and close M5

Status: done

## Parent

[M5 PRD](../PRD.md)

## What to build

Two runs on the dev split, two `RESULTS.md` entries, and the report that closes the milestone.

**This issue spends about $4.** The Evaluation Budget is $12 per run and the Milestone Budget is $20.

*Estimates corrected 2026-08-17 against issue 04's measurement. ADR-0009 put the main cell at ~$7.4 and ~6h before anything ran. Measured, it is $0.0107 to $0.0122 per Instance and about 59s, so ~$3.0 and ~4h.*

### The two cells

| Cell | Tool-call cap | Estimated cost | Estimated wall clock |
|---|---|---|---|
| `agent` — the ladder row | 8 | ~$3.0 | ~4h |
| `agent-no-tools` — the Ablation | 0 | ~$0.60 | ~25m |

Both pin `deepseek/deepseek-v4-pro` on the first-party `deepseek` route, reasoning at its default, and both were declared in ADR-0009 before either ran. The route serves fp8, and the entry records that beside the model ID and revision.

Run them one at a time. Sequential is the decision, and a run resumes from the response cache after an interruption.

### The baseline must be re-run, and it costs $0.49

Issue 02 found this. The paired test needs the baseline's **per-instance** Predictions, and M4 published only its aggregate.

The response cache holds 244 replies for `gpt-oss-high` and **4** for `deepseek-off`. `rerank-deepseek-on` has **none**. So its Predictions cannot be replayed and the cell must run again at about **$0.49**.

Do not substitute the free cached cell. `rerank` replays for $0.00, and it is `gpt-oss-high` on DeepInfra at high effort. Rung 4 pins `deepseek-on` on the first-party route. Comparing across those moves the model, the route and the reasoning setting at once, which is the confound ADR-0009's pin exists to remove.

Budget: ~$3.0 main cell, ~$0.60 zero-tool cell, ~$0.49 baseline. About **$4.1**, well inside the $12 Evaluation Budget and the $20 Milestone Budget. That leaves room for a full re-run if a fix changes the prompt.

### Run order, and why the cheap cell goes first

1. **`agent-no-tools`** — ~$0.60, ~25m. The sanity check as well as the Ablation.
2. **`rerank-deepseek-on`** — ~$0.49, ~178m. The paired-test baseline.
3. **`agent`** — ~$3.0, ~4h. The ladder row.

The zero-tool cell is one call per Instance with no tools and no loop, and it
still drives the whole 244-Instance harness: the Evaluation Budget, the
predictions file, the `RESULTS.md` entry, and the failure note. A bug that only
appears at scale therefore costs 25 minutes and $0.60 rather than four hours and
$3. M4 lost $2.25 to a failure of exactly that shape.

Commit between every run. A run's own `RESULTS.md` write dirties the tree, so two
back to back can never both be clean.

### The two deltas

**The ladder delta**, against rung 3's matched cell `rerank-deepseek-on` at 79.1% (73.6-83.7). Same model, same route, same reasoning setting, so the only thing that moves is the loop and the tools.

**The tools delta**, against `agent-no-tools`. This is the attributable one, because it holds the scaffolding and the output format fixed.

Report both, and **say which one licenses which claim.** Use issue 02's paired test for each, and keep the Wilson intervals on the table.

### What the entries and the report must carry

- Cost and latency beside every accuracy figure, as always
- The **distribution of tool-call counts**, and how often the cap of 8 was reached. If most Instances reached it, the cap produced the number and not the agent. That is ADR-0009's revisit condition.
- The **Path Guardrail catch rate**, which `CONTEXT.md` promises
- **Accepted Off-List Paths**: how many, and how many were correct. This is the measure of whether rung 4 earned its rung, because it is the only route above the 88.9% ceiling.
- **Tool-Reached**, split. A ground-truth path that no tool ever surfaced was recalled rather than found, and the Verified Set predates the training cutoff.
- **Per-tool contribution**, which decides whether `semantic_search` earned its slot
- Every counted failure path: absent submissions, truncated replies, guardrail rejections, and Stop Condition rates
- Per-repo results, and `sphinx` in particular. It sat exactly on its 63.6% ceiling in all four rung-3 cells. Whether rung 4 moves it is the sharpest single test of whether tools reach what retrieval missed.

### Closing the milestone

Update the README's results table and its narrative. Update `docs/milestones.md` with what M5 established and what it carries into M6 and M7. Record the spend against the Milestone Budget, and separate published rows from setup as ADR-0008's budget note does.

## Acceptance criteria

- [ ] ~~`rerank-deepseek-on` re-run so the baseline has per-instance Predictions~~ **DROPPED.** Pinning rung 4 to bounded reasoning left this cell unmatched, and re-running it cost 17x M4's figure. ADR-0009 records the drop. `agent-no-tools` isolates the tools more finely than this cell would have.
- [x] Both cells run over the full dev split, and each emits a `RESULTS.md` entry with measured cost
- [x] Both entries record the model ID, the revision, the provider tag and the serving precision
- [x] Neither run publishes from a dirty tree
- [x] The ladder delta and the tools delta are both reported, each with the paired test, and the entry states which licenses which claim *(the third, attributable delta, was dropped -- see above)*
- [x] Tool-call distribution and cap-reached rate published, **and the entry states whether the cap bound the result** — both smoke runs reached it on 6 of 6 Instances, median exactly 8, so ADR-0009's revisit condition has fired every time so far
- [x] Per-tool contribution decides `semantic_search`'s slot, or says why it cannot — three of five tools recorded zero calls across the three smoke Instances, none of which was a `sphinx` Instance
- [x] Path Guardrail catch rate published
- [x] Accepted Off-List Paths counted, and the correct share reported
- [x] Tool-Reached split reported
- [x] Per-tool contribution reported
- [x] Stop Condition rates and every counted failure path published
- [x] Per-repo results published, `sphinx` included
- [x] README figures match the log by string match, not by eye
- [x] Spend recorded against the Milestone Budget, with published rows separated from setup
- [x] `docs/milestones.md` records what M5 established
- [x] A null or negative delta is published as the finding, not held back

## Notes

**A null result closes this milestone.** ADR-0003 commits to it, and M3 already paid that price once. A flat rung-4 delta is a publishable finding about when an agent is not worth deploying, which is the argument the README makes for this whole project.

**Do not run both cells in parallel.** M4's first attempt launched four at once, spent $2.25, and completed nothing. Its per-instance estimates proved 45% low, and one cell died at seven minutes on an unretried 429.

**A run's own `RESULTS.md` write dirties the tree for the next run.** Commit between the two cells.

**Watch the counters during the run, not after.** M4 caught a Cerebras truncation bug at instance 40 of a run that would otherwise have published a plausible number produced entirely by fusion. Every one of these failures produces *a ranking*, so the run looks healthy in every metric except the one saying how often the model actually answered.

**A fix that changes the prompt invalidates the cache.** The Milestone Budget holds room for exactly one full re-run. Debug with `--limit 3` at roughly $0.09 before touching a full run.

The four rung-3 cells cost $1.95 in published rows against $5.59 on the account. Expect the gap here to be smaller, because the route is found and the client works, but do not assume it is zero.

## Blocked by

- [02 — Persist per-instance predictions, and add the paired test](02-persist-predictions-paired-test.md)
- [05 — The four remaining tools, each honoring the contract](05-remaining-tools.md)

## Comments

**Closed 2026-08-18.** Three runs, about **$11** against a $20 Milestone Budget. Entries `0567b05` and `578e473`, publication `bae8c88`.

### The result

| Cell | Top-1 | Cost | Wall clock |
|---|---|---|---|
| `agent` — the ladder row | **88.1%** (83.5-91.6) | $5.19 | 169m |
| `agent-no-tools` — the Ablation | 84.0% (78.9-88.1) | $5.59 | 167m |
| rung 3, `rerank` | 74.2% (68.3-79.3) | $0.39 | 186m |

**The tools delta is +4.1pp at p=0.087, and it is not established.** Nineteen Instances won, nine lost, twenty-eight discordant. That is the only comparison that isolates the tools, and it is what M5 publishes.

The ladder delta against rung 3 is +13.9pp at p=1.2e-06 and is **not** the agent's achievement. Six variables move at once, and the Ablation attributes about ten of those points to the loop and the answer format.

### The Ablation paid for itself, and it was declared first

ADR-0009 named it before either cell ran. Without it, M5 would have published +13.9pp as what an agent buys. This is the second time in this project an Ablation stopped a paid system from taking credit for something else: M3's chunking ablation was the first.

### Why the tools bought so little

**Rung 4 reached past the Candidate Set twice in 244 Instances.** That is its only structural advantage over a reranker, and the most direct explanation of the small delta. Both paths were surfaced by a tool rather than recalled, which Tool-Reached confirms.

Issue 01 measured the reachable ceiling at 95.5% and rung 4 reached 88.1%, so the gap that remains is retrieval, which no amount of tool use recovered.

### Two of five tools carry the work

`read_file` 811 calls and 121 Top-1 finds, `search_code` 618 and 81, `file_outline` 89 and 39, `find_definition` 10 and 1, `semantic_search` **3 calls and 0**. ADR-0002 takes a recorded correction.

### The cap binds

141 of 244 Instances reached the eight-call cap, median exactly 8. ADR-0009's revisit condition has fired, and 88.1% is a lower bound on what this design does with more room.

### What went wrong, and what it cost

Four real bugs, all found by running rather than by tests: a client with no request timeout, runaway reasoning that spent an entire 16,000-token budget without answering, a 900s timeout inherited from rung 3 that made eight retries take two hours, and a `request_timeout` fix that was itself the cause of a later hang.

Two claims I made and had to withdraw. I called a stalled run "progressing" from one signal, a cache that was growing from a different process. And I said the provider was down after four consecutive hangs, when a raw request to the same endpoint answered in 1.7 seconds — the fault was mine, in the parameter I had added two commits earlier.

One planned comparison was dropped rather than bought. Pinning rung 4 to bounded reasoning left M4's unbounded 79.1% cell unmatched, and re-running it cost 17x M4's measured figure and would have breached rung 3's $2.00 cap at Instance 57.

### What the free-replay property was worth

A run stopped at Instance 130 on an out-of-credit 402. Resuming replayed 162 Instances for **$0.00** and paid only for the remainder. That is why the response cache keys on the whole transcript and the tool surface, and why this project kept its own cache rather than the framework's.
