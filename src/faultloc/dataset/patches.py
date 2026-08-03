"""Extract the file list from a unified diff.

Pure: no I/O, no network. The Ground-Truth File Set is derived from a patch, so
a parsing bug here is indistinguishable from a wrong ground truth downstream --
the same reason `filters.py` is built test-first.
"""

from __future__ import annotations

import re

#: `diff --git a/<old> b/<new>`. The old path is captured non-greedily so that
#: the ` b/` separator binds as early as possible, which is what disambiguates
#: the (rare) case of a path containing spaces.
DIFF_HEADER = re.compile(r"^diff --git a/(?P<old>.+?) b/(?P<new>.+)$", re.MULTILINE)


def changed_files(patch: str) -> tuple[str, ...]:
    """Paths a unified diff touches, in the order the diff lists them.

    Returns the **post-image** path -- the `b/` side. For an ordinary edit the
    two sides are identical; for a rename the post-image is the file a fix now
    lives in, and for a deletion git still names the removed path on both sides.

    Duplicates are preserved. This is a parser: it reports what the diff says,
    and de-duplication is the Instance Filter's decision to make.
    """
    return tuple(match.group("new") for match in DIFF_HEADER.finditer(patch))
