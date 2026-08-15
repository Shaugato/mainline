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

WHERE THE OBJECT LISTS COME FROM — AND WHY THEY ARE NO LONGER WRITTEN DOWN HERE
------------------------------------------------------------------------------
Until 2026-08-15 this module carried its own copy of what ``mainline_api`` may reach: five
tuples named ``API_READ``, ``API_GATE_READ``, ``API_WRITE``, ``AUDIT_VIEWS`` and
``API_MEMBERSHIPS``. **That copy drifted, and the drift was measured.** Eleven relations the
shipping demo-api references —

    mainline.control_failure   mainline.ledger_leaf         trappoint.deploy_chain
    mainline.defeater_option   mainline.ledger_node         trappoint.schema_attestation
    mainline.delta_witness     mainline.receipt_expiry      trappoint.schema_migration
    mainline.event_edge        mainline_meas.silence_ledger

— were granted BY HAND against the live cluster on 2026-08-14, during five outages, and were
never written back into this file. A rebuild from scratch would therefore have reproduced all
five. A second copy of a list is a second thing to drift, and this is the one list that already
did.

So the five names still exist, and they are **derived from** ``verticals/mainline/db/GRANTS.yaml``
— the declarative matrix this repository already owns, already parses with
``trappoint_migrate.grants``, already applies idempotently with ``trappoint migrate grants apply``
and already censuses in ``scripts/chain/apply_chain.py``. There is one authority for what these
logins may reach and this file is not it. Adding a relation to the matrix adds it here; there is
no second place to remember.

Two consequences a reader should know before they are surprised by them:

* **This program refuses to provision when the matrix does not declare the login.** It does not
  fall back to a built-in list, and it does not create a login that can reach nothing. Both of
  those are ways of turning a missing declaration into a silent outcome, and the outcome the
  operator needs is a sentence naming the file to edit.
* **The classification survives in the matrix, not here.** ``GRANTS.yaml`` rows may carry
  ``demand: gate_chain`` to say that a ``SELECT`` exists for the merge transaction's trigger
  cascade rather than for a screen. Rows that carry it become ``API_GATE_READ``; the rest become
  ``API_READ``. The GRANT statements are identical either way — the split is what the log and the
  regression guard read, not what the cluster is told.

HOW THE GATE-CHAIN READ SET WAS DISCOVERED, WHICH IS NOT RECOVERABLE FROM THE SCHEMA
-----------------------------------------------------------------------------------
This paragraph is provenance and it belongs with the deploy, so it stays here even though the
list itself has moved.

Every trigger function in migrations 0100-0149 executes as the INVOKING role — none is
``SECURITY DEFINER``, and ``GRANTS.yaml`` records that as an open coupling rather than hiding it —
so the merge transaction's trigger chain needs ``SELECT`` on tables no demo screen ever displays.
The method was a loop: run the three beats as ``mainline_api``, parse the ``42501``, grant exactly
the named privilege on the named relation, repeat until the beats produced their real outcomes.
Thirteen grants, in this order::

    UPDATE blocking_check · SELECT change_request · INSERT ledger_intake · SELECT identity_residue
    SELECT permit_boundary · SELECT permit_slice · SELECT override_ledger · SELECT unwitnessed_debt
    SELECT disposition_citation · SELECT mechanism_predicate · UPDATE change_request
    SELECT cr_clause · SELECT cr_event

The ``change_request`` rows are there because ``fn_disposition_close`` and
``fn_check_materialised`` branch on ``subject_kind`` and touch the change-request arm even when the
subject is a permit. Guessing this list from the ARCHITECTURE would have produced a login that
fails in the middle of the demo's second beat, in front of a judge, with a privilege error.

The same holds for the write set. ``mainline_ops.outbox`` is written by the INVOKING role because
``fn_check_materialised`` and ``fn_disposition_close`` insert into it as whoever called them;
``mainline.ledger_intake`` is written because ``merge_permit`` appends the merge to the custody log
in the same transaction — the demo's admission beat writes an audit trail or it does not happen at
all. And the ``mainline_audit`` views are enumerated by name in the matrix rather than wildcarded,
because ``GRANT … ON ALL TABLES IN SCHEMA`` would silently pick up whatever a later migration adds,
and the whole point of the judge login is that its reach is a closed list somebody reviewed.

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
* **No password, anywhere in ``GRANTS.yaml``.** The matrix is the authority on reach and this file
  is the authority on the credential. Neither borrows from the other.

