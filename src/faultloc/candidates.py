"""Merging two rankings into one candidate list.

M3 measured the lexical and dense rungs as statistically indistinguishable in
aggregate while failing on *different* repositories -- embeddings gained on
`sphinx`, `matplotlib` and `requests`, and lost on `scikit-learn`, `astropy`
and `pytest`. Reranking either list alone would therefore inherit that list's
misses on exactly the repositories where the other one had the answer.

A reranker reorders; it never adds. So the merged list's hit rate at K is the
**hard ceiling** on any reranker's Top-1, and the merge rule decides what lands
inside K. That makes the rule a real decision rather than plumbing.
"""

from __future__ import annotations

from collections.abc import Sequence

#: Damping constant in reciprocal rank fusion. 60 is the value from the paper
#: the method comes from (Cormack et al., 2009) and the near-universal default.
#: Its effect is to flatten the difference between the top few ranks, so a list
#: that is confidently wrong at rank 1 cannot dominate a list that is right at
#: rank 2.
RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    damping: int = RRF_K,
) -> tuple[str, ...]:
    """Merge ranked lists by summed reciprocal rank.

    Each list contributes `1 / (damping + rank)` to every path it ranks, and
    paths are ordered by the total. An item both retrievers rank highly beats
    one that only a single retriever loves, which is the behaviour wanted when
    the two are known to disagree by repository.

    Chosen over raw score fusion because BM25 scores and cosine similarities
    are not on the same scale and normalising them would introduce a second
    arbitrary decision. Rank is the one thing both lists agree on the meaning
    of.

    Ties break by path, as everywhere else in this project: without it the
    order would follow dictionary insertion and determinism would hold only by
    luck.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, path in enumerate(ranking, start=1):
            scores[path] = scores.get(path, 0.0) + 1.0 / (damping + rank)

    return tuple(sorted(scores, key=lambda path: (-scores[path], path)))


def interleave(rankings: Sequence[Sequence[str]]) -> tuple[str, ...]:
    """Merge by taking one from each list in turn, skipping repeats.

    The naive alternative to fusion, kept so the choice between them can be
    measured rather than asserted. It guarantees each retriever's top item
    appears in the first few slots, which fusion does not -- but it is blind to
    agreement, so a path both retrievers rank second gains nothing from that.
    """
    merged: list[str] = []
    seen: set[str] = set()
    for position in range(max((len(r) for r in rankings), default=0)):
        for ranking in rankings:
            if position < len(ranking):
                path = ranking[position]
                if path not in seen:
                    seen.add(path)
                    merged.append(path)
    return tuple(merged)


def hit_at_k(ranked: Sequence[str], truth: Sequence[str], k: int) -> bool:
    """Whether any ground-truth file appears in the top k.

    Distinct from the scorer's `recall_at_k`, which is the *share* of truth
    files found. This is the quantity that bounds a reranker's Top-1: the
    reranker picks one path, and it can only be right if at least one correct
    path was in the list it was handed.
    """
    return bool(set(truth) & set(ranked[:k]))
