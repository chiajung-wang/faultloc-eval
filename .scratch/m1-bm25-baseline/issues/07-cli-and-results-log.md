# 07 — Wire the CLI and open the results log

Status: ready-for-agent

## Context

Closes M1. `faultloc evaluate --rung bm25 --split dev` runs the whole pipeline and prints the numbers.

`RESULTS.md` starts here and becomes the project's running log. Every number published anywhere in the repo must be traceable to an entry in it.

## Decided: the `RESULTS.md` entry format

Append-only, newest entry first, one block per run:

```markdown
## 2026-08-05 · rung 1 (BM25) · dev

| Metric | Value |
|---|---|
| Top-1 | 31.4% (95% CI 25.1-38.3) |
| Recall@3 | 52.1% |
| Recall@5 | 61.9% |
| Instances scored | 210 |
| Wall clock | 4m 12s |
| Cost | $0.00 |

**Per repo** — django 96 @ 28.1% · sympy 31 @ 35.5% · … · other 6 @ 33.3%

**Provenance**
- code `a1b2c3d` · dataset `princeton-nlp/SWE-bench_Verified` @ `c104f84` · split `dev` (seed 20260803)
- Filter: 500 → 420 kept. Dropped: too_many_source_files 61, no_source_files 19 (16.0%)
- Reproduce: `faultloc evaluate --rung bm25 --split dev`

**Read**: one line on what the number means, or what was surprising.
```

Why each field earns its place:

- **Code SHA + dataset revision + split seed** — the three inputs that can change a number without anyone noticing. Missing any one makes the entry unreproducible.
- **Filter counts inside every block**, not stated once elsewhere — ADR-0001 requires the Filter Rate be published, and keeping it adjacent to the metric stops the two drifting apart.
- **Confidence interval on Top-1, never a bare percentage** — at ~210 instances the interval is roughly ±6pp, so a 2pp rung-to-rung delta is not yet a result. Hiding the interval invites exactly that misreading.
- **Cost and wall clock from the first entry**, even at `$0.00` — locked decision #3 puts cost and latency beside every accuracy figure. A column present from the start never needs retrofitting.
- **Reproduce line** — the literal command.
- **Read line** — where null results and surprises are recorded rather than quietly dropped.

## Acceptance criteria

- `faultloc evaluate --rung bm25 --split dev [--limit N]` runs end to end
- Prints Top-1 with its confidence interval, Recall@3, Recall@5, per-repo breakdown, instance count, wall-clock time
- Prints the Filter Rate with per-reason drop counts
- `RESULTS.md` created with the first entry in the format above
- The entry is emitted by the CLI, not hand-written, so a number and its provenance cannot disagree
- README updated with the first real number

## Notes

The results-log format set here is permanent. Design it so a later reader can tell exactly which code produced which number.
