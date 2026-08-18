# M6 — decisions settled in grilling, 2026-08-18

Nine questions, each grounded in a measurement taken during the session. Every
number here traces to a probe named beside it. Nothing here is an issue yet.

## 1. The threshold is 2026-05-01

Rung 4 pins `deepseek/deepseek-v4-pro`. A web search found **no official training
cutoff**. Third parties place it at April 2026, which is also the release month.
`openai/gpt-oss-120b` declares June 2024, and LLMLagBench puts its empirical
changepoint at September 2023, earlier than declared.

The threshold clears the later cutoff with one month of margin. **The cutoff is
unofficial, so the margin is the whole defense**, and the ADR records it as an
assumption.

Rejected: a 2024-08 threshold clearing gpt-oss only. It opens a two-year window and
6x the yield, and rung 4's model trained through the whole of it, so the headline
rung would get no contamination test at all.

Rejected: repinning rung 4 to an older model. It breaks M5's published row.

## 2. The Fresh Set lands near 295 Instances

Measured with `gh api search/issues`, merged pull requests carrying `linked:issue`,
closed on or after 2026-05-01, across the 12 Verified repos: **398 candidates**.

A 56-PR sample ran through `filter_ground_truth_files`: **75% kept**, dropping
`no_source_files` 12 and `too_many_source_files` 2. So 398 x 0.75 is about **295**.

Test-stripping fired on **68%** of raw file lists. That is the M2 debt, and it is
load-bearing on real input for the first time.

## 3. django cannot enter the set

`repo:django/django is:issue closed:>=2026-05-01` returns **0**. django runs Trac.
Linked pull requests in the window: **1**, against django's 231 Verified Instances
and 113 dev Instances.

Rejected for this milestone: a Trac miner. It restores mix comparability and costs a
second miner against a different API and a different issue-text format.

## 4. The Instance Filter gains two rules

The 42 kept sample sets contained `AUTHORS` three times, `.mailmap` once, and
`sklearn/utils/_testing.py` twice. A bogus Ground-Truth File cannot be retrieved, so
it deflates Recall@3 and Recall@5 and leaves Top-1 alone.

Two rules: drop a basename with no extension, and drop test infrastructure such as
`_testing.py` and `conftest.py`.

**Both are measured no-ops on the Verified Set**: 0 of 490 Instances hold an
extensionless or test-infrastructure Ground-Truth File. No published number moves.
Recorded as an ADR-0001 amendment.

Rejected: a per-repo source-root allow-list. It also removes `build_tools/` and
codegen scripts, and it reverses ADR-0001's deny-list decision, which exists so that
`.pyx`, `.c` and `.js` fixes survive.

## 5. Structural rules plus a hand audit replace human validation

The pull request must close the issue through GitHub's own link. Exactly one pull
request may close it. The issue must open before the pull request. The issue body
must clear a minimum length. Then about 30 Instances get a hand audit, and the
agreement rate is published.

Rejected on measurement: a bug-label criterion. Of five probed repos, matplotlib and
pylint return **0** for their expected label string, so the taxonomy is per-repo.
Where the label exists it keeps 26% to 45% of closed issues, which puts the set near
**90 Instances**, below ADR-0006's floor of 150.

Rejected: an LLM validation pass. It puts a model inside ground-truth construction
for a set that the same model family is scored on.

## 6. Mix Reweighting, and what it costs

The two sets have opposite shapes. Weighting the Verified aggregate by the Fresh
repo mix puts **91% of the weight on repos holding 17 or fewer Verified dev
Instances**.

| design | effective n | detectable drop | detectable drop-minus-drop |
|---|---|---|---|
| dev split, reweighted | 66 | 7.5pp | **10.6pp** |
| full Verified, reweighted | 141 | 5.8pp | **8.2pp** |

**A larger Fresh Set does not help.** At n=1000 the detectable effect is still 9.6pp.
The Verified side is the constraint: the seven thick-Fresh repos hold 104 Verified dev
Instances between them, and 214 across the full set. Inverse-variance weighting was
checked and gives the same 3.8pp standard error, so no weighting scheme escapes it.

Rejected: an unweighted aggregate comparison. Rung 4's per-repo Top-1 spans 75.0% to
100%, so repo mix alone would move the headline by more than any expected effect.

Rejected: per-repo reporting with no aggregate. Every per-repo interval is too wide to
reach significance on its own.

## 7. Rung 4 runs on the Verified test split, once

That is what buys the move from 10.6pp to 8.2pp. **M7's coverage curve consumes the
same persisted Predictions**, so ADR-0004's single read of test stays single. Nothing
is tuned against it in between, because M7 builds the Calibrator on top of rung 4
rather than changing it.

## 8. The difficulty control is rung 2.5, not rung 1

Rung 4 warm-starts from `HybridRung`, checked in `rungs/agent.py`. Subtracting
hybrid's drop measures retrieval difficulty on the identical list, so the remainder is
what the model contributes. Rung 1's drop would price a list rung 4 never saw.

Hybrid is free, and the embedding index gets built for rung 4 anyway. The ADR must
state that hybrid acts as a Rung and as the Candidate Set here, so the two roles do
not blur.

## 9. Issue-text leakage is measured and not acted on

**26.1% of Verified Instances name their own answer file** in the issue text: 20.8%
a full path, 5.3% a basename only.

Split against the stored rung-4 dev predictions:

| stratum | n | rung-4 Top-1 |
|---|---|---|
| names its file | 60 | 91.7% |
| does not | 184 | 87.0% |

The stratum is worth **4.7pp**, inside the interval. A 15pp difference in naming rate
between the sets biases the aggregate by under 1pp, against 8.2pp detectable. Publish
the rate on both sets. Do not stratify the analysis.

## 10. The Fresh Set is frozen, hashed, and unsplit

A committed JSON file holds the mined Instances with their issue text. Its content
hash is the revision that every `RESULTS.md` entry stamps. `evaluate` currently
stamps `DATASET_ID` from `verified.py`, so this needs plumbing.

No dev/test split. The set is a control that gets read once, and nobody tunes against
it. If M7 wants it, M7 declares that and pays for it.

Rejected: storing identifiers and refetching text. GitHub issue text can be edited or
deleted, and a published number could stop reproducing with nothing in the repository
showing why.

## 11. The budget is $12, with no room for a re-run

Rung 4 on Verified test costs about $5.2, and rung 4 on the Fresh Set about $6.3.
Two index builds cost about 2.5 hours each and no money.

Rejected: $16 including rung 3's own contamination gap at about $0.90.

**Sequencing carries the risk that money cannot.** Freeze and audit the mining
artifact before either paid run starts. A `--limit` smoke test on the Fresh Set costs
about $0.21 of the $0.50 margin.
