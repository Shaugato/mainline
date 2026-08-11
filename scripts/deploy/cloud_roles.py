#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Create the two SQL logins the MAINLINE demo needs, and nothing else.

``mainline_api``
    The identity the Lambda connects as. It holds what the demo's three beats require and no
    more: read on the corpus the read resources show, the writes ``mainline.merge_permit`` and the
    disposition path actually perform, ``EXECUTE`` on the merge procedure, and membership in the
    three roles whose row-level-security policies make those statements *see* anything.

``mainline_judge``
    Read-only, for the judges. ``SELECT`` on the ``mainline_audit`` views and on nothing else in
    the cluster. Explicitly **not** ``mainline_qa``.

Both passwords are generated here, printed to stdout ONCE, and never written to a file, never
logged, and never put in an evidence artefact. There is no ``--password`` option, deliberately: an
operator who cannot pass a password on a command line cannot leave one in shell history.

WHY ROLE MEMBERSHIP AND NOT ONLY GRANTS
---------------------------------------
Four tables in this schema carry ``FORCE ROW LEVEL SECURITY`` (``RLS-MATRIX.yaml``:
``mainline.permit``, ``mainline.change_request``, ``mainline.disposition``,
``mainline_meas.standing``), and under FORCE *"if RLS is enabled but no policies apply to a given
combination of user and SQL statement, access is denied by default."* A bare ``GRANT SELECT ON
mainline.permit`` therefore buys **zero rows**, silently — which is the worst failure an audit
surface can have, because it is indistinguishable from a clean site.

The policies are written ``TO <role>``, and a policy matches any member of that role. So
``mainline_api`` is made a member of exactly three:

===================  ===========================================================================
``auditor_ro``       ``fleet_scope`` on permit and change_request, ``disposition_service_read``
``agent_gate``       ``service_read``, ``gate_insert``, ``gate_write`` — the merge transaction
``svc_disposition``  ``gate_write`` (the counter decrement) and ``disposition_insert``
===================  ===========================================================================

Those three are the principals the demo impersonates, one per beat. The memberships are for RLS
SCOPE; the table privileges are granted directly below, because ``GRANTS.yaml``'s table matrix is
applied by ``trappoint migrate grants apply`` and this program does not assume anybody has run it.
Measured on a freshly migrated database: ``information_schema.table_privileges`` for
``agent_gate``, ``svc_disposition`` and ``auditor_ro`` returns **no rows**. Relying on inheritance
alone would have produced a login that can see nothing and a demo that fails in front of a judge.

WHAT IS NOT HERE, AND WHY
-------------------------
* **No disposition procedure.** The brief names "the disposition procedures"; this schema has
  none. ``information_schema.routines`` holds exactly two procedures in ``mainline`` —
  ``merge_permit`` and ``merge_change_request``. A disposition is a plain ``INSERT`` into
  ``mainline.disposition``, projected by ``fn_disposition_project``. So the grant that corresponds
  to "may sign a disposition" is ``INSERT`` on that table plus the ``disposition_insert`` policy,
  and that is what is granted. Recording the absence is better than granting ``EXECUTE`` on a
  routine that does not exist and calling the deployment done.
* **Nothing in ``mainline_qa``, for either login, ever.** S14. The privileges are not merely
  omitted, they are REVOKED on every run — ``GRANTS.yaml`` §7's reasoning applies exactly: a
  migration runs once, drift happens continuously. The judge pack's own envelope names
  ``mainline_qa`` as never-issued, and ``--verify`` asserts ``42501`` on it for both logins rather
  than trusting that the absence of a grant is the absence of reach.
* **No ``DELETE``, for either login.** No role in ``GRANTS.yaml`` holds ``DELETE`` on anything
  (MI01), and a demo login that could delete would be the only principal in the system that can.

Usage::

    .venv/Scripts/python.exe scripts/deploy/cloud_roles.py              # create, grant, verify
    .venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate     # new passwords
    .venv/Scripts/python.exe scripts/deploy/cloud_roles.py --verify     # probe only, no DDL

Exit codes:

