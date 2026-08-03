"""Rung 1: BM25 over whole files.

The floor of the ladder. No model calls, no embeddings, no chunking -- the
crudest thing that could work, so that every rung above it has a number to beat.

Not a straw man. Issue reports are written by programmers and routinely quote
identifiers, file paths, and stack traces verbatim, which is exactly the
situation lexical matching is good at. If later rungs struggle to beat this,
ADR-0003 says that is a finding to publish rather than a bug to fix.
"""

from __future__ import annotations

import time

from rank_bm25 import BM25Okapi

from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.tokenize import tokenize, tokenize_path


class Bm25Rung:
    """Whole-file lexical retrieval at the instance's base commit.

    One document per source file. Chunking is rung 2's variable (locked
    decision #6); introducing it here would blur the delta that measures rung 2.
    """

    name = "bm25"

    def __init__(self, store: RepoStore | None = None) -> None:
        self.store = store or RepoStore()
        # Tokens keyed by blob SHA. Across the Verified Set the same file
        # content appears about 21 times, so this turns ~927k tokenisations
        # into ~43k. Blob SHAs are content hashes, so an entry is never wrong.
        self._tokens_by_blob: dict[str, list[str]] = {}

    def predict(self, instance: Instance) -> Prediction:
        started = time.perf_counter()

        files = self.store.list_source_files(instance.repo, instance.base_commit)
        if not files:
            return self._prediction(instance, (), StopCondition.NO_CANDIDATES, started)

        documents = self._documents(instance.repo, files)
        scores = BM25Okapi(documents).get_scores(tokenize(instance.issue_text))

        # Sort by descending score, breaking ties by path. Without the tiebreak
        # the ranking would depend on the enumeration order of equally-scoring
        # files, and "same instance, same ranking" would quietly stop holding.
        ranked = sorted(
            zip([f.path for f in files], scores, strict=True),
            key=lambda pair: (-pair[1], pair[0]),
        )
        paths = tuple(path for path, _score in ranked)

        return self._prediction(instance, paths, StopCondition.ANSWERED, started)

    def _documents(self, repo: str, files: tuple) -> list[list[str]]:
        """Token lists for each file, reusing work across identical contents."""
        wanted = [f.blob for f in files if f.blob not in self._tokens_by_blob]
        if wanted:
            for blob, text in self.store.read_blobs(repo, wanted).items():
                self._tokens_by_blob[blob] = tokenize(text)

        return [tokenize_path(f.path) + self._tokens_by_blob.get(f.blob, []) for f in files]

    @staticmethod
    def _prediction(
        instance: Instance,
        paths: tuple[str, ...],
        stop_condition: str,
        started: float,
    ) -> Prediction:
        return Prediction(
            instance_id=instance.instance_id,
            rung="bm25",
            ranked_files=paths,
            stop_condition=stop_condition,
            latency_s=time.perf_counter() - started,
            cost_usd=0.0,
        )
