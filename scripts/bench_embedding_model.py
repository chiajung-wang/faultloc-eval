"""Benchmark one local embedding model against the cached chunk sample.

Issue 07. Answers "which of these can we afford to run?" -- throughput, index
size, peak RAM, download size, and truncation loss. It deliberately does not
answer "which retrieves best": ranking models on a micro-benchmark would be
borrowed evidence, and this project measures Top-1 on its own instances.

One model per process, so peak RSS is that model's alone and one model's
warm caches cannot flatter the next.

Usage: uv run --group bench python scripts/bench_embedding_model.py <model> <revision>
"""

from __future__ import annotations

import argparse
import json
import random
import resource
import sys
import time
from pathlib import Path

SAMPLE = Path("data/cache/chunk_sample.json")
POPULATION = 753_421  # chunks in the dev-split index, measured at code 234b566
CORPUS_TOKENS = 106_216_710
HF_CACHE = Path.home() / ".cache" / "huggingface"

#: Stop timing after this many seconds. A long-context model on whole-file
#: chunks can be orders of magnitude slower than a 512-token one, and the
#: point is to measure that rate, not to wait for it to finish.
TIME_BUDGET_S = 180.0
ORDER_SEED = 20260804

#: Batches are built to a token budget rather than a fixed count. A fixed
#: batch of 32 whole-file chunks is ~1M tokens on a 32k-context model, which
#: exhausts memory; a fixed batch small enough to be safe there would
#: throttle the 512-token model and make the comparison meaningless. Equal
#: tokens per batch is the policy a real indexer would use anyway.
TOKEN_BUDGET = 8192
MAX_BATCH = 64


def dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def peak_rss_bytes() -> int:
    """macOS reports ru_maxrss in bytes; Linux in kilobytes."""
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw if sys.platform == "darwin" else raw * 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("revision")
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    payload = json.loads(SAMPLE.read_text())
    chunks = [c["text"] for c in payload["chunks"]]

    # Same order for every model. Sentence-transformers sorts by length
    # internally; identical input order keeps that identical too.
    random.Random(ORDER_SEED).shuffle(chunks)

    before = dir_size(HF_CACHE)

    import torch
    from sentence_transformers import SentenceTransformer

    device = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")

    load_started = time.perf_counter()
    model = SentenceTransformer(args.model, revision=args.revision, device=device)
    load_s = time.perf_counter() - load_started
    downloaded = max(0, dir_size(HF_CACHE) - before)

    max_seq = model.max_seq_length
    dim = model.get_sentence_embedding_dimension()

    # Truncation, over the whole sample. Needs no embedding -- tokenize and
    # count. This is the number that decides whether long context is worth
    # paying for, and it is the cheapest measurement here.
    tokenizer = model.tokenizer
    lengths = [
        len(tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])
        for text in chunks
    ]
    over = [n for n in lengths if n > max_seq]
    dropped = sum(n - max_seq for n in over)
    total_tokens = sum(lengths)

    batches: list[tuple[list[str], int]] = []
    current: list[str] = []
    budget = 0
    for text, length in zip(chunks, lengths, strict=True):
        cost = min(length, max_seq)
        if current and (budget + cost > TOKEN_BUDGET or len(current) >= MAX_BATCH):
            batches.append((current, budget))
            current, budget = [], 0
        current.append(text)
        budget += cost
    if current:
        batches.append((current, budget))

    # Warm-up: the first batch pays kernel compilation and lazy allocation.
    model.encode(batches[0][0], batch_size=MAX_BATCH, show_progress_bar=False)

    encoded = 0
    encoded_tokens = 0
    started = time.perf_counter()
    for batch, tokens in batches:
        model.encode(batch, batch_size=MAX_BATCH, show_progress_bar=False)
        encoded += len(batch)
        encoded_tokens += tokens
        if time.perf_counter() - started > TIME_BUDGET_S:
            break
    elapsed = time.perf_counter() - started

    rate = encoded / elapsed
    result = {
        "model": args.model,
        "revision": args.revision,
        "device": device,
        "dimensions": dim,
        "max_seq_length": max_seq,
        "load_s": round(load_s, 1),
        "download_bytes": downloaded,
        "peak_rss_bytes": peak_rss_bytes(),
        "encoded": encoded,
        "elapsed_s": round(elapsed, 1),
        "chunks_per_s": round(rate, 1),
        "tokens_per_s": round(encoded_tokens / elapsed),
        "full_index_s": round(POPULATION / rate),
        "index_bytes_fp32": POPULATION * dim * 4,
        "sample_tokens": total_tokens,
        "chunks_over_limit_pct": round(100 * len(over) / len(chunks), 2),
        "sample_tokens_dropped_pct": round(100 * dropped / total_tokens, 2),
        "corpus_tokens_dropped_est": round(CORPUS_TOKENS * dropped / total_tokens),
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
