"""The Path Guardrail, and how rung 4's answer is assembled.

`CONTEXT.md` defines the guardrail as a check on **existence**, and says plainly
that it never asks about membership. That distinction is the whole reason rung 4
can score above the Candidate Set's 88.9% ceiling.

**An Off-List Path is not a hallucination.** Rung 3 discards a path the Candidate
Set does not hold, because a reranker reorders and never adds. Rung 4 keeps one
that exists, because reaching past the list is the only thing rung 4 adds. Issue
01 measured how much that is worth: of 6 Off-List Paths recovered from a cached
rung-3 cell, **5 existed**, and all five were `sphinx` -- the repo sitting exactly
on its own ceiling. Treating them as hallucinations would have thrown away five
real files.

**The assembly never shrinks the list the ceiling was measured on.** Whatever the
agent says goes first. Every candidate it never mentioned follows, in Candidate
Set order. So a run that answers badly scores like the rung below it rather than
scoring zero, and a run that answers well is not capped by the list it started
from.

Top-1 and Recall@3 and Recall@5 all read positions inside 5, so list length past
that changes no published metric. There is no truncation constant here to justify.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.scoring import normalize_path


@dataclass(frozen=True)
class Guardrail:
    """Does this path exist in the repository at the Instance's `base_commit`?

    Checked against the same `list_files` listing the tools use, so a tool and
    the guardrail can never disagree about what exists. That listing is cached
    per commit, and a commit's tree is immutable, so the check is free after the
    first call.
    """

    store: RepoStore
    instance: Instance

    def split(self, paths: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Separate the paths that exist from the paths that do not.

        Order is preserved on both sides, because the surviving order is the
        agent's ranking and the rejected order is what the retry message quotes
        back. Duplicates are dropped here rather than later: `Prediction` refuses
        them, and a path named twice is one judgement, not two.
        """
        present = {
            normalize_path(entry.path)
            for entry in self.store.list_files(self.instance.repo, self.instance.base_commit)
        }

        kept: list[str] = []
        absent: list[str] = []
        seen: set[str] = set()

        for path in paths:
            cleaned = normalize_path(str(path).strip())
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            (kept if cleaned in present else absent).append(cleaned)

        return tuple(kept), tuple(absent)


@dataclass(frozen=True)
class Answer:
    """Rung 4's final ranking, with everything the entry has to disclose."""

    ranking: tuple[str, ...]
    #: Accepted, exists at `base_commit`, and the Candidate Set never held it.
    #: This is the measure of whether rung 4 earned its rung.
    off_list: tuple[str, ...]
    #: Named and absent at `base_commit`. The Path Guardrail's catch rate.
    hallucinated: tuple[str, ...]
    #: The agent contributed nothing usable, so the ranking is the Candidate Set
    #: order. It scores like the rung below, which is why it is never silent.
    fell_back: bool


def assemble(
    agent_order: Sequence[str],
    candidates: Sequence[str],
    hallucinated: Sequence[str] = (),
) -> Answer:
    """The agent's order first, then every candidate it did not mention.

    `agent_order` has already passed the guardrail. Nothing here checks existence
    a second time.
    """
    ranked: list[str] = []
    seen: set[str] = set()

    for path in list(agent_order) + list(candidates):
        cleaned = normalize_path(str(path))
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ranked.append(cleaned)

    known = {normalize_path(str(path)) for path in candidates}
    return Answer(
        ranking=tuple(ranked),
        off_list=tuple(p for p in agent_order if normalize_path(str(p)) not in known),
        hallucinated=tuple(hallucinated),
        fell_back=not agent_order,
    )


REJECTED_PATHS = (
    "These paths do not exist in the repository at this commit: {paths}. "
    "Call {submit} again with paths that do exist."
)

#: The terminal action, in the same plain-data form as the read-only tools. It is
#: not a sixth tool: ADR-0002's ceiling counts tools that gather information, and
#: this gathers none. It also does not count against the tool-call cap.
SUBMIT_RANKING_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_ranking",
        "description": (
            "Answer. Give every candidate path in order, most likely to need the fix first. "
            "Include any file you found with the tools that was not in the candidate list. "
            "Every path must exist in the repository at this commit."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Repository-relative paths, most likely first.",
                }
            },
            "required": ["paths"],
        },
    },
}