* ``0`` — both logins exist, hold what they should, and the probes agreed.
* ``1`` — a probe disagreed: something is reachable that should not be, or unreachable that should.
* ``2`` — no DSN, or no cluster.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.deploy.cloud_chain import (
    DEFAULT_DATABASE,
    cluster_label,
    load_dotenv,
    one_line,
    repo_root,
    rewrite_dsn,
    sqlstate_of,
)

EXIT_OK = 0
EXIT_PROBE_DISAGREED = 1
EXIT_USAGE = 2

API_USER = "mainline_api"
JUDGE_USER = "mainline_judge"

#: The refusal every negative probe expects. ``42501`` is ``insufficient_privilege``; it is what a
#: grant that was never made looks like from the other side of the connection.
REFUSED = "42501"

#: The audit surface. Fourteen views, enumerated by name rather than wildcarded, because
#: ``GRANT ... ON ALL TABLES IN SCHEMA`` would silently pick up whatever a later migration adds —
#: and the whole point of the judge login is that its reach is a closed list somebody reviewed.
AUDIT_VIEWS: tuple[str, ...] = (
    "v_agent_actions",
    "v_blame_coverage",
    "v_cbm_ledger",
    "v_changefeed_health",
    "v_disposition_coverage",
    "v_fixity_coverage",
    "v_gate_latency_daily",
    "v_ledger_health",
    "v_open_gate_summary",
    "v_recall_conservation",
    "v_silence_summary",
    "v_txn_restart_daily",
    "v_unused_indexes",
    "v_weakenings_without_disposition",
)

#: What the demo's read surfaces touch, enumerated. Every one of these is on the path from
#: "show me the permit" to "show me the precursor that obliged it and the pass that found it".
API_READ: tuple[str, ...] = (
    # the gated subject and its record
    "mainline.permit",
    "mainline.permit_clause",
    "mainline.permit_event",
    "mainline.boundary_certificate",
    "mainline.blocking_check",
    "mainline.disposition",
    "mainline.merge_record",
    "mainline.refusal_ledger",
    "mainline.exposure_receipt",
    "mainline.exposure_line",
    # the corpus the obligation points at
    "mainline.site",
    "mainline.person",
    "mainline.signing_credential",
    "mainline.doc",
    "mainline.clause",
    "mainline.clause_version",
    "mainline.event",
    "mainline.blame_edge",
    "mainline.clause_blame_closure",
    "mainline.clause_blame_current",
    "mainline.commit_obj",
    "mainline.commit_edge",
    "mainline.cbm_account",
    # the custody plane, and the lattices that make an illegal value unrepresentable
    "mainline.ledger_checkpoint",
    "mainline.cosignature",
    "mainline.subject_transition",
    "mainline.clearance_legal",
    # the recall pass and what it declined to surface
    "mainline_meas.recall_policy",
    "mainline_meas.recall_run",
    "mainline_meas.recall_candidate",
    "mainline_meas.silence_receipt",
)

#: What the GATE TRANSACTION reads, which is not the same list as what the read resources read.
#:
#: DISCOVERED BY RUNNING IT, not by reading the schema. Every trigger function in migrations
#: 0100-0149 executes as the INVOKING role — none is SECURITY DEFINER, and ``GRANTS.yaml`` records
#: that as an open coupling rather than hiding it — so the merge transaction's trigger chain needs
#: SELECT on tables no demo screen ever displays. The method was a loop: run the three beats as
#: ``mainline_api``, parse the ``42501``, grant exactly the named privilege on the named relation,
#: repeat until the beats produced their real outcomes. Thirteen grants, in this order:
#:
#:   UPDATE blocking_check · SELECT change_request · INSERT ledger_intake · SELECT identity_residue
#:   SELECT permit_boundary · SELECT permit_slice · SELECT override_ledger · SELECT unwitnessed_debt
#:   SELECT disposition_citation · SELECT mechanism_predicate · UPDATE change_request
#:   SELECT cr_clause · SELECT cr_event
#:
#: The change_request rows are there because ``fn_disposition_close`` and ``fn_check_materialised``
#: branch on ``subject_kind`` and touch the change-request arm even when the subject is a permit.
#: Guessing this list from the ARCHITECTURE would have produced a login that fails in the middle
#: of the demo's second beat, in front of a judge, with a privilege error.
API_GATE_READ: tuple[str, ...] = (
    "mainline.change_request",
    "mainline.cr_clause",
    "mainline.cr_event",
    "mainline.identity_residue",
    "mainline.permit_boundary",
    "mainline.permit_slice",
    "mainline.override_ledger",
    "mainline.unwitnessed_debt",
    "mainline.disposition_citation",
    "mainline.mechanism_predicate",
)

