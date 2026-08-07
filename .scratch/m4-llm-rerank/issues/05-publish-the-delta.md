# 05 — Publish the rung-3 delta, close M4

Status: done

## Parent

[M4 PRD](../PRD.md)

## What to build

Closes M4. The numbers already exist in `RESULTS.md`. This issue turns them into a stated result.

The README ladder table fills its LLM rerank row and gains the cross-model table. Report the delta against **rung 2 and the best lexical row**. M3 established that rung 2 did not beat rung 1, so "delta over the rung below" stays ambiguous until it names which row it means.

Three numbers govern what anyone may claim, and all three must appear:

- **The ceiling from issue 01.** A reranker cannot exceed its candidate list's recall. If rung 3 lands near that ceiling, the remaining headroom is a retrieval problem and not a model problem. That is the finding M5 inherits.
- **The intervals.** At n=244 the Wilson interval is about ±6pp. Every gap in the ladder table so far has been narrower than that. The README must keep saying so, or adjacency in the table will imply an ordering.
- **The price.** Rung 3 is the first rung with a non-zero cost. A real gain that costs 40× rung 2 per instance is a different result from the same gain for free. ADR-0003's whole claim is that a rung's value is its delta *at its cost*.

## Acceptance criteria

- [x] The README ladder table carries the rung-3 row with Top-1 + interval, Recall@3, Recall@5, cost per instance, and latency
- [x] The cross-model table is published, and it states explicitly what the measurement establishes and what it does not
- [x] The delta is reported against rung 2.6, rung 2, and the best lexical row, each one named. Rung 2.6 sits directly below, so the ladder's rule credits against it
- [x] The union recall ceiling is stated, along with rung 3's distance from it
- [x] Total money spent across the milestone is reported. This is the first milestone with a bill
- [x] Every figure traces to a `RESULTS.md` entry. Check this by string match
- [x] `docs/milestones.md` closes M4 and marks M5 current
- [x] Any prediction this milestone overturned stays on the record rather than disappear into an edit

## Notes

The M1 and M3 pattern holds. Predictions that measurement overturned stay on the record. M3 overturned M1's Sphinx hypothesis and said so. Expect M4 to overturn something of M3's.

If rung 3 fails to beat rung 2, that is publishable, and it would be the second consecutive rung where it happens. Two null results in a row is a finding about the problem, not about the implementation. The README should say what that implies for M5: an agent that can *search* rather than reorder is the remaining lever.

Carried into M5 so nobody forgets it: issue 03's rung-3 failure-mode counts are the first evidence for the Path Guardrail that M5 must build. The relevant count is files returned that were not candidates.

## Blocked by

- [03 — Rung 3 end to end, one model](03-rerank-rung.md)
- [04 — Cross-model comparison table](04-cross-model-table.md)
- [06 — Rung 2.6, a cross-encoder between fusion and the LLM](06-cross-encoder-rung.md) — rung 3's delta measures over the rung below it, and that row does not exist until 2.6 has a score

## Comments

**Closed 2026-08-07. M4 is complete.**

The README now carries the rung-3 row, the cross-model table, the deltas against three named rows, the ceiling and the distance from it, and the milestone bill. `docs/milestones.md` closes M4 and marks M5 current.

### The delta, against each row it could mean

The ladder's rule credits a rung against the rung directly below. That is rung 2.6, and it gives the largest number and the least meaning, because rung 2.6 scored below every free rung.

| Against | Its Top-1 | Delta |
|---|---|---|
| Rung 2.6, cross-encoder | 26.6% | +47.6pp |
| Rung 2.5, rank fusion | 45.5% | **+28.7pp** |
| Rung 2, embeddings | 43.0% | +31.2pp |
| Best lexical row | 43.9% | +30.3pp |

**+28.7pp over fusion is the honest figure** and the README leads with it. Reporting +47.6pp would be true, mechanical, and misleading.

### What M4 overturned

Two predictions, both this project's own, both left on the record.

**Issue 06 built rung 2.6 to stop rung 3 taking credit for what reranking-in-general buys.** The reasoning was sound and the result inverted it: the cross-encoder scored 26.6%, below every free rung, so it protected nothing and became a null result of its own.

**This project expected the cheaper model to be the weaker one.** ADR-0008's first amendment already corrected the belief that proprietary models are a capability ceiling. M4 went further: the cheapest configuration to run scored second of four, and the most expensive per run scored last.

M3's prediction survived. It argued that the useful list to rerank is the union of both retrievers, because the two fail on different repositories. Fusion scores 45.5%, above both rungs it merges, and rung 3 reranks that union.

### What the milestone cost

$1.95 in published rows. $5.59 on the account. The gap is two thirds of the total and it bought a working client plus three rejected providers, each rejected on measurement:

- Cerebras enforces an 8,192-token completion limit while advertising 40,960, and truncated a third of replies.
- OpenRouter's shared Groq capacity ran out mid-run and stayed out for over thirty minutes.
- DeepInfra timed out and dropped connections, which the retry did not cover until it was fixed three times.

ADR-0008 set a $5.00 milestone cap. Against the original cap the milestone did not fit. Against the re-based budget, agreed partway through when $2.25 of abandoned spend was charged to setup, it did.

### What M5 inherits

**The remaining headroom is retrieval, not ranking.** The candidate list holds the answer for 88.9% of instances. The best configuration reaches 79.1%. `sphinx` sits exactly on its own 63.6% ceiling in all four configurations, so every model there picks correctly on every instance it could. An agent that only reorders aims at a gap that is mostly closed. An agent that searches aims at the one that is not.

**92 off-list paths** across the four configurations, ranging from 6 to 43. That is the Path Guardrail's sizing evidence, and the rate is worst for the configurations that reason least.

**Recall@5 barely exceeds Recall@3** in every configuration. These models answer decisively rather than hedge, so an escalation strategy has less to work with than the ceiling suggests.

**Two measurement gaps stay open.** Recall@k still carries no confidence interval anywhere in the project, and it has now been load-bearing three times. Rung 3's run-to-run variance is unmeasured, because no repeats were budgeted.

### One thing left undone

The ladder row fell back to fusion on 7% of instances, from replies that returned empty. All 244 responses are cached, so a fix would re-call only those 17 and cost cents. The published 74.2% is therefore depressed by a serving quirk rather than by the model. Recorded rather than fixed, because the figure is published and a change to it needs its own run and its own entry.
