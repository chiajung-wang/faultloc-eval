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
from collections.abc import Sequence

from rank_bm25 import BM25Okapi

from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.chunks import aggregate_by_file, chunk_source
from faultloc.rungs.tokenize import tokenize, tokenize_path


class Bm25ChunksRung:
    """Lexical retrieval over chunks, aggregated back to files.

    `include_bodies` is the second ablation (issue 06). Issue 01 measured
    chunking costing ~9pp of Recall@5 and could not say which half did it,
    because "chunking" changed two things at once: the index unit shrank to a
    definition, *and* the body stopped being indexed. This flag moves only the
    second, so the two are finally separable.
    """

    def __init__(
        self,
        store: RepoStore | None = None,
        *,
        include_bodies: bool = False,
    ) -> None:
        self.store = store or RepoStore()
        self.include_bodies = include_bodies
        self.name = "bm25-chunks-bodies" if include_bodies else "bm25-chunks"
        # Chunk tokens keyed by blob SHA, the same content hash rung 1 keys its
        # token cache on. Parsing is markedly more expensive than tokenising, so
        # the ~21x content reuse across the Verified Set matters more here.
        # Path tokens are added per file rather than cached, because one blob
        # can appear at several paths and a cached entry must not depend on
        # where it was first seen.
        self._chunks_by_blob: dict[str, list[list[str]]] = {}
        # One instance's scoring, kept so `predict` and `evidence` do not each
        # run BM25 over the repository. Rung 2.6 asks for both, in that order.
        self._scored: tuple[Instance, tuple[str, ...], dict[str, int]] | None = None

    def predict(self, instance: Instance) -> Prediction:
        started = time.perf_counter()

        ranked, _evidence = self._score(instance)
        stop = StopCondition.ANSWERED if ranked else StopCondition.NO_CANDIDATES

        return self._prediction(instance, ranked, stop, started)

    def evidence(self, instance: Instance, paths: Sequence[str]) -> dict[str, str]:
        """The Evidence Chunk for each path: the text the file scored as.

        Chunk Aggregation scores a file as its best chunk and then keeps only
        the number. Rung 2.6 and rung 3 show a model *why* a file is a
        candidate, and showing it a chunk the retriever never matched on would
        make the two rungs disagree about what a candidate is.

        A path the lexical rung never ranked maps to the empty string rather
        than raising: the dense retriever contributes to the union too, and
        dropping its paths here would shrink the list issue 01 measured the
        ceiling on.
        """
        _ranked, best = self._score(instance)
        wanted = {path for path in paths if path in best}
        if not wanted:
            return dict.fromkeys(paths, "")

        blobs = {
            file.path: file.blob
            for file in self.store.list_source_files(instance.repo, instance.base_commit)
            if file.path in wanted
        }
        texts = self.store.read_blobs(instance.repo, sorted(set(blobs.values())))

        found: dict[str, str] = {}
        for path in paths:
            source = texts.get(blobs.get(path, ""), "")
            chunks = chunk_source(source, include_bodies=self.include_bodies) if source else ()
            index = best.get(path, -1)
            found[path] = chunks[index].text if 0 <= index < len(chunks) else ""
        return found

    def _score(self, instance: Instance) -> tuple[tuple[str, ...], dict[str, int]]:
        """Ranked paths, and the index of the chunk each file scored as.

        Memoised for one instance, compared by value: a memo that ignored which
        instance it held would hand the second one the first one's evidence,
        which is a wrong answer that looks like a working cache.
        """
        if self._scored is not None and self._scored[0] == instance:
            return self._scored[1], self._scored[2]

        ranked, best = self._compute(instance)
        self._scored = (instance, ranked, best)
        return ranked, best

    def _compute(self, instance: Instance) -> tuple[tuple[str, ...], dict[str, int]]:
        files = self.store.list_source_files(instance.repo, instance.base_commit)
        if not files:
            return (), {}

        documents: list[list[str]] = []
        owners: list[str] = []
        positions: list[int] = []
        for path, position, tokens in self._documents(instance.repo, files):
            documents.append(tokens)
            owners.append(path)
            positions.append(position)

        if not documents:
            return (), {}

        scores = BM25Okapi(documents).get_scores(tokenize(instance.issue_text))

        by_file: dict[str, list[float]] = {}
        best: dict[str, tuple[float, int]] = {}
        for path, position, score in zip(owners, positions, scores, strict=True):
            by_file.setdefault(path, []).append(score)
            # Ties keep the earlier chunk, so the Evidence Chunk is as
            # deterministic as the ranking it accompanies.
            if path not in best or score > best[path][0]:
                best[path] = (score, position)

        # Aggregate first, then sort. Ties break by path, as at rung 1: without
        # it the order would follow git's enumeration and determinism would hold
        # only by luck.
        ranked = sorted(
            ((path, aggregate_by_file(chunk_scores)) for path, chunk_scores in by_file.items()),
            key=lambda pair: (-pair[1], pair[0]),
        )

        return (
            tuple(path for path, _score in ranked),
            {path: position for path, (_score, position) in best.items()},
        )

    def _documents(self, repo: str, files: tuple) -> list[tuple[str, int, list[str]]]:
        """One (path, chunk position, tokens) triple per chunk, reusing work
        across identical files.

        The position indexes into `chunk_source`'s output for that file, which
        is deterministic, so it is enough to recover the Evidence Chunk's text
        later without holding the whole corpus in memory.
        """
        wanted = [f.blob for f in files if f.blob not in self._chunks_by_blob]
        if wanted:
            for blob, text in self.store.read_blobs(repo, wanted).items():
                chunks = chunk_source(text, include_bodies=self.include_bodies)
                self._chunks_by_blob[blob] = [tokenize(c.text) for c in chunks]

        documents: list[tuple[str, int, list[str]]] = []
        for file in files:
            path_tokens = tokenize_path(file.path)
            for position, chunk_tokens in enumerate(self._chunks_by_blob.get(file.blob, [])):
                documents.append((file.path, position, path_tokens + chunk_tokens))
        return documents

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
            cost_usd=0.0,
        )
