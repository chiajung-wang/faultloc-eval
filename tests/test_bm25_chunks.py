"""Tests for the BM25-over-chunks ablation rung.

Like rung 1's tests, these check the *contract* -- determinism, stop conditions,
the shape of the answer, and the blob cache -- not retrieval quality. A
two-file fixture cannot say anything about ranking: BM25's IDF term is zero for
a term appearing in half the corpus, so a toy breaks the statistics rather than
the code. Quality is measured by the scorer on real instances.

The one property tested here that rung 1 has no equivalent for: the rung must
rank *files*, not chunks, and must never emit a file twice however many of its
chunks matched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import Fixture, git

from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.rungs import StopCondition, bm25_chunks
from faultloc.rungs.bm25 import Bm25Rung
from faultloc.rungs.bm25_chunks import Bm25ChunksRung


@pytest.fixture
def multi_chunk(tmp_path: Path) -> Fixture:
    """A repo whose one interesting file holds two unrelated definitions.

    The shared `repo` fixture gives every file a single chunk, which cannot
    distinguish "returns the file's best chunk" from "returns its only chunk".

    The filler modules are not padding. BM25's IDF is zero for a term appearing
    in half the corpus, so in a two-chunk repository every score ties and the
    argmax is whatever came first -- the caveat this module's docstring already
    records. Enough distinct chunks and the discriminating term earns its
    weight back.
    """
    work = tmp_path / "work"
    (work / "pkg").mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=work)
    git("config", "user.email", "t@example.com", cwd=work)
    git("config", "user.name", "Test", cwd=work)

    (work / "pkg" / "core.py").write_text(
        "def parse_header(stream):\n"
        '    """Read the leading bytes of a stream."""\n'
        "    return stream.read(8)\n"
        "\n"
        "def align_widget(widget):\n"
        '    """Correct a widget alignment."""\n'
        "    return widget.align()\n"
    )
    for n, subject in enumerate(("socket", "cursor", "palette", "buffer", "registry", "clock")):
        (work / "pkg" / f"mod_{n}.py").write_text(
            f"def open_{subject}(target):\n"
            f'    """Open a {subject} for the given target."""\n'
            f"    return target.{subject}\n"
        )
    git("add", "-A", cwd=work)
    git("commit", "-qm", "first", cwd=work)
    head = git("rev-parse", "HEAD", cwd=work)

    root = tmp_path / "repos"
    root.mkdir()
    subprocess.run(
        ["git", "clone", "--bare", "-q", str(work), str(root / "acme__widget.git")],
        check=True,
    )

    return Fixture(
        store=RepoStore(root=root, cache_root=tmp_path / "cache"),
        first=head,
        second=head,
    )


def instance(repo_fixture: Fixture, issue_text: str, commit: str | None = None) -> Instance:
    return Instance(
        instance_id="acme__widget-1",
        repo=repo_fixture.repo,
        base_commit=commit or repo_fixture.first,
        issue_text=issue_text,
        ground_truth_files=("pkg/core.py",),
    )


class TestBm25ChunksRung:
    def test_ranks_files_not_chunks(self, repo: Fixture) -> None:
        prediction = Bm25ChunksRung(repo.store).predict(instance(repo, "core is broken"))

        assert prediction.stop_condition == StopCondition.ANSWERED
        assert set(prediction.ranked_files) == {"pkg/core.py", "pkg/util.py"}

    def test_never_emits_a_file_twice(self, repo: Fixture) -> None:
        """A multi-chunk file must collapse to one entry. A repeat would inflate
        Recall@k without finding anything new -- `Prediction` rejects it, so
        this asserts the aggregation ran at all."""
        prediction = Bm25ChunksRung(repo.store).predict(instance(repo, "first"))
        assert len(set(prediction.ranked_files)) == len(prediction.ranked_files)

    def test_candidate_set_matches_rung_one(self, repo: Fixture) -> None:
        """The ablation changes the index unit and nothing else. A different set
        of candidate files would confound the delta it exists to measure."""
        query = "anything"
        chunked = Bm25ChunksRung(repo.store).predict(instance(repo, query))
        whole = Bm25Rung(repo.store).predict(instance(repo, query))

        assert set(chunked.ranked_files) == set(whole.ranked_files)

    def test_excludes_tests_and_docs_from_candidates(self, repo: Fixture) -> None:
        prediction = Bm25ChunksRung(repo.store).predict(instance(repo, "anything"))

        assert "tests/test_core.py" not in prediction.ranked_files
        assert "README.md" not in prediction.ranked_files

    def test_is_deterministic(self, repo: Fixture) -> None:
        rung = Bm25ChunksRung(repo.store)
        target = instance(repo, "shared value")

        assert rung.predict(target).ranked_files == rung.predict(target).ranked_files

    def test_ties_break_by_path_not_enumeration_order(self, repo: Fixture) -> None:
        prediction = Bm25ChunksRung(repo.store).predict(instance(repo, "zzzz nonexistent term"))
        assert prediction.ranked_files == tuple(sorted(prediction.ranked_files))

    def test_sees_the_tree_at_the_pinned_commit(self, repo: Fixture) -> None:
        rung = Bm25ChunksRung(repo.store)

        first = rung.predict(instance(repo, "new", commit=repo.first))
        second = rung.predict(instance(repo, "new", commit=repo.second))

        assert "pkg/added.py" not in first.ranked_files
        assert "pkg/added.py" in second.ranked_files

    def test_reports_latency_and_zero_cost(self, repo: Fixture) -> None:
        prediction = Bm25ChunksRung(repo.store).predict(instance(repo, "core"))
        assert prediction.latency_s > 0
        assert prediction.cost_usd == 0.0

    def test_names_itself_distinctly_from_rung_one(self, repo: Fixture) -> None:
        """Results are labelled by rung. Two rows sharing a name would be
        indistinguishable in the log the whole ablation is published in."""
        assert Bm25ChunksRung(repo.store).predict(instance(repo, "core")).rung == "bm25-chunks"


class TestBlobReuse:
    def test_parses_each_distinct_blob_once(self, repo: Fixture) -> None:
        """Parsing costs more than tokenising, so the ~21x content reuse across
        the Verified Set matters more here than at rung 1."""
        rung = Bm25ChunksRung(repo.store)
        rung.predict(instance(repo, "x", commit=repo.first))
        after_first = dict(rung._chunks_by_blob)

        rung.predict(instance(repo, "x", commit=repo.second))

        util_blob = next(
            f.blob for f in repo.store.list_files(repo.repo, repo.first) if f.path == "pkg/util.py"
        )
        assert rung._chunks_by_blob[util_blob] is after_first[util_blob]

    def test_cached_chunks_do_not_carry_the_path_they_were_first_seen_at(
        self, repo: Fixture
    ) -> None:
        """One blob can appear at several paths. If path tokens were cached with
        the chunk, the second path would be scored on the first one's tokens."""
        rung = Bm25ChunksRung(repo.store)
        rung.predict(instance(repo, "x"))

        blob = next(
            f.blob for f in repo.store.list_files(repo.repo, repo.first) if f.path == "pkg/core.py"
        )
        assert not any("pkg/core.py" in tokens for tokens in rung._chunks_by_blob[blob])


