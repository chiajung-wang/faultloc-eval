# 02 — ADR-0008: rerank design, budget, and determinism

Status: done

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

- [x] `docs/adr/0008-llm-rerank.md` in the existing ADR format, with rationale and rejected alternatives
- [x] The determinism decision stated, with what a rung-3 `RESULTS.md` entry does and does not assert under it
- [x] Prompt content decided, with the token cost of each option estimated from issue 01's chosen K
- [x] Models named with a stated reason each, and pinned by exact model ID
- [x] Expected dev-split cost per model, and a hard spend cap
- [x] A revisit condition, as ADR-0007 has
- [x] `CONTEXT.md` updated if the decision introduces or renames domain language

## Notes

HITL because it spends the user's money and because the determinism question changes what every rung-3 number means.

Model IDs and pricing must be checked rather than recalled. ADR-0007's first draft named an embedding model from memory and the stated reason had already stopped holding — the same failure is available here and is cheap to avoid.

Worth deciding here rather than discovering later: whether the model returns a ranking or a single choice. A full reordering is more useful to Recall@k; a single pick is cheaper and matches Top-1, which is the headline metric.

## Blocked by

- [01 — The union candidate set and its recall ceiling](01-union-recall-ceiling.md) — sets K, which sets the token count, which sets the budget

## Comments

**Closed 2026-08-05.** [ADR-0008](../../../docs/adr/0008-llm-rerank.md) landed. Four decisions, one term added to `CONTEXT.md` (**Evidence Chunk**), no money spent yet.

Prompt size was measured before the model was chosen, which turned out to be the right order: [`scripts/prompt_token_cost.py`](../../../scripts/prompt_token_cost.py) shows the issue text is 420 tokens against 4,286 for twenty candidates' body chunks. **The payload, not the model, is what the budget binds on** — paths-only fits every model on the price list, body chunks fit only the cheap tier.

| Decision | Settled as |
|---|---|
| Provider | Together, `init_chat_model(model_provider="together")` |
| Models | `deepseek-ai/DeepSeek-V4-Flash-0731`, `MiniMaxAI/MiniMax-M3` |
| Payload | path + Evidence Chunk, K=20, 1.19 M input tokens/run |
| Output | full reordering of 20 |
| Thinking mode | measured, not chosen — 2 models × on/off = 4 runs, $1.92 |
| Determinism | **dropped.** Single sampled run, variance unmeasured, stated in the entry |
| Budget | $1.50/run hard cap, $5.00 milestone; supersedes the PRD's $0.50 |

### Two things the ADR settles that the issue did not ask about

**Which of the four runs is the ladder's rung-3 row** — declared in advance as Flash/thinking-on, so the headline cannot be whichever run wins. The issue's "which models, and why those" question quietly assumed one run per model.

**The `test_is_deterministic` assertion is dropped rather than satisfied.** Both mechanisms on offer would have let the word "deterministic" stand while meaning something weaker — a replay of a committed cache, or `temperature=0`, which thinking-on models ignore outright per DeepSeek's API docs.

### What went unresolved

The **2,000 thinking-tokens-per-instance estimate is a guess**, and every cost in the table moves with it. It is the one number in the ADR that was not measured or checked against a source. The $1.50 cap is what makes it safe to guess; issue 03's first run replaces it.

**No variance repeats are budgeted.** At n=244 the ±6pp Wilson interval would swallow any run-to-run variance under ~2pp, so repeats were expected to be uninformative — but that is a prediction, not a measurement, and it becomes load-bearing if rung 3's delta over rung 2.5 is small. Second known measurement gap, alongside Recall@k's missing interval.
