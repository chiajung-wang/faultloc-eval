# ADR-0004: Confidence comes from a calibrator, not from the model

**Status:** Accepted · 2026-07-31

## Context

The system is designed to abstain — to escalate low-confidence instances to a human rather than guess. That requires a confidence score, and the accuracy-vs-coverage curve requires that score to be meaningful.

The cheapest option is to ask the model to rate its own confidence. Language models are known to be poorly calibrated when doing so, clustering near high values regardless of correctness.

## Decision

Confidence is produced by a **logistic regression** over cheap features:

- retrieval margin (score gap between top-1 and top-2 candidates)
- the model's self-reported confidence
- number of tool calls used
- whether the predicted file appeared in retrieval top-k
- agreement across **two** samples

Fit on the dev split only. Reported with **ECE** and a reliability diagram alongside the coverage curve.

## Rationale

Self-report and retrieval margin are each weak alone — one is overconfident, the other blind to everything the agent did after retrieval. A calibrator combines them into an actual probability.

Two samples rather than five keeps sampling cost at roughly 2× while still yielding a stability feature. Five-sample self-consistency was priced at roughly $250 across the benchmark and still would not produce a calibrated probability — agreement rate is not a probability.

This enables the claim that distinguishes the project: *when the system says 80% confident, it is right 80% of the time* — measured, not asserted.

## Consequences

**Split discipline is mandatory.** Dev and test splits are fixed before any tuning. The calibrator is fit on dev. The test set is evaluated once. Violating this invalidates every calibration number, silently.

- Sampling cost roughly doubles for rungs where the agreement feature is used.
- The calibrator is itself a model that can be wrong, and its failure modes must be reported like any other component's.

## Alternatives rejected

- **LLM self-report alone** — free, but the coverage curve would mostly document its miscalibration
- **Retrieval margin alone** — free and deterministic, but degrades exactly where the agent adds value
- **Self-consistency at k=5** — strong signal, expensive, still uncalibrated
- **Token logprobs** — unavailable or unreliable across providers when tool use is involved
