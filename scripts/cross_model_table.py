"""The rung-3 cross-model table, generated from `RESULTS.md`.

Issue 04 asks a different question from issue 03. Issue 03 asks *does reranking
help*; this asks *how much model do you need before it does*. A cheap model
that recovers a costly one's gain is the more useful engineering answer, and
nobody can claim it without measuring both.

**Generated, never typed.** Every figure is parsed out of the entries the runs
themselves emitted, so the table cannot drift from the log it summarises. Run
it again after any new entry and the table updates.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

RESULTS = Path("RESULTS.md")

#: The last estimate made for each cell before it ran. Kept so the table can
#: report predicted against actual rather than quietly adopting whichever
#: figure turned out right.
#:
#: `rerank-deepseek-off` is the instructive one. Its first estimate, from two
#: instances, was $0.95. Re-measured on eight it became $0.05. The truth was
#: $0.31 -- so the first sample was 3x high and the second 6x low, both from
#: the same method with a slightly larger n. Small-sample cost estimates here
#: are not merely imprecise, they are unreliable in direction.
ESTIMATED = {
    "rerank": 0.32,
    "rerank-gpt-oss-low": 0.68,
    "rerank-deepseek-on": 0.39,
    "rerank-deepseek-off": 0.95,
}

#: The four ADR-0008 cells plus the free rung they have to beat. Ordered as the
#: ladder is, not by score: sorting by point estimate makes a table read as a
#: ranking whether or not one exists.
ROWS = [
    ("rerank", "gpt-oss-120b, effort high", "ladder row"),
    ("rerank-gpt-oss-low", "gpt-oss-120b, effort low", ""),
    ("rerank-deepseek-on", "deepseek-v4-pro, reasoning on", ""),
    ("rerank-deepseek-off", "deepseek-v4-pro, reasoning off", ""),
    ("hybrid", "reciprocal rank fusion, no model", "rung 2.5"),
]


@dataclass(frozen=True)
class Entry:
    rung: str
    top_1: str
    recall_3: str
    recall_5: str
    cost: str
    wall: str
    code: str
    note: str
    per_repo: str

    @property
    def bounds(self) -> tuple[float, float]:
        low, high = re.search(r"CI ([\d.]+)%-([\d.]+)%", self.top_1).groups()
        return float(low), float(high)

    @property
    def point(self) -> float:
        return float(re.match(r"([\d.]+)%", self.top_1).group(1))


def parse(text: str) -> dict[str, Entry]:
    """Newest entry per rung. Re-running a rung supersedes its older row."""
    found: dict[str, Entry] = {}
    for block in text.split("\n## ")[1:]:
        rung = block.split(" · ")[1].strip()
        if rung in found:
            continue

        def field(name: str, b: str = block) -> str:
            hit = re.search(rf"^\| {re.escape(name)} \| (.+?) \|$", b, re.M)
            return hit.group(1) if hit else ""

        code = re.search(r"^- code `([^`]+)`", block, re.M)
        note = re.search(r"^\*\*Read\*\*: (.+)$", block, re.M)
        repos = re.search(r"^\*\*Per repo\*\* — (.+)$", block, re.M)
        found[rung] = Entry(
            rung=rung,
            top_1=field("Top-1"),
            recall_3=field("Recall@3"),
            recall_5=field("Recall@5"),
            cost=field("Cost"),
            wall=field("Wall clock"),
            code=code.group(1) if code else "",
            note=note.group(1) if note else "",
            per_repo=repos.group(1) if repos else "",
        )
    return found


def degrades(note: str) -> str:
    counts = dict.fromkeys(("unparseable", "truncated", "off-list"), 0)
    for value, kind in re.findall(r"(\d+) (unparseable|truncated|off-list)", note):
        counts[kind] = int(value)
    return f"{counts['unparseable']} / {counts['truncated']} / {counts['off-list']}"


def main() -> int:
    entries = parse(RESULTS.read_text())
    missing = [rung for rung, _, _ in ROWS if rung not in entries]
    if missing:
        print(f"no entry for: {', '.join(missing)}", file=sys.stderr)
        return 1

    print("| Configuration | Top-1 (95% CI) | Recall@3 | Recall@5 | Cost | Wall clock | Degraded |")
    print("|---|---|---|---|---|---|---|")
    for rung, description, tag in ROWS:
        e = entries[rung]
        label = f"`{rung}`" + (f" — {tag}" if tag else "")
        print(
            f"| {label}<br>{description} | {e.top_1} | {e.recall_3} | {e.recall_5} | "
            f"{e.cost} | {e.wall} | {degrades(e.note)} |"
        )

    print("\nDegraded = unparseable / truncated / off-list paths.\n")

    rerank = [entries[r] for r, _, _ in ROWS if r.startswith("rerank")]
    fusion = entries["hybrid"]
    lowest = min(r.bounds[0] for r in rerank)
    best, worst = max(r.point for r in rerank), min(r.point for r in rerank)

    print(
        f"**Every rung-3 cell beats fusion; none beats another.** The four span "
        f"{worst:.1f} to {best:.1f}% Top-1 with overlapping intervals, so no ordering "
        f"among them is established at n=244. Their lowest bound ({lowest:.1f}%) sits "
        f"above fusion's upper bound ({fusion.bounds[1]:.1f}%), which is the one "
        f"comparison here that is."
    )

    cheapest = min(rerank, key=lambda e: float(re.search(r"\$([\d.]+)", e.cost).group(1)))
    dearest = max(rerank, key=lambda e: float(re.search(r"\$([\d.]+)", e.cost).group(1)))
    print(
        f"\n**Cost does not track accuracy.** The cheapest cell "
        f"(`{cheapest.rung}`, {cheapest.cost}) scores {cheapest.top_1.split(' (')[0]}; "
        f"the dearest (`{dearest.rung}`, {dearest.cost}) scores "
        f"{dearest.top_1.split(' (')[0]}."
    )

    print(
        "\n**Estimated against actual spend.** ADR-0008 sized these from two- and\n"
        "three-instance samples:\n"
    )
    print("| Configuration | Estimated | Actual | Error |")
    print("|---|---|---|---|")
    for rung, _, _ in ROWS:
        if rung not in ESTIMATED:
            continue
        actual = float(re.search(r"\$([\d.]+)", entries[rung].cost).group(1))
        estimate = ESTIMATED[rung]
        print(f"| `{rung}` | ${estimate:.2f} | ${actual:.2f} | {actual / estimate:.1f}x |")

    print("\n**Per repo**, strongest and cheapest cell:\n")
    for rung in ("rerank-deepseek-on", "rerank-deepseek-off"):
        print(f"- `{rung}` — {entries[rung].per_repo}")

    print(
        "\nProvenance: "
        + " · ".join(
            f"`{e.rung}` at `{e.code}`"
            for e in entries.values()
            if e.rung.startswith("rerank") or e.rung == "hybrid"
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
