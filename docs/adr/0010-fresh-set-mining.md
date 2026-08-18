# ADR-0010: The Fresh Set mines GitHub after 2026-05-01, and Contamination is a difference of two drops

**Status:** Accepted · 2026-08-18

## Context

[ADR-0006](0006-datasets.md) declared the Fresh Set and left every parameter open. It named a target size, a source, and a purpose. It did not name a date, a comparison, or a rule for reading the result.

M5 made those parameters expensive. Rung 4 scores **88.1% Top-1 on a set that is contaminated by construction**, because the newest Verified Instance dates to 2023-08-07. The higher the ladder climbs on that set, the larger the share of the number that memory alone could explain. The **Tool-Reached** flag records whether a tool surfaced a path, and it cannot record whether the model needed the tool. Only a post-cutoff set can.

This ADR settles the open parameters. Every one of them was measured first, and the measurements sit in `.scratch/m6-fresh-set/grilling-decisions.md`.

## Decision

| # | Parameter | Value |
|---|---|---|
| 1 | Threshold | Fixing pull request merged on or after **2026-05-01** |
| 2 | Source | GitHub merged pull requests carrying `linked:issue`, across the 12 Verified repos |
| 3 | Validation | Structural criteria, then a hand audit of about 30 Instances |
| 4 | Ground truth | The Instance Filter, with the rules that [ADR-0001](0001-ground-truth-file-set.md)'s 2026-08-18 amendment adds |
| 5 | Storage | One committed JSON file. Its content hash is the revision every `RESULTS.md` entry stamps |
| 6 | Split | **None.** The set is read once and nobody tunes against it |
| 7 | Estimator | Rung 4's reweighted drop, **minus** rung 2.5's drop across the same two sets |
| 8 | Comparability | **Mix Reweighting**: the Verified aggregate is a per-repo average weighted by the Fresh repo mix |
| 9 | Anchor | Rung 4 runs across the **full** Verified Set. M7 consumes the same persisted Predictions |
| 10 | Budget | **$12** Milestone Budget |

The structural criteria are four. The pull request must close the issue through GitHub's own link. Exactly one pull request may close it. The issue must open before the pull request. The issue body must clear a minimum length.

**The minimum detectable effect is published before the paid runs start.** A null that nobody bounded in advance is not a finding.

## Rationale

**Why 2026-05-01.** Rung 4 pins `deepseek/deepseek-v4-pro`. A search found **no official training cutoff for it**. Third parties place it at April 2026, which is also its release month. `openai/gpt-oss-120b` declares June 2024, and LLMLagBench puts its empirical changepoint at September 2023, earlier than declared. So any date that clears DeepSeek clears gpt-oss by two years, and one month of margin is what the threshold adds on top of an unofficial figure.

**Why the estimator subtracts a second drop.** A drop from Verified to Fresh has two causes. The model remembered Verified, or the Fresh Instances are harder. Rung 2.5 runs no model, so its drop prices difficulty alone. What remains after the subtraction is the Contamination estimate. A single rung's drop mixes the two and nothing inside it separates them.

**Why rung 2.5 rather than rung 1.** `AgentRung` warm-starts from `HybridRung`. Rung 2.5 is therefore the exact list rung 4 receives, so its drop measures difficulty *on that list*. Rung 1's drop would price a list rung 4 never saw. Rung 2.5 acts here as a Rung and as the Candidate Set at once, and the report names which role each figure uses.

**Why Mix Reweighting is not optional.** django/django runs its issue tracker on Trac. `repo:django/django is:issue closed:>=2026-05-01` returns **0**, and linked pull requests in the window return **1**. django is 231 of 500 Verified Instances. Post-cutoff activity instead concentrates in scikit-learn, pytest, astropy, matplotlib and pylint, which hold 4 to 17 dev Instances each. Rung 4's per-repo Top-1 spans 75.0% to 100%, so an unweighted comparison would move the headline by repo mix alone, by more than any effect this milestone hopes to find.

**Why the full Verified Set, and not the dev split.** Reweighting puts 91% of the weight on thin repos, and effective sample size collapses.

| design | effective n | detectable drop | detectable drop-minus-drop |
|---|---|---|---|
| dev split, reweighted | 66 | 7.5pp | 10.6pp |
| full Verified, reweighted | 141 | 5.8pp | **8.2pp** |

