# ADR-0004: Confidence comes from a calibrator, not from the model

**Status:** Accepted · 2026-07-31

## Context

The system abstains by design. It escalates low-confidence instances to a human rather than guess. That needs a confidence score, and the accuracy-vs-coverage curve needs that score to mean something.

The cheapest option is to ask the model to rate its own confidence. Language models calibrate poorly when they do this. Their scores cluster near high values whatever the true correctness.

## Decision

A **logistic regression** over cheap features produces the confidence score:

- retrieval margin (score gap between top-1 and top-2 candidates)
- the model's self-reported confidence
- number of tool calls used
- whether the predicted file appeared in retrieval top-k
- agreement across **two** samples

Fit the calibrator on the dev split only. Report it with **ECE** and a reliability diagram, beside the coverage curve.

## Rationale

Self-report and retrieval margin are each weak alone. One is overconfident. The other is blind to everything the agent did after retrieval. A calibrator combines them into an actual probability.

Two samples rather than five holds the sampling cost near 2× and still yields a stability feature. Five-sample self-consistency priced out at roughly $250 across the benchmark. It still would not produce a calibrated probability, because an agreement rate is not a probability.

This supports the claim that distinguishes the project: *when the system says 80% confident, it is right 80% of the time*. Measured, not asserted.

## Consequences

**Split discipline is mandatory.** Freeze the dev and test splits before any tuning. Fit the calibrator on dev. Evaluate the test set once. A break in this rule invalidates every calibration number, and it does so silently.

**That single read happens at M6, not M7.** [ADR-0010](0010-fresh-set-mining.md) runs rung 4 across the full Verified Set to buy statistical power for the contamination estimate, and it persists per-instance Predictions. M7 reads that artifact instead of running again. The calibrator sits on top of rung 4 and does not change it, so nothing is tuned against test in between.

- Sampling cost roughly doubles for every rung that uses the agreement feature.
- The calibrator is itself a model that can be wrong. Report its failure modes as you report any other component's.

## Alternatives rejected

- **LLM self-report alone** — free, but the coverage curve would mostly document its miscalibration
- **Retrieval margin alone** — free and deterministic, but it degrades exactly where the agent adds value
- **Self-consistency at k=5** — strong signal, expensive, still uncalibrated
- **Token logprobs** — unavailable or unreliable across providers when the agent uses tools
