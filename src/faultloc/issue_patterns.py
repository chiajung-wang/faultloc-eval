"""Searchable patterns pulled out of an issue report, grouped by kind.

This exists to answer one question, and it is the question rung 4 depends on.
The union Candidate Set's hit@20 is 88.9%, so about 27 dev-split Instances hold
no Ground-Truth File in the list at all. Those Instances are rung 4's whole
target, because no reranker can be right on them. A read-only tool reaches such
a file only if the report and the file share a searchable string.

**Crude on purpose.** A clever extractor would make the measurement a property
of the extractor rather than of the corpus. The agent writes its own patterns,
so a hand-tuned heuristic here measures the wrong thing. What this measures is
whether the *information* is present. It is a necessary condition, and not a
sufficient one: a pattern that `git grep` cannot follow, an agent cannot follow
either, and a pattern it can follow the agent may still never write.

The four kinds are separate because a single reachability number would not tell
anybody what to build. Rung 4's `search_code` has to accept the kinds that
actually lead to the answer, and M3 established that bug reports quote body
tokens constantly.
"""

from __future__ import annotations

import re

#: Patterns kept per kind, in first-occurrence order. A cap is necessary because
#: the measurement runs one `git grep` per pattern. First-occurrence rather than
#: alphabetical: a report states its subject early, and sorting would cap by
#: spelling. Both orders are deterministic, and only one of them is meaningful.
PER_KIND = 10

ERROR_STRINGS = "error strings"
DOTTED_NAMES = "dotted names"
IDENTIFIERS = "identifiers"
TRACEBACK_PATHS = "traceback paths"

KINDS = (ERROR_STRINGS, DOTTED_NAMES, IDENTIFIERS, TRACEBACK_PATHS)

#: The text after an exception's name. Reports paste rendered messages, and the
#: code holds a template, so a literal search often fails here. That failure is
#: the finding rather than a flaw: it is the reason `search_code` cannot be the
#: only tool.
_ERROR = re.compile(r"\b\w*(?:Error|Exception|Warning)\b\s*:\s*([^\n]+)")

#: `django.db.models.Field`, `np.ma.masked`. The most specific thing a report
#: usually contains, and the cheapest to search for.
#:
#: Every segment must start with a letter or an underscore, and that is what
#: rejects a version string. `1.11.3` matches nothing, and `numpy.2` matches
#: nothing. An explicit digit check stood here until a test proved it could
#: never fire.
_DOTTED = re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")

#: `get_queryset` and `HTTPResponse`. An underscore or an internal capital is
#: the whole test. Without one, the extractor would collect ordinary English
#: words and grep would match every file in the repository.
_SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_CAMEL = re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b")

#: Extensions that make a dotted string a file rather than a name. `_DOTTED`
#: matches `models.query.py` inside `django/db/models/query.py`, and comparing
#: against the extracted paths does not catch it, because the fragment is not
#: the path. Counting it under both kinds would credit dotted names with a reach
#: that traceback paths produced.
FILE_SUFFIXES = ("py", "pyx", "pxd", "c", "cc", "cpp", "h", "js")

_PATH = re.compile(rf"\b[\w][\w./-]*\.(?:{'|'.join(FILE_SUFFIXES)})\b")

#: A shorter string matches too much to locate anything.
MIN_TOKEN = 4
MIN_MESSAGE = 8


def _unique(values: list[str], limit: int) -> tuple[str, ...]:
    """Deduplicate and keep first-occurrence order, then cap."""
    return tuple(dict.fromkeys(values))[:limit]


def _is_a_file(value: str) -> bool:
    """`models.query.py` is a fragment of a path, not a dotted name."""
    return value.rpartition(".")[2] in FILE_SUFFIXES


def patterns(issue_text: str, limit: int = PER_KIND) -> dict[str, tuple[str, ...]]:
    """Searchable strings from `issue_text`, keyed by kind.

    Deterministic: the same text always yields the same patterns in the same
    order. A resumed or repeated measurement must produce the same number, and
    a set iteration would break that quietly.

    A pattern may appear under two kinds. `TypeError` is a name and it also
    starts a message. Attribution is per kind, so a shared pattern is counted
    for each kind that produced it.
    """
    messages = [
        message.strip().strip("`\"'.")
        for message in _ERROR.findall(issue_text)
        if len(message.strip()) >= MIN_MESSAGE
    ]

    paths = _PATH.findall(issue_text)
    dotted = [
        name
        for name in _DOTTED.findall(issue_text)
        if len(name) >= MIN_TOKEN and not _is_a_file(name)
    ]
    names = [
        token
        for token in _SNAKE.findall(issue_text) + _CAMEL.findall(issue_text)
        if len(token) >= MIN_TOKEN
    ]

    return {
        ERROR_STRINGS: _unique([m for m in messages if len(m) >= MIN_MESSAGE], limit),
        DOTTED_NAMES: _unique(dotted, limit),
        IDENTIFIERS: _unique(names, limit),
        TRACEBACK_PATHS: _unique(paths, limit),
    }
