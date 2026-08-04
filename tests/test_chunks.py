"""Tests for AST Chunk extraction and chunk-to-file aggregation.

Two things here are load-bearing beyond this module. Every file must yield at
least one chunk, or it silently leaves the candidate set and caps accuracy in a
way that reads as weak retrieval. And the aggregation rule is inherited
unchanged by rung 2, so a change to it invalidates the ablation rather than just
moving a number.
"""

from __future__ import annotations

from faultloc.rungs.chunks import Chunk, aggregate_by_file, chunk_source


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

    def test_body_is_not_indexed(self) -> None:
        """Bodies are mechanical and near-identical across a codebase; indexing
        them would swamp the docstring, which is the only prose in the file."""
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
