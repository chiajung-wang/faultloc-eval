"""Rung 4's read-only tools, and the contract they keep.

The `repo` fixture builds a real bare clone rather than mocking git, for the same
reason `test_repos.py` does: these tools exist to drive git correctly, and a mock
would only assert that git is called the way the author already believes.
"""

from __future__ import annotations

import pytest
from conftest import Fixture

from faultloc.agent_tools import (
    FILE_OUTLINE_SCHEMA,
    FIND_DEFINITION_SCHEMA,
    MAX_HITS,
    MAX_RESULT_CHARS,
    MAX_RESULT_LINES,
    READ_FILE_SCHEMA,
    SEARCH_CODE_SCHEMA,
    Toolbox,
    ToolError,
)
from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore


def box(repo: Fixture, commit: str | None = None, path: str = "pkg/core.py") -> Toolbox:
    return Toolbox(
        store=repo.store,
        instance=Instance(
            instance_id="acme__widget-1",
            repo=repo.repo,
            base_commit=commit or repo.first,
            issue_text="something is broken",
            ground_truth_files=(path,),
        ),
    )


class TestReadingAFile:
    def test_returns_the_contents_at_the_pinned_commit(self, repo: Fixture) -> None:
        result = box(repo).read_file("pkg/core.py")

        assert "def first" in result.text
        assert not result.rejected

    def test_reads_the_commit_the_instance_pins_and_not_the_branch(self, repo: Fixture) -> None:
        """`pkg/core.py` says `def first` at one commit and `def second` at the next.

        The agent never supplies the commit. It is the Instance, not a decision
        the model gets to make.
        """
        assert "def first" in box(repo, repo.first).read_file("pkg/core.py").text
        assert "def second" in box(repo, repo.second).read_file("pkg/core.py").text

    def test_numbers_the_lines(self, repo: Fixture) -> None:
        """Line numbers are how the agent asks for the next range, and `git grep
        -n` will report them the same way at issue 05."""
        assert "     1  def first" in box(repo).read_file("pkg/core.py").text

    def test_reports_which_range_of_which_file_it_returned(self, repo: Fixture) -> None:
        result = box(repo).read_file("pkg/core.py")

        assert "pkg/core.py lines 1-1 of 1" in result.text

    def test_surfaces_the_path_it_read(self, repo: Fixture) -> None:
        """`paths` feeds Tool-Reached, which separates a path the agent found
        from one it recalled. The Verified Set predates the training cutoff."""
        assert box(repo).read_file("pkg/core.py").paths == ("pkg/core.py",)

    def test_tolerates_a_leading_dot_slash(self, repo: Fixture) -> None:
        assert not box(repo).read_file("./pkg/core.py").rejected


class TestModelCausedFailures:
    """Each one returns text to the agent and costs one call. None of them raise."""

    def test_a_path_that_does_not_exist_is_reported_not_raised(self, repo: Fixture) -> None:
        """The Path Guardrail's lesson, delivered early and for free."""
        result = box(repo).read_file("pkg/invented.py")

        assert result.rejected
        assert "No file at `pkg/invented.py`" in result.text

    def test_a_file_from_the_wrong_commit_is_reported(self, repo: Fixture) -> None:
        """`pkg/added.py` exists at the second commit and not at the first.

        An agent that recalls a path from training data will do exactly this.
        """
        result = box(repo, repo.first).read_file("pkg/added.py")

        assert result.rejected
        assert not box(repo, repo.second).read_file("pkg/added.py").rejected

    def test_a_range_past_the_end_of_the_file_is_reported(self, repo: Fixture) -> None:
        result = box(repo).read_file("pkg/core.py", start=500, end=600)

        assert result.rejected
        assert "has 1 lines" in result.text

    @pytest.mark.parametrize(
        ("start", "end"),
        [(0, 10), (-5, 10), (20, 10)],
    )
    def test_an_impossible_range_is_reported(self, repo: Fixture, start: int, end: int) -> None:
        assert box(repo).read_file("pkg/core.py", start=start, end=end).rejected

    def test_an_empty_path_is_reported(self, repo: Fixture) -> None:
        assert box(repo).read_file("").rejected


