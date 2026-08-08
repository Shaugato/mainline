# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""DELTALATTICE's version, and a fingerprint over the tables that decide.

``LATTICE_VERSION`` is what a stored verdict records so that "which lattice said
this was a weakening" is answerable years later.  Bumping it is a decision
somebody signs, never a config flag and never an environment variable — the same
discipline :mod:`mainline_domain.cat.version` and :mod:`mainline_domain.canon.version`
apply to the identity functions.

:func:`rule_catalogue_fingerprint` exists for a narrower and sharper reason.  The
lattice's answer is a function of four hand-authored tables — the deontic ladder,
the comparator transition table, the bound inversions and the coverage ranks —
and every one of them is *editable*.  Move ``('<=', '<')`` out of
:data:`~mainline_domain.lattice.rules.WEAKENING_COMPARATOR_MOVES` after a verdict
has been disputed and the dispute evaporates, with no diff visible in any row the
gate reads.  That is the same retro-tuning attack DIRECTRIX refuses for
``safe_direction`` and M3 refuses for τ, one layer up, and it deserves the same
answer: the tables have a digest, the digest is stamped on the decision, and a
verdict whose fingerprint does not match today's tables is visibly a verdict from
a different lattice.

The fingerprint covers the **decision tables only** — not the note strings, not
the docstrings, not the module bytes.  Rewording a refusal message must not
invalidate a stored fingerprint, because the wording is not what decided
anything; and conversely a table edit disguised as a comment change cannot hide,
because the table is what is hashed.

Version log
-----------
``lat1`` — the nine rules of ``research/05-architecture/clause-identity.md`` §6.2
with a join over :data:`~mainline_domain.lattice.order.CHAIN`, a minimal
unsatisfiable subset and a minimal correction set per I14, and two deliberately
non-dual cells: the deontic polarity inversion (R1) and the bound polarity
inversion (R3).
"""

from __future__ import annotations

import hashlib
from typing import Final

__all__ = [
    "LATTICE_FINGERPRINT_DOMAIN",
    "LATTICE_VERSION",
    "rule_catalogue_fingerprint",
]

LATTICE_VERSION: Final[str] = "lat1"
"""Recorded on every :class:`~mainline_domain.lattice.decide.LatticeDecision`."""

LATTICE_FINGERPRINT_DOMAIN: Final[bytes] = b"mainline/lattice/v1"
"""Domain-separation prefix, so a lattice fingerprint can never be mistaken for a
canon digest, a CAT preimage digest or a lexicon fingerprint in an exhibit."""

_SEPARATOR: Final[bytes] = b"\x1f"


def _line(*parts: str) -> bytes:
    return _SEPARATOR.join(part.encode("utf-8") for part in parts) + b"\x1e"


def rule_catalogue_fingerprint() -> bytes:
    """A 32-byte digest over the four tables that decide a verdict.

    Deterministic across interpreter versions: every table is serialised in
    **sorted** order with explicit separators, so nothing depends on dict
    insertion order, on ``hash()`` (which is salted per process) or on ``repr``.
    """
    # Imported here rather than at module scope: `rules` imports the registry,
    # the quantity algebra and the CAT lexicons, and `version` must stay cheap
    # enough for a migration runner or an offline verifier to import.
    from .rules import (
        BOUND_POLARITY_INVERSIONS,
        COVERAGE_RANK,
        DEONTIC_POLARITY,
        DEONTIC_RUNG,
        WEAKENING_COMPARATOR_MOVES,
    )

    digest = hashlib.sha256()
    digest.update(LATTICE_FINGERPRINT_DOMAIN)
    digest.update(_SEPARATOR)
    digest.update(LATTICE_VERSION.encode("utf-8"))
    digest.update(b"\x1e")

    digest.update(b"R1_DEONTIC\x1e")
    for label in sorted(DEONTIC_RUNG):
        digest.update(_line(label, str(DEONTIC_RUNG[label]), DEONTIC_POLARITY[label]))

    digest.update(b"R3_COMPARATOR\x1e")
    for before, after in sorted(WEAKENING_COMPARATOR_MOVES):
        digest.update(_line(before, after, "weaken"))
    for before, after in sorted(BOUND_POLARITY_INVERSIONS):
        digest.update(_line(before, after, "inversion"))

    digest.update(b"R5_QUANTIFIER\x1e")
    for quantifier in sorted(COVERAGE_RANK):
        digest.update(_line(quantifier, str(COVERAGE_RANK[quantifier])))

    return digest.digest()
