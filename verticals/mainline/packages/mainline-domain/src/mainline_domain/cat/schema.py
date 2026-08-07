# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Control Assertion Tuple's controlled vocabularies and its validator.

The :class:`~mainline_domain.contracts.CAT` dataclass itself lives in
``contracts.py``, frozen by W1, and is re-exported here so that nothing in this
package ever redeclares it.  What this module adds is the *closed* part: which
values each slot is allowed to take, and a validator that says so out loud.

Why a validator rather than a type: ``CAT`` slots are ``str`` because a
``cat_key`` must be computable for a tuple containing a vocabulary miss — the
extractor is allowed to fall back to a normalised surface token, and that
fallback has to be hashable and comparable like any other.  So the vocabulary is
enforced where it can be *reported* (extraction, ingest) rather than where it
would prevent a tuple from existing at all.

``deontic`` is the exception: it is fully closed.  A deontic outside the six
labels is not a vocabulary gap, it is a bug in the extractor, because the label
set is what DELTALATTICE rule R1 orders and an unknown rung has no position in
that order.  :func:`validate_cat` raises on it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final, get_args

from ..contracts import CAT, CatConfidence, CATResult, Quantity, Reference

__all__ = [
    "CAT",
    "CAT_CONFIDENCES",
    "COMPARATORS",
    "COVERAGE_QUANTIFIERS",
    "DEONTIC_ABSENT",
    "DEONTIC_LABELS",
    "DEONTIC_TAXONOMY_CLASSES",
    "EMPTY_CAT",
    "REFERENCES",
    "CATResult",
    "CatConfidence",
    "Quantity",
    "Reference",
    "validate_cat",
    "weakest_confidence",
]

DEONTIC_ABSENT: Final[str] = "ABSENT"

DEONTIC_LABELS: Final[tuple[str, ...]] = (
    "MUST",
    "MUST_NOT",
    "SHOULD",
    "SHOULD_NOT",
    "MAY",
    DEONTIC_ABSENT,
)
"""The six deontic labels.  Closed, and enforced by :func:`validate_cat`.

``MUST_NOT``/``SHOULD_NOT`` are *not* extra rungs on R1's ladder — a prohibition
has the same force as the corresponding obligation, it is the polarity of the
action that differs.  Keeping them separate rather than folding them into
``MUST``/``SHOULD`` is what lets ``action`` stay positive: "shall not enter" is
``(MUST_NOT, enter)``, never ``(MUST, not_enter)``, so two clauses about entry
share a parameter and an object class and can be diffed against each other.
"""

DEONTIC_TAXONOMY_CLASSES: Final[frozenset[str]] = frozenset(
    {"OBLIGATION", "PROHIBITION", "PERMISSION", "RECOMMENDATION", "NONE"}
)
"""The legal-NLP taxonomy the labels roll up to (see ``data/lexicon/deontic.toml``)."""

COMPARATORS: Final[frozenset[str]] = frozenset({"<=", ">=", "<", ">", "=", "~", "+/-", "range", ""})
"""The comparator alphabet fixed by ``cat-key-v1.md`` §2.

``''`` means *no comparator asserted*, which is different from ``'='``.  A
clause that names a parameter with no relation ("the operating pressure is
recorded") must not be encoded as if it pinned a value.
"""

COVERAGE_QUANTIFIERS: Final[frozenset[str]] = frozenset(
    {"all", "any", "selected", "typical", "unspecified"}
)
"""What R5 orders.  ``unspecified`` is the default and is not the same as ``all``."""

CAT_CONFIDENCES: Final[tuple[str, ...]] = get_args(CatConfidence)
"""Exactly the three values ``clause_version.cat_confidence``'s ``CHECK`` permits.

Derived from the frozen ``Literal`` rather than retyped, so this constant cannot
drift away from the contract, and a test asserts it equals ``('ok','low','opaque')``
— which is what the SQL says.
"""

REFERENCES: Final[tuple[str, ...]] = get_args(Reference)

_CONFIDENCE_RANK: Final[dict[str, int]] = {"ok": 0, "low": 1, "opaque": 2}