#: What the three beats WRITE. Every entry is a statement the demo actually issues, or a write a
#: trigger performs as the invoking role. ``mainline_ops.outbox`` is on this list for that reason:
#: ``fn_check_materialised`` and ``fn_disposition_close`` insert into it as whoever called them.
#: ``mainline.ledger_intake`` is on it because ``merge_permit`` appends the merge to the custody
#: log in the same transaction — the demo's admission beat writes an audit trail or it does not
#: happen at all.
API_WRITE: tuple[tuple[str, str], ...] = (
    ("mainline.permit", "UPDATE"),
    ("mainline.permit_event", "INSERT"),
    ("mainline.merge_record", "INSERT"),
    ("mainline.refusal_ledger", "INSERT"),
    ("mainline.disposition", "INSERT"),
    ("mainline.disposition_citation", "INSERT"),
    ("mainline.override_ledger", "INSERT"),
    ("mainline.ledger_intake", "INSERT"),
    ("mainline.blocking_check", "UPDATE"),
    ("mainline.change_request", "UPDATE"),
    ("mainline_ops.outbox", "INSERT"),
)

#: For RLS scope, not for privileges. See the module docstring.
API_MEMBERSHIPS: tuple[str, ...] = ("auditor_ro", "agent_gate", "svc_disposition")

#: Never granted to either login. Re-revoked every run.
FORBIDDEN_SCHEMAS: tuple[str, ...] = ("mainline_qa",)


def generate_password() -> str:
    """A 32-character URL-safe secret.

    URL-safe on purpose: the value is inlined into ``CREATE USER ... PASSWORD '...'`` because
    CockroachDB takes no placeholder there, and an alphabet with no quote, backslash or space in
    it makes that inlining safe by construction rather than by an escaping routine somebody has
    to get right. It also survives being pasted into a DSN and into
    ``aws ssm put-parameter --value`` without shell quoting games.
    """
    return secrets.token_urlsafe(24)


def user_exists(conn: psycopg.Connection[Any], name: str) -> bool:
    row = conn.execute("SELECT count(*) FROM [SHOW USERS] WHERE username = %s", (name,)).fetchone()
    return bool(row and row[0])


def apply_statement(conn: psycopg.Connection[Any], sql: str, *, note: str) -> dict[str, Any]:
    """Run one grant statement, and report rather than abort when the object is not there.

    ``GRANTS.yaml``'s contract for ``grants apply`` is explicit: a row whose object is absent from
    the connected database is SKIPPED WITH A WARNING, never an error, because a cluster migrated
    only part-way must still be grantable. The same rule is followed here — a missing table is a
    warning naming the object, and everything else is a real failure.
    """
    try:
        conn.execute(sql)  # type: ignore[arg-type]
    except psycopg.Error as exc:
        state = sqlstate_of(exc)
        if state in {"42P01", "42883", "3F000"}:  # undefined table / function / schema
            return {"note": note, "skipped": True, "sqlstate": state, "why": one_line(exc)}
        return {"note": note, "ok": False, "sqlstate": state, "error": one_line(exc)}
    return {"note": note, "ok": True}


