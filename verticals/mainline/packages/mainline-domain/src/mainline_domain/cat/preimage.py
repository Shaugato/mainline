# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The ``cat_key`` preimage: a length-prefixed, typed field encoding.

Normative specification: ``verticals/mainline/spec/cat-key-v1.md``.  Conformance
fixture: ``tests/fixtures/domain/cat/golden-vectors.json``.  This module is the
reference implementation of that spec and nothing more — it makes no judgements,
because every judgement was made in :mod:`mainline_domain.cat.normalise` before
the tuple reached here.

**Why not JSON** (decision D2).  ``cat_key`` is identity axis 2: two clauses
sharing one are the same obligation, and blame attaches through that equality.
JSON leaves three degrees of freedom that each admit two conformant encoders
disagreeing — number formatting (``50`` / ``50.0`` / ``5.0e1``), object key
order, and string escaping — and closing them means vendoring an RFC 8785
canonicaliser, whose bugs would then be our bugs in the identity axis.  RFC 8785
also mandates IEEE-754 double serialisation, and a safety setpoint is a
``Decimal``.  The encoding here has none of those freedoms: every field is
length-prefixed so concatenation is unambiguous, every field is type-tagged so
*absent* and *empty* differ, and §4's canonical decimal gives one spelling per
value.

The whole encoder is about eighty lines because it has to be re-implementable
from the spec by someone trying to prove us wrong.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import fields as dataclass_fields
from decimal import Decimal
from typing import Final

from ..contracts import CAT, Quantity
from .version import (
    CAT_FIELD_ORDER,
    CAT_KEY_PREFIX,
    CAT_PREIMAGE_DOMAIN,
    CAT_PREIMAGE_SEPARATOR,
)

__all__ = [
    "TYPE_ABSENT",
    "TYPE_LIST",
    "TYPE_QUANTITY",
    "TYPE_TEXT",
    "canonical_decimal",
    "cat_key",
    "cat_preimage",
    "encode_absent",
    "encode_field",
    "encode_list",
    "encode_quantity",
    "encode_text",
]

# --------------------------------------------------------------------------- #
# Type bytes (spec §3.1).  Four, and there will never be a fifth in `cat1`.    #
# --------------------------------------------------------------------------- #

TYPE_ABSENT: Final[int] = 0x00
TYPE_TEXT: Final[int] = 0x01
TYPE_LIST: Final[int] = 0x02
TYPE_QUANTITY: Final[int] = 0x03

_LENGTH_BYTES: Final[int] = 4
_MAX_PAYLOAD: Final[int] = (1 << (8 * _LENGTH_BYTES)) - 1

_TEXT_SLOTS: Final[frozenset[str]] = frozenset(
    {
        "actor",
        "deontic",
        "action",
        "object_class",
        "hazard_energy",
        "parameter",
        "comparator",
        "coverage_quantifier",
    }
)
_LIST_SLOTS: Final[frozenset[str]] = frozenset({"conditions", "exceptions", "verification"})
_QUANTITY_SLOTS: Final[frozenset[str]] = frozenset({"value", "frequency"})


def encode_field(type_byte: int, payload: bytes) -> bytes:
    """One field: type byte, 4-byte big-endian **byte** length, payload (spec §3)."""
    if len(payload) > _MAX_PAYLOAD:
        raise ValueError(
            f"CAT field payload of {len(payload)} bytes exceeds the {_MAX_PAYLOAD}-byte "
            f"limit of a 4-byte length prefix"
        )
    return bytes((type_byte,)) + len(payload).to_bytes(_LENGTH_BYTES, "big") + payload


def encode_absent() -> bytes:
    """``00 00000000`` — distinct from an empty TEXT field (spec §3.1)."""
    return encode_field(TYPE_ABSENT, b"")


def encode_text(value: str) -> bytes:
    """``01 <len> <utf-8>``.  The length counts **bytes**, never characters."""
    return encode_field(TYPE_TEXT, value.encode("utf-8"))


def encode_list(values: Sequence[str]) -> bytes:
    """``02 <len> <TEXT field>*`` in the order given — **the encoder never sorts**.

    Ordering is a normalisation decision (spec §7.3), made before encoding.  An
    encoder that sorted here would conceal a normaliser that did not, and the
    concealment would surface as two identical obligations with different
    ``cat_key``s, which is an identity split nobody could explain.
    """
    return encode_field(TYPE_LIST, b"".join(encode_text(element) for element in values))


