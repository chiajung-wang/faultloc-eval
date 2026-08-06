"""Command-line entry point.

Kept deliberately thin: commands wire arguments to library calls and print
results. Logic lives in the package, so it stays testable without a subprocess.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Annotated

import typer

from faultloc import __version__
from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import DATASET_ID, DATASET_REVISION, load_verified_set
from faultloc.embedding import (
    DEFAULT_INDEX_ROOT,
    EmbeddingIndex,
    build_index,
    load_encoder,
)
from faultloc.llm import MODELS
from faultloc.reporting import (
    Provenance,
    code_version,
    prepend_entry,
    render_entry,
    render_terminal,
    today,
)
from faultloc.repos import RepoStore
from faultloc.rungs import Rung
from faultloc.rungs.bm25 import Bm25Rung
from faultloc.rungs.bm25_chunks import Bm25ChunksRung
from faultloc.rungs.cross_encoder import CrossEncoderRung
from faultloc.rungs.embed import EmbedRung
from faultloc.rungs.hybrid import HybridRung
from faultloc.rungs.rerank import BudgetExceededError, LlmRerankRung
from faultloc.scoring import score

app = typer.Typer(
    name="faultloc",
    help="Fault localization from issue reports, measured as a ladder of baselines.",
    no_args_is_help=True,
)

RUNGS: dict[str, Callable[[], Rung]] = {
    "bm25": Bm25Rung,
    "bm25-chunks": Bm25ChunksRung,
    "bm25-chunks-bodies": partial(Bm25ChunksRung, include_bodies=True),
    "embed": EmbedRung,
    "hybrid": HybridRung,
    "cross-encoder": CrossEncoderRung,
    # `rerank` is ADR-0008's declared ladder row, named before any number
    # existed. The other three are the cross-model table and the reasoning
    # ablations, and are not the rung-3 headline whatever they score.
    "rerank": partial(LlmRerankRung, model=MODELS["gpt-oss-high"]),
    "rerank-gpt-oss-low": partial(LlmRerankRung, model=MODELS["gpt-oss-low"]),
    "rerank-deepseek-off": partial(LlmRerankRung, model=MODELS["deepseek-off"]),
    "rerank-deepseek-on": partial(LlmRerankRung, model=MODELS["deepseek-on"]),
}
DEFAULT_RESULTS = Path("RESULTS.md")


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def index(
    split: Annotated[str, typer.Option(help="Dataset split: dev | test")] = "dev",
    limit: Annotated[int, typer.Option(help="Index only the first N instances; 0 = all.")] = 0,
    root: Annotated[Path, typer.Option(help="Where the index lives.")] = DEFAULT_INDEX_ROOT,
    device: Annotated[str, typer.Option(help="torch device; blank to auto-detect.")] = "",
) -> None:
    """Embed every AST Chunk a split needs, skipping blobs already indexed.

    Separate from ``evaluate`` on purpose: this is a long, resumable, costed
    job, and a rung that rebuilt its index inside the prediction loop is the
    bug M1 already found once. Re-running is near-free -- blobs are keyed by
    content hash, so only new content is embedded.
    """
    loaded = load_verified_set()
    splits = load_splits()
    instances = splits.select(loaded.instances, split)
    if not instances:
        raise typer.BadParameter(f"split {split!r} selected no instances")
    if limit:
        instances = instances[:limit]

    store = EmbeddingIndex(root=root)
    typer.echo(f"Indexing {len(instances)} instances into {store.root}")
    typer.echo(f"  model {store.spec.name} @ {store.spec.revision[:12]}")

    def progress(done: int, total: int) -> None:
        if done % 25 == 0 or done == total:
            typer.echo(f"  ... {done}/{total} instances", nl=True)

    report = build_index(
        instances,
        store=RepoStore(),
        index=store,
        encode=load_encoder(store.spec, device=device or None),
        on_progress=progress,
    )

    typer.echo(
        f"\n  blobs       {report.blobs_total:,} "
        f"({report.blobs_embedded:,} embedded, {report.blobs_reused:,} reused)"
    )
    typer.echo(f"  chunks      {report.chunks_embedded:,} embedded")
    typer.echo(f"  index size  {store.size_bytes() / 1e9:.2f} GB")
    typer.echo(f"  wall clock  {report.wall_clock_s / 60:.1f}m")
    typer.echo(f"  cost        ${report.cost_usd:.2f}")


def _failure_note(engine: Rung) -> str:
    """The ways a rung silently kept its input ranking, if it counts them."""
    counted = [
        (label, getattr(engine, attribute, 0))
        for attribute, label in (
            ("unparseable", "unparseable replies"),
            ("truncated", "truncated replies"),
            ("off_list", "off-list paths"),
        )
    ]
    reported = [f"{count} {label}" for label, count in counted if count]
    if not reported:
        return ""
    return f"Degraded: {', '.join(reported)}."


@app.command()
def evaluate(
    rung: Annotated[
        str,
        typer.Option(
            help="Which rung: bm25 | bm25-chunks | bm25-chunks-bodies | embed | rerank | agent"
        ),
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
    try:
        predictions = [engine.predict(instance) for instance in instances]
    except BudgetExceededError as stopped:
        # No entry, no partial score. A run that stopped early was scored on a
        # different instance set, which is exactly what `--limit` refuses to
        # publish for.
        raise typer.BadParameter(f"budget cap reached: {stopped}") from stopped

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

    # Rung 3's failure modes all leave a *ranking* behind -- the one it was
    # handed -- so a run that failed everywhere scores like the rung below it
    # and reads as a null result. The counts go in the entry's note so the
    # number can never be published without them.
    note = " ".join(part for part in (note, _failure_note(engine)) if part)

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
