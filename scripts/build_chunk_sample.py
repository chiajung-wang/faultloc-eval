"""Draw a uniform random sample of AST Chunks from the dev split.

Issue 07 benchmarks three embedding models against the same text. Loading
every one of the 753,421 chunks three times would dominate the measurement
with git and parsing work rather than embedding work, so the sample is built
once here and cached.

Sampling is a reservoir over the whole chunk population, not the first N
chunks of the first N repositories. The corpus is dominated by a small number
of very large whole-file fallback chunks -- 5.5% of chunks carrying most of
the 106M tokens -- and any sampling scheme that under-represents them would
report a throughput number that flatters every model equally and truncation
figures that are simply wrong.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import load_verified_set
from faultloc.repos import RepoStore
from faultloc.rungs.chunks import chunk_source

SAMPLE_SIZE = 25_000
SEED = 20260804
OUT = Path("data/cache/chunk_sample.json")


def main() -> int:
    random.seed(SEED)

    loaded = load_verified_set()
    splits = load_splits()
    instances = splits.select(loaded.instances, "dev")

    store = RepoStore()
    seen: set[str] = set()
    reservoir: list[dict[str, str]] = []
    total = 0

    for n, instance in enumerate(instances, 1):
        files = store.list_source_files(instance.repo, instance.base_commit)
        wanted = [f.blob for f in files if f.blob not in seen]
        if not wanted:
            continue

        # One path per blob, for reporting only. A blob reachable from several
        # paths is the same text, and the sample is of text.
        path_of = {f.blob: f.path for f in files}

        for blob, text in store.read_blobs(instance.repo, wanted).items():
            seen.add(blob)
            for chunk in chunk_source(text):
                total += 1
                record = {
                    "repo": instance.repo,
                    "path": path_of.get(blob, ""),
                    "kind": chunk.kind,
                    "text": chunk.text,
                }
                if len(reservoir) < SAMPLE_SIZE:
                    reservoir.append(record)
                else:
                    j = random.randrange(total)
                    if j < SAMPLE_SIZE:
                        reservoir[j] = record

        if n % 50 == 0:
            print(f"  ... {n}/{len(instances)} instances, {total:,} chunks seen", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"seed": SEED, "population": total, "chunks": reservoir}))

    fallbacks = sum(1 for c in reservoir if c["kind"] == "file")
    print(f"population:      {total:,} chunks")
    print(f"sampled:         {len(reservoir):,}")
    print(f"fallback share:  {fallbacks / len(reservoir):.1%} (population is ~5.5%)")
    print(f"wrote:           {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