# One branch per GRANT CLASS, deliberately. Each loop below corresponds to a numbered section
# of GRANTS.yaml or to a measured need, and each writes its own `note` into the log so that the
# operator's terminal names the reason for every statement. Merging them into a generic
# (role, object, privilege) table would produce a log in which "SELECT on mainline.cr_event"
# carries no clue that it exists because a trigger branches on subject_kind.
def provision(  # noqa: PLR0912
    conn: psycopg.Connection[Any], database: str, *, rotate: bool
) -> tuple[dict[str, str | None], list[dict[str, Any]]]:
    """Create both logins and assert every privilege. Idempotent.

    A password is set only when the login is CREATED, or when ``--rotate`` says so. Re-running
    this program against a live deployment must not invalidate the credential the Lambda is
    already using; a deploy script that silently rotates a secret is a deploy script that takes
    the demo down every time somebody re-runs it.
    """
    secrets_issued: dict[str, str | None] = {}
    log: list[dict[str, Any]] = []

    for user in (API_USER, JUDGE_USER):
        existed = user_exists(conn, user)
        if not existed or rotate:
            password = generate_password()
            try:
                # No placeholder is possible here and none is used. The password alphabet is
                # URL-safe, so there is nothing in it to escape, and this statement is the ONLY
                # place in this package where a secret is interpolated into SQL.
                conn.execute(
                    f"CREATE USER IF NOT EXISTS \"{user}\" WITH LOGIN PASSWORD '{password}'"
                )
                if existed:
                    conn.execute(f"ALTER USER \"{user}\" WITH PASSWORD '{password}'")
            except psycopg.Error as exc:
                # AN INSECURE CLUSTER CANNOT HOLD A PASSWORD. The local single-node development
                # node runs with `--insecure`, and CockroachDB refuses outright:
                # "setting or updating a password is not supported in insecure mode". That is not
                # a deployment failure, it is a different cluster, and a rehearsal on the laptop
                # has to be possible or nobody rehearses. The login is created without one, and
                # the fact is stated in the output and in every probe line, so that a passing
                # rehearsal is never mistaken for a passing deployment.
                if "insecure" not in one_line(exc).lower():
                    raise
                conn.execute(f'CREATE USER IF NOT EXISTS "{user}" WITH LOGIN')
                secrets_issued[user] = ""
                log.append(
                    {
                        "note": f"{user}: created WITHOUT a password — this cluster is insecure",
                        "ok": True,
                    }
                )
                log.append(
                    apply_statement(
                        conn,
                        f'GRANT CONNECT ON DATABASE "{database}" TO "{user}"',
                        note=f"{user}: CONNECT on {database}",
                    )
                )
                continue
            secrets_issued[user] = password
            log.append({"note": f"{user}: {'rotated' if existed else 'created'}", "ok": True})
        else:
            secrets_issued[user] = None
            log.append(
                {
                    "note": f"{user}: already exists, password left alone (--rotate to change)",
                    "ok": True,
                }
            )
        log.append(
            apply_statement(
                conn,
                f'GRANT CONNECT ON DATABASE "{database}" TO "{user}"',
                note=f"{user}: CONNECT on {database}",
            )
        )

    # ── mainline_api ─────────────────────────────────────────────────────────────────────────
    for schema in ("mainline", "mainline_meas", "mainline_audit", "mainline_ops"):
        log.append(
            apply_statement(
                conn,
                f'GRANT USAGE ON SCHEMA {schema} TO "{API_USER}"',
                note=f"{API_USER}: USAGE on {schema}",
            )
        )
    for role in API_MEMBERSHIPS:
        log.append(
            apply_statement(
                conn,
                f'GRANT "{role}" TO "{API_USER}"',
                note=f"{API_USER}: member of {role} (for RLS policy scope, not privileges)",
            )
        )
    for table in API_READ:
        log.append(
            apply_statement(
                conn,
                f'GRANT SELECT ON TABLE {table} TO "{API_USER}"',
                note=f"{API_USER}: SELECT on {table} (read resources)",
            )
        )
    for table in API_GATE_READ:
        log.append(
            apply_statement(
                conn,
                f'GRANT SELECT ON TABLE {table} TO "{API_USER}"',
                note=f"{API_USER}: SELECT on {table} (gate trigger chain)",
            )
        )
    for view in AUDIT_VIEWS:
        log.append(
            apply_statement(
                conn,
                f'GRANT SELECT ON TABLE mainline_audit.{view} TO "{API_USER}"',
                note=f"{API_USER}: SELECT on mainline_audit.{view}",
            )
        )
    for table, privilege in API_WRITE:
        log.append(
            apply_statement(
                conn,
                f'GRANT {privilege} ON TABLE {table} TO "{API_USER}"',
                note=f"{API_USER}: {privilege} on {table}",
            )
        )
    log.append(
        apply_statement(
            conn,
            f"GRANT EXECUTE ON PROCEDURE mainline.merge_permit"
            f'(UUID, BYTES, STRING, STRING, JSONB, BYTES, INT2, BYTES) TO "{API_USER}"',
            note=f"{API_USER}: EXECUTE on mainline.merge_permit",
        )
    )

    # ── mainline_judge ───────────────────────────────────────────────────────────────────────
    #
    # MEASURED, AND NOT WHAT THE DOCUMENTATION LED ME TO EXPECT (CockroachDB CCL v26.2.5, local
    # single node, 2026-08-10). A view runs the underlying query with its OWNER's table
    # privileges — that is the fourth trap RLS-MATRIX.yaml names, and it holds. But the SCHEMA
    # USAGE check is made against the INVOKER regardless:
    #
    #   with USAGE on mainline_audit only:
    #     SELECT count(*) FROM mainline_audit.v_open_gate_summary
    #       → 42501  user mainline_judge does not have USAGE privilege on schema mainline
    #
    #   with USAGE additionally on mainline, mainline_meas, mainline_ops:
    #     SELECT count(*) FROM mainline_audit.v_open_gate_summary   → OK, rows=1
    #     SELECT count(*) FROM mainline.permit
    #       → 42501  user mainline_judge does not have SELECT privilege on relation permit
    #
    # So the judge login needs USAGE on the schemas its views TRAVERSE, and gets no table
    # privilege in any of them. USAGE is the right to name a schema; it is not the right to read
    # anything in it, and the second probe above is the evidence rather than the assurance.
    # `mainline_qa` is NOT in this list and never will be: without USAGE the schema is not even
    # nameable, which is a stronger position than a revoked SELECT.
    for schema in ("mainline_audit", "mainline", "mainline_meas", "mainline_ops"):
        log.append(
            apply_statement(
                conn,
                f'GRANT USAGE ON SCHEMA {schema} TO "{JUDGE_USER}"',
                note=(
                    f"{JUDGE_USER}: USAGE on {schema}"
                    + (
                        ""
                        if schema == "mainline_audit"
                        else " (traversal only, no table privilege)"
                    )
                ),
            )
        )
    for view in AUDIT_VIEWS:
        log.append(
            apply_statement(
                conn,
                f'GRANT SELECT ON TABLE mainline_audit.{view} TO "{JUDGE_USER}"',
                note=f"{JUDGE_USER}: SELECT on mainline_audit.{view}",
            )
        )

    # ── the revocations, re-asserted, because drift is additive ──────────────────────────────
    for user in (API_USER, JUDGE_USER):
        for schema in FORBIDDEN_SCHEMAS:
            log.append(
                apply_statement(
                    conn,
                    f'REVOKE ALL ON SCHEMA {schema} FROM "{user}"',
                    note=f"{user}: REVOKE ALL on schema {schema} (S14)",
                )
            )
            log.append(
                apply_statement(
                    conn,
                    f'REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM "{user}"',
                    note=f"{user}: REVOKE ALL on every view in {schema} (S14)",
                )
            )
    for schema in ("mainline", "mainline_meas", "mainline_ops"):
        log.append(
            apply_statement(
                conn,
                f'REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM "{JUDGE_USER}"',
                note=(
                    f"{JUDGE_USER}: REVOKE ALL on every table in {schema} — the login may NAME "
                    "these schemas so its views can traverse them, and may read nothing in them"
                ),
            )
        )
    return secrets_issued, log


