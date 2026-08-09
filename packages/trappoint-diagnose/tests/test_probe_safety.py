# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The probe must never be able to mutate the gate. These are the tests of that sentence.

Four claims, each asserted rather than documented:

1. the probe transaction is rolled back **even when the oracle raises** — the whole point
   of putting the rollback in a `finally`;
2. it is rolled back when the PLAN raises, when the CALLER raises, and on the happy path;
3. every probe is wrapped in ``SAVEPOINT`` / ``ROLLBACK TO SAVEPOINT``, in that order,
   with the rollback issued whether the attempt succeeded or was refused;
4. an oracle refuses at construction a connection that is already inside a transaction —
   because row locks survive ``ROLLBACK TO SAVEPOINT`` in CockroachDB, so a probe on the
   gate's connection would leave the gate holding locks it never took.

The fake connection records every statement, so the assertions are about the sequence of
SQL the oracle actually emitted rather than about what it says it does.
"""

from __future__ import annotations

import pytest

from trappoint_diagnose.errors import (
    OracleUnavailable,
    ProbeBudgetExhausted,
    ProbeUnsafe,
)
from trappoint_diagnose.oracle import ProbePlan, SavepointOracle, probe_transaction


class Refused(Exception):
    """Stands in for a driver error carrying a SQLSTATE."""

    def __init__(self, sqlstate: str) -> None:
        super().__init__(f"refused with {sqlstate}")
        self.sqlstate = sqlstate


class FakeCursor:
    def __init__(self, log, rows=None):
        self.log = log
        self._rows = list(rows or [])
        self.closed = False

    def execute(self, query, params=None):
        self.log.append(("execute", " ".join(query.split()), params))

    def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    def close(self):
        self.closed = True
        self.log.append(("close-cursor", None, None))


class FakeInfo:
    def __init__(self, transaction_status):
        self.transaction_status = transaction_status


class FakeConnection:
    def __init__(self, transaction_status=0, rows=None):
        self.log = []
        self.info = FakeInfo(transaction_status)
        self.rolled_back = 0
        self.closed = 0
        self._rows = rows

    def cursor(self):
        return FakeCursor(self.log, self._rows)

    def rollback(self):
        self.rolled_back += 1
        self.log.append(("rollback", None, None))

    def close(self):
        self.closed += 1
        self.log.append(("close-connection", None, None))


def statements(connection):
    return [text for kind, text, _ in connection.log if kind == "execute"]


def noop_plan(**overrides):
    def apply(cursor, fact):
        cursor.execute("-- apply", (fact,))

    def attempt(cursor):
        cursor.execute("-- attempt")

    return ProbePlan(apply=overrides.get("apply", apply), attempt=overrides.get("attempt", attempt))


def test_the_probe_transaction_is_rolled_back_when_the_oracle_raises():
    connection = FakeConnection()

    def attempt(_cursor):
        raise RuntimeError("the oracle blew up mid-probe")

    with (
        pytest.raises(OracleUnavailable),
        probe_transaction(lambda: connection, noop_plan(attempt=attempt)) as oracle,
    ):
        oracle.admissible(["a"])

    assert connection.rolled_back == 1, "the gate must not inherit a probe's writes"
    assert connection.closed == 1


def test_the_probe_transaction_is_rolled_back_when_the_caller_raises():
    connection = FakeConnection()
    with pytest.raises(ZeroDivisionError), probe_transaction(lambda: connection, noop_plan()):
        raise ZeroDivisionError
    assert connection.rolled_back == 1
    assert connection.closed == 1


def test_the_probe_transaction_is_rolled_back_on_the_happy_path():
    connection = FakeConnection()
    with probe_transaction(lambda: connection, noop_plan()) as oracle:
        assert oracle.admissible(["a", "b"]) is True
    assert connection.rolled_back == 1
    assert connection.closed == 1


def test_the_connection_is_closed_even_when_the_rollback_itself_fails():
    connection = FakeConnection()

    def exploding_rollback():
        raise RuntimeError("connection lost")

    connection.rollback = exploding_rollback  # type: ignore[method-assign]
    with (
        pytest.raises(RuntimeError, match="connection lost"),
        probe_transaction(lambda: connection, noop_plan()),
    ):
        pass
    assert connection.closed == 1, "a failed rollback must not leak the connection"


def test_every_probe_is_bracketed_by_a_savepoint_and_its_rollback():
    connection = FakeConnection()
    with probe_transaction(lambda: connection, noop_plan()) as oracle:
        oracle.admissible(["a"])
        oracle.admissible(["b"])
    emitted = statements(connection)
    assert emitted[0].startswith("SET statement_timeout")
    assert emitted[1] == "SAVEPOINT tp_probe_1"
    assert emitted[4] == "ROLLBACK TO SAVEPOINT tp_probe_1"
    assert emitted[5] == "SAVEPOINT tp_probe_2"
    assert emitted[-1] == "ROLLBACK TO SAVEPOINT tp_probe_2"


def test_the_savepoint_is_rolled_back_after_a_refusal_too():
    connection = FakeConnection()

    def attempt(_cursor):
        raise Refused("23514")

    with probe_transaction(lambda: connection, noop_plan(attempt=attempt)) as oracle:
        assert oracle.admissible(["a"]) is False
    assert "ROLLBACK TO SAVEPOINT tp_probe_1" in statements(connection)


def test_a_non_refusal_error_is_not_reported_as_inadmissible():
    # 42501 is a fact about the WRITER. Reporting it as inadmissible would produce a
    # minimal unsatisfiable subset of a permissions problem.
    connection = FakeConnection()

    def attempt(_cursor):
        raise Refused("42501")

    with (
        pytest.raises(OracleUnavailable),
        probe_transaction(lambda: connection, noop_plan(attempt=attempt)) as oracle,
    ):
        oracle.admissible(["a"])


def test_an_oracle_refuses_a_connection_already_inside_a_transaction():
    in_transaction = FakeConnection(transaction_status=2)
    with pytest.raises(ProbeUnsafe, match="already inside a transaction"):
        SavepointOracle(in_transaction, noop_plan())


def test_the_budget_is_enforced_by_the_savepoint_oracle_itself():
    connection = FakeConnection()
    oracle = SavepointOracle(connection, noop_plan(), budget=1)
    assert oracle.admissible(["a"]) is True
    with pytest.raises(ProbeBudgetExhausted):
        oracle.admissible(["b"])
    assert oracle.calls == 1


def test_a_savepoint_prefix_that_is_not_an_identifier_is_refused():
    # The prefix is interpolated into `SAVEPOINT <name>`, which cannot take a bind
    # parameter. Checking it is what makes the interpolation safe.
    with pytest.raises(ValueError, match="is not an identifier"):
        SavepointOracle(FakeConnection(), noop_plan(), savepoint_prefix="p; DROP TABLE x --")


def test_a_plan_that_raises_while_applying_a_fact_still_rolls_back_its_savepoint():
    connection = FakeConnection()

    def apply(_cursor, _fact):
        raise Refused("23503")

    with probe_transaction(lambda: connection, noop_plan(apply=apply)) as oracle:
        assert oracle.admissible(["a"]) is False
    assert "ROLLBACK TO SAVEPOINT tp_probe_1" in statements(connection)
    assert connection.rolled_back == 1
