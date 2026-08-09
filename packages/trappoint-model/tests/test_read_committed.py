# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The isolation-downgrade differential: the same histories, one level weaker.

``ARCHITECTURE.md`` §5.11 says the projected counter is a **materialised conflict**, and
§4.1 law 3 draws the consequence: the gate is welded by a plain-column CHECK over a
scalar that a trigger wrote, so it does not depend on the isolation level to hold. That
is an architectural assertion. This file is the cheapest way to convert it into evidence.

Run the identical generated histories with ``SET default_transaction_isolation = 'read
committed'`` and assert **L1 still holds** and the oracle still agrees. If the claim were
false, this is where it would break first: READ COMMITTED permits the read skew that a
gate depending on serialization order would need protection from.

**What a green run here does and does not prove.** It proves the *sequential* histories
the machine generates are refused identically at both levels — which is what the
materialised-conflict claim is about, since the conflict is materialised on a row that
every writer must update. It does not prove anything about concurrent interleavings at
READ COMMITTED; that is :mod:`~trappoint_model.scheduler`'s job and
``tests/concurrency/`` runs it at both levels. Saying so is not hedging: a claim that
overreaches its evidence is the thing this whole domain exists to make impossible.

**A MEASURED LIMIT, stated because it bounds the claim.** ``cluster_logical_timestamp()``
raises ``0A000 unsupported in READ COMMITTED isolation`` on CockroachDB v26.2.5 (measured
2026-08-09; :func:`test_the_measured_platform_limit_still_holds` re-measures it every
run). Two consequences:

* The blame closure cannot be seeded on the downgraded connection, because
  ``fn_closure_guard`` records the closure in the custody ledger in the same transaction
  using that builtin. Authority-source seeding therefore runs on a second, SERIALIZABLE
  connection — it is fixture setup, not the gate.
* **MAINLINE's own ``merge_permit`` calls it too**, in step 7's ledger intake. So on the
  MAINLINE binding a merge at READ COMMITTED is refused by the *ledger's clock* before
  the gate is reached, and this differential's evidence is for the reference vertical,
  where step 7 is not rendered. That is a statement about what has been proved, not a
  hedge: the materialised-conflict claim is about the gate, and the gate is what is run
  here.

Nightly, not per-push: it doubles the differential's cluster time and the SERIALIZABLE
run is the one that gates a merge.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from hypothesis import settings
from hypothesis.stateful import run_state_machine_as_test
from trappoint_model.machine import make_machine
from trappoint_model.refschema import Fixture

pytestmark = [pytest.mark.requires_cluster, pytest.mark.slow]


@pytest.fixture
def read_committed_conn(conn: Any) -> Any:
    """The same connection, downgraded — explicitly, and asserted rather than assumed."""
    conn.execute("SET default_transaction_isolation = 'read committed'")
    observed = conn.execute("SHOW transaction_isolation").fetchone()
    assert observed is not None, "SHOW transaction_isolation returned no row"
    assert "read committed" in str(observed[0]).lower(), (
        f"the session reports isolation {observed[0]!r}; the downgrade differential is "
        "only evidence if the downgrade actually happened"
    )
    return conn


@pytest.fixture
def serializable_setup_conn(schema: Any) -> Iterator[Any]:
    """A second connection, at SERIALIZABLE, for authority-source seeding only."""
    connection = psycopg.connect(schema.dsn, autocommit=True)
    connection.execute("SET default_transaction_isolation = 'serializable'")
    try:
        yield connection
    finally:
        connection.close()


def test_the_measured_platform_limit_still_holds(read_committed_conn: Any) -> None:
    """Re-measure the limit that shapes this file, every run.

    Written to FAIL on the good news. The day ``cluster_logical_timestamp()`` works under
    READ COMMITTED, this test fails, the separate seeding connection becomes unnecessary,
    and the MAINLINE binding becomes testable at READ COMMITTED end to end. A comment
    recording a platform limit rots; a test recording one does not.
    """
    with pytest.raises(psycopg.errors.FeatureNotSupported) as raised:
        read_committed_conn.execute("SELECT cluster_logical_timestamp()")
    assert raised.value.sqlstate == "0A000"


@pytest.mark.timeout(1800)
def test_gate_agrees_with_the_oracle_at_read_committed(
    read_committed_conn: Any, serializable_setup_conn: Any, fixture: Fixture
) -> None:
    """L1 survives the downgrade, and so does every exhibit."""
    run_state_machine_as_test(
        make_machine(read_committed_conn, fixture, serializable_setup_conn),
        settings=settings(settings.default, print_blob=True),
    )
