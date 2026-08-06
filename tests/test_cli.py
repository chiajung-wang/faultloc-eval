"""Tests for the command-line surface.

Only the parts with logic in them. Wiring is left to the commands themselves,
which is the point of keeping them thin.
"""

from __future__ import annotations

from faultloc.cli import _failure_note, _progress_line


class StubEngine:
    def __init__(self, **counts: int) -> None:
        self.__dict__.update(counts)


class TestProgressLine:
    def test_shows_spend_against_the_cap_when_there_is_one(self) -> None:
        line = _progress_line(40, 244, 18, 0.208, 2.0, 196.0, (0, 0, 1))
        assert "$0.208/$2.00" in line

    def test_omits_the_cap_for_a_rung_that_cannot_spend(self) -> None:
        """Rungs 1 through 2.6 are free. `$0.00/$0.00` would read as a budget
        about to be breached rather than one that does not exist."""
        line = _progress_line(40, 244, 18, 0.0, 0.0, 20.0, (0, 0, 0))

        assert "$0.00" in line
        assert "/$" not in line

    def test_projects_the_remaining_time_from_the_pace_so_far(self) -> None:
        # 40 of 244 done in 200s is 5s each; 204 left is 1020s, near 17 minutes.
        assert "eta 17m" in _progress_line(40, 244, 18, 0.0, 0.0, 200.0, (0, 0, 0))

    def test_running_top_1_is_of_what_has_been_scored_not_the_whole_split(self) -> None:
        """The signal that catches a broken run early: a rung whose replies all
        fail degrades to its input ranking and tracks the rung below it."""
        assert "top-1 45.0%" in _progress_line(40, 244, 18, 0.0, 0.0, 20.0, (0, 0, 0))


class TestFailureNote:
    def test_says_nothing_when_nothing_degraded(self) -> None:
        assert _failure_note(StubEngine(unparseable=0, truncated=0, off_list=0)) == ""

    def test_names_only_the_failures_that_happened(self) -> None:
        note = _failure_note(StubEngine(unparseable=3, truncated=0, off_list=7))

        assert "3 unparseable replies" in note
        assert "7 off-list paths" in note
        assert "truncated" not in note

    def test_a_rung_that_counts_nothing_contributes_nothing(self) -> None:
        """Rungs 1 through 2.6 have no such counters, and `getattr` defaults
        must not turn that into a row of zeroes in every entry's note."""
        assert _failure_note(StubEngine()) == ""
