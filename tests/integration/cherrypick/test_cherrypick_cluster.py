# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The three propagation claims that only a real CockroachDB can settle.

**This suite never passes by absence.** It skips with a reason in exactly two
situations, and each reason names the thing that was missing: no driver or no
cluster, or the tables not yet existing. ``lesson``, ``propagation``,
``merge_conflict`` and ``resolution_memory`` are migrations ``0094-0097`` and
belong to the data-model lead; the moment they land, this suite starts running for
real with no edit here.

What it settles:

1. **MI23 against the constraint, not against our mirror of it.**
   :class:`~mainline_cherrypick.types.Lesson` refuses to construct a weakening. A
   mirror that has never been checked against the `CHECK` it mirrors is a guess,
   so this inserts one and asserts `23514` on ``only_tightenings_travel``.
2. **The compare-and-set is really a compare-and-set.** CockroachDB has **no
   advisory locks**, so two workers handed the same at-least-once delivery are
   held apart by ``WHERE … AND state = %s`` and nothing else. Running the same
   transition twice must affect one row and then zero.
3. **The grant boundary.** ``agent_fleet`` must hold no ``UPDATE`` on
   ``merge_conflict`` — that absence is one of the four barriers behind *a
   recorded resolution is proposed, never auto-applied*, and it is the only one of
   the four that lives in the database rather than in this package.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _src in (
    _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-cherrypick" / "src",
    _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src",
    _REPO_ROOT / "packages" / "mainline-agentkit" / "src",
    _REPO_ROOT / "packages" / "trappoint-jcs" / "src",
):
    if str(_src) not in sys.path:  # pragma: no cover - import-time bootstrap
        sys.path.insert(0, str(_src))

from mainline_cherrypick import (  # noqa: E402  (after the sys.path bootstrap)
    SCORER_VERSION,
    STATEMENTS,
    UPDATE_PROPAGATION_STATE_SQL,
)

try:  # soft, NOT `importorskip`
    import psycopg
except ImportError:  # pragma: no cover - depends on which extras are installed
    psycopg = None  # type: ignore[assignment]

pytestmark = pytest.mark.requires_cluster

DSN_ENV = ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN")
REQUIRED_TABLES = ("lesson", "propagation", "merge_conflict", "resolution_memory")


def _dsn() -> str | None:
    for name in DSN_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return None


@pytest.fixture(scope="module")
def connection():
    """A live connection, or a skip whose message names what was missing."""
    if psycopg is None:
        pytest.skip("psycopg 3 is required to talk to CockroachDB; `uv sync --extra db`")
    dsn = _dsn()
    if dsn is None:
        pytest.skip(
            f"no cluster: set one of {', '.join(DSN_ENV)}. AWS credentials are not valid "
            f"on this build machine, so a local `cockroach` binary or a container is the "
            f"intended path"
        )
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="module")
def tables(connection):
    """Skip, naming the migration band, until the propagation tables exist."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
             WHERE table_schema = 'mainline' AND table_name = ANY(%s)
            """,
            (list(REQUIRED_TABLES),),
        )
        present = {row[0] for row in cur.fetchall()}
    missing = sorted(set(REQUIRED_TABLES) - present)
    if missing:
        pytest.skip(
            f"migrations 0094-0097 have not landed: mainline.{', mainline.'.join(missing)} "
            f"do not exist. Those tables belong to the data-model lead; this suite runs for "
            f"real the moment they appear, with no edit here"
        )
    return present


def test_a_weakening_is_refused_by_the_database(connection, tables):
    """MI23, against ``CHECK only_tightenings_travel`` itself."""
    assert "lesson" in tables
    with connection.cursor() as cur, pytest.raises(Exception) as excinfo:  # noqa: PT011
        cur.execute(
            """
            INSERT INTO mainline.lesson (
              origin_site, origin_commit, anchor_event, max_severity,
              control_delta, patch_digest, merge_base, envelope
            ) VALUES (
              gen_random_uuid(), %s, gen_random_uuid(), 5,
              'weaken', %s, %s, '{}'::JSONB
            )
            """,
            (b"\xa1" * 32, b"\xb2" * 32, b"\xc3" * 32),
        )
    sqlstate = getattr(excinfo.value, "sqlstate", None)
    assert sqlstate == "23514", f"expected 23514, got {sqlstate}: {excinfo.value}"
    assert "only_tightenings_travel" in str(excinfo.value)


def test_the_state_transition_is_a_compare_and_set(connection, tables):
    """Two deliveries of one transition advance the row once.

    There are no advisory locks in CockroachDB, so this is the whole of the
    mutual exclusion. A second worker replaying an at-least-once delivery must
    match no row rather than re-apply the transition.
    """
    assert "propagation" in tables
    lesson_id, site_id = uuid.uuid4(), uuid.uuid4()
    now = datetime.now(tz=UTC)
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mainline.propagation (
              lesson_id, site_id, state, score, model_version, proposed_at, due_by
            ) VALUES (%s, %s, 'proposed', %s, %s, %s, %s)
            ON CONFLICT (lesson_id, site_id) DO NOTHING
            """,
            (lesson_id, site_id, "0.850", SCORER_VERSION, now, now),
        )
        cur.execute(UPDATE_PROPAGATION_STATE_SQL, ("conflicted", lesson_id, site_id, "proposed"))
        first = cur.fetchall()
        cur.execute(UPDATE_PROPAGATION_STATE_SQL, ("conflicted", lesson_id, site_id, "proposed"))
        second = cur.fetchall()
    assert len(first) == 1
    assert second == []


def test_the_fleet_role_cannot_update_merge_conflict(connection, tables):
    """The barrier that lives in the database rather than in this package."""
    assert "merge_conflict" in tables
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT privilege_type FROM information_schema.role_table_grants
             WHERE table_schema = 'mainline' AND table_name = 'merge_conflict'
               AND grantee = 'agent_fleet'
            """
        )
        granted = {row[0].upper() for row in cur.fetchall()}
    assert "UPDATE" not in granted, (
        f"agent_fleet holds {sorted(granted)} on mainline.merge_conflict. An UPDATE here "
        f"would make 'a recorded resolution is proposed, never auto-applied' a policy "
        f"instead of a privilege"
    )
    assert "DELETE" not in granted


def test_every_emitted_statement_parses_on_the_cluster(connection, tables):
    """`PREPARE` each statement so a column this package names but the DDL lacks fails here."""
    assert tables
    for index, sql in enumerate(STATEMENTS):
        name = f"cherrypick_shape_{index}"
        with connection.cursor() as cur:
            cur.execute(f"PREPARE {name} AS {sql}")
            cur.execute(f"DEALLOCATE {name}")
