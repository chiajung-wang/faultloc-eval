# ADR-0006: SWE-bench Verified as the anchor, a self-mined Fresh Set as the control

**Status:** Accepted · 2026-08-03

## Context

The project reports a Top-1 accuracy number. That number means nothing until two questions have answers: *compared to what?* and *did the model localize, or did it remember?*

The first question needs a dataset that other people have published numbers against. The second needs instances that no evaluated model could hold in its training data. No single existing dataset does both. A benchmark becomes established precisely because it stays public long enough for models to train on it.

## Decision

Two evaluation sets, both frozen before any tuning.

**Verified Set** — SWE-bench Verified, pinned:

| Field | Value |
|---|---|
| Hugging Face ID | `princeton-nlp/SWE-bench_Verified` |
| Config | `default` |
| Split | `test` |
| Revision | `c104f840cc67f8b6eec6f759ebc8b2693d585d4a` |
| Instances | 500, across 12 Python repositories |

The code pins the revision. It never resolves to `main`. A dataset that updates silently invalidates a result silently.

**Fresh Set** — self-mined GitHub issues, closed *after* the evaluated model's training cutoff, target 150–300 instances. Mined per M6. The same Instance Filter code path derives its ground truth, so the two numbers stay comparable.

[ADR-0010](0010-fresh-set-mining.md) settles every parameter this ADR left open: the threshold date, the mining criteria, the estimator, and the reweighting that django's absence forces.

The headline metric is reported on both. **This ADR originally called the gap between them the contamination estimate. That is superseded.** A raw gap mixes memory with task difficulty, and the two sets turned out to hold opposite repo mixes. [ADR-0010](0010-fresh-set-mining.md) replaces it with a reweighted difference of two drops.

## Rationale

**Why SWE-bench Verified rather than the full benchmark.** "Verified" names 500 instances that human annotators confirmed are solvable and whose issue text specifies the problem. The full 2294-instance set holds issues that are under-specified. It also holds issues whose linked PR does something other than what the issue asked. For a localization task, an under-specified issue is unscoreable noise, not difficulty.

**Why an external benchmark at all.** Published localization numbers exist against Verified (Agentless, AutoCodeRover, and others). A self-mined-only project reports a number that floats free. Nobody, including the author, can tell whether 40% is good. Per ADR-0001, cite those published numbers only with an explicit note that instance subsets differ. This project's filter drops instances that they kept.

**Why the Fresh Set is not optional.** Every Verified instance predates current model cutoffs by roughly three years. The newest dates from **2023-08-07**. The repositories are among the most-starred Python projects on GitHub. Their code, issues, and fixing commits therefore appear in training data repeatedly and in several forms. Any rung-3 or rung-4 accuracy number on this set mixes localization skill with recall, and nothing inside the set can separate the two. The Fresh Set is the only instrument that can.

Either outcome is publishable. A gap means the public number was inflated and the project measured it. No gap is evidence that the system generalizes, which is a stronger claim than the headline number alone supports.

**Confounder control on the Fresh Set.** Mine from the *same repositories* wherever they still show post-cutoff activity. Otherwise a measured gap could mean repo difficulty rather than contamination, and the control proves nothing.

## Consequences

**Python only.** Both sets are Python. The project claims nothing about other languages, and must say so rather than implying generality.

**The aggregate number is largely a Django number.** Verified instance distribution:

| Repo | Instances |
|---|---|
| django/django | 231 |
| sympy/sympy | 75 |
| sphinx-doc/sphinx | 44 |
| matplotlib/matplotlib | 34 |
| scikit-learn/scikit-learn | 32 |
| pydata/xarray | 22 |
| astropy/astropy | 22 |
| pytest-dev/pytest | 19 |
| pylint-dev/pylint | 10 |
| psf/requests | 8 |
| mwaskom/seaborn | 2 |
| pallets/flask | 1 |

Django is 46% of the set. A change that helps one large, deeply-nested, convention-heavy codebase moves the headline number on its own. **Every report therefore carries per-repo Top-1 beside the aggregate.** Without it, the aggregate quietly measures Django-specific behavior.

**Verified is contaminated by construction.** Every report labels it that way. It is the anchor, never the evidence that the system generalizes.

**The Fresh Set is not human-validated.** It inherits none of Verified's quality guarantee, so its instances are noisier. Three things reduce that risk: identical filter code, published mining criteria, and a manual audit of a sample before the set freezes.

**Time pressure cannot drop M6.** Without it the project reports a contaminated number with no control. That is the overclaim this ADR exists to prevent.

## Alternatives rejected

- **Full SWE-bench (2294 instances)** — more data, but it holds under-specified issues that add unscoreable noise. Human validation is the exact property this project pays for
- **SWE-bench Lite (300 instances)** — filtered toward easy single-file fixes, and the most-reported subset in the literature. It is therefore both the easiest and the most saturated, and an anchor here flatters the result
- **Defects4J / BugsInPy** — curated fault datasets, but no comparable body of published *LLM localization* numbers exists to anchor against, and issue text quality varies
- **Verified only, no Fresh Set** — cheapest path to a number. It leaves that number indefensible under the first contamination question anyone asks
- **Fresh Set only** — honest, unanchored, and unreviewable. 40% would mean nothing to a reader
