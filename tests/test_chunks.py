"""Tests for AST Chunk extraction and chunk-to-file aggregation.

Two things here are load-bearing beyond this module. Every file must yield at
least one chunk, or it silently leaves the candidate set and caps accuracy in a
way that reads as weak retrieval. And the aggregation rule is inherited
unchanged by rung 2, so a change to it invalidates the ablation rather than just
moving a number.
"""

from __future__ import annotations

from faultloc.rungs.chunks import WINDOW_CHARS, Chunk, aggregate_by_file, chunk_source


def names(source: str) -> list[str]:
    return [c.name for c in chunk_source(source)]


class TestExtraction:
    def test_one_chunk_per_function_and_class(self) -> None:
        source = "def alpha(): ...\n\n\nclass Beta:\n    pass\n"
        assert names(source) == ["alpha", "Beta"]

    def test_methods_carry_their_class(self) -> None:
        """A report naming both the class and the method is common; an
        unqualified `filter` would lose half of that signal."""
        source = "class QuerySet:\n    def filter(self): ...\n"
        assert names(source) == ["QuerySet", "QuerySet.filter"]

    def test_nested_definitions_are_chunked(self) -> None:
        source = "def outer():\n    def inner(): ...\n"
        assert names(source) == ["outer", "outer.inner"]

    def test_async_definitions_are_not_dropped(self) -> None:
        """`AsyncFunctionDef` is a separate grammar node; missing it would drop
        every async definition without any error."""
        assert names("async def fetch(): ...\n") == ["fetch"]

    def test_signature_keeps_arguments_and_return_type(self) -> None:
        (chunk,) = chunk_source("def rotate(text, angle=0) -> str: ...\n")
        assert chunk.signature == "def rotate(text, angle=0) -> str"

    def test_class_signature_keeps_bases(self) -> None:
        (chunk,) = chunk_source("class Widget(Base): pass\n")
        assert chunk.signature == "class Widget(Base)"

    def test_docstring_is_captured(self) -> None:
        (chunk,) = chunk_source('def rotate():\n    """Turn a label sideways."""\n')
        assert "Turn a label sideways." in chunk.text

    def test_body_is_not_indexed_by_default(self) -> None:
        """The original design: bodies were expected to swamp the docstring,
        which is the only prose in the file. Issue 01 measured that costing
        ~9pp of Recall@5, so it is now a flag rather than an assumption."""
        (chunk,) = chunk_source("def rotate():\n    unmistakable_body_token = 1\n")
        assert "unmistakable_body_token" not in chunk.text

    def test_decorators_do_not_break_the_signature(self) -> None:
        (chunk,) = chunk_source("@property\ndef value(self): ...\n")
        assert chunk.signature == "def value(self)"


class TestNoFileIsInvisible:
    """Every file must produce at least one retrievable chunk.

    A file absent from the candidate set can never be predicted, so its
    instances are unwinnable -- and the failure is indistinguishable from bad
    ranking in every metric the project reports.
    """

    def test_unparseable_python_falls_back_to_the_whole_file(self) -> None:
        (chunk,) = chunk_source("print 'python 2'\n")
        assert chunk.kind == "file"
        assert "python 2" in chunk.text

    def test_non_python_source_falls_back_to_the_whole_file(self) -> None:
        """The source filter keeps `.c`, `.pyx`, and `.js` files because real
        fixes touch them; none of them parse as Python."""
        (chunk,) = chunk_source("int main(void) { return 0; }\n")
        assert chunk.kind == "file"
        assert "main" in chunk.text

    def test_module_without_definitions_falls_back_to_the_whole_file(self) -> None:
        """Parses cleanly, defines nothing -- a constants table is still an
        answer some instance needs."""
        (chunk,) = chunk_source("SHARED = 1\nDEFAULT_TIMEOUT = 30\n")
        assert chunk.kind == "file"
        assert "DEFAULT_TIMEOUT" in chunk.text

    def test_empty_file_still_yields_a_chunk(self) -> None:
        assert len(chunk_source("")) == 1

    def test_null_bytes_do_not_raise(self) -> None:
        """Blobs are decoded with `errors="replace"`, so a binary-ish file can
        reach the parser as text containing nulls -- where `ast.parse` raises
        `ValueError`, not `SyntaxError`.

        The source defines a function on purpose: a file with no definitions
        would fall back anyway, and the test would pass whether or not the
        exception was handled.
        """
        (chunk,) = chunk_source("def f():\n    data = '\x00'\n")
        assert chunk.kind == "file"


