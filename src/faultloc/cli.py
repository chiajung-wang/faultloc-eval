"""Command-line entry point.

Kept deliberately thin: commands wire arguments to library calls and print
results. Logic lives in the package, so it stays testable without a subprocess.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer

from faultloc import __version__
from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import DATASET_ID, DATASET_REVISION, load_verified_set
from faultloc.reporting import (
    Provenance,
    code_version,
    prepend_entry,
    render_entry,
    render_terminal,
    today,
)
from faultloc.rungs.bm25 import Bm25Rung
from faultloc.rungs.bm25_chunks import Bm25ChunksRung
from faultloc.scoring import score

app = typer.Typer(
    name="faultloc",
    help="Fault localization from issue reports, measured as a ladder of baselines.",
    no_args_is_help=True,
)

RUNGS = {"bm25": Bm25Rung, "bm25-chunks": Bm25ChunksRung}
DEFAULT_RESULTS = Path("RESULTS.md")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def evaluate(
    rung: Annotated[
        str, typer.Option(help="Which rung: bm25 | bm25-chunks | embed | rerank | agent")
    ] = "bm25",
    split: Annotated[str, typer.Option(help="Dataset split: dev | test")] = "dev",
    limit: Annotated[int, typer.Option(help="Evaluate only the first N instances; 0 = all.")] = 0,
    note: Annotated[str, typer.Option(help="One line for the log: what the number means.")] = "",
    results: Annotated[Path, typer.Option(help="Results log to prepend to.")] = DEFAULT_RESULTS,
    write: Annotated[bool, typer.Option(help="Write an entry to the results log.")] = True,
) -> None:
    """Run a rung against a split and report Top-1, Recall@3, Recall@5, cost, latency.

    ``bm25-chunks`` is the ablation, not a rung of the ladder: it isolates the
    chunking half of rung 2's change so the embedding half can be priced on its
    own. See the M3 PRD.
    """
    if rung not in RUNGS:
        raise typer.BadParameter(f"unknown rung {rung!r}; available: {', '.join(sorted(RUNGS))}")

    started = time.perf_counter()

    loaded = load_verified_set()
    splits = load_splits()
    instances = splits.select(loaded.instances, split)
    if not instances:
        raise typer.BadParameter(f"split {split!r} selected no instances")
    if limit:
        instances = instances[:limit]

    # One rung for the whole run. A fresh instance per prediction would discard
    # the blob-keyed token cache, and with it the 21x content reuse measured in
    # issue 04 -- the difference between 80 seconds and half an hour.
    engine = RUNGS[rung]()
    predictions = [engine.predict(instance) for instance in instances]
    report = score(predictions, instances, rung=rung, split=split)
    wall_clock = time.perf_counter() - started

    command = f"faultloc evaluate --rung {rung} --split {split}"
    provenance = Provenance(
        code_sha=code_version(),
        dataset=DATASET_ID,
        dataset_revision=DATASET_REVISION,
        split=split,
        seed=splits.seed,
        command=command,
        run_date=today(),
    )

    typer.echo(render_terminal(report, provenance, loaded.report, wall_clock))

    # A truncated run is not the benchmark. Letting `--limit` write an entry
    # would put a number scored on a different instance set into a log whose
    # whole purpose is that every entry is comparable.
    if limit:
        typer.echo(f"\n  --limit {limit} set: no results entry written.")
        return
    if not write:
        typer.echo("\n  --no-write: no results entry written.")
        return

    prepend_entry(results, render_entry(report, provenance, loaded.report, wall_clock, note))
    typer.echo(f"\n  Wrote entry to {results}")


if __name__ == "__main__":
    app()
