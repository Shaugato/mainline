# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``GET /v1/health`` — the cheapest true sentence about the database behind this API.

WHAT CALLS IT, AND WHY THAT SHAPES IT
-------------------------------------
A GitHub Actions cron, every few minutes, for the eight days between now and judging.
The deployment lead priced the alternative and refused it: one CloudWatch Synthetics
canary at five-minute intervals is 8 640 runs a month at $0.0012 — **$10.37/month,
thirty times the cost of everything else in the stack combined**. A cron hitting this
endpoint costs nothing and its failures are visible in the repository the judges are
already reading.

So this endpoint has to be cheap, and cheap has a specific meaning here: **one round
trip, no joins**. The statement below reads ``version()``, ``current_database()``,
``now()`` and five scalar subqueries over the ``trappoint`` bookkeeping tables. Scalar
subqueries in a select list are not joins; the marker ones are primary-key point lookups
against a table that holds one row per database. Nothing in it touches ``mainline.*``, so
the cost does not grow with the demo's data.

TWO APPLIERS, TWO LEDGERS, AND WHY THIS ENDPOINT NAMES THE ONE IT QUOTED
------------------------------------------------------------------------
Two programs in this tree apply the 271-file migration chain, and they keep two
different ledgers:

* ``trappoint migrate up`` writes one row per file into ``trappoint.schema_migration``.
  ``trappoint_migrate/runner.py`` holds the only ``INSERT`` into that table anywhere in
  the tree.
* ``scripts/deploy/cloud_chain.py`` runs ``trappoint migrate bootstrap`` — which is what
  writes ``trappoint.schema_attestation``, and therefore what makes the fingerprint below
  non-null — then applies the files itself and records **one marker row** in
  ``trappoint.deploy_chain`` carrying ``files``, ``applied``, ``failed``, ``retried``,
  both fingerprints and ``applied_by``.

``cloud_chain.py`` is what built Cloud ``mainline_demo``, and it is what builds every
scratch database, so on the deployed cluster ``trappoint.schema_migration`` is empty **by
construction**. This endpoint used to report that emptiness as a bare
``migrations_applied: 0`` and stop — a true count of the wrong ledger, which reads to a
judge as *no migrations ran*. Measured 2026-08-12 UTC against a local rehearsal of the
real deploy program (``cloud_chain.py --database w_w5 --recreate``, verdict ``APPLIED``,
271/271, 0 failed)::

    migrations_applied 0      deploy_chain_applied 271   deploy_chain_files 271
    applied_by "scripts/deploy/cloud_chain.py"

The fix is not to count files on disk and not to hard-code 271: either would make this
endpoint quote the repository instead of the database, which is the failure mode the
whole evidence bundle exists to avoid. The fix is to read **both** ledgers and say which
applier's ledger the numbers came from.

WHAT IT REPORTS, AND WHAT EACH FIELD IS FOR
-------------------------------------------
``ok``                  the summary. 200 if and only if this is true. It keys on the
                        fingerprint and on nothing else — a database honestly built by
                        either applier is healthy, so neither count may decide this.
``cluster_version``     ``version()``. A judge can compare it with the version the
                        submission claims. It is the cluster's word, not ours.
``database``            ``current_database()``. Which database this Lambda is actually
                        pointed at — the one question a misconfigured environment
                        variable makes urgent.
``schema_fingerprint``  the newest ``trappoint.schema_attestation.fingerprint``, hex.
                        The migration chain's own hash-linked attestation ledger: it
                        changes when and only when the schema changes, so the console's
                        honesty chrome can show that the cluster serving the demo is the
                        cluster the evidence bundle was captured from.
``migrations_applied``  ``count(*)`` of ``trappoint.schema_migration`` in state
                        ``applied`` — the ledger ``trappoint migrate up`` writes, and
                        ``0`` on a database ``cloud_chain.py`` built. Left exactly as it
                        was: it is a true count of that table, and the honest repair for
                        a number that answers the wrong question is another number, not
                        a louder version of this one.