class TestInfrastructureFailures:
    """These raise. As empty results they would read as a thorough search."""

    def test_a_missing_clone_ends_the_instance(self, tmp_path) -> None:
        broken = Toolbox(
            store=RepoStore(root=tmp_path / "none", cache_root=tmp_path / "cache"),
            instance=Instance(
                instance_id="acme__widget-1",
                repo="acme/widget",
                base_commit="a" * 40,
                issue_text="broken",
                ground_truth_files=("pkg/core.py",),
            ),
        )

        with pytest.raises(ToolError):
            broken.read_file("pkg/core.py")

    def test_a_missing_commit_ends_the_instance(self, repo: Fixture) -> None:
        """The measured trap this design exists for.

        `RepoStore.read_file` raises `CommitUnavailableError` for a missing path
        AND for a missing commit, so the split cannot be made on exception type.
        Asking `list_files` first is what tells the two apart.
        """
        with pytest.raises(ToolError):
            box(repo, "0" * 40).read_file("pkg/core.py")


class TestCaps:
    def test_caps_the_number_of_lines(self, repo: Fixture) -> None:
        long_file = "\n".join(f"line {n}" for n in range(1, 1000))
        result = _read_synthetic(repo, long_file, start=1, end=999)

        assert result.truncated
        assert len(result.text.splitlines()) <= MAX_RESULT_LINES + 1  # +1 for the header

    def test_caps_the_number_of_characters(self, repo: Fixture) -> None:
        """A file of very long lines must not slip past a line cap.

        The character cap is what makes ADR-0009's cost arithmetic a bound rather
        than a guess.
        """
        wide = "\n".join("x" * 500 for _ in range(50))
        result = _read_synthetic(repo, wide, start=1, end=50)

        assert result.truncated
        assert len(result.text) <= MAX_RESULT_CHARS + 200  # header allowance

    def test_says_so_when_it_cuts(self, repo: Fixture) -> None:
        """A silent cut is a biased slice the agent cannot know about."""
        result = _read_synthetic(repo, "\n".join(f"line {n}" for n in range(999)), 1, 999)

        assert "ask for a smaller range" in result.text

    def test_a_small_file_is_not_truncated(self, repo: Fixture) -> None:
        assert not box(repo).read_file("pkg/core.py").truncated


class TestDeterminism:
    def test_two_reads_are_byte_identical(self, repo: Fixture) -> None:
        """The property the free replay rests on.

        A resumed run replays from the response cache only while each step's
        prompt stays byte-identical, so a tool that varies between calls makes a
        six-hour run pay twice.
        """
        first = box(repo).read_file("pkg/core.py").text
        second = box(repo).read_file("pkg/core.py").text

        assert first == second

    def test_a_fresh_toolbox_produces_the_same_bytes(self, repo: Fixture) -> None:
        """Not merely stable inside one object. A resumed run builds new ones."""
        assert box(repo).read_file("pkg/core.py").text == box(repo).read_file("pkg/core.py").text

    def test_leaks_no_absolute_path(self, repo: Fixture) -> None:
        """`data/repos/...` in a result would differ between machines, and it
        would put a local filesystem into a published transcript."""
        text = box(repo).read_file("pkg/core.py").text

        assert "/" in text  # the repo-relative path is there
        assert str(repo.store.root) not in text


class TestSchema:
    def test_names_the_tool_the_model_will_call(self) -> None:
        assert READ_FILE_SCHEMA["function"]["name"] == "read_file"

    def test_only_path_is_required(self) -> None:
        """The agent should be able to read the head of a file without guessing
        a range."""
        assert READ_FILE_SCHEMA["function"]["parameters"]["required"] == ["path"]

    def test_is_json_serializable(self) -> None:
        """It goes into the response cache key, so it has to serialize stably."""
        import json

        assert json.dumps(READ_FILE_SCHEMA, sort_keys=True)


