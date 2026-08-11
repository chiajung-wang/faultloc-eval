"""Command-line entry point.

Kept deliberately thin: commands wire arguments to library calls and print
results. Logic lives in the package, so it stays testable without a subprocess.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import Annotated

import typer

from faultloc import __version__
from faultloc.dataset.models import Instance
from faultloc.dataset.splits import load_splits
from faultloc.dataset.verified import DATASET_ID, DATASET_REVISION, load_verified_set
from faultloc.embedding import (
    DEFAULT_INDEX_ROOT,
    EmbeddingIndex,
    build_index,
    load_encoder,
)
from faultloc.env import load_env
from faultloc.llm import MODELS
from faultloc.predictions import read_run, run_path, write_run
from faultloc.reporting import (
    Provenance,
    code_version,
    prepend_entry,
    render_comparison,
    render_entry,
    render_terminal,
    today,
)
from faultloc.repos import RepoStore
from faultloc.response_cache import ResponseCache
from faultloc.rungs import Prediction, Rung
from faultloc.rungs.bm25 import Bm25Rung
from faultloc.rungs.bm25_chunks import Bm25ChunksRung
from faultloc.rungs.cross_encoder import CrossEncoderRung
from faultloc.rungs.embed import EmbedRung
from faultloc.rungs.hybrid import HybridRung
from faultloc.rungs.rerank import BudgetExceededError, LlmRerankRung
from faultloc.scoring import compare, score, top_1_hit

load_env()

app = typer.Typer(
    name="faultloc",
    help="Fault localization from issue reports, measured as a ladder of baselines.",
    no_args_is_help=True,
)


def _agent(max_tool_calls: int | None = None) -> Rung:
    """Rung 4, with the framework imported here and not at module scope.

    `cli.py` imports every rung at module level, and `agent_graph.py` imports
    LangGraph at module level. A top-level import chain would therefore break
    `faultloc --help` for anyone who installed without the extra. `embedding.py`
    and `reranking.py` raise from inside their loaders for the same reason.
    """
    try:
        from faultloc.agent_client import AgentCache
        from faultloc.rungs.agent import AgentRung
    except ImportError as missing:
        raise typer.BadParameter(
            "agent support is an optional extra; install it with `uv sync --extra agent`"
        ) from missing

    caps = {} if max_tool_calls is None else {"max_tool_calls": max_tool_calls}
    return AgentRung(cache=AgentCache(), **caps)


def _rerank(model: str) -> LlmRerankRung:
    """A rung-3 cell with its response cache attached.

    The cache is wired here rather than defaulted inside the rung so that
    tests cannot write into the real cache directory by forgetting to pass
    one. A run is 244 sequential calls over hours; without the cache, a
    failure at 90% re-buys the first 90%.
    """
    return LlmRerankRung(model=MODELS[model], cache=ResponseCache())


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
    "rerank": partial(_rerank, "gpt-oss-high"),
    "rerank-gpt-oss-low": partial(_rerank, "gpt-oss-low"),
    "rerank-deepseek-off": partial(_rerank, "deepseek-off"),
    "rerank-deepseek-on": partial(_rerank, "deepseek-on"),
    # ADR-0009 declared both rung-4 cells before either ran, so both exist here
    # from the start rather than one appearing once the other has a number.
    "agent": _agent,
    "agent-no-tools": partial(_agent, max_tool_calls=0),
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


#: Instances between progress lines. Every instance is too noisy to tail for
#: 244 of them; every 25 leaves a rung-3 run silent for two minutes at a time.
PROGRESS_EVERY = 10


def _progress_line(
    done: int,
    total: int,
    hits: int,
    spent: float,
    cap: float,
    elapsed_s: float,
    degraded: tuple[int, int, int],
) -> str:
    """One status line for a run in flight.

    Running Top-1 is here to catch a broken run early rather than after an
    hour: a rung whose replies are all failing degrades to its input ranking,
    so its accuracy tracks the rung below it from the first ten instances.
    """
    pace = elapsed_s / done if done else 0.0
    eta_m = pace * (total - done) / 60
    budget = f"${spent:.3f}/${cap:.2f}" if cap else f"${spent:.2f}"
    return (
        f"[{done:>4}/{total}] {done / total:>4.0%}   "
        f"top-1 {hits / done:>5.1%}   {budget}   "
        f"{pace:.1f}s/inst   eta {eta_m:.0f}m   "
        f"degraded {degraded[0]}/{degraded[1]}/{degraded[2]}"
    )


def _run(engine: Rung, instances: Sequence[Instance]) -> list[Prediction]:
    """Predict every instance, reporting progress as it goes.

    Progress is echoed rather than rendered with a live display: a long run is
    detached with its output redirected, where a terminal-only progress bar
    prints nothing at all. `nl` forces a flush so `tee` shows it live instead
    of holding it in a pipe buffer.
    """
    predictions: list[Prediction] = []
    started = time.perf_counter()
    hits = 0

    for done, instance in enumerate(instances, 1):
        prediction = engine.predict(instance)
        predictions.append(prediction)
        hits += top_1_hit(prediction, instance)

        if done % PROGRESS_EVERY == 0 or done == len(instances):
            typer.echo(
                _progress_line(
                    done,
                    len(instances),
                    hits,
                    sum(p.cost_usd for p in predictions),
                    getattr(engine, "budget_usd", 0.0),
                    time.perf_counter() - started,
                    (
                        _count(engine, "unparseable"),
                        _count(engine, "truncated"),
                        _count(engine, "off_list"),
                    ),
                ),
                nl=True,
            )

    return predictions


def _count(engine: Rung, attribute: str) -> int:
    """How many, whether the rung counts with an integer or keeps a list.

    Rung 3 counts `off_list` as an integer. Rung 4 keeps the paths themselves, so
    the entry can show what a hallucinated path looks like rather than only how
    many there were. Without this, rung 4's note would print a Python list into
    the results log.
    """
    value = getattr(engine, attribute, 0)
    return len(value) if isinstance(value, list | set | tuple) else int(value)


def _tool_call_note(engine: Rung) -> str:
    """The tool-call distribution, which is ADR-0009's stated revisit condition.

    If most Instances reach the cap, the cap produced the number rather than the
    agent, and the cap has to rise. A cap of 8 cannot answer how many steps the
    agent actually wants, which was the one virtue of the PRD's original 25.
    """
    calls = getattr(engine, "calls_per_instance", None)
    if not calls:
        return ""

    cap = getattr(engine, "max_tool_calls", 0)
    ordered = sorted(calls)
    median = ordered[len(ordered) // 2]
    at_cap = sum(1 for n in calls if cap and n >= cap)
    return (
        f"Tool calls: median {median}, mean {sum(calls) / len(calls):.1f}, "
        f"cap of {cap} reached on {at_cap}/{len(calls)} instances."
    )


def _guardrail_note(engine: Rung) -> str:
    """The Path Guardrail's catch rate, which `CONTEXT.md` promises to publish.

    Reported apart from the degrade counts because an Off-List Path is not a
    failure. It is what rung 4 adds over rung 3, and issue 01 measured that 5 of
    6 such paths from a cached rung-3 cell existed. `Tool-Reached` splits the
    accepted ones: a real path that no tool ever surfaced was recalled from
    training data rather than found, and the Verified Set predates the cutoff.
    """
    if not hasattr(engine, "hallucinated"):
        return ""

    absent = _count(engine, "hallucinated")
    retries = _count(engine, "guardrail_retries")
    accepted = _count(engine, "off_list")
    recalled = _count(engine, "recalled")

    return (
        f"Guardrail: {absent} paths rejected as absent at base_commit, "
        f"{retries} retries. Off-list accepted: {accepted}, of which "
        f"{recalled} were never surfaced by a tool."
    )


def _tool_roster_note(engine: Rung) -> str:
    """Per tool: calls made, and how often it found the file that became Top-1.

    ADR-0002 called five tools "a deliberate ceiling", and ADR-0009 turned the
    roster into a measurement rather than an assertion. A tool that never surfaces
    a path reaching an answer does not earn its slot, and dropping it is a recorded
    correction to ADR-0002 rather than a quiet edit.

    Top-1 credit rather than "appeared in the ranking": the assembly appends every
    candidate behind the agent's order, so almost any path would qualify under the
    looser test and every tool would look useful.
    """
    calls = getattr(engine, "calls_by_tool", None)
    if not calls:
        return ""

    credited = getattr(engine, "credited_by_tool", {}) or {}
    parts = [
        f"{name} {count} calls/{credited.get(name, 0)} top-1"
        for name, count in sorted(calls.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return f"Tools: {', '.join(parts)}."


def _failure_note(engine: Rung) -> str:
    """What the entry has to admit about how its number was produced.

    Several different things, deliberately worded apart. *Degraded* counts the
    ways a rung silently kept its input ranking -- each one a route to looking
    like a null result while having failed. *Replayed* is not a failure at all: it
    says how much of the run came from cache rather than from fresh calls, which a
    reader needs in order to read the cost column correctly. The guardrail and
    tool-call lines belong to rung 4 and are absent for every rung below it.
    """
    # An Off-List Path is a degrade at rung 3 and the *product* at rung 4. Rung 3
    # discards one, because a reranker reorders and never adds. Rung 4 keeps one
    # that exists, and reports it under the guardrail instead. Filing it as a
    # degrade here would be the exact conflation ADR-0009 corrects.
    reaches_past_the_list = hasattr(engine, "hallucinated")
    tracked = (
        ("unparseable", "unparseable replies"),
        ("truncated", "truncated replies"),
        ("no_candidates", "instances with no candidates"),
        ("unknown_tools", "calls to tools that do not exist"),
    )
    if not reaches_past_the_list:
        tracked += (("off_list", "off-list paths"),)

    degraded = [(label, _count(engine, attribute)) for attribute, label in tracked]
    parts = []
    reported = [f"{count} {label}" for label, count in degraded if count]
    if reported:
        parts.append(f"Degraded: {', '.join(reported)}.")

    parts.extend(
        part
        for part in (_guardrail_note(engine), _tool_call_note(engine), _tool_roster_note(engine))
        if part
    )

    replayed = getattr(engine, "cache_hits", 0)
    if replayed:
        parts.append(f"Replayed {replayed} responses from cache; cost is what they cost to make.")

    return " ".join(parts)


@app.command()
def evaluate(
    rung: Annotated[
        str,
        typer.Option(
            help=(
                "Which rung: bm25 | bm25-chunks | bm25-chunks-bodies | embed | "
                "hybrid | cross-encoder | rerank | agent | agent-no-tools"
            )
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
        predictions = _run(engine, instances)
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

    # Written even when `--limit` refuses an entry. A truncated run's Predictions
    # are still the only record of what happened, and the stored header carries
    # the limit so nobody can mistake it for the benchmark.
    stored = run_path(rung, split, provenance)
    write_run(
        stored,
        rung=rung,
        split=split,
        provenance=provenance,
        predictions=predictions,
        limit=limit,
    )

    typer.echo(render_terminal(report, provenance, loaded.report, wall_clock))
    typer.echo(f"\n  Wrote {len(predictions)} predictions to {stored}")

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

    prepend_entry(
        results,
        render_entry(report, provenance, loaded.report, wall_clock, note, predictions=stored),
    )
    typer.echo(f"\n  Wrote entry to {results}")


@app.command(name="compare")
def compare_runs(
    a: Annotated[Path, typer.Option(help="Stored run for the lower rung.")],
    b: Annotated[Path, typer.Option(help="Stored run for the upper rung.")],
) -> None:
    """Test whether one rung's Top-1 really beats another's, on the same Instances.

    The Wilson interval on each row describes that row alone, and it treats two
    rows as independent samples. They are not. Every rung answers the same
    Instances, so the sampling error is shared, and two overlapping intervals do
    not mean two rungs are indistinguishable.

    Issue 01 made this the milestone's deciding instrument rather than a
    refinement. Rung 4's whole available delta over rung 3 is about 6.6 points
    against a ±6pp interval, so a perfect agent would still publish an
    inconclusive row on unpaired intervals.
    """
    loaded = load_verified_set()
    splits = load_splits()

    left = read_run(a)
    right = read_run(b)

    if left.split != right.split:
        raise typer.BadParameter(
            f"{left.rung} ran on split {left.split!r} and {right.rung} on {right.split!r}"
        )
    truncated = [run.rung for run in (left, right) if run.is_truncated]
    if truncated:
        raise typer.BadParameter(
            f"truncated runs are not comparable: {', '.join(truncated)}. "
            "A truncated run is scored on a different instance set."
        )

    instances = splits.select(loaded.instances, left.split)
    try:
        result = compare(
            left.predictions,
            right.predictions,
            instances,
            a=left.rung,
            b=right.rung,
        )
    except ValueError as refused:
        raise typer.BadParameter(str(refused)) from refused

    typer.echo(render_comparison(result, left.provenance, right.provenance))


if __name__ == "__main__":
    app()
