"""AST Chunks: the index unit rungs 2 and above retrieve over.

A whole file is a poor retrieval unit. `django/db/models/query.py` is 2,600
lines covering dozens of unrelated behaviours, and a report about one of them
matches the file only weakly once every other behaviour's vocabulary is averaged
in. Chunking splits that file into the units a person would name -- one function
or class each -- so a match is against something the size of an answer.

A chunk's searchable text is its **signature, docstring, and path**, and
optionally its **body**. Excluding the body was the original design -- bodies
are mechanical (`for i in range(n)`) and were expected to swamp the docstring,
the one place in source code where a human wrote English about intent. Issue 01
measured that choice costing ~9pp of Recall@5, because bug reports quote body
tokens constantly: called functions, locals, string literals, error messages,
traceback frames. `include_bodies` makes it a measurable variable rather than an
assumption; see issue 06.

Every chunk is **windowed** to a bounded length. A file with no definitions
falls back to a whole-file chunk, and those average 16,296 characters against
191 for a function -- 1.6% of chunks carrying 55% of the corpus. Handing one to
an embedding model with a 512-token limit discards everything past the limit
silently, and buying a longer context does not fix it: 8192 tokens still drops a
quarter of the corpus, and 32k costs 487 hours to index against 2.8 (ADR-0007).
Splitting instead of truncating keeps the text at the small model's speed.

One deliberate consequence remains a cost of chunking rather than a bug:
**module-level code is not indexed** when a file also defines functions, so a
constants table or a top-level configuration block becomes unretrievable.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass

#: Nodes that become a chunk. `AsyncFunctionDef` is separate from `FunctionDef`
#: in the grammar, and omitting it would silently drop every async definition.
DEFINITION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

#: Maximum characters in one chunk's text. Sized to the pinned embedding
#: model's 512-token limit at roughly four characters per token (ADR-0007), so
#: a window survives embedding without the tokenizer silently dropping its tail.
#:
#: Applied to the lexical rung as well as the dense one, deliberately. The two
#: rungs are compared to each other, and a chunk definition that differed
#: between them would make that delta measure the definition rather than the
#: matching function.
WINDOW_CHARS = 2048


@dataclass(frozen=True)
class Chunk:
    """One retrievable unit of a file.

    `name` is qualified (`QuerySet.filter`), so the class a method belongs to is
    part of what can be matched -- a report naming both the class and the method
    is common, and an unqualified `filter` would lose half of that.
    """

    name: str
    kind: str
    signature: str
    docstring: str
    #: Raw contents: the whole file for a fallback chunk, or the definition's
    #: own source when `include_bodies` is set. Empty otherwise.
    content: str = ""

    @property
    def text(self) -> str:
        """Everything about this chunk that is worth matching against.

        Path is excluded on purpose: it belongs to the file, not the chunk, and
        the same content can live at two paths. Callers add it, which keeps
        chunk extraction cacheable by blob SHA.
        """
        return "\n".join(part for part in (self.signature, self.docstring, self.content) if part)


def chunk_source(source: str, *, include_bodies: bool = False) -> tuple[Chunk, ...]:
    """Chunks for one file's contents, each windowed to `WINDOW_CHARS`.

    Never returns empty. A file that cannot be parsed -- Python 2 syntax, a
    deliberately broken test fixture, or any of the `.pyx`, `.c`, and `.js`
    files the source filter keeps -- falls back to a single whole-file chunk, as
    does a valid module that simply defines nothing.

    The fallback is not a nicety. A file with no chunks is absent from the
    candidate set, so no prediction naming it can ever be correct. That is a
    silent ceiling on accuracy which looks identical to weak retrieval, and it
    would be diagnosed as a bad retriever rather than a missing document.

    With `include_bodies`, a definition carries **its own** source and not that
    of the definitions nested inside it -- those are chunks in their own right,
    and including them would index the same text at every level of nesting,
    inflating both the corpus and the enclosing chunk's length.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):  # ValueError: source containing null bytes
        return _windowed(_whole_file(source))

    lines = source.splitlines() if include_bodies else []
    chunks = tuple(_walk(tree.body, prefix="", lines=lines))
    if not chunks:
        return _windowed(_whole_file(source))

    return tuple(window for chunk in chunks for window in _windowed(chunk))


