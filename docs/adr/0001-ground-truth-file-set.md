# ADR-0001: Ground truth is source files in the fixing PR, capped at three

**Status:** Accepted · 2026-07-31 · *amended 2026-08-18: raw pull request file lists put files into the Ground-Truth File Set that the deny-list never anticipated. See the [amendment](#amended-2026-08-18--the-deny-list-met-a-file-with-no-extension).*

## Context

To score fault localization, you must know which files were "the answer". The mechanical source is the pull request that closed the issue. But a real PR touches source files, test files, documentation, changelogs, and lockfiles. Some PRs touch thirty files because they refactor rather than fix.

Without a stated rule, the metric measures the wrong thing and no reader can reproduce it.

## Decision

Derive the Ground-Truth File Set as follows:

1. Take all files modified by the linked, merged PR
2. Drop non-source files — tests, docs, config, lockfiles, changelogs
3. If more than **3** source files remain, drop the instance entirely
4. Publish the rejection rate, broken down by drop reason

## Rationale

A test file is a *consequence* of a fix, not the location of the bug. A system that must predict it answers a different question. Documentation is never where the bug is.

The cap exists because an instance whose fix touches twenty source files has no meaningful single answer. For that instance, "where is the bug" is ill-posed. Such instances add noise that nobody can diagnose. The score absorbs the noise instead.

Three matches how curated fault-localization benchmarks constrain instances. It also keeps multi-file fixes representable.

## Consequences

**Accepted cost:** the benchmark skews easier than the raw issue distribution. This is a real bias and must not be hidden.

**Required mitigation:** every result set publishes the Filter Rate, per drop reason. This ADR exists to prevent one failure mode: a filter that nobody reports. Such a filter converts an honest constraint into an overclaim.

**Comparability limit:** published numbers from other work used different subsets. Cite them only alongside an explicit statement that the instance sets differ.

## Measured consequences (2026-08-03, Verified Set)

Filter run over all 500 gold patches once the implementation existed:

| Outcome | Count | Share |
|---|---|---|
| kept | 490 | 98.0% |
| dropped — `too_many_source_files` | 10 | 2.0% |
| dropped — `no_source_files` | 0 | 0.0% |

Ground-Truth File Set sizes among the kept: **431 one-file, 47 two-file, 12 three-file**. Top-1 is therefore a well-posed question for 88% of the benchmark. That is what makes it a defensible headline metric rather than an arbitrary one.

Per-repo keep rate is 95–100% everywhere except `pylint-dev/pylint` at 8/10. The filter is not quietly reshaping the repo distribution.

**The test-stripping rule is close to a no-op on this dataset, and the report must say so.** Across all 500 patches exactly two files were classified non-source:

```
pylint-dev__pylint-4661:            setup.cfg
scikit-learn__scikit-learn-12682:   examples/decomposition/plot_sparse_coding.py
```

Zero test files, because SWE-bench separates `patch` from `test_patch` when it builds the dataset. The tests were never in the field the filter reads. So **100% of the published 2.0% Filter Rate comes from the >3-file cap**. A report that calls the filter "strips tests, docs, and config" beside that number would credit rules that did no work here.

The rule is still correct and still required. The miner takes Fresh Set instances (M6) from raw PRs, which are *not* pre-split. There, test-stripping does the heavy work. The two catches above confirm that the doc and config rules fire correctly on real paths, just rarely.

## Alternatives rejected

- **All PR files** — the metric would penalize the system when it fails to predict `CHANGELOG.md`
- **Source files, no cap** — keeps ill-posed refactor instances. Low scores become undiagnosable
- **Single-file instances only** — cleanest metric, but drops roughly half the data and invites a fair accusation of cherry-picking

## Amended 2026-08-18 — the deny-list met a file with no extension

M6 mines raw pull requests, and this ADR predicted what would happen there. **The prediction holds.** Test-stripping fired on **38 of 56** sampled raw file lists, which is 68%. On the Verified Set it fired zero times, because SWE-bench separates `patch` from `test_patch`. The rule that did no work on the anchor does most of the work on the control.

The same sample surfaced a failure this ADR did not anticipate. Of 42 kept Ground-Truth File Sets, six held a file that no fix could ever live in:

```
AUTHORS                         x3   (pytest-dev/pytest)
.mailmap                        x1   (sympy/sympy)
sklearn/utils/_testing.py       x2   (scikit-learn/scikit-learn)
```

`AUTHORS` and `.mailmap` carry no extension, so no suffix rule reaches them. `_testing.py` is test infrastructure that sits outside `tests/` and starts with an underscore rather than `test_`, so neither test rule reaches it either.

**The harm is one-sided, which is why it is easy to miss.** A bogus Ground-Truth File cannot be retrieved by anything. It therefore deflates Recall@3 and Recall@5, and it leaves Top-1 untouched, because Top-1 asks only whether the top prediction is *somewhere* in the set. A headline that looks healthy would sit beside a Recall figure that is quietly wrong.

### The two rules

1. Drop a file whose basename holds no extension.
2. Drop test infrastructure: a basename containing `_testing`, and `conftest.py`.

### Why this does not change any published number

Both rules were run against the Verified Set before they landed. **0 of 490 Instances hold an extensionless or test-infrastructure Ground-Truth File.** The rules are a measured no-op on the anchor and take effect only on the control.

That measurement is the argument. A change to the Instance Filter is a change to what every past number means, so a filter rule that cannot be shown to be inert is a re-run of the whole ladder.

### What stays rejected

**A per-repo source-root allow-list**, keeping only paths under `sklearn/`, `lib/matplotlib/`, `src/_pytest/` and so on. It would also remove `build_tools/get_comment.py` and `xarray/util/generate_aggregations.py`, which the sample shows surviving. It reverses this ADR's deny-list decision, which exists so that `.pyx`, `.c` and `.js` fixes are not dropped in silence, and it adds per-repo configuration that every future repository must extend.

The deny-list still loses to an allow-list on precision. It wins on the failure mode that matters: an over-broad allow-list drops a real Ground-Truth File, and a dropped ground-truth file is indistinguishable from a wrong prediction downstream.
