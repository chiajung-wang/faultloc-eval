"""Rung 4's read-only tools, and the contract every one of them keeps.

[ADR-0002](../../docs/adr/0002-no-code-execution.md) fixed five tools and no code
execution. This module holds `read_file` and the contract that the other four
inherit at issue 05. One tool first, on purpose: a contract proven on one tool is
a contract four more can copy, and a contract invented across five at once cannot
be attributed when it fails.

**Errors split by cause, and the split cannot be made on exception type.**
`RepoStore.read_file` raises `CommitUnavailableError` for a missing *path* and for
a missing *commit*, measured 2026-08-10. Those are opposite kinds of failure: one
is the agent guessing, the other is a broken checkout. So a tool asks
`list_files` first, which is cached per commit and is the same listing the Path
Guardrail checks. The tool and the guardrail therefore never disagree about what
exists.

A model-caused failure returns text to the agent and costs one call. Telling the
agent that a path does not exist at this commit delivers the guardrail's lesson
early and for free. An infrastructure failure raises and fails the Instance
loudly, because as an empty result it would read as "the agent searched and found
nothing" across every affected Instance.

**Output is capped, and truncation is deterministic.** A resumed run replays from
the response cache only while each step's prompt stays byte-identical, so a tool
that ordered or trimmed its output differently on two runs would make a six-hour
run pay twice. No timestamps. No absolute paths. Nothing that varies between
processes.
"""

from __future__ import annotations

from dataclasses import dataclass

from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.rungs.chunks import definitions

#: Characters a single tool result may carry. About 1,000 tokens at four
#: characters each, which is the per-result figure ADR-0009's cost arithmetic
#: assumes for eight steps. The cap makes that estimate a bound rather than a
#: guess: a request for two thousand lines cannot quietly cost the run a dollar.
MAX_RESULT_CHARS = 4000

#: Files one `search_code` call may name. Issue 01 measured the cost of this cap
#: at one Instance of 27: a Ground-Truth File was reachable but sat outside the
#: first 30 matches. The true match count goes beside the list, so a cap the agent
#: can see drives a refinement instead of a biased slice.
MAX_HITS = 30

#: Lines a single `read_file` call may return, before the character cap applies.
#: A bound on lines as well as characters, so a file of very long lines and a
#: file of very short ones both return something a model can reason about.
MAX_RESULT_LINES = 200


class ToolError(RuntimeError):
    """A tool failed for a reason the agent cannot fix.

    Distinct from a result that reports a mistake back to the agent. This one
    ends the Instance, because the alternative is a run that looks like a
    thorough search and was a broken checkout.
    """


@dataclass(frozen=True)
class ToolResult:
    """What one tool call produced.

    `paths` is the list of files this call put in front of the agent. It feeds
    Tool-Reached, which records whether a predicted path was ever surfaced by a
    tool or was named from memory. The Verified Set predates the training cutoff,
    so that distinction is the difference between localization and recall.
    """

    text: str
    paths: tuple[str, ...] = ()
    truncated: bool = False
    #: The agent made a mistake it can correct on its next call. Counted, and not
    #: absorbed, because a rung whose tools all fail still produces a ranking.
    rejected: bool = False


def _fit(rendered: list[str]) -> tuple[str, bool]:
    """Join lines within both caps, and say whether anything was cut."""
    kept: list[str] = []
    used = 0
    for line in rendered[:MAX_RESULT_LINES]:
        if used + len(line) + 1 > MAX_RESULT_CHARS:
            break
        kept.append(line)
        used += len(line) + 1
    return "\n".join(kept), len(kept) < len(rendered)


def _clip(lines: list[str], first: int) -> tuple[str, bool]:
    """Render numbered lines within both caps, and say whether anything was cut.

    Line numbers are included because they are how the agent asks for the next
    range, and because `git grep -n` reports them the same way at issue 05.
    """
    kept: list[str] = []
    used = 0
    truncated = False

    for offset, line in enumerate(lines[:MAX_RESULT_LINES]):
        rendered = f"{first + offset:>6}  {line}"
        if used + len(rendered) + 1 > MAX_RESULT_CHARS:
            truncated = True
            break
        kept.append(rendered)
        used += len(rendered) + 1

    truncated = truncated or len(lines) > len(kept)
    return "\n".join(kept), truncated


