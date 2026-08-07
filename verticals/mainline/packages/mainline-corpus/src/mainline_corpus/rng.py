# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Per-stream deterministic randomness and stable identity minting.

This module is the reason two runs of ``corpusgen skeleton`` produce byte-identical trees, and
it is the reason a downstream worker can compute an id without reading the skeleton output.

---------------------------------------------------------------------------------------------
DECISION D5 — one RNG stream per generator, never one global stream
---------------------------------------------------------------------------------------------
A single global ``random.Random(seed)`` shared by ten generators has a property that looks
harmless and is not: adding one draw anywhere shifts every subsequent draw everywhere.  Add a
generator, and every person, every date and every asset assignment in the corpus changes.  The
committed render cache — which is keyed by ``sha256(prompt || model_id || prompt_version)`` —
then misses wholesale, and the claim *"regeneration is a no-op unless a prompt changes"* stops
being true.

So every generator takes its own stream, seeded from its own name:

    seed(name) = int.from_bytes(sha256(b"0xMAINLINE" + name.encode()).digest()[:8], "big")

Streams are independent.  Adding ``stream("moc.justification")`` does not perturb
``stream("event.time")``.

---------------------------------------------------------------------------------------------
BANNED, and why
---------------------------------------------------------------------------------------------
* ``random.random()`` / ``random.choice()`` and friends — module-level functions share one
  process-global Mersenne Twister that anything at all can reseed.
* ``mimesis.random.global_seed`` / ``Faker.seed()`` — same defect, plus the pool contents move
  between library versions, which re-keys every ``signer_sub`` in the corpus.
* ``datetime.now()`` / ``time.time()`` / ``uuid.uuid1()`` / ``uuid.uuid4()`` — a wall clock or
  an entropy source in a reproducible artefact is a defect, not a convenience.  Every timestamp
  in this corpus is derived from ``anchors.yaml``'s fixed epoch and a named stream.
* the builtin ``hash()`` — salted per process.
* ``CREATE SEQUENCE`` / ``nextval`` / ``unique_rowid()`` on the database side — the ledger is
  gap-free by compare-and-swap, so a gap MEANS tampering.

---------------------------------------------------------------------------------------------
Why the draw helpers are hand-rolled
---------------------------------------------------------------------------------------------
``Random.choice``, ``Random.shuffle`` and ``Random.sample`` are implemented on top of the
private ``_randbelow``, whose implementation CPython is free to change; ``Random.random()`` and
``Random.getrandbits()`` are the documented, stable primitives.  Every helper here is built on
``random()`` alone, so the corpus is reproducible across CPython versions and not merely across
runs of one interpreter.  ``weighted`` uses an explicit cumulative sum for the same reason.

The cost is a handful of obvious functions.  The benefit is that the reproducibility claim
survives a Python upgrade, which is a claim the judge-facing ``MANIFEST.sha256`` depends on.
"""

from __future__ import annotations

import hashlib
import math
import random
import uuid
from collections.abc import Iterable, Sequence
from typing import Final, TypeVar

__all__ = [
    "CORPUS_NS",
    "MASTER_SEED",
    "Stream",
    "exponential_interval",
    "gauss",
    "index_below",
    "pick",
    "poisson_thin_accept",
    "sample_without_replacement",
    "seed_for",
    "shuffled",
    "sid",
    "stream",
    "sub_stream",
    "unit",
    "weighted",
    "weighted_index",
]

T = TypeVar("T")

#: The master seed.  Written as bytes, not as an int, so it appears verbatim in the lock file
#: and in ``corpus.lock.json``'s ``"seed": "0xMAINLINE"`` field.
MASTER_SEED: Final[bytes] = b"0xMAINLINE"

#: UUID namespace for every id in the corpus.  It is itself derived from the master seed by
#: uuid5 under the DNS namespace, so it is reproducible from first principles and is not a
#: magic constant somebody typed.
CORPUS_NS: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_DNS, "mainline.corpus.0xMAINLINE")


def seed_for(name: str) -> int:
    """Return the 64-bit seed of the named stream.

    ``int.from_bytes(sha256(b"0xMAINLINE" + name.encode()).digest()[:8], "big")``.
    """
    return int.from_bytes(hashlib.sha256(MASTER_SEED + name.encode("utf-8")).digest()[:8], "big")


class Stream(random.Random):
    """A named ``random.Random``.

    Carrying the name on the object is what lets :func:`sid` take a stream directly and still
    produce a stable id — the identity of a stream is its *name*, never its internal state, so
    ``sid`` never advances the generator and ids do not depend on how many draws preceded them.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(seed_for(name))

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Stream({self.name!r})"


def stream(name: str) -> Stream:
    """Return a fresh :class:`Stream` seeded by ``name``.

    Fresh, deliberately: calling ``stream("event.time")`` twice gives two generators at the same
    starting state.  A generator therefore cannot be made to depend on whether another generator
    ran first, which is the property that makes the stages independently re-runnable.
    """
    return Stream(name)


def sub_stream(parent: Stream | str, suffix: str) -> Stream:
    """Return the stream named ``"<parent>/<suffix>"``.

    Used when a generator needs per-entity independence — one stream per site, per document, per
    event — so that regenerating one entity cannot perturb its siblings.
    """
    base = parent.name if isinstance(parent, Stream) else parent
    return Stream(f"{base}/{suffix}")