Usage::

    .venv/Scripts/python.exe scripts/deploy/cloud_roles.py              # create, grant, verify
    .venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate     # new passwords
    .venv/Scripts/python.exe scripts/deploy/cloud_roles.py --verify     # probe only, no DDL

Exit codes:

* ``0`` — both logins exist, hold what they should, and the probes agreed.
* ``1`` — a probe disagreed: something is reachable that should not be, or unreachable that should.
* ``2`` — no DSN, no cluster, or the grant matrix does not declare these logins.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from collections.abc import Mapping
from dataclasses import dataclass
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

#: Never granted to either login. Re-revoked every run.
#:
#: This is a DENIAL, not a copy of a grant list, which is why it is still written here: the matrix
#: says what a role may reach and this says what is taken away afterwards regardless. S14. A
#: migration runs once; drift is additive and continuous.
FORBIDDEN_SCHEMAS: tuple[str, ...] = ("mainline_qa",)

#: The ONE grant the matrix cannot express, with the reason it cannot.
#:
#: ``GRANTS.yaml``'s identifier grammar is ``lower_snake`` with at most one dot
#: (``trappoint_migrate.grants._QUALIFIED``), so it can name ``mainline.merge_permit`` and it
#: cannot name ``mainline.merge_permit(UUID, BYTES, …)``. CockroachDB needs the argument list to
#: disambiguate an overload, so the SIGNATURE lives here and nothing else does. If the matrix ever
#: names an ``EXECUTE`` row for one of these logins, its object is taken from the matrix and its
#: signature is looked up in this table — a routine the matrix names and this table does not know
#: how to spell is a refusal, never a silently dropped grant.
ROUTINE_SIGNATURES: dict[str, str] = {
    "mainline.merge_permit": "(UUID, BYTES, STRING, STRING, JSONB, BYTES, INT2, BYTES)",
}

#: Granted unconditionally to ``mainline_api`` because the demo's first beat is a ``CALL`` of it.
#: One statement, not a list — see ``gate_probe`` below, which is the evidence that it works.
API_ROUTINES: tuple[str, ...] = ("mainline.merge_permit",)

#: Where the authority lives, relative to the repository root.
GRANTS_MATRIX_RELPATH = Path("verticals") / "mainline" / "db" / "GRANTS.yaml"

#: Sections of the matrix this program derives from. Each must appear in the matrix's own
#: ``apply_order``: a section outside it is NOT applied by ``trappoint migrate grants apply``, so
#: deriving from it would make this program and that command disagree about the same file.
DERIVED_SECTIONS: tuple[str, ...] = ("memberships", "schema_privileges", "table_privileges")

#: The privileges this program knows how to issue against a relation, by class.
_READ_PRIVILEGES: frozenset[str] = frozenset({"SELECT"})
_WRITE_PRIVILEGES: frozenset[str] = frozenset({"INSERT", "UPDATE"})
_ROUTINE_PRIVILEGES: frozenset[str] = frozenset({"EXECUTE"})

_AUDIT_SCHEMA = "mainline_audit"


class MatrixIncomplete(Exception):
    """The grant matrix does not carry what this program needs to provision a login.

    Raised rather than defaulted. A deploy script that substitutes a built-in list when the
    declaration is missing is a deploy script that hides the missing declaration, and the missing
    declaration is the defect.
    """


# ═════════════════════════════════════════════════════════════════════════════════════
# the matrix — one authority, read rather than restated
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class MatrixGrant:
    """One ``table_privileges`` row the matrix addresses to one of these two logins."""

    object: str
    privileges: tuple[str, ...]
    why: str
    gate_chain: bool


@dataclass(frozen=True, slots=True)
class SchemaGrant:
    """One ``schema_privileges`` row, expanded to a single schema."""

    schema: str
    privileges: tuple[str, ...]
    why: str


