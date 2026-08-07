# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CU-5 — the evidentiary payload profile, and the refusals that make it worth having.

The distinction under test is the whole point of the ruling: ``canonicalise`` stays fully
RFC 8785 conformant (a float is serialised, exactly as ECMAScript would), while
``canonicalise_payload`` — the function the sequencer and every agent actually call —
refuses the float outright. We keep the conformance and remove *evidence's* dependence on
the riskiest path in the specification.

A refusal-shaped product needs its refusals tested at least as hard as its successes, so
each raising path below is asserted on the exception **type**, and the negative cases are
paired with a positive case that proves the guard is not simply refusing everything.
"""

from __future__ import annotations

import json

import pytest
from trappoint_jcs.canon_v1 import (
    MAX_DEPTH,
    MAX_SAFE_INTEGER,
    DepthExceeded,
    DuplicateKey,
    InvalidString,
    NonEvidentiaryNumber,
    NonFiniteNumber,
    NonInteroperableNumber,
    NonStringKey,
    UnsupportedType,
    canonicalise,
    canonicalise_json,
    canonicalise_payload,
)

# --------------------------------------------------------------------------------------
# The float ban
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        1.0,
        [1.0],
        {"setpoint_bar": 3.5},
        {"a": {"b": [{"c": 0.1}]}},
        {"ok": 1, "not_ok": -0.0},
        [[[[1, 2, 3.0]]]],
        {"tuple_in_a_list": [(1, 2.5)]},
    ],
)
def test_payload_refuses_every_float_position(payload: object) -> None:
    with pytest.raises(NonEvidentiaryNumber):
        canonicalise_payload(payload)


def test_conformance_path_still_serialises_the_same_float() -> None:
    """The ban is a profile, not a capability removed from the canonicaliser."""
    assert canonicalise({"setpoint_bar": 3.5}) == b'{"setpoint_bar":3.5}'
    with pytest.raises(NonEvidentiaryNumber):
        canonicalise_payload({"setpoint_bar": 3.5})


def test_the_refusal_names_the_alternative() -> None:
    with pytest.raises(NonEvidentiaryNumber) as caught:
        canonicalise_payload({"pressure_kpa": 101.325})
    message = str(caught.value)
    assert "101.325" in message
    assert "integer" in message and "decimal string" in message


def test_the_intended_encodings_are_accepted() -> None:
    """What a payload carries instead of a float: exact integers and decimal strings."""
    payload = {
        "setpoint_millibar": 3500,
        "pressure_kpa": "101.325",
        "severity": 5,
        "bonded": True,
        "precursor_event_id": None,
        "clauses": ["4.2.1", "4.2.2"],
    }
    assert canonicalise_payload(payload) == canonicalise(payload)


def test_bool_is_not_caught_by_the_float_ban() -> None:
    assert canonicalise_payload({"blocking": True, "advisory": False}) == (
        b'{"advisory":false,"blocking":true}'
    )


def test_whole_structure_is_checked_before_any_byte_is_produced() -> None:
    """The refusal must name the offending value, not arrive part-way through."""
    with pytest.raises(NonEvidentiaryNumber) as caught:
        canonicalise_payload({"zzz_last_key": 0.25, "aaa_first_key": "fine"})
    assert "0.25" in str(caught.value)


# --------------------------------------------------------------------------------------
# Integers: exact, or refused
# --------------------------------------------------------------------------------------


def test_safe_integers_are_exact() -> None:
    assert canonicalise_payload(MAX_SAFE_INTEGER) == b"9007199254740991"
    assert canonicalise_payload(-MAX_SAFE_INTEGER) == b"-9007199254740991"


@pytest.mark.parametrize("value", [MAX_SAFE_INTEGER + 1, -(MAX_SAFE_INTEGER + 1), 10**30])
def test_integers_beyond_the_safe_range_are_refused(value: int) -> None:
    """A value ECMAScript would round is a value two implementations disagree about."""
    with pytest.raises(NonInteroperableNumber):
        canonicalise_payload(value)
    with pytest.raises(NonInteroperableNumber):
        canonicalise(value)


# --------------------------------------------------------------------------------------
# Everything else that must not silently become bytes
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_refused_by_the_conformance_path(value: float) -> None:
    with pytest.raises(NonFiniteNumber):
        canonicalise(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_refused_by_the_payload_path(value: float) -> None:
    # The payload profile refuses them one step earlier, as floats.
    with pytest.raises(NonEvidentiaryNumber):
        canonicalise_payload(value)


@pytest.mark.parametrize(
    "value",
    [
        b"bytes",
        {"decimal-like": object()},
        {1: "int key"},
        {"set": {1, 2}},
    ],
)
def test_non_json_values_are_refused(value: object) -> None:
    with pytest.raises((UnsupportedType, NonStringKey)):
        canonicalise(value)
    with pytest.raises((UnsupportedType, NonStringKey)):
        canonicalise_payload(value)


def test_duplicate_member_names_in_source_json_are_refused() -> None:
    """RFC 8785 §3.1 requires duplicate-free input.

    Resolving last-wins would mean choosing, on the writer's behalf, which of two records
    was the one that got signed.
    """
    with pytest.raises(DuplicateKey):
        canonicalise_json('{"disposition":"accepted","disposition":"mechanism_absent"}')


def test_unpaired_surrogates_have_no_canonical_form() -> None:
    lone = "\ud83d"  # a high surrogate with nothing after it
    with pytest.raises(InvalidString):
        canonicalise({"key": lone})
    with pytest.raises(InvalidString):
        canonicalise({lone: "value"})


def test_depth_is_bounded() -> None:
    shallow: object = "leaf"
    for _ in range(MAX_DEPTH - 1):
        shallow = [shallow]
    canonicalise(shallow)  # at the limit: fine

    deep: object = "leaf"
    for _ in range(MAX_DEPTH + 2):
        deep = [deep]
    with pytest.raises(DepthExceeded):
        canonicalise(deep)
    with pytest.raises(DepthExceeded):
        canonicalise_payload(deep)


def test_a_realistic_disposition_payload_round_trips() -> None:
    """The shape a ``disposition`` leaf actually carries, end to end."""
    payload = {
        "entry_kind": "disposition",
        "site_code": "BLK-07",
        "check_id": "018f3a2e-6c40-7b21-9c55-2a5c9e0f1b77",
        "disposition_kind": "mechanism_absent",
        "defeater_code": "D-114",
        "signer_sub": "auth0|4f2c",
        "signer_rank": 4,
        "severity": 5,
        "virulence": "blood_fatal",
        "issued_at": "2026-08-07T02:14:07.481Z",
        "rationale_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "clauses": ["4.2.1", "4.2.2"],
        "carried": False,
        "precursor_event_id": None,
    }
    canonical = canonicalise_payload(payload)
    assert canonical.startswith(b'{"carried":false,"check_id":')
    # The canonical bytes are valid JSON and canonicalising them again is a no-op.
    assert canonicalise(json.loads(canonical)) == canonical
