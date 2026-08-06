# ADR-0001: Ground truth is source files in the fixing PR, capped at three

**Status:** Accepted · 2026-07-31

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
