# 02 — ADR-0008: rerank design, budget, and determinism

Status: ready-for-human

## Parent

[M4 PRD](../PRD.md)

## What to build

`docs/adr/0008-llm-rerank.md`, settling four things before any money is spent.

**Determinism.** Every rung so far asserts `test_is_deterministic` — same instance, same ranking, every run — and every `RESULTS.md` entry implicitly claims a reader can regenerate the number from a commit, a dataset revision, and a seed. **An LLM cannot guarantee that.** Two options, and they mean different things:

- *Cache responses*, keyed by a hash of the exact prompt and model. A rerun is then free and byte-identical, and the cache is the reproducibility artifact — but it is local, so a third party regenerating from scratch still gets a different number.
- *Accept nondeterminism* and report variance across repeated runs, which is more honest about what the system is and multiplies the cost of every published figure.

This decides what a rung-3 entry in the results log asserts, which is why it is an ADR and not a code choice.

**What the model sees.** Paths alone are cheap and may be enough — a reranker choosing between `django/db/models/query.py` and `docs/conf.py` needs little else. Chunk text is richer and multiplies tokens by an order of magnitude. The decision drives the entire cost model, and the cheap option should be ruled out by measurement rather than by assumption.

**Which models, and why those.** M4 requires a cross-model table. Name the models and what each is there to show — a frontier model for the ceiling, a cheap one for the cost-effectiveness question. A table of models chosen because they were familiar is not a comparison.

**The budget.** The PRD sets $0.50, 25 tool calls, and 120 seconds per run. Rung 3 makes one call per instance, so state the expected total for a dev-split run per model, and a hard cap that stops the run rather than discovering the overspend afterwards.

## Acceptance criteria

- [ ] `docs/adr/0008-llm-rerank.md` in the existing ADR format, with rationale and rejected alternatives
- [ ] The determinism decision stated, with what a rung-3 `RESULTS.md` entry does and does not assert under it
- [ ] Prompt content decided, with the token cost of each option estimated from issue 01's chosen K
- [ ] Models named with a stated reason each, and pinned by exact model ID
- [ ] Expected dev-split cost per model, and a hard spend cap
- [ ] A revisit condition, as ADR-0007 has
- [ ] `CONTEXT.md` updated if the decision introduces or renames domain language

## Notes

HITL because it spends the user's money and because the determinism question changes what every rung-3 number means.

Model IDs and pricing must be checked rather than recalled. ADR-0007's first draft named an embedding model from memory and the stated reason had already stopped holding — the same failure is available here and is cheap to avoid.

Worth deciding here rather than discovering later: whether the model returns a ranking or a single choice. A full reordering is more useful to Recall@k; a single pick is cheaper and matches Top-1, which is the headline metric.

## Blocked by

- [01 — The union candidate set and its recall ceiling](01-union-recall-ceiling.md) — sets K, which sets the token count, which sets the budget
