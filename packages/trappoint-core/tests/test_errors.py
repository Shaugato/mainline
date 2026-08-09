# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal taxonomy, and the three tiers of exhibit recovery. No database."""

from __future__ import annotations

import logging

import pytest
from psycopg import errors as pgerrors

from trappoint_core.errors import (
    DENIED_SQLSTATE,
    MODELLED_SQLSTATES,
    REFUSAL_SQLSTATES,
    RETRYABLE_SQLSTATE,
    GateRefused,
    UnmodelledRefusal,
    diagnose,
    gate_refused,
    sqlstate_of,
)


def test_the_taxonomy_is_exactly_the_five_modelled_codes():
    assert {"23514", "23503", "23505", "P0001"} == REFUSAL_SQLSTATES
    assert RETRYABLE_SQLSTATE == "40001"
    assert {"40001", "23514", "23503", "23505", "P0001"} == MODELLED_SQLSTATES
    # 42501 is excluded BY DEFINITION, not by exception: no gate condition was ever
    # evaluated, so it is a fact about the writer rather than a diagnosis of the subject.
    assert DENIED_SQLSTATE not in MODELLED_SQLSTATES


def test_sqlstate_is_read_from_the_real_psycopg_classes():
    assert sqlstate_of(pgerrors.SerializationFailure("x")) == "40001"
    assert sqlstate_of(pgerrors.CheckViolation("x")) == "23514"
    assert sqlstate_of(pgerrors.ForeignKeyViolation("x")) == "23503"
    assert sqlstate_of(pgerrors.UniqueViolation("x")) == "23505"
    assert sqlstate_of(pgerrors.RaiseException("x")) == "P0001"
    assert sqlstate_of(pgerrors.InsufficientPrivilege("x")) == "42501"
    assert sqlstate_of(ValueError("not a database error")) is None


def test_tier_one_a_reported_constraint_name_is_not_weakened(make_error):
    found = diagnose(
        make_error("23514", "gate_closed_when_issued", "failed to satisfy CHECK constraint")
    )
    assert found.sqlstate == "23514"
    assert found.constraint == "gate_closed_when_issued"
    assert found.weakened is False


def test_tier_two_p0001_names_its_own_object_in_the_message(make_error):
    # CockroachDB v26.2.5 populates neither `constraint_name` nor `context` for a
    # PL/pgSQL RAISE, so the kernel's templates emit the object into the message and
    # spec/errors.md 2.5 requires exactly that. Recovering it is NOT weakened: the
    # substrate controls the text.
    found = diagnose(
        make_error(
            "P0001",
            None,
            "MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived "
            "open obligation count is 1 while the projected counter reads zero",
        )
    )
    assert found.constraint == "mainline.fn_permit_merge_gate"
    assert found.weakened is False


def test_tier_three_a_bare_prefix_is_weakened_and_says_so(caplog, make_error):
    with caplog.at_level(logging.WARNING, logger="trappoint_core.errors"):
        found = diagnose(make_error("P0001", None, "MAINLINE: something refused this write"))
    assert found.constraint == "MAINLINE"
    assert found.weakened is True
    assert "weakened diagnosis" in caplog.text


def test_an_exhibit_is_never_smuggled_out_of_free_text(make_error):
    # The regex admits one shape: a lower-case dot-qualified SQL identifier. An exhibit
    # is written to a ledger and read in a courtroom, so free text may not become one.
    found = diagnose(
        make_error("P0001", None, "MAINLINE: refused by Robert'); DROP TABLE permit;--")
    )
    assert found.constraint == "MAINLINE"
    assert found.weakened is True


def test_gate_refused_carries_the_subject_and_the_epoch(make_error):
    refusal = gate_refused(
        make_error("23503", "epoch_pin_permit", "violates foreign key constraint"),
        subject_kind="permit",
        subject_id="00000000-0000-0000-0000-00000000000a",
        gate_epoch=3,
    )
    assert isinstance(refusal, GateRefused)
    payload = refusal.as_dict()
    assert payload["sqlstate"] == "23503"
    assert payload["constraint"] == "epoch_pin_permit"
    assert payload["subject_kind"] == "permit"
    assert payload["gate_epoch"] == 3
    assert payload["weakened"] is False


def test_a_retryable_code_cannot_be_dressed_up_as_a_refusal(make_error):
    # An undecided transaction has no reason set (spec/errors.md 5). Building a
    # GateRefused out of 40001 would put a refusal in the ledger for a decision the gate
    # never made.
    with pytest.raises(ValueError, match="not a refusal code"):
        gate_refused(make_error("40001", None, "restart transaction"))


def test_unmodelled_refusal_is_not_a_gate_refused():
    # A caller that catches GateRefused is handling a decision. 23502 is not one: it
    # means a NOT NULL projected column was left unset, which is a defect in the
    # substrate, and it must not be absorbed by refusal-handling code.
    unmodelled = UnmodelledRefusal("23502", "null value in column violates not-null")
    assert not isinstance(unmodelled, GateRefused)
    assert "23502" in str(unmodelled)
    assert "nobody modelled" in str(unmodelled)
