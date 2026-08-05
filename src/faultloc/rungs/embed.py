"""Rung 2: dense retrieval over AST Chunks.

The first rung with a model in it. The issue text is embedded once, scored
against every chunk vector in the instance's repository at its base commit, and
the chunk scores are aggregated to files by the same rule the lexical rungs use
(`aggregate_by_file`). That shared rule is what makes the rung-1 to rung-2 delta
mean anything: if the two aggregated differently, the delta would measure
aggregation rather than the matching function.

**This rung reads the index; it never builds it.** Embedding a split takes about
an hour, and a rung that quietly did that inside its prediction loop is the bug
M1 already found once. A missing blob raises `IndexMissingError` naming the
command to run.

Similarity is a dot product because vectors are unit-normalised at write time
(`faultloc.embedding`). Nothing here re-normalises, so a future change that
stored unnormalised vectors would show up as a wrong number rather than a
silently different metric -- worth knowing, and the reason normalisation lives
at the writer.
"""

from __future__ import annotations

import time

import numpy as np

from faultloc.dataset.models import Instance
from faultloc.embedding import DEFAULT_MODEL, EmbeddingIndex, Encoder, ModelSpec
from faultloc.repos import RepoStore
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.chunks import aggregate_by_file


class EmbedRung:
    """Dense retrieval against the cached chunk index."""

    name = "embed"

    def __init__(
        self,
        store: RepoStore | None = None,
        *,
        index: EmbeddingIndex | None = None,
        encode: Encoder | None = None,
        spec: ModelSpec = DEFAULT_MODEL,
    ) -> None:
        self.store = store or RepoStore()
        self.index = index or EmbeddingIndex(spec=spec)
        self.spec = spec
        self._encode = encode
        # Query vectors keyed by issue text. Instances are scored once each, so
        # this earns nothing today; it exists because rung 3 will re-score the
        # same issue against reordered candidates.
        self._queries: dict[str, np.ndarray] = {}

    @property
    def encode(self) -> Encoder:
        """Loaded on first use, so constructing the rung costs nothing.

        Rung 1 pays no torch import to run, and `--rung bm25` must stay that
        way even though both rungs live behind the same CLI.
        """
        if self._encode is None:
            from faultloc.embedding import load_encoder

            self._encode = load_encoder(self.spec)
        return self._encode

    def predict(self, instance: Instance) -> Prediction:
        started = time.perf_counter()

        files = self.store.list_source_files(instance.repo, instance.base_commit)
        if not files:
            return self._prediction(instance, (), StopCondition.NO_CANDIDATES, started)

        query = self._query_vector(instance.issue_text)

        by_file: dict[str, list[float]] = {}
        for file in files:
            vectors = self.index.read(file.blob)
            if vectors.size == 0:
                continue
            by_file.setdefault(file.path, []).extend((vectors @ query).tolist())

        if not by_file:
            return self._prediction(instance, (), StopCondition.NO_CANDIDATES, started)

        # Aggregate first, then sort, ties broken by path -- identical to the
        # lexical rungs. Without the tiebreak the order would follow git's
        # enumeration and determinism would hold only by luck.
        ranked = sorted(
            ((path, aggregate_by_file(scores)) for path, scores in by_file.items()),
            key=lambda pair: (-pair[1], pair[0]),
        )

        return self._prediction(
            instance,
            tuple(path for path, _score in ranked),
            StopCondition.ANSWERED,
            started,
        )

    def _query_vector(self, issue_text: str) -> np.ndarray:
        """Embed the issue, with the model's query instruction attached.

        bge models are trained asymmetrically: the query carries an instruction
        and the document carries none. Omitting it costs retrieval quality
        quietly, which is why it is a field on `ModelSpec` and applied here
        rather than left to a caller to remember.
        """
        cached = self._queries.get(issue_text)
        if cached is None:
            cached = np.asarray(self.encode([self.spec.query_prefix + issue_text])[0])
            self._queries[issue_text] = cached
        return cached

    def _prediction(
        self,
        instance: Instance,
        paths: tuple[str, ...],
        stop_condition: str,
        started: float,
    ) -> Prediction:
        return Prediction(
            instance_id=instance.instance_id,
            rung=self.name,
            ranked_files=paths,
            stop_condition=stop_condition,
            latency_s=time.perf_counter() - started,
            # Query embedding runs locally, so a prediction spends nothing.
            # The index cost is amortised and reported by `faultloc index`;
            # collapsing the two into one figure would answer neither question.
            cost_usd=0.0,
        )