class TestIncludeBodies:
    def test_body_is_indexed_when_asked(self) -> None:
        (chunk,) = chunk_source(
            "def rotate():\n    unmistakable_body_token = 1\n", include_bodies=True
        )
        assert "unmistakable_body_token" in chunk.text

    def test_a_class_does_not_carry_its_methods_text(self) -> None:
        """Methods are chunks in their own right. A class carrying them would
        index the same text at every level of nesting, inflating the corpus and
        making the class match anything any of its methods matches."""
        source = (
            "class Widget:\n"
            '    """A widget."""\n'
            "    registry = {}\n"
            "    def rotate(self):\n"
            "        method_only_token = 1\n"
        )
        widget, rotate = chunk_source(source, include_bodies=True)

        assert "registry" in widget.text
        assert "method_only_token" not in widget.text
        assert "method_only_token" in rotate.text

    def test_module_level_code_is_still_unindexed(self) -> None:
        """A cost of chunking that bodies do not fix: a file with definitions
        never indexes the statements outside them."""
        source = "MODULE_LEVEL_TOKEN = 1\n\n\ndef rotate():\n    pass\n"
        (chunk,) = chunk_source(source, include_bodies=True)
        assert "MODULE_LEVEL_TOKEN" not in chunk.text

    def test_the_fallback_is_unaffected(self) -> None:
        """A file with no definitions already carries its whole text."""
        source = "SHARED = 1\n"
        assert chunk_source(source)[0].text == chunk_source(source, include_bodies=True)[0].text


class TestWindowing:
    def test_short_chunks_are_left_alone(self) -> None:
        assert len(chunk_source("def f():\n    pass\n")) == 1

    def test_long_chunks_are_split_not_truncated(self) -> None:
        """The failure this exists to prevent: an embedding model with a
        512-token limit silently discards everything past it, and 1.6% of
        chunks carry 55% of the corpus."""
        source = "".join(f"CONSTANT_{i} = {i}\n" for i in range(400))
        chunks = chunk_source(source)

        assert len(chunks) > 1
        rejoined = "".join(c.text for c in chunks)
        assert "CONSTANT_0" in rejoined
        assert "CONSTANT_399" in rejoined

    def test_no_window_exceeds_the_budget(self) -> None:
        source = "".join(f"CONSTANT_{i} = {i}\n" for i in range(400))
        assert all(len(c.text) <= WINDOW_CHARS for c in chunk_source(source))

    def test_windows_do_not_repeat_the_signature(self) -> None:
        """Signature and docstring are inside the split text already; carrying
        them on every window would index them once per window."""
        body = "".join(f"    value_{i} = {i}\n" for i in range(400))
        chunks = chunk_source(f"def rotate():\n{body}", include_bodies=True)

        assert len(chunks) > 1
        assert sum(1 for c in chunks if "def rotate" in c.text) == 1

    def test_a_single_over_long_line_is_hard_split(self) -> None:
        """Minified and generated files exist. One unbounded chunk would be
        exactly the document shape windowing is here to prevent."""
        chunks = chunk_source("X = '" + "a" * (WINDOW_CHARS * 3) + "'\n")

        assert len(chunks) > 1
        assert all(len(c.text) <= WINDOW_CHARS for c in chunks)

    def test_windows_are_deterministic(self) -> None:
        source = "".join(f"CONSTANT_{i} = {i}\n" for i in range(400))
        assert [c.text for c in chunk_source(source)] == [c.text for c in chunk_source(source)]


class TestAggregation:
    def test_a_file_scores_as_its_best_chunk(self) -> None:
        assert aggregate_by_file([0.1, 9.0, 0.2]) == 9.0

    def test_extra_irrelevant_chunks_do_not_dilute_a_match(self) -> None:
        """`mean` would rank a small file matching nothing above a large file
        containing the answer."""
        assert aggregate_by_file([9.0] + [0.0] * 199) == aggregate_by_file([9.0])

    def test_extra_weak_chunks_do_not_accumulate(self) -> None:
        """`sum` would let a long file outscore the answer by being long."""
        assert aggregate_by_file([0.1] * 100) < aggregate_by_file([1.0])

    def test_a_file_with_no_chunks_scores_zero(self) -> None:
        assert aggregate_by_file([]) == 0.0

    def test_negative_scores_are_not_clamped(self) -> None:
        """BM25 emits negative scores for terms in most of the corpus. Treating
        the best of them as 0.0 would tie every such file with the ones that had
        nothing to say."""
        assert aggregate_by_file([-3.0, -1.0]) == -1.0


class TestChunkText:
    def test_path_is_not_part_of_chunk_text(self) -> None:
        """Path belongs to the file, not the chunk. The same blob can live at
        two paths, and a cache keyed by blob SHA must not depend on which one
        was seen first."""
        chunk = Chunk(name="f", kind="function", signature="def f()", docstring="Doc.")
        assert chunk.text == "def f()\nDoc."
