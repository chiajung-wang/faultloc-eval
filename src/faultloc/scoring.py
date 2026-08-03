"""Turn Predictions into the metrics the project publishes.

Pure: no I/O, no network, no model calls. Like the Instance Filter, a silent bug
here would invalidate every number in the results log while everything stayed
green, so it is built with the same density of tests.

Definitions, fixed by locked decision #3:

- **Top-1** -- the rank-1 path is in the Ground-Truth File Set. The workflow
  number: what a triage tool would actually show someone.
- **Recall@k** -- the share of ground-truth files appearing in the top k,
  averaged across instances. Diagnoses whether a miss was retrieval (the file
  was never a candidate) or ranking (it was, and lost).
- Cost and latency travel beside every accuracy figure, always.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from faultloc.dataset.models import Instance
from faultloc.rungs import Prediction

#: Repos with fewer instances than this are reported inside an `other` bucket.
#: `pallets/flask` has one instance in the whole benchmark and `mwaskom/seaborn`
#: two -- a per-repo row for them would read as a 0% or 100% result and invite
#: exactly the over-reading the breakdown exists to prevent.
MIN_REPO_INSTANCES = 3
OTHER_BUCKET = "other"

#: 95% two-sided.
Z_95 = 1.959963984540054


def normalize_path(path: str) -> str:
    """Compare paths without being fooled by cosmetic differences.

    Handles the `./` prefix, a leading slash, Windows separators, and repeated
    slashes -- all of which are the same file written differently.

    Deliberately does **not** lowercase. Paths are case-sensitive on the
    platforms these repositories are built on, and folding case would turn a
    genuine miss into a false hit, which is the one error a scorer must never
    make.
    """
    cleaned = path.replace("\\", "/")
    while "//" in cleaned:
        cleaned = cleaned.replace("//", "/")
    cleaned = cleaned.lstrip("/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def wilson_interval(successes: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Confidence interval for a proportion, by the Wilson score method.

    The textbook normal approximation is unusable here: it produces bounds
    outside [0, 1] and collapses to zero width at 0% or 100%, which is exactly
    where the small per-repo rows sit. Wilson stays inside [0, 1] and keeps a
    sensible width at the extremes and at small n.
    """
    if total == 0:
        return (0.0, 0.0)

    proportion = successes / total
    denominator = 1 + z**2 / total
    centre = proportion + z**2 / (2 * total)
    spread = z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2))
    return (
        max(0.0, (centre - spread) / denominator),
        min(1.0, (centre + spread) / denominator),
    )


@dataclass(frozen=True)
class InstanceScore:
    """One prediction scored against one instance."""

    instance_id: str
    repo: str
    hit_1: bool
    recall_3: float
    recall_5: float
    latency_s: float
    cost_usd: float
    stop_condition: str


@dataclass(frozen=True)
class Aggregate:
    """Metrics over a set of instances, with cost and latency alongside."""

    n: int
    top_1: float
    top_1_ci: tuple[float, float]
    recall_3: float
    recall_5: float
    latency_s_total: float
    latency_s_median: float
    cost_usd_total: float

    @property
    def cost_usd_per_instance(self) -> float:
        return self.cost_usd_total / self.n if self.n else 0.0


@dataclass(frozen=True)
class ScoreReport:
    """What a run produces. Overall figures plus the per-repo breakdown.

    ADR-0006 requires the breakdown: Django is 46% of the benchmark, so an
    aggregate number is largely a Django number and a change that helps one
    large convention-heavy codebase moves it on its own.
    """

    rung: str
    split: str
    overall: Aggregate
    by_repo: dict[str, Aggregate]
    stop_conditions: dict[str, int] = field(default_factory=dict)


def recall_at_k(prediction: Prediction, instance: Instance, k: int) -> float:
    """Share of the Ground-Truth File Set appearing in the top k.

    Averaged across instances later, so a two-file instance where one file is
    found scores 0.5 rather than counting as a whole hit or a whole miss.
    """
    truth = {normalize_path(p) for p in instance.ground_truth_files}
    if not truth:
        return 0.0

    ranked = {normalize_path(p) for p in prediction.ranked_files[:k]}
    return len(truth & ranked) / len(truth)


def top_1_hit(prediction: Prediction, instance: Instance) -> bool:
    """True if the rank-1 path is in the Ground-Truth File Set."""
    if not prediction.ranked_files:
        return False
    truth = {normalize_path(p) for p in instance.ground_truth_files}
    return normalize_path(prediction.ranked_files[0]) in truth


def score_instance(prediction: Prediction, instance: Instance) -> InstanceScore:
    """Score one prediction, refusing to score a mismatched pair.

    A misaligned prediction and instance would produce a plausible-looking
    number that is simply about the wrong question, and nothing downstream could
    detect it.
    """
    if prediction.instance_id != instance.instance_id:
        raise ValueError(
            f"prediction is for {prediction.instance_id}, instance is {instance.instance_id}"
        )

    return InstanceScore(
        instance_id=instance.instance_id,
        repo=instance.repo,
        hit_1=top_1_hit(prediction, instance),
        recall_3=recall_at_k(prediction, instance, 3),
        recall_5=recall_at_k(prediction, instance, 5),
        latency_s=prediction.latency_s,
        cost_usd=prediction.cost_usd,
        stop_condition=prediction.stop_condition,
    )


def _aggregate(scores: Sequence[InstanceScore]) -> Aggregate:
    n = len(scores)
    if n == 0:
        return Aggregate(0, 0.0, (0.0, 0.0), 0.0, 0.0, 0.0, 0.0, 0.0)

    hits = sum(1 for s in scores if s.hit_1)
    latencies = sorted(s.latency_s for s in scores)

    return Aggregate(
        n=n,
        top_1=hits / n,
        top_1_ci=wilson_interval(hits, n),
        recall_3=sum(s.recall_3 for s in scores) / n,
        recall_5=sum(s.recall_5 for s in scores) / n,
        latency_s_total=sum(latencies),
        latency_s_median=latencies[n // 2],
        cost_usd_total=sum(s.cost_usd for s in scores),
    )


def score(
    predictions: Sequence[Prediction],
    instances: Sequence[Instance],
    *,
    rung: str,
    split: str,
    min_repo_instances: int = MIN_REPO_INSTANCES,
) -> ScoreReport:
    """Score a whole run.

    Pairs predictions to instances by id rather than by position, so a reordered
    or partial prediction list cannot silently score the wrong pairs.
    """
    by_id = {i.instance_id: i for i in instances}
    missing = [p.instance_id for p in predictions if p.instance_id not in by_id]
    if missing:
        raise ValueError(f"predictions reference unknown instances: {missing[:5]}")

    scores = [score_instance(p, by_id[p.instance_id]) for p in predictions]

    grouped: dict[str, list[InstanceScore]] = defaultdict(list)
    for item in scores:
        grouped[item.repo].append(item)

    by_repo: dict[str, list[InstanceScore]] = defaultdict(list)
    for repo, items in grouped.items():
        bucket = repo if len(items) >= min_repo_instances else OTHER_BUCKET
        by_repo[bucket].extend(items)

    return ScoreReport(
        rung=rung,
        split=split,
        overall=_aggregate(scores),
        by_repo={repo: _aggregate(items) for repo, items in sorted(by_repo.items())},
        stop_conditions=dict(Counter(s.stop_condition for s in scores)),
    )
