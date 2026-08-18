# faultloc-eval — PRD

## Problem

When a bug report arrives, the expensive first step is to decide *where* the bug lives. Which file, and which owner. A human usually writes the fix afterwards. Most LLM work on this problem skips straight to generating patches. There, the choice of model decides almost the whole score.

This project answers the earlier, cheaper, more useful question: **given an issue report, which source file must change?**

## Deliverable

Two halves, weighted equally:

1. **A system** — a ladder of localization approaches, the top rung a tool-using agent, deployed and clickable. `CONTEXT.md` holds the current rung list. [ADR-0003](adr/0003-baseline-ladder.md) fixed four rungs. Rungs 2.5 and 2.6 arrived later.
2. **The evidence** — a reproducible benchmark, published numbers per rung with cost and latency, a contamination control, and a calibrated confidence model that lets the system abstain.

The second half is the differentiator. Anyone can wire an LLM to a repository. The claim here is different: *this project knows whether the system works, and when it does not.*

## Scope

**In:** issue text → ranked file paths + calibrated confidence. Read-only repository access. Offline benchmark evaluation. A deployed API and replay UI.

**Out:** patch generation, test execution, sandboxed environments, multi-agent orchestration, non-Python repositories. Each exclusion is a deliberate cost decision — see the ADRs.

## Success criteria

The project succeeds if all of these are true, whatever the accuracy number turns out to be:

- Every reported number traces to a model, a dataset split, a commit, and a date
- The project publishes the Instance Filter's rejection rate per drop reason
- The project reports each rung's delta over the rung below, at its cost and latency. This includes rungs that add nothing
- The project measures and states the Verified/Fresh accuracy gap, in whichever direction it goes
- The project publishes the confidence model's ECE and reliability diagram
- A reviewer can regenerate the dataset from the same inputs

A null result is a reportable finding, not a failure. This covers an agent that fails to beat retrieval. It also covers a contamination gap that does not appear.

## Non-goals

Beating a leaderboard. Competing with patch-generation agents. Visual design.

## Primary metric

Top-1 accuracy on the Ground-Truth File Set. Secondary: Recall@3, Recall@5, accuracy-vs-coverage curve. Every accuracy figure carries a cost in dollars and a latency in seconds, always.

## Users

The reader of the README is the primary user. This reader is a reviewer. The reviewer decides in ninety seconds whether the author can build and evaluate an LLM system. The replay gallery exists so the reviewer can click instead of read.

## Constraints

`Run` named two different things, and it now names three. `CONTEXT.md` defines a **Budget** with one name per scope, and this document uses those names.

**Instance Budget**, one localization request at rung 4: **8 tool calls and 600 seconds**. It carries no dollar cap, because eight capped tool results cannot reach $0.05. The graph state checks it before each dispatch. See [ADR-0009](adr/0009-tool-using-agent.md).

This supersedes the 25 tool calls and 120 seconds this document carried before anyone measured a step. On the pinned route a step takes 4 to 8 seconds and a full reply takes about 44, so a 120-second cap would have fired on ordinary variance and a 25-call cap could never have been reached.

**Evaluation Budget**, one evaluation of a whole split: **$12**. It is checked against spend already incurred, so a run stops rather than report an overspend afterwards.

**Milestone Budget**: **$20** for M5. This supersedes ADR-0008's $2.00 and $5.00, which were set for a rung making one call per Instance.

The live demo serves requests under a rate cap and a hard daily budget. All model calls run server-side.

## Open questions

- How to cache the index per unique commit at rung 2 (~500 base commits across ~12 repos)
- Fresh Set size: 150 or 300. Trade this against mining time and per-instance evaluation cost

Closed:

- Which embedding model at rung 2, and whether it runs local or hosted. [ADR-0007](adr/0007-embedding-model.md) decided this.
