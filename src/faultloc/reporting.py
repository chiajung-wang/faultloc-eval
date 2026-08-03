"""Render a scored run for the terminal and for `RESULTS.md`.

The results log is append-only and newest-first, and every entry carries the
three inputs that can change a number without anyone noticing: the code commit,
the dataset revision, and the split seed. Missing any one of them makes the
entry unreproducible, which is the failure this format exists to prevent.

Entries are emitted from a run, never hand-written, so a number and its
provenance cannot disagree.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from faultloc.dataset.verified import LoadReport
from faultloc.scoring import ScoreReport

RESULTS_HEADER = """# Results

Every number published anywhere in this repository traces to an entry below.
Entries are emitted by `faultloc evaluate`, never written by hand, so a figure
and its provenance cannot drift apart.

Top-1 is reported with a 95% Wilson interval. At these sample sizes a small
difference between two rungs or two repositories is not yet a result, and the
interval is what says so.
"""

UNRECORDED_NOTE = "_(not recorded)_"


@dataclass(frozen=True)
class Provenance:
    """Everything needed to reproduce a number."""

    code_sha: str
    dataset: str
    dataset_revision: str
    split: str
    seed: int
    command: str
    run_date: str

    @property
    def is_dirty(self) -> bool:
        return self.code_sha.endswith("-dirty")


def code_version(root: Path | None = None) -> str:
    """Short commit SHA, suffixed `-dirty` when the tree has uncommitted edits.

    The suffix matters more than the SHA. A number produced from a modified
    working tree cannot be reproduced from any commit, and an entry that hides
    that is worse than one with no provenance at all -- it looks trustworthy.
    """
    cwd = str(root) if root else None
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
            cwd=cwd,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        check=False,
        text=True,
        cwd=cwd,
    ).stdout.strip()
    return f"{sha}-dirty" if status else sha


def format_duration(seconds: float) -> str:
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}m {remainder:02d}s" if minutes else f"{remainder}s"


def _per_repo_line(report: ScoreReport) -> str:
    parts = [
        f"{repo.split('/')[-1]} {agg.n} @ {agg.top_1:.1%}"
        for repo, agg in sorted(report.by_repo.items(), key=lambda kv: -kv[1].n)
    ]
    return " · ".join(parts)


def _filter_line(load: LoadReport) -> str:
    drops = ", ".join(f"{reason} {count}" for reason, count in sorted(load.drops.items()))
    return (
        f"Filter: {load.total} → {load.kept} kept. "
        f"Dropped: {drops or 'none'} ({load.filter_rate:.1%})"
    )


def render_entry(
    report: ScoreReport,
    provenance: Provenance,
    load: LoadReport,
    wall_clock_s: float,
    note: str = "",
) -> str:
    """One `RESULTS.md` block."""
    low, high = report.overall.top_1_ci
    overall = report.overall

    dirty_warning = (
        "\n> **Uncommitted changes were present when this ran.** "
        "The code SHA does not fully describe it.\n"
        if provenance.is_dirty
        else ""
    )

    return f"""## {provenance.run_date} · {report.rung} · {report.split}
{dirty_warning}
| Metric | Value |
|---|---|
| Top-1 | {overall.top_1:.1%} (95% CI {low:.1%}-{high:.1%}) |
| Recall@3 | {overall.recall_3:.1%} |
| Recall@5 | {overall.recall_5:.1%} |
| Instances scored | {overall.n} |
| Wall clock | {format_duration(wall_clock_s)} |
| Cost | ${overall.cost_usd_total:.2f} (${overall.cost_usd_per_instance:.4f}/instance) |

**Per repo** — {_per_repo_line(report)}

**Stop conditions** — {", ".join(f"{k} {v}" for k, v in sorted(report.stop_conditions.items()))}

**Provenance**
- code `{provenance.code_sha}` · dataset `{provenance.dataset}` @ \
`{provenance.dataset_revision[:7]}` · split `{provenance.split}` (seed {provenance.seed})
- {_filter_line(load)}
- Reproduce: `{provenance.command}`

**Read**: {note or UNRECORDED_NOTE}
"""


def prepend_entry(path: Path, entry: str) -> None:
    """Insert `entry` directly under the header, newest first.

    Appending would bury the current number under history; rewriting the file
    would risk losing entries. Prepending keeps the log append-only in spirit
    and puts the number a reader wants at the top.
    """
    if not path.is_file():
        path.write_text(f"{RESULTS_HEADER}\n{entry}")
        return

    existing = path.read_text()
    if existing.startswith(RESULTS_HEADER):
        body = existing[len(RESULTS_HEADER) :].lstrip("\n")
        path.write_text(f"{RESULTS_HEADER}\n{entry}\n{body}")
    else:
        path.write_text(f"{entry}\n{existing}")


def render_terminal(
    report: ScoreReport,
    provenance: Provenance,
    load: LoadReport,
    wall_clock_s: float,
) -> str:
    """Human-readable summary. Same figures as the entry, wider layout."""
    low, high = report.overall.top_1_ci
    overall = report.overall

    lines = [
        f"{report.rung} · {report.split} · n={overall.n}",
        "",
        f"  Top-1      {overall.top_1:6.1%}   (95% CI {low:.1%}-{high:.1%})",
        f"  Recall@3   {overall.recall_3:6.1%}",
        f"  Recall@5   {overall.recall_5:6.1%}",
        f"  Wall clock {format_duration(wall_clock_s):>7}",
        f"  Cost       ${overall.cost_usd_total:.2f}"
        f"  (${overall.cost_usd_per_instance:.4f}/instance)",
        "",
        f"  {_filter_line(load)}",
        f"  Stops: {', '.join(f'{k} {v}' for k, v in sorted(report.stop_conditions.items()))}",
        "",
        f"  {'repo':30} {'n':>4} {'Top-1':>7}   95% CI",
    ]
    for repo, agg in sorted(report.by_repo.items(), key=lambda kv: -kv[1].n):
        repo_low, repo_high = agg.top_1_ci
        lines.append(f"  {repo:30} {agg.n:4d} {agg.top_1:7.1%}   {repo_low:5.1%}-{repo_high:5.1%}")

    lines += ["", f"  code {provenance.code_sha} · dataset @ {provenance.dataset_revision[:7]}"]
    if provenance.is_dirty:
        lines.append("  WARNING: uncommitted changes present; this run is not reproducible")

    return "\n".join(lines)


def today() -> str:
    return date.today().isoformat()
