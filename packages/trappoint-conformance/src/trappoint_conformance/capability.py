# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Resolving a case's ``requires`` token against the cluster actually in front of us.

Twenty-two cases in ``spec/conformance/manifest.toml`` declare a capability they need:

``mainline.propagation``
    a relation. The case writes to it, so a cluster without it cannot run the case.
``role:mainline_auditor``
    a database role. ``CF-69`` asserts what the auditor may *not* do; with no such role
    there is nobody to assert it about.
``policy:mainline.permit``
    a row-level-security policy on a relation. ``CF-22`` asserts the gate still refuses
    with ``FORCE ROW LEVEL SECURITY`` in play, which is a claim about a cluster that has
    policies.

**Before this module the only way to satisfy a token was for a human to type
``--requires``.** That is not a measurement, it is an assertion by the person running the
suite, and it fails in both directions: against a fully migrated cluster every one of
those cases reported ``SKIPPED`` for objects that were sitting right there, and a run
where somebody typed ``--requires mainline.propagation`` on a cluster that has no such
relation would have marched the case straight into a refusal it would then have to
diagnose. This module *looks*.

**What it will not do.** It never reports a capability as satisfied because a catalogue
was unreadable, and it never reports one as absent because a catalogue was unreadable
either — those are different sentences and the second is the one people get wrong. If the
probe cannot read the catalogue it says so, naming the catalogue and the driver's error,
and the token stays unsatisfied with that as its reason.

**Every unsatisfied token carries a one-line reason that names the object.** ``requires
mainline.propagation`` tells a reader nothing they could act on. ``relation
"mainline.propagation" does not exist (pg_class, schema "mainline" is present, database
"w_w7")`` tells them the object, the catalogue that was consulted, whether the *schema*
is the thing that is missing, and which database was asked.

MEASURED, 2026-08-10, CockroachDB CCL v26.2.5, database ``w_w7``:

* ``pg_catalog.pg_policies`` exists, is readable as ``root``, and returned 21 rows across
  ``mainline.permit`` (7), ``mainline.change_request`` (7), ``mainline.disposition`` (7)
  and ``mainline_meas.standing`` (4);
* there is **no** ``crdb_internal`` equivalent —
  ``SELECT table_name FROM information_schema.tables WHERE table_schema = 'crdb_internal'
  AND table_name ILIKE '%polic%'`` returns the empty set — so ``pg_policies`` is not one
  of two options, it is the only readable source, and the fallback path below exists to
  *report* its absence rather than to route around it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MANIFEST_NAMESPACE",
    "POLICY",
    "RELATION",
    "ROLE",
    "UNKNOWN",
    "Capability",
    "CapabilityReport",
    "parse_token",
    "probe",
]

#: The namespace the manifest writes every capability token in, whatever the profile —
#: the same convention ``cases/_exhibit.MANIFEST_NAMESPACE`` uses for ``P0001`` exhibits.
#: The manifest is one document; the schema is a property of the binding.
MANIFEST_NAMESPACE = "mainline"

RELATION = "relation"
ROLE = "role"
POLICY = "policy"
UNKNOWN = "unknown"

#: ``pg_class.relkind`` values a ``requires`` token may legitimately name. A case that
#: needs ``mainline.propagation`` needs something it can write to or read from; a view or
#: a materialised view satisfies the token exactly as a table does, and the kind is
#: recorded in the satisfied detail so a report never has to guess which it got.
_RELKIND: dict[str, str] = {
    "r": "table",
    "p": "partitioned table",
    "v": "view",
    "m": "materialised view",
    "f": "foreign table",
}


@dataclass(frozen=True, slots=True)
class Capability:
    """One ``requires`` token, resolved against the cluster."""

    token: str
    """The token exactly as the manifest wrote it. Never rewritten: the manifest is the
    document a claim of conformance cites, and a report that renamed its tokens would be
    citing something else."""

    kind: str
    """:data:`RELATION`, :data:`ROLE`, :data:`POLICY` or :data:`UNKNOWN`."""

    schema: str
    """The schema the token was probed in, after re-homing into the profile's namespace.
    Empty for a ``role:`` token, which is a cluster-wide object."""

    name: str
    """The local object name that was probed."""

    satisfied: bool
    detail: str = ""
    """What was found, when it was found. ``table mainline.permit``, ``7 polic(ies)``."""

    reason: str = ""
    """One line naming the object, when it was not found. Empty when satisfied."""

    @property
    def object_name(self) -> str:
        """The fully-qualified object this token names, as probed."""
        return f"{self.schema}.{self.name}" if self.schema else self.name


