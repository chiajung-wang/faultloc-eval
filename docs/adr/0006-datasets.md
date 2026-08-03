# ADR-0006: SWE-bench Verified as the anchor, a self-mined Fresh Set as the control

**Status:** Accepted · 2026-08-03

## Context

The project reports a Top-1 accuracy number. That number is only meaningful if two questions have answers: *compared to what?* and *did the model localise, or did it remember?*

The first question needs a dataset other people have published numbers against. The second needs instances that could not have been in any evaluated model's training data. No single existing dataset does both — an established benchmark is established precisely because it has been public long enough to be trained on.

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

The revision is pinned in code, not left to resolve to `main`. A silently updated dataset is a silently invalidated result.

**Fresh Set** — self-mined GitHub issues, closed *after* the evaluated model's training cutoff, target 150–300 instances. Mined per M6. Ground truth is derived by the same Instance Filter code path as the Verified Set, so the two numbers are comparable.

The headline metric is reported on both. The gap between them is the contamination estimate.

## Rationale

**Why SWE-bench Verified rather than the full benchmark.** "Verified" means 500 instances that human annotators confirmed are solvable and whose issue text actually specifies the problem. The full 2294-instance set contains issues that are under-specified or whose linked PR does something other than what the issue asked. For a localization task, an under-specified issue is unscoreable noise, not difficulty.

**Why an external benchmark at all.** Published localization numbers exist against Verified (Agentless, AutoCodeRover, and others). A self-mined-only project reports a number that floats free — nobody, including the author, can tell whether 40% is good. Per ADR-0001 those published numbers may be cited only with an explicit note that instance subsets differ, since this project's filter drops instances they kept.

**Why the Fresh Set is not optional.** Every Verified instance predates current model cutoffs by roughly three years — the newest was created **2023-08-07**. The repositories are among the most-starred Python projects on GitHub, so their code, issues, and fixing commits appear in training data repeatedly and in multiple forms. Any accuracy number from rung 3 or rung 4 on this set is a mix of localization skill and recall, and nothing internal to the set can separate them. The Fresh Set is the only instrument that can.

Either outcome is publishable. A gap means the public number was inflated and the project measured it. No gap is evidence the system generalises, which is a stronger claim than the headline number alone supports.

**Confounder control on the Fresh Set.** Mine from the *same repositories* wherever they still have post-cutoff activity. Otherwise a measured gap could be repo difficulty rather than contamination, and the control proves nothing.

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

Django is 46% of the set. A change that helps one large, deeply-nested, convention-heavy codebase moves the headline number on its own. **Per-repo Top-1 is therefore reported alongside the aggregate**, or the aggregate is quietly measuring Django-specific behaviour.

**Verified is contaminated by construction** and is labelled that way everywhere it is reported. It is the anchor, never the evidence of generalisation.

**The Fresh Set is not human-validated.** It inherits none of Verified's quality guarantee, so its instances are noisier. Mitigation: identical filter code, published mining criteria, and a manual audit of a sample before the set is frozen.

**M6 cannot be dropped under time pressure.** Without it the project reports a contaminated number with no control, which is the overclaim this ADR exists to prevent.

## Alternatives rejected

- **Full SWE-bench (2294 instances)** — more data, but includes under-specified issues that add unscoreable noise. Human validation is exactly the property being paid for
- **SWE-bench Lite (300 instances)** — filtered toward easy single-file fixes and the most-reported subset in the literature, so it is both the easiest and the most saturated. Anchoring here flatters the result
- **Defects4J / BugsInPy** — curated fault datasets, but with no comparable body of published *LLM localization* numbers to anchor against, and issue text quality varies
- **Verified only, no Fresh Set** — cheapest path to a number, and leaves it indefensible under the first contamination question anyone asks
- **Fresh Set only** — honest, unanchored, and unreviewable. 40% would mean nothing to a reader
