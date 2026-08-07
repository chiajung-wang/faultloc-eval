"""Rung 2.6: a cross-encoder reorders the Candidate Set. No API, no money.

This rung exists so rung 3 is not credited with a gain that reranking-in-general
produces. `CONTEXT.md` makes a rung's value its delta over the rung *below*, so
inserting one changes what the rung above is credited with -- and without this
row, an LLM's number would be measured against fusion and quietly absorb
everything a free local model could have done.

The mechanism is what earns it a number rather than an Ablation. Rung 2 embeds
the issue and the chunk separately, so a chunk's vector cannot depend on the
query. A cross-encoder reads both in one forward pass and can score a chunk as
relevant *to this issue*. Rung 3 also reads both together, but reasons over all
twenty candidates at once in natural language. Three mechanisms, one metric.

The payload is ADR-0008's, exactly: each candidate is its path plus its
Evidence Chunk. A rung that scored different text would make the 2.6-to-3 delta
measure the payload rather than the mechanism.

Only the head is reordered. The tail keeps fusion's order so the list stays the
one issue 01 measured a ceiling on -- a rung that dropped it would be scored on
a different candidate set from the rung it is compared against.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.rungs import Prediction, Rung, StopCondition
from faultloc.rungs.hybrid import HybridRung

#: Candidates shown to the model. ADR-0008 fixes this at the knee of issue 01's
#: ceiling curve: K=20 holds the answer for 88.9% of instances, and K=50 buys
#: five more points for 2.5x the work.
TOP_K = 20

#: Takes (query, document) pairs, returns one relevance score per pair.
Scorer = Callable[[Sequence[tuple[str, str]]], Sequence[float]]

#: Takes an instance and candidate paths, returns each path's Evidence Chunk.
EvidenceSource = Callable[[Instance, Sequence[str]], dict[str, str]]


@dataclass(frozen=True)
class RerankerSpec:
    """The cross-encoder, pinned by identifier *and* revision.

    Both halves are load-bearing for the same reason ADR-0007 pins rung 2's
    encoder: a model name is not provenance.
    """

    name: str
    revision: str
    #: Tokens the model accepts. Below the pair length, the tail is discarded
    #: silently, which is indistinguishable from weak ranking in every metric.
    max_length: int


class CrossEncoderRung:
    """Joint (issue, Evidence Chunk) scoring over the Candidate Set."""

    name = "cross-encoder"

    def __init__(
        self,
        store: RepoStore | None = None,
        *,
        candidates: Rung | None = None,
        evidence: EvidenceSource | None = None,
        score: Scorer | None = None,
        spec: RerankerSpec | None = None,
        top_k: int = TOP_K,
    ) -> None:
        self.candidates = candidates or HybridRung(store)
        self.evidence = evidence or self.candidates.lexical.evidence
        self.spec = spec
        self.top_k = top_k
        self._score = score

    @property
    def score(self) -> Scorer:
        """Loaded on first use, so constructing the rung costs nothing.

        Rung 1 pays no torch import to run, and `--rung bm25` must stay that
        way even though both rungs live behind the same CLI.
        """
        if self._score is None:
            # Imported here rather than at module scope: `faultloc.reranking`
            # needs this module's `RerankerSpec`, so the two would cycle.
            from faultloc.reranking import DEFAULT_RERANKER, load_reranker

            self._score = load_reranker(self.spec or DEFAULT_RERANKER)
        return self._score

    def predict(self, instance: Instance) -> Prediction:
        started = time.perf_counter()

        base = self.candidates.predict(instance)
        if not base.ranked_files:
            return self._prediction(
                instance, (), StopCondition.NO_CANDIDATES, started, base.cost_usd
            )

        head = base.ranked_files[: self.top_k]
        tail = base.ranked_files[self.top_k :]

        chunks = self.evidence(instance, head)
        pairs = [
            (instance.issue_text, "\n".join(part for part in (path, chunks.get(path)) if part))
            for path in head
        ]
        scores = self.score(pairs)

        # Ties break by path, as at every rung: a model returning the same
        # score twice must not leave the order to whatever `sorted` saw first.
        reordered = tuple(
            path
            for _score, path in sorted(
                zip((-s for s in scores), head, strict=True),
            )
        )

        return self._prediction(
            instance, reordered + tail, StopCondition.ANSWERED, started, base.cost_usd
        )

    def _prediction(
        self,
        instance: Instance,
        paths: tuple[str, ...],
        stop_condition: str,
        started: float,
        cost_usd: float,
    ) -> Prediction:
        return Prediction(
            instance_id=instance.instance_id,
            rung=self.name,
            ranked_files=paths,
            stop_condition=stop_condition,
            latency_s=time.perf_counter() - started,
            # Local weights add nothing, so this is whatever the candidate
            # supplier spent -- currently zero. Carried rather than hard-coded
            # so a priced retriever underneath could never be reported as free.
            cost_usd=cost_usd,
        )
