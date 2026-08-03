# 07 — Wire the CLI and open the results log

Status: done

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

## Comments

**Closed 2026-08-03.** M1 is complete. The first entry in `RESULTS.md` was emitted by `faultloc evaluate --rung bm25 --split dev` at code `70b01bb`.

```
bm25 · dev · n=244
  Top-1       39.3%   (95% CI 33.4%-45.6%)
  Recall@3    59.3%
  Recall@5    68.5%
  Wall clock  1m 23s
  Cost        $0.00
  Filter: 500 → 490 kept. Dropped: too_many_source_files 10 (2.0%)
  Stops: answered 244
```

### The dirty-tree marker changed the order of work

`code_version` suffixes the SHA with `-dirty` when the working tree has uncommitted edits, and the entry carries a blockquote warning rather than a footnote. The first full run was made before the CLI itself was committed, and the warning fired correctly — so the run was repeated with `--no-write`, the code committed, and only then was the real entry generated. A number produced from a modified tree cannot be reproduced from any commit, and an entry that hides that is worse than one with no provenance at all because it looks trustworthy.

`code_version` returns `"unknown"` outside a repository rather than raising or inventing a value. Missing provenance is stated.

### Decisions

**`--limit` refuses to write an entry.** A truncated run is scored on a different instance set; admitting it to a log whose entire purpose is comparability would poison it.

**Entries are prepended, not appended**, so a reader meets the current number rather than the archaeology. Tested that repeated writes never lose an entry and never duplicate the header.

**The `Read` line defaults to `_(not recorded)_`** — visibly unfilled, so an entry lacking human interpretation does not read as finished.

### Two bugs found while wiring

**The rung was constructed inside the prediction loop.** A fresh `Bm25Rung` per instance discarded the blob-keyed token cache and the 21× content reuse behind it: 1.3s per instance against the 0.29s median measured in issue 05, which over the full dev split is roughly half an hour instead of eighty seconds. Hoisting it out of the loop was one line.

**A test that could not fail.** `assert code_version(tmp_path) in {"unknown", ""} or True` — the trailing `or True` made it vacuous. It was replaced with a real assertion that a non-repository directory reports `"unknown"`. A test that cannot fail is worse than no test: it occupies the slot where a real one would go, and reads as coverage.
