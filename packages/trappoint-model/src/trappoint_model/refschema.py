# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Putting the REAL substrate SQL on a cluster, and saying exactly what was stood in for.

The differential is worthless against a schema this package wrote. It applies
``packages/trappoint-sql/refvertical/sql/`` — the reference vertical, rendered from the
same templates the MAINLINE binding renders from — file by file, in lexicographic order,
one statement per file, exactly as ``trappoint migrate`` would.

**THE GAP, STATED FIRST.** Measured on CockroachDB v26.2.5 on 2026-08-09: the reference
vertical's own file list does not contain six relations its rendered SQL names. Applying
the tree alone leaves 23 of 109 files unapplied, and the unapplied set includes
``blocking_check``, ``disposition``, both merge procedures and both merge-gate triggers —
that is, the entire gate. The missing relations are:

===============================================  ==============================================
Relation                                         Named by
===============================================  ==============================================
``trappoint_ref.event``                          ``blocking_check.precursor_event_id`` FK (0058)
``trappoint_ref.clause``                         ``disposition.compensating_clause_uuid`` (0066)
``trappoint_ref.site``                           ``fn_closure_guard`` / ``fn_site_role``
``trappoint_ref.ledger_intake``                  ``fn_closure_guard``'s in-transaction ledger row
``trappoint_ref.event_severity_revision``        ``fn_closure_guard``'s downgrade test
``trappoint_ref_meas.recall_policy``             ``fn_disposition_project`` step 8
===============================================  ==============================================

:data:`STANDINS` supplies each one and **nothing else**. Every stand-in is a *dependency*
of a mechanism, never a mechanism: not one of them carries a CHECK, a trigger or a
foreign key that the gate consults. Whether the reference vertical should ship these
itself is the render worker's call, not this package's — a differential that hand-edited
the tree under test would be asserting its own behaviour. The list is asserted for size
by ``tests/test_refschema.py`` so that a stand-in cannot be quietly grown into a
mechanism.

``trappoint`` (the bootstrap schema, ruling D6) is created here for the same reason:
``0119a_fn_explain_refusal.sql`` creates ``trappoint.explain_refusal`` and
``trappoint migrate bootstrap`` — which is outside the numbered sequence — is what
normally creates the schema.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg

__all__ = [
    "REF_SQL_DIR",
    "SCHEMA",
    "STANDINS",
    "Fixture",
    "apply_reference_vertical",
    "drop_database",
    "scratch_database",
    "seed_clause_version",
    "seed_fixture",
    "tree_files",
]

#: The schema every object under test lives in.
SCHEMA = "trappoint_ref"

#: The rendered reference vertical. Resolved from this file so a checkout anywhere works.
REF_SQL_DIR = (
    Path(__file__).resolve().parents[4] / "packages" / "trappoint-sql" / "refvertical" / "sql"
)

#: Applied immediately before ``0038_clause_blame_closure.sql`` — after every schema and
#: type exists and before the first file that needs any of them.
_STANDIN_ANCHOR = "0038_clause_blame_closure.sql"

STANDINS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS trappoint",
    # The precursor an obligation points at. In MAINLINE this is 0033_event.sql; the gate
    # reads nothing from it and every generated check leaves the column NULL.
    (
        f"CREATE TABLE {SCHEMA}.event (event_id UUID NOT NULL PRIMARY KEY, "
        "site_id UUID NOT NULL, occurred_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    ),
    # The compensating-clause target. MAINLINE 0028_clause.sql.
    (
        f"CREATE TABLE {SCHEMA}.clause (clause_uuid UUID NOT NULL PRIMARY KEY, "
        "site_id UUID NOT NULL)"
    ),
    # The tenancy row every projection reads its scope token out of. MAINLINE 0020a_site.sql.
    (
        f"CREATE TABLE {SCHEMA}.site (site_id UUID NOT NULL PRIMARY KEY, "
        "site_code STRING NOT NULL, site_role NAME NOT NULL)"
    ),
    # The custody intake the closure guard writes into. MAINLINE 0072_ledger_intake.sql.
    (
        f"CREATE TABLE {SCHEMA}.ledger_intake ("
        "intake_id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY, "
        "site_code STRING NOT NULL, entry_kind STRING NOT NULL, subject_id UUID NOT NULL, "
        "actor STRING NOT NULL, actor_kind STRING NOT NULL, payload JSONB NOT NULL, "
        "canon_bytes BYTES NOT NULL, payload_ver INT2 NOT NULL, leaf_hash BYTES NOT NULL, "
        "hlc DECIMAL NOT NULL)"
    ),
    # The signed second-rater revision a severity downgrade costs. MAINLINE 0036.
    (
        f"CREATE TABLE {SCHEMA}.event_severity_revision ("
        "revision_id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY, "
        "at TIMESTAMPTZ NOT NULL DEFAULT now())"
    ),
    # The reading-rate policy the disposition projection degrades from. MAINLINE 0080.
    (
        f"CREATE TABLE {SCHEMA}_meas.recall_policy ("
        "policy_version STRING NOT NULL PRIMARY KEY, tau JSONB NOT NULL)"
    ),
)


