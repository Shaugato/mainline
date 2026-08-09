# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""N gate workers, one subject, one merge. And a count of who saw what.

This is the crudest test in the domain and one of the most load-bearing. Fire N merges of
the same permit at once and assert the database produced **exactly one** ``merge_record``
row and **exactly one** ``permit_event`` at that ``seq``. Not "at most one" — a race that
produced zero would mean every worker lost, which is a liveness failure and equally a bug.

``N = 8`` on every push and ``N = 64`` nightly. The two numbers test different things: at
8 the contention is a handful of retries, and at 64 the retry budget itself is under
pressure and a client that retried a refusal would show up as a second ``merge_record``
attempt in the ledger.

**The refusal census is the deliverable, not a diagnostic.** Every losing attempt is
recorded by SQLSTATE, printed, and asserted to lie inside the taxonomy. Which code a loser
sees is a fact about the mechanism that beat it:

``40001``
    two gate transactions conflicted and CockroachDB refused to serialise them. The
    caller's discipline is to retry — see ``test_retry_taxonomy_spy.py``.
``23505``
    a loser reached ``merge_record`` after the winner committed and met
    ``merge_record_pkey``, or reached ``permit_event`` and met ``linear``. Structural.
``23503``
    a loser read ``state = 'merged'`` and the edge merged → merged is not in
    ``subject_transition``. Refusal by data.
``P0001``
    the compare-and-swap in step 8 matched no row: the head moved under the transaction.

Every one of those is a correct answer. A census that came back with something *else* is
the finding, which is why the census is asserted rather than logged.

**WHAT THE CENSUS ACTUALLY SAYS ON v26.2.5 (measured 2026-08-09, N ∈ {8, 16, 32}).**
Every trial returned one winner and (N - 1) x ``23503`` on ``legal_edge``. No ``40001``.
No ``23505``. The reason is step 1 of ``merge_permit``: ``SELECT … FOR UPDATE`` on the
subject row orders the callers into a queue, so each loser reads ``state = 'merged'``
after the winner commits and is refused by the transition table rather than by a
serialisation conflict.

Three things follow and all three are stated rather than assumed:

* The lock anchor is doing what its comment says — *"lock ordering and retry-thrash
  reduction only, never correctness"* — and the retry budget in ``trappoint-core`` is not
  under pressure at these N.
* ``merge_record_pkey`` (case CF-09) is a **structural backstop that this race does not
  reach**. Its depth is proved by the unwelding matrix, which is where that claim belongs;
  this lane must not be cited as evidence for it.
* The census is therefore RECORDED, and what is ASSERTED is what holds regardless of how
  the platform schedules: one completion record, one merge event, one winner, every code
  inside the taxonomy, every refusal carrying an exhibit, and no loser refused by the
  counter.
