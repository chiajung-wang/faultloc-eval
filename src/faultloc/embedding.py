"""The chunk embedding index: build it once, read it many times.

Rung 2 ranks AST Chunks by embedding similarity. Producing those embeddings for
a whole split is a long job -- ~1,013,340 chunks, roughly 3.7 hours at the
throughput measured in issue 07 -- so it is a command of its own rather than
something a rung does inside its prediction loop. M1 already paid for that
lesson once: a rung constructed per instance discarded its blob-keyed cache and
turned eighty seconds into half an hour.

Keyed by **blob SHA**, like `RepoStore`'s tree cache and `Bm25Rung`'s token
cache. A blob SHA is a content hash, so an entry can never go stale, is safe
across process restarts, and is shared by every instance and repository holding
that content. Across the Verified Set the same content appears about 21 times.

Vectors are stored **without** chunk text or names. `chunk_source` is
deterministic, so row `i` of a blob's array is chunk `i` of that blob, and a
rung scoring a file needs only the rows -- not what they say.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from faultloc.dataset.models import Instance
from faultloc.repos import RepoStore
from faultloc.rungs.chunks import chunk_source

DEFAULT_INDEX_ROOT = Path("data/index")

#: Texts sent to the encoder at once. Large enough that per-call overhead is
#: amortised, small enough that one batch of whole-file windows fits in memory.
BATCH_TEXTS = 256


@dataclass(frozen=True)
class ModelSpec:
    """The embedding model, pinned by identifier *and* revision.

    Both halves are load-bearing. `sentence-transformers/all-MiniLM-L6-v2`
    moved its main branch on 2026-06-01 while this model has not moved since
    2024-02-22 -- a model name is not provenance. See ADR-0007.
    """

    name: str
    revision: str
    dimensions: int
    #: bge models are trained asymmetrically: the query carries an instruction
    #: and the document carries none. Omitting it costs retrieval quality
    #: quietly, so it lives here rather than in a comment.
    query_prefix: str

    @property
    def slug(self) -> str:
        return f"{self.name.replace('/', '__')}@{self.revision[:12]}"


DEFAULT_MODEL = ModelSpec(
    name="BAAI/bge-small-en-v1.5",
    revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
    dimensions=384,
    query_prefix="Represent this sentence for searching relevant passages: ",
)

#: Takes document texts, returns one unit-normalised row per text.
Encoder = Callable[[Sequence[str]], np.ndarray]


class IndexIncompatibleError(RuntimeError):
    """An index on disk was built by a different model or revision.

    Vectors from two models are indistinguishable once written. Reading one
    with the other produces a plausible number with no valid provenance, which
    is worse than a crash.
    """


class IndexMissingError(RuntimeError):
    """A rung asked for a blob the index does not hold."""


@dataclass
class IndexReport:
    """What a build did. Printed, and the basis of rung 2's cost column."""

    blobs_embedded: int = 0
    blobs_reused: int = 0
    chunks_embedded: int = 0
    wall_clock_s: float = 0.0
    cost_usd: float = 0.0

    @property
    def blobs_total(self) -> int:
        return self.blobs_embedded + self.blobs_reused


