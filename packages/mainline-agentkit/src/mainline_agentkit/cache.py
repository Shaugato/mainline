# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Explicit prompt caching: one breakpoint, a warmed prefix, and an asserted read.

Decision A9. **Automatic prompt caching does not exist on Bedrock.** Every profile
places exactly one ``cache_control: {"type": "ephemeral"}`` breakpoint on the last
system block, over a byte-frozen prefix, and the cache read is *asserted* rather than
hoped for — an un-asserted cache is usually a broken cache, and a broken cache is
invisible until the bill arrives.

Two failure modes this module makes loud:

* **The prefix is below the generation's cacheable minimum.** The breakpoint is
  accepted and does nothing. Opus 5's minimum is 512 tokens, which is precisely why
  decision A4 refuses Haiku triage: at 4096 the shared rubric prefix would silently
  cost full price on every call. :class:`CachePrefixTooSmall` is raised at build time.
* **A cold fan-out.** A cache entry is readable only once the first response *begins
  streaming*, so N parallel calls sharing an unwarmed prefix all pay full price and
  all look successful. :class:`WarmRegistry` makes that a refusal:
  ``mainline_agentkit.call.warm_then_fanout`` marks the prefix at the first streamed
  token and every fan-out call checks the mark.

``warm_then_fanout`` itself lives in :mod:`mainline_agentkit.call`, because it drives
the full call path; this module owns the primitives it drives.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ._canon import canonical_json_bytes, sha256_hex
from .errors import CachePrefixTooSmall, ColdFanout

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "CACHE_CONTROL_EPHEMERAL",
    "DEFAULT_MIN_CACHEABLE_TOKENS",
    "MIN_CACHEABLE_TOKENS_BY_GENERATION",
    "CacheFacts",
    "WarmRegistry",
    "cache_facts_from_usage",
    "estimate_tokens",
    "min_cacheable_tokens",
    "place_cache_breakpoint",
    "prefix_digest",
]

#: The only cache-control value this package emits.
CACHE_CONTROL_EPHEMERAL: Mapping[str, str] = {"type": "ephemeral"}

#: Minimum cacheable prefix length, per model generation, from decision A4.
#:
#: Only the two figures the domain plan states as measured facts are here. A
#: generation that is not in this table gets :data:`DEFAULT_MIN_CACHEABLE_TOKENS`,
#: which is the *most conservative* published minimum — guessing low would produce a
#: cache that silently never reads.
MIN_CACHEABLE_TOKENS_BY_GENERATION: Mapping[str, int] = {
    "claude-opus-5": 512,
    "claude-haiku-4-5": 4096,
}

#: Used for any generation absent from the table above. Deliberately the largest known
#: minimum: an over-strict floor produces a loud refusal, an under-strict one produces
#: a silent full-price call.
DEFAULT_MIN_CACHEABLE_TOKENS = 4096

#: Characters per token. A cheap, deliberately pessimistic estimate — see
#: :func:`estimate_tokens`.
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True, slots=True)
class CacheFacts:
    """What the cache actually did on one call, as reported by the model's usage block.

    Attributes:
        prefix_digest: ``sha256`` of the frozen system prefix the breakpoint covers.
        creation_tokens: ``cache_creation_input_tokens`` — the warming write.
        read_tokens: ``cache_read_input_tokens`` — the thing decision A9 asserts is
            greater than zero on call #2.
        warmed: whether this call is the one that warmed the prefix.
    """

    prefix_digest: str
    creation_tokens: int
    read_tokens: int
    warmed: bool

    @property
    def read_hit(self) -> bool:
        """True when this call read from the cache rather than paying for the prefix."""
        return self.read_tokens > 0


class WarmRegistry:
    """Process-local record of which frozen prefixes have been warmed.

    Not a cache and not a source of truth about the *server's* cache — it is a record
    of whether **this process** has observed a first streamed token for a prefix. That
    is exactly the precondition decision A9 states, and it is the only one a client can
    check without lying about server state.
    """

    def __init__(self) -> None:
        """Start with nothing warmed."""
        self._lock = threading.Lock()
        self._warm: set[str] = set()

    def mark(self, digest: str) -> None:
        """Record that a first token has been observed for ``digest``."""
        with self._lock:
            self._warm.add(digest)

    def is_warm(self, digest: str) -> bool:
        """Whether ``digest`` has been warmed in this process."""
        with self._lock:
            return digest in self._warm

    def require_warm(self, digest: str) -> None:
        """Raise :class:`ColdFanout` unless ``digest`` has been warmed."""
        if not self.is_warm(digest):
            raise ColdFanout(digest)

    def clear(self) -> None:
        """Forget every warm mark. Used by tests to reconstruct the cold case."""
        with self._lock:
            self._warm.clear()


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text``.

    Four characters per token, rounded up. This is an estimate and it is used for
    exactly one purpose: refusing a system prefix that is obviously below the
    generation's cacheable minimum. That is a **cost** control, not a safety control,
    which is why an estimate is the right instrument — no gate reads this number, and
    nothing in the ledger is derived from it.
    """
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def min_cacheable_tokens(model_key: str) -> int:
    """Return the cacheable-prefix minimum for a model generation."""
    return MIN_CACHEABLE_TOKENS_BY_GENERATION.get(model_key, DEFAULT_MIN_CACHEABLE_TOKENS)


def prefix_digest(system_blocks: Sequence[Mapping[str, Any]]) -> str:
    """``sha256`` over the canonical form of the frozen system prefix.

    This is what a cassette records and what :class:`WarmRegistry` keys on. It covers
    the blocks *including* their cache-control markers, so moving the breakpoint is a
    different prefix and a different cassette — which is the point: decision A13 says a
    prompt edit is a commit, and a silent prompt edit that still replayed old cassettes
    would defeat it.
    """
    return sha256_hex(canonical_json_bytes([dict(block) for block in system_blocks]))


def place_cache_breakpoint(
    texts: Sequence[str],
    *,
    profile_id: str,
    model_key: str,
    allow_uncacheable_prefix: bool = False,
) -> list[dict[str, Any]]:
    """Build the ``system`` array with exactly one breakpoint, on the last block.

    Args:
        texts: the frozen system blocks, in order. Must be non-empty.
        profile_id: for the refusal message.
        model_key: the model generation, used to look up the cacheable minimum.
        allow_uncacheable_prefix: permit a prefix below the minimum. Set only by
            profiles whose prefix is deliberately short and whose cost is negligible;
            the default is a refusal because a breakpoint that does nothing is worse
            than no breakpoint at all.

    Raises:
        ValueError: if ``texts`` is empty.
        CachePrefixTooSmall: if the estimated prefix is below the generation minimum
            and ``allow_uncacheable_prefix`` is false.
    """
    if not texts:
        raise ValueError(f"profile {profile_id!r} has no system blocks to cache")
    estimated = estimate_tokens("".join(texts))
    minimum = min_cacheable_tokens(model_key)
    if estimated < minimum and not allow_uncacheable_prefix:
        raise CachePrefixTooSmall(profile_id, estimated, minimum)
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text} for text in texts]
    blocks[-1]["cache_control"] = dict(CACHE_CONTROL_EPHEMERAL)
    return blocks


def cache_facts_from_usage(
    usage: Mapping[str, Any],
    *,
    digest: str,
    warmed: bool,
) -> CacheFacts:
    """Read the cache counters out of a response usage block.

    Missing counters are read as zero rather than as an error: Bedrock omits them
    entirely when caching is not in play, and a missing counter is honestly a zero.
    """
    return CacheFacts(
        prefix_digest=digest,
        creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        warmed=warmed,
    )
