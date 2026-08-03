"""The frozen dev/test split.

ADR-0004 makes split discipline mandatory: the calibrator is fit on dev and the
test set is read once. That only means anything if the split is fixed *before*
any tuning, so it is computed once, written to a file, and committed.

`load_splits` reads that file. It does not shuffle, sample, or fall back to
recomputing -- a split that can be regenerated at runtime is a split that can
silently change between two runs whose numbers get compared.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import resources
from typing import Any

from faultloc.dataset.models import Instance

SPLIT_SEED = 20260803
DEV_SHARE = 0.5
CI_SLICE_SIZE = 50

SPLITS_PACKAGE = "faultloc.data.splits"
VERIFIED_SPLITS_FILE = "verified.json"


@dataclass(frozen=True)
class Splits:
    """Instance IDs assigned to each side, plus the provenance to reproduce them.

    The provenance fields are not decoration. A split is only meaningful
    relative to the instance universe it was drawn from, so the dataset and
    revision travel with it -- otherwise a future reader cannot tell whether a
    missing ID means the split is stale or the filter changed.
    """

    dev: tuple[str, ...]
    test: tuple[str, ...]
    ci_slice: tuple[str, ...]
    seed: int
    dataset: str
    revision: str

    def __post_init__(self) -> None:
        overlap = set(self.dev) & set(self.test)
        if overlap:
            raise ValueError(f"dev and test overlap on {sorted(overlap)[:5]}")

        stray = set(self.ci_slice) - set(self.dev)
        if stray:
            raise ValueError(f"ci_slice must be drawn from dev, found {sorted(stray)[:5]}")

    @property
    def size(self) -> int:
        return len(self.dev) + len(self.test)

    def select(self, instances: Iterable[Instance], name: str) -> tuple[Instance, ...]:
        """Instances belonging to one side, in the order the split lists them.

        Ordering comes from the split file rather than from the caller's
        iteration order, so two runs over the same side see the same sequence.
        """
        wanted = {"dev": self.dev, "test": self.test, "ci": self.ci_slice}[name]
        by_id = {instance.instance_id: instance for instance in instances}
        return tuple(by_id[i] for i in wanted if i in by_id)


def _largest_remainder(counts: dict[str, int], total_wanted: int) -> dict[str, int]:
    """Apportion `total_wanted` across groups in proportion to their size.

    Plain rounding does not sum back to the target. Largest-remainder assigns
    the floor to everyone and then hands the leftovers to whoever was rounded
    down hardest, which keeps the CI slice exactly `CI_SLICE_SIZE` items.
    """
    pool = sum(counts.values())
    if pool == 0:
        return dict.fromkeys(counts, 0)

    exact = {group: total_wanted * n / pool for group, n in counts.items()}
    allocated = {group: min(int(value), counts[group]) for group, value in exact.items()}

    remaining = total_wanted - sum(allocated.values())
    by_remainder = sorted(
        counts,
        key=lambda group: (-(exact[group] - int(exact[group])), group),
    )
    for group in by_remainder:
        if remaining <= 0:
            break
        if allocated[group] < counts[group]:
            allocated[group] += 1
            remaining -= 1

    return allocated


def build_splits(
    instances: Sequence[Instance],
    *,
    seed: int = SPLIT_SEED,
    dataset: str = "",
    revision: str = "",
) -> Splits:
    """Compute the split. Run once; the result is committed, not recomputed.

    Stratified by repo: each repo is shuffled independently and cut in half, so
    no repo lands entirely on one side. Repos with a single instance are the
    unavoidable exception -- they go wherever the seed puts them, which is why
    they are reported inside an `other` bucket rather than as their own row.
    """
    by_repo: dict[str, list[str]] = defaultdict(list)
    for instance in instances:
        by_repo[instance.repo].append(instance.instance_id)

    dev: list[str] = []
    test: list[str] = []
    for repo in sorted(by_repo):
        # Sort before shuffling: input order must not reach the RNG, or the
        # split changes when the loader's iteration order does.
        ids = sorted(by_repo[repo])
        random.Random(f"{seed}:{repo}").shuffle(ids)
        cut = round(len(ids) * DEV_SHARE)
        dev.extend(ids[:cut])
        test.extend(ids[cut:])

    dev_by_repo = {repo: len([i for i in dev if i in set(by_repo[repo])]) for repo in by_repo}
    quota = _largest_remainder(dev_by_repo, CI_SLICE_SIZE)

    ci: list[str] = []
    for repo in sorted(by_repo):
        repo_dev = [i for i in dev if i in set(by_repo[repo])]
        ci.extend(repo_dev[: quota[repo]])

    return Splits(
        dev=tuple(sorted(dev)),
        test=tuple(sorted(test)),
        ci_slice=tuple(sorted(ci)),
        seed=seed,
        dataset=dataset,
        revision=revision,
    )


def load_splits() -> Splits:
    """Read the committed split. The only way a split enters the pipeline."""
    raw = resources.files(SPLITS_PACKAGE).joinpath(VERIFIED_SPLITS_FILE).read_text()
    payload: dict[str, Any] = json.loads(raw)
    return Splits(
        dev=tuple(payload["dev"]),
        test=tuple(payload["test"]),
        ci_slice=tuple(payload["ci_slice"]),
        seed=payload["seed"],
        dataset=payload["dataset"],
        revision=payload["revision"],
    )


def dumps(splits: Splits) -> str:
    """Serialise a split for committing. Stable key order, one ID per line."""
    return json.dumps(
        {
            "dataset": splits.dataset,
            "revision": splits.revision,
            "seed": splits.seed,
            "dev_count": len(splits.dev),
            "test_count": len(splits.test),
            "ci_slice_count": len(splits.ci_slice),
            "dev": list(splits.dev),
            "test": list(splits.test),
            "ci_slice": list(splits.ci_slice),
        },
        indent=2,
    )
