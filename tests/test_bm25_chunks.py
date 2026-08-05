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

from conftest import Fixture

from faultloc.dataset.models import Instance
from faultloc.rungs import StopCondition
from faultloc.rungs.bm25 import Bm25Rung
from faultloc.rungs.bm25_chunks import Bm25ChunksRung


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