``deploy_chain_applied``, ``deploy_chain_files``
                        ``applied`` and ``files`` from **this database's own**
                        ``trappoint.deploy_chain`` marker (``marker_id =
                        current_database()``, the key ``cloud_chain.py`` writes and reads
                        it by), or ``None`` where there is no marker. ``files -
                        applied`` is the recorded gap, and the marker's own ``CHECK
                        (applied + failed = files)`` is what makes that subtraction
                        sound.
``applied_by``          **which applier built this database**, so that the two counts
                        above are self-describing rather than a puzzle. See
                        :func:`_applier` for the three values and why the third is
                        ``"unrecorded"`` rather than a guess.
``seconds``             wall clock for the round trip, measured here. It is the number
                        that tells the cron the difference between "up" and "up, from
                        Australia, across the Pacific".

ONE ROUND TRIP, AND THE ONE KIND OF DATABASE THAT COSTS TWO
------------------------------------------------------------
``trappoint.deploy_chain`` is created by ``cloud_chain.py``, so a database built by
``trappoint migrate up`` — or by this app's test fixture, which executes the files
directly — does not have it. CockroachDB resolves every relation in a statement at plan
time, so the missing table fails the **whole** statement with ``42P01`` even though it is
named only inside a scalar subquery, and there is no SQL spelling that reads a relation
conditionally on its existence. Measured: the full statement raises
``psycopg.errors.UndefinedTable`` ``42P01 relation "trappoint.deploy_chain" does not
exist`` on ``w3_demo_api_*`` and on a ``migrate up`` database, and answers on ``w_w5``.

So the marker's absence is classified by **behaviour, not by parsing an error message**:
on ``42P01`` the same statement minus the marker subqueries —
:data:`HEALTH_STATEMENT_WITHOUT_DEPLOY_CHAIN` — is run once. If it answers, the missing
relation was the marker and this is a healthy **200** with the marker fields ``None``. If
it raises too, the ``trappoint`` bookkeeping really is absent, and *that* is the
``no_bookkeeping`` 503. The exception the 503 quotes is therefore always raised by a
statement that cannot name ``deploy_chain``, which is how the marker's absence is made
structurally incapable of producing a 503. ``db._open`` opens with ``autocommit=True``,
so the failed statement leaves no transaction to roll back — measured, the connection
answers ``SELECT 1`` immediately afterwards.

The deployed cluster carries the marker, so it costs one round trip. Only a marker-less
database pays a second, and only for the failed first statement.

THREE OUTCOMES, THREE STATUSES
------------------------------
* **200** — the statement answered.
* **503, ``dsn_unset``** — no ``$MAINLINE_DSN`` and no ``$MAINLINE_DSN_PARAM``. Nobody
  told this function where the database is. Fixed by a deploy, not by a database.
* **503, ``unreachable`` / ``no_bookkeeping``** — the database did not answer, or it
  answered and has no ``trappoint`` schema. The second is a real state: a node with an
  empty database is running, and reporting it as healthy would make this endpoint a
  liveness probe for a Lambda rather than a health check for a demo.

