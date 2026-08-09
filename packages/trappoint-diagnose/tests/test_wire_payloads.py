# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The emitter against the SHIPPED specification, not against a copy of it.

The four worked payloads in ``spec/wire/refusal.md`` section 8 exist so an emitter has
something to diff against rather than prose to interpret. This module reads them out of
the markdown at test time and validates each one. Copying them in here would defeat the
purpose twice over: the copies would drift, and the drift would be invisible because each
copy would keep validating.

Section 8.5 lists sixteen mutations the schema must REJECT. Those are the assertions that
matter — a schema that accepts everything is documentation. Each mutation below is applied
to the section 8.1 payload and asserted to fail, so the negative half of the contract is
proved rather than assumed.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from trappoint_diagnose.errors import PayloadInvalid
from trappoint_diagnose.model import (
    CapabilityGap,
    DisposeObligations,
    Obligation,
    RefusalContext,
)
from trappoint_diagnose.wire import build_payload, load_refusal_schema, validate_payload

_FENCE = re.compile(r"```json\n(?P<body>.*?)\n```", re.DOTALL)
UUID_A = "6f1c7f0e-2b7c-4c0e-9f1b-77a1f0d3c2aa"
UUID_B = "3d0b6b17-6c3a-4d6b-a0f4-8e5b0a9d1c22"


def repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "spec" / "wire" / "refusal.md").is_file():
            return parent
    pytest.skip("spec/wire/refusal.md is not in this checkout")
    raise AssertionError


def worked_payloads() -> list[dict]:
    text = (repo_root() / "spec" / "wire" / "refusal.md").read_text(encoding="utf-8")
    return [json.loads(match.group("body")) for match in _FENCE.finditer(text)]


@pytest.fixture(scope="module")
def schema() -> dict:
    return load_refusal_schema()


def test_the_specification_still_carries_its_four_worked_payloads():
    # If section 8 loses its examples, the rest of this module silently asserts nothing.
    assert len(worked_payloads()) == 4


def test_every_worked_payload_validates(schema):
    for index, payload in enumerate(worked_payloads()):
        validate_payload(payload, schema)
        assert payload["class"] == "gate", f"payload {index} is not a gate outcome"


@pytest.fixture
def counter_refusal() -> dict:
    """Section 8.1: the counter refusal. Every mutation below is applied to this."""
    for payload in worked_payloads():
        if payload["constraint"] == "gate_closed_when_issued":
            return payload
    pytest.skip("spec section 8.1 no longer carries the counter refusal")
    raise AssertionError


def mutate(payload: dict, **changes) -> dict:
    out = copy.deepcopy(payload)
    for key, value in changes.items():
        if value is ...:
            out.pop(key, None)
        else:
            out[key] = value
    return out


def test_null_alternative_without_a_reason_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, naa=None, naa_reason=...), schema)


def test_null_alternative_with_a_null_reason_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, naa=None, naa_reason=None), schema)


def test_an_alternative_and_a_reason_at_once_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, naa_reason="not_computable"), schema)


def test_a_declarative_diagnosis_that_probed_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, probe_calls=3), schema)


def test_diagnosis_none_with_an_alternative_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, diagnosis="none", probe_calls=0), schema)


def test_an_unknown_top_level_field_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, confidence=0.9), schema)


def test_an_empty_reason_set_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, mus=[]), schema)


@pytest.mark.parametrize("code", ["40001", "42501", "00000"])
def test_a_non_refuse_class_code_is_refused(counter_refusal, schema, code):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, sqlstate=code), schema)


def test_a_blank_exhibit_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, constraint=""), schema)


def test_an_unknown_key_inside_an_atom_is_refused(counter_refusal, schema):
    # THE ONE THAT MATTERS. `additionalProperties: false` on every atom is the wire-level
    # enforcement of invariant I15: there is no field on this payload where a score about
    # a human being could be placed.
    broken = copy.deepcopy(counter_refusal)
    broken["mus"][0]["signer_attentiveness"] = 0.2
    with pytest.raises(PayloadInvalid):
        validate_payload(broken, schema)


