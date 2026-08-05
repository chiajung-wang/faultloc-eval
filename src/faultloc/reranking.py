"""Loading a cross-encoder, pinned by revision.

Separate from `faultloc.embedding` because the two models are chosen against
different constraints. Rung 2's encoder is dominated by throughput over a
million chunks; this one scores 4,880 pairs per run and is dominated by input
length instead -- ADR-0007's 487-hour wall is a property of the corpus size,
not of running locally, and it does not transfer here.
"""

from __future__ import annotations

from collections.abc import Sequence

from faultloc.rungs.cross_encoder import RerankerSpec, Scorer

#: The bake-off field. Revisions and licences checked against the Hub API on
#: 2026-08-05; all three are permissively licensed. `max_length` is the model's
#: own limit, not a choice -- what a run does with pairs longer than it is the
#: measurement issue 06 exists to make.
CANDIDATES = {
    "bge-v2-m3": RerankerSpec(
        name="BAAI/bge-reranker-v2-m3",
        revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        max_length=8192,
    ),
    "qwen3-0.6b": RerankerSpec(
        name="Qwen/Qwen3-Reranker-0.6B",
        revision="e61197ed45024b0ed8a2d74b80b4d909f1255473",
        max_length=32768,
    ),
    "minilm-l6": RerankerSpec(
        name="cross-encoder/ms-marco-MiniLM-L6-v2",
        revision="c5ee24cb16019beea0893ab7796b1df96625c6b8",
        max_length=512,
    ),
}

#: Pinned by measurement, not by reputation. `scripts/bench_reranker.py` on 60
#: dev instances: this at 35.0% Top-1 against MiniLM's 26.7%, and it truncates
#: none of the pairs where MiniLM truncates 82%. Both lose to fusion's 43.3% --
#: the pin says which cross-encoder, not that a cross-encoder helps.
DEFAULT_RERANKER = CANDIDATES["bge-v2-m3"]


def load_reranker(spec: RerankerSpec, device: str | None = None) -> Scorer:
    """A pair scorer for the pinned model.

    Imported lazily: `sentence-transformers` pulls in torch, and rung 1 must
    stay runnable without it.
    """
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:  # pragma: no cover - exercised by the install path
        raise RuntimeError(
            "cross-encoder support is an optional extra; install it with `uv sync --extra embed`"
        ) from exc

    model = CrossEncoder(
        spec.name,
        revision=spec.revision,
        max_length=spec.max_length,
        device=device,
    )

    def score(pairs: Sequence[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        return [float(value) for value in model.predict(list(pairs), show_progress_bar=False)]

    return score
