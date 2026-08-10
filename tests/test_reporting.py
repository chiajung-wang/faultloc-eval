"""Tests for the results log.

The log's whole purpose is that a number cannot drift from its provenance, so
what is tested here is that the provenance is actually present and honest --
particularly the dirty-tree marker, which is the difference between an entry
that is reproducible and one that merely looks it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers import make_instance

from faultloc.dataset.verified import LoadReport
from faultloc.reporting import (
    RESULTS_HEADER,
    UNRECORDED_NOTE,
    Provenance,
    code_version,
    format_duration,
    prepend_entry,
    render_comparison,
    render_entry,
    render_terminal,
)
from faultloc.rungs import Prediction, StopCondition
from faultloc.scoring import PairedComparison, score

REVISION = "c104f840cc67f8b6eec6f759ebc8b2693d585d4a"


def provenance(code_sha: str = "abc1234") -> Provenance:
    return Provenance(
        code_sha=code_sha,
        dataset="princeton-nlp/SWE-bench_Verified",
        dataset_revision=REVISION,
        split="dev",
        seed=20260803,
        command="faultloc evaluate --rung bm25 --split dev",
        run_date="2026-08-03",
    )


def a_report():
    instances = [make_instance(f"i-{n}", "big/repo") for n in range(4)]
    predictions = [
        Prediction(
            instance_id=f"i-{n}",
            rung="bm25",
            ranked_files=("pkg/core.py",) if n < 2 else ("wrong.py",),
            stop_condition=StopCondition.ANSWERED,
            latency_s=0.5,
        )
        for n in range(4)
    ]
    return score(predictions, instances, rung="bm25", split="dev")


def a_load() -> LoadReport:
    return LoadReport(total=500, kept=490, drops={"too_many_source_files": 10})


class TestFormatDuration:
    @pytest.mark.parametrize(
        ("seconds", "expected"), [(9, "9s"), (59, "59s"), (60, "1m 00s"), (252, "4m 12s")]
    )
    def test_formats(self, seconds: int, expected: str) -> None:
        assert format_duration(seconds) == expected


class TestCodeVersion:
    def test_reports_the_short_sha(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@x"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "T"], check=True)
        (tmp_path / "a.txt").write_text("one\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "x"], check=True)

        assert code_version(tmp_path).isalnum()

    def test_marks_a_dirty_tree(self, tmp_path: Path) -> None:
        """A number produced from a modified tree is not reproducible from any
        commit, and an entry that hides that looks trustworthy while being
        worse than one with no provenance at all."""
        subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@x"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "T"], check=True)
        (tmp_path / "a.txt").write_text("one\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "x"], check=True)
        (tmp_path / "a.txt").write_text("edited\n")

        assert code_version(tmp_path).endswith("-dirty")

    def test_outside_a_repository_reports_unknown(self, tmp_path: Path) -> None:
        """Missing provenance must be stated, not crash and not be invented."""
        outside = tmp_path / "not-a-repo"
        outside.mkdir()
        assert code_version(outside) == "unknown"


class TestRenderEntry:
    def test_contains_the_three_reproducibility_inputs(self) -> None:
        """Code commit, dataset revision, split seed. Missing any one makes the
        entry unreproducible without anything looking wrong."""
        entry = render_entry(a_report(), provenance(), a_load(), 252.0)

        assert "abc1234" in entry
        assert REVISION[:7] in entry
        assert "20260803" in entry

    def test_reports_top_1_with_its_interval(self) -> None:
        entry = render_entry(a_report(), provenance(), a_load(), 252.0)
        assert "50.0% (95% CI" in entry

    def test_publishes_the_filter_rate_with_drop_reasons(self) -> None:
        """ADR-0001 requires it beside every result set."""
        entry = render_entry(a_report(), provenance(), a_load(), 252.0)
        assert "500 → 490 kept" in entry
        assert "too_many_source_files 10" in entry
        assert "2.0%" in entry

    def test_includes_the_reproduce_command(self) -> None:
        entry = render_entry(a_report(), provenance(), a_load(), 252.0)
        assert "faultloc evaluate --rung bm25 --split dev" in entry

    def test_records_cost_even_when_zero(self) -> None:
        """Locked decision #3: cost sits beside every accuracy figure."""
        assert "| Cost | $0.00" in render_entry(a_report(), provenance(), a_load(), 1.0)

    def test_marks_an_unrecorded_read_line(self) -> None:
        entry = render_entry(a_report(), provenance(), a_load(), 1.0)
        assert UNRECORDED_NOTE in entry

    def test_keeps_the_note_when_given(self) -> None:
        entry = render_entry(a_report(), provenance(), a_load(), 1.0, note="Sphinx is the outlier.")
        assert "Sphinx is the outlier." in entry

    def test_warns_prominently_on_a_dirty_tree(self) -> None:
        entry = render_entry(a_report(), provenance("abc1234-dirty"), a_load(), 1.0)
        assert "Uncommitted changes" in entry