def test_an_atom_missing_its_identifying_field_is_refused(counter_refusal, schema):
    broken = copy.deepcopy(counter_refusal)
    del broken["mus"][0]["obligation_id"]
    with pytest.raises(PayloadInvalid):
        validate_payload(broken, schema)


def test_an_alternative_without_cardinality_is_refused(counter_refusal, schema):
    broken = copy.deepcopy(counter_refusal)
    del broken["naa"]["cardinality"]
    with pytest.raises(PayloadInvalid):
        validate_payload(broken, schema)


def test_a_class_other_than_gate_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, **{"class": "retry"}), schema)


def test_a_negative_gate_epoch_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, gate_epoch=-1), schema)


def test_a_digest_with_an_unrecognised_prefix_is_refused(counter_refusal, schema):
    broken = copy.deepcopy(counter_refusal)
    broken["evidence"][0]["digest"] = "md5:deadbeef"
    with pytest.raises(PayloadInvalid):
        validate_payload(broken, schema)


def test_a_naive_observed_at_is_refused(counter_refusal, schema):
    with pytest.raises(PayloadInvalid):
        validate_payload(mutate(counter_refusal, observed_at="2026-08-04T02:14:07.481"), schema)


# ── the emitter's own refusals, before the schema ever sees the payload ────────────


def context(**overrides) -> RefusalContext:
    fields = {
        "sqlstate": "23514",
        "constraint": "gate_closed_when_issued",
        "message": "MAINLINE: merge refused — undispositioned precursor in blame ancestry",
        "subject_kind": "permit",
        "subject_id": UUID_A,
        "gate_epoch": 7,
    }
    fields.update(overrides)
    return RefusalContext(**fields)  # type: ignore[arg-type]


def test_the_emitter_produces_a_payload_that_validates(schema):
    payload = build_payload(
        context(),
        spec_version="1.0.0-rc.1",
        diagnosis="declarative",
        mus=[Obligation(obligation_id=UUID_B, severity=5, virulence="blood_fatal")],
        naa=DisposeObligations(
            obligation_ids=[UUID_B],
            cardinality=1,
            legal_kinds=["applied", "mitigated"],
            description="one obligation remains open",
        ),
        naa_reason=None,
        profile="mainline",
        schema=schema,
    )
    wire = payload.to_wire()
    validate_payload(wire, schema)
    assert wire["mus"][0]["obligation_id"] == UUID_B
    assert wire["naa"]["cardinality"] == 1
    assert wire["naa_reason"] is None


def test_a_context_outside_the_refuse_class_is_refused_at_construction():
    with pytest.raises(ValueError, match="not a REFUSE-class code"):
        context(sqlstate="40001")


def test_a_context_with_no_exhibit_is_refused_at_construction():
    with pytest.raises(ValueError, match="no exhibit"):
        context(constraint="")


def test_the_emitter_refuses_a_declarative_diagnosis_that_probed(schema):
    with pytest.raises(ValueError, match="consumes no oracle calls"):
        build_payload(
            context(),
            spec_version="1.0.0-rc.1",
            diagnosis="declarative",
            mus=[CapabilityGap(capability="x")],
            naa=None,
            naa_reason="not_computable",
            probe_calls=4,
            schema=schema,
        )


def test_the_emitter_refuses_an_empty_reason_set(schema):
    with pytest.raises(ValueError, match="no reason set"):
        build_payload(
            context(),
            spec_version="1.0.0-rc.1",
            diagnosis="none",
            mus=[],
            naa=None,
            naa_reason="not_computable",
            schema=schema,
        )


def test_atoms_are_emitted_in_a_byte_stable_order(schema):
    atoms = [
        Obligation(obligation_id="ffffffff-0000-0000-0000-000000000001"),
        CapabilityGap(capability="permit.open_blocking"),
        Obligation(obligation_id="00000000-0000-0000-0000-000000000002"),
    ]
    wire = build_payload(
        context(),
        spec_version="1.0.0-rc.1",
        diagnosis="none",
        mus=atoms,
        naa=None,
        naa_reason="not_computable",
        schema=schema,
    ).to_wire()
    assert [atom["kind"] for atom in wire["mus"]] == [
        "capability_gap",
        "obligation",
        "obligation",
    ]
    assert wire["mus"][1]["obligation_id"].startswith("00000000")
