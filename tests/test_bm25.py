"""Tests for rung 1 and the Prediction contract.

Rung 1 is the floor every later rung is measured against, so what is tested
here is mostly the *contract* -- determinism, stop conditions, the shape of the
answer -- rather than retrieval quality.

Ranking quality is deliberately *not* tested here, and the first attempt showed
why. BM25's IDF term is `log(N - n + 0.5) - log(n + 0.5)`, which is exactly zero
for a term appearing in half the corpus. With a two-file fixture every
discriminating term scores zero and the ranking is meaningless -- the toy breaks
the statistics rather than the code. Quality is measured by the scorer on real
instances with hundreds of candidates, which is the only place the number means
anything.
"""

from __future__ import annotations

import pytest
from conftest import Fixture

from faultloc.dataset.models import Instance
from faultloc.rungs import Prediction, StopCondition
from faultloc.rungs.bm25 import Bm25Rung


def instance(repo_fixture: Fixture, issue_text: str, commit: str | None = None) -> Instance:
    return Instance(
        instance_id="acme__widget-1",
        repo=repo_fixture.repo,
        base_commit=commit or repo_fixture.first,
        issue_text=issue_text,
        ground_truth_files=("pkg/core.py",),
    )


class TestPredictionContract:
    def test_answered_must_rank_something(self) -> None:
        """An empty answer is a stop condition, not a ranking."""
        with pytest.raises(ValueError, match="must rank at least one"):
            Prediction(
                instance_id="x",
                rung="bm25",
                ranked_files=(),
                stop_condition=StopCondition.ANSWERED,
                latency_s=0.0,
            )

    def test_rejects_duplicate_paths(self) -> None:
        """A repeated path would inflate Recall@k without finding anything new."""
        with pytest.raises(ValueError, match="duplicates"):
            Prediction(
                instance_id="x",
                rung="bm25",
                ranked_files=("a.py", "a.py"),
                stop_condition=StopCondition.ANSWERED,
                latency_s=0.0,
            )

    def test_no_candidates_may_be_empty(self) -> None:
        prediction = Prediction(
            instance_id="x",
            rung="bm25",
            ranked_files=(),
            stop_condition=StopCondition.NO_CANDIDATES,
            latency_s=0.0,
        )
        assert prediction.top_1 is None

    def test_carries_cost_and_latency_from_rung_one(self) -> None:
        """Locked decision #3: cost and latency sit beside every accuracy figure.

        Rung 1 spends no money, but the field exists now so no stored run needs
        backfilling when rung 3 does.
        """
        prediction = Prediction(
            instance_id="x",
            rung="bm25",
            ranked_files=("a.py",),
            stop_condition=StopCondition.ANSWERED,
            latency_s=1.5,
        )
        assert prediction.cost_usd == 0.0
        assert prediction.latency_s == 1.5


class TestBm25Rung:
    def test_ranks_every_source_file(self, repo: Fixture) -> None:
        prediction = Bm25Rung(repo.store).predict(instance(repo, "core is broken"))

        assert prediction.stop_condition == StopCondition.ANSWERED
        assert set(prediction.ranked_files) == {"pkg/core.py", "pkg/util.py"}

    def test_excludes_tests_and_docs_from_candidates(self, repo: Fixture) -> None:
        """Same rule as the Ground-Truth File Set, or some instances become
        unwinnable and it reads as a weak retriever."""
        prediction = Bm25Rung(repo.store).predict(instance(repo, "anything"))

        assert "tests/test_core.py" not in prediction.ranked_files
        assert "README.md" not in prediction.ranked_files

    def test_is_deterministic(self, repo: Fixture) -> None:
        """Same instance, same ranking -- otherwise a score change cannot be
        attributed to a code change."""
        rung = Bm25Rung(repo.store)
        target = instance(repo, "shared value")

        assert rung.predict(target).ranked_files == rung.predict(target).ranked_files

    def test_ties_break_by_path_not_enumeration_order(self, repo: Fixture) -> None:
        """A query matching nothing scores every file zero.

        Without an explicit tiebreak the order would follow whatever git
        happened to list first, and determinism would hold only by luck.
        """
        prediction = Bm25Rung(repo.store).predict(instance(repo, "zzzz nonexistent term"))
        assert prediction.ranked_files == tuple(sorted(prediction.ranked_files))

    def test_sees_the_tree_at_the_pinned_commit(self, repo: Fixture) -> None:
        """`added.py` exists only at the second commit."""
        rung = Bm25Rung(repo.store)

        first = rung.predict(instance(repo, "new", commit=repo.first))
        second = rung.predict(instance(repo, "new", commit=repo.second))

        assert "pkg/added.py" not in first.ranked_files
        assert "pkg/added.py" in second.ranked_files

    def test_reports_latency_and_zero_cost(self, repo: Fixture) -> None:
        prediction = Bm25Rung(repo.store).predict(instance(repo, "core"))
        assert prediction.latency_s > 0
        assert prediction.cost_usd == 0.0

    def test_names_itself(self, repo: Fixture) -> None:
        """The scorer labels results by rung; the name travels with the answer."""
        assert Bm25Rung(repo.store).predict(instance(repo, "core")).rung == "bm25"


class TestBlobReuse:
    def test_tokenises_each_distinct_blob_once(self, repo: Fixture) -> None:
        """Across the Verified Set the same content appears ~21 times.

        The cache is keyed by blob SHA, which is a content hash, so an entry
        can never be wrong -- only absent.
        """
        rung = Bm25Rung(repo.store)
        rung.predict(instance(repo, "x", commit=repo.first))
        after_first = dict(rung._tokens_by_blob)

        rung.predict(instance(repo, "x", commit=repo.second))

        util_blob = next(
            f.blob for f in repo.store.list_files(repo.repo, repo.first) if f.path == "pkg/util.py"
        )
        assert rung._tokens_by_blob[util_blob] is after_first[util_blob]
