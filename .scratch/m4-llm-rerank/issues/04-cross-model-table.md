# 04 — Cross-model comparison table

Status: ready-for-agent

## Parent

[M4 PRD](../PRD.md)

## What to build

The same rung, the same candidate lists, the same prompt, run against the models ADR-0008 named — and a table comparing them on accuracy, cost, and latency.

This is the milestone's second deliverable and it answers a different question from issue 03. Issue 03 asks *does reranking help?*; this asks *how much model do you need for it to?* A cheap model that recovers most of a frontier model's gain at a fraction of the price is the more useful engineering result, and it cannot be claimed without measuring both.

One `RESULTS.md` entry per model, so each figure keeps its own provenance. The table is a view over those entries, never a place where numbers are typed by hand.

## Acceptance criteria

- [ ] Every model from ADR-0008 run on the full dev split, each with its own `RESULTS.md` entry
- [ ] Table reports Top-1 with interval, Recall@3, Recall@5, cost per instance, and latency per model
- [ ] Total spend per model reported, and the actual against ADR-0008's estimate
- [ ] Overlapping intervals called out explicitly — with three models at n=244 the intervals are ±6pp and most pairs will not be separable
- [ ] Per-repo breakdown for at least the best and cheapest model, since M3 showed the aggregate hides redistribution
- [ ] Failure modes counted per model: unparseable responses, files returned that were not candidates
- [ ] Every figure traces to a `RESULTS.md` entry, checked by string match rather than by eye

## Notes

The interval problem is sharper here than anywhere else in the project. Three models at n=244 gives three overlapping intervals, and a table sorted by point estimate reads as a ranking whether or not one exists. Say plainly what is and is not established, as the M3 README does.

If the models are indistinguishable on accuracy, **that is the result** — and it makes the cheapest one the right choice, which is a stronger engineering claim than a frontier model winning by a point.

Cost per instance is the number that makes this table worth building. Report it beside accuracy in the same row, never in a footnote.

## Blocked by

- [03 — Rung 3 end to end, one model](03-rerank-rung.md)
