# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The refusal has a shape, and `spec/errors.md` §4 says how many times it is attempted.

Two properties, and neither of them is "an exception was raised":

**The exhibit survives the service.** A `GateRefused` that leaves
:func:`mainline_gate_svc.service.merge_permit` carries the five-character SQLSTATE *and*
the constraint name — the name of the `CHECK`, the unique index, or the raising object
for `P0001`. §3.1 is explicit that a test asserting only a SQLSTATE is not conformant,
because in a product whose deliverable is the diagnosis, *"an exception was raised"* is
worth nothing.

**A refusal is attempted exactly once, ever** (§4). Not once per retry budget; once.
`40001` climbs the ladder because the transaction is *undecided*; `23514` does not,
because the gate already decided. The difference between those two sentences is the
product: a retried `23514` writes five identical rows into the refusal ledger for one
attempted history, and the count of refusals stops being a count of anything.

Everything here runs against a scripted connection rather than a cluster, on purpose —
the property being asserted is a property of the CLIENT, and a test that needed a live
node to observe it would be a test nobody runs before pushing. The live half is the
gate-refusal proof (`scripts/proof/gate_refusal.py`, W3's `done_when`), which asserts
the same shape against a real CockroachDB refusal.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from mainline_gate_svc.config import GateConfig
from mainline_gate_svc.service import (
    MERGE_CALL_FIELDS,
    ConnectionUnavailable,
    DirectConnection,
    WrongBinding,
    call_parameters,
    merge_permit,
    merge_request_from_mapping,
)

from trappoint_core import (
    ISOLATION_STATEMENT,
    AuthorisationDenied,
    GateRefused,
    MergeRequest,
    RecordingObserver,
    RetryBudgetExhausted,
    RetryPolicy,
    UnmodelledRefusal,
)
from trappoint_core.gate import call_statement

# A ladder with no wait: `full_jitter` returns `U(0, 0) == 0.0`, so the retry path is
# exercised in full and the suite spends no wall clock on it.
INSTANT = RetryPolicy(max_attempts=4, base_delay_s=0.0, cap_delay_s=0.0)

CONFIG = GateConfig(dsn="postgresql://root@127.0.0.1:26257/nowhere?sslmode=disable")


class _Diag:
    """The two `psycopg` diagnostic fields `trappoint_core.errors.diagnose` reads."""

    def __init__(self, constraint_name: str, message_primary: str) -> None:
        self.constraint_name = constraint_name
        self.message_primary = message_primary


class FakeSqlError(psycopg.Error):
    """A driver error with a chosen SQLSTATE and diagnostic.

    A `psycopg.Error` subclass and not a bare `Exception`, because `run_gate` catches
    `psycopg.Error` *specifically* — a blanket catch is how a refusal becomes a silence
    — and a double that was not one would never reach the classifier under test.
    """

    def __init__(self, sqlstate: str, constraint: str = "", message: str = "") -> None:
        self._sqlstate = sqlstate
        self._diag = _Diag(constraint, message)
        super().__init__(message)

    @property
    def sqlstate(self) -> str:
        return self._sqlstate

    @property
    def diag(self) -> Any:
        return self._diag


class ScriptedConnection:
    """One connection. Records every statement; raises what the script says on the CALL."""

    def __init__(self, outcome: BaseException | None, log: list[list[Any]]) -> None:
        self.outcome = outcome
        self.statements: list[Any] = []
        self.committed = 0
        self.rolled_back = 0
        self.closed = False
        log.append(self.statements)

    def cursor(self) -> ScriptedConnection:
        return self

    def execute(self, statement: Any, params: Sequence[Any] | None = None) -> None:
        self.statements.append(statement)
        if params is None:
            return  # the isolation statement; it never fails in these cases
        if self.outcome is not None:
            raise self.outcome

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1


class ScriptedSource:
    """A `ConnectionSource` that hands out one connection per attempt, in script order."""

    def __init__(self, outcomes: Sequence[BaseException | None]) -> None:
        self.outcomes = list(outcomes)
        self.attempts = 0
        self.statement_log: list[list[Any]] = []
        self.connections: list[ScriptedConnection] = []

    @contextmanager
    def connection(self) -> Iterator[ScriptedConnection]:
        outcome = self.outcomes[self.attempts] if self.attempts < len(self.outcomes) else None
        self.attempts += 1
        conn = ScriptedConnection(outcome, self.statement_log)
        self.connections.append(conn)
        try:
            yield conn
        finally:
            conn.closed = True


def a_request(**overrides: Any) -> MergeRequest:
    """A structurally valid merge request. Values are shaped, not meaningful."""
    fields: dict[str, Any] = {
        "schema": "mainline",
        "subject_kind": "permit",
        "subject_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "merged_commit": bytes(range(32)),
        "merged_by": "auth0|inspector",
        "actor_kind": "human",
        "payload": '{"kind":"merge"}',
        "canon_bytes": b'{"kind":"merge"}',
        "payload_ver": 1,
        "leaf_hash": bytes(32),
        "gate_epoch": 7,
    }
    fields.update(overrides)
    return MergeRequest(**fields)


# ---------------------------------------------------------------------------
# The exhibit
# ---------------------------------------------------------------------------


def test_a_check_violation_arrives_with_its_constraint_name() -> None:
    refusal = FakeSqlError(
        "23514",
        "gate_closed_when_issued",
        "MAINLINE: merge refused by mainline.fn_permit_merge_gate - obligations are open",
    )
    source = ScriptedSource([refusal])
    spy = RecordingObserver()

    with pytest.raises(GateRefused) as caught:
        merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT, observer=spy)

    assert caught.value.sqlstate == "23514"
    assert caught.value.constraint == "gate_closed_when_issued"
    assert caught.value.weakened is False
    assert caught.value.subject_id == "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    assert caught.value.gate_epoch == 7