A 503 body is deliberately as informative as a 200 body. A health check that says only
``{"ok": false}`` sends whoever is on call to the logs; this one names the failure.
"""

from __future__ import annotations

import time
from typing import Any, Final

import psycopg
from psycopg.rows import dict_row

from . import db
from .envelope import rfc3339

__all__ = [
    "HEALTH_PATH",
    "HEALTH_STATEMENT",
    "HEALTH_STATEMENT_WITHOUT_DEPLOY_CHAIN",
    "health",
]

HEALTH_PATH: Final = "/v1/health"

#: The half of the statement every database that has been bootstrapped can answer.
_HEALTH_CORE: Final = """
SELECT version()                                            AS cluster_version,
       current_database()                                   AS database,
       now()                                                AS server_date,
       (SELECT encode(fingerprint, 'hex')
          FROM trappoint.schema_attestation
         ORDER BY ordinal DESC
         LIMIT 1)                                           AS schema_fingerprint,
       (SELECT count(*)
          FROM trappoint.schema_migration
         WHERE state = 'applied')                           AS migrations_applied"""

#: The other applier's ledger. Three primary-key point lookups at one row, not a join.
_HEALTH_DEPLOY_CHAIN: Final = """,
       (SELECT applied
          FROM trappoint.deploy_chain
         WHERE marker_id = current_database())              AS deploy_chain_applied,
       (SELECT files
          FROM trappoint.deploy_chain
         WHERE marker_id = current_database())              AS deploy_chain_files,
       (SELECT applied_by
          FROM trappoint.deploy_chain
         WHERE marker_id = current_database())              AS applied_by"""

#: ONE round trip, BOTH ledgers. Carried as a module constant so the README, the tests
#: and the Terraform alarm description can all quote the same string.
HEALTH_STATEMENT: Final = _HEALTH_CORE + _HEALTH_DEPLOY_CHAIN + "\n"

#: The fallback, for a database no ``cloud_chain.py`` run ever marked. Composed from the
#: same text rather than written out again, so the two can never drift apart in the four
#: columns they share.
HEALTH_STATEMENT_WITHOUT_DEPLOY_CHAIN: Final = _HEALTH_CORE + "\n"

#: What ``trappoint migrate up`` is called, where this module has to name it. The string
#: is the command a reader would run, not ``schema_migration.applied_by``: that column
#: holds ``runner.actor()``, a username and a hostname, and a public health endpoint is
#: not the place to publish either.
_MIGRATE_UP: Final = "trappoint migrate up"

#: Every 503 carries the same keys as a 200, with the readings ``None`` rather than the
#: keys missing — a caller written against one shape cannot be broken by the other.
#: Spread into a fresh dict at each site; never mutated.
_NO_READING: Final[dict[str, Any]] = {
    "cluster_version": None,
    "database": None,
    "schema_fingerprint": None,
    "migrations_applied": None,
    "deploy_chain_applied": None,
    "deploy_chain_files": None,
    "applied_by": None,
}


def _applier(marker_applied_by: Any, migrations_applied: int) -> str:
    """Name the applier whose ledger this body just quoted. Three values, no guessing.

    * the marker's own ``applied_by`` when ``trappoint.deploy_chain`` has a row for this
      database — the database's own word, in practice
      ``"scripts/deploy/cloud_chain.py"``, which is the literal that program writes;
    * ``"trappoint migrate up"`` when there is no marker but ``schema_migration`` holds
      applied rows. That is an inference, and it is sound for exactly one reason:
      ``trappoint_migrate/runner.py`` holds the only ``INSERT`` into that table in this
      tree, so a non-empty ledger has only one possible writer;
    * ``"unrecorded"`` when neither ledger holds anything. That is what this app's test
      fixture looks like — ``conftest._apply_chain`` bootstraps and then executes each
      file itself, so it writes to neither — and it is what any hand-applied database
      looks like. Naming an applier there would be a guess, and the fingerprint is still
      real, so the honest report is that no applier left a record.
    """
    if marker_applied_by:
        return str(marker_applied_by)
    if migrations_applied > 0:
        return _MIGRATE_UP
    return "unrecorded"


def _read(conn: psycopg.Connection[Any], statement: str) -> dict[str, Any] | None:
    """Run *statement* through a cursor that DECLARES the shape it is read with.

    ``db._open`` opens production connections with ``row_factory=dict_row`` and the
    columns below are read by name, so inheriting the connection's factory would work
    today and break silently the day it changed. That is the defect class that took
    ``/v1/gate/run`` down with ``KeyError: 0``; a statement should carry its own shape.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement)
        return cur.fetchone()