def sid(stream: Stream | str, key: str) -> uuid.UUID:
    """Mint the stable id ``uuid5(CORPUS_NS, f"{stream}:{key}")``.

    This is a *pure function of the natural key*.  It consumes no randomness, so ids do not
    depend on draw order, and any worker in the fleet can recompute an id from the natural key
    without reading a byte of skeleton output::

        sid("event", "INC-2013-044")     # the 2013 seal fire
        sid("site", "MRD")               # Marrindal
        sid("doc", "MRD/PRO-MEC-014")    # the spine's origin document

    That is the entire cross-worker identity interface.  There is no registry to keep in sync,
    and nothing to coordinate on.
    """
    return uuid.uuid5(CORPUS_NS, f"{stream}:{key}")


# ── draw helpers, all built on Random.random() only ──────────────────────────────────────────


def unit(rnd: random.Random) -> float:
    """A float in ``[0.0, 1.0)``.  The single primitive every other helper is built on."""
    return rnd.random()


def index_below(rnd: random.Random, n: int) -> int:
    """A uniform index in ``range(n)``.

    ``int(random() * n)`` rather than ``randrange``: ``random()`` is documented and stable,
    ``randrange`` routes through the private ``_randbelow``.  ``random()`` returns strictly less
    than 1.0, so the product is strictly less than ``n`` and the clamp below is defensive only.
    """
    if n <= 0:
        raise ValueError("index_below requires n >= 1")
    value = int(rnd.random() * n)
    return value if value < n else n - 1


def pick(rnd: random.Random, items: Sequence[T]) -> T:
    """Choose one element uniformly."""
    if len(items) == 0:
        raise ValueError("pick from an empty sequence")
    return items[index_below(rnd, len(items))]


def weighted_index(rnd: random.Random, weights: Sequence[float]) -> int:
    """Choose an index with probability proportional to ``weights``.

    Explicit cumulative sum, not ``random.choices``: ``choices`` is free to change its internal
    strategy, and this one draw per call is the shape the corpus needs anyway.
    """
    total = 0.0
    for weight in weights:
        if weight < 0.0:
            raise ValueError("negative weight")
        total += weight
    if total <= 0.0:
        raise ValueError("weights must sum to a positive number")
    target = rnd.random() * total
    running = 0.0
    for position, weight in enumerate(weights):
        running += weight
        if target < running:
            return position
    return len(weights) - 1


def weighted(rnd: random.Random, items: Sequence[T], weights: Sequence[float]) -> T:
    """Choose one element with probability proportional to ``weights``."""
    if len(items) != len(weights):
        raise ValueError("items and weights differ in length")
    return items[weighted_index(rnd, weights)]


def shuffled(rnd: random.Random, items: Iterable[T]) -> list[T]:
    """Return a shuffled copy.

    Fisher-Yates on ``random()`` rather than ``Random.shuffle``, for the stability reason in the
    module docstring.  The input is copied; the caller's sequence is never mutated.
    """
    out = list(items)
    for position in range(len(out) - 1, 0, -1):
        swap = index_below(rnd, position + 1)
        out[position], out[swap] = out[swap], out[position]
    return out


def sample_without_replacement(rnd: random.Random, items: Sequence[T], count: int) -> list[T]:
    """Return ``count`` distinct elements, order-stable given the stream state."""
    if count < 0:
        raise ValueError("count must be >= 0")
    if count > len(items):
        raise ValueError(f"cannot sample {count} from {len(items)} items")
    return shuffled(rnd, items)[:count]


def gauss(rnd: random.Random, mu: float, sigma: float) -> float:
    """A normal deviate by the Box-Muller transform.

    ``Random.gauss`` keeps state between calls (it caches the second deviate on the instance),
    which makes a single draw depend on whether an odd or even number of draws preceded it.
    Box-Muller here is stateless: two ``random()`` calls in, one deviate out, every time.
    """
    u1 = rnd.random()
    while u1 <= 0.0:
        u1 = rnd.random()
    u2 = rnd.random()
    return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def poisson_thin_accept(rnd: random.Random, intensity: float, bound: float) -> bool:
    """Ogata thinning acceptance test for a non-homogeneous Poisson process.

    Candidate points are drawn from a homogeneous process at rate ``bound``; a candidate at time
    *t* is kept with probability ``intensity(t) / bound``.  The result is an exact sample from
    the inhomogeneous process provided ``bound >= intensity`` everywhere, which the caller is
    responsible for and which this function checks.
    """
    if bound <= 0.0:
        raise ValueError("thinning bound must be positive")
    if intensity < 0.0:
        raise ValueError("intensity must be non-negative")
    if intensity > bound:
        raise ValueError(
            f"thinning bound {bound!r} is below the intensity {intensity!r}; the sample would be "
            "silently wrong rather than merely slow"
        )
    return rnd.random() * bound < intensity


def exponential_interval(rnd: random.Random, rate: float) -> float:
    """An exponential inter-arrival time at ``rate`` per unit.

    ``-log(1 - u) / rate`` computed explicitly; ``Random.expovariate``'s formula has changed
    once already in CPython's history.
    """
    if rate <= 0.0:
        raise ValueError("rate must be positive")
    u = rnd.random()
    while u >= 1.0:  # pragma: no cover - random() is < 1.0 by contract
        u = rnd.random()
    return -math.log(1.0 - u) / rate
