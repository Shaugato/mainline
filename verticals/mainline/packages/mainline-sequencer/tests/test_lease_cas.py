# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The lease protocol, asserted on the wire rather than on a live cluster.

These tests drive an in-process double that records every statement and every parameter.
That is deliberate: the property under test is the *shape of the compare-and-swap* — the
epoch fence, the `+ 1`, the zero-row reading — and a live cluster would confirm the
outcome while leaving the shape unasserted. The database-level behaviour (two sequencers,
one winner) is proven against a real single-node CockroachDB in
`tests/concurrency/custody/test_sequencer_cas.py`.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from mainline_sequencer import lease

NOW = datetime(2026, 8, 4, 12, 0, 0, tzinfo=UTC)
SITE = "blk-07"


class FakeCursor:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self.rows: list[tuple] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params=None) -> None:
        self.conn.calls.append((sql, params))
        self.rows = self.conn.answer(sql, params)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    @property
    def rowcount(self) -> int:
        return len(self.rows)


class FakeConn:
    """Records statements, replays scripted answers. No SQL is parsed or executed."""

    def __init__(self, answers: dict[str, list[tuple]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, object]] = []

    def answer(self, sql: str, _params) -> list[tuple]:
        for marker, rows in self.answers.items():
            if marker in sql:
                return rows
        return []

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    @contextmanager
    def transaction(self):
        yield self


def _observe_row(holder: str, epoch: int, *, expired: bool) -> tuple:
    return (holder, epoch, NOW + timedelta(seconds=60), expired)


# ── The shape of the statement is itself an assertion ──────────────────────────────────


def test_the_epoch_fence_is_in_the_acquire_predicate() -> None:
    """Migration 0079 makes `epoch = $observed_epoch` part of the CAS predicate.

    Without it, two invocations presenting the SAME holder id — a warm container invoked
    twice, a retry after a client timeout — both match the `holder = $me` disjunct and
    both believe they won the election. The fence is what makes a stale holder lose even
    when its clock is wrong, and a "simplification" that drops it looks equivalent and is
    not.
    """
    normalised = " ".join(lease.ACQUIRE_SQL.split())
    assert "AND epoch = %s" in normalised
    assert "AND (holder = %s OR expires_at < now())" in normalised
    assert "RETURNING holder, epoch, expires_at" in normalised


def test_lease_sql_never_touches_a_ledger_table() -> None:
    """The one mutable object in the custody plane is the lease, and only the lease."""
    for statement in (lease.OBSERVE_SQL, lease.ACQUIRE_SQL, lease.RELEASE_SQL):
        assert "mainline_ops.sequencer_lease" in statement
        assert "ledger_" not in statement


def test_expiry_is_decided_by_the_database_clock() -> None:
    """`expires_at < now()` is evaluated server-side and returned as a column.

    A Lambda whose clock has drifted must not be able to declare a live lease dead, so
    the comparison is never made in Python.
    """
    assert "expires_at < now() AS expired" in lease.OBSERVE_SQL


# ── Behaviour ──────────────────────────────────────────────────────────────────────────


def test_observe_raises_when_the_site_has_no_lease_row() -> None:
    conn = FakeConn({"FROM mainline_ops.sequencer_lease": []})
    with pytest.raises(lease.LeaseRowMissing) as caught:
        lease.observe(conn, site_code=SITE)
    assert "provisioning path" in str(caught.value)


def test_acquire_swaps_the_observed_epoch_plus_one() -> None:
    conn = FakeConn(
        {
            "FROM mainline_ops.sequencer_lease": [_observe_row("other", 41, expired=True)],
            "UPDATE mainline_ops.sequencer_lease": [("me", 42, NOW + timedelta(seconds=60))],
        }
    )
    held = lease.acquire(conn, site_code=SITE, holder="me", ttl_seconds=60)

    assert held is not None
    assert held.epoch == 42
    assert held.holder == "me"

    _observe_sql, observe_params = conn.calls[0]
    acquire_sql, acquire_params = conn.calls[1]
    assert observe_params == (SITE,)
    assert "UPDATE mainline_ops.sequencer_lease" in acquire_sql
    # holder, new epoch, ttl, site, OBSERVED epoch, holder
    assert acquire_params == ("me", 42, timedelta(seconds=60), SITE, 41, "me")


