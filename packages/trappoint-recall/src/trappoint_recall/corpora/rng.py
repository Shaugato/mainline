# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A counter-based deterministic generator, because ``random`` is not a contract.

Committed fixtures have to be regenerable byte-for-byte, years from now, on a different
interpreter. :class:`random.Random` is documented as reproducible for a fixed seed *on a
given Python version* — its Mersenne Twister core is stable, but the derivation from a
seed to a bounded integer is an implementation detail, and ``random.shuffle`` and
``random.sample`` have both changed algorithm across releases before.

So this module derives every draw from ``blake2b(seed || counter)``. It is slower than
``random`` by a margin nobody will ever notice at fixture scale, and it is a contract:
same seed, same stream, forever, on any implementation with blake2b.

Rejection sampling is used for bounded integers rather than modulo, so the distribution
is exactly uniform and does not depend on the relationship between the bound and 2**64.
"""

from __future__ import annotations

import hashlib
from collections.abc import MutableSequence, Sequence
from typing import Final, TypeVar

__all__ = ["DeterministicRandom"]

T = TypeVar("T")

_BLOCK: Final = 8
_MASK: Final = (1 << 64) - 1


class DeterministicRandom:
    """A reproducible stream of draws from a string seed.

    Not cryptographically secure and not intended to be: it exists so that a fixture and
    its rebuild are the same bytes, which is a reproducibility property, not a secrecy one.
    """

    __slots__ = ("_counter", "_seed")

    def __init__(self, seed: str) -> None:
        self._seed = seed.encode("utf-8")
        self._counter = 0

    def _next_u64(self) -> int:
        digest = hashlib.blake2b(
            self._counter.to_bytes(_BLOCK, "big"), key=self._seed[:64], digest_size=_BLOCK
        ).digest()
        self._counter += 1
        return int.from_bytes(digest, "big") & _MASK

    def below(self, bound: int) -> int:
        """Uniform integer in ``[0, bound)``, by rejection sampling.

        Raises:
            ValueError: if ``bound`` is not positive.
        """
        if bound <= 0:
            raise ValueError(f"bound must be positive, got {bound}")
        limit = (1 << 64) - ((1 << 64) % bound)
        while True:
            value = self._next_u64()
            if value < limit:
                return value % bound

    def integer(self, low: int, high: int) -> int:
        """Uniform integer in ``[low, high]``, inclusive at both ends."""
        if high < low:
            raise ValueError(f"empty range [{low}, {high}]")
        return low + self.below(high - low + 1)

    def choice(self, options: Sequence[T]) -> T:
        """Uniform choice from a non-empty sequence."""
        if not options:
            raise ValueError("cannot choose from an empty sequence")
        return options[self.below(len(options))]

    def chance(self, numerator: int, denominator: int) -> bool:
        """True with probability ``numerator / denominator``.

        Expressed as a ratio rather than a float so that a fixture's composition is
        auditable as exact arithmetic — "18 of every 200 citations are unresolvable" is a
        reviewable statement, "0.09" is a rounding.
        """
        if denominator <= 0:
            raise ValueError("denominator must be positive")
        return self.below(denominator) < numerator

    def shuffled(self, items: Sequence[T]) -> list[T]:
        """Fisher-Yates, in this module's own stream. Returns a new list."""
        out: MutableSequence[T] = list(items)
        for index in range(len(out) - 1, 0, -1):
            swap = self.below(index + 1)
            out[index], out[swap] = out[swap], out[index]
        return list(out)

    def sample(self, items: Sequence[T], k: int) -> list[T]:
        """``k`` distinct items, order-stable relative to the shuffle."""
        if k > len(items):
            raise ValueError(f"cannot sample {k} from {len(items)} items")
        return self.shuffled(items)[:k]