class TestPrependEntry:
    def test_creates_the_file_with_a_header(self, tmp_path: Path) -> None:
        path = tmp_path / "RESULTS.md"
        prepend_entry(path, "## entry one\n")

        assert path.read_text().startswith(RESULTS_HEADER)
        assert "## entry one" in path.read_text()

    def test_puts_the_newest_entry_first(self, tmp_path: Path) -> None:
        """A reader wants the current number, not the archaeology."""
        path = tmp_path / "RESULTS.md"
        prepend_entry(path, "## older\n")
        prepend_entry(path, "## newer\n")

        text = path.read_text()
        assert text.index("## newer") < text.index("## older")

    def test_never_loses_an_existing_entry(self, tmp_path: Path) -> None:
        path = tmp_path / "RESULTS.md"
        for n in range(4):
            prepend_entry(path, f"## entry {n}\n")

        text = path.read_text()
        assert all(f"## entry {n}" in text for n in range(4))
        assert text.count(RESULTS_HEADER) == 1


class TestRenderTerminal:
    def test_shows_the_same_headline_as_the_entry(self) -> None:
        report, prov, load = a_report(), provenance(), a_load()
        terminal = render_terminal(report, prov, load, 252.0)

        assert "50.0%" in terminal
        assert "Filter: 500 → 490 kept" in terminal

    def test_warns_when_the_tree_is_dirty(self) -> None:
        terminal = render_terminal(a_report(), provenance("abc-dirty"), a_load(), 1.0)
        assert "not reproducible" in terminal


class TestPredictionsLine:
    def test_names_the_stored_run_when_there_is_one(self) -> None:
        """A paired test must be traceable to the two runs that produced it."""
        entry = render_entry(
            a_report(),
            provenance(),
            a_load(),
            12.0,
            predictions=Path("data/predictions/bm25-dev-2026-08-03-abc1234.jsonl"),
        )

        assert "- Predictions: `data/predictions/bm25-dev-2026-08-03-abc1234.jsonl`" in entry

    def test_an_entry_without_stored_predictions_is_unchanged(self) -> None:
        """Every entry written before M5 had no such file, and the format must
        not gain an empty bullet that reads as a missing value."""
        entry = render_entry(a_report(), provenance(), a_load(), 12.0)

        assert "Predictions" not in entry


def a_comparison(a_only: int, b_only: int, p_value: float) -> PairedComparison:
    return PairedComparison(
        a="rerank-deepseek-on",
        b="agent",
        n=244,
        both_hit=180,
        both_miss=48,
        a_only=a_only,
        b_only=b_only,
        p_value=p_value,
    )


class TestRenderComparison:
    def test_states_the_verdict_rather_than_leave_it_to_the_reader(self) -> None:
        """The whole reason the test exists. A reader who compares two Wilson
        intervals would reach the opposite conclusion."""
        rendered = render_comparison(a_comparison(0, 16, 0.00003), provenance(), provenance())

        assert "difference is established" in rendered
        assert "agent beats rerank-deepseek-on on 16" in rendered

    def test_says_nothing_established_when_the_split_is_even(self) -> None:
        rendered = render_comparison(a_comparison(7, 9, 0.8), provenance(), provenance())

        assert "Nothing established" in rendered

    def test_reports_a_reversal_in_the_direction_it_happened(self) -> None:
        """A rung that loses must not be rendered as a rung that won."""
        rendered = render_comparison(a_comparison(16, 0, 0.00003), provenance(), provenance())

        assert "goes the other way" in rendered
        assert "rerank-deepseek-on beats agent on 16" in rendered

    def test_agreement_everywhere_is_untestable_and_says_so(self) -> None:
        rendered = render_comparison(a_comparison(0, 0, 1.0), provenance(), provenance())

        assert "agree on every Instance" in rendered

    def test_names_the_discordant_count_as_the_evidence(self) -> None:
        rendered = render_comparison(a_comparison(4, 20, 0.002), provenance(), provenance())

        assert "discordant" in rendered
        assert "the whole evidence" in rendered

    def test_warns_that_a_wilson_interval_does_not_license_the_claim(self) -> None:
        rendered = render_comparison(a_comparison(4, 20, 0.002), provenance(), provenance())

        assert "describes that row alone" in rendered