@dataclass(frozen=True, slots=True)
class Derived:
    """Everything this program grants, read out of ``GRANTS.yaml``.

    ``declared`` is false when the matrix names neither login. The lists are then EMPTY — not
    substituted, not guessed — and :func:`grant_plan` refuses. ``status`` is the sentence an
    operator is shown.
    """

    source: Path
    declared: bool
    status: str
    api_schemas: tuple[SchemaGrant, ...]
    api_memberships: tuple[tuple[str, str], ...]
    api_tables: tuple[MatrixGrant, ...]
    judge_schemas: tuple[SchemaGrant, ...]
    judge_tables: tuple[MatrixGrant, ...]


def matrix_path() -> Path:
    """The committed grant matrix — the single authority on what these logins may reach."""
    return repo_root() / GRANTS_MATRIX_RELPATH


def load_document(path: Path) -> Mapping[str, Any]:
    """Parse the matrix with ``trappoint_migrate.grants``, never with a second YAML reader.

    A second parser is a second set of rules about what the file means, and the file's header is
    explicit that ``grants apply`` is its contract.

    EVERY way of failing to read the matrix becomes :class:`MatrixIncomplete`, including a YAML
    syntax error. That is not swallowing the fault — the message carries the parser's own words
    and the path — it is refusing to let an unreadable matrix arrive as a traceback from
    somewhere else. ``scripts/deploy/judge_access.py`` imports this module for one constant, and
    a half-written matrix must not turn that import into a scanner error at collection time.

    Raises:
        MatrixIncomplete: the parser is unavailable, or the file is absent, unreadable, or not
            valid YAML.
    """
    try:
        from trappoint_migrate.grants import load_matrix
    except ImportError as exc:
        raise MatrixIncomplete(
            "cannot read the grant matrix: `trappoint_migrate` is not importable in this "
            "environment. Install the workspace (`uv sync`) or run this from the repository "
            "root with the project's .venv. This program does not carry a fallback copy of "
            "what the logins may reach, deliberately."
        ) from exc
    from trappoint_migrate.errors import UsageError

    try:
        import yaml

        parse_errors: tuple[type[BaseException], ...] = (yaml.YAMLError,)
    except ImportError:  # pragma: no cover - PyYAML absent; load_matrix says so itself
        parse_errors = ()

    try:
        return load_matrix(path)
    except (UsageError, OSError, ValueError, *parse_errors) as exc:
        raise MatrixIncomplete(
            f"{path} could not be read as a grant matrix — {one_line(exc)}"
        ) from exc


def _section(document: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    raw = document.get(name)
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, Mapping)]


def _why(row: Mapping[str, Any]) -> str:
    """The matrix's own sentence for this row, flattened to one line.

    ``why`` first, then ``note``, then ``purpose``: all three spellings are in the committed file
    and all three are the same thing to an operator reading a deploy log.
    """
    for key in ("why", "note", "purpose"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
    return ""


def _privileges(row: Mapping[str, Any]) -> tuple[str, ...]:
    raw = row.get("privileges")
    if not isinstance(raw, list):
        return ()
    return tuple(str(item).upper() for item in raw if isinstance(item, str))


def _is_gate_chain(row: Mapping[str, Any]) -> bool:
    """Whether this ``SELECT`` exists for the merge transaction's trigger cascade.

    Two spellings accepted, both ignored by ``grants apply`` (its contract says unknown keys are
    ignored, so a documentation field is legal): ``demand: gate_chain`` or ``gate_chain: true``.
    An unmarked row is a read-surface row. The GRANT is the same either way — this only decides
    which of ``API_READ`` / ``API_GATE_READ`` the object lands in, and therefore what the log and
    ``scripts/qa/regression_guard.py`` call it.
    """
    if row.get("gate_chain") is True:
        return True
    return str(row.get("demand", "")).strip().lower() == "gate_chain"


def _schema_grants(document: Mapping[str, Any], role: str) -> tuple[SchemaGrant, ...]:
    out: list[SchemaGrant] = []
    for row in _section(document, "schema_privileges"):
        if row.get("role") != role:
            continue
        schemas = row.get("schemas")
        if not isinstance(schemas, list):
            continue
        why = _why(row)
        privileges = _privileges(row)
        out.extend(
            SchemaGrant(schema=str(schema), privileges=privileges, why=why)
            for schema in schemas
            if isinstance(schema, str)
        )
    return tuple(out)


def _memberships(document: Mapping[str, Any], member: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(row["role"]), _why(row))
        for row in _section(document, "memberships")
        if row.get("member") == member and isinstance(row.get("role"), str)
    )


