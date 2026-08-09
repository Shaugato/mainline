# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint migrate grants apply`` — the role matrix as re-asserted state, not history.

`docs/leads/datamodel.md` **DM-7**. Roles and grants leave the numbered migration set and
become a declarative matrix (``GRANTS.yaml``) that is applied idempotently, because:

* **A ``RESTORE`` into a new cluster does not carry role membership or grants.** A
  migration runs once. Grants have to be *re-asserted*, or the restore drill produces a
  cluster whose schema is right and whose privileges are absent — and the privileges are
  most of the security argument.
* **The real control is the privilege probe, not the DDL.** What makes the claim true is
  the test that asserts ``42501`` for every forbidden (role, object) pair, which is why
  ``GRANTS.yaml`` carries a ``denials:`` block: the negative space is *data*, exported by
  :func:`denials` and asserted by ``tests/integration/schema``. A grant matrix that only
  listed what is permitted would be a document about intentions.

DR-8 is the accepted cost: a freshly restored cluster is unusable until this runs. It is
accepted because the alternative — grants inside migrations — is a cluster that looks
correct and is not.

**Every identifier is validated before it reaches a statement.** ``GRANT`` has no
parameter placeholders for identifiers, so role names, schema names and object names are
interpolated. They come from a committed file rather than from a request, which is a
reason to be careful and not a reason to relax: :func:`_identifier` refuses anything that
is not ``lower_snake`` (optionally one dot for a schema-qualified object), and privileges
are matched against a closed set. A typo becomes a refusal here rather than a statement
somewhere else.

**PyYAML is imported dynamically, and that is deliberate.** This distribution declares
exactly one runtime dependency, ``psycopg``, because it writes the schema attestation in
the same connection discipline that writes the ledger and every extra dependency in that
path is another thing an opposing expert has to trust. ``ci.yml``'s repository-wide
sequence-ban job installs ``trappoint-migrate`` alone. So the parser is resolved at call
time and its absence produces a sentence naming the fix, rather than an import error at
the top of a module that ``lint`` also imports.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg

from .db import in_txn
from .errors import UsageError

__all__ = [
    "APPLY_ORDER",
    "ApplyResult",
    "Denial",
    "GrantPlan",
    "Statement",
    "apply",
    "default_matrix_path",
    "denials",
    "describe",
    "load_matrix",
    "plan",
]

#: Section → the order it is applied in when the matrix does not say. The matrix's own
#: ``apply_order`` wins; this is the fallback and the vocabulary of legal section names.
APPLY_ORDER: tuple[str, ...] = (
    "roles",
    "memberships",
    "schema_privileges",
    "table_privileges",
    "schema_wide",
    "default_privileges",
    "revocations",
)

# `lower_snake`, optionally one dot for `schema.object`. Deliberately narrower than SQL
# allows: every identifier in this system is lower_snake by convention, so a name that
# needs quoting is a name that is wrong.
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_QUALIFIED = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")

_PRIVILEGES: frozenset[str] = frozenset(
    {"SELECT", "INSERT", "UPDATE", "DELETE", "USAGE", "CREATE", "EXECUTE", "ZONECONFIG", "ALL"}
)
_OBJECT_TYPES: frozenset[str] = frozenset({"TABLES", "SEQUENCES", "TYPES", "SCHEMAS", "FUNCTIONS"})
_REVOKE_OBJECT_TYPES: frozenset[str] = frozenset({"SCHEMA", "TABLE", "DATABASE"})

#: A SQLSTATE is five characters. Named, so the check below reads as a claim about
#: SQLSTATEs rather than as an unexplained length comparison.
_SQLSTATE_LENGTH = 5

#: A grant against an object that does not exist yet. Reported as a *missing object*
#: rather than as a failure, when the caller asks for that, because during the build the
#: matrix legitimately runs ahead of the tree.
_MISSING_OBJECT_SQLSTATES: frozenset[str] = frozenset(
    {
        "42P01",  # undefined_table
        "42704",  # undefined_object
        "3F000",  # invalid_schema_name
    }
)


@dataclass(frozen=True, slots=True)
class Statement:
    """One idempotent statement, with the matrix row it came from."""

    section: str
    sql: str
    why: str

    def __str__(self) -> str:
        """Return the SQL itself — what a plan prints."""
        return self.sql


