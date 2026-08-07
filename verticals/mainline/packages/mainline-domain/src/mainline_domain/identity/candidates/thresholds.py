# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The cascade's bands, and the fingerprint that makes retro-tuning visible.

Every number in :data:`DEFAULT_BANDS` is transcribed from the S0-S6 table in
``research/05-architecture/clause-identity.md`` §4.  None of them was invented
here and none of them is calibrated: they are the *design's* bands, and the
corpus that would calibrate them does not exist yet.  That is stated in
``novelty/minhash-band.yaml`` under ``unverified`` and it is stated again here,
because a threshold whose provenance is a docstring is a threshold somebody
will quietly move.

**Why a fingerprint.**  Decision D11 puts the content hash of
``identity_policy-v1.toml`` on every ``identity_assignment`` row so that
retro-tuning the matcher to make a drop look reasonable becomes visible.  That
policy file is W8's artefact; this module supplies the piece W8 needs from the
cascade — a 32-byte digest over the exact band values a run used — so the two
can be folded together without this package reaching into W8's file.

The bands are **data, not policy**: nothing here decides anything.  A stage is
handed a :class:`StageBands` and reports which side of it each pair fell.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from typing import Final

__all__ = [
    "BANDS_FINGERPRINT_DOMAIN",
    "DEFAULT_BANDS",
    "StageBands",
]

BANDS_FINGERPRINT_DOMAIN: Final[bytes] = b"mainline/identity/bands/v1\n"
"""Domain separator for :meth:`StageBands.fingerprint`.

A bare hash over a tuple of floats collides with every other bare hash over a
tuple of floats in the system.  Prefixing the preimage with a versioned domain
string costs nothing and makes the digest mean one thing.
"""


@dataclass(frozen=True, slots=True)
class StageBands:
    """Auto-accept and auto-reject bands for S1-S4, plus S2's trigram floor.

    A stage never consults anything outside this object.  ``float`` throughout,
    even where the value is exactly 1.0, because the comparison the stages
    perform is a float comparison and a mixed int/float band is a rounding
    argument waiting to happen.
    """

    #: S1 — ``canon_sha256`` equality.  Exact identity, so the band is 1.0 and
    #: there is nothing below it: a digest either matches or the pair is not a
    #: candidate at all.
    exact_accept: float

    #: S2 — identity-anchor-set equality plus the trigram floor.
    anchor_accept: float
    anchor_trigram_floor: float

    #: S3 — MinHash/LSH banding, rescored in the application.
    lexical_accept: float
    lexical_reject: float

    #: S4 — anchor-gated ANN.  ``semantic_accept`` applies **only** to pairs
    #: that already passed :meth:`AnchorSet.compatible_with`; an incompatible
    #: pair is dropped before its cosine is looked at, so no band applies to it.
    semantic_accept: float
    semantic_reject: float

    def fingerprint(self) -> bytes:
        r"""Digest the band values into 32 bytes, for D11's audit trail.

        The preimage is the domain separator followed by one
        ``name=repr(value)\\n`` line per field **in declaration order**, so it
        is reproducible by hand from this file and from nothing else.
        ``repr`` of a float is round-trip exact in CPython, which is what makes
        the preimage a function of the value rather than of a formatting
        choice.
        """
        parts = [BANDS_FINGERPRINT_DOMAIN]
        for f in fields(self):
            value: float = getattr(self, f.name)
            parts.append(f"{f.name}={value!r}\n".encode())
        return hashlib.sha256(b"".join(parts)).digest()


DEFAULT_BANDS: Final[StageBands] = StageBands(
    exact_accept=1.0,
    anchor_accept=0.92,
    anchor_trigram_floor=0.55,
    lexical_accept=0.90,
    lexical_reject=0.30,
    semantic_accept=0.93,
    semantic_reject=0.70,
)
"""The bands exactly as ``clause-identity.md`` §4 states them.

======  ==============================================  ============  ============
Stage   Mechanism                                        Auto-accept   Auto-reject
======  ==============================================  ============  ============
S1      ``canon_sha256`` equality                        ≥ 1.0         —
S2      anchor-set equality + trigram ``≥ 0.55``          ≥ 0.92        —
S3      MinHash/LSH banding, rescored                     ≥ 0.90        < 0.30
S4      ANN cosine **and** anchor-compatible              ≥ 0.93        < 0.70
======  ==============================================  ============  ============

S1 and S2 carry no auto-reject band on purpose.  Falling below S2's floor is
not evidence that the pair is *unrelated* — it is evidence that anchor equality
alone was carrying the match — so the pair falls through to S3 and S4 instead
of being rejected on a stage that never looked at the text.
"""