def test_a_p0001_recovers_the_raising_object_from_the_message() -> None:
    """`diag.constraint_name` is empty for P0001; §2.5 puts the object in the message."""
    refusal = FakeSqlError(
        "P0001",
        "",
        "MAINLINE: merge refused by mainline.merge_permit - the head moved under the gate",
    )
    with pytest.raises(GateRefused) as caught:
        merge_permit(a_request(), config=CONFIG, source=ScriptedSource([refusal]), policy=INSTANT)

    assert caught.value.sqlstate == "P0001"
    assert caught.value.constraint == "mainline.merge_permit"
    assert caught.value.weakened is False


def test_a_refusal_payload_carries_every_field_the_wire_shape_requires() -> None:
    refusal = FakeSqlError("23505", "merge_record_pkey", "MAINLINE: merge refused - already merged")
    with pytest.raises(GateRefused) as caught:
        merge_permit(a_request(), config=CONFIG, source=ScriptedSource([refusal]), policy=INSTANT)

    payload = caught.value.as_dict()
    assert set(payload) == {
        "sqlstate",
        "constraint",
        "message",
        "subject_kind",
        "subject_id",
        "gate_epoch",
        "weakened",
    }
    assert payload["sqlstate"] == "23505"
    assert payload["constraint"] == "merge_record_pkey"


def test_the_service_never_swallows_the_refusal() -> None:
    """There is no return value that could be mistaken for a verdict."""
    refusal = FakeSqlError("23503", "permit_gate_epoch_fk", "MAINLINE: merge refused")
    source = ScriptedSource([refusal])
    with pytest.raises(GateRefused):
        merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT)
    assert source.connections[0].committed == 0
    assert source.connections[0].rolled_back == 1


# ---------------------------------------------------------------------------
# Attempted exactly once, ever (§4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sqlstate", ["23514", "23503", "23505", "P0001"])
def test_a_refusal_is_attempted_exactly_once(sqlstate: str) -> None:
    refusal = FakeSqlError(sqlstate, "an_exhibit", "MAINLINE: merge refused by mainline.gate - no")
    source = ScriptedSource([refusal, refusal, refusal, refusal])
    spy = RecordingObserver()

    with pytest.raises(GateRefused):
        merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT, observer=spy)

    assert source.attempts == 1, f"{sqlstate} was attempted {source.attempts} times"
    assert spy.attempts_for(sqlstate) == 1
    assert spy.retries == []
    assert len(spy.refusals) == 1


def test_a_serialization_failure_is_retried_and_then_commits() -> None:
    retryable = FakeSqlError("40001", "", "restart transaction: TransactionRetryWithProtoRefresh")
    source = ScriptedSource([retryable, retryable, None])
    spy = RecordingObserver()

    outcome = merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT, observer=spy)

    assert source.attempts == 3
    assert outcome.attempts == 3
    assert outcome.retried_sqlstates == ("40001", "40001")
    assert spy.attempts_for("40001") == 2
    assert spy.successes == [2]
    assert source.connections[-1].committed == 1


def test_a_serialization_failure_that_outlasts_the_budget_is_undecided_not_refused() -> None:
    retryable = FakeSqlError("40001", "", "restart transaction")
    source = ScriptedSource([retryable] * 6)

    with pytest.raises(RetryBudgetExhausted) as caught:
        merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT)

    assert not isinstance(caught.value, GateRefused)
    assert source.attempts == INSTANT.max_attempts


def test_retry_and_refusal_in_one_history_still_attempts_the_refusal_once() -> None:
    """The shape that actually happens: contention, then a decision."""
    retryable = FakeSqlError("40001", "", "restart transaction")
    refusal = FakeSqlError("23514", "gate_closed_when_issued", "MAINLINE: merge refused")
    source = ScriptedSource([retryable, refusal])
    spy = RecordingObserver()

    with pytest.raises(GateRefused) as caught:
        merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT, observer=spy)

    assert caught.value.constraint == "gate_closed_when_issued"
    assert spy.attempts_for("40001") == 1
    assert spy.attempts_for("23514") == 1
    assert source.attempts == 2


