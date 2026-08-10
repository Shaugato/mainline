# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
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
``now()`` and two scalar subqueries over the ``trappoint`` bookkeeping tables. Scalar
subqueries in a select list are not joins; nothing in it touches ``mainline.*``, so the
cost does not grow with the demo's data.

WHAT IT REPORTS, AND WHAT EACH FIELD IS FOR
-------------------------------------------
``ok``                  the summary. 200 if and only if this is true.
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
                        ``applied``. 271 files on this tree as of 2026-08-10.
``seconds``             wall clock for the round trip, measured here. It is the number
                        that tells the cron the difference between "up" and "up, from
                        Australia, across the Pacific".

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

from . import db
from .envelope import rfc3339

__all__ = ["HEALTH_PATH", "HEALTH_STATEMENT", "health"]

HEALTH_PATH: Final = "/v1/health"

#: ONE round trip. Carried as a module constant so the README, the tests and the
#: Terraform alarm description can all quote the same string.
HEALTH_STATEMENT: Final = """
SELECT version()                                            AS cluster_version,
       current_database()                                   AS database,
       now()                                                AS server_date,
       (SELECT encode(fingerprint, 'hex')
          FROM trappoint.schema_attestation
         ORDER BY ordinal DESC
         LIMIT 1)                                           AS schema_fingerprint,
       (SELECT count(*)
          FROM trappoint.schema_migration
         WHERE state = 'applied')                           AS migrations_applied
"""


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
                "cluster_version": None,
                "database": None,
                "schema_fingerprint": None,
                "migrations_applied": None,
                "seconds": round(time.monotonic() - started, 4),
            }

    try:
        conn = db.connection(dsn=dsn)
        row = conn.execute(HEALTH_STATEMENT).fetchone()
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
            "cluster_version": None,
            "database": None,
            "schema_fingerprint": None,
            "migrations_applied": None,
            "seconds": round(time.monotonic() - started, 4),
        }
    except psycopg.Error as exc:
        db.close()
        return 503, {
            "ok": False,
            "reason": "unreachable",
            "detail": f"[{exc.sqlstate or '-----'}] {str(exc).splitlines()[0][:400]}",
            "dsn": db.redact(dsn),
            "cluster_version": None,
            "database": None,
            "schema_fingerprint": None,
            "migrations_applied": None,
            "seconds": round(time.monotonic() - started, 4),
        }

    if row is None:  # pragma: no cover - the statement returns exactly one row or raises
        return 503, {
            "ok": False,
            "reason": "unreachable",
            "detail": "the health statement returned no row",
            "cluster_version": None,
            "database": None,
            "schema_fingerprint": None,
            "migrations_applied": None,
            "seconds": round(time.monotonic() - started, 4),
        }

    fingerprint = row["schema_fingerprint"]
    body: dict[str, Any] = {
        "ok": fingerprint is not None,
        "cluster_version": row["cluster_version"],
        "database": row["database"],
        "schema_fingerprint": fingerprint,
        "migrations_applied": int(row["migrations_applied"] or 0),
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
