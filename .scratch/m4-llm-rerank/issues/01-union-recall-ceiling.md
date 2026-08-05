# 01 — The union candidate set and its recall ceiling

Status: done

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

## Comments

**Closed 2026-08-05.** Measured at code `ab5e4b1`, dev split, n=244, no model calls. Median candidate list is 841 files per instance.

```
hit@K  -- ceiling on rung-3 Top-1
                      K=1     K=3     K=5     K=10    K=20    K=50    K=100
lexical                43.9%   62.7%   67.2%   78.7%   85.2%   91.0%   95.1%
dense                  43.0%   60.7%   70.5%   80.7%   84.8%   89.3%   93.9%
union (rrf)            45.5%   67.6%   75.8%   83.2%   88.9%   93.9%   95.9%
union (interleave)     43.9%   67.6%   72.1%   83.6%   88.9%   93.9%   96.3%
```

### The headline: this is a ranking problem, not a retrieval problem

**The answer sits in the top 20 for 88.9% of instances. The rungs pick it 43.9% of the time.**

Roughly 45 points of headroom, and none of it is retrieval — the candidate list already holds the answer. That is the strongest justification rung 3 has had, and it also tells M5 something: an agent whose advantage is *searching harder* is aiming at a gap that mostly is not there. The gap is in choosing.

### Recommended K: 20

| K | ceiling | vs K=20 | candidates sent |
|---|---|---|---|
| 5 | 75.8% | −13.1pp | 4× fewer |
| 10 | 83.2% | −5.7pp | 2× fewer |
| **20** | **88.9%** | — | — |
| 50 | 93.9% | +5.0pp | 2.5× more |
| 100 | 95.9% | +7.0pp | 5× more |

K=20 is the knee. Below it the ceiling falls faster than the token count; above it, 2.5× the tokens buys five points of headroom that a reranker is unlikely to convert, since the marginal candidates are ones both retrievers ranked poorly.

Stated for ADR-0008 rather than decided here: K=50 becomes worth revisiting if rung 3 lands *at* the K=20 ceiling, because then the ceiling is the binding constraint rather than the model.

### The merge rule barely matters, and my argument for it was overconfident

I chose reciprocal rank fusion on the grounds that it rewards agreement — a path both retrievers rank second beats one that a single retriever ranks first — and argued that property was exactly right given M3's finding that the two are confidently wrong on different repositories.

**At K=20 the two rules are identical: 88.9% each.** RRF wins at K=5 (75.8 vs 72.1), interleave edges it at K=10 and K=100. For supplying a reranker with candidates the choice is irrelevant, and the reasoning bought nothing.

RRF is kept, on a different justification: the hybrid rung below is a scored row in its own right, and Top-1, Recall@3 and Recall@5 all live at K≤5 where RRF is ahead in two of three. That margin is four instances out of 244 with no interval, so it is a defensible default rather than a demonstrated result. The agreement property is real and pinned by a test; it simply does not matter much on this data.

### M3's complementarity reading holds, modestly

The union beats the better single retriever by +3.7pp at K=20 and +5.3pp at K=5. Real, and smaller than "the retrievers are complementary" implied. Had the union come in level with the better of the two, rung 3's whole premise would have needed rewriting — it did not, but the margin is thinner than M3's per-repo table suggested.

### An unplanned finding: fusion alone beats every rung

`union (rrf)` at K=1 is **45.5%**, above both rungs it merges (43.9% lexical, 43.0% dense). A free method, no model, ahead of everything in the project.

That is outside this issue's scope but too consequential to leave as a note, so the `hybrid` rung was added and scored. It changes rung 3's comparison point: reranking has to beat *fusion*, not rung 2, or the model is credited with a gain that reciprocal rank fusion produced for nothing.

**Scored at code `0f3389b`, and it is the best row in the project:**

| Row | Top-1 | Recall@3 | Recall@5 | Cost |
|---|---|---|---|---|
| `bm25` whole file | 39.3% (33.4–45.6) | 59.3% | 68.5% | $0.00 |
| `bm25-chunks-bodies` | 43.9% (37.8–50.1) | 60.3% | 65.7% | $0.00 |
| `embed` | 43.0% (37.0–49.3) | 57.9% | 67.8% | $0.00 |
| **`hybrid`** | **45.5%** (39.4–51.8) | **65.2%** | **73.1%** | $0.00 |

Top-1's interval still overlaps every other row, so on the headline metric nothing is established — as has been true of every gap in this ladder. The Recall@3 and Recall@5 margins are the largest in the project (+4.9pp and +4.6pp over the previous best), and they remain the statistic with no interval.

Sphinx reaches **36.4%**, eight times rung 1's 4.5%.

**Fusion is not strictly better than its parents per repo.** `scikit-learn` 68.8% against lexical's 81.2%, `pylint` 25% against lexical's 50%. A rank-based rule has no way to know which retriever to trust on which repository, so where one is confidently right and the other confidently wrong, fusion splits the difference and can land below both.

That is exactly the judgement a reranker could supply, and it sharpens rung 3's job: not "reorder a list" but "decide which retriever was right here". It also means the +45pp of headroom above is not uniformly available — some of it requires knowing something fusion structurally cannot.

### Sphinx is the ceiling's problem child

Per-repo hit@20 for the union:

| repo | n | hit@20 |
|---|---|---|
| scikit-learn, xarray, requests, seaborn | 32 | 100% |
| matplotlib | 17 | 94.1% |
| django | 113 | 91.2% |
| astropy, pytest | 20 | 90.0% |
| sympy | 36 | 86.1% |
| pylint | 4 | 75.0% |
| **sphinx** | **22** | **63.6%** |

A perfect reranker caps Sphinx at 63.6%. It is the only repo where the ceiling itself is the binding constraint — everywhere else there is room for a model to earn its cost. Sphinx has now been the outlier at every rung, and for a third distinct reason.

### The recall-interval gap

This issue's Notes flagged that Recall@k carries no confidence interval anywhere in the project, and warned it would become load-bearing here. It did, mildly: the K=20 vs K=50 choice rests on a 5pp difference in an unbounded statistic, and the RRF-vs-interleave call rests on ~4 instances. Neither decision is close enough for an interval to flip it, so it is still recorded rather than fixed.
