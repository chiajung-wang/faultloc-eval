# 05 — Publish the rung-3 delta, close M4

Status: ready-for-agent

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

- [ ] The README ladder table carries the rung-3 row with Top-1 + interval, Recall@3, Recall@5, cost per instance, and latency
- [ ] The cross-model table is published, and it states explicitly what the measurement establishes and what it does not
- [ ] The delta is reported against rung 2.6, rung 2, and the best lexical row, each one named. Rung 2.6 sits directly below, so the ladder's rule credits against it
- [ ] The union recall ceiling is stated, along with rung 3's distance from it
- [ ] Total money spent across the milestone is reported. This is the first milestone with a bill
- [ ] Every figure traces to a `RESULTS.md` entry. Check this by string match
- [ ] `docs/milestones.md` closes M4 and marks M5 current
- [ ] Any prediction this milestone overturned stays on the record rather than disappear into an edit

## Notes

The M1 and M3 pattern holds. Predictions that measurement overturned stay on the record. M3 overturned M1's Sphinx hypothesis and said so. Expect M4 to overturn something of M3's.

If rung 3 fails to beat rung 2, that is publishable, and it would be the second consecutive rung where it happens. Two null results in a row is a finding about the problem, not about the implementation. The README should say what that implies for M5: an agent that can *search* rather than reorder is the remaining lever.

Carried into M5 so nobody forgets it: issue 03's rung-3 failure-mode counts are the first evidence for the Path Guardrail that M5 must build. The relevant count is files returned that were not candidates.

## Blocked by

- [03 — Rung 3 end to end, one model](03-rerank-rung.md)
- [04 — Cross-model comparison table](04-cross-model-table.md)
- [06 — Rung 2.6, a cross-encoder between fusion and the LLM](06-cross-encoder-rung.md) — rung 3's delta measures over the rung below it, and that row does not exist until 2.6 has a score
