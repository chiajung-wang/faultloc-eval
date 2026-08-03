"""Load the Verified Set into Instances.

See ADR-0006 for why this dataset and why the revision is pinned. The pin is a
module constant rather than a call-site literal: a dataset that silently updates
is a published number that silently stops being reproducible.

The only I/O in this module is `fetch_rows`. Everything above it is pure and
tested without a network.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from faultloc.dataset.filters import filter_ground_truth_files
from faultloc.dataset.models import Instance
from faultloc.dataset.patches import changed_files

DATASET_ID = "princeton-nlp/SWE-bench_Verified"
DATASET_CONFIG = "default"
DATASET_SPLIT = "test"
DATASET_REVISION = "c104f840cc67f8b6eec6f759ebc8b2693d585d4a"

#: Fields read from a dataset row. `hints_text` is deliberately absent -- it
#: holds the issue's comment thread, which frequently names the offending file
#: or quotes the fix. It is excluded here, at the boundary, so that no
#: downstream component can reach it even by accident.
ROW_FIELDS = ("instance_id", "repo", "base_commit", "problem_statement", "patch")

Rows = Iterable[Mapping[str, Any]]
FetchRows = Callable[[str, str, str, str], Rows]


@dataclass(frozen=True)
class LoadReport:
    """The Filter Rate, which ADR-0001 requires be published with every result.

    Dropped instances are counted, never silently discarded -- an unreported
    drop turns an honest constraint into an overclaim.
    """

    total: int
    kept: int
    drops: Mapping[str, int] = field(default_factory=dict)

    @property
    def dropped(self) -> int:
        return self.total - self.kept

    @property
    def filter_rate(self) -> float:
        """Share of instances dropped. Zero for an empty set rather than NaN."""
        return self.dropped / self.total if self.total else 0.0


@dataclass(frozen=True)
class LoadedDataset:
    instances: tuple[Instance, ...]
    report: LoadReport


def fetch_rows(dataset_id: str, config: str, split: str, revision: str) -> Rows:
    """The one impure function here: pull rows from Hugging Face.

    `datasets` caches downloads under `HF_HOME` (`~/.cache/huggingface` by
    default), so a warm run needs no network. Imported lazily so that the pure
    parts of this module stay importable without the dependency loaded.
    """
    from datasets import load_dataset

    return load_dataset(dataset_id, config, split=split, revision=revision)


def _classify(row: Mapping[str, Any]) -> tuple[Instance | None, str | None]:
    """Apply the Instance Filter to one row.

    Exactly one of the returned pair is set, mirroring `FilterResult`. Kept
    here as the single place a row meets the filter, so the loader cannot drift
    from `to_instance`.
    """
    result = filter_ground_truth_files(changed_files(row["patch"]))
    if result.files is None:
        return None, result.drop_reason

    instance = Instance(
        instance_id=row["instance_id"],
        repo=row["repo"],
        base_commit=row["base_commit"],
        issue_text=row["problem_statement"],
        ground_truth_files=result.files,
    )
    return instance, None


def to_instance(row: Mapping[str, Any]) -> Instance | None:
    """Build an Instance from a dataset row, or `None` if the filter drops it.

    Returns `None` rather than raising: a dropped instance is an expected,
    countable outcome of the benchmark's definition, not an error.
    """
    return _classify(row)[0]


def load_verified_set(*, fetch: FetchRows = fetch_rows) -> LoadedDataset:
    """Load, filter, and count the Verified Set.

    `fetch` is injectable so the revision pin can be asserted without a network
    call -- the pin is the thing most likely to rot silently, so it is the thing
    most worth testing.
    """
    instances: list[Instance] = []
    drops: dict[str, int] = {}
    total = 0

    for row in fetch(DATASET_ID, DATASET_CONFIG, DATASET_SPLIT, DATASET_REVISION):
        total += 1
        instance, drop_reason = _classify(row)
        if instance is not None:
            instances.append(instance)
        else:
            drops[str(drop_reason)] = drops.get(str(drop_reason), 0) + 1

    return LoadedDataset(
        instances=tuple(instances),
        report=LoadReport(total=total, kept=len(instances), drops=drops),
    )