@dataclass(frozen=True)
class Toolbox:
    """The tools for one Instance, with the repository state bound.

    The agent supplies a path and a range. It never supplies the repository or
    the commit, because those are the Instance and not a decision the model gets
    to make.
    """

    store: RepoStore
    instance: Instance

    def read_file(self, path: str, start: int = 1, end: int = MAX_RESULT_LINES) -> ToolResult:
        """Lines `start` to `end` of `path`, at the Instance's `base_commit`."""
        if not path or not isinstance(path, str):
            return ToolResult("Give a repository-relative file path.", rejected=True)
        if start < 1:
            return ToolResult(f"start must be 1 or greater, got {start}.", rejected=True)
        if end < start:
            return ToolResult(f"end ({end}) is before start ({start}).", rejected=True)

        cleaned = path.strip().lstrip("./")

        # Existence first. This is the only way to tell a path the agent invented
        # from a checkout that is broken, and it is the same listing the Path
        # Guardrail uses.
        try:
            present = {entry.path for entry in self.store.list_files(*self._pin)}
        # Broad on purpose, and re-raised rather than swallowed. Anything that
        # stops a commit's tree from listing is a broken checkout, not something
        # the agent can fix by asking differently.
        except Exception as broken:
            raise ToolError(f"cannot list {self.instance.repo} at {self._pin[1]}") from broken

        if cleaned not in present:
            return ToolResult(
                f"No file at `{cleaned}` in {self.instance.repo} at this commit.",
                rejected=True,
            )

        body = self.store.read_file(*self._pin, cleaned)
        lines = body.splitlines()
        window = lines[start - 1 : end]

        if not window:
            return ToolResult(
                f"`{cleaned}` has {len(lines)} lines, so there is nothing at {start}-{end}.",
                paths=(cleaned,),
                rejected=True,
            )

        rendered, truncated = _clip(window, start)
        header = f"{cleaned} lines {start}-{start + len(window) - 1} of {len(lines)}"
        if truncated:
            header += " (cut to fit; ask for a smaller range)"

        return ToolResult(f"{header}\n{rendered}", paths=(cleaned,), truncated=truncated)

    def search_code(self, pattern: str) -> ToolResult:
        """Source files containing `pattern` literally, at the pinned commit."""
        cleaned = (pattern or "").strip()
        if not cleaned:
            return ToolResult("Give text to search for.", rejected=True)

        try:
            hits = self.store.grep(*self._pin, cleaned)
        except Exception as broken:
            raise ToolError(f"cannot search {self.instance.repo} at {self._pin[1]}") from broken

        if not hits:
            # Not a mistake. A search that finds nothing is a fact about the
            # repository, and the agent needs it in order to try another term.
            return ToolResult(f"No source file contains `{cleaned}` at this commit.")

        shown = hits[:MAX_HITS]
        header = f"{len(hits)} source files contain `{cleaned}`"
        if len(hits) > len(shown):
            header += f", showing the first {len(shown)} in repository order"
        return ToolResult(
            f"{header}:\n" + "\n".join(f"  {path}" for path in shown),
            paths=shown,
            truncated=len(hits) > len(shown),
        )

    def file_outline(self, path: str) -> ToolResult:
        """The definitions in `path`, with their lines and without their bodies.

        The cheapest tool in tokens, and the natural follow-up to a search hit:
        find a file, outline it, then read only the range that matters.
        """
        found = self._require(path)
        if isinstance(found, ToolResult):
            return found

        definitions = self._definitions(found)
        if not definitions:
            return ToolResult(f"`{found}` defines no functions or classes.", paths=(found,))

        rendered = [f"{chunk.line:>6}  {chunk.signature}" for chunk in definitions]
        body, truncated = _fit(rendered)
        header = f"{found}: {len(definitions)} definitions"
        if truncated:
            header += " (cut to fit)"
        return ToolResult(f"{header}\n{body}", paths=(found,), truncated=truncated)

    def find_definition(self, symbol: str) -> ToolResult:
        """Where `symbol` is defined, across the repository at the pinned commit.

        The tool most likely to reach a file the Candidate Set never held, because
        it follows structure rather than similarity -- and reaching past the list
        is the only thing rung 4 adds over rung 3.

        `git grep` narrows the search before any parsing. Parsing every source
        file would be thousands of `ast.parse` calls per call on django, and the
        name has to appear literally in a file that defines it.
        """
        wanted = (symbol or "").strip()
        if not wanted:
            return ToolResult("Give a function or class name.", rejected=True)

        # Narrow on the LAST segment. A qualified name never appears literally in
        # the file that defines it: the source says `class Widget` and then `def
        # build`, so a grep for `Widget.build` finds nothing at the definition
        # site. The bare name does appear, and the parse below is what confirms it
        # is a definition rather than a mention.
        bare = wanted.rpartition(".")[2]
        try:
            candidates = self.store.grep(*self._pin, bare)
        except Exception as broken:
            raise ToolError(f"cannot search {self.instance.repo} at {self._pin[1]}") from broken

        hits: list[tuple[str, int, str]] = []
        for candidate in candidates:
            for chunk in self._definitions(candidate):
                if chunk.name == wanted or chunk.name.endswith(f".{wanted}"):
                    hits.append((candidate, chunk.line, chunk.signature))

        if not hits:
            return ToolResult(
                f"No definition of `{wanted}` found at this commit. "
                "It may be imported from elsewhere, or defined dynamically."
            )

        body, truncated = _fit([f"  {p}:{line}  {sig}" for p, line, sig in hits[:MAX_HITS]])
        header = f"{len(hits)} definitions of `{wanted}`"
        if len(hits) > MAX_HITS:
            header += f", showing the first {MAX_HITS}"
        return ToolResult(
            f"{header}:\n{body}",
            paths=tuple(dict.fromkeys(p for p, _, _ in hits[:MAX_HITS])),
            truncated=truncated or len(hits) > MAX_HITS,
        )

    def _definitions(self, path: str) -> tuple:
        """Named definitions in one file, in source order.

        `chunks.definitions` walks the tree and does not window. A window carries
        no signature and no line, and it renames the pieces to `name#0` and
        `name#1`, so an outline built on windows lists a long definition as
        nameless rubbish. A test with a 3,200-character docstring found exactly
        that.

        The qualified-name and nesting rules stay in `chunks.py`, written once, so
        two parsers cannot drift apart about what a definition is.
        """
        return definitions(self.store.read_file(*self._pin, path))

    def _require(self, path: str) -> str | ToolResult:
        """The cleaned path, or the result to send back instead.

        Existence is checked against `list_files`, which is the only way to tell a
        path the agent invented from a broken checkout: `RepoStore` raises the
        same exception for both.
        """
        if not path or not isinstance(path, str):
            return ToolResult("Give a repository-relative file path.", rejected=True)

        cleaned = path.strip().lstrip("./")
        try:
            present = {entry.path for entry in self.store.list_files(*self._pin)}
        except Exception as broken:
            raise ToolError(f"cannot list {self.instance.repo} at {self._pin[1]}") from broken

        if cleaned not in present:
            return ToolResult(
                f"No file at `{cleaned}` in {self.instance.repo} at this commit.",
                rejected=True,
            )
        return cleaned

    @property
    def _pin(self) -> tuple[str, str]:
        return (self.instance.repo, self.instance.base_commit)


