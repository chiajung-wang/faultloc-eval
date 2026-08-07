"""The candidate union's recall ceiling, over the dev split.

A reranker reorders a list; it never adds to it. So the fraction of instances
whose candidate list contains *any* ground-truth file is the hard upper bound
on rung 3's Top-1, and it is free to measure -- both retrievers already run and
no model is called.

Reports two quantities that are easy to confuse:

- **hit@K** -- at least one ground-truth file inside the top K. This is the
  bound on Top-1, because the reranker picks one path and can only be right if
  a correct one was in front of it.
- **recall@K** -- the share of an instance's ground-truth files inside the top
  K, averaged. This is the scorer's existing definition and bounds Recall@k.

They differ only for multi-file instances, which are 12% of the benchmark.

Also compares two merge rules, so the choice between them is measured rather
than asserted.
"""

from __future__ import annotations

import sys
from collections import defaultdict

from faultloc.candidates import hit_at_k, interleave, reciprocal_rank_fusion
from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import load_verified_set
from faultloc.repos import RepoStore
from faultloc.rungs.bm25_chunks import Bm25ChunksRung
from faultloc.rungs.embed import EmbedRung
from faultloc.scoring import normalize_path

KS = (1, 3, 5, 10, 20, 50, 100)
REPO_K = 20


def recall_at_k(ranked: tuple[str, ...], truth: set[str], k: int) -> float:
    return len(truth & set(ranked[:k])) / len(truth) if truth else 0.0


def main() -> int:
    loaded = load_verified_set()
    splits = load_splits()
    instances = splits.select(loaded.instances, "dev")

    store = RepoStore()
    lexical = Bm25ChunksRung(store, include_bodies=True)
    dense = EmbedRung(store)

    hits: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    recalls: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    by_repo: dict[str, list[bool]] = defaultdict(list)
    lengths: list[int] = []

    for n, instance in enumerate(instances, 1):
        truth = {normalize_path(p) for p in instance.ground_truth_files}

        lex = tuple(normalize_path(p) for p in lexical.predict(instance).ranked_files)
        den = tuple(normalize_path(p) for p in dense.predict(instance).ranked_files)
        variants = {
            "lexical": lex,
            "dense": den,
            "union (rrf)": reciprocal_rank_fusion([lex, den]),
            "union (interleave)": interleave([lex, den]),
        }
        lengths.append(len(variants["union (rrf)"]))

        for name, ranked in variants.items():
            for k in KS:
                hits[name][k] += hit_at_k(ranked, sorted(truth), k)
                recalls[name][k] += recall_at_k(ranked, truth, k)

        by_repo[instance.repo].append(hit_at_k(variants["union (rrf)"], sorted(truth), REPO_K))

        if n % 50 == 0:
            print(f"  ... {n}/{len(instances)}", flush=True)

    total = len(instances)
    print(f"\ndev split, n={total}   median candidates/instance: {sorted(lengths)[total // 2]:,}")

    header = "  ".join(f"K={k:<4}" for k in KS)
    print(f"\nhit@K  -- ceiling on rung-3 Top-1\n{'':22}{header}")
    for name in ("lexical", "dense", "union (rrf)", "union (interleave)"):
        row = "  ".join(f"{100 * hits[name][k] / total:5.1f}%" for k in KS)
        print(f"{name:22}{row}")

    print(f"\nrecall@K -- ceiling on rung-3 Recall@k\n{'':22}{header}")
    for name in ("lexical", "dense", "union (rrf)", "union (interleave)"):
        row = "  ".join(f"{100 * recalls[name][k] / total:5.1f}%" for k in KS)
        print(f"{name:22}{row}")

    print(f"\nunion (rrf) hit@{REPO_K} per repo")
    for repo, flags in sorted(by_repo.items(), key=lambda kv: -len(kv[1])):
        print(f"  {repo:28} n={len(flags):3}  {100 * sum(flags) / len(flags):5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
