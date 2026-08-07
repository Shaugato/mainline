# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""CATSEAL conformance: the committed golden vectors, twice over.

This is worker W3's PL-2 red test.  It was committed before
``mainline_domain.cat`` existed and failed with ``ModuleNotFoundError`` — a
conformance suite that has only ever been green proves that the implementation
agrees with itself, which is worth nothing.

The file asserts two independent things, and the second is the load-bearing one:

1. The **package** encoder reproduces every committed ``preimage_hex`` and
   ``cat_key`` byte-for-byte.
2. A **second encoder, written in this file directly from the prose of
   ``verticals/mainline/spec/cat-key-v1.md``** and importing nothing from
   ``mainline_domain``, produces the same bytes.

(2) is what makes the vectors evidence rather than a snapshot.  If the package
encoder and the fixture were the only two parties, a bug in the encoder would be
frozen into the fixture the moment it was regenerated, and the suite would go on
passing forever.  The in-file encoder is the opposing expert: it is short enough
to read in one sitting, it was transcribed from the spec, and it has no way to
learn the package's mistakes.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

import pytest

_FIXTURE: Final[Path] = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "domain"
    / "cat"
    / "golden-vectors.json"
)


def _load() -> dict[str, Any]:
    with _FIXTURE.open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


GOLDEN: Final[dict[str, Any]] = _load()
VECTORS: Final[list[dict[str, Any]]] = GOLDEN["vectors"]


# --------------------------------------------------------------------------- #
# The independent encoder — transcribed from cat-key-v1.md, §3 through §6.     #
# It must not import anything from mainline_domain.                            #
# --------------------------------------------------------------------------- #

_DOMAIN: Final[bytes] = b"mainline/cat/v1"
_ABSENT, _TEXT, _LIST, _QUANTITY = 0x00, 0x01, 0x02, 0x03