# ═════════════════════════════════════════════════════════════════════════════════════
# the probes — the part that turns a grant into evidence
# ═════════════════════════════════════════════════════════════════════════════════════


def as_user(dsn: str, user: str, password: str, database: str) -> str:
    """The same DSN, with the userinfo replaced. An empty *password* means none is sent.

    Everything else — host, port, `sslmode`, `options` carrying the Cloud routing id — is carried
    over untouched, because a Cloud Basic DSN's query string is load-bearing and rebuilding it by
    hand is how a probe ends up testing a different cluster from the one being deployed.
    """
    parts = urlsplit(rewrite_dsn(dsn, database=database, application_name="mainline-deploy-probe"))
    host = parts.hostname or "localhost"
    port = f":{parts.port}" if parts.port else ""
    userinfo = f"{user}:{password}@" if password else f"{user}@"
    return urlunsplit(
        (parts.scheme, f"{userinfo}{host}{port}", parts.path, parts.query, parts.fragment)
    )


def probe(dsn: str, expectations: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    """Run each probe as the login itself and record what the CLUSTER said.

    A grant is a claim about intent; a ``42501`` is evidence about behaviour. ``GRANTS.yaml`` says
    that in its own header and names the privilege probe, not the matrix, as the real control.
    These probes are the deployment's version of it, and both directions are asserted — what must
    be readable and what must not — because a login that can read nothing passes every negative
    test.
    """
    results: list[dict[str, Any]] = []
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        for label, sql, expected in expectations:
            try:
                row = conn.execute(sql).fetchone()  # type: ignore[arg-type]
            except psycopg.Error as exc:
                observed, detail = sqlstate_of(exc), one_line(exc)
                conn.rollback()
            else:
                observed, detail = "00000", f"rows={row[0] if row else 0}"
            results.append(
                {
                    "probe": label,
                    "expected": expected,
                    "observed": observed,
                    "agreed": observed == expected,
                    "detail": detail,
                }
            )
    finally:
        conn.close()
    return results


def gate_probe(dsn: str) -> dict[str, Any] | None:
    """Ask, as ``mainline_api``, whether this login can actually drive the demo's first beat.

    Every other probe here tests one privilege. This one tests the whole chain at once — the
    procedure, the trigger cascade, the RLS policies and a dozen SELECTs on tables no screen shows
    — by calling ``mainline.merge_permit`` on the seeded permit and asserting the refusal is the
    product's refusal (``23514`` / ``gate_closed_when_issued``) rather than a privilege error.

    A ``42501`` here would mean the login is short a grant, and it would surface in the middle of
    the demo's first beat, in front of a judge. The statement aborts on the refusal, so nothing is
    written; and if the database has not been seeded yet — ``cloud_roles.py`` runs BEFORE
    ``seed_demo.py`` in the deploy order — the probe reports that instead of failing, because "not
    seeded" and "not privileged" are different findings.
    """
    permit = "dec0de00-0006-4000-8000-000000000001"
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        row = conn.execute(
            "SELECT count(*) FROM mainline.permit WHERE permit_id = %s", (permit,)
        ).fetchone()
        if not (row and row[0]):
            return None
        import hashlib
        import json as _json

        payload = {"permit": permit, "merged_by": "demo.signer", "probe": "cloud_roles.gate"}
        canon = _json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            conn.execute(
                "CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    permit,
                    hashlib.sha256(b"mainline-demo/commit/roles-probe").digest(),
                    "demo.signer",
                    "human",
                    psycopg.types.json.Jsonb(payload),
                    canon,
                    1,
                    hashlib.sha256(b"\x00" + canon).digest(),
                ),
            )
        except psycopg.Error as exc:
            diag = getattr(exc, "diag", None)
            observed = sqlstate_of(exc)
            exhibit = (diag.constraint_name if diag is not None else None) or ""
            return {
                "probe": "drive the demo's first beat (CALL mainline.merge_permit)",
                "expected": "23514",
                "observed": observed,
                "agreed": observed == "23514" and exhibit == "gate_closed_when_issued",
                "detail": f"{exhibit or one_line(exc)[:70]}",
            }
        return {
            "probe": "drive the demo's first beat (CALL mainline.merge_permit)",
            "expected": "23514",
            "observed": "00000",
            "agreed": False,
            "detail": "the merge was ADMITTED — the gate did not refuse an open obligation",
        }
    finally:
        conn.close()


