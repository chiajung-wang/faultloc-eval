"""Tests for rung 2.

No model is loaded and no index is built: the rung takes both an encoder and
an index, so the tests supply a fake encoder and write vectors directly. What
is under test is the rung contract -- determinism, stop conditions, the shared
aggregation rule, and the refusal to build an index it was only meant to read.

Retrieval quality is not tested here, for the same reason it is not tested at
rung 1: a two-file fixture cannot say anything about ranking. Quality is Top-1
on the dev split, measured by the scorer.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import Fixture

from faultloc.dataset.models import Instance
from faultloc.embedding import EmbeddingIndex, IndexMissingError, ModelSpec
from faultloc.rungs import StopCondition
from faultloc.rungs.embed import EmbedRung

SPEC = ModelSpec(name="fake/model", revision="f" * 40, dimensions=2, query_prefix="QUERY: ")


def instance(repo_fixture: Fixture, issue_text: str = "core is broken") -> Instance:
    return Instance(
        instance_id="acme__widget-1",
        repo=repo_fixture.repo,
        base_commit=repo_fixture.first,
        issue_text=issue_text,
        ground_truth_files=("pkg/core.py",),
    )


def unit(x: float, y: float) -> np.ndarray:
    vector = np.asarray([[x, y]], dtype=np.float32)
    return vector / np.linalg.norm(vector)


@pytest.fixture
def index(tmp_path) -> EmbeddingIndex:
    return EmbeddingIndex(root=tmp_path / "index", spec=SPEC)


@pytest.fixture
def seeded(repo: Fixture, index: EmbeddingIndex) -> EmbeddingIndex:
    """Every source blob gets one vector; `pkg/core.py` points at the query."""
    index.ensure_compatible()
    for file in repo.store.list_source_files(repo.repo, repo.first):
        aligned = file.path == "pkg/core.py"
        index.write(file.blob, unit(1.0, 0.0) if aligned else unit(0.0, 1.0))
    return index


def encoder(vector: np.ndarray):
    def encode(texts):
        return np.repeat(vector, len(texts), axis=0)

    return encode


class TestContract:
    def test_ranks_files_by_similarity(self, repo: Fixture, seeded: EmbeddingIndex) -> None:
        rung = EmbedRung(repo.store, index=seeded, encode=encoder(unit(1.0, 0.0)), spec=SPEC)
        prediction = rung.predict(instance(repo))

        assert prediction.stop_condition == StopCondition.ANSWERED
        assert prediction.ranked_files[0] == "pkg/core.py"

    def test_never_emits_a_file_twice(self, repo: Fixture, seeded: EmbeddingIndex) -> None:
        rung = EmbedRung(repo.store, index=seeded, encode=encoder(unit(1.0, 0.0)), spec=SPEC)
        ranked = rung.predict(instance(repo)).ranked_files

        assert len(set(ranked)) == len(ranked)

    def test_candidate_set_matches_the_lexical_rungs(
        self, repo: Fixture, seeded: EmbeddingIndex
    ) -> None:
        """Same files considered, or the rung-1 to rung-2 delta measures
        candidate selection rather than the matching function."""
        rung = EmbedRung(repo.store, index=seeded, encode=encoder(unit(1.0, 0.0)), spec=SPEC)
        ranked = set(rung.predict(instance(repo)).ranked_files)

        assert "tests/test_core.py" not in ranked
        assert "README.md" not in ranked

    def test_is_deterministic(self, repo: Fixture, seeded: EmbeddingIndex) -> None:
        rung = EmbedRung(repo.store, index=seeded, encode=encoder(unit(1.0, 0.0)), spec=SPEC)
        target = instance(repo)

        assert rung.predict(target).ranked_files == rung.predict(target).ranked_files

    def test_ties_break_by_path(self, repo: Fixture, index: EmbeddingIndex) -> None:
        """Every file scoring identically must still order stably; otherwise
        the order follows git's enumeration and determinism holds by luck."""
        index.ensure_compatible()
        for file in repo.store.list_source_files(repo.repo, repo.first):
            index.write(file.blob, unit(1.0, 0.0))

        rung = EmbedRung(repo.store, index=index, encode=encoder(unit(1.0, 0.0)), spec=SPEC)
        ranked = rung.predict(instance(repo)).ranked_files

        assert ranked == tuple(sorted(ranked))

    def test_names_itself(self, repo: Fixture, seeded: EmbeddingIndex) -> None:
        rung = EmbedRung(repo.store, index=seeded, encode=encoder(unit(1.0, 0.0)), spec=SPEC)
        assert rung.predict(instance(repo)).rung == "embed"

    def test_reports_latency_and_zero_query_cost(
        self, repo: Fixture, seeded: EmbeddingIndex
    ) -> None:
        """The model runs locally, so a prediction spends nothing. Index cost
        is amortised and reported by `faultloc index` -- collapsing the two
        into one figure would answer neither question."""
        rung = EmbedRung(repo.store, index=seeded, encode=encoder(unit(1.0, 0.0)), spec=SPEC)
        prediction = rung.predict(instance(repo))

        assert prediction.latency_s > 0
        assert prediction.cost_usd == 0.0


class TestReadsButNeverBuilds:
    def test_missing_index_fails_with_the_fix(self, repo: Fixture, index: EmbeddingIndex) -> None:
        """An unbuilt index must stop the run, not trigger an hour of silent
        embedding inside the prediction loop."""
        rung = EmbedRung(repo.store, index=index, encode=encoder(unit(1.0, 0.0)), spec=SPEC)

        with pytest.raises(IndexMissingError, match="faultloc index"):
            rung.predict(instance(repo))

    def test_the_encoder_is_not_loaded_until_used(self, repo: Fixture) -> None:
        """Constructing a rung must not import torch. `--rung bm25` shares this
        CLI and has to stay runnable without the optional extra."""
        rung = EmbedRung(repo.store, index=EmbeddingIndex(spec=SPEC))
        assert rung._encode is None


class TestQuery:
    def test_applies_the_model_query_prefix(self, repo: Fixture, seeded: EmbeddingIndex) -> None:
        """bge is trained asymmetrically; dropping the instruction costs
        retrieval quality silently."""
        seen: list[str] = []

        def encode(texts):
            seen.extend(texts)
            return np.repeat(unit(1.0, 0.0), len(texts), axis=0)

        EmbedRung(repo.store, index=seeded, encode=encode, spec=SPEC).predict(
            instance(repo, "labels are sideways")
        )

        assert seen == ["QUERY: labels are sideways"]

    def test_embeds_a_repeated_issue_once(self, repo: Fixture, seeded: EmbeddingIndex) -> None:
        calls: list[int] = []

        def encode(texts):
            calls.append(len(texts))
            return np.repeat(unit(1.0, 0.0), len(texts), axis=0)

        rung = EmbedRung(repo.store, index=seeded, encode=encode, spec=SPEC)
        target = instance(repo)
        rung.predict(target)
        rung.predict(target)

        assert len(calls) == 1
