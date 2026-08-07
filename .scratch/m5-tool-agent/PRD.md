# M5 — Tool-using agent (rung 4)

## Goal

A rung-4 number on the dev split, reported as a **delta over rung 3** at its cost and latency, plus the zero-tool Ablation that separates the tools from the scaffolding around them.

## What M4 changed about this milestone

[ADR-0003](../../docs/adr/0003-baseline-ladder.md) describes rung 4 as *"a tool-using loop"* and says no more. M4's result says what the loop is for.

Rung 3 established the first real gap in this ladder. An LLM that reranks twenty candidates scores 74.2% Top-1 against fusion's 45.5%, and the intervals do not touch. The best of four cells reaches 79.1%.

**The Candidate Set holds a ground-truth file in its top 20 for 88.9% of Instances.** That is a hard ceiling on anything that reorders, because a reranker reorders and never adds. `sphinx` proves the shape of what is left: all four rung-3 cells score exactly 63.6% there, which is exactly its own hit@20. Every model picks correctly on every sphinx Instance where the answer was retrievable. Its remaining loss belongs to retrieval.

So rung 4 is not "rank better". It is: **go and find what retrieval missed.** Roughly 27 Instances of 244 are the target. No reranker can ever be right on them.

M4 also produced the first sizing evidence for hallucinated paths. Rung 3 named 92 files that were never candidates, and the rate differs sharply by cell. The two configurations that reason least hallucinate most, by roughly seven to one.

## The things this milestone must resolve

**Whether the target is reachable at all.** A read-only tool cannot reach a file that shares no token with the issue. If the 27 missed Instances are unreachable, a flat rung-4 result cannot be attributed between a weak agent and an impossible target. This is free to measure and it runs first.

**A delta that the statistics can read.** The test split stays closed until M7, so n stays at 244. A realistic rung-4 result of 78-82% is a delta of 4 to 8 percentage points against a ±6pp Wilson interval. Rung 3 and rung 4 run on the same Instances, so a paired test has far more power than two marginal intervals. Per-instance predictions must be persisted before any paired test is possible.

**Three variables that move together.** Rung 4 changes the scaffolding, the tools, and the output format at once. The zero-tool cell separates them, and it costs 8% of the main cell.

**Real money, and a six-hour run.** The main cell estimates at ~$7.4 and the zero-tool cell at ~$0.60. A fix that changes the prompt invalidates the response cache, so a re-run costs the same again.

## Done when

Rung-4 delta over rung 3 reported at cost and latency, with the zero-tool ablation that separates tools from scaffolding. Five read-only tools, stop conditions, path guardrail, budget caps.

Reported, and not positive. [ADR-0003](../../docs/adr/0003-baseline-ladder.md) publishes a null result as a finding.

## Out of scope

The Fresh Set (M6), the Calibrator and the coverage curve (M7), the service (M8). Rung 4 returns a ranked list and a Stop Condition. It does not report a Confidence, because [ADR-0004](../../docs/adr/0004-calibrated-confidence.md) gives that job to the Calibrator.

Code execution stays out, as [ADR-0002](../../docs/adr/0002-no-code-execution.md) decided. No test runs, no sandbox, no container per Instance.