# ---------------------------------------------------------------------------
# The codes that are NOT gate refusals
# ---------------------------------------------------------------------------


def test_42501_is_a_denial_and_is_never_retried() -> None:
    denied = FakeSqlError("42501", "", "user inspector does not have INSERT privilege")
    source = ScriptedSource([denied, denied])

    with pytest.raises(AuthorisationDenied) as caught:
        merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT)

    assert not isinstance(caught.value, GateRefused)
    assert caught.value.sqlstate == "42501"
    assert source.attempts == 1


def test_an_unmodelled_sqlstate_is_not_dressed_up_as_a_refusal() -> None:
    unmodelled = FakeSqlError("23502", "", "null value in column violates not-null constraint")
    with pytest.raises(UnmodelledRefusal) as caught:
        merge_permit(
            a_request(), config=CONFIG, source=ScriptedSource([unmodelled]), policy=INSTANT
        )
    assert not isinstance(caught.value, GateRefused)
    assert caught.value.sqlstate == "23502"


def test_an_unreachable_cluster_is_not_a_gate_verdict() -> None:
    """A failed connect must not be classified against the SQLSTATE taxonomy."""
    source = DirectConnection(
        GateConfig(dsn="postgresql://root@127.0.0.1:1/none?sslmode=disable", connect_timeout_s=1)
    )
    with pytest.raises(ConnectionUnavailable) as caught:
        merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT)
    assert not isinstance(caught.value, (GateRefused, UnmodelledRefusal))
    assert "127.0.0.1:1" in str(caught.value)


# ---------------------------------------------------------------------------
# The transaction the service actually issues
# ---------------------------------------------------------------------------


def test_the_isolation_level_is_the_first_statement_of_every_attempt() -> None:
    retryable = FakeSqlError("40001", "", "restart transaction")
    source = ScriptedSource([retryable, None])

    merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT)

    assert len(source.statement_log) == 2
    for statements in source.statement_log:
        assert statements[0] == ISOLATION_STATEMENT
        assert len(statements) == 2


def test_the_call_is_composed_against_the_binding_schema() -> None:
    source = ScriptedSource([None])
    merge_permit(a_request(), config=CONFIG, source=source, policy=INSTANT)
    composed = source.statement_log[0][1]
    assert composed == call_statement("mainline", "permit")


def test_the_parameter_list_matches_the_procedure_signature() -> None:
    """Eight fields here, eight placeholders in the CALL. A mismatch is 42883 in prod."""
    text = call_statement("mainline", "permit").as_string()
    assert text.count("%s") == len(MERGE_CALL_FIELDS) == 8
    assert len(call_parameters(a_request())) == 8


def test_the_outcome_records_what_the_transaction_did() -> None:
    clock = iter([100.0, 100.25])
    outcome = merge_permit(
        a_request(),
        config=CONFIG,
        source=ScriptedSource([None]),
        policy=INSTANT,
        now=lambda: next(clock),
    )
    assert outcome.as_dict()["merged"] is True
    assert outcome.attempts == 1
    assert outcome.retried_sqlstates == ()
    assert outcome.elapsed_ms == pytest.approx(250.0)
    assert outcome.isolation_statement == ISOLATION_STATEMENT
    assert outcome.domain_version


# ---------------------------------------------------------------------------
# Refusals that happen before a connection is opened
# ---------------------------------------------------------------------------


def test_a_request_for_another_binding_is_refused_without_connecting() -> None:
    source = ScriptedSource([None])
    with pytest.raises(WrongBinding):
        merge_permit(a_request(schema="other"), config=CONFIG, source=source, policy=INSTANT)
    assert source.attempts == 0


def test_a_request_for_another_subject_kind_is_refused_without_connecting() -> None:
    source = ScriptedSource([None])
    with pytest.raises(WrongBinding):
        merge_permit(
            a_request(subject_kind="change_request"),
            config=CONFIG,
            source=source,
            policy=INSTANT,
        )
    assert source.attempts == 0


def test_the_wire_shape_round_trips_through_base64() -> None:
    body = {
        "subject_id": "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "merged_commit": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "merged_by": "auth0|inspector",
        "actor_kind": "human",
        "payload": '{"kind":"merge"}',
        "canon_bytes": "eyJraW5kIjoibWVyZ2UifQ==",
        "payload_ver": 1,
        "leaf_hash": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        "gate_epoch": 7,
    }
    request = merge_request_from_mapping(body, schema="mainline", subject_kind="permit")
    assert request.canon_bytes == b'{"kind":"merge"}'
    assert request.gate_epoch == 7
    assert len(request.leaf_hash) == 32