class EmbeddingIndex:
    """Blob-keyed vectors on disk, one array per blob.

    One file per blob rather than a single packed array: presence *is* the
    resumability record, so an interrupted build needs no separate progress
    file that could disagree with what was actually written.
    """

    def __init__(
        self,
        root: Path = DEFAULT_INDEX_ROOT,
        spec: ModelSpec = DEFAULT_MODEL,
    ) -> None:
        self.spec = spec
        self.root = Path(root) / spec.slug

    @property
    def meta_path(self) -> Path:
        return self.root / "meta.json"

    def ensure_compatible(self) -> None:
        """Refuse to extend an index built by a different model.

        The slug already separates models by directory, so a mismatch here
        means the same name and revision produced different dimensions -- weights
        changed under a stable identifier, which is the failure ADR-0007 pins
        the revision to catch.
        """
        if not self.meta_path.is_file():
            self.root.mkdir(parents=True, exist_ok=True)
            self.meta_path.write_text(
                json.dumps(
                    {
                        "model": self.spec.name,
                        "revision": self.spec.revision,
                        "dimensions": self.spec.dimensions,
                    }
                )
            )
            return

        stored = json.loads(self.meta_path.read_text())
        current = {
            "model": self.spec.name,
            "revision": self.spec.revision,
            "dimensions": self.spec.dimensions,
        }
        if stored != current:
            raise IndexIncompatibleError(
                f"index at {self.root} was built by {stored}, not {current}"
            )

    def path_for(self, blob: str) -> Path:
        # Two-character fan-out: 32,667 files in one directory is legal but
        # slow to list on every filesystem this might run on.
        return self.root / blob[:2] / f"{blob}.npy"

    def has(self, blob: str) -> bool:
        return self.path_for(blob).is_file()

    def read(self, blob: str) -> np.ndarray:
        path = self.path_for(blob)
        if not path.is_file():
            raise IndexMissingError(f"no vectors for blob {blob}; run `faultloc index` first")
        return np.load(path)

    def write(self, blob: str, vectors: np.ndarray) -> None:
        """Write then rename, so an interrupted build leaves no partial entry.

        A half-written `.npy` that a later run treats as complete would silently
        corrupt every score derived from it -- and presence is what resumability
        reads, so a partial file is indistinguishable from a finished one.
        """
        path = self.path_for(blob)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".npy.tmp")
        # Through a file handle: `np.save` appends `.npy` to a *path* that
        # lacks it, so passing `tmp` directly would write `.npy.tmp.npy` and
        # the rename below would find nothing.
        with tmp.open("wb") as handle:
            np.save(handle, vectors.astype(np.float32))
        tmp.replace(path)

    def size_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.root.rglob("*.npy"))


@dataclass
class _Pending:
    """Chunks waiting to be encoded, and which blob each row belongs to."""

    texts: list[str] = field(default_factory=list)
    owners: list[tuple[str, int]] = field(default_factory=list)

    def add(self, blob: str, chunk_texts: list[str]) -> None:
        self.texts.extend(chunk_texts)
        self.owners.append((blob, len(chunk_texts)))

    def clear(self) -> None:
        self.texts.clear()
        self.owners.clear()


def build_index(
    instances: Sequence[Instance],
    *,
    store: RepoStore,
    index: EmbeddingIndex,
    encode: Encoder,
    include_bodies: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
) -> IndexReport:
    """Embed every chunk the split needs, skipping blobs already on disk.

    Cost is reported as measured rather than estimated. It is `$0.00` for a
    local model, and that zero is honest: a fabricated figure would be worse
    (ADR-0007).
    """
    index.ensure_compatible()

    report = IndexReport()
    started = time.perf_counter()
    seen: set[str] = set()
    pending = _Pending()

    def flush() -> None:
        if not pending.texts:
            return
        vectors = encode(pending.texts)
        offset = 0
        for blob, count in pending.owners:
            index.write(blob, vectors[offset : offset + count])
            offset += count
        pending.clear()

    for n, instance in enumerate(instances, 1):
        files = store.list_source_files(instance.repo, instance.base_commit)
        wanted = [f.blob for f in files if f.blob not in seen]
        if wanted:
            seen.update(wanted)
            fresh = [blob for blob in wanted if not index.has(blob)]
            report.blobs_reused += len(wanted) - len(fresh)

            if fresh:
                for blob, text in store.read_blobs(instance.repo, fresh).items():
                    chunks = chunk_source(text, include_bodies=include_bodies)
                    pending.add(blob, [c.text for c in chunks])
                    report.blobs_embedded += 1
                    report.chunks_embedded += len(chunks)
                    if len(pending.texts) >= BATCH_TEXTS:
                        flush()

        if on_progress:
            on_progress(n, len(instances))

    flush()
    report.wall_clock_s = time.perf_counter() - started
    return report


def load_encoder(spec: ModelSpec = DEFAULT_MODEL, device: str | None = None) -> Encoder:
    """A document encoder for the pinned model.

    Imported lazily: `sentence-transformers` pulls in torch, and rung 1 must
    stay runnable without it.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - exercised by the install path
        raise RuntimeError(
            "embedding support is an optional extra; install it with `uv sync --extra embed`"
        ) from exc

    model = SentenceTransformer(spec.name, revision=spec.revision, device=device)

    def encode(texts: Sequence[str]) -> np.ndarray:
        # Normalised at write time so similarity is a dot product, and so a
        # later reader cannot forget to normalise and quietly score by
        # magnitude instead of direction.
        return model.encode(
            list(texts),
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

    return encode
