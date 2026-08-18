# M6 — Fresh Set mining

## Goal

A frozen Fresh Set of post-cutoff Instances, and a **Contamination** estimate: rung 4's accuracy drop from the Verified Set to the Fresh Set, minus the drop that rung 2.5 shows across the same two sets, at cost and latency.

## What M5 changed about this milestone

**Rung 4 scores 88.1% Top-1 on a set that is contaminated by construction.** The newest Verified Instance dates to 2023-08-07. The higher the ladder climbs on that set, the larger the share of the number that memory alone could explain, and nothing inside the set separates the two.

M5 built the **Tool-Reached** flag against exactly this problem, and it is a diagnostic rather than a control. It records whether a tool surfaced a predicted path. It cannot record whether the model needed the tool.

The rung-4 numbers sharpen the question. The agent reached past the Candidate Set **twice in 244 Instances**, and it still scored **+4.1pp over the same agent with no tools, at p=0.087**. If the agent's advantage on Verified is recall rather than search, the Fresh Set is the only place that shows.

## What the grilling established

Nine decisions, each measured before it was made. The measurements sit in `grilling-decisions.md`.

**The threshold is 2026-05-01.** Rung 4 pins `deepseek/deepseek-v4-pro`. Its training cutoff is **April 2026, and no publisher states it officially**. One month of margin is the whole defense, so the ADR records the threshold as an assumption rather than a fact. `openai/gpt-oss-120b` declares June 2024 and probes place it earlier, so any date that clears DeepSeek clears gpt-oss by two years.

**398 raw candidates exist in that window, and the Instance Filter keeps 75%.** A 56-PR sample measured the keep rate, so the Fresh Set lands near **295 Instances**. ADR-0006's 150–300 target is met and it is not the binding constraint.

**django cannot enter the Fresh Set.** django/django runs its issue tracker on Trac, and GitHub issue linkage finds 1 candidate. django is 231 of 500 Verified Instances and 113 of 244 dev Instances. Post-cutoff activity instead concentrates in scikit-learn, pytest, astropy, matplotlib and pylint, which hold 4 to 17 dev Instances each.

**So every comparison uses Mix Reweighting, and it is expensive.** Weighting the Verified aggregate by the Fresh repo mix puts 91% of the weight on thin repos. Effective sample size falls from 244 to **66** on the dev split. The milestone could then resolve only a 10.6pp effect.

**Mining more does not fix that.** Growing the Fresh Set from 295 to 1000 moves the detectable effect from 10.6pp to 9.6pp. The Verified side is the constraint, and no weighting scheme escapes it: the seven thick-Fresh repos hold 104 Verified dev Instances between them.

**So rung 4 runs on the Verified test split, once.** That lifts effective n to **141** and the detectable effect to **8.2pp**. M7's coverage curve consumes the same persisted Predictions, so ADR-0004's single read of test stays single. Nothing is tuned against it in between, because M7 builds the Calibrator on top of rung 4 rather than changing it.

**The Instance Filter gains two rules.** Raw pull request file lists put `AUTHORS`, `.mailmap` and `sklearn/utils/_testing.py` into Ground-Truth File Sets. A bogus Ground-Truth File cannot be retrieved, so it deflates Recall and inflates nothing. Dropping extensionless basenames and test infrastructure changes **zero** Verified Instances, measured before the rules land.

**A bug-label criterion is rejected on measurement.** Two of five sampled repos return zero for their expected label string, so the taxonomy is per-repo and fragile. Where the label exists it keeps 26% to 45%, which puts the Fresh Set near 90 Instances, below ADR-0006's floor.

**Issue-text leakage is second-order.** 26.1% of Verified Instances name their own answer file. Rung 4 scores 91.7% on those and 87.0% on the rest, a 4.7pp difference inside the interval. A 15pp difference in naming rate between the sets would bias the aggregate by under 1pp, against a detectable effect of 8.2pp. Measure the rate on both sets and publish it. Do not stratify.

## The things this milestone must still resolve

**Nobody validates a Fresh Instance.** SWE-bench Verified paid humans to confirm each issue specifies a real, solvable problem. Structural rules replace part of that: the pull request must close the issue through GitHub's own link, exactly one pull request may close it, the issue must open before the pull request, and the issue body must clear a minimum length. A hand audit of about 30 Instances covers the rest, and its agreement rate is published.

**The Fresh Set needs an identity that a result can name.** `evaluate` stamps every entry with `DATASET_ID` and `DATASET_REVISION` from `verified.py`, so a Fresh run today would publish the wrong dataset. The frozen Instances go in a committed JSON file, and its content hash becomes the revision.

**Two index builds nobody priced.** `AgentRung` defaults to `HybridRung`, so rung 4 warm-starts from bm25 **and** the embedding index. The Verified test split was never indexed, and the Fresh Set sits on post-2026 commits that share few blobs with the 2023-era index. That is about 2.5 hours each, free in dollars.

**The budget leaves no room to be wrong.** Rung 4 on Verified test costs about $5.2 and rung 4 on the Fresh Set about $6.3, against a **$12 Milestone Budget**. A prompt-changing fix invalidates the response cache and costs a full re-run, which M5 recorded as the failure that actually happens. Sequencing carries the risk that money cannot: freeze and audit the mining artifact **before** either paid run starts.

## Done when

1. An ADR publishes the mining criteria, the cutoff source, the threshold date, the reweighting rule, and the alternatives that measurement rejected.
2. The Fresh Set is frozen, committed, content-hashed, and audited on a sample, with the agreement rate reported.
3. The Filter Rate over raw pull request file lists is published, per drop reason.
4. The Contamination estimate is published per repo and reweighted, at cost and latency, with rung 2.5's drop beside it and the effective sample size on every reweighted figure.
5. The minimum detectable effect is published **before** the paid runs, so a null is bounded rather than empty.

ADR-0006 states that no gap is also a finding. At 8.2pp detectable, a null is the most likely outcome, and it is only worth publishing because the bound is stated in advance.

## Out of scope

The Calibrator and the coverage curve (M7), the service (M8), and any new rung.

**A Trac miner for django**, which would restore mix comparability at the price of a second miner against a different API and a different issue-text format.

**Rung 3's own contamination gap**, at about $0.90. It would give a second, independent gap at a different model scale. The $12 budget does not hold it.

**Retrieval improvement.** M5 measured the reachable ceiling at 95.5% against rung 4's 88.1%, so the Candidate Set is the binding constraint and the temptation is real. It belongs to a milestone with a declared Ablation, not to one whose job is a control.

Non-Python repositories stay out, as ADR-0006 decided.