def _table_grants(document: Mapping[str, Any], role: str) -> tuple[MatrixGrant, ...]:
    return tuple(
        MatrixGrant(
            object=str(row["object"]),
            privileges=_privileges(row),
            why=_why(row),
            gate_chain=_is_gate_chain(row),
        )
        for row in _section(document, "table_privileges")
        if row.get("role") == role and isinstance(row.get("object"), str)
    )


def _declared_roles(document: Mapping[str, Any]) -> set[str]:
    return {
        str(row["name"]) for row in _section(document, "roles") if isinstance(row.get("name"), str)
    }


def derive(path: Path | None = None) -> Derived:
    """Read the matrix and return what these two logins may reach.

    Raises:
        MatrixIncomplete: the matrix cannot be read, or it declares a section this program
            derives from that its own ``apply_order`` does not apply. The second case matters:
            a row in an unapplied section is a grant ``trappoint migrate grants apply`` would
            never make, so honouring it here would put the two out of step on one file.
    """
    source = path or matrix_path()
    document = load_document(source)

    order = document.get("apply_order")
    ordered = {str(name) for name in order} if isinstance(order, list) else set()
    unapplied = [name for name in DERIVED_SECTIONS if name in document and name not in ordered]
    if unapplied:
        raise MatrixIncomplete(
            f"{source}: section(s) {', '.join(unapplied)} carry grants but are absent from "
            "apply_order, so `trappoint migrate grants apply` would not apply them. This "
            "program will not apply what that command would not."
        )

    roles = _declared_roles(document)
    missing = [name for name in (API_USER, JUDGE_USER) if name not in roles]
    if missing:
        return Derived(
            source=source,
            declared=False,
            status=(
                f"{source} declares no role named {' or '.join(missing)}. The privilege surface "
                "of the login an anonymous caller on the public Function URL executes as is not "
                "in the matrix, so there is nothing here to derive and nothing will be granted. "
                "Declare it in GRANTS.yaml (roles / memberships / schema_privileges / "
                "table_privileges) and re-run."
            ),
            api_schemas=(),
            api_memberships=(),
            api_tables=(),
            judge_schemas=(),
            judge_tables=(),
        )

    api_tables = _table_grants(document, API_USER)
    return Derived(
        source=source,
        declared=True,
        status=f"{source.name}: both logins declared",
        api_schemas=_schema_grants(document, API_USER),
        api_memberships=_memberships(document, API_USER),
        api_tables=api_tables,
        judge_schemas=_schema_grants(document, JUDGE_USER),
        judge_tables=_table_grants(document, JUDGE_USER),
    )


def _empty(source: Path, status: str) -> Derived:
    return Derived(
        source=source,
        declared=False,
        status=status,
        api_schemas=(),
        api_memberships=(),
        api_tables=(),
        judge_schemas=(),
        judge_tables=(),
    )


def _derive_at_import() -> Derived:
    """Derive once, at import, without ever letting a missing declaration raise here.

    The five module constants below are read by ``scripts/deploy/judge_access.py`` and by
    operator tooling. An import that raises would take those down for a reason that belongs to
    the matrix rather than to them. So the constants go EMPTY and carry the reason in
    :data:`MATRIX_STATUS`, and the refusal happens where it has consequences — in
    :func:`grant_plan`, which is what issues DDL.
    """
    source = matrix_path()
    try:
        return derive(source)
    except MatrixIncomplete as exc:
        return _empty(source, one_line(exc))


MATRIX = _derive_at_import()

#: True when ``GRANTS.yaml`` declares both logins. False means every list below is empty because
#: the matrix says nothing, not because anything was dropped.
MATRIX_DECLARES_LOGINS: bool = MATRIX.declared

#: Why, in one sentence, for an operator who is looking at an empty list.
MATRIX_STATUS: str = MATRIX.status


def _api_selects(derived: Derived) -> tuple[MatrixGrant, ...]:
    return tuple(g for g in derived.api_tables if _READ_PRIVILEGES & set(g.privileges))


