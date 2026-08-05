# 05 — Publish the rung-3 delta, close M4

Status: ready-for-agent

## Parent

[M4 PRD](../PRD.md)

## What to build

Closes M4. The numbers exist in `RESULTS.md`; this turns them into a stated result.

The README ladder table fills its LLM rerank row and gains the cross-model table. The delta is reported against **rung 2 and the best lexical row**, because M3 established that rung 2 did not beat rung 1 — so "delta over the rung below" is ambiguous unless it names which row it means.

Three numbers govern what may be claimed, and all three must appear:

- **The ceiling from issue 01.** A reranker cannot exceed its candidate list's recall. If rung 3 lands near that ceiling, the remaining headroom is a retrieval problem and not a model problem, and that is the finding M5 inherits.
- **The intervals.** At n=244 the Wilson interval is about ±6pp. Every gap in the ladder table so far has been narrower than that, and the README must keep saying so rather than letting adjacency imply an ordering.
- **The price.** Rung 3 is the first rung with a non-zero cost. A gain that is real but costs 40× rung 2 per instance is a different result from the same gain for free, and ADR-0003's whole claim is that a rung's value is its delta *at its cost*.

## Acceptance criteria

- [ ] README ladder table carries the rung-3 row with Top-1 + interval, Recall@3, Recall@5, cost per instance, latency
- [ ] Cross-model table published, with what is and is not established stated explicitly
- [ ] Delta reported against both rung 2 and the best lexical row, each named
- [ ] The union recall ceiling stated, and rung 3's distance from it
- [ ] Total money spent across the milestone reported — this is the first milestone with a bill
- [ ] Every figure traces to a `RESULTS.md` entry, checked by string match
- [ ] `docs/milestones.md` updated to close M4 and mark M5 current
- [ ] Any prediction this milestone overturned recorded rather than edited away

## Notes

The M1 and M3 pattern holds: predictions that measurement overturned stay on the record. M3 overturned M1's Sphinx hypothesis and said so; M4 should expect to overturn something of M3's.

If rung 3 fails to beat rung 2, that is publishable and this is the second consecutive rung where it would be. Two null results in a row is a finding about the problem, not about the implementation, and the README should say what it implies for M5: that an agent which can *search* rather than reorder is the remaining lever.

Carried into M5 so it is not forgotten: the rung-3 failure-mode counts from issue 03 — files returned that were not candidates — are the first evidence for the Path Guardrail that M5 must build.

## Blocked by

- [03 — Rung 3 end to end, one model](03-rerank-rung.md)
- [04 — Cross-model comparison table](04-cross-model-table.md)