EMPTY_CAT: Final[CAT] = CAT(
    actor="",
    deontic=DEONTIC_ABSENT,
    action="",
    object_class="",
    hazard_energy="",
    parameter="",
    comparator="",
    value=None,
    conditions=(),
    exceptions=(),
    verification=(),
    frequency=None,
    coverage_quantifier="unspecified",
)
"""The tuple an extraction starts from.  Every slot is the *weakest* legal value.

Starting from ``ABSENT``/``unspecified`` rather than from a guess is the P3
fail-closed shape applied to extraction: a slot the extractor could not fill
reads as "this clause asserts nothing here", which is the reading that makes an
edge *toward* a filled slot look like a strengthening and an edge *away* look
like a weakening — the correct direction in both cases.
"""


def weakest_confidence(*confidences: str) -> str:
    """Return the least confident of the arguments (``opaque`` > ``low`` > ``ok``).

    Confidence composes downward only.  There is no operation in this package
    that raises a confidence, because every stage that can learn something new
    about a clause can only learn that it is *harder* to read than it looked.
    """
    if not confidences:
        return "ok"
    unknown = [c for c in confidences if c not in _CONFIDENCE_RANK]
    if unknown:
        raise ValueError(
            f"not a cat_confidence value: {unknown!r}; legal values are {CAT_CONFIDENCES}"
        )
    return max(confidences, key=lambda c: _CONFIDENCE_RANK[c])


def _validate_quantity(quantity: Quantity | None, slot: str) -> None:
    if quantity is None:
        return
    if not isinstance(quantity.value, Decimal):
        raise TypeError(
            f"CAT.{slot}.value must be a Decimal, got {type(quantity.value).__name__}. "
            f"A float setpoint is a rounding error waiting to become a safe_direction flip."
        )
    if not quantity.value.is_finite():
        raise ValueError(f"CAT.{slot}.value must be finite, got {quantity.value!r}")
    if not quantity.unit:
        raise ValueError(
            f"CAT.{slot} has a value with no unit. The extractor must never guess a unit: "
            f"a bare number is confidence='low' with value=None, not an invented unit."
        )
    if not quantity.dimension:
        raise ValueError(f"CAT.{slot}.dimension must not be empty")
    if quantity.reference not in REFERENCES:
        raise ValueError(
            f"CAT.{slot}.reference is {quantity.reference!r}; legal values are {REFERENCES}"
        )


def validate_cat(cat: CAT) -> None:
    """Raise if a CAT is outside the vocabularies this spec closes.

    Called on every extraction result and intended to be called by any ingest
    path that constructs a CAT by hand.  It is not called by
    :func:`~mainline_domain.cat.cat_preimage`: the encoder must be able to hash
    *whatever* tuple it is handed, including a malformed one, so that a dispute
    about a stored ``cat_key`` can always be reproduced.
    """
    if cat.deontic not in DEONTIC_LABELS:
        raise ValueError(
            f"CAT.deontic is {cat.deontic!r}; legal labels are {DEONTIC_LABELS}. "
            f"An unknown deontic has no position in DELTALATTICE rule R1's order."
        )
    if cat.comparator not in COMPARATORS:
        raise ValueError(
            f"CAT.comparator is {cat.comparator!r}; legal values are {sorted(COMPARATORS)}"
        )
    if cat.coverage_quantifier not in COVERAGE_QUANTIFIERS:
        raise ValueError(
            f"CAT.coverage_quantifier is {cat.coverage_quantifier!r}; "
            f"legal values are {sorted(COVERAGE_QUANTIFIERS)}"
        )
    for slot_name in ("conditions", "exceptions", "verification"):
        slot = getattr(cat, slot_name)
        if not isinstance(slot, tuple):
            raise TypeError(f"CAT.{slot_name} must be a tuple, got {type(slot).__name__}")
        if any(not isinstance(element, str) for element in slot):
            raise TypeError(f"CAT.{slot_name} must contain only str")
        if any(element == "" for element in slot):
            raise ValueError(
                f"CAT.{slot_name} contains an empty element. Normalisation drops empties: an "
                f"unnamed exception is not the same fact as no exception, and encoding one by "
                f"accident splits the identity of every clause it happens to."
            )
    if cat.comparator == "" and cat.value is not None:
        raise ValueError(
            "CAT has a value with no comparator: a bare setpoint asserts no relation and "
            "cannot be ordered by DELTALATTICE rule R2."
        )
    _validate_quantity(cat.value, "value")
    _validate_quantity(cat.frequency, "frequency")
