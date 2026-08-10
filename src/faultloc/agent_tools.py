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

#: Characters a single tool result may carry. About 1,000 tokens at four
#: characters each, which is the per-result figure ADR-0009's cost arithmetic
#: assumes for eight steps. The cap makes that estimate a bound rather than a
#: guess: a request for two thousand lines cannot quietly cost the run a dollar.
MAX_RESULT_CHARS = 4000

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

    @property
    def _pin(self) -> tuple[str, str]:
        return (self.instance.repo, self.instance.base_commit)


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
