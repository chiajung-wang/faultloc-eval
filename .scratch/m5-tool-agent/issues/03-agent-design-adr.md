# 03 — ADR-0009: rung 4's design, its budgets, and two cells declared in advance

Status: done

## Parent

[M5 PRD](../PRD.md)

## What to build

ADR-0009, plus two editorial sweeps that the ADR makes necessary.

A grilling session on 2026-08-07 settled seventeen questions about rung 4. The record sits in [`grilling-decisions.md`](../grilling-decisions.md). This issue turns that record into a decision document with its rationale and its rejected alternatives, in the shape of [ADR-0008](../../../docs/adr/0008-llm-rerank.md).

### What the ADR must decide

**The agent starts warm.** It receives the issue text and the top-20 union Candidate Set with Evidence Chunks. That payload is byte-identical to rung 3's prompt. One variable moves against rung 3: the loop and the tools. Rung 4 replaces rung 3's single call, and it does not chain onto rung 3's output.

**The tool roster stays at five, as [ADR-0002](../../../docs/adr/0002-no-code-execution.md) fixed it.** `search_code` is `git grep`, not BM25 over the same chunks. `submit_ranking` carries the final answer, and it is a terminal action rather than a sixth read-only tool.

**Three Budget scopes**, as `CONTEXT.md` now names them. The Instance Budget is 8 tool calls and 600s. The Evaluation Budget is $12. The Milestone Budget is $20. The Instance Budget holds no dollar cap, because eight capped tool results cannot reach $0.05.

**The pin: `deepseek/deepseek-v4-pro`, the first-party `deepseek` route, reasoning at its default.** Declared before any number exists. Its matched rung-3 baseline already exists at 79.1% (73.6-83.7), $0.49 and 178m, so the delta is attributable for no extra money. The route serves fp8, which a probe established on 2026-08-07.

**Two cells, both declared in advance.** The main cell at 8 tool calls. The zero-tool cell at a cap of 0, which costs about $0.60. The ADR names both before either runs, for the reason ADR-0008 gives: the headline cannot become whichever cell happens to win.

**The answer contract.** The Path Guardrail drops paths absent at `base_commit`. The agent's own order comes first. Unmentioned candidates append behind in Candidate Set order. Duplicates go. Top-1 and Recall@3 and Recall@5 all read positions inside 5, so list length past 5 needs no truncation constant.

**The guardrail retries once and it never fails the Instance.** No sixth Stop Condition. The run counts the event, and that count is the catch rate.

**Tool errors split by cause.** A model-caused error returns to the agent as a tool result and costs one call. An infrastructure error raises and fails the Instance loudly.

**Determinism is a contract on every tool**, because a resumed run replays from the response cache only while each step's prompt stays byte-identical.

### What the ADR must state as a consequence

**A declared confound.** Rung 3 parsed text and rung 4 does not. Part of rung 4's delta is therefore a better output format. Rung 3 lost 17 of 244 replies to unparseable content. The zero-tool cell prices this, and the ADR must say so rather than discover it.

**The cap of 8 may produce the number.** If most Instances reach it, the cap bound the result. The entry reports the tool-call distribution, and that is the revisit condition for raising the cap.

**A prompt-changing fix costs a full re-run**, because it invalidates the cache. The Milestone Budget of $20 holds room for exactly one.

**[ADR-0005](../../../docs/adr/0005-langgraph.md)'s explanatory debt is due at this milestone.** Its amendment names the four questions. This ADR answers the tool-error one already.

### The two sweeps

**Apply the Budget scope names outside `CONTEXT.md`.** `docs/PRD.md` and ADR-0008 use the bare word *run* where they mean an Evaluation Budget. `rerank.py`'s `BUDGET_USD` is an Evaluation Budget. The PRD's per-instance caps of $0.50, 25 tool calls and 120s are superseded, and the PRD must say so rather than contradict this ADR.

**Amend M5's row in `docs/milestones.md`** to the done-when in the [PRD](../PRD.md). The current wording names machinery only, so M5 could close with no number.

## Acceptance criteria

- [x] `docs/adr/0009-*.md` exists, with Context, Decision, Rationale, Consequences, Revisit condition and Alternatives rejected
- [x] Every decision above appears with its rationale
- [x] Both cells are named before any run
- [x] The output-format confound is stated as a consequence, not left implicit
- [x] Alternatives rejected covers at least: the cold start, chaining onto rung 3, BM25 as `search_code`, a four-tool roster, a free-text answer, a sixth Stop Condition, a per-instance dollar cap, and a deferred ablation
- [x] It cites issue 01's reachability finding
- [x] `docs/PRD.md` and ADR-0008 use the Budget scope names, and the PRD's superseded caps say so
- [x] `docs/milestones.md` carries M5's amended done-when
- [x] ADR-0003's rung table and `CONTEXT.md` still agree with each other about rung 4

## Notes

**Cite issue 01 rather than assume it.** If few of the missed Instances are reachable by any pattern class, this ADR has to answer that instead of writing past it. A rung whose target is unreachable is worth knowing about before $8 rather than after.

Read [`grilling-decisions.md`](../grilling-decisions.md) first. It carries the reasoning, including the options that lost and why. An ADR that records only the winners is worth less than one that records the trade.

Two decisions in that file came from the owner against a recommendation, and both held up. Sequential running over concurrency. Reasoning on rather than off, because M4 measured its reasoning null result on single-turn reranking and that does not transfer to multi-turn planning. Keep both attributions.

## Blocked by

- [01 — Is the target reachable? Grep-reachability where the Candidate Set misses](01-grep-reachability.md)


## Comments

**Closed 2026-08-17.** ADR-0009 shipped in commit `0bb25ba`, and the status line was simply never flipped afterwards. Every criterion was re-checked against the files rather than ticked from memory.

**One was genuinely unmet.** ADR-0008 carried no Budget scope names at all. Its amendments say "per-run cap" throughout, meaning one evaluation of a split, and `CONTEXT.md` now reserves that word for three different scopes.

The amendments keep their original wording. They are the record of what was decided and when, and rewriting them would be an edit rather than a correction. A terminology note sits above them instead, mapping "per-run" to the Evaluation Budget and pointing at ADR-0009's $12 and $20. A rung-4 Instance makes up to eight calls where a rung-3 Instance makes one, so ADR-0008's caps do not transfer.

**Corrections ADR-0009 has taken since it was written**, both recorded in place:

- `search_code` was described as "a literal and regex search". Literal is what issue 01 measured its 59.3% reachability with, and literal is what shipped.
- Its cost and latency estimates ran high. The measured figures are about $3.0 and four hours per cell against ~$7.4 and ~6h, and issue 04's closing comment carries the arithmetic.

**One claim it makes is now contradicted by evidence.** ADR-0009 sets the tool-call cap at 8 and names the distribution as its revisit condition. The cap has been reached on **6 of 6 Instances** across two smoke runs, median exactly 8. Issue 06 must report that, and if it holds at scale the published number belongs to the cap rather than to the agent.