def test_acquire_returns_none_when_another_holder_wins() -> None:
    """Zero rows updated means somebody else holds it. That is the entire protocol.

    `None` is an ordinary outcome and the caller stands down for one 15-second tick. A
    loser that retried inside the same invocation would be the second writer the lease
    exists to prevent.
    """
    conn = FakeConn(
        {
            "FROM mainline_ops.sequencer_lease": [_observe_row("other", 7, expired=False)],
            "UPDATE mainline_ops.sequencer_lease": [],
        }
    )
    assert lease.acquire(conn, site_code=SITE, holder="me") is None


@pytest.mark.parametrize(
    ("holder", "ttl", "fragment"),
    [("", 60, "non-empty opaque identity"), ("me", 0, "positive"), ("me", -1, "positive")],
)
def test_acquire_refuses_a_lease_that_could_not_be_told_apart(holder, ttl, fragment) -> None:
    conn = FakeConn({})
    with pytest.raises(ValueError, match=fragment):
        lease.acquire(conn, site_code=SITE, holder=holder, ttl_seconds=ttl)
    assert conn.calls == [], "the argument check must precede the round trip"


def test_release_reports_whether_this_holder_still_held_it() -> None:
    held = lease.Lease(site_code=SITE, holder="me", epoch=42, expires_at=NOW)

    won = FakeConn({"UPDATE mainline_ops.sequencer_lease": [("row",)]})
    assert lease.release(won, held) is True
    assert won.calls[0][1] == (SITE, 42, "me")

    moved_on = FakeConn({"UPDATE mainline_ops.sequencer_lease": []})
    assert lease.release(moved_on, held) is False


# ── contend: the difference between "somebody else won" and "we do not know" ───────────


class FlakyConn(FakeConn):
    """A connection whose transactions fail with 40001 a scripted number of times."""

    def __init__(self, answers, failures: int) -> None:
        super().__init__(answers)
        self.remaining = failures
        self.transactions = 0

    @contextmanager
    def transaction(self):
        self.transactions += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise psycopg.errors.SerializationFailure("restart transaction: WriteTooOldError")
        yield self


def test_an_undecided_election_is_retried_and_a_lost_one_is_not() -> None:
    """MEASURED on v26.2.5: sixteen contenders produce ``40001``, not a zero-row result.

    The two outcomes look alike from outside and are entirely different facts. A ``40001``
    swallowed as a lost election would leave a site unsequenced for a tick while every
    contender believed it had lost; a lost election retried would be a second writer
    trying again.
    """
    conn = FlakyConn(
        {
            "FROM mainline_ops.sequencer_lease": [_observe_row("other", 3, expired=True)],
            "UPDATE mainline_ops.sequencer_lease": [("me", 4, NOW)],
        },
        failures=3,
    )
    held = lease.contend(conn, site_code=SITE, holder="me", sleep=lambda _s: None)
    assert held is not None
    assert held.epoch == 4
    assert conn.transactions == 4, "three undecided attempts, then one that decided"


def test_a_lost_election_returns_none_without_retrying() -> None:
    conn = FlakyConn(
        {
            "FROM mainline_ops.sequencer_lease": [_observe_row("other", 3, expired=False)],
            "UPDATE mainline_ops.sequencer_lease": [],
        },
        failures=0,
    )
    assert lease.contend(conn, site_code=SITE, holder="me", sleep=lambda _s: None) is None
    assert conn.transactions == 1


def test_contend_gives_up_rather_than_looping_forever() -> None:
    conn = FlakyConn({}, failures=lease.MAX_CONTEND_ATTEMPTS)
    slept: list[float] = []
    with pytest.raises(psycopg.errors.SerializationFailure):
        lease.contend(conn, site_code=SITE, holder="me", sleep=slept.append)
    assert conn.transactions == lease.MAX_CONTEND_ATTEMPTS
    assert len(slept) == lease.MAX_CONTEND_ATTEMPTS - 1, "no sleep after the final attempt"


def test_a_missing_lease_row_is_not_retried() -> None:
    """A provisioning fault reports immediately; retrying only makes it take longer."""
    conn = FlakyConn({"FROM mainline_ops.sequencer_lease": []}, failures=0)
    with pytest.raises(lease.LeaseRowMissing):
        lease.contend(conn, site_code=SITE, holder="me", sleep=lambda _s: None)
    assert conn.transactions == 1


def test_release_does_not_bump_the_epoch() -> None:
    """Release expires the lease in place.

    Bumping here would produce an epoch nobody ever held — harmless, and it would make the
    epoch a poor forensic record of how many elections a site has actually had.
    """
    normalised = " ".join(lease.RELEASE_SQL.split())
    assert "SET expires_at = now()" in normalised
    assert "epoch =" not in normalised.split("WHERE")[0]
