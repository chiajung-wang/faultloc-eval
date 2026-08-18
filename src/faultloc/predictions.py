"""Store one run's Predictions, so two Rungs can be compared per Instance.

Until now a run built a Prediction for each Instance, scored the set, and then
dropped the list. Only the aggregate entry survived. That was enough while the
gaps were large: rung 3 beat rank fusion by 28.7 points, and no per-instance
comparison was needed to see it.

Issue 01 ended that. `git grep` reaches 16 of the 27 Instances the Candidate Set
misses, so rung 4's whole available delta over rung 3 is about 6.6 points against
a ±6pp interval. Two marginal intervals cannot resolve a difference that small,
and a paired test can. A paired test needs the per-instance results, and nothing
kept them.

**Format.** One file per run. The first line is the run header, and every line
after it is one Prediction. JSON Lines rather than one large object: a run writes
244 records, and a reader that wants the header alone reads one line.

The header carries the same `Provenance` the `RESULTS.md` entry carries, so a
stored run and its entry cannot disagree about which commit produced them.

**Truncated runs are stored and labelled.** `--limit` still refuses to write a
results entry, because a truncated run is scored on a different Instance set. It
does write its Predictions, and the header records the limit. A reader must be
able to tell the two apart, and a missing file cannot say anything at all.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from faultloc.reporting import Provenance
from faultloc.rungs import Prediction

DEFAULT_PREDICTIONS_ROOT = Path("data/predictions")


@dataclass(frozen=True)
class StoredRun:
    """A run read back from disk.

    `rung` is the name the CLI was invoked with, and not `Prediction.rung`. All
    four rung-3 cells share the rung name `rerank`, so the Prediction's own field
    cannot tell `rerank` from `rerank-deepseek-on`. Those two are different
    numbers at different prices.
    """

    rung: str
    split: str
    provenance: Provenance
    predictions: tuple[Prediction, ...]
    limit: int = 0

    @property
    def is_truncated(self) -> bool:
        return bool(self.limit)


def run_path(
    rung: str,
    split: str,
    provenance: Provenance,
    root: Path = DEFAULT_PREDICTIONS_ROOT,
) -> Path:
    """Where a run's Predictions go, never overwriting an earlier run.

    The name carries the rung, the split, the date and the code SHA, which is
    what a reader matches against a `RESULTS.md` entry. Two runs of the same cell
    on the same day from the same commit are still possible, so a repeat takes a
    numeric suffix rather than replace what is already there.
    """
    stem = f"{rung}-{split}-{provenance.run_date}-{provenance.code_sha}"
    candidate = root / f"{stem}.jsonl"
    attempt = 2
    while candidate.exists():
        candidate = root / f"{stem}-{attempt}.jsonl"
        attempt += 1
    return candidate


def write_run(
    path: Path,
    *,
    rung: str,
    split: str,
    provenance: Provenance,
    predictions: Sequence[Prediction],
    limit: int = 0,
) -> None:
    """Write a run, header first, then one Prediction per line.

    Written then renamed. A killed run must not leave a half-written file that a
    later read would treat as complete, which is the rule `RepoStore` and
    `ResponseCache` already follow.
    """
    header = {
        "kind": "run",
        "rung": rung,
        "split": split,
        "limit": limit,
        "n": len(predictions),
        "provenance": asdict(provenance),
    }
    lines = [json.dumps(header)]
    lines += [json.dumps(asdict(prediction)) for prediction in predictions]

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".jsonl.{os.getpid()}.tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(path)


def read_run(path: Path) -> StoredRun:
    """Read a stored run back.

    Raises on a file whose header is missing or whose record count disagrees with
    the header. A silently short read would drop Instances from a paired test,
    and a paired test on two different Instance sets is the error the whole
    comparison exists to avoid.
    """
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"{path} is empty")

    header = json.loads(lines[0])
    if header.get("kind") != "run":
        raise ValueError(f"{path} does not start with a run header")

    predictions = tuple(
        Prediction(
            instance_id=record["instance_id"],
            rung=record["rung"],
            ranked_files=tuple(record["ranked_files"]),
            stop_condition=record["stop_condition"],
            latency_s=record["latency_s"],
            cost_usd=record["cost_usd"],
            confidence=record["confidence"],
        )
        for record in (json.loads(line) for line in lines[1:])
    )
    if len(predictions) != header["n"]:
        raise ValueError(
            f"{path} header says {header['n']} predictions, file holds {len(predictions)}"
        )

    return StoredRun(
        rung=header["rung"],
        split=header["split"],
        provenance=Provenance(**header["provenance"]),
        predictions=predictions,
        limit=header.get("limit", 0),
    )
