"""AST Chunks: the index unit rungs 2 and above retrieve over.

A whole file is a poor retrieval unit. `django/db/models/query.py` is 2,600
lines covering dozens of unrelated behaviours, and a report about one of them
matches the file only weakly once every other behaviour's vocabulary is averaged
in. Chunking splits that file into the units a person would name -- one function
or class each -- so a match is against something the size of an answer.

A chunk's searchable text is its **signature, docstring, and path**, not its
body. Bodies are mechanical (`for i in range(n)`), near-identical across a
codebase, and would swamp the one place in source code where a human wrote
English about intent. Reports are prose, so the docstring is the bridge.

Two deliberate consequences, both costs of chunking rather than bugs:

- **Module-level code is not indexed** when a file also defines functions. A
  constants table or a top-level configuration block becomes unretrievable.
- **The candidate set grows by roughly an order of magnitude**, which changes
  what a Recall@5 number means relative to rung 1's.

Both are exactly what the BM25-over-chunks ablation is built to price. See
`.scratch/m3-embedding-retrieval/PRD.md`.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass

#: Nodes that become a chunk. `AsyncFunctionDef` is separate from `FunctionDef`
#: in the grammar, and omitting it would silently drop every async definition.
DEFINITION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


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
    #: Raw contents, populated only by the whole-file fallback below. A parsed
    #: definition never carries its body -- that is the point of chunking.
    content: str = ""

    @property
    def text(self) -> str:
        """Everything about this chunk that is worth matching against.

        Path is excluded on purpose: it belongs to the file, not the chunk, and
        the same content can live at two paths. Callers add it, which keeps
        chunk extraction cacheable by blob SHA.
        """
        return "\n".join(part for part in (self.signature, self.docstring, self.content) if part)


def chunk_source(source: str) -> tuple[Chunk, ...]:
    """Chunks for one file's contents.

    Never returns empty. A file that cannot be parsed -- Python 2 syntax, a
    deliberately broken test fixture, or any of the `.pyx`, `.c`, and `.js`
    files the source filter keeps -- falls back to a single whole-file chunk, as
    does a valid module that simply defines nothing.

    The fallback is not a nicety. A file with no chunks is absent from the
    candidate set, so no prediction naming it can ever be correct. That is a
    silent ceiling on accuracy which looks identical to weak retrieval, and it
    would be diagnosed as a bad retriever rather than a missing document.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):  # ValueError: source containing null bytes
        return (_whole_file(source),)

    chunks = tuple(_walk(tree.body, prefix=""))
    return chunks or (_whole_file(source),)


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


def _walk(body: list[ast.stmt], *, prefix: str) -> Iterable[Chunk]:
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
        )
        yield from _walk(node.body, prefix=f"{name}.")


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
