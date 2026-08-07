# 01 — Is the target reachable? Grep-reachability where the Candidate Set misses

Status: ready-for-agent

## Parent

[M5 PRD](../PRD.md)

## What to build

A measurement script, in the shape of [`scripts/union_ceiling.py`](../../../scripts/union_ceiling.py). It runs free, it calls no model, and it answers the one question that decides whether rung 4 can work.

The union Candidate Set's hit@20 is 88.9% on the dev split. So about 27 Instances of 244 hold no ground-truth file anywhere in the list. **Those Instances are rung 4's entire target.** No reranker can be right on them, and they are the only source of headroom above the ceiling.

For each of those Instances, ask whether `git grep` could reach a ground-truth file from the issue text. Extract candidate patterns from the issue report, run them against the source files at `base_commit`, and record whether any pattern's hits include a ground-truth file.

Report the share of the missed Instances that are reachable, broken out **by pattern class**, because the classes are the evidence for what `search_code` must accept:

- quoted error strings and exception messages
- dotted identifiers and qualified names
- bare identifiers such as a function or class name
- traceback frame paths

Report the same figures per repo. `sphinx` is the case to watch, because its reports describe rendered output. If `sphinx` is unreachable by every pattern class, that is a named prediction rather than a surprise later.

The script prints its findings. It writes no `RESULTS.md` entry, because it scores no rung.

**Also, as a footnote:** `data/cache/responses` holds 248 entries for M4's `gpt-oss-high` cell, which produced 6 of the 92 Off-List Paths. Check whether those 6 paths exist at their Instance's `base_commit`. That is the only part of the off-list split that is free, and it is the first real evidence for the Path Guardrail's catch rate.

## Acceptance criteria

- [ ] The script identifies the dev-split Instances whose union Candidate Set holds no ground-truth file in the top 20
- [ ] For each, it reports whether `git grep` reaches a ground-truth file from issue-text patterns
- [ ] Results break out by pattern class and by repo
- [ ] The script calls no model and writes no `RESULTS.md` entry
- [ ] Pattern extraction is deterministic and covered by unit tests on fixed issue text
- [ ] The 6 cached Off-List Paths are existence-checked and reported
- [ ] `uv run pytest` and `uv run ruff check` clean

## Notes

This runs before ADR-0009 so that the ADR cites a measured number instead of an assumption. A serial step on free work is worth it here, because the finding could change rung 4's design.

**A low number is a finding, not a failure.** If few of the missed Instances are greppable, that is an argument about the tool roster, and the ADR must answer it rather than proceed past it.

The pattern extraction is the part with a real design choice in it. Keep it crude and legible. A clever extractor would make the number a property of the extractor rather than of the corpus, and the agent will write its own patterns anyway. What this measures is whether the *information* is present, not whether one heuristic finds it.

## Blocked by

None - can start immediately.
