# 04 — Cross-model comparison table

Status: ready-for-agent

## Parent

[M4 PRD](../PRD.md)

## What to build

Run the same rung, the same candidate lists, and the same prompt against every model ADR-0008 named. Then build a table that compares them on accuracy, cost, and latency.

This is the milestone's second deliverable, and it answers a different question from issue 03. Issue 03 asks *does reranking help?* This asks *how much model do you need before it does?* A cheap model that recovers most of a frontier model's gain at a fraction of the price is the more useful engineering result. Nobody can claim it without measuring both.

Write one `RESULTS.md` entry per model, so each figure keeps its own provenance. The table is a view over those entries. Never type a number into it by hand.

## Acceptance criteria

- [ ] Every model from ADR-0008 runs on the full dev split, each with its own `RESULTS.md` entry
- [ ] The table reports Top-1 with interval, Recall@3, Recall@5, cost per instance, and latency per model
- [ ] The table reports total spend per model, and the actual figure against ADR-0008's estimate
- [ ] The table states overlapping intervals explicitly. At n=244 the intervals are ±6pp, so most pairs will not separate
- [ ] Per-repo breakdown for at least the best and the cheapest model. M3 showed that the aggregate hides redistribution
- [ ] Failure modes counted per model: unparseable responses, and files returned that were not candidates
- [ ] Every figure traces to a `RESULTS.md` entry. Check this by string match rather than by eye

## Notes

The interval problem is sharper here than anywhere else in the project. Three models at n=244 give three overlapping intervals. A table sorted by point estimate reads as a ranking whether or not a ranking exists. State plainly what the measurement establishes and what it does not, as the M3 README does.

If the models are indistinguishable on accuracy, **that is the result**. It makes the cheapest one the right choice, which is a stronger engineering claim than a frontier model that wins by a point.

Cost per instance is the number that makes this table worth building. Report it beside accuracy in the same row. Never put it in a footnote.

## Blocked by

- [03 — Rung 3 end to end, one model](03-rerank-rung.md)
