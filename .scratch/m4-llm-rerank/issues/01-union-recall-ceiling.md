# 01 — The union candidate set and its recall ceiling

Status: ready-for-agent

## Parent

[M4 PRD](../PRD.md)

## What to build

A measurement, and the candidate-union code the rung will reuse.

A reranker reorders a list; it cannot add to it. So **the union's Recall@K is rung 3's hard ceiling** — if the union of both retrievers holds the answer in its top 20 for 85% of instances, no model reranking that list can exceed 85% Top-1. Measuring it costs nothing: both rungs already run, and no model is called.

Report Recall@K for K across a useful range for three candidate sets: lexical alone, dense alone, and their union. The comparison is the point — if the union is barely above the better of the two, then M3's "the retrievers are complementary" reading was wishful, and rung 3's premise is weaker than the PRD assumes.

The union also needs a defined merge order, since a reranker shown a list may be influenced by its order. State the rule and why.

This runs before the ADR because K sets the number of candidates, which sets the token count, which sets the bill. Choosing K after paying for it would be the wrong order.

## Acceptance criteria

- [ ] Candidate union produced from the two retrievers with a stated, deterministic merge order
- [ ] Recall@K reported for lexical, dense, and union across a range of K, on the dev split
- [ ] The union's ceiling stated plainly: the highest Top-1 any reranker over this list could achieve
- [ ] A recommended K, with the accuracy-against-token-count tradeoff shown rather than asserted
- [ ] Per-repo union recall reported, since M3's whole finding was that the aggregate hides a redistribution
- [ ] No model calls, no cost
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

Both retrievers already rank *every* source file, not a top-k slice, so "union" here means merging two full rankings and truncating — not a set union of two short lists. The merge rule is therefore a real decision: interleaving by rank, concatenating one after the other, and scoring by best rank across the two are all defensible and produce different lists.

Recall@K carries no confidence interval anywhere in this project yet, which M3 flagged as a gap. This issue leans on recall harder than any previous one. If the ceiling is close to a decision boundary, that gap becomes load-bearing and worth fixing here rather than noting again.

The dense rung needs the index at `data/index/`, which is gitignored and already built for the dev split. It is content-keyed, so nothing needs rebuilding.

## Blocked by

None — can start immediately.