"""

from __future__ import annotations

import os
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import psycopg
import pytest

# Module-level `importorskip`, and it belongs HERE rather than in the conftest: a skip
# raised while a conftest is imported applies to the whole directory, and
# `tests/concurrency/` also holds the custody and recall lanes, which do not depend on
# this package. Raised here it reaches exactly this module.
pytest.importorskip(
    "trappoint_model",
    reason=(
        "the kernel concurrency lane drives the gate through `trappoint-model`; "
        "`uv sync --package trappoint-model` installs it. A SKIP IS NOT EVIDENCE."
    ),
)

from trappoint_model.adapter import Adapter
from trappoint_model.invariants import check_all
from trappoint_model.model import Accept, Refuse
from trappoint_model.programs import merge_program
from trappoint_model.refschema import SCHEMA, Fixture

pytestmark = [pytest.mark.requires_cluster, pytest.mark.slow]

CI_WORKERS = 8
NIGHTLY_WORKERS = 64
TAXONOMY = frozenset({"40001", "23514", "23503", "23505", "P0001"})

#: What each losing code MEANS on this path. A census entry with no explanation is the
#: finding: it is a mechanism refusing a merge for a reason this lane never modelled.
LOSER_EXPLANATIONS: dict[str, str] = {
    "40001": "two gate transactions conflicted; the caller's discipline is to retry",
    "23503": "the winner committed first and merged → merged is not a legal edge",
    "23505": "a loser reached merge_record or the event chain after the winner committed",
    "P0001": "the compare-and-swap in step 8 matched no row: the head moved",
}


def _cleared_subject(conn: Any, fixture: Fixture) -> uuid.UUID:
    """A subject in ``dispositioned`` with zero open obligations: one step from merged."""
    adapter = Adapter(conn, fixture)
    sid, cid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert isinstance(adapter.create_subject(sid), Accept)
    assert isinstance(adapter.materialise_check(sid, cid), Accept)
    assert isinstance(adapter.sign_disposition(cid, did), Accept)
    return sid


def _one_attempt(dsn: str, subject: uuid.UUID, fixture: Fixture) -> str:
    """One worker's single, unretried attempt. Returns the SQLSTATE, or ``00000`` on success.

    **Deliberately unretried.** This test measures what the DATABASE did when N callers
    arrived at once; a retry loop here would convert a refusal into a later success and
    the census would measure the loop instead. The retry discipline is asserted separately
    and directly, in ``test_retry_taxonomy_spy.py``.
    """
    statement = merge_program(subject, fixture)[0]
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("SET default_transaction_isolation = 'serializable'")
        conn.execute("SET statement_timeout = '30s'")
        try:
            conn.execute(statement.sql, statement.params)
        except psycopg.Error as exc:
            return exc.sqlstate or "unknown"
    return "00000"


def _race(dsn: str, subject: uuid.UUID, fixture: Fixture, workers: int) -> Counter[str]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one_attempt, dsn, subject, fixture) for _ in range(workers)]
        return Counter(future.result() for future in futures)


def _assert_exactly_one_merge(
    conn: Any, subject: uuid.UUID, census: Counter[str], workers: int
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) FROM {SCHEMA}.merge_record WHERE subject_id = %s",  # noqa: S608
            (subject,),
        )
        records = cur.fetchone()[0]
        cur.execute(
            f"SELECT count(*) FROM {SCHEMA}.permit_event "  # noqa: S608
            "WHERE permit_id = %s AND to_state = 'merged'",
            (subject,),
        )
        events = cur.fetchone()[0]
        cur.execute(f"SELECT state, head_seq FROM {SCHEMA}.permit WHERE permit_id = %s", (subject,))  # noqa: S608
        state, head = cur.fetchone()

    report = (
        f"\nN={workers} · census {dict(census)} · merge_record={records} · "
        f"permit_event(to merged)={events} · permit=({state}, head_seq={head})"
    )
    assert records == 1, f"expected exactly one completion record, found {records}.{report}"
    assert events == 1, f"expected exactly one merge event, found {events}.{report}"
    assert census["00000"] == 1, (
        f"expected exactly one winner, {census['00000']} reported success.{report}"
    )
    unmodelled = sorted(set(census) - TAXONOMY - {"00000"})
    assert not unmodelled, (
        f"losing attempts saw {unmodelled}, which is outside the refusal taxonomy — the "
        f"database refused for a reason nobody modelled.{report}"
    )
    violations, _ = check_all(conn)
    assert not violations, "conservation broken by the race:\n" + "\n".join(
        str(v) for v in violations
    )
    print(report)


@pytest.mark.timeout(600)
def test_eight_parallel_merges_produce_exactly_one_merge_record(
    kernel_schema: Any, kernel_conn: Any, kernel_fixture: Fixture
) -> None:
    """Every push. Eight callers, one subject, one completion record."""
    subject = _cleared_subject(kernel_conn, kernel_fixture)
    census = _race(kernel_schema.dsn, subject, kernel_fixture, CI_WORKERS)
    _assert_exactly_one_merge(kernel_conn, subject, census, CI_WORKERS)


@pytest.mark.timeout(1800)
@pytest.mark.skipif(
    os.environ.get("TRAPPOINT_NIGHTLY") != "1",
    reason=(
        "N=64 is the nightly arm: set TRAPPOINT_NIGHTLY=1. It is skipped rather than "
        "scaled down because a 64-way race that quietly ran 8-way would report a "
        "contention level nobody measured."
    ),
)
def test_sixty_four_parallel_merges_produce_exactly_one_merge_record(
    kernel_schema: Any, kernel_conn: Any, kernel_fixture: Fixture
) -> None:
    """Nightly. Sixty-four callers, one subject, one completion record."""
    subject = _cleared_subject(kernel_conn, kernel_fixture)
    census = _race(kernel_schema.dsn, subject, kernel_fixture, NIGHTLY_WORKERS)
    _assert_exactly_one_merge(kernel_conn, subject, census, NIGHTLY_WORKERS)


@pytest.mark.timeout(600)
def test_the_census_is_explained_and_the_counter_refused_nobody(
    kernel_schema: Any, kernel_conn: Any, kernel_fixture: Fixture
) -> None:
    """Record the 40001-versus-23505 tally, and assert what holds however it comes out.

    Two assertions, and neither depends on how CockroachDB chose to schedule the callers:

    * **Every losing code has a stated meaning.** A code with no entry in
      :data:`LOSER_EXPLANATIONS` is a mechanism refusing a merge for a reason this lane
      never modelled, which is a finding rather than an edge case.
    * **No loser was refused by the counter.** The subject entered the race with zero open
      obligations, so a ``23514`` on ``gate_closed_when_issued`` would mean
      ``open_blocking`` moved while nothing materialised an obligation — a projection
      writing a value no obligation justifies, which is the one direction of counter error
      that could also go the other way and open the gate.
    """
    subject = _cleared_subject(kernel_conn, kernel_fixture)
    census = _race(kernel_schema.dsn, subject, kernel_fixture, CI_WORKERS)
    losers = {code: n for code, n in census.items() if code != "00000"}

    print(
        f"\n[census N={CI_WORKERS}] "
        + " | ".join(f"{code} x{n}" for code, n in sorted(losers.items()))
        + f"  (40001={census['40001']}, 23505={census['23505']})"
    )

    unexplained = sorted(set(losers) - set(LOSER_EXPLANATIONS))
    assert not unexplained, (
        f"losing attempts saw {unexplained}, which this lane has no explanation for. "
        f"Full census: {dict(census)}"
    )
    assert census["23514"] == 0, (
        f"{census['23514']} attempt(s) were refused by gate_closed_when_issued, but the "
        "subject entered the race with zero open obligations. The projected counter moved "
        "without an obligation to justify it."
    )


@pytest.mark.timeout(300)
def test_the_loser_carries_an_exhibit(
    kernel_schema: Any, kernel_conn: Any, kernel_fixture: Fixture
) -> None:
    """Every refusal a loser saw names the mechanism that produced it.

    ``40001`` is exempt and that is the contract, not an oversight: an undecided
    transaction is not a refusal and has no reason set (``spec/errors.md`` §5).
    """
    subject = _cleared_subject(kernel_conn, kernel_fixture)
    statement = merge_program(subject, kernel_fixture)[0]
    exhibits: list[Refuse] = []

    def attempt() -> None:
        from trappoint_model.adapter import verdict_of

        with psycopg.connect(kernel_schema.dsn, autocommit=True) as conn:
            conn.execute("SET default_transaction_isolation = 'serializable'")
            try:
                conn.execute(statement.sql, statement.params)
            except psycopg.Error as exc:
                exhibits.append(verdict_of(exc))

    with ThreadPoolExecutor(max_workers=CI_WORKERS) as pool:
        for future in [pool.submit(attempt) for _ in range(CI_WORKERS)]:
            future.result()

    unnamed = [r for r in exhibits if r.sqlstate != "40001" and not r.constraint]
    assert not unnamed, (
        f"{len(unnamed)} refusal(s) carried no exhibit: {unnamed}. The constraint name is "
        "the courtroom exhibit; a refusal without one is an exception, not a decision."
    )