def _audit_views(role_tables: tuple[MatrixGrant, ...]) -> tuple[str, ...]:
    return tuple(
        g.object.split(".", 1)[1]
        for g in role_tables
        if g.object.startswith(f"{_AUDIT_SCHEMA}.") and _READ_PRIVILEGES & set(g.privileges)
    )


#: The audit surface, derived. Fourteen views on the committed matrix, enumerated there by name
#: rather than wildcarded, because ``GRANT … ON ALL TABLES IN SCHEMA`` would silently pick up
#: whatever a later migration adds — and the whole point of the judge login is that its reach is a
#: closed list somebody reviewed. ``scripts/deploy/judge_access.py`` compares its own copy against
#: this one at provision time and refuses when they differ.
AUDIT_VIEWS: tuple[str, ...] = _audit_views(MATRIX.api_tables)

#: What the demo's read surfaces touch. Every one of these is on the path from "show me the
#: permit" to "show me the precursor that obliged it and the pass that found it".
API_READ: tuple[str, ...] = tuple(
    g.object
    for g in _api_selects(MATRIX)
    if not g.object.startswith(f"{_AUDIT_SCHEMA}.") and not g.gate_chain
)

#: What the GATE TRANSACTION reads, which is not the same list as what the read resources read —
#: see the module docstring for how it was discovered, one ``42501`` at a time. The membership is
#: the matrix's ``demand: gate_chain`` rows.
#:
#: ONE CONSUMER STILL READS THIS BY PARSING THIS FILE, AND IT NO LONGER MATCHES — SAY SO RATHER
#: THAN LET IT GO QUIET. ``scripts/qa/regression_guard.py``'s ``gate_chain_reads`` (line 827)
#: ``ast.literal_eval``s the right-hand side of this assignment, which was a literal tuple until
#: 2026-08-15 and is now a comprehension. It returns ``[]``, and its ``gate_chain`` check is
#: ``not gate_denied`` — so an empty list makes that check PASS while asserting nothing, with
#: ``0 tables from cloud_roles.py:API_GATE_READ`` in its own detail line. That guard is not this
#: module's file to edit. The repair is one function, and it is the same lesson as this refactor:
#: read the ``demand: gate_chain`` rows out of ``GRANTS.yaml`` instead of parsing a Python
#: literal out of a deploy script. Until it lands, ``docs/regression/GUARD.md``'s plant P4 (a
#: temp copy of this file with a bogus relation added to this tuple) no longer discriminates
#: either, and P4 should become a planted matrix row.
API_GATE_READ: tuple[str, ...] = tuple(
    g.object
    for g in _api_selects(MATRIX)
    if not g.object.startswith(f"{_AUDIT_SCHEMA}.") and g.gate_chain
)

#: What the three beats WRITE. Every entry is a statement the demo actually issues, or a write a
#: trigger performs as the invoking role.
API_WRITE: tuple[tuple[str, str], ...] = tuple(
    (g.object, privilege)
    for g in MATRIX.api_tables
    for privilege in g.privileges
    if privilege in _WRITE_PRIVILEGES
)

#: For RLS scope, not for privileges. See the module docstring.
API_MEMBERSHIPS: tuple[str, ...] = tuple(role for role, _ in MATRIX.api_memberships)


# ═════════════════════════════════════════════════════════════════════════════════════
# the plan — every statement, with the sentence the operator reads
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Planned:
    """One statement the provisioning run will issue.

    ``note`` is what reaches the operator's terminal when the statement is skipped or fails. It
    names the class the grant belongs to AND carries the matrix's own ``why`` for the row, so a
    log line reading "SELECT on mainline.cr_event" still says that it exists because a trigger
    branches on ``subject_kind``. A bare (role, object, privilege) triple would not.
    """

    sql: str
    note: str
    kind: str


_WHY_LIMIT = 200


def _note(user: str, headline: str, why: str) -> str:
    if not why:
        return f"{user}: {headline}"
    return f"{user}: {headline} - {why[:_WHY_LIMIT]}"