SEARCH_CODE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_code",
        "description": (
            "Find source files containing an exact string, at the repository's pinned commit. "
            "The match is literal, so brackets and dots mean themselves. "
            "Search for an identifier, a dotted name, or a function name. "
            "Do NOT paste an error message: a report shows the rendered message and the code "
            "holds the template, so the message itself appears in no file. Search the "
            "identifiers inside it instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Exact text to find, for example get_queryset or Model.objects",
                }
            },
            "required": ["pattern"],
        },
    },
}

FILE_OUTLINE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "file_outline",
        "description": (
            "List the functions and classes a file defines, with their line numbers "
            "and without their bodies. Cheapest way to see a file's shape. "
            "Use it after a search hit, then read only the range that matters."
        ),
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Repository-relative path."}},
            "required": ["path"],
        },
    },
}

FIND_DEFINITION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_definition",
        "description": (
            "Find where a function or class is defined, anywhere in the repository. "
            "Give a bare name such as get_queryset, or a qualified one such as "
            "QuerySet.filter. Use it to follow a call or an import to the file that "
            "owns it, which is often a file the candidate list does not contain."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Function or class name, for example get_queryset",
                }
            },
            "required": ["symbol"],
        },
    },
}

#: The tool surface the model sees, in OpenAI function format. Written as plain
#: data rather than taken from a decorator, so this module imports no framework
#: and stays testable without the `agent` extra. It is also part of the response
#: cache key, so its shape has to be stable and serializable.
READ_FILE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read numbered lines from a source file at the repository's pinned commit. "
            "Use it to check whether a candidate file really contains the reported fault, "
            "and to find the imports and calls that lead to other files."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Repository-relative path, for example lib/matplotlib/dates.py",
                },
                "start": {"type": "integer", "description": "First line, 1-based."},
                "end": {"type": "integer", "description": "Last line, inclusive."},
            },
            "required": ["path"],
        },
    },
}
