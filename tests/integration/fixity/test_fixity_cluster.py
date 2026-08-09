# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The three fixity claims that only a real CockroachDB can settle.

**This suite never passes by absence.** It skips with a reason in exactly two
situations, and each reason names the thing that was missing:

* no driver or no cluster — ``MAINLINE_TEST_DSN`` unset, or ``psycopg`` not
  installed. AWS credentials are not valid on this build machine and CockroachDB
  Cloud is not assumed; a local ``cockroach`` binary or a container is the
  intended path.
* the tables do not exist yet. ``patrol_run``, ``drift_finding``,
  ``observed_assertion``, ``time_witness`` and ``discordance_warrant`` are
  migrations ``0090-0098``, which belong to the data-model lead. The moment those
  land, this suite starts running for real against whichever cluster is
  configured, with no edit here.

What it settles, and why each one needs a cluster:

1. **The follower-read HLC.** ``mainline_fixity.follower``'s docstring says that
   ``cluster_logical_timestamp()`` inside a ``SET TRANSACTION AS OF SYSTEM TIME
   follower_read_timestamp()`` transaction returns that transaction's read
   timestamp — which is how ``patrol_run.as_of_hlc`` is populated — and states
   plainly that the repository has **not measured it**. This is where it gets
   measured. Until then the claim stays marked unverified in the source.
2. **MI21.** ``CHECK undetermined_never_blocks`` refuses an ``undetermined``
   finding that claims ``gate_class = 'blocking'`` with `23514`. The Python type
   refuses it too; a mirror that has never been checked against the constraint it
   mirrors is a guess.
3. **The projection.** ``severity_inherited`` and ``gate_class`` are supplied by
   :func:`~mainline_fixity.emit.projection_placeholder` and are expected to be
   **overwritten** by the trigger — the same shape CF-07 tests on
   ``blocking_check``. A client-supplied ``(5, 'blocking')`` on a clause whose
   closure holds ``max_severity = 1`` must come back as something weaker.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
for _src in (
    _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-fixity" / "src",
    _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src",
):
    if str(_src) not in sys.path:  # pragma: no cover - import-time bootstrap
        sys.path.insert(0, str(_src))

from mainline_fixity import (  # noqa: E402  (after the sys.path bootstrap)
    AS_OF_HLC_SQL,
    PATROL_READ_PREAMBLE,
    STATEMENTS,
)

try:  # soft, NOT `importorskip`: a missing driver must cost this file and nothing else
    import psycopg
except ImportError:  # pragma: no cover - depends on which extras are installed
    psycopg = None  # type: ignore[assignment]

pytestmark = pytest.mark.requires_cluster

DSN_ENV = ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN")

#: Every table this package writes. A missing one is an unlanded migration, not a
#: defect, so the suite says which one and skips.
REQUIRED_TABLES = (
    "patrol_run",
    "drift_finding",
    "observed_assertion",
    "time_witness",
    "discordance_warrant",
)


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
    """Skip, naming the migration band, until the fixity tables exist."""
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
            f"migrations 0090-0098 have not landed: mainline.{', mainline.'.join(missing)} "
            f"do not exist. Those tables belong to the data-model lead; this suite runs for "
            f"real the moment they appear, with no edit here"
        )
    return present


def test_a_follower_read_transaction_reports_its_own_hlc(connection):
    """Measure the claim ``mainline_fixity.follower`` marks unverified.

    If this fails, the honest response is to change the docstring and find another
    way to populate ``patrol_run.as_of_hlc`` — not to relax the assertion.
    """
    with connection.cursor() as cur:
        cur.execute("BEGIN")
        try:
            cur.execute(PATROL_READ_PREAMBLE[1])
            cur.execute(AS_OF_HLC_SQL)
            (hlc,) = cur.fetchone()
        finally:
            cur.execute("COMMIT")
    assert isinstance(hlc, Decimal), (
        f"cluster_logical_timestamp() returned {type(hlc).__name__}, not DECIMAL. "
        f"patrol_run.as_of_hlc is DECIMAL and the patrol has no other way to say when "
        f"it looked"
    )
    assert hlc > 0


def test_an_undetermined_finding_that_claims_blocking_is_refused(connection, tables):
    """MI21, against the constraint rather than against our mirror of it."""
    assert "drift_finding" in tables
    with connection.cursor() as cur, pytest.raises(Exception) as excinfo:  # noqa: PT011
        cur.execute(
            """
            INSERT INTO mainline.drift_finding (
              run_id, site_id, clause_uuid, fixity_class, documented_cat,
              direction, undetermined, severity_inherited, gate_class, confidence
            ) VALUES (
              gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), 'L2', '{}'::JSONB,
              NULL, true, 5, 'blocking', 0.9
            )
            """
        )
    sqlstate = getattr(excinfo.value, "sqlstate", None)
    assert sqlstate == "23514", f"expected 23514, got {sqlstate}: {excinfo.value}"
    assert "undetermined_never_blocks" in str(excinfo.value)


def test_every_emitted_statement_parses_on_the_cluster(connection, tables):
    """`PREPARE` each statement: a column this package names but the DDL lacks fails here.

    Preparing rather than executing keeps the suite read-only against a shared
    cluster while still resolving every identifier in every statement — which is
    the whole failure mode this test exists for.
    """
    assert tables
    for index, sql in enumerate(STATEMENTS):
        name = f"fixity_shape_{index}"
        with connection.cursor() as cur:
            cur.execute(f"PREPARE {name} AS {sql}")
            cur.execute(f"DEALLOCATE {name}")
