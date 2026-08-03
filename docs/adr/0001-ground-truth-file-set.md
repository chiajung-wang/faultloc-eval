# ADR-0001: Ground truth is source files in the fixing PR, capped at three

**Status:** Accepted · 2026-07-31

## Context

Scoring fault localization requires knowing which files were "the answer". The mechanical source is the pull request that closed the issue — but a real PR touches source files, test files, documentation, changelogs, and lockfiles, and some PRs touch thirty files because they are refactors rather than fixes.

Without a stated rule, the metric measures the wrong thing and no reader can reproduce it.

## Decision

The Ground-Truth File Set is derived by:

1. Take all files modified by the linked, merged PR
2. Drop non-source files — tests, docs, config, lockfiles, changelogs
3. If more than **3** source files remain, drop the instance entirely
4. Publish the rejection rate, broken down by drop reason

## Rationale

A test file is a *consequence* of a fix, not the location of the bug — requiring the system to predict it measures a different task. Documentation is never where the bug is.

The cap exists because an instance whose fix touches twenty source files has no meaningful single answer; "where is the bug" is ill-posed for it. Including such instances adds noise that cannot be diagnosed, only absorbed into a lower score.

Three is chosen to match how curated fault-localization benchmarks constrain instances, while keeping multi-file fixes representable.

## Consequences

**Accepted cost:** the benchmark skews easier than the raw issue distribution. This is a real bias and must not be hidden.

**Required mitigation:** the Filter Rate is published with every result set, per drop reason. Unreported filtering is the failure mode this ADR exists to prevent — it converts an honest constraint into an overclaim.

**Comparability limit:** published numbers from other work used different subsets. They may be cited only alongside an explicit statement that the instance sets differ.

## Alternatives rejected

- **All PR files** — the system would be penalised for failing to predict `CHANGELOG.md`
- **Source files, no cap** — retains ill-posed refactor instances; low scores become undiagnosable
- **Single-file instances only** — cleanest metric, but filters roughly half the data and invites a fair accusation of cherry-picking