@dataclass(frozen=True, slots=True)
class CapabilityReport:
    """What one probe of one cluster found."""

    database: str
    schema: str
    capabilities: tuple[Capability, ...] = ()

    @property
    def satisfied(self) -> frozenset[str]:
        """Every token the cluster actually supplies."""
        return frozenset(c.token for c in self.capabilities if c.satisfied)

    @property
    def unsatisfied(self) -> tuple[Capability, ...]:
        """Every token it does not, each carrying its own reason."""
        return tuple(c for c in self.capabilities if not c.satisfied)

    def reasons(self) -> dict[str, str]:
        """``token -> one-line reason``, for the unsatisfied tokens only."""
        return {c.token: c.reason for c in self.unsatisfied}

    def summary(self) -> str:
        """One line for the console."""
        n = len(self.capabilities)
        return (
            f"capabilities {len(self.satisfied)}/{n} satisfied · database {self.database} "
            f"· schema {self.schema} · probed pg_class, pg_namespace, pg_roles, pg_policies"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────


def _rehome(namespace: str, schema: str) -> str:
    """Map a manifest namespace onto the profile's own schema.

    ``mainline`` -> ``<schema>`` and ``mainline_meas`` -> ``<schema>_meas``, which is the
    naming the reference vertical and MAINLINE both follow. Any other namespace is left
    alone: a token that names a third schema means that schema, and inventing a mapping
    for it would be the runner deciding what the manifest meant.
    """
    if not namespace or schema == MANIFEST_NAMESPACE:
        return namespace
    if namespace == MANIFEST_NAMESPACE:
        return schema
    if namespace.startswith(f"{MANIFEST_NAMESPACE}_"):
        return schema + namespace[len(MANIFEST_NAMESPACE) :]
    return namespace


def parse_token(token: str, *, schema: str) -> tuple[str, str, str]:
    """Return ``(kind, schema, name)`` for one ``requires`` token.

    ``role:x`` is cluster-wide and has no schema. ``policy:s.t`` and a bare ``s.t`` are
    schema-qualified and are re-homed into the profile's namespace. A token with no
    qualifier at all is read as a relation in the profile's own schema, which is the only
    reading that does not require guessing.
    """
    raw = token.strip()
    head, sep, tail = raw.partition(":")
    if sep and head == ROLE:
        return ROLE, "", tail.strip()
    if sep and head == POLICY:
        namespace, dot, relation = tail.strip().partition(".")
        if not dot:
            return POLICY, schema, namespace
        return POLICY, _rehome(namespace, schema), relation
    if sep:
        return UNKNOWN, "", raw
    namespace, dot, relation = raw.partition(".")
    if not dot:
        return RELATION, schema, namespace
    return RELATION, _rehome(namespace, schema), relation


# ─────────────────────────────────────────────────────────────────────────────
# Probing
# ─────────────────────────────────────────────────────────────────────────────


def _fetch(conn: Any, sql: str, params: Sequence[Any]) -> tuple[list[tuple[Any, ...]], str]:
    """Run one catalogue read. Returns ``(rows, "")`` or ``([], "<error>")``.

    A catalogue that cannot be read is reported, never treated as an empty catalogue.
    The distinction is the whole point of this module.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall()), ""
    except Exception as exc:  # noqa: BLE001 — any driver failure is a read failure
        return [], f"{type(exc).__name__}: {str(exc).strip()}"


_SQL_NAMESPACES = "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname = ANY(%s)"

_SQL_RELATIONS = (
    "SELECT n.nspname, c.relname, c.relkind "
    "FROM pg_catalog.pg_class c "
    "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = ANY(%s) AND c.relname = ANY(%s)"
)

_SQL_ROLES = "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY(%s)"

_SQL_POLICIES = (
    "SELECT schemaname, tablename, policyname FROM pg_catalog.pg_policies "
    "WHERE schemaname = ANY(%s) AND tablename = ANY(%s)"
)


def _database_of(conn: Any) -> str:
    try:
        return str(conn.info.dbname)
    except Exception:  # noqa: BLE001 — a stub connection has no `info`
        return "<unknown>"


@dataclass(frozen=True, slots=True)
class _Catalogues:
    """Everything the four catalogue reads returned, plus what could not be read.

    A record rather than a dozen loose arguments, because each field is a *measurement*
    and a resolver that took them positionally would be one argument re-order away from
    reporting a role as a relation.
    """

    database: str
    present_schemas: frozenset[str] = frozenset()
    relations: dict[tuple[str, str], str] | None = None
    roles: frozenset[str] = frozenset()
    policies: dict[tuple[str, str], list[str]] | None = None
    schema_error: str = ""
    relation_error: str = ""
    role_error: str = ""
    policy_error: str = ""

    def relkind(self, schema: str, name: str) -> str | None:
        """Return ``pg_class.relkind`` for one relation, or ``None`` when it is absent."""
        return (self.relations or {}).get((schema, name))

    def policy_names(self, schema: str, name: str) -> list[str]:
        """Return the policy names on one relation, possibly empty."""
        return (self.policies or {}).get((schema, name), [])


def probe(conn: Any, tokens: Iterable[str], *, schema: str) -> CapabilityReport:
    """Resolve every token in *tokens* against the live connection *conn*.

    Four catalogue reads for the whole run, never one per token: ``pg_namespace`` (so an
    absent *schema* is reported as an absent schema rather than as forty absent
    relations), ``pg_class``, ``pg_roles`` and ``pg_policies``.
    """
    parsed = [(token, *parse_token(token, schema=schema)) for token in dict.fromkeys(tokens)]
    database = _database_of(conn)
    if not parsed:
        return CapabilityReport(database=database, schema=schema)

    rel_schemas = sorted({s for _, k, s, _ in parsed if k in (RELATION, POLICY)})
    rel_names = sorted({n for _, k, _, n in parsed if k in (RELATION, POLICY)})
    role_names = sorted({n for _, k, _, n in parsed if k == ROLE})

    present_schemas: frozenset[str] = frozenset()
    relations: dict[tuple[str, str], str] = {}
    schema_error = ""
    relation_error = ""
    if rel_schemas:
        rows, schema_error = _fetch(conn, _SQL_NAMESPACES, (rel_schemas,))
        present_schemas = frozenset(str(r[0]) for r in rows)
        rows, relation_error = _fetch(conn, _SQL_RELATIONS, (rel_schemas, rel_names))
        relations = {(str(r[0]), str(r[1])): str(r[2]) for r in rows}

    roles: frozenset[str] = frozenset()
    role_error = ""
    if role_names:
        rows, role_error = _fetch(conn, _SQL_ROLES, (role_names,))
        roles = frozenset(str(r[0]) for r in rows)

    policies: dict[tuple[str, str], list[str]] = {}
    policy_error = ""
    if any(k == POLICY for _, k, _, _ in parsed):
        rows, policy_error = _fetch(conn, _SQL_POLICIES, (rel_schemas, rel_names))
        for row in rows:
            policies.setdefault((str(row[0]), str(row[1])), []).append(str(row[2]))

    catalogues = _Catalogues(
        database=database,
        present_schemas=present_schemas,
        relations=relations,
        roles=roles,
        policies=policies,
        schema_error=schema_error,
        relation_error=relation_error,
        role_error=role_error,
        policy_error=policy_error,
    )
    resolved = tuple(
        _resolve(token, kind, token_schema, name, catalogues)
        for token, kind, token_schema, name in parsed
    )
    return CapabilityReport(database=database, schema=schema, capabilities=resolved)


def _resolve(token: str, kind: str, schema: str, name: str, cat: _Catalogues) -> Capability:
    """Turn one parsed token plus the catalogue reads into one :class:`Capability`."""
    if kind == ROLE:
        return _resolve_role(token, name, cat)
    if kind == RELATION:
        return _resolve_relation(token, schema, name, cat)
    if kind == POLICY:
        return _resolve_policy(token, schema, name, cat)
    return Capability(
        token=token,
        kind=UNKNOWN,
        schema="",
        name=name,
        satisfied=False,
        reason=(
            f'"{token}" is not a capability token this prober understands. Known forms: '
            f"<schema>.<relation>, role:<name>, policy:<schema>.<relation>."
        ),
    )


def _resolve_role(token: str, name: str, cat: _Catalogues) -> Capability:
    """Resolve a ``role:`` token against ``pg_roles``."""
    if cat.role_error:
        return Capability(
            token, ROLE, "", name, False, reason=_unreadable("pg_roles", cat.role_error, name)
        )
    if name in cat.roles:
        return Capability(token, ROLE, "", name, True, detail=f"role {name}")
    return Capability(
        token,
        ROLE,
        "",
        name,
        False,
        reason=f'role "{name}" does not exist on this cluster (pg_roles)',
    )


def _resolve_relation(token: str, schema: str, name: str, cat: _Catalogues) -> Capability:
    """Resolve a ``<schema>.<relation>`` token against ``pg_class`` / ``pg_namespace``."""
    unreadable = cat.relation_error or cat.schema_error
    if unreadable:
        return Capability(
            token,
            RELATION,
            schema,
            name,
            False,
            reason=_unreadable("pg_class/pg_namespace", unreadable, f"{schema}.{name}"),
        )
    relkind = cat.relkind(schema, name)
    if relkind is None:
        return Capability(token, RELATION, schema, name, False, reason=_absent(schema, name, cat))
    return Capability(
        token,
        RELATION,
        schema,
        name,
        True,
        detail=f"{_RELKIND.get(relkind, f'relkind {relkind!r}')} {schema}.{name}",
    )


def _resolve_policy(token: str, schema: str, name: str, cat: _Catalogues) -> Capability:
    """Resolve a ``policy:`` token against ``pg_policies``, naming what it found."""
    qualified = f"{schema}.{name}"
    unreadable = cat.policy_error or cat.relation_error or cat.schema_error
    if unreadable:
        catalogue = "pg_policies" if cat.policy_error else "pg_class/pg_namespace"
        return Capability(
            token,
            POLICY,
            schema,
            name,
            False,
            reason=_unreadable(catalogue, unreadable, qualified),
        )
    if cat.relkind(schema, name) is None:
        return Capability(
            token,
            POLICY,
            schema,
            name,
            False,
            reason=f"no row-level-security policy on {qualified} — {_absent(schema, name, cat)}",
        )
    found = cat.policy_names(schema, name)
    if not found:
        return Capability(
            token,
            POLICY,
            schema,
            name,
            False,
            reason=(
                f'relation "{qualified}" exists but carries no row-level-security policy '
                f'(pg_policies, database "{cat.database}")'
            ),
        )
    return Capability(
        token,
        POLICY,
        schema,
        name,
        True,
        detail=f"{len(found)} policy/policies on {qualified}: {', '.join(sorted(found))}",
    )


def _absent(schema: str, name: str, cat: _Catalogues) -> str:
    """Return the one-line reason for an absent relation, naming what is missing."""
    qualified = f"{schema}.{name}"
    if schema and schema not in cat.present_schemas:
        return (
            f'relation "{qualified}" does not exist — schema "{schema}" is not in '
            f'database "{cat.database}" (pg_namespace)'
        )
    return (
        f'relation "{qualified}" does not exist (pg_class; schema "{schema}" is present '
        f'in database "{cat.database}")'
    )


def _unreadable(catalogue: str, error: str, qualified: str) -> str:
    """Return the reason for a token whose catalogue could not be read.

    Deliberately not the same sentence as "does not exist". A suite that reported an
    unreadable catalogue as an absent object would publish a cannot-run whose stated cause
    is false, and the reader would go looking for a migration instead of a grant.
    """
    return (
        f"could not read {catalogue} to resolve {qualified}, so its presence is UNKNOWN "
        f"rather than absent: {error}"
    )
