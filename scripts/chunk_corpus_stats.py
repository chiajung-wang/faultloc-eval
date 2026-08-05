"""Corpus size for each chunk definition, over the whole dev split.

Issue 06 changes what a chunk is, twice over: long chunks are windowed rather
than truncated, and bodies can be indexed. Both change the document count and
the token volume, which changes what a Recall@5 number means and what an
embedding index costs to build. Reported rather than estimated.
"""

from __future__ import annotations

import sys

from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import load_verified_set
from faultloc.repos import RepoStore
from faultloc.rungs.chunks import chunk_source

CHARS_PER_TOKEN = 4


def main() -> int:
    loaded = load_verified_set()
    splits = load_splits()
    instances = splits.select(loaded.instances, "dev")

    store = RepoStore()
    seen: set[str] = set()
    counts = {False: 0, True: 0}
    chars = {False: 0, True: 0}
    longest = {False: 0, True: 0}

    for n, instance in enumerate(instances, 1):
        files = store.list_source_files(instance.repo, instance.base_commit)
        wanted = [f.blob for f in files if f.blob not in seen]
        if not wanted:
            continue

        for blob, text in store.read_blobs(instance.repo, wanted).items():
            seen.add(blob)
            for bodies in (False, True):
                chunks = chunk_source(text, include_bodies=bodies)
                counts[bodies] += len(chunks)
                chars[bodies] += sum(len(c.text) for c in chunks)
                longest[bodies] = max(longest[bodies], max(len(c.text) for c in chunks))

        if n % 50 == 0:
            print(f"  ... {n}/{len(instances)} instances, {len(seen):,} blobs", flush=True)

    print(f"distinct blobs:      {len(seen):,}")
    for bodies in (False, True):
        label = "with bodies" if bodies else "no bodies  "
        print(
            f"{label}  chunks={counts[bodies]:>9,}  "
            f"tokens~{chars[bodies] // CHARS_PER_TOKEN:>12,}  "
            f"longest chunk={longest[bodies]:>6,} chars"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