def printable(text: str) -> str:
    """Fold *text* to what THIS terminal can actually encode.

    The matrix's ``why`` text is prose, and this repository's prose uses ``—``, ``§`` and curly
    quotes. A Windows ``cp1252`` console raises ``UnicodeEncodeError`` on all three, and
    ``trappoint_migrate.grants.GrantPlan.render`` already carries the same rule for the same
    reason: *a plan that cannot be printed is a plan nobody reviews.* A deploy that dies while
    printing a WARNING about a skipped grant is strictly worse than the warning.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return text.encode(encoding, "replace").decode(encoding, "replace")
    return text


def _routine_statements(user: str, derived: Derived) -> list[Planned]:
    """``EXECUTE`` grants: objects from the matrix where it names them, always the merge procedure.

    Raises:
        MatrixIncomplete: the matrix names an ``EXECUTE`` row whose signature this module cannot
            spell. Refused rather than skipped — a dropped ``EXECUTE`` surfaces as a ``42501`` in
            the middle of the demo's first beat, in front of a judge.
    """
    named = {g.object: g.why for g in derived.api_tables if _ROUTINE_PRIVILEGES & set(g.privileges)}
    unknown = sorted(set(named) - set(ROUTINE_SIGNATURES))
    if unknown:
        raise MatrixIncomplete(
            f"{derived.source} grants EXECUTE on {', '.join(unknown)}, and cloud_roles.py holds "
            "no argument signature for it. CockroachDB needs the argument list to disambiguate "
            "an overload and the matrix's identifier grammar cannot carry one, so add the "
            "signature to ROUTINE_SIGNATURES rather than letting the grant be dropped."
        )
    for name in API_ROUTINES:
        named.setdefault(name, "the demo's first beat is a CALL of it")
    return [
        Planned(
            sql=(f'GRANT EXECUTE ON PROCEDURE {routine}{ROUTINE_SIGNATURES[routine]} TO "{user}"'),
            note=_note(user, f"EXECUTE on {routine}", named[routine]),
            kind="routine",
        )
        for routine in sorted(named)
    ]


def _relation_statements(user: str, tables: tuple[MatrixGrant, ...]) -> list[Planned]:
    """One statement per (object, privilege), in matrix order, each carrying its own reason.

    The classes are not merged away. ``kind`` distinguishes the read surface, the gate trigger
    chain, the audit views and the writes, exactly as the four separate loops used to — the
    difference is that the membership of each class is now read out of the matrix instead of
    being restated here.
    """
    out: list[Planned] = []
    for grant in tables:
        audit = grant.object.startswith(f"{_AUDIT_SCHEMA}.")
        for privilege in grant.privileges:
            if privilege in _READ_PRIVILEGES:
                if audit:
                    kind, label = "audit", "audit surface"
                elif grant.gate_chain:
                    kind, label = "gate_read", "gate trigger chain"
                else:
                    kind, label = "read", "read resources"
            elif privilege in _WRITE_PRIVILEGES:
                kind, label = "write", "write path"
            else:
                continue  # EXECUTE is issued by _routine_statements, which knows the signature
            out.append(
                Planned(
                    sql=f'GRANT {privilege} ON TABLE {grant.object} TO "{user}"',
                    note=_note(user, f"{privilege} on {grant.object} ({label})", grant.why),
                    kind=kind,
                )
            )
    return out


def _judge_revocation_schemas(derived: Derived) -> tuple[str, ...]:
    """Schemas the judge may NAME and must read nothing in.

    MEASURED, AND NOT WHAT THE DOCUMENTATION LED ME TO EXPECT (CockroachDB CCL v26.2.5, local
    single node, 2026-08-10). A view runs the underlying query with its OWNER's table privileges —
    that is the fourth trap ``RLS-MATRIX.yaml`` names, and it holds. But the SCHEMA USAGE check is
    made against the INVOKER regardless::

        with USAGE on mainline_audit only:
          SELECT count(*) FROM mainline_audit.v_open_gate_summary
            → 42501  user mainline_judge does not have USAGE privilege on schema mainline

        with USAGE additionally on mainline, mainline_meas, mainline_ops:
          SELECT count(*) FROM mainline_audit.v_open_gate_summary   → OK, rows=1
          SELECT count(*) FROM mainline.permit
            → 42501  user mainline_judge does not have SELECT privilege on relation permit

    So the judge login needs USAGE on the schemas its views TRAVERSE, and gets no table privilege
    in any of them. USAGE is the right to name a schema; it is not the right to read anything in
    it, and the second probe above is the evidence rather than the assurance. ``mainline_qa`` is
    NOT among them and never will be: without USAGE the schema is not even nameable, which is a
    stronger position than a revoked SELECT.

    The set is therefore derived, not listed: every schema the judge holds USAGE on in which the
    matrix gives it no table privilege at all.
    """
    readable = {g.object.split(".", 1)[0] for g in derived.judge_tables if g.privileges}
    seen: list[str] = []
    for grant in derived.judge_schemas:
        if grant.schema not in readable and grant.schema not in seen:
            seen.append(grant.schema)
    return tuple(seen)


def grant_plan(derived: Derived | None = None) -> tuple[Planned, ...]:
    """Every statement this program issues after the two logins exist, in order.

    Pure: it touches no cluster, so the whole grant surface is inspectable — and testable — with
    no database anywhere. ``tests/deploy/test_cloud_roles_reads_the_matrix.py`` reads the object
    names back out of this SQL and diffs them against ``GRANTS.yaml`` by an independent path.

    Raises:
        MatrixIncomplete: the matrix does not declare these logins. Refused rather than defaulted;
            see :class:`MatrixIncomplete`.
    """
    matrix = derived if derived is not None else MATRIX
    if not matrix.declared:
        raise MatrixIncomplete(matrix.status)

    plan: list[Planned] = []
    for grant in matrix.api_schemas:
        privileges = ", ".join(grant.privileges) or "USAGE"
        plan.append(
            Planned(
                sql=f'GRANT {privileges} ON SCHEMA {grant.schema} TO "{API_USER}"',
                note=_note(API_USER, f"{privileges} on schema {grant.schema}", grant.why),
                kind="schema",
            )
        )
    for role, why in matrix.api_memberships:
        plan.append(
            Planned(
                sql=f'GRANT "{role}" TO "{API_USER}"',
                note=_note(
                    API_USER,
                    f"member of {role} (for RLS policy scope, not privileges)",
                    why,
                ),
                kind="membership",
            )
        )
    plan.extend(_relation_statements(API_USER, matrix.api_tables))
    plan.extend(_routine_statements(API_USER, matrix))

    for grant in matrix.judge_schemas:
        privileges = ", ".join(grant.privileges) or "USAGE"
        traversal = "" if grant.schema == _AUDIT_SCHEMA else " (traversal only, no table privilege)"
        plan.append(
            Planned(
                sql=f'GRANT {privileges} ON SCHEMA {grant.schema} TO "{JUDGE_USER}"',
                note=_note(
                    JUDGE_USER, f"{privileges} on schema {grant.schema}{traversal}", grant.why
                ),
                kind="schema",
            )
        )
    plan.extend(_relation_statements(JUDGE_USER, matrix.judge_tables))

    # ── the revocations, re-asserted, because drift is additive ──────────────────────────────
    for user in (API_USER, JUDGE_USER):
        for schema in FORBIDDEN_SCHEMAS:
            plan.append(
                Planned(
                    sql=f'REVOKE ALL ON SCHEMA {schema} FROM "{user}"',
                    note=f"{user}: REVOKE ALL on schema {schema} (S14)",
                    kind="revocation",
                )
            )
            plan.append(
                Planned(
                    sql=f'REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM "{user}"',
                    note=f"{user}: REVOKE ALL on every view in {schema} (S14)",
                    kind="revocation",
                )
            )
    for schema in _judge_revocation_schemas(matrix):
        plan.append(
            Planned(
                sql=f'REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM "{JUDGE_USER}"',
                note=(
                    f"{JUDGE_USER}: REVOKE ALL on every table in {schema} — the login may NAME "
                    "these schemas so its views can traverse them, and may read nothing in them"
                ),
                kind="revocation",
            )
        )
    return tuple(plan)


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


# The login lifecycle is the ONE thing this file is still the authority on. Every branch below
# writes a different sentence into the report a human reads before handing a credential to a
# judge: created, rotated, left alone, created without a password because the cluster is
# insecure. The grants that follow come from the matrix and each carries its own `note`, so the
# operator's terminal still names the reason for every statement.
def provision(
    conn: psycopg.Connection[Any],
    database: str,
    *,
    rotate: bool,
    derived: Derived | None = None,
) -> tuple[dict[str, str | None], list[dict[str, Any]]]:
    """Create both logins and assert every privilege the matrix declares. Idempotent.

    A password is set only when the login is CREATED, or when ``--rotate`` says so. Re-running
    this program against a live deployment must not invalidate the credential the Lambda is
    already using; a deploy script that silently rotates a secret is a deploy script that takes
    the demo down every time somebody re-runs it.

    Raises:
        MatrixIncomplete: the matrix does not declare these logins. Raised BEFORE any DDL, so a
            run that cannot grant correctly does not create a login either.
    """
    plan = grant_plan(derived)  # refuses before the first CREATE USER, deliberately

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

    log.extend(apply_statement(conn, item.sql, note=item.note) for item in plan)
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
    the grant lists, and the reason is the same: the copy that drifts is the one nobody re-reads.

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


def _print_matrix_summary(matrix: Derived) -> None:
    """Say where the object lists came from, and how many of each, before anything is issued."""
    print(f"matrix        {matrix.source}")
    if not matrix.declared:
        print(f"              {matrix.status}")
        return
    print(
        f"              {API_USER}: {len(API_READ)} read, {len(API_GATE_READ)} gate-chain, "
        f"{len(AUDIT_VIEWS)} audit view(s), {len(API_WRITE)} write(s), "
        f"{len(API_MEMBERSHIPS)} membership(s)"
    )


# One branch per PRINCIPAL and per OUTCOME. This function's whole output is a report a human
# reads before handing a credential to a judge, and every branch below writes a different
# sentence into it: created, rotated, left alone, skipped because the object is absent, skipped
# because no password was minted, agreed, disagreed. A loop over a table would flatten those into
# one message and lose the distinction the report exists to draw.
def run(args: argparse.Namespace) -> int:  # noqa: PLR0912, PLR0915
    matrix = derive(args.grants) if args.grants else MATRIX
    admin_dsn = rewrite_dsn(
        args.dsn, database=args.database, application_name="mainline-deploy-roles"
    )
    conn = psycopg.connect(admin_dsn, autocommit=True)
    who = conn.execute("SELECT current_user").fetchone()
    print(f"cluster       {cluster_label(args.dsn)}")
    print(f"database      {args.database}  (as {who[0] if who else '?'})")
    _print_matrix_summary(matrix)

    issued: dict[str, str | None] = {}
    if not args.verify:
        try:
            issued, log = provision(conn, args.database, rotate=args.rotate, derived=matrix)
        except MatrixIncomplete as exc:
            conn.close()
            print()
            print(f"REFUSED       {one_line(exc)}")
            print(
                "              No DDL was issued. This program derives what these logins may "
                "reach from the grant matrix and carries no second copy of it, so a login it "
                "cannot grant correctly is a login it will not create."
            )
            return EXIT_USAGE
        skipped = [entry for entry in log if entry.get("skipped")]
        failed = [entry for entry in log if entry.get("ok") is False]
        print(
            f"statements    {len(log)} issued, {len(skipped)} skipped (absent object), "
            f"{len(failed)} failed"
        )
        for entry in skipped:
            print(printable(f"  - skipped   {entry['note']}  [{entry['sqlstate']}]"))
        for entry in failed:
            print(
                printable(f"  ! FAILED    {entry['note']}  [{entry['sqlstate']}] {entry['error']}")
            )
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
            "Create mainline_api and mainline_judge, grant exactly what GRANTS.yaml declares "
            "each may reach, probe both."
        ),
    )
    parser.add_argument("--dsn", default=None, help="admin DSN (default: COCKROACH_DSN from .env)")
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument(
        "--grants",
        type=Path,
        default=None,
        help="path to the grant matrix (default: verticals/mainline/db/GRANTS.yaml)",
    )
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
    except MatrixIncomplete as exc:
        print(f"cloud_roles: {one_line(exc)}", file=sys.stderr)
        return EXIT_USAGE
    except psycopg.OperationalError as exc:
        print(f"cloud_roles: could not reach the cluster: {one_line(exc)}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
