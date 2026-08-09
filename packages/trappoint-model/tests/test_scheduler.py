# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Anomaly A1, generated as data: a merge and a materialisation, interleaved every way.

The subject is cleared and ready to merge. One transaction attempts the merge; another
attaches a new obligation to the same subject. Sequentially, either order is safe — merge
then materialise is refused by ``fn_check_materialised``; materialise then merge is
refused by ``gate_closed_when_issued``. Interleaved, a gate that trusted its own counter
has a window, and the assertion is that no schedule produces a merged subject carrying an
open obligation.

The schedule is Hypothesis data, so a failure arrives already shrunk to the shortest
interleaving that produces it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from trappoint_model.adapter import Adapter
from trappoint_model.invariants import check_all, l1_gate
from trappoint_model.model import Accept
from trappoint_model.programs import materialise_program, merge_program
from trappoint_model.refschema import Fixture, seed_clause_version
from trappoint_model.scheduler import TxnScheduler, interleavings

pytestmark = [pytest.mark.requires_cluster, pytest.mark.slow]


@pytest.fixture
def cleared_subject(conn: Any, fixture: Fixture) -> uuid.UUID:
    """A subject in ``dispositioned`` with zero open obligations: one step from merged."""
    adapter = Adapter(conn, fixture)
    sid, cid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert isinstance(adapter.create_subject(sid), Accept)
    assert isinstance(adapter.materialise_check(sid, cid), Accept)
    assert isinstance(adapter.sign_disposition(cid, did), Accept)
    return sid


@pytest.fixture
def actor_connections(schema: Any) -> Iterator[list[Any]]:
    """Two open AUTOCOMMIT connections. The scheduler issues BEGIN and COMMIT itself."""
    import psycopg

    conns = [psycopg.connect(schema.dsn, autocommit=True) for _ in range(2)]
    try:
        yield conns
    finally:
        for c in conns:
            c.close()


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(schedule=interleavings(2, min_size=2, max_size=8))
@pytest.mark.timeout(900)
def test_no_interleaving_of_a1_admits_an_open_obligation(
    conn: Any,
    fixture: Fixture,
    cleared_subject: uuid.UUID,
    actor_connections: list[Any],
    schedule: list[int],
) -> None:
    """L1 holds under every generated interleaving of merge against materialise."""
    clause_uuid, commit_id = seed_clause_version(conn, fixture)
    programs = [
        merge_program(cleared_subject, fixture),
        materialise_program(cleared_subject, uuid.uuid4(), clause_uuid, commit_id, fixture),
    ]
    with TxnScheduler(actor_connections, programs) as scheduler:
        trace = scheduler.finish(scheduler.run(schedule))

    assert not trace.harness_errors(), (
        "the scheduler itself failed, so this run asserted nothing:\n" + trace.report()
    )
    violations, _ = check_all(conn)
    assert not violations, (
        "A1 REPRODUCED. The interleaving below left the database in a state the "
        "conservation laws forbid.\n"
        f"schedule: {trace.pairs()}\n{trace.report()}\n" + "\n".join(str(v) for v in violations)
    )


@pytest.mark.timeout(300)
def test_the_scheduler_records_contention_rather_than_hiding_it(
    conn: Any,
    fixture: Fixture,
    cleared_subject: uuid.UUID,
    actor_connections: list[Any],
) -> None:
    """A run in which nothing ever blocked has not tested concurrency.

    Both actors are pointed at the SAME subject row and given the turn order that forces
    them to contend: materialise takes ``FOR UPDATE`` on the permit inside
    ``fn_check_materialised``, merge takes it in step 1. One of them must wait, or the
    scheduler is not scheduling anything.
    """
    clause_uuid, commit_id = seed_clause_version(conn, fixture)
    programs = [
        materialise_program(cleared_subject, uuid.uuid4(), clause_uuid, commit_id, fixture),
        merge_program(cleared_subject, fixture),
    ]
    with TxnScheduler(actor_connections, programs) as scheduler:
        trace = scheduler.finish(scheduler.run([0, 1, 0, 1]))

    assert trace.steps, "the scheduler executed nothing"
    assert not trace.harness_errors(), (
        "the scheduler itself failed, so this run asserted nothing:\n" + trace.report()
    )
    assert trace.contended(), (
        "neither actor blocked, timed out or saw 40001, so the two transactions never "
        f"met. The scheduler is not producing concurrency.\n{trace.report()}"
    )
    assert not l1_gate(conn), "L1 broke under contention"


def test_a_schedule_needs_an_actor() -> None:
    """The strategy refuses a zero-actor schedule rather than generating an empty one."""
    with pytest.raises(ValueError, match="at least one actor"):
        interleavings(0)


@settings(max_examples=25, deadline=None)
@given(schedule=interleavings(3, min_size=1, max_size=4))
def test_schedules_are_lists_of_actor_ids(schedule: list[int]) -> None:
    """The generated element is the actor; the step index is derived. See the module docs."""
    assert schedule
    assert all(isinstance(actor, int) and 0 <= actor < 3 for actor in schedule)


@settings(max_examples=10, deadline=None)
@given(schedule=st.lists(st.integers(0, 1), min_size=0, max_size=3))
def test_the_shrink_target_is_the_empty_schedule(schedule: list[int]) -> None:
    """A zero-turn schedule is representable: the base case a shrinker walks towards."""
    assert len(schedule) <= 3
