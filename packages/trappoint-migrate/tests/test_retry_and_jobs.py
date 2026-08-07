# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The retry loop and the job wait, tested against fakes rather than a cluster.

`spec/errors.md` §4 makes attempt-once a property of the product, for an evidentiary
reason rather than a performance one: if a client retries a `23514`, the refusal ledger
holds five identical refusals for one attempted history and the count of refusals stops
being a count of anything. So "retries 40001, and retries nothing else" is not a detail
to be asserted by reading the code — it gets a spy.
"""

from __future__ import annotations

import random
from typing import Any

import psycopg
import pytest

from trappoint_migrate import db
from trappoint_migrate.errors import SchemaJobFailed


class _Txn:
    def __enter__(self) -> _Txn:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class FakeConn:
    """Just enough connection to drive `in_txn`."""

    def __init__(self) -> None:
        self.transactions = 0

    def transaction(self) -> _Txn:
        self.transactions += 1
        return _Txn()


def _serialization_failure() -> psycopg.errors.SerializationFailure:
    return psycopg.errors.SerializationFailure("restart transaction: TransactionRetryError")


def test_forty_thousand_and_one_is_retried_until_it_succeeds() -> None:
    conn = FakeConn()
    attempts = {"n": 0}
    slept: list[float] = []

    def body(_: Any) -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _serialization_failure()
        return "committed"

    result = db.in_txn(
        conn,  # type: ignore[arg-type]
        body,
        rng=random.Random(7),
        sleep=slept.append,
    )
    assert result == "committed"
    assert attempts["n"] == 3
    assert len(slept) == 2, "one backoff per retry, and none after the successful attempt"


def test_backoff_is_capped_and_fully_jittered() -> None:
    conn = FakeConn()
    slept: list[float] = []

    def body(_: Any) -> None:
        raise _serialization_failure()

    with pytest.raises(psycopg.errors.SerializationFailure):
        db.in_txn(conn, body, attempts=8, rng=random.Random(1), sleep=slept.append)

    assert len(slept) == 7
    # Full jitter: every delay is drawn from U(0, ceiling), so none may exceed the cap
    # and they must not be monotone (that would be equal jitter, which does not break a
    # synchronised herd on the first retry).
    assert all(0.0 <= s <= 2.0 for s in slept)
    assert slept != sorted(slept)


def test_a_refusal_is_not_retried() -> None:
    conn = FakeConn()
    calls = {"n": 0}

    def body(_: Any) -> None:
        calls["n"] += 1
        raise psycopg.errors.CheckViolation("gate_closed_when_issued")

    with pytest.raises(psycopg.errors.CheckViolation):
        db.in_txn(conn, body, rng=random.Random(0), sleep=lambda _: None)
    assert calls["n"] == 1, "23514 is a decision; retrying it would corrupt the refusal count"


def test_a_unique_violation_is_not_retried() -> None:
    # The attestation chain's CAS loser gets 23505. Retrying it would silently hide the
    # fact that two migration streams were running against one cluster.
    conn = FakeConn()
    calls = {"n": 0}

    def body(_: Any) -> None:
        calls["n"] += 1
        raise psycopg.errors.UniqueViolation("attestation_chain_linear")

    with pytest.raises(psycopg.errors.UniqueViolation):
        db.in_txn(conn, body, rng=random.Random(0), sleep=lambda _: None)
    assert calls["n"] == 1


class FakeJobsConn:
    """A connection whose `SHOW JOBS` returns a scripted sequence of snapshots."""

    def __init__(self, snapshots: list[list[dict[str, Any]]]) -> None:
        self.snapshots = snapshots
        self.reads = 0

    def cursor(self, row_factory: Any = None) -> FakeJobsConn:  # noqa: ARG002
        return self

    def __enter__(self) -> FakeJobsConn:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, *_: Any, **__: Any) -> None:
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        index = min(self.reads, len(self.snapshots) - 1)
        self.reads += 1
        return self.snapshots[index]


def _job(job_id: str, status: str, error: str = "") -> dict[str, Any]:
    return {
        "job_id": job_id,
        "job_type": "SCHEMA CHANGE",
        "status": status,
        "description": "ALTER TABLE …",
        "error": error,
    }


def test_the_version_waits_for_the_job_not_the_statement() -> None:
    conn = FakeJobsConn(
        [
            [_job("1", "running")],
            [_job("1", "running")],
            [_job("1", "succeeded")],
        ]
    )
    slept: list[float] = []
    ids = db.wait_for_schema_jobs(
        conn,  # type: ignore[arg-type]
        since=None,
        sleep=slept.append,
    )
    assert ids == ("1",)
    assert len(slept) == 2


def test_a_failed_job_stops_the_run_and_carries_the_error() -> None:
    conn = FakeJobsConn([[_job("9", "failed", "relation already exists")]])
    with pytest.raises(SchemaJobFailed, match="relation already exists"):
        db.wait_for_schema_jobs(conn, since=None, sleep=lambda _: None)  # type: ignore[arg-type]


def test_a_reverting_job_is_terminal_failure() -> None:
    # A job that has begun reverting has already decided it will not succeed. Waiting
    # politely for it to finish reverting waits to be told something already known.
    conn = FakeJobsConn([[_job("9", "reverting")]])
    with pytest.raises(SchemaJobFailed):
        db.wait_for_schema_jobs(conn, since=None, sleep=lambda _: None)  # type: ignore[arg-type]


def test_timeout_refuses_to_advance_the_version() -> None:
    conn = FakeJobsConn([[_job("1", "running")]])
    clock = {"t": 0.0}

    def now() -> float:
        clock["t"] += 1.0
        return clock["t"]

    with pytest.raises(SchemaJobFailed, match="NOT advanced"):
        db.wait_for_schema_jobs(
            conn,  # type: ignore[arg-type]
            since=None,
            timeout_s=2.0,
            sleep=lambda _: None,
            now=now,
        )


def test_status_column_name_drift_is_tolerated() -> None:
    # `SHOW JOBS` is an observability surface, not a stable API; its columns have moved
    # between releases. Reading by name with fallbacks beats asserting a shape.
    conn = FakeJobsConn([[{"job_id": "4", "job_type": "SCHEMA CHANGE", "job_status": "succeeded"}]])
    assert db.wait_for_schema_jobs(conn, since=None, sleep=lambda _: None) == ("4",)  # type: ignore[arg-type]