def tree_files() -> list[Path]:
    """Return the reference vertical's files, in apply order.

    Raises:
        FileNotFoundError: the rendered tree is absent, which is a repository fault and
            never something to skip past — a differential against nothing proves nothing.
    """
    if not REF_SQL_DIR.is_dir():
        raise FileNotFoundError(
            f"the rendered reference vertical is not at {REF_SQL_DIR}. "
            "Run `trappoint render` before the differential."
        )
    return sorted(REF_SQL_DIR.glob("*.sql"))


def _statements() -> Iterator[tuple[str, str]]:
    for path in tree_files():
        if path.name == _STANDIN_ANCHOR:
            for i, sql in enumerate(STANDINS):
                yield (f"<standin {i}>", sql)
        yield (path.name, path.read_text(encoding="utf-8"))


def apply_reference_vertical(dsn: str) -> None:
    """Apply the whole tree into the database *dsn* names, one statement at a time.

    Raises:
        RuntimeError: any file failed. The message names the file and the SQLSTATE,
            because a schema that half-applied is the one failure that must never be
            mistaken for a gate that refused.
    """
    with psycopg.connect(dsn, autocommit=True) as conn:
        for name, sql in _statements():
            try:
                conn.execute(sql)
            except psycopg.Error as exc:
                raise RuntimeError(
                    f"the reference vertical failed to apply at {name}: "
                    f"{exc.sqlstate} {str(exc).splitlines()[0]}"
                ) from exc


@dataclass(frozen=True, slots=True)
class Fixture:
    """One tenancy, seeded with everything a signature needs and nothing the gate reads.

    Every field here is an *input* to a mechanism. Not one of them is a projected column:
    a fixture that supplied a projected value would be testing the harness.
    """

    site_id: uuid.UUID
    site_code: str
    site_role: str
    signer_sub: str
    credential_id: bytes
    policy_version: str


#: The `substantive` CHECK on `disposition` requires at least this many characters of
#: rationale. Named rather than inlined so the assertion below reads as a contract.
MIN_RATIONALE_CHARS = 120

_RATIONALE = (
    "The ancestral control was written by an incident in which an isolation point was "
    "assumed dead and was not; the compensating measure named below is verbatim from the "
    "recommendation and has been verified in the field today."
)
# S101: a module-level contract check. A fixture whose rationale is too short would
# make every generated signature fail on `substantive`, and the differential would
# report a disagreement about the harness rather than about the gate.
assert len(_RATIONALE) >= MIN_RATIONALE_CHARS, (  # noqa: S101
    f"the `substantive` CHECK requires {MIN_RATIONALE_CHARS} characters of rationale"
)


