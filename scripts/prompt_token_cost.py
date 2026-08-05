"""What a rung-3 prompt costs in tokens, per payload option, at K=20.

ADR-0008 has to price "paths only" against "paths plus text" before a model is
chosen, and the two differ by an order of magnitude. Measured rather than
assumed: the issue text turns out to be the small part of the prompt, and the
payload is what decides which models fit the budget.

Totals are reported on means, not medians, because a run pays for every
instance and the per-file distributions are heavily skewed -- whole-file
fallbacks are 1.6% of chunks carrying 55% of the corpus (ADR-0007).

Uses the CHARS_PER_TOKEN = 4 convention from `chunk_corpus_stats.py`, so the
numbers here are comparable to the ones that sized the rung-2 index.
"""

from __future__ import annotations

import random
import statistics
import sys

from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import load_verified_set
from faultloc.repos import RepoStore
from faultloc.rungs.chunks import chunk_source

CHARS_PER_TOKEN = 4
K = 20

#: Chunking every one of the 32,667 dev-split blobs twice takes minutes for a
#: mean that stabilises far sooner. Seeded so the figure in ADR-0008 is the
#: figure a rerun produces.
BLOB_SAMPLE = 2000
SEED = 0


def main() -> int:
    loaded = load_verified_set()
    splits = load_splits()
    instances = splits.select(loaded.instances, "dev")

    issue_tokens = [len(i.issue_text) / CHARS_PER_TOKEN for i in instances]

    store = RepoStore()
    blobs: dict[str, tuple[str, str]] = {}  # blob -> (repo, path)
    for instance in instances:
        for file in store.list_source_files(instance.repo, instance.base_commit):
            blobs.setdefault(file.blob, (instance.repo, file.path))

    path_tokens = [len(path) / CHARS_PER_TOKEN for _, path in blobs.values()]

    sample = random.Random(SEED).sample(sorted(blobs), min(BLOB_SAMPLE, len(blobs)))
    by_repo: dict[str, list[str]] = {}
    for blob in sample:
        by_repo.setdefault(blobs[blob][0], []).append(blob)

    file_tokens: list[float] = []
    signatures_per_file: list[float] = []  # every signature chunk of one file
    signature_tokens: list[float] = []  # one signature chunk
    body_tokens: list[float] = []  # one chunk carrying its body

    for repo, wanted in by_repo.items():
        for text in store.read_blobs(repo, wanted).values():
            file_tokens.append(len(text) / CHARS_PER_TOKEN)

            rendered = [
                f"{chunk.signature}\n{chunk.docstring}"
                for chunk in chunk_source(text, include_bodies=False)
            ]
            signatures_per_file.append(sum(len(r) for r in rendered) / CHARS_PER_TOKEN)
            signature_tokens.extend(len(r) / CHARS_PER_TOKEN for r in rendered)

            body_tokens.extend(
                len(chunk.content) / CHARS_PER_TOKEN
                for chunk in chunk_source(text, include_bodies=True)
                if chunk.content
            )

    print(
        f"dev split, n={len(instances)}, {len(blobs)} unique blobs, "
        f"{len(sample)} sampled (seed {SEED}), tokens = chars/{CHARS_PER_TOKEN}\n"
    )

    print("per-unit tokens")
    units = (
        ("issue text", issue_tokens),
        ("path", path_tokens),
        ("one signature chunk", signature_tokens),
        ("one body chunk", body_tokens),
        ("all signatures of a file", signatures_per_file),
        ("whole file", file_tokens),
    )
    for name, values in units:
        deciles = statistics.quantiles(values, n=10)
        print(
            f"  {name:<26} n={len(values):>6}  mean={statistics.mean(values):>8.0f}  "
            f"median={statistics.median(values):>8.0f}  p90={deciles[8]:>8.0f}"
        )

    print(f"\nprompt input at K={K}, on means (mean issue + K x mean unit)")
    issue_mean = statistics.mean(issue_tokens)
    path_mean = statistics.mean(path_tokens)
    payloads = (
        ("paths only", 0.0),
        ("path + one signature chunk", statistics.mean(signature_tokens)),
        ("path + one body chunk", statistics.mean(body_tokens)),
        ("path + all signatures", statistics.mean(signatures_per_file)),
        ("path + whole file", statistics.mean(file_tokens)),
    )
    for name, payload in payloads:
        per_instance = issue_mean + K * (path_mean + payload)
        print(
            f"  {name:<26} {per_instance:>9.0f} tokens/instance  "
            f"{per_instance * len(instances) / 1e6:>6.2f} M/run"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