def _read_synthetic(repo: Fixture, body: str, start: int, end: int):
    """Commit `body` as a new file, then read it back through the tool."""
    import subprocess
    from pathlib import Path

    work = Path(repo.store.root).parent / "synthetic"
    if not work.is_dir():
        subprocess.run(
            ["git", "clone", "-q", str(repo.store.clone_path(repo.repo)), str(work)], check=True
        )
        subprocess.run(
            ["git", "-C", str(work), "config", "user.email", "t@example.com"], check=True
        )
        subprocess.run(["git", "-C", str(work), "config", "user.name", "T"], check=True)

    (work / "pkg" / "big.py").write_text(body + "\n")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", "big"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "push", "-q", "origin", "HEAD:refs/heads/big"], check=True
    )
    sha = subprocess.run(
        ["git", "-C", str(work), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()

    return box(repo, sha).read_file("pkg/big.py", start=start, end=end)


class TestSearchCode:
    def test_finds_the_files_containing_the_text(self, repo: Fixture) -> None:
        result = box(repo).search_code("def first")

        assert "pkg/core.py" in result.text
        assert result.paths == ("pkg/core.py",)

    def test_searches_the_commit_the_instance_pins(self, repo: Fixture) -> None:
        assert box(repo, repo.first).search_code("def second").paths == ()
        assert box(repo, repo.second).search_code("def second").paths == ("pkg/core.py",)

    def test_matches_literally_and_not_as_a_pattern(self, repo: Fixture) -> None:
        """A report quotes text full of dots, brackets and asterisks, and every one
        of them means itself. ADR-0009 first said "literal and regex" and was
        corrected: literal is what issue 01 measured and what shipped."""
        assert box(repo).search_code("f...t").paths == ()
        assert box(repo).search_code("def first(): ...").paths == ("pkg/core.py",)

    def test_reports_the_count_when_it_finds_some(self, repo: Fixture) -> None:
        assert "1 source files contain" in box(repo).search_code("def first").text

    def test_finding_nothing_is_a_fact_and_not_a_mistake(self, repo: Fixture) -> None:
        """A search that finds nothing is information about the repository. The
        agent needs it in order to try another term, and marking it as a mistake
        would tell it the wrong thing."""
        result = box(repo).search_code("nowhere_at_all")

        assert result.paths == ()
        assert not result.rejected
        assert "No source file contains" in result.text

    def test_an_empty_pattern_is_a_mistake(self, repo: Fixture) -> None:
        assert box(repo).search_code("   ").rejected

    def test_excludes_non_source_files(self, repo: Fixture) -> None:
        """`tests/test_core.py` contains `first` and is not an answer. Filtered by
        the same `is_source_file` that builds the Ground-Truth File Set."""
        assert box(repo).search_code("first").paths == ("pkg/core.py",)

    def test_caps_the_hits_and_reports_the_true_count(self, repo: Fixture) -> None:
        """The cap the agent can see. Issue 01 measured its cost at one Instance of
        27, and a silent cut would be a biased slice the agent cannot know about.
        """
        sha = _commit_many_files(repo, MAX_HITS + 12, "WIDGET_MARKER")
        result = box(repo, sha).search_code("WIDGET_MARKER")

        assert len(result.paths) == MAX_HITS
        assert f"{MAX_HITS + 12} source files contain" in result.text
        assert f"showing the first {MAX_HITS}" in result.text
        assert result.truncated

    def test_does_not_claim_truncation_when_it_showed_everything(self, repo: Fixture) -> None:
        assert not box(repo).search_code("def first").truncated

    def test_two_searches_are_byte_identical(self, repo: Fixture) -> None:
        assert box(repo).search_code("first").text == box(repo).search_code("first").text

    def test_a_missing_commit_ends_the_instance(self, repo: Fixture) -> None:
        with pytest.raises(ToolError):
            box(repo, "0" * 40).search_code("first")


class TestSearchCodeSchema:
    def test_names_the_tool(self) -> None:
        assert SEARCH_CODE_SCHEMA["function"]["name"] == "search_code"

    def test_warns_the_model_off_pasting_error_messages(self) -> None:
        """Issue 01's sharpest finding: error strings reach NOTHING, zero of 27. A
        report shows the rendered message and the code holds the template, so the
        message appears in no file. Without this line the agent would waste steps
        discovering that."""
        description = SEARCH_CODE_SCHEMA["function"]["description"]

        assert "Do NOT paste an error message" in description
        assert "identifiers inside it" in description

    def test_says_the_match_is_literal(self) -> None:
        assert "literal" in SEARCH_CODE_SCHEMA["function"]["description"]


def _commit_many_files(repo: Fixture, count: int, marker: str) -> str:
    """Commit `count` source files that all contain `marker`, and return the SHA."""
    import subprocess
    from pathlib import Path

    work = Path(repo.store.root).parent / "many"
    subprocess.run(
        ["git", "clone", "-q", str(repo.store.clone_path(repo.repo)), str(work)], check=True
    )
    for name, value in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(work), "config", name, value], check=True)

    for n in range(count):
        (work / "pkg" / f"gen{n:03d}.py").write_text(f"{marker} = {n}\n")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", "many"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "push", "-q", "origin", "HEAD:refs/heads/many"], check=True
    )
    return subprocess.run(
        ["git", "-C", str(work), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


class TestFileOutline:
    def test_lists_the_definitions_with_their_lines(self, repo: Fixture) -> None:
        sha = _commit_file(repo, "pkg/shape.py", SHAPE_SOURCE)
        result = box(repo, sha).file_outline("pkg/shape.py")

        assert "     1  class Widget" in result.text
        assert "     8  def helper(value)" in result.text
        # Qualified, because `_signature` uses the qualified name. A method's class
        # is part of what a report names, and an unqualified `build` would lose it.
        assert "     4  def Widget.build(self, size)" in result.text

    def test_reports_a_qualified_method_name(self, repo: Fixture) -> None:
        """`_walk` qualifies a method with its class, and that rule lives in
        chunks.py so two parsers cannot disagree about it."""
        sha = _commit_file(repo, "pkg/shape.py", SHAPE_SOURCE)

        assert "Widget.build" in box(repo, sha).file_outline("pkg/shape.py").text

    def test_says_so_when_a_file_defines_nothing(self, repo: Fixture) -> None:
        """`pkg/util.py` is a module of constants. An empty result would read as a
        broken tool."""
        result = box(repo).file_outline("pkg/util.py")

        assert "defines no functions or classes" in result.text
        assert not result.rejected

    def test_an_absent_path_is_reported_not_raised(self, repo: Fixture) -> None:
        assert box(repo).file_outline("pkg/invented.py").rejected

    def test_surfaces_the_path_it_outlined(self, repo: Fixture) -> None:
        assert box(repo).file_outline("pkg/core.py").paths == ("pkg/core.py",)

    def test_two_outlines_are_byte_identical(self, repo: Fixture) -> None:
        sha = _commit_file(repo, "pkg/shape.py", SHAPE_SOURCE)
        first = box(repo, sha).file_outline("pkg/shape.py").text
        second = box(repo, sha).file_outline("pkg/shape.py").text

        assert first == second

    def test_a_missing_commit_ends_the_instance(self, repo: Fixture) -> None:
        with pytest.raises(ToolError):
            box(repo, "0" * 40).file_outline("pkg/core.py")

    def test_names_a_windowed_definition_only_once(self, repo: Fixture) -> None:
        """`chunk_source` windows a chunk longer than the Window into several.

        Retrieval wants that. Navigation does not: the same definition listed twice
        wastes the agent's tokens and reads as two functions. A long docstring is
        enough to split one, because an outline asks for no bodies.
        """
        long_doc = "x " * 1600
        source = f'''def only(value):
    """{long_doc}"""
    return value
'''
        sha = _commit_file(repo, "pkg/wide.py", source)

        result = box(repo, sha).file_outline("pkg/wide.py")

        assert result.text.count("def only(value)") == 1
        assert "1 definitions" in result.text


class TestFindDefinition:
    def test_finds_a_function(self, repo: Fixture) -> None:
        sha = _commit_file(repo, "pkg/shape.py", SHAPE_SOURCE)
        result = box(repo, sha).find_definition("build")

        assert "pkg/shape.py:" in result.text
        assert result.paths == ("pkg/shape.py",)

    def test_finds_a_class(self, repo: Fixture) -> None:
        sha = _commit_file(repo, "pkg/shape.py", SHAPE_SOURCE)

        assert "class Widget" in box(repo, sha).find_definition("Widget").text

    def test_accepts_a_qualified_name(self, repo: Fixture) -> None:
        sha = _commit_file(repo, "pkg/shape.py", SHAPE_SOURCE)

        assert box(repo, sha).find_definition("Widget.build").paths == ("pkg/shape.py",)

    def test_a_symbol_that_is_not_defined_is_reported_not_raised(self, repo: Fixture) -> None:
        """It may be imported or built dynamically. That is a fact about the
        repository, not a mistake the agent made."""
        result = box(repo).find_definition("nowhere_defined")

        assert not result.rejected
        assert "No definition of" in result.text

    def test_an_empty_symbol_is_a_mistake(self, repo: Fixture) -> None:
        assert box(repo).find_definition("  ").rejected

    def test_does_not_match_a_mere_mention(self, repo: Fixture) -> None:
        """A file that calls `build()` without defining it must not be reported.

        This is the difference between `find_definition` and `search_code`, and it
        is why the tool parses rather than trusting the grep it used to narrow.

        The caller defines something ELSE on purpose. A file with no definitions at
        all cannot catch a tool that skips the name check, because the matching
        branch never runs -- which is exactly how a break test found this test
        unable to fail.
        """
        sha = _commit_file(
            repo,
            "pkg/caller.py",
            "from pkg.shape import build\n\n\ndef unrelated():\n    return build()\n",
        )
        result = box(repo, sha).find_definition("build")

        assert "pkg/caller.py" not in result.paths
        assert "unrelated" not in result.text

    def test_skips_a_file_that_cannot_be_parsed(self, repo: Fixture) -> None:
        """These repositories contain fixtures that are deliberately not valid
        Python. One of them must not fail the call."""
        sha = _commit_file(repo, "pkg/broken.py", "def build(:\n    this is not python\n")
        result = box(repo, sha).find_definition("build")

        assert "pkg/broken.py" not in result.paths

    def test_two_lookups_are_byte_identical(self, repo: Fixture) -> None:
        sha = _commit_file(repo, "pkg/shape.py", SHAPE_SOURCE)
        assert (
            box(repo, sha).find_definition("build").text
            == box(repo, sha).find_definition("build").text
        )

    def test_a_missing_commit_ends_the_instance(self, repo: Fixture) -> None:
        with pytest.raises(ToolError):
            box(repo, "0" * 40).find_definition("build")


class TestNavigationSchemas:
    def test_outline_names_its_tool(self) -> None:
        assert FILE_OUTLINE_SCHEMA["function"]["name"] == "file_outline"

    def test_find_definition_names_its_tool(self) -> None:
        assert FIND_DEFINITION_SCHEMA["function"]["name"] == "find_definition"

    def test_find_definition_says_it_reaches_outside_the_candidate_list(self) -> None:
        """The only thing rung 4 adds over rung 3, so the agent has to be told."""
        assert (
            "candidate list does not contain" in FIND_DEFINITION_SCHEMA["function"]["description"]
        )

    def test_both_are_json_serializable(self) -> None:
        import json

        assert json.dumps([FILE_OUTLINE_SCHEMA, FIND_DEFINITION_SCHEMA], sort_keys=True)


SHAPE_SOURCE = '''class Widget:
    """A widget."""

    def build(self, size):
        return size * 2


def helper(value):
    return value
'''


def _commit_file(repo: Fixture, path: str, body: str) -> str:
    """Commit one file into the bare clone and return the new SHA."""
    import subprocess
    from pathlib import Path

    work = Path(repo.store.root).parent / f"w_{abs(hash(path)) % 9999}"
    subprocess.run(
        ["git", "clone", "-q", str(repo.store.clone_path(repo.repo)), str(work)], check=True
    )
    for name, value in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(work), "config", name, value], check=True)

    target = work / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", path], check=True)
    branch = f"b{abs(hash(path)) % 9999}"
    subprocess.run(
        ["git", "-C", str(work), "push", "-q", "origin", f"HEAD:refs/heads/{branch}"], check=True
    )
    return subprocess.run(
        ["git", "-C", str(work), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