def seed_fixture(conn: psycopg.Connection[Any], scope: str) -> Fixture:
    """Seed one tenancy and return its handles.

    Args:
        conn: an autocommit connection.
        scope: a short label; it becomes the site code and makes rows attributable to the
            test that wrote them.

    Returns:
        The fixture. ``issued_at`` on every exposure receipt is set an hour in the past by
        :func:`~trappoint_model.adapter.Adapter.sign_disposition`, so ``reading_floor_met``
        projects true and the reading-rate axis stays out of the differential — it is the
        conformance corpus's case, not this one's.
    """
    site_id = uuid.uuid4()
    signer = f"sub-{scope}"
    credential = uuid.uuid4().bytes
    policy = f"rp-{scope}"
    digest32 = b"\x11" * 32
    conn.execute(
        f"INSERT INTO {SCHEMA}.site (site_id, site_code, site_role) VALUES (%s, %s, %s)",  # noqa: S608
        (site_id, scope, f"site_{scope}"),
    )
    conn.execute(
        f"INSERT INTO {SCHEMA}_meas.recall_policy (policy_version, tau) VALUES (%s, %s)",  # noqa: S608
        (policy, '{"tau0": 5, "rho": 4}'),
    )
    conn.execute(
        f"INSERT INTO {SCHEMA}.person (signer_sub, effective_from, org, rank, "  # noqa: S608
        "competency_source_id, competency_sha256, competency_snapshot, identity_source, "
        "enrolment_assurance) VALUES (%s, now() - INTERVAL '1 day', %s, %s, %s, %s, %s, %s, %s)",
        (
            signer,
            "acme",
            5,
            uuid.uuid4(),
            digest32,
            '{"authorisations": ["ISOLATION_AUTHORITY"]}',
            "hr",
            "hr_system_of_record",
        ),
    )
    conn.execute(
        f"INSERT INTO {SCHEMA}.signing_credential (credential_id, signer_sub, public_key_cose, "  # noqa: S608
        "aaguid, transports, attachment, enrolment_assurance) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (
            credential,
            signer,
            b"\x02",
            b"\x03" * 16,
            ["usb"],
            "cross-platform",
            "hr_system_of_record",
        ),
    )
    return Fixture(
        site_id=site_id,
        site_code=scope,
        site_role=f"site_{scope}",
        signer_sub=signer,
        credential_id=credential,
        policy_version=policy,
    )


def seed_clause_version(
    conn: psycopg.Connection[Any], fixture: Fixture, virulence: str = "routine", severity: int = 2
) -> tuple[uuid.UUID, bytes]:
    """Write one clause version and its generation-zero blame closure.

    This is the **authority source** every projection on the gate path reads. Absence of
    the closure refuses the obligation with ``P0001`` — which is rule P-2 working, not a
    fixture failure, so the differential never generates the absence and the conformance
    corpus owns that case.
    """
    clause_uuid = uuid.uuid4()
    commit_id = uuid.uuid4().bytes + uuid.uuid4().bytes
    conn.execute(
        f"INSERT INTO {SCHEMA}.clause (clause_uuid, site_id) VALUES (%s, %s)",  # noqa: S608
        (clause_uuid, fixture.site_id),
    )
    conn.execute(
        f"INSERT INTO {SCHEMA}.clause_version (clause_uuid, commit_id, site_id, control_delta, "  # noqa: S608
        "body_sha256) VALUES (%s, %s, %s, %s, %s)",
        (clause_uuid, commit_id, fixture.site_id, "strengthen", b"\x22" * 32),
    )
    conn.execute(
        f"INSERT INTO {SCHEMA}.clause_blame_closure (clause_uuid, as_of_commit, closure_gen, "  # noqa: S608
        "site_id, ancestor_events, ancestor_count, max_severity, virulence, depth, computed_by, "
        "projector_ver) VALUES (%s, %s, 0, %s, %s, 0, %s, %s, 1, 'differential', 'v1')",
        (clause_uuid, commit_id, fixture.site_id, [], severity, virulence),
    )
    return clause_uuid, commit_id


def scratch_database(base_dsn: str, prefix: str = "trappoint_diff") -> tuple[str, str]:
    """Create a fresh database on *base_dsn* and return ``(dsn, name)``.

    A fresh database rather than a fresh ``site_id``: the differential disables and drops
    nothing, but it does apply DDL, and DDL is not tenanted.
    """
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    name = f"{prefix}_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(base_dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    # `conninfo_to_dict` is typed as returning heterogeneous values (the port is an
    # int) while `make_conninfo` wants strings, so the round trip is stringified here
    # rather than silenced with an ignore. A dropped key would produce a DSN that
    # quietly connected somewhere else, which is the one bug a scratch database must
    # not have.
    parts = {k: str(v) for k, v in conninfo_to_dict(base_dsn).items() if v is not None}
    parts["dbname"] = name
    return make_conninfo(**parts), name


def drop_database(base_dsn: str, name: str) -> None:
    """Drop a scratch database. Only ever called on one :func:`scratch_database` made."""
    with psycopg.connect(base_dsn, autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name} CASCADE")