def health(*, dsn: str | None = None) -> tuple[int, dict[str, Any]]:
    """Answer ``GET /v1/health``. Returns ``(status, body)``; never raises.

    *dsn* bypasses :func:`db.resolve_dsn`, which is how the tests point it at a scratch
    database and how a local run points it at the Docker node.
    """
    started = time.monotonic()

    if dsn is None:
        try:
            dsn = db.resolve_dsn()
        except db.DsnUnavailable as exc:
            return 503, {
                "ok": False,
                "reason": "dsn_unset",
                "detail": str(exc),
                **_NO_READING,
                "seconds": round(time.monotonic() - started, 4),
            }

    try:
        conn = db.connection(dsn=dsn)
        try:
            row = _read(conn, HEALTH_STATEMENT)
        except psycopg.errors.UndefinedTable:
            # Which relation was missing? Asked of the database rather than of the error
            # text. This statement names neither `deploy_chain` nor anything else the
            # marker needs, so if it answers, the marker was the only thing absent and
            # this is a healthy 200. If it raises, the exception that reaches the handler
            # below was raised by a statement that CANNOT be about `deploy_chain`.
            row = _read(conn, HEALTH_STATEMENT_WITHOUT_DEPLOY_CHAIN)
    except psycopg.errors.UndefinedTable as exc:
        # The node answered. It has no `trappoint` bookkeeping, so this is a database
        # the migration chain has never been bootstrapped into. Naming the relation is
        # the difference between "the demo is down" and "you pointed it at defaultdb".
        return 503, {
            "ok": False,
            "reason": "no_bookkeeping",
            "detail": (
                "the database answered but carries no trappoint bookkeeping "
                f"({str(exc).splitlines()[0]}). Run `trappoint migrate bootstrap` and the "
                "migration chain into it, or point $MAINLINE_DSN at the database that has one."
            ),
            **_NO_READING,
            "seconds": round(time.monotonic() - started, 4),
        }
    except psycopg.Error as exc:
        db.close()
        return 503, {
            "ok": False,
            "reason": "unreachable",
            "detail": f"[{exc.sqlstate or '-----'}] {str(exc).splitlines()[0][:400]}",
            "dsn": db.redact(dsn),
            **_NO_READING,
            "seconds": round(time.monotonic() - started, 4),
        }

    if row is None:  # pragma: no cover - the statement returns exactly one row or raises
        return 503, {
            "ok": False,
            "reason": "unreachable",
            "detail": "the health statement returned no row",
            **_NO_READING,
            "seconds": round(time.monotonic() - started, 4),
        }

    fingerprint = row["schema_fingerprint"]
    migrations_applied = int(row["migrations_applied"] or 0)
    # `.get`, not `[...]`: the fallback statement does not select these columns at all,
    # and their absence from the row is exactly the "no marker in this database" case.
    chain_applied = row.get("deploy_chain_applied")
    chain_files = row.get("deploy_chain_files")
    body: dict[str, Any] = {
        "ok": fingerprint is not None,
        "cluster_version": row["cluster_version"],
        "database": row["database"],
        "schema_fingerprint": fingerprint,
        "migrations_applied": migrations_applied,
        "deploy_chain_applied": None if chain_applied is None else int(chain_applied),
        "deploy_chain_files": None if chain_files is None else int(chain_files),
        "applied_by": _applier(row.get("applied_by"), migrations_applied),
        "server_date": rfc3339(row["server_date"]),
        "seconds": round(time.monotonic() - started, 4),
    }
    if fingerprint is None:
        # `trappoint.schema_attestation` exists and is EMPTY. Only reachable if someone
        # created the schema without the genesis attestation `trappoint migrate
        # bootstrap` writes, which means the chain's hash link has no anchor.
        body["reason"] = "no_bookkeeping"
        body["detail"] = (
            "trappoint.schema_attestation is empty: this database has the bookkeeping "
            "schema but no genesis attestation, so there is no fingerprint to report."
        )
        return 503, body
    return 200, body