@dataclass(frozen=True, slots=True)
class Denial:
    """One row of the ``denials:`` block: what a role must NOT be able to do.

    Exported as data because the privilege-probe test is the control, and a test that
    re-typed the negative space would be asserting its own copy of it.
    """

    role: str
    forbidden: tuple[str, ...]
    scope: str
    expect_sqlstate: str
    why: str


@dataclass(frozen=True, slots=True)
class GrantPlan:
    """Every statement the matrix asks for, in application order."""

    source: Path
    statements: tuple[Statement, ...]
    unapplied_sections: tuple[str, ...]
    """Sections present in the matrix but absent from its ``apply_order``.

    Reported rather than applied and rather than ignored. ``subject_access_views`` is one
    today: it grants on a view whose migration number was revoked by MR-7, so applying it
    would fail on a correct cluster. Silence would make that a thing somebody discovers.
    """

    def render(self) -> str:
        """Return the whole plan as SQL a human can read, paste and diff.

        ASCII only. This is printed to a console whose encoding is not ours to choose —
        a Windows ``cp1252`` terminal raises ``UnicodeEncodeError`` on the box-drawing
        characters the rest of this repository's prose uses, and a plan that cannot be
        printed is a plan nobody reviews before applying it.
        """
        lines: list[str] = []
        current = ""
        for statement in self.statements:
            if statement.section != current:
                current = statement.section
                lines.extend(("", f"-- ---- {current} " + "-" * max(0, 60 - len(current))))
            lines.append(f"{statement.sql};")
        return "\n".join(lines).strip() + "\n"


def _yaml() -> ModuleType:
    """Resolve PyYAML at call time. See this module's docstring for why not at import."""
    try:
        return importlib.import_module("yaml")
    except ImportError as exc:
        raise UsageError(
            "reading GRANTS.yaml needs PyYAML, which `trappoint-migrate` deliberately "
            "does not declare: this distribution has exactly one runtime dependency "
            "(psycopg) because it writes the schema attestation in the same connection "
            "discipline as the ledger. Install it in the environment that runs `grants` "
            "— `uv sync --package mainline-mcp` brings it in — or run the command from "
            "the full workspace (`uv sync`)."
        ) from exc


def _identifier(value: object, *, where: str, qualified: bool = False) -> str:
    """Validate one identifier before it is interpolated into a statement."""
    if not isinstance(value, str):
        raise UsageError(f"{where}: expected an identifier, got {type(value).__name__}")
    pattern = _QUALIFIED if qualified else _IDENT
    if pattern.match(value) is None:
        shape = "schema.object" if qualified else "lower_snake"
        raise UsageError(
            f"{where}: {value!r} is not a {shape} identifier. GRANT has no placeholder "
            "for an identifier, so every name in this matrix is validated before it "
            "reaches a statement."
        )
    return value


