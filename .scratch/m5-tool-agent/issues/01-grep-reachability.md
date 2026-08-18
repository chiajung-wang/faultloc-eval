# 01 — Is the target reachable? Grep-reachability where the Candidate Set misses

Status: done

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

- [x] The script identifies the dev-split Instances whose union Candidate Set holds no ground-truth file in the top 20
- [x] For each, it reports whether `git grep` reaches a ground-truth file from issue-text patterns
- [x] Results break out by pattern class and by repo
- [x] The script calls no model and writes no `RESULTS.md` entry
- [x] Pattern extraction is deterministic and covered by unit tests on fixed issue text
- [x] The 6 cached Off-List Paths are existence-checked and reported
- [x] `uv run pytest` and `uv run ruff check` clean

## Notes

This runs before ADR-0009 so that the ADR cites a measured number instead of an assumption. A serial step on free work is worth it here, because the finding could change rung 4's design.

**A low number is a finding, not a failure.** If few of the missed Instances are greppable, that is an argument about the tool roster, and the ADR must answer it rather than proceed past it.

The pattern extraction is the part with a real design choice in it. Keep it crude and legible. A clever extractor would make the number a property of the extractor rather than of the corpus, and the agent will write its own patterns anyway. What this measures is whether the *information* is present, not whether one heuristic finds it.

## Blocked by

None - can start immediately.

## Comments

**Closed 2026-08-07.** `scripts/grep_reachability.py`, `src/faultloc/issue_patterns.py`, and `RepoStore.grep`. Cost $0, and no model ran.

**The measurement reproduced the published ceiling exactly.** hit@20 = 88.9%, and 27 Instances of 244 hold no Ground-Truth File in the list. The cache reconstruction also hit 244 of 244 replies, so the prompt this script builds is byte-identical to the one M4 paid for.

### Rung 4's premise holds, and its ceiling is now a number

| | Share of the 27 | Instances |
|---|---|---|
| reachable at all | **63.0%** | 17 |
| reachable within a 30-hit cap | **59.3%** | 16 |
| lost to truncation | 3.7% | 1 |

So a tool-using Rung raises the ceiling from **88.9% to about 95.5%**. That is 16 more Instances of 244, or **6.6pp**.

**That number is the sharpest thing this measurement produced, and it is a warning.** The best rung-3 cell scores 79.1%. A rung 4 that found *every* reachable Instance and lost nothing else would reach about 85.7%, so its whole available delta is **6.6pp against a ±6pp Wilson interval**. A perfect agent would still publish an inconclusive row on unpaired intervals. Issue 02's paired test is not an improvement here. It is the only instrument that can read this milestone's result.

### Error strings reach nothing at all

Zero of 27. A complete null, and it is the cleanest finding here.

A report pastes a *rendered* message and the code holds the *template*, so `"cannot convert 'NoneType' object to str"` appears in no source file. A literal search cannot bridge that.

The consequence for issue 05 is specific. `search_code` must not be fed pasted error text. The identifiers *inside* a message are what carry the signal, and an exception name reaches its file where the message never does.

| Pattern kind | reachable | within cap |
|---|---|---|
| dotted names | **44.4%** | 37.0% |
| identifiers | 29.6% | 25.9% |
| traceback paths | 7.4% | 7.4% |
| error strings | **0.0%** | 0.0% |

Dotted names carry most of the reach. Traceback paths carry very little, which is consistent with a traceback naming where an exception surfaced rather than where the fix belongs.

### A 30-hit cap is nearly free

Truncation cost one Instance of 27. So `HIT_CAP = 30` is a defensible constant for issue 05, and the number is measured rather than chosen.

### The sphinx prediction was half wrong, and that record stays

Issue 01 predicted that `sphinx` would be unreachable by every pattern kind, because its reports describe rendered output. **It reaches 50% of its 8 missed Instances.** Its vocabulary is in the code more often than predicted, which is the same correction M1's sphinx prediction took at M3.

| Repo | missed | within cap |
|---|---|---|
| django/django | 10 | 80.0% |
| sphinx-doc/sphinx | 8 | 50.0% |
| sympy/sympy | 5 | 40.0% |
| matplotlib/matplotlib | 1 | 100.0% |
| pylint-dev/pylint | 1 | 100.0% |
| astropy/astropy | 1 | 0.0% |
| pytest-dev/pytest | 1 | 0.0% |

n=27 in total and n=1 for four repos. **Read this as direction and never as magnitude.**

### The footnote validates the Q2 guardrail decision

6 Off-List Paths from the cached `gpt-oss-high` cell. **5 exist at their `base_commit`. One does not.**

The one the Path Guardrail catches is `django/db`, which is a directory and not a file. That is exactly the class the guardrail exists for.

The other five are real files, and all five are `sphinx` — the repo that sits exactly on its own ceiling. Rung 3 reached outside the list precisely where the list was worst. **Treating an Off-List Path as a hallucination would have discarded five real files**, which is the error `CONTEXT.md` now records and the reason rung 4 keeps them.

Catch rate on this cell is 1 of 6. The cell produced the fewest Off-List Paths of M4's four, so treat the rate as a single observation.

### What this does not say

The 63.0% comes from a deliberately crude extractor. The agent writes its own patterns, so this is a **necessary condition and not a prediction**. A pattern `git grep` cannot follow, an agent cannot follow either. A pattern it can follow, the agent may still never write.

### Two defects found by watching tests fail

- `_DOTTED` filed `models.query.py` as a dotted name. The guard compared against extracted paths, and the fragment is not the path. Now excluded by suffix.
- **`_is_a_version` was dead code.** Removing it broke no test, because `_DOTTED` requires every segment to start with a letter or an underscore, so a matched segment can never be all digits. The version test had passed for the wrong reason. The check is gone and the test now guards the regex that does the work.

Two tests were also near-vacuous and were replaced. `patterns(x) == patterns(x)` survives set-based deduplication, because a set is stable inside one process. And a tree-order assertion survives an added `sort()`, because git's byte-order walk matches `sorted()` for these paths. That test now claims only what it can hold.
