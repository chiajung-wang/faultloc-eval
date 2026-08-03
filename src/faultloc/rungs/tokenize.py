"""Turn issue text and source code into comparable tokens.

Lexical retrieval only works if the query and the document agree on what a word
is. A bug report says "separability matrix"; the code says
`separability_matrix`. Naive whitespace splitting never matches them, and the
strongest signal in the whole dataset -- a report quoting a real identifier --
would be thrown away before scoring.
"""

from __future__ import annotations

import re

#: Runs of letters, digits, and underscores. The underscore is deliberately
#: *inside* the word: `separability_matrix` must survive as one string long
#: enough to be emitted as a compound token. Dots and slashes stay separators,
#: so dotted module paths and file paths still split.
WORD = re.compile(r"[A-Za-z0-9_]+")

#: Split CamelCase and acronym boundaries: `HttpRequest` -> Http, Request, and
#: `HTTPServer` -> HTTP, Server rather than H, T, T, P, Server.
CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|[0-9]+")

MIN_TOKEN_LENGTH = 2


def tokenize(text: str) -> list[str]:
    """Lowercased tokens, with compound identifiers kept alongside their parts.

    `separability_matrix` yields `separability`, `matrix`, *and*
    `separability_matrix`. The parts let a report that says "separability
    matrix" match at all; the whole is far rarer than either part, so BM25
    scores it heavily when a report quotes the identifier exactly. Dropping
    either one loses a real signal.

    Single characters are dropped: they carry almost no information and appear
    everywhere in code as loop variables.
    """
    tokens: list[str] = []
    for word in WORD.findall(text):
        parts = [p.lower() for p in CAMEL.findall(word)]
        parts = [p for p in parts if len(p) >= MIN_TOKEN_LENGTH]
        tokens.extend(parts)

        lowered = word.lower()
        if len(parts) > 1 and len(lowered) >= MIN_TOKEN_LENGTH:
            tokens.append(lowered)

    return tokens


def tokenize_path(path: str) -> list[str]:
    """Tokens for a file path, including the path itself.

    Bug reports quote paths constantly -- tracebacks are made of them -- so the
    path is part of the document, not just its label. The full path is kept as a
    token so an exact quote scores far above a coincidental directory-name
    match.
    """
    return [*tokenize(path), path.lower()]
