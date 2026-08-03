"""Command-line entry point.

Kept deliberately thin: commands wire arguments to library calls and print
results. Logic lives in the package, so it stays testable without a subprocess.
"""

from __future__ import annotations

import typer

from faultloc import __version__

app = typer.Typer(
    name="faultloc",
    help="Fault localization from issue reports, measured as a ladder of baselines.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def evaluate(
    rung: str = typer.Option("bm25", help="Which rung to evaluate: bm25 | embed | rerank | agent"),
    split: str = typer.Option("dev", help="Dataset split: dev | test"),
    limit: int = typer.Option(0, help="Evaluate only the first N instances; 0 means all."),
) -> None:
    """Run a rung against a split and report Top-1, Recall@3, Recall@5, cost, latency.

    M1 implements the ``bm25`` rung only.
    """
    raise NotImplementedError(f"rung={rung} split={split} limit={limit}")


if __name__ == "__main__":
    app()
