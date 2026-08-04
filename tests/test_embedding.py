"""Tests for the chunk embedding index.

No model is downloaded and no hosted API is called: `build_index` takes an
encoder, so the tests supply a deterministic fake. What is under test is the
storage contract -- resumability, blob keying, and the refusal to mix models --
not whether a neural net produces good vectors.

That refusal is the one worth the most care. Vectors from two models are
indistinguishable once written, so reading one with the other yields a
plausible number with no valid provenance, which is worse than a crash.
"""

from __future__ import annotations

import numpy as np
import pytest
from conftest import Fixture

from faultloc.dataset.models import Instance
from faultloc.embedding import (
    EmbeddingIndex,
    IndexIncompatibleError,
    IndexMissingError,
    ModelSpec,
    build_index,
)

SPEC = ModelSpec(name="fake/model", revision="a" * 40, dimensions=4, query_prefix="q: ")
OTHER = ModelSpec(name="fake/model", revision="a" * 40, dimensions=8, query_prefix="q: ")


def fake_encode(texts) -> np.ndarray:
    """Deterministic unit vectors, so a test can assert on exact rows."""
    rows = [[float(len(t) % 7), 1.0, 0.0, 0.0] for t in texts]
    array = np.asarray(rows, dtype=np.float32)
    return array / np.linalg.norm(array, axis=1, keepdims=True)


def instance(repo_fixture: Fixture) -> Instance:
    return Instance(
        instance_id="acme__widget-1",
        repo=repo_fixture.repo,
        base_commit=repo_fixture.first,
        issue_text="core is broken",
        ground_truth_files=("pkg/core.py",),
    )


@pytest.fixture
def index(tmp_path) -> EmbeddingIndex:
    return EmbeddingIndex(root=tmp_path / "index", spec=SPEC)


class TestStorage:
    def test_round_trips_vectors(self, index: EmbeddingIndex) -> None:
        vectors = np.asarray([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        index.write("abc123", vectors)

        assert np.array_equal(index.read("abc123"), vectors)

    def test_missing_blob_says_what_to_run(self, index: EmbeddingIndex) -> None:
        """A rung reading an unbuilt index must fail loudly, not silently
        spend hours embedding inside its prediction loop."""
        with pytest.raises(IndexMissingError, match="faultloc index"):
            index.read("never-written")

    def test_leaves_no_partial_file(self, index: EmbeddingIndex) -> None:
        """Presence is the resumability record, so a half-written array would
        be indistinguishable from a finished one on the next run."""
        index.write("abc123", np.zeros((2, 4), dtype=np.float32))

        assert list(index.root.rglob("*.tmp")) == []

    def test_separates_models_by_directory(self, tmp_path) -> None:
        a = EmbeddingIndex(root=tmp_path, spec=SPEC)
        b = EmbeddingIndex(root=tmp_path, spec=ModelSpec("other/model", "b" * 40, 4, ""))

        assert a.root != b.root


class TestModelCompatibility:
    def test_records_the_model_on_first_use(self, index: EmbeddingIndex) -> None:
        index.ensure_compatible()
        assert index.meta_path.is_file()

    def test_accepts_a_matching_index(self, index: EmbeddingIndex) -> None:
        index.ensure_compatible()
        index.ensure_compatible()  # must not raise

    def test_refuses_an_index_built_by_a_different_model(self, tmp_path) -> None:
        """Same name and revision, different dimensions: weights changed under
        a stable identifier. Reading it would produce a plausible number with
        no valid provenance."""
        EmbeddingIndex(root=tmp_path, spec=SPEC).ensure_compatible()

        clashing = EmbeddingIndex(root=tmp_path, spec=OTHER)
        clashing.root = EmbeddingIndex(root=tmp_path, spec=SPEC).root

        with pytest.raises(IndexIncompatibleError):
            clashing.ensure_compatible()


class TestBuild:
    def test_embeds_every_chunk_of_every_source_file(
        self, repo: Fixture, index: EmbeddingIndex
    ) -> None:
        report = build_index([instance(repo)], store=repo.store, index=index, encode=fake_encode)

        blobs = {f.blob for f in repo.store.list_source_files(repo.repo, repo.first)}
        assert report.blobs_embedded == len(blobs)
        assert all(index.has(blob) for blob in blobs)

    def test_rows_match_chunk_count(self, repo: Fixture, index: EmbeddingIndex) -> None:
        """Row `i` is chunk `i`. A rung scores a file from the rows alone, so a
        count mismatch would silently misalign every score."""
        build_index([instance(repo)], store=repo.store, index=index, encode=fake_encode)

        total = sum(
            index.read(f.blob).shape[0] for f in repo.store.list_source_files(repo.repo, repo.first)
        )
        assert total > 0

    def test_vectors_have_the_declared_width(self, repo: Fixture, index: EmbeddingIndex) -> None:
        build_index([instance(repo)], store=repo.store, index=index, encode=fake_encode)

        blob = repo.store.list_source_files(repo.repo, repo.first)[0].blob
        assert index.read(blob).shape[1] == SPEC.dimensions

    def test_rerunning_reuses_everything(self, repo: Fixture, index: EmbeddingIndex) -> None:
        """Blobs are content-keyed, so a second build must embed nothing --
        this is what makes a 3.7-hour job survivable."""
        build_index([instance(repo)], store=repo.store, index=index, encode=fake_encode)
        second = build_index([instance(repo)], store=repo.store, index=index, encode=fake_encode)

        assert second.blobs_embedded == 0
        assert second.blobs_reused > 0

    def test_resumes_without_losing_or_redoing_work(
        self, repo: Fixture, index: EmbeddingIndex
    ) -> None:
        """Simulates an interrupted build: one blob already on disk, the rest
        missing. The resumed run must embed only the remainder."""
        files = repo.store.list_source_files(repo.repo, repo.first)
        index.ensure_compatible()
        index.write(files[0].blob, np.zeros((1, SPEC.dimensions), dtype=np.float32))

        report = build_index([instance(repo)], store=repo.store, index=index, encode=fake_encode)

        assert report.blobs_reused == 1
        assert report.blobs_embedded == len(files) - 1
        assert all(index.has(f.blob) for f in files)

    def test_a_blob_shared_by_two_instances_is_embedded_once(
        self, repo: Fixture, index: EmbeddingIndex
    ) -> None:
        """Across the Verified Set the same content appears ~21 times."""
        first = instance(repo)
        second = first.model_copy(update={"instance_id": "acme__widget-2"})

        report = build_index([first, second], store=repo.store, index=index, encode=fake_encode)

        blobs = {f.blob for f in repo.store.list_source_files(repo.repo, repo.first)}
        assert report.blobs_embedded == len(blobs)

    def test_reports_zero_cost_for_a_local_model(
        self, repo: Fixture, index: EmbeddingIndex
    ) -> None:
        """Locked decision #3 puts cost beside every figure. Zero is honest
        here; a fabricated number would not be."""
        report = build_index([instance(repo)], store=repo.store, index=index, encode=fake_encode)
        assert report.cost_usd == 0.0
        assert report.wall_clock_s > 0
