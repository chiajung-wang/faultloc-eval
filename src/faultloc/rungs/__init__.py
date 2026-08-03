"""The contract every rung of the ladder satisfies.

ADR-0003 makes the ladder's value the *delta* between rungs, which only means
something if the rungs are compared by the same scorer on the same instances.
So the shape is fixed here, once, before the first rung exists: a rung takes an
Instance and returns a Prediction, and the harness never learns which rung it
is holding.

Cost and latency are on the Prediction from the start even though rung 1 spends
neither. Locked decision #3 requires them beside every accuracy figure, and a
field added later is a field that has to be backfilled into every stored run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from faultloc.dataset.models import Instance


class StopCondition:
    """How a run ended. Exactly one, always logged.

    `no_candidates` is separate from an empty ranking on purpose: "I had nothing
    to search" and "I searched and found nothing worth ranking" are different
    failures, and collapsing them hides the first inside the second's score.
    """

    ANSWERED = "answered"
    LOW_CONFIDENCE = "low_confidence"
    BUDGET_EXCEEDED = "budget_exceeded"
    TIMEOUT = "timeout"
    NO_CANDIDATES = "no_candidates"


@dataclass(frozen=True)
class Prediction:
    """One rung's answer for one Instance."""

    instance_id: str
    rung: str
    ranked_files: tuple[str, ...]
    stop_condition: str
    latency_s: float
    cost_usd: float = 0.0
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.stop_condition == StopCondition.ANSWERED and not self.ranked_files:
            raise ValueError("an answered prediction must rank at least one file")
        if len(set(self.ranked_files)) != len(self.ranked_files):
            raise ValueError("ranked_files contains duplicates")

    @property
    def top_1(self) -> str | None:
        return self.ranked_files[0] if self.ranked_files else None


class Rung(Protocol):
    """A retrieval strategy. Later rungs swap in without touching the harness."""

    name: str

    def predict(self, instance: Instance) -> Prediction: ...
