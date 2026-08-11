"""The Path Guardrail and the answer assembly.

The distinction under test is the one `CONTEXT.md` had wrong until M5 corrected
it. The guardrail asks whether a path **exists**. It never asks whether the
Candidate Set held it. Issue 01 measured what conflating the two would cost: of 6
Off-List Paths recovered from a cached rung-3 cell, 5 existed.
"""

from __future__ import annotations

from conftest import Fixture

from faultloc.agent_answer import SUBMIT_RANKING_SCHEMA, Guardrail, assemble
from faultloc.dataset.models import Instance

CANDIDATES = ("pkg/core.py", "pkg/util.py")


def rail(repo: Fixture, commit: str | None = None) -> Guardrail:
    return Guardrail(
        store=repo.store,
        instance=Instance(
            instance_id="acme__widget-1",
            repo=repo.repo,
            base_commit=commit or repo.first,
            issue_text="broken",
            ground_truth_files=("pkg/core.py",),
        ),
    )


class TestTheGuardrail:
    def test_keeps_a_path_that_exists(self, repo: Fixture) -> None:
        kept, absent = rail(repo).split(["pkg/core.py"])

        assert kept == ("pkg/core.py",)
        assert absent == ()

    def test_rejects_a_path_that_does_not_exist(self, repo: Fixture) -> None:
        kept, absent = rail(repo).split(["pkg/invented.py"])

        assert kept == ()
        assert absent == ("pkg/invented.py",)

    def test_keeps_a_path_the_candidate_set_never_held(self, repo: Fixture) -> None:
        """The whole reason rung 4 can pass the 88.9% ceiling.

        `pkg/util.py` exists and is not a candidate here. Rung 3 discards such a
        path. Rung 4 keeps it, because reaching past the list is the only thing
        rung 4 adds.
        """
        kept, absent = rail(repo).split(["pkg/util.py"])

        assert kept == ("pkg/util.py",)
        assert absent == ()

    def test_asks_about_existence_at_the_pinned_commit(self, repo: Fixture) -> None:
        """`pkg/added.py` exists at the second commit and not at the first.

        An agent recalling a path from training data will name a file that exists
        today and did not exist then. That is a hallucination for this Instance.
        """
        assert rail(repo, repo.first).split(["pkg/added.py"])[1] == ("pkg/added.py",)
        assert rail(repo, repo.second).split(["pkg/added.py"])[0] == ("pkg/added.py",)

    def test_keeps_order_on_both_sides(self, repo: Fixture) -> None:
        """The surviving order is the agent's ranking, and the rejected order is
        what the retry message quotes back."""
        kept, absent = rail(repo).split(["pkg/util.py", "no/a.py", "pkg/core.py", "no/b.py"])

        assert kept == ("pkg/util.py", "pkg/core.py")
        assert absent == ("no/a.py", "no/b.py")

    def test_drops_a_path_named_twice(self, repo: Fixture) -> None:
        """`Prediction` refuses duplicates, and a path named twice is one
        judgement rather than two."""
        kept, _ = rail(repo).split(["pkg/core.py", "pkg/core.py"])

        assert kept == ("pkg/core.py",)

    def test_normalises_before_comparing(self, repo: Fixture) -> None:
        """`./pkg/core.py` and `pkg/core.py` are the same file written twice."""
        kept, absent = rail(repo).split(["./pkg/core.py"])

        assert kept == ("pkg/core.py",)
        assert absent == ()

    def test_ignores_an_empty_path(self, repo: Fixture) -> None:
        kept, absent = rail(repo).split(["", "   ", "pkg/core.py"])

        assert kept == ("pkg/core.py",)
        assert absent == ()

    def test_a_test_file_still_counts_as_existing(self, repo: Fixture) -> None:
        """The guardrail asks about existence, not about being a valid answer.

        `tests/test_core.py` is in the tree and is not a source file. Scoring
        decides it is wrong. The guardrail is not the place to hide that, because
        rejecting it would report a hallucination that did not happen.
        """
        kept, absent = rail(repo).split(["tests/test_core.py"])

        assert kept == ("tests/test_core.py",)
        assert absent == ()


class TestAssembly:
    def test_the_agent_order_comes_first(self) -> None:
        answer = assemble(["pkg/util.py"], CANDIDATES)

        assert answer.ranking[0] == "pkg/util.py"

    def test_unmentioned_candidates_follow_in_candidate_set_order(self) -> None:
        """Never shrinks the list the ceiling was measured on."""
        answer = assemble(["pkg/util.py"], CANDIDATES)

        assert answer.ranking == ("pkg/util.py", "pkg/core.py")

    def test_an_off_list_path_is_reported(self) -> None:
        """The measure of whether rung 4 earned its rung."""
        answer = assemble(["src/found.py", "pkg/core.py"], CANDIDATES)

        assert answer.off_list == ("src/found.py",)
        assert answer.ranking[0] == "src/found.py"

    def test_a_candidate_is_not_an_off_list_path(self) -> None:
        answer = assemble(["pkg/core.py"], CANDIDATES)

        assert answer.off_list == ()

    def test_no_answer_falls_back_to_the_candidate_set(self) -> None:
        """It scores like the rung below, which is why `fell_back` exists."""
        answer = assemble([], CANDIDATES)

        assert answer.ranking == CANDIDATES
        assert answer.fell_back

    def test_an_answer_is_not_a_fallback(self) -> None:
        assert not assemble(["pkg/core.py"], CANDIDATES).fell_back

    def test_removes_duplicates(self) -> None:
        """`Prediction.__post_init__` raises on a repeated path."""
        answer = assemble(["pkg/core.py", "pkg/core.py"], CANDIDATES)

        assert answer.ranking == ("pkg/core.py", "pkg/util.py")

    def test_a_reordering_keeps_every_candidate(self) -> None:
        answer = assemble(["pkg/util.py", "pkg/core.py"], CANDIDATES)

        assert set(answer.ranking) == set(CANDIDATES)
        assert answer.ranking == ("pkg/util.py", "pkg/core.py")

    def test_carries_the_hallucinated_paths_through(self) -> None:
        """The guardrail's catch rate, which CONTEXT.md promises to publish."""
        answer = assemble(["pkg/core.py"], CANDIDATES, hallucinated=["no/a.py"])

        assert answer.hallucinated == ("no/a.py",)
        assert "no/a.py" not in answer.ranking

    def test_normalises_paths_in_the_ranking(self) -> None:
        answer = assemble(["./pkg/util.py"], CANDIDATES)

        assert answer.ranking[0] == "pkg/util.py"


class TestSchema:
    def test_names_the_terminal_action(self) -> None:
        assert SUBMIT_RANKING_SCHEMA["function"]["name"] == "submit_ranking"

    def test_requires_the_paths_argument(self) -> None:
        assert SUBMIT_RANKING_SCHEMA["function"]["parameters"]["required"] == ["paths"]

    def test_asks_for_an_array_of_strings(self) -> None:
        paths = SUBMIT_RANKING_SCHEMA["function"]["parameters"]["properties"]["paths"]

        assert paths["type"] == "array"
        assert paths["items"]["type"] == "string"

    def test_tells_the_model_off_list_paths_are_welcome(self) -> None:
        """If the description did not say so, the agent would have no reason to
        report a file it found outside the candidate list -- and that file is the
        only thing rung 4 adds over rung 3."""
        assert "not in the candidate list" in SUBMIT_RANKING_SCHEMA["function"]["description"]

    def test_is_json_serializable(self) -> None:
        import json

        assert json.dumps(SUBMIT_RANKING_SCHEMA, sort_keys=True)
