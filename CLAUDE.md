# faultloc-eval

Fault localization from issue reports — given a bug report, predict which source file(s) must change. Built as a measured ladder (BM25 → embedding retrieval → LLM rerank → tool-using agent), evaluated against SWE-bench Verified plus a self-mined post-cutoff contamination control.

**The evidence is half the deliverable.** Anyone can wire an LLM to a repository; the claim here is knowing whether it works and when it doesn't. That is why the rules below have teeth.

## Never state external facts from memory

**Search before naming any model, price, capability ranking, availability, or library API.** Training data goes stale; this repo's ADRs are decisions made against it.

If a search is unavailable or fails, write *"I believe X — unverified"*. Never present a recalled fact as a recommendation.

This rule exists because it was broken three times in one session: a model named in ADR-0007 whose stated justification had already stopped holding; a pinned model never compared against current alternatives, which hid a 59% corpus loss behind a documented "accepted consequence"; and a capability ranking asserted that was smaller than this project's own confidence interval. Each arrived wrapped in a recommendation table, which made it harder to spot than a hedge would have been.

## Non-negotiables

**Every published number traces to a `RESULTS.md` entry**, emitted by the run itself. Never type a figure by hand — check README figures against the log by string match, not by eye. That has caught real errors.

**Never publish from a dirty tree.** `code_version` suffixes the SHA with `-dirty` and the entry carries a warning. Discard the run, commit, re-run. A number produced from a tree matching no commit is worse than none, because it looks trustworthy.

**Cost and latency sit beside every accuracy figure**, always, including when cost is `$0.00`.

**Top-1 carries a 95% Wilson interval.** At n=244 that is ±6pp — wider than every gap in the ladder so far. When intervals overlap, say so; never let table adjacency imply a ranking. Recall@k has no interval yet: report it as direction, not magnitude.

**Change one variable at a time, or publish an Ablation that separates them.** M3's entire result — that indexing function bodies, not chunking, moved the number — came from this. A single delta over two changes credits the wrong one.

**A rung's value is its delta over the rung below, priced.** Inserting a system between two rungs changes what the rung above is credited with. See `CONTEXT.md` for the numbering.

**Null results are published as findings.** Rung 2 did not beat rung 1; that is in the README, not buried.

**Corrections are recorded, not edited away.** Overturned predictions and wrong ADR reasoning stay on the record with the correction beside them. A wrong prediction that measurement overturned is better evidence of a working method than one that happened to be right.

**A test you did not watch fail is not evidence.** Three near-vacuous tests shipped in this repo before being caught — each passed with *and* without the fix it claimed to verify. Stash the fix, watch the test fail, restore it.

## Commands

```bash
uv run pytest                                    # ~290 tests
uv run ruff check && uv run ruff format
uv run faultloc evaluate --rung <name> --split dev [--limit N] [--no-write]
uv run faultloc index --split dev                # rung 2's vector index, ~2.5h
```

Rungs: `bm25`, `bm25-chunks`, `bm25-chunks-bodies`, `embed`, `hybrid`.

`--limit` refuses to write a results entry — a truncated run is scored on a different instance set.

## Layout

| Path | What |
|---|---|
| `CONTEXT.md` | Domain language. Read before naming anything. |
| `docs/adr/` | Decisions with rationale and rejected alternatives |
| `docs/milestones.md` | M1–M9, one line each; only the current one is sliced |
| `RESULTS.md` | Every number, newest first, machine-written |
| `.scratch/<milestone>/` | PRD + issues for the current milestone |
| `src/faultloc/rungs/` | One module per rung; all satisfy the `Rung` protocol |
| `scripts/` | One-off measurements that informed a decision |
| `data/` | Gitignored except `splits/` and `bench/` |

Embedding support is an optional extra: `uv sync --extra embed` (torch, sentence-transformers). Rung 1 must stay runnable without it.

## Gotchas learned the hard way

- **A run's own `RESULTS.md` write dirties the tree for the next run.** Two evaluations back-to-back can never both be clean — commit between them.
- **The index is gitignored, content-keyed, and takes ~2.5 hours.** It survives chunk-definition changes only if the content is unchanged; changing what a chunk contains invalidates all of it.
- **zsh does not word-split unquoted expansions.** `set -- $spec` in a loop passes the whole string as one argument.
- **`np.save` appends `.npy`** to a path lacking it, which breaks write-then-rename unless you pass a file handle.
- **Piping a long-running command through `grep` buffers its progress output.** Track progress another way or drop the pipe.

## Agent skills

**Issue tracker** — issues live as markdown under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

**Triage labels** — the five canonical roles plus a local `done`. See `docs/agents/triage-labels.md`.

**Domain docs** — single-context: `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.
