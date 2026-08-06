"""Reading `.env` into the environment.

`.env.sample` tells a reader to copy it and fill it in, and documents two
variables: the OpenRouter key that rung 3 spends against, and an optional
Hugging Face token that raises the Hub's download rate limits. Loading only
the first made the sample file untrue for the second.

Deliberately not `python-dotenv`: a dozen lines against a dependency, for a
file with two entries in it.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_FILE = Path(".env")


def load_env(path: Path = DEFAULT_ENV_FILE) -> None:
    """Set any name in `path` that the environment does not already define.

    The environment wins. A key exported for one run must not be silently
    overridden by a stale file, which is the failure that makes a "why is it
    still using the old key" afternoon.

    A missing file is not an error: rungs 1 through 2.6 need no keys at all,
    so having no `.env` is the normal case for most of this project.
    """
    if not path.is_file():
        return

    for line in path.read_text().splitlines():
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not name or name.startswith("#"):
            continue
        os.environ.setdefault(name, value.strip().strip("'\""))
