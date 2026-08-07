# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""CATSEAL versions: changing any constant in this module is a migration.

Two versions live here and they are deliberately independent:

``CAT_KEY_VERSION`` / ``CAT_PREIMAGE_DOMAIN``
    The *encoding*.  Bumping it re-keys every ``clause_version.cat_key`` in
    history, because the domain prefix is part of the preimage.  ``cat_key`` is
    identity axis 2 and blame attaches through it, so re-keying is a migration
    with a re-match of the affected commits behind it — never a config flag,
    never an environment variable.  This mirrors ``canon_version``'s discipline
    in :mod:`mainline_domain.canon.version`, and for the same reason: a silent
    change to an identity function makes the exact-match stage stop matching,
    and a silent stop is the failure mode this product exists to refuse.

``CAT_EXTRACTOR_VERSION``
    The *extractor*.  Bumping it changes which CAT is extracted from a given
    clause, so it changes ``cat_key`` values going forward — but it does **not**
    invalidate stored keys, because a stored key is a fact about a tuple, not
    about the code that guessed the tuple.  It is recorded on every
    :class:`~mainline_domain.contracts.CATResult` so a disputed extraction can
    be reproduced with the extractor that produced it.

Neither constant is ever read from ``os.environ``, a TOML file, a CLI flag or a
database row, and :func:`mainline_domain.cat.cat_key` takes no version
parameter.  One process, one encoding, decided at build time.

Version log
-----------
``cat1`` — initial encoding: length-prefixed typed field encoding over the
thirteen CAT fields in declaration order; ABSENT/TEXT/LIST/QUANTITY type bytes;
canonical plain-notation decimals.  Normative specification:
``verticals/mainline/spec/cat-key-v1.md``.

``CAT_EXTRACTOR_VERSION = 1`` — initial Path-A extractor: shallow closed-class
grammar over ``canon_text`` with matrix/condition/exception carving, controlled
deontic lexicon with longest-cue-wins negation handling, ANCHORLOCK-resolved
actors and objects, literal quantity parsing with unstated pressure references
preserved as ``'none'``, and the three-state opacity policy.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "CAT_EXTRACTOR_VERSION",
    "CAT_FIELD_ORDER",
    "CAT_KEY_PREFIX",
    "CAT_KEY_VERSION",
    "CAT_PREIMAGE_DOMAIN",
    "CAT_PREIMAGE_SEPARATOR",
]

CAT_KEY_VERSION: Final[str] = "cat1"
"""The encoding version tag.  Appears verbatim as the ``cat_key`` prefix."""

CAT_KEY_PREFIX: Final[str] = f"{CAT_KEY_VERSION}:"
"""``'cat1:'`` — what every ``cat_key`` starts with."""

CAT_PREIMAGE_DOMAIN: Final[bytes] = b"mainline/cat/v1"
"""Domain-separation prefix for the CAT preimage.

Carries the version, so ``cat2`` moves every preimage by construction.  It also
keeps a CAT preimage from ever colliding with a canon preimage
(``mainline/canon/v…``) or a gazetteer fingerprint preimage: the three digests
mean different things and must not be interchangeable in an exhibit.
"""

CAT_PREIMAGE_SEPARATOR: Final[bytes] = b"\x1f"
"""ASCII unit separator between the domain prefix and the first field.

Strictly redundant — the prefix has a fixed length — and kept anyway so a
preimage is visibly self-describing in a hex dump, which is the form an opposing
expert will be handed.
"""

CAT_EXTRACTOR_VERSION: Final[int] = 1
"""Recorded on every :class:`~mainline_domain.contracts.CATResult`."""

CAT_FIELD_ORDER: Final[tuple[str, ...]] = (
    "actor",
    "deontic",
    "action",
    "object_class",
    "hazard_energy",
    "parameter",
    "comparator",
    "value",
    "conditions",
    "exceptions",
    "verification",
    "frequency",
    "coverage_quantifier",
)
"""The normative field order (spec §2).  **Never sorted, never reordered.**

This tuple is the single source of truth for the encoding order and is checked
against ``dataclasses.fields(CAT)`` by a test, so a field added to the frozen
contract without a decision here fails loudly rather than encoding in whatever
order the dataclass happened to declare.
"""