def api_expectations() -> list[tuple[str, str, str]]:
    return [
        (
            "read the gated subject (RLS must let it through)",
            "SELECT count(*) FROM mainline.permit",
            "00000",
        ),
        ("read the obligation", "SELECT count(*) FROM mainline.blocking_check", "00000"),
        ("read the corpus", "SELECT count(*) FROM mainline.clause_version", "00000"),
        ("read the recall pass", "SELECT count(*) FROM mainline_meas.recall_run", "00000"),
        (
            "read the audit surface",
            "SELECT count(*) FROM mainline_audit.v_open_gate_summary",
            "00000",
        ),
        (
            "mainline_qa is unreachable (S14)",
            "SELECT count(*) FROM mainline_qa.v_disposition_profile",
            REFUSED,
        ),
        (
            "mainline_qa per-person view is unreachable (S14)",
            "SELECT count(*) FROM mainline_qa.v_standing_components",
            REFUSED,
        ),
        ("no DELETE anywhere (MI01)", "DELETE FROM mainline.blocking_check WHERE false", REFUSED),
    ]


def judge_expectations() -> list[tuple[str, str, str]]:
    """What the judge login must and must not reach, at deploy time.

    THE NEGATIVES ARE NOT WRITTEN OUT HERE. They are derived from
    ``judge_access.NEGATIVE_PROBES``, which is the authority on what the published credential
    claims, so that adding an assertion there extends this deploy-time check automatically. Two
    hand-maintained copies of a security surface is the failure this module already refuses for
    ``AUDIT_VIEWS``, and the reason is the same: the copy that drifts is the one nobody re-reads.

    ``destructive`` probes — ``CREATE TABLE`` and ``DROP VIEW`` — are FILTERED OUT here and are
    proved by ``judge_access.py attest`` instead. That is not a gap being tolerated; it is where
    the guard lives. On CockroachDB a rolled-back transaction does not undo a schema change
    (measured, v26.2.5), so a ``DROP VIEW`` probe is only safe when an admin connection is holding
    the view's ``SHOW CREATE`` ready to rebuild it. ``run()`` below has no such connection open at
    probe time, and a destructive probe issued without a repair in hand is a worse deployment
    check than no probe at all.
    """
    positives = [
        (
            "read the audit surface",
            "SELECT count(*) FROM mainline_audit.v_open_gate_summary",
            "00000",
        ),
        (
            "read the silence summary",
            "SELECT count(*) FROM mainline_audit.v_silence_summary",
            "00000",
        ),
        ("read the conservation law", "SELECT count(*) FROM mainline_audit.v_cbm_ledger", "00000"),
        ("the corpus is unreachable", "SELECT count(*) FROM mainline.clause_version", REFUSED),
        ("mainline_meas is unreachable", "SELECT count(*) FROM mainline_meas.recall_run", REFUSED),
    ]
    try:
        from scripts.deploy.judge_access import NEGATIVE_PROBES
    except ImportError:  # pragma: no cover - judge_access absent; the local list still applies
        return [
            *positives,
            ("the base tables are unreachable", "SELECT count(*) FROM mainline.permit", REFUSED),
            (
                "mainline_qa is unreachable (S14)",
                "SELECT count(*) FROM mainline_qa.v_disposition_profile",
                REFUSED,
            ),
            (
                "no write path exists",
                "INSERT INTO mainline.refusal_ledger (spec_version) VALUES ('x')",
                REFUSED,
            ),
        ]
    derived = [
        (f"{probe['category']}: {probe['target']}", str(probe["sql"]), REFUSED)
        for probe in NEGATIVE_PROBES
        if probe["category"] != "create_table" and probe["category"] != "drop_view"
    ]
    return [*positives, *derived]