_ORDER: Final[tuple[str, ...]] = (
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
_QTY_SLOTS: Final[frozenset[str]] = frozenset({"value", "frequency"})


def _field(type_byte: int, payload: bytes) -> bytes:
    """§3: one type byte, a 4-byte big-endian byte length, then the payload."""
    return bytes([type_byte]) + len(payload).to_bytes(4, "big") + payload


def _text(value: str) -> bytes:
    """§3.2."""
    return _field(_TEXT, value.encode("utf-8"))


def _canonical_decimal(raw: str) -> str:
    """§4: plain positional notation, trailing fractional zeros stripped, no ``-0``."""
    dec = Decimal(raw)
    if not dec.is_finite():
        raise ValueError("non-finite decimal has no canonical spelling")
    text = format(dec, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in ("", "-", "-0"):
        text = "0"
    return text


def _quantity(slot: dict[str, str] | None) -> bytes:
    """§3.4, or §3.1 ABSENT."""
    if slot is None:
        return _field(_ABSENT, b"")
    payload = (
        _text(_canonical_decimal(slot["value"]))
        + _text(slot["unit"])
        + _text(slot["dimension"])
        + _text(slot["reference"])
    )
    return _field(_QUANTITY, payload)


def spec_preimage(cat: dict[str, Any]) -> bytes:
    """§5: ``DOMAIN || 0x1F || F1 .. F13``."""
    parts: list[bytes] = [_DOMAIN, b"\x1f"]
    for name in _ORDER:
        slot = cat[name]
        if name in _TEXT_SLOTS:
            parts.append(_text(slot))
        elif name in _LIST_SLOTS:
            parts.append(_field(_LIST, b"".join(_text(element) for element in slot)))
        elif name in _QTY_SLOTS:
            parts.append(_quantity(slot))
        else:  # pragma: no cover - _ORDER is exhaustive by construction
            raise AssertionError(name)
    return b"".join(parts)


def spec_cat_key(cat: dict[str, Any]) -> str:
    """§6."""
    return "cat1:" + hashlib.sha256(spec_preimage(cat)).hexdigest()


# --------------------------------------------------------------------------- #
# Bridging the fixture's JSON into the package's dataclasses                    #
# --------------------------------------------------------------------------- #


def build_cat(payload: dict[str, Any]) -> Any:
    """Construct a :class:`mainline_domain.contracts.CAT` from fixture JSON."""
    from mainline_domain.contracts import CAT, Quantity

    def quantity(slot: dict[str, str] | None) -> Quantity | None:
        if slot is None:
            return None
        return Quantity(
            value=Decimal(slot["value"]),
            unit=slot["unit"],
            dimension=slot["dimension"],
            reference=slot["reference"],  # type: ignore[arg-type]
        )

    return CAT(
        actor=payload["actor"],
        deontic=payload["deontic"],
        action=payload["action"],
        object_class=payload["object_class"],
        hazard_energy=payload["hazard_energy"],
        parameter=payload["parameter"],
        comparator=payload["comparator"],
        value=quantity(payload["value"]),
        conditions=tuple(payload["conditions"]),
        exceptions=tuple(payload["exceptions"]),
        verification=tuple(payload["verification"]),
        frequency=quantity(payload["frequency"]),
        coverage_quantifier=payload["coverage_quantifier"],
    )


_IDS: Final[list[str]] = [v["id"] for v in VECTORS]


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_fixture_is_well_formed() -> None:
    """The fixture pins the constants the spec declares, so a drifting spec fails here."""
    assert GOLDEN["cat_key_version"] == "cat1"
    assert bytes.fromhex(GOLDEN["preimage_domain_hex"]) == _DOMAIN
    assert GOLDEN["separator_hex"] == "1f"
    assert tuple(GOLDEN["field_order"]) == _ORDER
    assert GOLDEN["type_bytes"] == {"absent": 0, "text": 1, "list": 2, "quantity": 3}
    assert len(VECTORS) >= 12, "the spec's conformance suite is at least twelve vectors"
    assert len(set(_IDS)) == len(_IDS)


@pytest.mark.parametrize("vector", VECTORS, ids=_IDS)
def test_package_reproduces_committed_preimage(vector: dict[str, Any]) -> None:
    """The package encoder must reproduce the committed bytes exactly."""
    from mainline_domain.cat import cat_preimage

    assert cat_preimage(build_cat(vector["cat"])).hex() == vector["preimage_hex"], vector["why"]


@pytest.mark.parametrize("vector", VECTORS, ids=_IDS)
def test_package_reproduces_committed_cat_key(vector: dict[str, Any]) -> None:
    """``cat_key`` is ``'cat1:' + sha256(preimage).hex()`` and nothing else."""
    from mainline_domain.cat import cat_key

    key = cat_key(build_cat(vector["cat"]))
    assert key == vector["cat_key"], vector["why"]
    assert len(key) == 69
    assert key.startswith("cat1:")
    assert key[5:] == key[5:].lower()


@pytest.mark.parametrize("vector", VECTORS, ids=_IDS)
def test_independent_spec_encoder_agrees(vector: dict[str, Any]) -> None:
    """An encoder written from the spec prose, not from the code, gets the same bytes."""
    assert spec_preimage(vector["cat"]).hex() == vector["preimage_hex"]
    assert spec_cat_key(vector["cat"]) == vector["cat_key"]


@pytest.mark.parametrize("vector", VECTORS, ids=_IDS)
def test_package_and_spec_encoders_agree(vector: dict[str, Any]) -> None:
    """The two encoders agree without the fixture standing between them."""
    from mainline_domain.cat import cat_preimage

    assert cat_preimage(build_cat(vector["cat"])) == spec_preimage(vector["cat"])


def test_boundary_ambiguity_vectors_differ() -> None:
    """V11/V12 are the reason length prefixes exist; a naive encoder collides them."""
    by_id = {v["id"]: v for v in VECTORS}
    v11, v12 = by_id["V11"], by_id["V12"]
    assert v11["cat"]["actor"] + v11["cat"]["action"] == v12["cat"]["actor"] + v12["cat"]["action"]
    assert v11["preimage_hex"] != v12["preimage_hex"]
    assert v11["cat_key"] != v12["cat_key"]


def test_absent_and_empty_are_different_keys() -> None:
    """V01 vs V02 (quantity), V04 vs V05 (list): absent is not empty."""
    by_id = {v["id"]: v for v in VECTORS}
    assert by_id["V01"]["cat_key"] != by_id["V02"]["cat_key"]
    assert by_id["V04"]["cat_key"] != by_id["V05"]["cat_key"]


def test_canonical_decimal_collapses_representation_but_not_value() -> None:
    """V07 spells 1750 as ``1750.000`` and MUST land on V01's key; V08/V09 must not."""
    by_id = {v["id"]: v for v in VECTORS}
    assert by_id["V07"]["cat_key"] == by_id["V01"]["cat_key"]
    assert by_id["V08"]["cat_key"] != by_id["V01"]["cat_key"]
    assert by_id["V09"]["cat_key"] != by_id["V01"]["cat_key"], "gauge != absolute (D5)"


def test_list_order_is_significant_in_the_encoder() -> None:
    """V10 is V01 with the verification list reversed: the encoder does not sort."""
    by_id = {v["id"]: v for v in VECTORS}
    assert sorted(by_id["V10"]["cat"]["verification"]) == sorted(
        by_id["V01"]["cat"]["verification"]
    )
    assert by_id["V10"]["cat_key"] != by_id["V01"]["cat_key"]


def test_every_other_vector_pair_is_distinct() -> None:
    """Exactly one intended collision (V07 == V01) across the whole suite."""
    keys: dict[str, list[str]] = {}
    for vector in VECTORS:
        keys.setdefault(vector["cat_key"], []).append(vector["id"])
    collisions = {key: ids for key, ids in keys.items() if len(ids) > 1}
    assert list(collisions.values()) == [["V01", "V07"]], collisions
