"""The rung-2.6 bake-off: which cross-encoder, and what does it truncate.

Issue 06's dominant criterion is input length. A pair is the issue text plus an
Evidence Chunk, and `scripts/prompt_token_cost.py` puts a p90 pair near 1,450
tokens -- so a 512-token cross-encoder discards most of the issue report before
it reaches the code. ADR-0007 recorded a 512-token cap as an accepted
consequence and it later turned out to be dropping 59% of the corpus. This
measures the truncation rather than accepting it.

Retrieval runs once and is shared by every model, so the comparison is of the
rerankers and not of the machine's mood. `ms-marco-MiniLM-L6-v2` is in the
field deliberately as the row that *will* truncate.

Subsample, not the full split: this picks a model. The winner is then scored on
all 244 instances through the rung itself, which is what a published number
has to come from.

Takes candidate keys as arguments, defaulting to all of them, so a model can be
re-measured without paying for the others again.
"""

from __future__ import annotations

import random
import statistics
import sys
import time

from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import load_verified_set
from faultloc.repos import RepoStore
from faultloc.reranking import CANDIDATES, load_reranker
from faultloc.rungs.cross_encoder import TOP_K
from faultloc.rungs.hybrid import HybridRung
from faultloc.scoring import normalize_path

SAMPLE = 60
SEED = 0


def main() -> int:
    loaded = load_verified_set()
    splits = load_splits()
    instances = splits.select(loaded.instances, "dev")
    sample = random.Random(SEED).sample(sorted(instances, key=lambda i: i.instance_id), SAMPLE)

    store = RepoStore()
    hybrid = HybridRung(store)

    print(f"building candidates for {len(sample)} instances ...", flush=True)
    cases: list[tuple[list[tuple[str, str]], list[str], set[str]]] = []
    started = time.perf_counter()
    for n, instance in enumerate(sample, 1):
        head = list(hybrid.predict(instance).ranked_files[:TOP_K])
        chunks = hybrid.lexical.evidence(instance, head)
        pairs = [
            (instance.issue_text, "\n".join(part for part in (path, chunks.get(path)) if part))
            for path in head
        ]
        cases.append((pairs, head, {normalize_path(p) for p in instance.ground_truth_files}))
        if n % 10 == 0:
            print(f"  ... {n}/{len(sample)}", flush=True)
    print(f"  retrieval took {time.perf_counter() - started:.0f}s\n", flush=True)

    baseline = sum(head[0] in truth for _pairs, head, truth in cases if head)
    print(f"fusion, unreranked:  top-1 {baseline}/{len(cases)} = {baseline / len(cases):.1%}\n")

    for key in sys.argv[1:] or list(CANDIDATES):
        spec = CANDIDATES[key]
        print(f"{key}  {spec.name}@{spec.revision[:8]}  max_length={spec.max_length}", flush=True)
        try:
            score = load_reranker(spec)
        except Exception as exc:
            print(f"  LOAD FAILED  {type(exc).__name__}: {exc}\n", flush=True)
            continue

        from sentence_transformers import CrossEncoder

        tokenizer = CrossEncoder(spec.name, revision=spec.revision).tokenizer
        lengths = [
            len(tokenizer(query, document)["input_ids"])
            for pairs, _head, _truth in cases
            for query, document in pairs
        ]
        over = [length for length in lengths if length > spec.max_length]

        hits = 0
        elapsed = 0.0
        for pairs, head, truth in cases:
            began = time.perf_counter()
            scores = score(pairs)
            elapsed += time.perf_counter() - began
            ranked = sorted(zip((-s for s in scores), head, strict=True))
            if ranked and ranked[0][1] in truth:
                hits += 1

        deciles = statistics.quantiles(lengths, n=10)
        print(
            f"  top-1        {hits}/{len(cases)} = {hits / len(cases):.1%}  "
            f"({hits - baseline:+d} vs fusion)\n"
            f"  pair tokens  mean={statistics.mean(lengths):.0f}  "
            f"median={statistics.median(lengths):.0f}  p90={deciles[8]:.0f}  "
            f"max={max(lengths)}\n"
            f"  truncated    {len(over)}/{len(lengths)} = {len(over) / len(lengths):.1%} of pairs\n"
            f"  throughput   {len(lengths) / elapsed:.1f} pairs/s  "
            f"({elapsed / len(cases):.2f}s per instance)\n",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