class TestEvidenceChunks:
    """The Evidence Chunk: the chunk a file scored as, kept rather than
    discarded so rung 2.6 and rung 3 can show a model *why* a file is a
    candidate."""

    def test_returns_the_text_that_was_scored(self, repo: Fixture) -> None:
        rung = Bm25ChunksRung(repo.store)
        evidence = rung.evidence(instance(repo, "core is broken"), ("pkg/core.py",))

        assert "first" in evidence["pkg/core.py"]

    def test_picks_the_chunk_the_file_scored_as(self, multi_chunk: Fixture) -> None:
        """The crux. A file with several definitions must surrender the one the
        retriever matched on, not whichever happened to be parsed first --
        otherwise the model is shown code the retriever never looked at."""
        rung = Bm25ChunksRung(multi_chunk.store, include_bodies=True)
        evidence = rung.evidence(instance(multi_chunk, "widget alignment"), ("pkg/core.py",))

        assert "align_widget" in evidence["pkg/core.py"]
        assert "parse_header" not in evidence["pkg/core.py"]

    def test_asking_for_an_unknown_path_yields_nothing_rather_than_raising(
        self, repo: Fixture
    ) -> None:
        """A candidate list can name a path the lexical rung never ranked --
        the dense retriever contributes to the union too. Dropping it here
        would shrink the list the ceiling was measured on."""
        rung = Bm25ChunksRung(repo.store)
        evidence = rung.evidence(instance(repo, "x"), ("pkg/core.py", "pkg/ghost.py"))

        assert evidence["pkg/ghost.py"] == ""

    def test_scores_the_repository_once_for_a_prediction_and_its_evidence(
        self, repo: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`HybridRung` asks for the ranking and rung 2.6 then asks for the
        Evidence Chunks of the same instance. Running BM25 over the repository
        twice for one prediction is pure waste, and at 244 instances it is
        minutes."""
        built = []
        original = bm25_chunks.BM25Okapi
        monkeypatch.setattr(
            bm25_chunks, "BM25Okapi", lambda corpus: built.append(1) or original(corpus)
        )

        rung = Bm25ChunksRung(repo.store)
        subject = instance(repo, "core is broken")

        rung.predict(subject)
        rung.evidence(subject, ("pkg/core.py",))

        assert len(built) == 1

    def test_a_second_instance_is_scored_afresh(
        self, repo: Fixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The memo holds one instance. If it keyed on nothing, the second
        instance would be handed the first one's evidence -- a wrong answer
        that looks like a working cache."""
        built = []
        original = bm25_chunks.BM25Okapi
        monkeypatch.setattr(
            bm25_chunks, "BM25Okapi", lambda corpus: built.append(1) or original(corpus)
        )

        rung = Bm25ChunksRung(repo.store)
        rung.predict(instance(repo, "core is broken"))
        rung.predict(instance(repo, "util is broken", commit=repo.second))

        assert len(built) == 2
