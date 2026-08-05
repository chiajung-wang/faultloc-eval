"""Rank fusion of the lexical and dense rungs. No model.

Not a rung of the ladder in ADR-0003's sense -- nothing is stacked on it. It
exists because measuring the candidate union's ceiling (M4 issue 01) showed
fusion alone at 45.5% hit@1, above both the rungs it merges, and a free method
that beats every priced one has to be measured properly rather than mentioned.

It is also the honest comparison point for rung 3. Reranking the union with a
model has to beat *this*, not rung 2 -- otherwise the model is being credited
with a gain that reciprocal rank fusion produced for nothing.

Cost is the sum of its parts, which is currently zero. Latency is not: this
runs both retrievers, so it is strictly slower than either.
"""

from __future__ import annotations

import time

from faultloc.candidates import reciprocal_rank_fusion
from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.rungs import Prediction, Rung, StopCondition
from faultloc.rungs.bm25_chunks import Bm25ChunksRung
from faultloc.rungs.embed import EmbedRung


class HybridRung:
    """Both retrievers, merged by reciprocal rank fusion."""

    name = "hybrid"

    def __init__(
        self,
        store: RepoStore | None = None,
        *,
        lexical: Rung | None = None,
        dense: Rung | None = None,
    ) -> None:
        shared = store or RepoStore()
        self.lexical = lexical or Bm25ChunksRung(shared, include_bodies=True)
        self.dense = dense or EmbedRung(shared)

    def predict(self, instance: Instance) -> Prediction:
        started = time.perf_counter()

        parts = [self.lexical.predict(instance), self.dense.predict(instance)]
        merged = reciprocal_rank_fusion([p.ranked_files for p in parts])

        # `no_candidates` only when *both* retrievers had nothing. One empty
        # list is a retriever result, not a pipeline failure, and collapsing
        # the two would hide the second inside the first.
        stop = StopCondition.ANSWERED if merged else StopCondition.NO_CANDIDATES

        return Prediction(
            instance_id=instance.instance_id,
            rung=self.name,
            ranked_files=merged,
            stop_condition=stop,
            # Wall clock of the whole fusion, not the sum of the parts: the
            # merge itself costs something and a reader comparing rungs is
            # comparing end-to-end time.
            latency_s=time.perf_counter() - started,
            cost_usd=sum(p.cost_usd for p in parts),
        )
