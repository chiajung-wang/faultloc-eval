# faultloc-eval — PRD

## Problem

When a bug report arrives, the expensive first step is deciding *where* the bug lives — which file, which owner. Writing the fix usually happens afterwards, by a human. Most LLM work on this problem skips straight to generating patches, where the score is decided almost entirely by which model was called.

This project answers the earlier, cheaper, more useful question: **given an issue report, which source file must change?**

## Deliverable

Two halves, weighted equally:

1. **A system** — a ladder of four localization approaches, the top rung a tool-using agent, deployed and clickable.
2. **The evidence** — a reproducible benchmark, published numbers per rung with cost and latency, a contamination control, and a calibrated confidence model that lets the system abstain.

The second half is the differentiator. Anyone can wire an LLM to a repository. The claim here is *knowing whether it works, and when it doesn't.*

## Scope

**In:** issue text → ranked file paths + calibrated confidence. Read-only repository access. Offline benchmark evaluation. A deployed API and replay UI.

**Out:** patch generation, test execution, sandboxed environments, multi-agent orchestration, non-Python repositories. Each exclusion is a deliberate cost decision — see the ADRs.

## Success criteria

The project succeeds if all of these are true, regardless of how high the accuracy number lands:

- Every reported number is traceable to a model, a dataset split, a commit, and a date
- The Instance Filter's rejection rate is published per drop reason
- Each rung's delta over the rung below is reported at its cost and latency, including rungs that add nothing
- The Verified/Fresh accuracy gap is measured and stated, whichever direction it goes
- The confidence model's ECE and reliability diagram are published
- A reviewer can regenerate the dataset from the same inputs

A null result — the agent failing to beat retrieval, or no contamination gap — is a reportable finding, not a failure.

## Non-goals

Beating a leaderboard. Competing with patch-generation agents. Visual design.

## Primary metric

Top-1 accuracy on the Ground-Truth File Set. Secondary: Recall@3, Recall@5, accuracy-vs-coverage curve. Cost ($) and latency (s) reported alongside every accuracy figure, always.

## Users

The reader of the README is the primary user: a reviewer deciding in ninety seconds whether the author can build and evaluate an LLM system. The replay gallery exists so that decision can be made by clicking rather than reading.

## Constraints

Per run: $0.50, 25 tool calls, 120 seconds. Live demo runs rate-capped with a hard daily budget. All model calls server-side.

## Open questions

- Index-per-unique-commit caching strategy at rung 2 (~500 base commits across ~12 repos)
- Fresh Set size — 150 or 300 — traded against mining time and per-instance evaluation cost
- Which embedding model at rung 2, and whether local or hosted
