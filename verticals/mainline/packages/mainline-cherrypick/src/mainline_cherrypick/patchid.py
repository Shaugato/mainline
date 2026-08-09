# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``patch_digest`` — the same change, recognised in a document where it sits elsewhere.

``mainline.lesson.patch_digest`` is described in §5.9 as *sha256 over the
NORMALISED delta set (git patch-id)*. The parenthesis is the specification, and it
names a real algorithm with a real purpose: ``git patch-id`` strips line numbers,
whitespace and hunk headers so that the same change applied at two different
offsets in two different trees hashes to the same value. It is what lets git say
"you already have this commit" about a commit whose SHA it has never seen.

Our normalisation strips one more thing, and it is the important one: **site-local
clause identity**. A ``clause_uuid`` is meaningful only inside one site's document
tree, so a delta set keyed on ``clause_uuid`` would give every site a different
digest for the same control change and ``lesson.by_digest`` would never hit. The
delta set is therefore keyed on ``cat_key`` — identity axis 2, the hash of the
*control the clause asserts* rather than of the sentence it asserts it in. Two
plants that wrote the same obligation in entirely different prose produce the same
element.

Three normalisation rules, each with a reason a reviewer can check:

**Sorted.** A lesson is a *set* of control changes; the order they appear in a
procedure is layout. Sorting means a site that lists its isolation steps before
its gas-testing steps produces the same digest as one that lists them the other
way.

**Deduplicated.** The same control change appearing twice in one document is a
drafting artefact, not two changes. Counting it twice would give an otherwise
identical lesson a different digest.

**RFC 8785 canonical bytes, with a domain prefix.** Never
``sha256(jsonb::string)`` — JSONB reorders keys and ``sha256`` returns hex text,
so a digest taken that way cannot be reproduced by a stranger holding the same
data. The domain prefix means a patch digest can never collide with a ledger leaf
or a commit id that happens to canonicalise to the same bytes.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final

from trappoint_jcs import canonicalise_payload

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .types import ClauseDelta

__all__ = [
    "PATCH_DIGEST_DOMAIN",
    "PATCH_DIGEST_VERSION",
    "normalise_delta_set",
    "patch_digest",
]

#: Bumped only by a change to the normalisation, never by a change to this file's
#: prose. It is part of the domain prefix, so a bump makes every previously
#: computed digest visibly different rather than silently incomparable.
PATCH_DIGEST_VERSION: Final[int] = 1

#: Domain separation. A digest with no domain is a digest that can be confused
#: with another digest over the same bytes, and this one indexes a table.
PATCH_DIGEST_DOMAIN: Final[bytes] = f"mainline.patch_digest.v{PATCH_DIGEST_VERSION}\x00".encode()


def normalise_delta_set(deltas: Iterable[ClauseDelta]) -> list[dict[str, str | None]]:
    """Sort, deduplicate and render a delta set into its canonical form.

    Returns a list of plain dicts with fixed key order — ``after``, ``before``,
    ``delta`` — which RFC 8785 will sort by key anyway; the order here is written
    out so a reader of this function and a reader of the canonical bytes see the
    same thing.

    Raises:
        ValueError: on an empty delta set. A lesson that changes nothing has
            nothing to offer a sister site, and hashing the empty set would give
            every such lesson the same digest and make ``by_digest`` useless.
    """
    rendered = {
        (element.before or "", element.after or "", element.delta.value): element.normalised()
        for element in deltas
    }
    if not rendered:
        raise ValueError(
            "a lesson's delta set is empty. A lesson that changes no control has nothing "
            "to propagate, and every empty lesson would share one patch_digest"
        )
    return [rendered[key] for key in sorted(rendered)]


def patch_digest(deltas: Iterable[ClauseDelta]) -> bytes:
    """Return the 32-byte ``patch_digest`` of a lesson's delta set.

    Stable across sites, across document layout and across prose: two plants that
    made the same control change hash to the same value even if neither has seen
    the other's document.
    """
    payload = normalise_delta_set(deltas)
    return hashlib.sha256(PATCH_DIGEST_DOMAIN + canonicalise_payload(payload)).digest()