# One branch per PRINCIPAL and per OUTCOME. This function's whole output is a report a human
# reads before handing a credential to a judge, and every branch below writes a different
# sentence into it: created, rotated, left alone, skipped because the object is absent, skipped
# because no password was minted, agreed, disagreed. A loop over a table would flatten those into
# one message and lose the distinction the report exists to draw.
def run(args: argparse.Namespace) -> int:  # noqa: PLR0912, PLR0915
    admin_dsn = rewrite_dsn(
        args.dsn, database=args.database, application_name="mainline-deploy-roles"
    )
    conn = psycopg.connect(admin_dsn, autocommit=True)
    who = conn.execute("SELECT current_user").fetchone()
    print(f"cluster       {cluster_label(args.dsn)}")
    print(f"database      {args.database}  (as {who[0] if who else '?'})")

    issued: dict[str, str | None] = {}
    if not args.verify:
        issued, log = provision(conn, args.database, rotate=args.rotate)
        skipped = [entry for entry in log if entry.get("skipped")]
        failed = [entry for entry in log if entry.get("ok") is False]
        print(
            f"statements    {len(log)} issued, {len(skipped)} skipped (absent object), "
            f"{len(failed)} failed"
        )
        for entry in skipped:
            print(f"  - skipped   {entry['note']}  [{entry['sqlstate']}]")
        for entry in failed:
            print(f"  ! FAILED    {entry['note']}  [{entry['sqlstate']}] {entry['error']}")
    else:
        print("statements    none (--verify)")
    conn.close()

    if args.verify and not args.password_from_env:
        print()
        print("--verify needs each login's password to connect AS that login. Set")
        print("  MAINLINE_API_PASSWORD and MAINLINE_JUDGE_PASSWORD, and pass --password-from-env.")
        return EXIT_OK

    passwords = {
        API_USER: os.environ.get("MAINLINE_API_PASSWORD")
        if args.password_from_env
        else issued.get(API_USER),
        JUDGE_USER: os.environ.get("MAINLINE_JUDGE_PASSWORD")
        if args.password_from_env
        else issued.get(JUDGE_USER),
    }

    disagreed = 0
    for user, expectations in (
        (API_USER, api_expectations()),
        (JUDGE_USER, judge_expectations()),
    ):
        password = passwords[user]
        print()
        if password is None:
            print(f"probes        {user}: SKIPPED — this run did not mint a password, so it")
            print(f"              cannot connect as {user}. Re-run with --rotate to reissue, or")
            print("              export the password and pass --password-from-env.")
            continue
        insecure = "  (no password, insecure cluster)" if not password else ""
        print(f"probes        {user}{insecure}")
        login_dsn = as_user(args.dsn, user, password, args.database)
        try:
            results = probe(login_dsn, expectations)
            if user == API_USER:
                gate = gate_probe(login_dsn)
                if gate is None:
                    print(
                        "  -- skipped  drive the demo's first beat — the demo permit is not "
                        "seeded yet (run seed_demo.py, then --verify)"
                    )
                else:
                    results.append(gate)
        except psycopg.OperationalError as exc:
            print(f"  ! could not connect as {user}: {one_line(exc)}")
            disagreed += 1
            continue
        for result in results:
            mark = "ok " if result["agreed"] else "!! "
            print(
                f"  {mark}[{result['observed']:<5}] expected [{result['expected']:<5}] "
                f"{result['probe']}  {result['detail'][:70]}"
            )
            if not result["agreed"]:
                disagreed += 1

    print()
    for user, password in issued.items():
        if password:
            print(f"PASSWORD  {user}  {password}")
    if any(issued.values()):
        print()
        print("Those two lines are the only place these secrets are ever printed. They are not")
        print("written to any file by this program and are not in any evidence artefact. Put them")
        print("in SSM Parameter Store as SecureStrings now:")
        print("  aws ssm put-parameter --name /mainline-demo/db/api-dsn  --type SecureString ...")
        print("  aws ssm put-parameter --name /mainline-demo/db/judge-dsn --type SecureString ...")
    print()
    verdict = "ROLES PROVISIONED" if disagreed == 0 else f"{disagreed} PROBE(S) DISAGREED"
    print(f"VERDICT       {verdict}")
    return EXIT_OK if disagreed == 0 else EXIT_PROBE_DISAGREED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloud_roles",
        description=(
            "Create mainline_api and mainline_judge, grant exactly what each needs, probe both."
        ),
    )
    parser.add_argument("--dsn", default=None, help="admin DSN (default: COCKROACH_DSN from .env)")
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument(
        "--rotate", action="store_true", help="issue new passwords even if the logins exist"
    )
    parser.add_argument("--verify", action="store_true", help="run the probes only; issue no DDL")
    parser.add_argument(
        "--password-from-env",
        action="store_true",
        help="take passwords from MAINLINE_API_PASSWORD / MAINLINE_JUDGE_PASSWORD",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    load_dotenv(root)
    args = build_parser().parse_args(argv)
    args.dsn = args.dsn or os.environ.get("COCKROACH_DSN")
    if not args.dsn:
        print(
            "cloud_roles: no DSN. Pass --dsn, or put COCKROACH_DSN in the repo-root .env.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        return run(args)
    except psycopg.OperationalError as exc:
        print(f"cloud_roles: could not reach the cluster: {one_line(exc)}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