**A larger Fresh Set cannot buy this.** At n=1000 the detectable effect is still 9.6pp. The Verified side is the constraint: the seven thick-Fresh repos hold 104 Verified dev Instances between them and 214 across the full set. Inverse-variance weighting was checked and returns the same 3.8pp standard error, so no weighting scheme escapes it.

**Why one read of test serves two milestones.** [ADR-0004](0004-calibrated-confidence.md) requires that the test split be evaluated once. M6 runs rung 4 across it and persists per-instance Predictions. M7 builds the Calibrator on top of rung 4 rather than changing it, so M7 reads the stored artifact instead of running again. One read, two uses, and no tuning in between.

**Why the set stays whole.** A dev/test split inside the Fresh Set would halve a sample that the power calculation already shows is not the bottleneck, and it would buy protection against tuning that nobody plans to do. If M7 wants Fresh Instances, M7 declares that and pays for it.

**Why the issue text is frozen rather than refetched.** GitHub issue text can be edited or deleted after mining. A published number could then stop reproducing with nothing in the repository showing why.

## Consequences

**The anchor's dominant repo is absent from the control.** Every Fresh figure describes a different repo population than the headline Verified figure, and only Mix Reweighting connects the two. Every reweighted figure therefore carries its effective sample size, next to the number.

**A null is the likely outcome, and it is bounded.** At 8.2pp detectable, this milestone can rule out a large Contamination effect and cannot resolve a small one. ADR-0006 already commits to publishing that as a finding. The bound is what makes it one.

**The threshold rests on an unofficial cutoff.** If DeepSeek's real training data runs past April 2026, the Fresh Set is contaminated and **no measurement in this milestone detects that**. The one-month margin is the entire defense. This ADR states it as an assumption rather than a fact, so a later reader can retest the assumption instead of the conclusion.

**ADR-0004's single read of the test split moves to M6.** If a later milestone changes rung 4, the persisted Predictions go stale and that read was spent for nothing.

**The budget holds no re-run.** Rung 4 on Verified test costs about $5.2 and rung 4 on the Fresh Set about $6.3, against $12. M5 recorded that a prompt-changing fix invalidates the response cache and costs a full re-run. Sequencing carries the risk that money cannot: the mining artifact is frozen and audited before either paid run starts.

**Two index builds, about 2.5 hours each.** Rung 4 warm-starts from the embedding index. The Verified test split was never indexed, and the Fresh Set sits on post-2026 commits that share few blobs with the 2023-era index.

**The Fresh Set is not human-validated.** It inherits none of the Verified Set's quality guarantee. Structural criteria and a sampled audit are what it has instead, and the audit's agreement rate is published beside every Fresh number.

**Issue-text leakage is measured and not corrected.** 26.1% of Verified Instances name their own answer file. Rung 4 scores 91.7% on that stratum against 87.0% on the rest, a 4.7pp difference inside the interval. The rate is published for both sets, and the analysis is not stratified.

## Alternatives rejected

- **A 2024-08 threshold, clearing gpt-oss only** — opens a two-year window and roughly 6x the yield. Rung 4's model trained through the whole of it, so the headline rung would get no contamination test at all
- **Repinning rung 4 to an older-cutoff model** — allows a long window, and breaks M5's published row
- **A bug-label mining criterion** — rejected on measurement. Of five probed repos, matplotlib and pylint return **0** for their expected label string, so the taxonomy is per-repo and hand-built. Where the label exists it keeps 26% to 45% of closed issues, which puts the set near **90 Instances**, below ADR-0006's floor of 150
- **An LLM validation pass replacing the human one** — puts a model inside ground-truth construction for a set that the same model family is then scored on
- **A larger Fresh Set** — 295 to 1000 Instances moves the detectable effect 10.6pp to 9.6pp. The money and time buy almost nothing
- **The dev split alone** — free, and it can resolve only a 10.6pp effect. That is an underpowered study rather than a finding
- **An unweighted aggregate comparison** — cheapest to explain, and it measures repo mix
- **Per-repo reporting with no aggregate** — confound-free by construction. Each repo holds 4 to 36 Verified Instances, so no per-repo interval reaches significance
- **Rung 1 as the difficulty control** — model-free and index-free, and it prices a list rung 4 never saw
- **A Trac miner for django** — restores mix comparability, at the price of a second miner against a different API and a different issue-text format. Deferred, not refused
- **Storing identifiers and refetching issue text** — keeps the repository small, and lets a published number stop reproducing silently
- **Rung 3's own contamination gap at about $0.90** — gpt-oss is also clean on this set, so it would give a second independent gap at a different model scale. The $12 budget does not hold it
