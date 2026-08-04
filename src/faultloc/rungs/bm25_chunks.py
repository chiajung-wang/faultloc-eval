"""The ablation rung: BM25 over AST Chunks.

Rung 2 changes two things at once -- word matching becomes embedding similarity,
*and* whole files become chunks. A win over rung 1 is therefore unattributable:
it could be entirely a chunking effect, obtainable with no model and no cost.

This rung changes only the second. Same tokeniser, same scorer, same instances
as rung 1, so the delta between them prices chunking alone and whatever is left
over belongs to the embeddings. It is built before rung 2 rather than after so
that the control cannot be skipped once the interesting number exists.

Not a rung of the ladder in ADR-0003's sense -- nothing is stacked on it. It is
a measurement instrument that happens to satisfy the same contract.
"""

from __future__ import annotations

import time

from rank_bm25 import BM25Okapi

from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.chunks import aggregate_by_file, chunk_source
from faultloc.rungs.tokenize import tokenize, tokenize_path


class Bm25ChunksRung:
    """Lexical retrieval over chunks, aggregated back to files."""

    name = "bm25-chunks"

    def __init__(self, store: RepoStore | None = None) -> None:
        self.store = store or RepoStore()
        # Chunk tokens keyed by blob SHA, the same content hash rung 1 keys its
        # token cache on. Parsing is markedly more expensive than tokenising, so
        # the ~21x content reuse across the Verified Set matters more here.
        # Path tokens are added per file rather than cached, because one blob
        # can appear at several paths and a cached entry must not depend on
        # where it was first seen.
        self._chunks_by_blob: dict[str, list[list[str]]] = {}

    def predict(self, instance: Instance) -> Prediction:
        started = time.perf_counter()

        files = self.store.list_source_files(instance.repo, instance.base_commit)
        if not files:
            return self._prediction(instance, (), StopCondition.NO_CANDIDATES, started)

        documents: list[list[str]] = []
        owners: list[str] = []
        for path, tokens in self._documents(instance.repo, files):
            documents.append(tokens)
            owners.append(path)

        if not documents:
            return self._prediction(instance, (), StopCondition.NO_CANDIDATES, started)

        scores = BM25Okapi(documents).get_scores(tokenize(instance.issue_text))

        by_file: dict[str, list[float]] = {}
        for path, score in zip(owners, scores, strict=True):
            by_file.setdefault(path, []).append(score)

        # Aggregate first, then sort. Ties break by path, as at rung 1: without
        # it the order would follow git's enumeration and determinism would hold
        # only by luck.
        ranked = sorted(
            ((path, aggregate_by_file(chunk_scores)) for path, chunk_scores in by_file.items()),
            key=lambda pair: (-pair[1], pair[0]),
        )

        return self._prediction(
            instance,
            tuple(path for path, _score in ranked),
            StopCondition.ANSWERED,
            started,
        )

    def _documents(self, repo: str, files: tuple) -> list[tuple[str, list[str]]]:
        """One (path, tokens) pair per chunk, reusing work across identical files."""
        wanted = [f.blob for f in files if f.blob not in self._chunks_by_blob]
        if wanted:
            for blob, text in self.store.read_blobs(repo, wanted).items():
                self._chunks_by_blob[blob] = [tokenize(c.text) for c in chunk_source(text)]

        documents: list[tuple[str, list[str]]] = []
        for file in files:
            path_tokens = tokenize_path(file.path)
            for chunk_tokens in self._chunks_by_blob.get(file.blob, []):
                documents.append((file.path, path_tokens + chunk_tokens))
        return documents

    @staticmethod
    def _prediction(
        instance: Instance,
        paths: tuple[str, ...],
        stop_condition: str,
        started: float,
    ) -> Prediction:
        return Prediction(
            instance_id=instance.instance_id,
            rung="bm25-chunks",
            ranked_files=paths,
            stop_condition=stop_condition,
            latency_s=time.perf_counter() - started,
            cost_usd=0.0,
        )
