# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``execute_gate`` without a database: the isolation statement, the CALL, the verdict."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from trappoint_core.errors import GateRefused
from trappoint_core.gate import (
    ISOLATION_STATEMENT,
    SUBJECT_KINDS,
    MergeRequest,
    call_statement,
    execute_gate,
    procedure_name,
    refusals_of,
)
from trappoint_core.retry import RecordingObserver, RetryPolicy


def a_request(**overrides) -> MergeRequest:
    fields: dict[str, Any] = {
        "schema": "mainline",
        "subject_kind": "permit",
        "subject_id": "00000000-0000-0000-0000-00000000000a",
        "merged_commit": bytes(32),
        "merged_by": "alice",
        "actor_kind": "human",
        "payload": '{"note":"merge"}',
        "canon_bytes": b'{"note":"merge"}',
        "payload_ver": 1,
        "leaf_hash": bytes(32),
        "gate_epoch": 0,
    }
    fields.update(overrides)
    return MergeRequest(**fields)


class FakeCursor:
    def __init__(self, owner: FakeConnection) -> None:
        self.owner = owner

    def execute(self, query, params=None):
        self.owner.statements.append((query, params))
        if self.owner.raises and len(self.owner.statements) == 2:
            raise self.owner.raises


class FakeConnection:
    def __init__(self, raises: BaseException | None = None) -> None:
        self.statements: list[tuple[object, object]] = []
        self.commits = 0
        self.rollbacks = 0
        self.raises = raises

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakePool:
    def __init__(self, *connections: FakeConnection) -> None:
        self.queue = list(connections)
        self.handed_out: list[FakeConnection] = []

    @contextmanager
    def connection(self):
        conn = self.queue.pop(0)
        self.handed_out.append(conn)
        yield conn


def test_the_procedure_lives_in_the_binding_schema_not_a_shared_one():
    # Two bindings on one cluster would otherwise render one object twice and the second
    # migration would silently redefine the first vertical's gate. See migration 0117.
    assert procedure_name("mainline", "permit").as_string() == '"mainline"."merge_permit"'
    assert procedure_name("trappoint_ref", "permit").as_string() == '"trappoint_ref"."merge_permit"'
    assert (
        procedure_name("mainline", "change_request").as_string()
        == '"mainline"."merge_change_request"'
    )
    # Never `trappoint.merge_permit`: one shared object cannot serve two bindings.
    assert "trappoint." not in procedure_name("mainline", "permit").as_string()


def test_an_identifier_is_never_composed_out_of_free_text():
    with pytest.raises(ValueError, match="unknown subject kind"):
        procedure_name("mainline", "permit; DROP TABLE permit")
    with pytest.raises(ValueError, match="lower-case SQL identifier"):
        procedure_name('mainline"; DROP SCHEMA mainline; --', "permit")
    with pytest.raises(ValueError, match="unknown subject kind"):
        a_request(subject_kind="release")


def test_the_call_names_the_procedure_and_takes_eight_parameters():
    text = call_statement("mainline", "permit").as_string()
    assert "CALL" in text
    assert '"mainline"."merge_permit"' in text
    assert text.count("%s") == 8


def test_isolation_is_asserted_as_the_first_statement_of_every_attempt():
    conn = FakeConnection()
    pool = FakePool(conn)
    execute_gate(pool, a_request())
    assert conn.statements[0][0] == ISOLATION_STATEMENT
    assert conn.commits == 1
    assert conn.rollbacks == 0


def test_a_refusal_rolls_back_and_is_attempted_exactly_once(make_error):
    refused = make_error("23514", "gate_closed_when_issued", "failed to satisfy CHECK constraint")
    conn = FakeConnection(raises=refused)
    pool = FakePool(conn)
    spy = RecordingObserver()

    with pytest.raises(GateRefused) as caught:
        execute_gate(pool, a_request(), policy=RetryPolicy(max_attempts=5), observer=spy)

    assert caught.value.constraint == "gate_closed_when_issued"
    assert caught.value.subject_kind == "permit"
    assert caught.value.gate_epoch == 0
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert spy.attempts == [0]
    assert len(pool.handed_out) == 1, "one attempt means one connection checked out"


def test_40001_retries_on_a_fresh_connection_from_begin(make_error):
    # spec/errors.md 2.1: retry the WHOLE transaction, never a statement. A statement
    # replayed into an aborted transaction is 25P02, which the taxonomy calls a client
    # bug in transaction handling.
    transient = make_error("40001", None, "restart transaction")
    first = FakeConnection(raises=transient)
    second = FakeConnection()
    pool = FakePool(first, second)
    spy = RecordingObserver()

    execute_gate(pool, a_request(), observer=spy)

    assert first.rollbacks == 1
    assert second.commits == 1
    assert second.statements[0][0] == ISOLATION_STATEMENT
    assert len(spy.retries) == 1


def test_refusals_of_yields_a_payload_only_for_a_decision():
    refusal = GateRefused("23514", "gate_closed_when_issued", "refused", "permit", "abc", 2)
    assert [payload["constraint"] for payload in refusals_of(refusal)] == [
        "gate_closed_when_issued"
    ]
    assert list(refusals_of(RuntimeError("undecided"))) == []


def test_the_subject_kinds_match_the_two_the_kernel_gates():
    assert {"permit", "change_request"} == SUBJECT_KINDS
