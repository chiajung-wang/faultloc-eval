"""Tests for the command-line surface.

Only the parts with logic in them. Wiring is left to the commands themselves,
which is the point of keeping them thin.
"""

from __future__ import annotations

from faultloc.cli import _count, _failure_note, _progress_line


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


class TestCacheNote:
    def test_replays_are_reported_but_not_called_a_degradation(self) -> None:
        """A cache hit is not a failure. Filing it under 'Degraded' would make
        a clean resumed run read as a broken one."""
        note = _failure_note(StubEngine(unparseable=0, truncated=0, off_list=0, cache_hits=200))

        assert "Degraded" not in note
        assert "Replayed 200" in note

    def test_a_run_that_both_degraded_and_replayed_says_both(self) -> None:
        note = _failure_note(StubEngine(unparseable=2, truncated=0, off_list=9, cache_hits=110))

        assert "2 unparseable replies" in note
        assert "9 off-list paths" in note
        assert "Replayed 110" in note

    def test_a_fresh_clean_run_says_nothing(self) -> None:
        assert _failure_note(StubEngine(unparseable=0, truncated=0, off_list=0, cache_hits=0)) == ""


class TestCount:
    def test_reads_an_integer_counter(self) -> None:
        assert _count(StubEngine(off_list=6), "off_list") == 6

    def test_reads_the_length_of_a_list_counter(self) -> None:
        """Rung 3 counts off-list paths with an integer. Rung 4 keeps the paths,
        so the entry can show what a hallucinated path looks like. Without this
        the note would print a Python list into the results log."""
        assert _count(StubEngine(off_list=["a.py", "b.py"]), "off_list") == 2

    def test_a_missing_counter_is_zero(self) -> None:
        assert _count(StubEngine(), "off_list") == 0


class TestFailureNoteForFreeRungs:
    def test_a_clean_free_rung_says_nothing(self) -> None:
        """Rungs 1 and 2 have no counters at all, and their entries must not gain
        an empty sentence."""
        assert _failure_note(StubEngine()) == ""

    def test_rung_3_renders_exactly_as_it_did_before(self) -> None:
        """The regression that matters. Rung 4's disclosures must not change a
        single character of what rung 3 publishes, or the M4 entries and the M5
        entries stop being comparable prose."""
        engine = StubEngine(unparseable=17, truncated=3, off_list=6, cache_hits=244)

        note = _failure_note(engine)

        assert note == (
            "Degraded: 17 unparseable replies, 3 truncated replies, 6 off-list paths. "
            "Replayed 244 responses from cache; cost is what they cost to make."
        )

    def test_a_free_rung_gets_no_guardrail_line(self) -> None:
        assert "Guardrail" not in _failure_note(StubEngine(unparseable=1))

    def test_a_free_rung_gets_no_tool_call_line(self) -> None:
        assert "Tool calls" not in _failure_note(StubEngine(unparseable=1))


class TestFailureNoteForRungFour:
    def agent(self, **overrides: object) -> StubEngine:
        fields: dict = {
            "unparseable": 2,
            "truncated": 1,
            "off_list": ["src/found.py", "src/other.py"],
            "hallucinated": ["ghost.py"],
            "guardrail_retries": 1,
            "recalled": ["src/other.py"],
            "calls_per_instance": [1, 3, 8, 8],
            "max_tool_calls": 8,
        }
        fields.update(overrides)
        return StubEngine(**fields)

    def test_an_off_list_path_is_not_filed_as_a_degrade(self) -> None:
        """It is what rung 4 adds over rung 3. Rung 3 discards such a path; rung 4
        keeps one that exists. Calling it a degrade would be the exact conflation
        ADR-0009 corrects."""
        note = _failure_note(self.agent())

        assert "off-list paths" not in note
        assert "Off-list accepted: 2" in note

    def test_publishes_the_guardrail_catch_rate(self) -> None:
        """`CONTEXT.md` promises it."""
        note = _failure_note(self.agent())

        assert "1 paths rejected as absent at base_commit" in note
        assert "1 retries" in note

    def test_publishes_tool_reached(self) -> None:
        """A real path no tool surfaced was recalled from training data rather
        than found. The Verified Set predates the cutoff."""
        assert "1 were never surfaced by a tool" in _failure_note(self.agent())

    def test_publishes_the_tool_call_distribution(self) -> None:
        """ADR-0009's revisit condition. If most Instances reach the cap, the cap
        produced the number rather than the agent."""
        note = _failure_note(self.agent())

        assert "median 8" in note
        assert "cap of 8 reached on 2/4 instances" in note

    def test_still_reports_the_ways_it_kept_its_input_ranking(self) -> None:
        note = _failure_note(self.agent())

        assert "2 unparseable replies" in note
        assert "1 truncated replies" in note

    def test_reports_instances_that_had_no_candidates(self) -> None:
        assert "3 instances with no candidates" in _failure_note(self.agent(no_candidates=3))

    def test_a_clean_agent_run_still_reports_its_tool_calls(self) -> None:
        """Zero failures is not zero information. The distribution decides whether
        the cap bound the result."""
        note = _failure_note(
            self.agent(
                unparseable=0,
                truncated=0,
                off_list=[],
                hallucinated=[],
                guardrail_retries=0,
                recalled=[],
            )
        )

        assert "Degraded" not in note
        assert "Tool calls: median 8" in note

    def test_the_zero_tool_cell_reports_no_cap(self) -> None:
        """The Ablation makes no tool calls at all, so a cap line would be noise."""
        note = _failure_note(self.agent(calls_per_instance=[0, 0], max_tool_calls=0))

        assert "cap of 0 reached on 0/2" in note

    def test_reports_a_tool_the_model_invented(self) -> None:
        """It costs a step against the Instance Budget, so it cannot be silent."""
        note = _failure_note(self.agent(unknown_tools=2))

        assert "2 calls to tools that do not exist" in note