def canonical_decimal(value: Decimal) -> str:
    """One spelling per value (spec §4).

    ``Decimal`` carries significance: ``Decimal('50')`` and ``Decimal('50.0')``
    are equal in value and different in representation.  Identity has to follow
    value, so trailing fractional zeros are stripped and exponent notation is
    expanded.  A non-finite decimal **raises** — there is no canonical spelling
    for a ``NaN`` setpoint, and there is no safe default for one either.
    """
    if not value.is_finite():
        raise ValueError(
            f"a CAT quantity must be a finite Decimal; got {value!r}. "
            f"There is no canonical spelling for a non-finite setpoint."
        )
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-", "-0"):
        text = "0"
    return text


def encode_quantity(quantity: Quantity | None) -> bytes:
    """``03 <len> TEXT(value) TEXT(unit) TEXT(dimension) TEXT(reference)``, or ABSENT.

    ``reference`` is the fourth sub-field and is load-bearing: ``50 psig`` and
    ``50 psia`` differ here and therefore differ in ``cat_key``.  That is the
    whole point of decision D5 — a gauge reading silently treated as absolute
    flips a ``safe_direction`` comparison, so a weakening reads as a
    strengthening on the way past the gate.
    """
    if quantity is None:
        return encode_absent()
    payload = (
        encode_text(canonical_decimal(quantity.value))
        + encode_text(quantity.unit)
        + encode_text(quantity.dimension)
        + encode_text(quantity.reference)
    )
    return encode_field(TYPE_QUANTITY, payload)


def _check_field_order() -> None:
    """Fail loudly if the frozen contract grew a field the encoding does not name.

    ``contracts.CAT`` is owned by W1 and this module may not edit it.  If a
    future change adds a slot, the encoding order for it is a *decision*, not a
    consequence of declaration order, so this raises rather than encoding
    whatever ``dataclasses.fields`` happens to return.
    """
    declared = tuple(f.name for f in dataclass_fields(CAT))
    if declared != CAT_FIELD_ORDER:
        raise RuntimeError(
            "mainline_domain.contracts.CAT no longer matches CAT_FIELD_ORDER. "
            f"contract={declared!r} encoding={CAT_FIELD_ORDER!r}. "
            "Adding a CAT field is a cat_key migration: bump CAT_PREIMAGE_DOMAIN, "
            "extend verticals/mainline/spec/cat-key-v1.md, and regenerate the golden vectors."
        )


_check_field_order()


def cat_preimage(cat: CAT) -> bytes:
    """``DOMAIN || 0x1F || F1 .. F13`` (spec §5)."""
    parts: list[bytes] = [CAT_PREIMAGE_DOMAIN, CAT_PREIMAGE_SEPARATOR]
    for name in CAT_FIELD_ORDER:
        slot = getattr(cat, name)
        if name in _TEXT_SLOTS:
            if not isinstance(slot, str):
                raise TypeError(f"CAT.{name} must be a str, got {type(slot).__name__}")
            parts.append(encode_text(slot))
        elif name in _LIST_SLOTS:
            if isinstance(slot, str) or not isinstance(slot, Iterable):
                raise TypeError(f"CAT.{name} must be a tuple of str, got {type(slot).__name__}")
            elements = tuple(slot)
            for element in elements:
                if not isinstance(element, str):
                    raise TypeError(
                        f"CAT.{name} elements must be str, got {type(element).__name__}"
                    )
            parts.append(encode_list(elements))
        elif name in _QUANTITY_SLOTS:
            if slot is not None and not isinstance(slot, Quantity):
                raise TypeError(f"CAT.{name} must be a Quantity or None, got {type(slot).__name__}")
            parts.append(encode_quantity(slot))
        else:  # pragma: no cover - _check_field_order guarantees exhaustiveness
            raise AssertionError(f"no encoding declared for CAT.{name}")
    return b"".join(parts)


def cat_key(cat: CAT) -> str:
    """``'cat1:' + sha256(preimage).hex()`` (spec §6).  Always 69 characters."""
    return CAT_KEY_PREFIX + hashlib.sha256(cat_preimage(cat)).hexdigest()
