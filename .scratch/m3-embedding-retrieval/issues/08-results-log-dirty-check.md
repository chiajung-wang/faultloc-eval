# 08 — The results log dirties its own provenance check

Status: ready-for-agent

## Parent

[M3 PRD](../PRD.md)

## What to build

`code_version` suffixes the code SHA with `-dirty` when the working tree has uncommitted changes, and the results entry carries a blockquote warning that the run is not reproducible. That guard is correct and has already caught a real mistake twice.

It also has a false positive: **a run writes its entry to `RESULTS.md`, which dirties the tree for the next run.** Two evaluations back-to-back therefore cannot both produce clean entries, even when the code is byte-identical and neither run is in any way unreproducible. Observed during issue 06, where the second of two runs was discarded and repeated for no reason other than the first run's own output.

The check tests the working tree, which is a proxy for "does this SHA describe the code that ran". A modified `RESULTS.md` cannot change a number — it is the run's output, never its input. Excluding the results log from the dirtiness check makes the proxy tighter, not looser.

Deliberately not done inline during issue 06: this narrows what `-dirty` means, and that is a provenance decision rather than a side effect of an unrelated change.

## Acceptance criteria

- [ ] The dirty check ignores the results log itself, and nothing else
- [ ] A tree dirty only by an unwritten results entry reports a clean SHA
- [ ] A tree dirty by any source, test, or config change still reports `-dirty` — pinned by a test, because this is the case the guard exists for
- [ ] Two evaluations run back-to-back both produce clean entries
- [ ] The reasoning is recorded where a reader of `RESULTS.md` would find it, since it changes what a clean SHA asserts

## Notes

Scope this narrowly. The temptation is a general "ignore untracked files" or "ignore docs" rule, which would let a genuinely modified tree report clean and would quietly gut the guarantee. One named path is the whole change.

The path is configurable at the CLI (`--results`), so the check should exclude whichever file this run will write, not a hard-coded name.

## Blocked by

None — can start immediately.