def _privileges(value: object, *, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise UsageError(f"{where}: 'privileges' must be a non-empty list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.upper() not in _PRIVILEGES:
            raise UsageError(
                f"{where}: {item!r} is not a privilege this matrix may name. "
                f"Allowed: {sorted(_PRIVILEGES)}"
            )
        out.append(item.upper())
    return tuple(out)


def _rows(document: Mapping[str, Any], section: str) -> list[Mapping[str, Any]]:
    raw = document.get(section)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise UsageError(f"GRANTS.yaml: '{section}' must be a list, not {type(raw).__name__}")
    rows: list[Mapping[str, Any]] = []
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise UsageError(f"GRANTS.yaml: {section}[{index}] is not a mapping")
        rows.append(row)
    return rows


def load_matrix(path: Path) -> Mapping[str, Any]:
    """Parse ``GRANTS.yaml``.

    Raises:
        UsageError: when the file is absent, is not a mapping, or PyYAML is not installed.
    """
    if not path.is_file():
        raise UsageError(
            f"no grant matrix at {path}. Roles and grants are cluster state a RESTORE "
            "does not carry (DM-7), so they live in a matrix that is re-asserted rather "
            "than in a migration that ran once."
        )
    document: object = _yaml().safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise UsageError(f"{path}: the top level must be a mapping")
    return document


def _roles(document: Mapping[str, Any]) -> list[Statement]:
    out: list[Statement] = []
    for row in _rows(document, "roles"):
        name = _identifier(row.get("name"), where="roles[].name")
        login = row.get("login")
        if not isinstance(login, bool):
            raise UsageError(
                f"roles[{name}].login must be a boolean. Every role in this system is "
                "NOLOGIN unless it says otherwise, and 'unless it says otherwise' has to "
                "be a value rather than an omission."
            )
        clause = "LOGIN" if login else "NOLOGIN"
        out.append(
            Statement(
                section="roles",
                sql=f"CREATE ROLE IF NOT EXISTS {name} {clause}",
                why=str(row.get("purpose", "")).strip().splitlines()[0]
                if row.get("purpose")
                else "",
            )
        )
    return out


def _memberships(document: Mapping[str, Any]) -> list[Statement]:
    out: list[Statement] = []
    for row in _rows(document, "memberships"):
        role = _identifier(row.get("role"), where="memberships[].role")
        member = _identifier(row.get("member"), where="memberships[].member")
        out.append(
            Statement(
                section="memberships",
                sql=f"GRANT {role} TO {member}",
                why=str(row.get("why", "")),
            )
        )
    return out


def _schema_privileges(document: Mapping[str, Any]) -> list[Statement]:
    out: list[Statement] = []
    for row in _rows(document, "schema_privileges"):
        role = _identifier(row.get("role"), where="schema_privileges[].role")
        schemas = row.get("schemas")
        if not isinstance(schemas, list) or not schemas:
            raise UsageError(f"schema_privileges[{role}].schemas must be a non-empty list")
        names = ", ".join(
            _identifier(s, where=f"schema_privileges[{role}].schemas") for s in schemas
        )
        privileges = ", ".join(
            _privileges(row.get("privileges"), where=f"schema_privileges[{role}]")
        )
        out.append(
            Statement(
                section="schema_privileges",
                sql=f"GRANT {privileges} ON SCHEMA {names} TO {role}",
                why=str(row.get("why", "")),
            )
        )
    return out


def _table_privileges(document: Mapping[str, Any]) -> list[Statement]:
    out: list[Statement] = []
    for row in _rows(document, "table_privileges"):
        role = _identifier(row.get("role"), where="table_privileges[].role")
        obj = _identifier(
            row.get("object"), where=f"table_privileges[{role}].object", qualified=True
        )
        privileges = ", ".join(
            _privileges(row.get("privileges"), where=f"table_privileges[{role}]")
        )
        out.append(
            Statement(
                section="table_privileges",
                sql=f"GRANT {privileges} ON TABLE {obj} TO {role}",
                why=str(row.get("why", "")),
            )
        )
    return out


def _schema_wide(document: Mapping[str, Any]) -> list[Statement]:
    out: list[Statement] = []
    for row in _rows(document, "schema_wide"):
        role = _identifier(row.get("role"), where="schema_wide[].role")
        schema = _identifier(row.get("schema"), where=f"schema_wide[{role}].schema")
        privileges = ", ".join(_privileges(row.get("privileges"), where=f"schema_wide[{role}]"))
        out.append(
            Statement(
                section="schema_wide",
                sql=f"GRANT {privileges} ON ALL TABLES IN SCHEMA {schema} TO {role}",
                why=str(row.get("why", "")),
            )
        )
    return out


def _default_privileges(document: Mapping[str, Any]) -> list[Statement]:
    out: list[Statement] = []
    for row in _rows(document, "default_privileges"):
        for_role = _identifier(row.get("for_role"), where="default_privileges[].for_role")
        to_role = _identifier(row.get("to_role"), where="default_privileges[].to_role")
        schema = _identifier(row.get("schema"), where="default_privileges[].schema")
        object_type = row.get("object_type")
        if not isinstance(object_type, str) or object_type.upper() not in _OBJECT_TYPES:
            raise UsageError(
                f"default_privileges[{to_role}].object_type is {object_type!r}; allowed: "
                f"{sorted(_OBJECT_TYPES)}"
            )
        privileges = ", ".join(
            _privileges(row.get("privileges"), where=f"default_privileges[{to_role}]")
        )
        out.append(
            Statement(
                section="default_privileges",
                sql=(
                    f"ALTER DEFAULT PRIVILEGES FOR ROLE {for_role} IN SCHEMA {schema} "
                    f"GRANT {privileges} ON {object_type.upper()} TO {to_role}"
                ),
                why=str(row.get("why", "")),
            )
        )
    return out


def _revocations(document: Mapping[str, Any]) -> list[Statement]:
    out: list[Statement] = []
    for row in _rows(document, "revocations"):
        grantee = row.get("grantee")
        if grantee != "public" and not isinstance(grantee, str):
            raise UsageError("revocations[].grantee must be a role name or 'public'")
        grantee_sql = (
            "public" if grantee == "public" else _identifier(grantee, where="revocations[].grantee")
        )
        object_type = row.get("object_type")
        if not isinstance(object_type, str) or object_type.upper() not in _REVOKE_OBJECT_TYPES:
            raise UsageError(
                f"revocations[].object_type is {object_type!r}; allowed: "
                f"{sorted(_REVOKE_OBJECT_TYPES)}"
            )
        objects = row.get("objects")
        if not isinstance(objects, list) or not objects:
            raise UsageError("revocations[].objects must be a non-empty list")
        qualified = object_type.upper() == "TABLE"
        names = ", ".join(
            _identifier(o, where="revocations[].objects", qualified=qualified) for o in objects
        )
        privileges = ", ".join(_privileges(row.get("privileges"), where="revocations[]"))
        out.append(
            Statement(
                section="revocations",
                sql=(f"REVOKE {privileges} ON {object_type.upper()} {names} FROM {grantee_sql}"),
                why=str(row.get("why", "")),
            )
        )
    return out


_BUILDERS = {
    "roles": _roles,
    "memberships": _memberships,
    "schema_privileges": _schema_privileges,
    "table_privileges": _table_privileges,
    "schema_wide": _schema_wide,
    "default_privileges": _default_privileges,
    "revocations": _revocations,
}


def plan(path: Path) -> GrantPlan:
    """Render ``GRANTS.yaml`` at *path* into the ordered statements that assert it.

    Every statement is idempotent — ``CREATE ROLE IF NOT EXISTS``, ``GRANT``, ``REVOKE``,
    ``ALTER DEFAULT PRIVILEGES`` — which is what lets this run on every deploy rather
    than once. Idempotence here is a property of the statements, not of a guard around
    them, so a partially-applied run is resolved by running it again.

    Raises:
        UsageError: on a malformed matrix, an identifier that is not ``lower_snake``, a
            privilege outside the closed set, or a section name the runner has no builder
            for. An unknown section is refused rather than skipped: a typo'd section name
            would otherwise mean a whole block of the matrix silently stopped being applied.
    """
    document = load_matrix(path)
    order_raw = document.get("apply_order")
    order = tuple(order_raw) if isinstance(order_raw, list) and order_raw else APPLY_ORDER
    for section in order:
        if section not in _BUILDERS:
            raise UsageError(
                f"{path}: apply_order names section {section!r}, which this runner has no "
                f"builder for. Known: {sorted(_BUILDERS)}. A section that cannot be built "
                "must not be silently skipped — that is a block of the matrix quietly "
                "ceasing to be asserted."
            )

    statements: list[Statement] = []
    for section in order:
        statements.extend(_BUILDERS[str(section)](document))

    # A grant-bearing section the matrix declares but never applies. Both halves matter:
    # a builder we have and nobody ordered, and a section we know carries grants and have
    # no builder for. Reported, because a block of the matrix that quietly stopped being
    # asserted is exactly the drift DM-7 exists to catch.
    candidates = set(_BUILDERS) | set(_EXTRA_SECTIONS)
    unapplied = sorted(name for name in candidates if name in document and name not in order)
    return GrantPlan(
        source=path,
        statements=tuple(statements),
        unapplied_sections=tuple(unapplied),
    )


#: Sections that carry grants but are not in ``apply_order`` today. Named here so the
#: plan can report them; a section nobody names is a section nobody notices.
_EXTRA_SECTIONS: tuple[str, ...] = ("subject_access_views",)


def denials(path: Path) -> tuple[Denial, ...]:
    """Return the ``denials:`` block, as data for the privilege-probe test.

    Raises:
        UsageError: on a row missing ``role``, ``forbidden``, ``scope`` or
            ``expect_sqlstate``. A denial with no expected SQLSTATE is a denial the probe
            cannot assert, which would make it a comment.
    """
    document = load_matrix(path)
    out: list[Denial] = []
    for index, row in enumerate(_rows(document, "denials")):
        # `role:` (one) or `roles:` (a list). Both spellings are in the committed matrix
        # and both are legitimate: "the auditor may not INSERT" is one sentence about one
        # role, "no application role holds CREATE" is one sentence about eighteen. The
        # probe wants one row per (role, denial) pair either way, so the list form is
        # expanded here rather than being a second shape every consumer has to handle.
        names = row.get("roles") if "roles" in row else [row.get("role")]
        if not isinstance(names, list) or not names:
            raise UsageError(
                f"denials[{index}] carries neither a 'role' nor a non-empty 'roles' list"
            )
        roles = [_identifier(name, where=f"denials[{index}].role") for name in names]
        label = ", ".join(roles)
        forbidden = row.get("forbidden")
        if not isinstance(forbidden, list) or not forbidden:
            raise UsageError(f"denials[{label}].forbidden must be a non-empty list")
        scope = row.get("scope")
        sqlstate = row.get("expect_sqlstate")
        if not isinstance(scope, str) or not scope.strip():
            raise UsageError(f"denials[{label}].scope must say what the denial covers")
        if not isinstance(sqlstate, str) or len(sqlstate) != _SQLSTATE_LENGTH:
            raise UsageError(
                f"denials[{label}].expect_sqlstate is {sqlstate!r}; a denial the probe "
                "cannot assert an exact code for is a comment, not a control"
            )
        out.extend(
            Denial(
                role=role,
                forbidden=tuple(str(f).upper() for f in forbidden),
                scope=scope.strip(),
                expect_sqlstate=sqlstate,
                why=str(row.get("why", "")).strip(),
            )
            for role in roles
        )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """What ``grants apply`` did, statement by statement."""

    applied: tuple[str, ...]
    missing_objects: tuple[str, ...]
    """Statements skipped because their object does not exist yet, with the SQLSTATE.

    Only ever non-empty when the caller passed ``allow_missing=True``. During the build
    the matrix legitimately runs ahead of the tree; on a finished cluster a missing object
    is a defect, which is why the default is to refuse.
    """


def apply(
    conn: psycopg.Connection[Any],
    grant_plan: GrantPlan,
    *,
    allow_missing: bool = False,
) -> ApplyResult:
    """Assert every statement in *grant_plan* against the cluster, in order.

    One statement per transaction, deliberately. A grant matrix is not a unit of
    atomicity — it is a set of independent assertions, each idempotent — and wrapping two
    hundred of them in one transaction would mean a single missing table discarded the
    hundred and ninety-nine that were correct.

    Raises:
        psycopg.Error: the database refused a statement, and ``allow_missing`` did not
            cover it. Not wrapped: the SQLSTATE and the database's own words are what an
            operator needs, and a refusal is the runner working.
    """
    applied: list[str] = []
    missing: list[str] = []
    for statement in grant_plan.statements:
        try:

            def body(c: psycopg.Connection[Any], sql: str = statement.sql) -> None:
                c.execute(sql)

            in_txn(conn, body)
        except psycopg.Error as exc:
            state = exc.diag.sqlstate if exc.diag is not None else None
            if allow_missing and state in _MISSING_OBJECT_SQLSTATES:
                missing.append(f"[{state}] {statement.sql}")
                continue
            raise
        applied.append(statement.sql)
    return ApplyResult(applied=tuple(applied), missing_objects=tuple(missing))


def default_matrix_path(root: Path) -> Path:
    """Where a vertical's grant matrix lives, given its ``db/`` root."""
    return root / "GRANTS.yaml"


def describe(grant_plan: GrantPlan) -> Sequence[str]:
    """One summary line per section — what ``--check`` prints instead of 200 statements."""
    counts: dict[str, int] = {}
    for statement in grant_plan.statements:
        counts[statement.section] = counts.get(statement.section, 0) + 1
    lines = [f"{section}: {count} statement(s)" for section, count in counts.items()]
    if grant_plan.unapplied_sections:
        lines.append(
            "declared but NOT in apply_order (reported, not applied): "
            + ", ".join(grant_plan.unapplied_sections)
        )
    return lines