def _windowed(chunk: Chunk, budget: int = WINDOW_CHARS) -> tuple[Chunk, ...]:
    """Split an over-long chunk into windows, rather than let it be truncated.

    Splits on line boundaries so an identifier is never cut in half; a single
    line longer than the budget is hard-split, because a minified or generated
    file must not become one unbounded chunk.

    No overlap. Aggregation takes the *best* chunk of a file (`aggregate_by_file`),
    so a query matching across a boundary still scores in both windows and the
    file's rank is unaffected -- overlap would inflate the corpus to buy back
    something the aggregation rule already covers.
    """
    text = chunk.text
    if len(text) <= budget:
        return (chunk,)

    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        while len(line) > budget:
            if current:
                pieces.append("".join(current))
                current, size = [], 0
            pieces.append(line[:budget])
            line = line[budget:]
        if current and size + len(line) > budget:
            pieces.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        pieces.append("".join(current))

    # Windows carry their text in `content` alone: the signature and docstring
    # are already inside the split text, and repeating them would index them
    # once per window.
    return tuple(
        Chunk(
            name=f"{chunk.name}#{i}" if chunk.name else f"#{i}",
            kind=chunk.kind,
            signature="",
            docstring="",
            content=piece,
        )
        for i, piece in enumerate(pieces)
    )


def aggregate_by_file(scores: Iterable[float]) -> float:
    """A file's score, given the scores of its chunks: the best one.

    `max` is chosen over `sum` and `mean` because it is the only one that
    answers the question being asked. "Which file must change" is settled by a
    file containing *one* strongly matching function; the other forty are not
    evidence against it.

    - `sum` rewards size. A 200-function module accumulates score by being long,
      which is the length bias BM25's own normalisation already fights.
    - `mean` inverts that: one perfect match diluted by 199 irrelevant siblings
      scores below a small file that matches nothing in particular.

    **Rung 2 must reuse this function unchanged.** The ablation's whole purpose
    is that the lexical and dense rungs differ in exactly one variable. If they
    aggregated differently, their delta would be confounded and unattributable,
    and the milestone would have measured nothing.
    """
    best = None
    for score in scores:
        if best is None or score > best:
            best = score
    return 0.0 if best is None else best


def _whole_file(source: str) -> Chunk:
    return Chunk(name="", kind="file", signature="", docstring="", content=source)


def _walk(body: list[ast.stmt], *, prefix: str, lines: list[str]) -> Iterable[Chunk]:
    """Definitions in source order, descending into classes and functions.

    Nested definitions are chunked too. A closure or an inner helper class is
    still where a bug lives, and its enclosing name travels with it.
    """
    for node in body:
        if not isinstance(node, DEFINITION_NODES):
            continue

        name = f"{prefix}{node.name}"
        yield Chunk(
            name=name,
            kind="class" if isinstance(node, ast.ClassDef) else "function",
            signature=_signature(node, name),
            docstring=ast.get_docstring(node) or "",
            content=_own_source(node, lines) if lines else "",
        )
        yield from _walk(node.body, prefix=f"{name}.", lines=lines)


def _own_source(node: ast.stmt, lines: list[str]) -> str:
    """A definition's source, minus the definitions nested directly inside it.

    A class body contains its methods, and each method is already a chunk. Left
    whole, a class would index every method's text a second time -- doubling the
    corpus for deep files and making the class chunk match anything any of its
    methods matches, which defeats the point of chunking.
    """
    start = node.lineno
    end = node.end_lineno or start

    nested: set[int] = set()
    for child in node.body:
        if isinstance(child, DEFINITION_NODES):
            nested.update(range(child.lineno, (child.end_lineno or child.lineno) + 1))

    return "\n".join(lines[n - 1] for n in range(start, end + 1) if n not in nested)


def _signature(node: ast.stmt, name: str) -> str:
    """The definition line, rebuilt from the tree rather than sliced from text.

    Reading it back out of the source would have to cope with decorators,
    continuation lines, and comments; `ast.unparse` already knows the grammar.
    """
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(ast.unparse(base) for base in node.bases)
        return f"class {name}({bases})" if bases else f"class {name}"

    assert isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"def {name}({ast.unparse(node.args)}){returns}"
