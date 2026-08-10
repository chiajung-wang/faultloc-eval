"""Storing a run's Predictions.

The paired test in `scoring.compare` is only as trustworthy as what it reads. A
stored run that silently loses Instances would produce a p-value over a subset
and nothing downstream could tell.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultloc.predictions import read_run, run_path, write_run
from faultloc.reporting import Provenance
from faultloc.rungs import Prediction, StopCondition


def provenance(sha: str = "abc1234") -> Provenance:
    return Provenance(
        code_sha=sha,
        dataset="princeton-nlp/SWE-bench_Verified",
        dataset_revision="c104f840cc67f8b6eec6f759ebc8b2693d585d4a",
        split="dev",
        seed=0,
        command="faultloc evaluate --rung bm25 --split dev",
        run_date="2026-08-10",
    )


def prediction(number: int, **overrides: object) -> Prediction:
    fields: dict = {
        "instance_id": f"acme__widget-{number}",
        "rung": "bm25",
        "ranked_files": ("pkg/core.py", "pkg/util.py"),
        "stop_condition": StopCondition.ANSWERED,
        "latency_s": 0.25,
        "cost_usd": 0.0,
    }
    fields.update(overrides)
    return Prediction(**fields)  # type: ignore[arg-type]


class TestRoundTrip:
    def test_predictions_survive_a_write_and_a_read(self, tmp_path: Path) -> None:
        original = [prediction(0), prediction(1)]
        path = tmp_path / "run.jsonl"

        write_run(path, rung="bm25", split="dev", provenance=provenance(), predictions=original)

        assert read_run(path).predictions == tuple(original)

    def test_ranked_files_comes_back_as_a_tuple(self, tmp_path: Path) -> None:
        """JSON has no tuples, and `Prediction` is frozen with tuple fields.

        A list would compare unequal to the original and would break the
        duplicate check in `__post_init__` on any later reconstruction.
        """
        path = tmp_path / "run.jsonl"
        write_run(
            path, rung="bm25", split="dev", provenance=provenance(), predictions=[prediction(0)]
        )

        assert isinstance(read_run(path).predictions[0].ranked_files, tuple)

    def test_an_absent_confidence_survives(self, tmp_path: Path) -> None:
        """Rung 4 reports no Confidence. ADR-0004 gives that job to the Calibrator."""
        path = tmp_path / "run.jsonl"
        write_run(
            path, rung="bm25", split="dev", provenance=provenance(), predictions=[prediction(0)]
        )

        assert read_run(path).predictions[0].confidence is None

    def test_the_header_carries_the_provenance_of_the_entry(self, tmp_path: Path) -> None:
        """A stored run and its `RESULTS.md` entry must not disagree on the commit."""
        path = tmp_path / "run.jsonl"
        write_run(
            path,
            rung="rerank-deepseek-on",
            split="dev",
            provenance=provenance(sha="deadbee"),
            predictions=[prediction(0)],
        )

        stored = read_run(path)

        assert stored.provenance.code_sha == "deadbee"
        assert stored.rung == "rerank-deepseek-on"
        assert stored.split == "dev"

    def test_the_rung_is_the_cli_name_and_not_the_prediction_field(self, tmp_path: Path) -> None:
        """All four rung-3 cells set `Prediction.rung` to `rerank`.

        So the Prediction's own field cannot tell `rerank` from
        `rerank-deepseek-on`, and those are different numbers at different
        prices. The header has to carry the name the CLI was invoked with.
        """
        path = tmp_path / "run.jsonl"
        write_run(
            path,
            rung="rerank-deepseek-on",
            split="dev",
            provenance=provenance(),
            predictions=[prediction(0, rung="rerank")],
        )

        stored = read_run(path)

        assert stored.rung == "rerank-deepseek-on"
        assert stored.predictions[0].rung == "rerank"


class TestTruncatedRuns:
    def test_a_truncated_run_records_its_limit(self, tmp_path: Path) -> None:
        """`--limit` writes Predictions and still refuses a results entry.

        A reader must be able to tell a truncated run from a full one, because a
        truncated run is scored on a different Instance set.
        """
        path = tmp_path / "run.jsonl"
        write_run(
            path,
            rung="bm25",
            split="dev",
            provenance=provenance(),
            predictions=[prediction(0)],
            limit=1,
        )

        stored = read_run(path)

        assert stored.limit == 1
        assert stored.is_truncated

    def test_a_full_run_is_not_truncated(self, tmp_path: Path) -> None:
        path = tmp_path / "run.jsonl"
        write_run(
            path, rung="bm25", split="dev", provenance=provenance(), predictions=[prediction(0)]
        )

        assert not read_run(path).is_truncated


class TestRunPath:
    def test_names_the_run_after_what_identifies_it(self, tmp_path: Path) -> None:
        path = run_path("bm25", "dev", provenance(), root=tmp_path)

        assert path.name == "bm25-dev-2026-08-10-abc1234.jsonl"

    def test_a_repeat_run_never_overwrites_the_first(self, tmp_path: Path) -> None:
        """Same cell, same day, same commit is possible, and both runs matter."""
        first = run_path("bm25", "dev", provenance(), root=tmp_path)
        first.parent.mkdir(parents=True, exist_ok=True)
        first.touch()

        second = run_path("bm25", "dev", provenance(), root=tmp_path)

        assert second != first
        assert second.name == "bm25-dev-2026-08-10-abc1234-2.jsonl"

    def test_a_dirty_run_is_visible_in_the_filename(self, tmp_path: Path) -> None:
        """`code_version` suffixes `-dirty`, and that must not be lost here."""
        path = run_path("bm25", "dev", provenance(sha="abc1234-dirty"), root=tmp_path)

        assert "dirty" in path.name


class TestRefusals:
    def test_an_empty_file_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "run.jsonl"
        path.write_text("")

        with pytest.raises(ValueError, match="empty"):
            read_run(path)

    def test_a_file_without_a_header_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "run.jsonl"
        path.write_text(json.dumps({"instance_id": "acme__widget-0"}) + "\n")

        with pytest.raises(ValueError, match="run header"):
            read_run(path)

    def test_a_short_read_is_refused(self, tmp_path: Path) -> None:
        """The failure this check exists for.

        A half-written or hand-trimmed file would otherwise feed the paired test
        a subset, and the p-value would be about a benchmark nobody ran.
        """
        path = tmp_path / "run.jsonl"
        write_run(
            path,
            rung="bm25",
            split="dev",
            provenance=provenance(),
            predictions=[prediction(0), prediction(1)],
        )
        lines = path.read_text().splitlines()
        path.write_text("\n".join(lines[:-1]) + "\n")

        with pytest.raises(ValueError, match="header says 2"):
            read_run(path)


class TestAtomicWrite:
    def test_leaves_no_temporary_file_behind(self, tmp_path: Path) -> None:
        path = tmp_path / "run.jsonl"
        write_run(
            path, rung="bm25", split="dev", provenance=provenance(), predictions=[prediction(0)]
        )

        assert not list(tmp_path.rglob("*.tmp"))

    def test_creates_the_directory_it_needs(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deeper" / "run.jsonl"
        write_run(
            path, rung="bm25", split="dev", provenance=provenance(), predictions=[prediction(0)]
        )

        assert path.is_file()
