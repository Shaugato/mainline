#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""LEG B — the privilege PROBE. What a login can actually reach, asked of the database.

``GRANTS.yaml``'s own header says what this file is for, and says it twice::

    A GRANT is a claim about intent. A 42501 is evidence about behaviour.

and::

    The control is the privilege probe ... which walks every (role, table) pair this file
    does NOT name and asserts the refusal. This file is the input to that probe as much
    as it is the input to `grants apply`.

Leg A (``verticals/mainline/apps/demo-api/tests/test_privilege_census.py``) compares two
documents — what the shipping source demands against what the matrix declares. It runs in
milliseconds and it would have gone red before the first deploy. It is still a comparison
of two texts. **This is the other leg: it connects AS the role and asks the cluster.**

WHAT IT ASSERTS, IN BOTH DIRECTIONS
===================================
* **Positive.** Every ``(object, verb)`` pair the matrix grants the role — directly, or
  through a role it is a member of, or through ``GRANT ... ON ALL TABLES IN SCHEMA`` —
  must NOT be refused with ``42501``.
* **Negative.** A deterministic sample of the pairs the matrix does **not** name must be
  refused with exactly ``42501``.

**The positive direction is not optional and it is not decoration.** A login that can read
nothing passes every negative test perfectly. ``cloud_roles.probe``'s docstring already
names that trap; this file is the same claim made against a database built from the tree
rather than against a deployment.

THE ZERO-ROW PROBE SHAPE, AND WHY EVERY STATEMENT BELOW TOUCHES NO ROW
======================================================================
Each probe is written so that the statement plans, the privilege check runs, and then
**no row is read, written, changed or deleted**::

    SELECT  SELECT 1 FROM <rel> WHERE false
    INSERT  INSERT INTO <rel> (<col>) SELECT NULL WHERE false
    UPDATE  UPDATE <rel> SET <col> = NULL WHERE false
    DELETE  DELETE FROM <rel> WHERE false

That shape is not squeamishness about the scratch database. It is what makes the answer
mean one thing. A ``CHECK`` constraint, an append-only trigger and a row-level-security
``WITH CHECK`` clause are all evaluated per row, and a statement that touches zero rows
never reaches any of them — so a ``42501`` here is the grant graph and nothing else, which
is precisely the distinction ``packages/trappoint-conformance/cases/_privilege.py`` draws
when it excludes ``42501`` from the refusal taxonomy *by definition*: the writer was stopped
before any gate condition was evaluated, so classifying it with ``23514`` would say the gate
refused something the gate never saw.

**Zero rows does not mean zero refusals, and the positive direction is written for that.**
Measured on CockroachDB v26.2.5, 2026-08-15:
``INSERT INTO mainline.exposure_line (<col>) SELECT NULL WHERE false`` as a login that HOLDS
the privilege returns ``23502 missing "check_id" primary key column`` — the planner checks
column presence whether or not a row arrives. That is not a privilege refusal, so the
positive direction asserts **"not ``42501``"** rather than "``00000``". Asserting success
would have turned a correct grant into a red and taught somebody to weaken the probe.

The exhibit for a refusal is that module's token, ``grant:<verb>:<object>:<role>``
(``spec/errors.md`` §3.1), so a refusal recorded here is legible beside every other
refusal in the corpus.

WHAT THIS PROGRAM WILL NOT DO
=============================
* It never prints a DSN, a userinfo, or a password. The target is named by its **cluster
  label** — host, port and database — and every message it emits, including a driver's own
  error text, goes through :func:`safe` first.
* It never connects to AWS, never deploys, and never writes a secret anywhere.
* It creates the login **without a password** when the cluster is insecure, because
  CockroachDB refuses one there outright (*"setting or updating a password is not
  supported in insecure mode"*). ``scripts/deploy/cloud_roles.py`` documents that branch
  and this file handles it the same way rather than discovering it as a failure mid-run.
  The matrix itself carries no password and never will.
* It does not add a grant, and it does not close a difference it finds. A difference IS
  the finding.

USAGE
-----
::

    # build a database from the tree, apply the matrix, probe, drop it again
    .venv/Scripts/python.exe scripts/qa/privilege_conformance.py

    # probe a database that is already migrated (nothing is created and nothing is dropped)
    .venv/Scripts/python.exe scripts/qa/privilege_conformance.py --database chain_2026...

    # any cluster, by DSN; the DSN is never echoed
    .venv/Scripts/python.exe scripts/qa/privilege_conformance.py --dsn "$LOCAL_DSN"

Exit codes:

* ``0`` — every positive pair was reachable and every sampled negative pair returned 42501.
* ``1`` — a difference. The table names each one.
* ``2`` — could not run: no cluster, no matrix, no driver, no migration tree.
* ``3`` — the matrix does not declare the role, so the probe has no subject to ask about.
  Distinct from ``1`` on purpose: nothing disagreed, there was nothing to disagree with.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg

if __package__ in (None, ""):  # pragma: no cover - the standalone-script path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# `cloud_chain` is plumbing shared by every program in this repository that speaks to a
# cluster: the DSN rewriter, the SQLSTATE extractor and the password redactor. It is NOT
# `cloud_roles.py`. This probe deliberately imports nothing from the deploy script whose
# grants it exists to check — a control that shares its subject's code cannot falsify it,
# and `as_role` below is six lines rather than an import for exactly that reason.
from scripts.deploy.cloud_chain import cluster_label, one_line, redact, rewrite_dsn, sqlstate_of

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
DEFAULT_MATRIX = REPO_ROOT / "verticals" / "mainline" / "db" / "GRANTS.yaml"
DEFAULT_MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"
DEFAULT_TREE = "mainline"

#: The role an anonymous caller on the `authorization_type = NONE` Function URL executes as.
DEFAULT_ROLE = "mainline_api"

EXIT_OK = 0
EXIT_DIFFERENCE = 1
EXIT_UNUSABLE = 2
EXIT_NO_SUBJECT = 3

#: ``insufficient_privilege``. What a grant that was never made looks like from the other
#: side of the connection, and the only SQLSTATE a negative probe accepts.
DENY = "42501"

#: What the driver reports when a statement completed. Not a SQLSTATE the driver raises —
#: this program synthesises it so that "it worked" and "it was refused with X" are the same
#: kind of value and can sit in one column of one table.
OK = "00000"

#: An object the matrix names and the migration tree does not create. ``GRANTS.yaml``'s own
#: contract for `grants apply` says such a row is *"SKIPPED WITH A WARNING, never an error"*,
#: and `scripts/chain/apply_chain.py` records the census of them (producers-plan D12: they
#: are REPORTED, not authored). A probe of an absent object is therefore reported in its own
#: category and is not counted as a disagreement — the role's reach is not what is wrong.
ABSENT_SQLSTATES: frozenset[str] = frozenset({"42P01", "3F000", "42704", "42883"})

#: The verbs this leg probes behaviourally. Each has a zero-row statement shape (see the
#: module docstring) that isolates the privilege check from every other check in the system.
PROBE_VERBS: tuple[str, ...] = ("SELECT", "INSERT", "UPDATE", "DELETE")

#: ``ALL`` in the matrix means every privilege; expanded to the verbs this leg can ask about.
#: The expansion is deliberately not silent — a row that says ALL is reported as such in the
#: provenance column, so a reader can tell an enumerated grant from a widened one.
_ALL_EXPANDS_TO: tuple[str, ...] = PROBE_VERBS

#: Verbs a matrix row may legally carry that this leg does not probe by executing something.
#: They are LISTED in the report rather than dropped, with where they ARE proved: `EXECUTE`
#: by `cloud_roles.gate_probe`, which calls `mainline.merge_permit` and asserts the product's
#: own refusal; `CREATE`/`ZONECONFIG` by the DDL denials in `GRANTS.yaml` §8, whose probe is
#: `tests/integration/schema/test_mi_foundation.py`. Naming them is the difference between a
#: stated limit and a hole.
UNPROBED_VERBS: Mapping[str, str] = {
    "EXECUTE": "routine invocation; proved by cloud_roles.gate_probe (CALL mainline.merge_permit)",
    "CREATE": "DDL; proved by the CREATE denials in GRANTS.yaml section 8",
    "USAGE": "schema traversal; proved implicitly — every probe below names a schema",
    "ZONECONFIG": "zone configuration; no relation-level probe shape exists",
}

#: A schema-qualified relation, `lower_snake` on both sides. Every name this program
#: interpolates into a statement is checked against it first, because SQL has no
#: placeholder for an identifier and these names come from a YAML file and from
#: `information_schema` rather than from a request.
_QUALIFIED = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

#: Any postgres URL, whatever it carries. `cloud_chain.redact` strips the password out of a
#: DSN; this blanks the whole URL, because the brief for this file is stricter than that —
#: not the DSN, not the userinfo, not the password, in any output, ever.
_DSN_URL = re.compile(r"(?i)postgres(?:ql)?://\S*")


def safe(text: str) -> str:
    """Return *text* with anything DSN-shaped removed. Every printed string passes through.

    Two passes, and both are wanted. :func:`cloud_chain.redact` handles ``password=`` in the
    keyword form as well as the URL form; this then blanks the URL entirely, because a DSN
    with no password in it still carries a host, a port and a database name that this
    program is asked never to echo. Driver errors quote the connection string more often
    than anyone expects, so the redaction belongs at the boundary and not at each ``print``.
    """
    return _DSN_URL.sub("<dsn withheld>", redact(text))


@dataclass(frozen=True, slots=True, repr=False)
class Target:
    """A DSN that refuses to print itself. ``repr`` is the cluster label and nothing else.

    Not decoration, and not paranoia about ``print``. **A traceback prints its arguments.**
    pytest's default long traceback renders the parameters of every frame it shows, and a
    fixture that took a bare ``str`` put
    ``admin_dsn = 'postgresql://root@127.0.0.1:26257/…'`` into a CI log the first time
    anything failed — measured, 2026-08-15, in this file's own first run. Against a cluster
    whose DSN carries a password that log is the leak, and it happens on the failure path,
    which is the path nobody rehearses.

    So the DSN travels through this program inside an object whose every string form is
    ``<cluster host:port/database>``, and is unwrapped only at the moment it is handed to
    the driver. :func:`safe` is the second layer, for text the driver itself produced.
    """

    dsn: str

    def __repr__(self) -> str:
        """Return the cluster label, which is host, port and database and nothing else."""
        return f"<cluster {cluster_label(self.dsn)}>"

    __str__ = __repr__

    @property
    def label(self) -> str:
        """The same label, for a report that wants it without the angle brackets."""
        return cluster_label(self.dsn)

    def at(self, database: str, *, application_name: str = "mainline-privilege") -> Target:
        """The same cluster, pointed at *database*."""
        return Target(rewrite_dsn(self.dsn, database=database, application_name=application_name))


def _qualified(name: str) -> str:
    if _QUALIFIED.match(name) is None:
        raise ValueError(
            f"{name!r} is not a schema.object identifier. Identifiers are interpolated "
            "into these statements because SQL has no placeholder for one, so the shape is "
            "checked rather than trusted."
        )
    return name


def _ident(name: str) -> str:
    if _IDENT.match(name) is None:
        raise ValueError(f"{name!r} is not a lower_snake identifier")
    return name


# ═════════════════════════════════════════════════════════════════════════════════════
# what the matrix says the role may reach
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True, order=True)
class Pair:
    """One ``(object, verb)`` — the unit both directions of this probe are stated in."""

    obj: str
    verb: str

    def __str__(self) -> str:
        """Return ``VERB object``, which is how the table prints it."""
        return f"{self.verb:<6} {self.obj}"

    @property
    def schema(self) -> str:
        """The schema half of the qualified name."""
        return self.obj.partition(".")[0]

    @property
    def relation(self) -> str:
        """The relation half of the qualified name."""
        return self.obj.partition(".")[2]


@dataclass(frozen=True, slots=True)
class Reach:
    """What ``GRANTS.yaml`` says one role may reach, closed over role membership.

    Nothing in this object is typed out anywhere: every field is derived from the matrix
    and from the relations the connected database actually holds. A second copy of a list
    is a second thing to drift, and the list that drifts is the one nobody re-reads —
    which is the lesson `test_seed_covers_every_console_resource.py` states and the lesson
    R4 of the lead plan measured being learned the hard way.
    """

    role: str
    #: Roles whose privileges *role* inherits, transitively, in the order discovered.
    members_of: tuple[str, ...]
    #: ``Pair -> provenance``. The provenance is printed on every line of the report so a
    #: reader can see *why* a pair is expected to work without opening the matrix.
    granted: Mapping[Pair, str]
    #: ``schema -> privileges`` from ``schema_privileges``, closed over membership.
    schema_privileges: Mapping[str, tuple[str, ...]]
    #: Pairs whose reachability depends on the ORDER objects were created in, because
    #: ``ALTER DEFAULT PRIVILEGES`` grants on objects created *after* it runs and on no
    #: others. Excluded from both directions, and printed, rather than guessed at.
    deferred: frozenset[Pair]
    #: ``verb -> objects`` for verbs the matrix names that this leg does not execute.
    unprobed: Mapping[str, tuple[str, ...]]

    @property
    def declared(self) -> bool:
        """True when the matrix declares the role at all.

        A role the matrix never names has an empty reach, and an empty reach passes every
        negative probe there is. That is the vacuity this whole wave exists to end, so the
        two cases are kept distinguishable rather than collapsing into "nothing granted".
        """
        return bool(self.granted) or bool(self.schema_privileges) or bool(self.members_of)


def _membership_closure(document: Mapping[str, Any], role: str) -> tuple[str, ...]:
    """Every role whose privileges *role* inherits, transitively.

    A CockroachDB role inherits the privileges of every role it is a member of, so the
    matrix's ``memberships:`` block is part of the answer to "what may this login reach"
    and not a separate topic. ``cloud_roles.py``'s module docstring explains that the three
    memberships it grants ``mainline_api`` exist for **row-level-security scope** rather
    than for privileges — that is true of the INTENT and irrelevant to the EFFECT. A policy
    written ``TO agent_gate`` matches any member of ``agent_gate``, and so does every
    ``GRANT`` ever made to ``agent_gate``. Computing the closure is the difference between
    a negative direction that names real denials and one that reports two hundred false
    ones.
    """
    inherits: dict[str, list[str]] = {}
    for row in document.get("memberships") or []:
        if not isinstance(row, Mapping):
            continue
        parent, member = row.get("role"), row.get("member")
        if isinstance(parent, str) and isinstance(member, str):
            inherits.setdefault(member, []).append(parent)

    seen: list[str] = []
    frontier = list(inherits.get(role, ()))
    while frontier:
        name = frontier.pop(0)
        if name in seen or name == role:
            continue
        seen.append(name)
        frontier.extend(inherits.get(name, ()))
    return tuple(seen)


def _row_privileges(row: Mapping[str, Any]) -> tuple[str, ...]:
    raw = row.get("privileges")
    if not isinstance(raw, list):
        return ()
    return tuple(str(p).upper() for p in raw)


def _deferred_pairs(
    document: Mapping[str, Any], holders: Sequence[str], relations: Mapping[str, Relation]
) -> set[Pair]:
    """Pairs whose reachability ``ALTER DEFAULT PRIVILEGES`` makes order-dependent.

    A default privilege grants on objects created **after** it runs and on no others. Every
    object in a freshly migrated database was created before the matrix was applied, so a
    default privilege adds nothing here — but that is a statement about ORDER, not about
    intent, and a probe that asserted ``42501`` on these pairs would be asserting the order
    it happened to run in. They are excluded from both directions and reported, so the
    exclusion is visible rather than convenient.
    """
    deferred: set[Pair] = set()
    for row in document.get("default_privileges") or []:
        if not isinstance(row, Mapping) or row.get("to_role") not in holders:
            continue
        schema = _ident(str(row.get("schema")))
        names = [n for n in relations if n.partition(".")[0] == schema]
        for privilege in _row_privileges(row):
            verbs = _ALL_EXPANDS_TO if privilege == "ALL" else (privilege,)
            deferred.update(
                Pair(obj=name, verb=verb) for name in names for verb in verbs if verb in PROBE_VERBS
            )
    return deferred


def matrix_reach(matrix: Path, role: str, relations: Mapping[str, Relation]) -> Reach:
    """Compute what *role* may reach, from *matrix*, against the relations that exist.

    ``GRANTS.yaml`` is parsed by :mod:`trappoint_migrate.grants` — the runner that applies
    it — and never by a second YAML reader of this file's own. The matrix and the probe
    must disagree about privileges, which is the point; they must not be able to disagree
    about what the file *says*.

    *relations* is what the connected database holds, and it is what turns
    ``GRANT SELECT ON ALL TABLES IN SCHEMA mainline`` from a sentence into a set. That
    statement grants on the relations present when it runs and on no others, so expanding
    it against the live catalogue is not an approximation — it is the same expansion the
    cluster performed.
    """
    from trappoint_migrate.grants import load_matrix

    document = load_matrix(matrix)
    members_of = _membership_closure(document, role)
    holders = (role, *members_of)

    granted: dict[Pair, str] = {}
    unprobed: dict[str, list[str]] = {}

    def record(obj: str, privileges: Iterable[str], provenance: str) -> None:
        for privilege in privileges:
            verbs = _ALL_EXPANDS_TO if privilege == "ALL" else (privilege,)
            note = f"{provenance} (ALL)" if privilege == "ALL" else provenance
            for verb in verbs:
                if verb in PROBE_VERBS:
                    granted.setdefault(Pair(obj=obj, verb=verb), note)
                elif verb in UNPROBED_VERBS:
                    unprobed.setdefault(verb, []).append(obj)

    for row in document.get("table_privileges") or []:
        if not isinstance(row, Mapping) or row.get("role") not in holders:
            continue
        obj = _qualified(str(row.get("object")))
        via = str(row.get("role"))
        record(obj, _row_privileges(row), f"table_privileges{'' if via == role else f' via {via}'}")

    for row in document.get("schema_wide") or []:
        if not isinstance(row, Mapping) or row.get("role") not in holders:
            continue
        schema = _ident(str(row.get("schema")))
        via = str(row.get("role"))
        note = f"schema_wide {schema}{'' if via == role else f' via {via}'}"
        for name in sorted(relations):
            if name.partition(".")[0] == schema:
                record(name, _row_privileges(row), note)

    schema_privileges: dict[str, list[str]] = {}
    for row in document.get("schema_privileges") or []:
        if not isinstance(row, Mapping) or row.get("role") not in holders:
            continue
        for schema in row.get("schemas") or []:
            existing = schema_privileges.setdefault(_ident(str(schema)), [])
            existing.extend(p for p in _row_privileges(row) if p not in existing)

    deferred = _deferred_pairs(document, holders, relations) - set(granted)

    return Reach(
        role=role,
        members_of=members_of,
        granted=dict(sorted(granted.items())),
        schema_privileges={k: tuple(v) for k, v in sorted(schema_privileges.items())},
        deferred=frozenset(deferred),
        unprobed={verb: tuple(sorted(set(objs))) for verb, objs in sorted(unprobed.items())},
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# what the database holds
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Relation:
    """One relation in the connected database, and the column the write probes name.

    *column* is chosen rather than assumed: a generated column cannot be the target of an
    ``INSERT`` or an ``UPDATE`` and would produce a syntax-class error instead of a
    privilege one, which would make a passing probe mean nothing.
    """

    schema: str
    name: str
    kind: str
    column: str | None

    @property
    def obj(self) -> str:
        """The schema-qualified name."""
        return f"{self.schema}.{self.name}"

    @property
    def writable(self) -> bool:
        """True when ``INSERT``/``UPDATE``/``DELETE`` have a meaningful probe here.

        A view refuses a write with ``55000``/``0A000`` — *cannot insert into a view* —
        which is neither a grant nor a denial, so the write verbs are asked only of base
        tables. ``mainline_audit`` and ``mainline_qa`` hold nothing but views, and the
        claim that matters about them is a ``SELECT`` claim.
        """
        return self.kind == "BASE TABLE" and self.column is not None


_RELATIONS_SQL = """
SELECT t.table_schema,
       t.table_name,
       t.table_type,
       (SELECT c.column_name
          FROM information_schema.columns AS c
         WHERE c.table_schema = t.table_schema
           AND c.table_name = t.table_name
           AND c.is_generated = 'NEVER'
         ORDER BY c.ordinal_position
         LIMIT 1) AS probe_column
  FROM information_schema.tables AS t
 WHERE t.table_schema = ANY(%s)
 ORDER BY 1, 2
"""


def relations_in(conn: psycopg.Connection[Any], schemas: Sequence[str]) -> dict[str, Relation]:
    """Every relation the connected database holds in *schemas*, keyed by qualified name.

    ``information_schema`` rather than a list in this file, and rather than the migration
    tree: the subject of this leg is the cluster, and the cluster is the only authority on
    what it contains. A relation the matrix names and the tree does not create simply does
    not appear here, and is reported as ABSENT rather than as a refusal.
    """
    found: dict[str, Relation] = {}
    for schema, name, kind, column in conn.execute(_RELATIONS_SQL, (list(schemas),)).fetchall():
        relation = Relation(
            schema=str(schema), name=str(name), kind=str(kind), column=column and str(column)
        )
        found[relation.obj] = relation
    return found


# ═════════════════════════════════════════════════════════════════════════════════════
# the probe
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Check:
    """One statement to run as the login, and the SQLSTATE the matrix predicts."""

    pair: Pair
    expected: str
    sql: str
    provenance: str

    @property
    def direction(self) -> str:
        """``allow`` when the matrix names the pair, ``deny`` when it does not."""
        return "deny" if self.expected == DENY else "allow"


@dataclass(frozen=True, slots=True)
class Outcome:
    """What the cluster said, beside what the matrix predicted."""

    check: Check
    observed: str
    detail: str
    exhibit: str | None

    @property
    def absent(self) -> bool:
        """True when the object is not in this database at all."""
        return self.observed in ABSENT_SQLSTATES

    @property
    def agreed(self) -> bool:
        """True when the cluster and the matrix said the same thing.

        An ABSENT object agrees vacuously and is counted separately — see
        :data:`ABSENT_SQLSTATES` for why that is the matrix's own contract and not a
        convenience.

        A positive check agrees when it was **not** refused for privilege. The claim being
        made is "this login is not stopped by the grant graph here", and a statement that
        got as far as a planner or constraint error has already established it — measured:
        ``INSERT INTO mainline.exposure_line`` as a login that holds INSERT returns
        ``23502``, because CockroachDB checks primary-key column presence whether or not a
        row arrives. Requiring ``00000`` would have called that a missing grant.
        """
        if self.absent:
            return True
        if self.check.expected == DENY:
            return self.observed == DENY
        return self.observed != DENY


def statement_for(relation: Relation, verb: str) -> str | None:
    """The zero-row statement that asks one privilege question and nothing else.

    Returns ``None`` when the verb has no meaningful shape for this relation — a write
    verb against a view, or a relation with no column that may be written. ``None`` is a
    reason to leave the pair out of the report's probed set and say so, never to record a
    pass.
    """
    obj = _qualified(relation.obj)
    if verb == "SELECT":
        return f"SELECT 1 FROM {obj} WHERE false"  # noqa: S608 - identifier validated above
    if not relation.writable:
        return None
    column = _ident(str(relation.column))
    if verb == "INSERT":
        # `SELECT NULL WHERE false` and not `VALUES (NULL)`: the VALUES form supplies one
        # row, which reaches the NOT NULL constraint and the RLS WITH CHECK clause. This
        # form supplies none, so the privilege check is the only check that runs.
        return f"INSERT INTO {obj} ({column}) SELECT NULL WHERE false"
    if verb == "UPDATE":
        # `SET <col> = NULL` and not `SET <col> = <col>`: reading a column in the SET
        # expression would require SELECT as well, and a probe that needs two privileges
        # cannot tell you which one is missing.
        return f"UPDATE {obj} SET {column} = NULL WHERE false"  # noqa: S608
    if verb == "DELETE":
        return f"DELETE FROM {obj} WHERE false"  # noqa: S608
    return None


def _exhibit(pair: Pair, role: str) -> str:
    """The specified token for a privilege refusal, ``grant:<verb>:<object>:<role>``.

    :func:`cases._privilege.grant_exhibit` is the authority for the shape and is used
    rather than re-spelled. It re-homes the object into the manifest namespace — correct
    for a conformance case, every one of which lives in that one schema — while this probe
    spans five. ``spec/errors.md`` §3.1 defines ``<object>`` as the relation, and the
    worked examples in ``spec/invariants/`` are fully qualified
    (``grant:INSERT:mainline.disposition:mainline_auditor``), so a relation outside the
    manifest namespace carries its own schema and the re-homing is undone for it.
    """
    from cases._exhibit import MANIFEST_NAMESPACE
    from cases._privilege import grant_exhibit

    token = grant_exhibit(pair.verb, pair.relation, role)
    if pair.schema == MANIFEST_NAMESPACE:
        return token
    return token.replace(f"{MANIFEST_NAMESPACE}.{pair.relation}", pair.obj, 1)


@dataclass(frozen=True, slots=True)
class Plan:
    """Both directions, built. What was asked, what could not be asked, and of what."""

    checks: tuple[Check, ...]
    #: Granted pairs with no zero-row statement shape — a write verb against a view, or a
    #: relation with no writable column. Carried rather than dropped: a pair that was never
    #: asked about must not be able to look like a pair that answered.
    unprobeable: tuple[Pair, ...]
    #: Every ``(schema, verb)`` that occurs among the pairs the matrix does NOT name. The
    #: sample is stratified over this set, so it is what a coverage claim is made against —
    #: and it is derived from the catalogue, never typed out.
    strata: frozenset[tuple[str, str]]
    #: How many ungranted, probeable pairs exist in total. The sample is a subset of it.
    complement: int


def _stratified(complement: Sequence[tuple[Pair, str]], sample: int) -> dict[Pair, str]:
    """Take at most *sample* pairs: one per ``(schema, verb)`` first, then in sorted order.

    Only reached when a cap is asked for. The stratification runs BEFORE the fill so that a
    schema or a verb cannot fall out of a capped run quietly — which is the only way a
    sample can lie about what it covered.
    """
    chosen: dict[Pair, str] = {}
    covered: set[tuple[str, str]] = set()
    for pair, sql in complement:
        key = (pair.schema, pair.verb)
        if key not in covered:
            covered.add(key)
            chosen[pair] = sql
    for pair, sql in complement:
        if len(chosen) >= sample:
            break
        chosen.setdefault(pair, sql)
    return chosen


def checks_for(reach: Reach, relations: Mapping[str, Relation], *, sample: int) -> Plan:
    """Build both directions.

    **``sample <= 0`` asks about EVERY ungranted pair, and that is the default.** Migration
    ``0009e`` and ``GRANTS.yaml``'s header both state the control in those words — *"asserts
    42501 for every (role, object) pair the matrix does NOT name"* — and on this schema the
    complement is a few hundred pairs, each a plan-time refusal that costs milliseconds. A
    control that can afford to be exhaustive and chooses to sample is choosing to be weaker
    for no reason.

    **When a cap IS given, the sample is deterministic and stratified, never random.** A
    random sample makes a red build irreproducible, and a red nobody can reproduce is a red
    somebody deletes. The complement is sorted, one pair is taken for every
    ``(schema, verb)`` combination that occurs in it — so no schema and no verb can fall out
    quietly — and the remainder is filled in sorted order up to *sample*. The cap exists for
    a vertical whose complement is thousands of pairs, not for this one.

    The ``strata`` and ``complement`` fields of the returned :class:`Plan` are what a
    coverage claim is made against, so that "every schema and every verb was covered" is a
    statement about the catalogue and not about a number typed into a test.
    """
    checks: list[Check] = []
    unprobeable: list[Pair] = []

    for pair, provenance in reach.granted.items():
        relation = relations.get(pair.obj)
        if relation is None:
            # The matrix names it; this tree does not create it. Recorded as ABSENT by the
            # probe itself, so the statement is still issued against the qualified name.
            checks.append(
                Check(
                    pair=pair,
                    expected=OK,
                    sql=f"SELECT 1 FROM {_qualified(pair.obj)} WHERE false",  # noqa: S608
                    provenance=provenance,
                )
            )
            continue
        sql = statement_for(relation, pair.verb)
        if sql is None:
            unprobeable.append(pair)
            continue
        checks.append(Check(pair=pair, expected=OK, sql=sql, provenance=provenance))

    complement: list[tuple[Pair, str]] = []
    for name, relation in sorted(relations.items()):
        for verb in PROBE_VERBS:
            pair = Pair(obj=name, verb=verb)
            if pair in reach.granted or pair in reach.deferred:
                continue
            sql = statement_for(relation, verb)
            if sql is not None:
                complement.append((pair, sql))

    chosen = dict(complement) if sample <= 0 else _stratified(complement, sample)

    checks.extend(
        Check(
            pair=pair,
            expected=DENY,
            sql=sql,
            provenance=f"not named by the matrix for {reach.role}",
        )
        for pair, sql in sorted(chosen.items(), key=lambda item: item[0])
    )
    return Plan(
        checks=tuple(checks),
        unprobeable=tuple(unprobeable),
        strata=frozenset((pair.schema, pair.verb) for pair, _ in complement),
        complement=len(complement),
    )


def run_probe(role_target: Target, checks: Sequence[Check], role: str) -> list[Outcome]:
    """Run every check AS the login and record what the cluster said.

    Autocommit, because the subject is refusals: a shared open transaction would make the
    statement after a refusal fail with ``25P02`` — *current transaction is aborted* — which
    is a different refusal from the one under test and would quietly replace it.
    """
    outcomes: list[Outcome] = []
    conn = psycopg.connect(role_target.dsn, autocommit=True)
    try:
        for check in checks:
            try:
                conn.execute(check.sql)  # type: ignore[arg-type]
            except psycopg.Error as exc:
                observed, detail = sqlstate_of(exc), safe(one_line(exc))
                conn.rollback()
            else:
                observed, detail = OK, "completed, 0 rows"
            outcomes.append(
                Outcome(
                    check=check,
                    observed=observed,
                    detail=detail,
                    exhibit=_exhibit(check.pair, role) if observed == DENY else None,
                )
            )
    finally:
        conn.close()
    return outcomes


# ═════════════════════════════════════════════════════════════════════════════════════
# building a world to probe
# ═════════════════════════════════════════════════════════════════════════════════════


def as_role(target: Target, role: str, database: str, password: str = "") -> Target:
    """The same target with the userinfo replaced. An empty *password* means none is sent.

    Host, port, ``sslmode`` and any ``options`` are carried over untouched: rebuilding a
    DSN by hand is how a probe ends up asking a different cluster from the one under test.

    *password* exists so that this function is usable against a secure cluster by a caller
    that already holds a credential. Nothing in this program ever supplies one — the only
    clusters it points itself at are insecure ones it built.
    """
    parts = urlsplit(target.at(database).dsn)
    host = parts.hostname or "localhost"
    port = f":{parts.port}" if parts.port else ""
    userinfo = f"{role}:{password}@" if password else f"{role}@"
    return Target(
        urlunsplit(
            (parts.scheme, f"{userinfo}{host}{port}", parts.path, parts.query, parts.fragment)
        )
    )


def ephemeral_name(tag: str = "w4") -> str:
    """A scratch database name following the pattern already in use on the local node.

    ``w_*`` / ``d_w*`` is what the ~140 worker databases on that cluster are called. Unique
    per run, because a halted migration leaves a version DIRTY and the recovery is a fresh
    database, never ``trappoint migrate force``.
    """
    return f"w_{tag}_{uuid.uuid4().hex[:10]}"


def create_database(admin: Target, database: str) -> None:
    """Create the scratch database. Never reused, never a name an operator might be using."""
    with psycopg.connect(admin.dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{_ident(database)}"')


def drop_database(admin: Target, database: str) -> None:
    """Drop it. A leaked scratch database is untidy; a failure to drop one is not a finding."""
    try:
        with psycopg.connect(admin.dsn, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{_ident(database)}" CASCADE')
    except psycopg.Error as exc:  # pragma: no cover - reported, never fatal
        print(f"  ! could not drop the scratch database: {safe(one_line(exc))}")


def apply_chain(target: Target, migrations: Path, tree: str = DEFAULT_TREE) -> tuple[int, str]:
    """Apply the migration tree through the real runner, as a subprocess. Returns (rc, tail).

    The runner is driven rather than reimplemented — what this records is the exit status
    of ``trappoint migrate up`` itself, which is the same instrument
    ``scripts/chain/apply_chain.py`` drives for the record run.

    ``--attest final`` and not ``--attest each``. The attestation chain is a different
    claim with its own control (``apply_chain.py``, and ``trappoint migrate verify``);
    recomputing a stable fingerprint after each of 271 files costs the wall-clock budget of
    this leg several times over and proves nothing about privilege.

    ``sys.executable -m`` and not the console script, so the subprocess cannot resolve to a
    different virtualenv from the one that imported psycopg above. The module entry point
    takes the subcommand directly — ``python -m trappoint_migrate up``, where the console
    script spells the same thing ``trappoint migrate up``.
    """
    base = [sys.executable, "-m", "trappoint_migrate"]
    tail = ""
    for argv in (
        [*base, "bootstrap", "--dsn", target.dsn],
        [
            *base,
            "up",
            "--dsn",
            target.dsn,
            "--tree",
            tree,
            "--migrations",
            str(migrations),
            "--attest",
            "final",
        ],
    ):
        # An argv list, never a shell string, and every element is either `sys.executable`,
        # a literal from this file, or a path the caller passed. Nothing here is data.
        proc = subprocess.run(
            argv,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        # The runner echoes its own `--dsn` on some error paths, so its last line is
        # redacted before it is carried anywhere. That is the whole reason `tail` is a
        # separate value rather than the caller reading `proc.stderr`.
        lines = [ln.rstrip() for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()]
        tail = safe(lines[-1]) if lines else ""
        if proc.returncode != 0:
            return proc.returncode, tail
    return 0, tail


def apply_matrix(target: Target, matrix: Path) -> tuple[int, tuple[str, ...]]:
    """Assert ``GRANTS.yaml`` against the database. Returns (statements applied, absent).

    ``allow_missing=True`` follows the matrix's own published contract: *"a row whose
    object is absent from the connected database is SKIPPED WITH A WARNING, never an
    error"*. The skipped rows are returned so the report can name them; a warning nobody
    prints is a warning nobody reads.
    """
    from trappoint_migrate.grants import apply, plan

    grant_plan = plan(matrix)
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        result = apply(conn, grant_plan, allow_missing=True)
    return len(result.applied), result.missing_objects


def chain_state(
    target: Target, migrations: Path, tree: str = DEFAULT_TREE
) -> tuple[int, int, bool]:
    """``(applied, files_on_disk, dirty)`` for the tree in the connected database.

    THE GUARD ON THE BORROWED PATH. A database handed to this program with ``--database``
    is trusted for nothing: if it were only part-migrated, most relations would be absent,
    every positive probe would report ABSENT — which agrees vacuously by design, because an
    absent object is the matrix's own documented skip — and the run would print a green that
    meant "there was almost nothing here". So the bookkeeping is read back and compared with
    the files on disk before a single probe is issued.

    ``trappoint.schema_migration`` is the runner's own record, read with SQL rather than
    parsed out of its prose, which is the same thing ``scripts/chain/apply_chain.py`` does
    for the record run.
    """
    files = len(sorted(migrations.glob("*.sql")))
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        try:
            rows = conn.execute(
                "SELECT state FROM trappoint.schema_migration WHERE tree = %s", (tree,)
            ).fetchall()
        except psycopg.Error as exc:
            if sqlstate_of(exc) not in ABSENT_SQLSTATES:
                raise
            return 0, files, False
    states = [str(row[0]) for row in rows]
    return states.count("applied"), files, "dirty" in states


def ensure_login(target: Target, role: str, database: str) -> str:
    """Make *role* a login that can open a connection to *database*. Returns a note.

    Two facts are handled here rather than discovered as failures.

    **An insecure cluster cannot hold a password.** The local single-node development node
    runs ``--insecure`` and CockroachDB refuses outright: *"setting or updating a password
    is not supported in insecure mode"*. ``scripts/deploy/cloud_roles.py`` documents that
    branch and states the fact in every probe line so a passing rehearsal is never mistaken
    for a passing deployment; the same is done here. **No password is generated, printed or
    stored by this program at all** — it never needs one, because the only cluster it is
    ever pointed at is one it built.

    **``CONNECT`` is plumbing, not surface.** Without it the probe cannot open the
    connection, and "could not connect" would be reported as though every privilege were
    missing. It is granted explicitly and is not part of what this leg asserts.
    """
    note = ""
    with psycopg.connect(target.dsn, autocommit=True) as conn:
        try:
            conn.execute(f'CREATE ROLE IF NOT EXISTS "{_ident(role)}" LOGIN')
        except psycopg.Error as exc:
            if "insecure" not in one_line(exc).lower():
                raise
            conn.execute(f'CREATE ROLE IF NOT EXISTS "{_ident(role)}"')
            note = "created without a password — this cluster is insecure"
        conn.execute(f'GRANT CONNECT ON DATABASE "{_ident(database)}" TO "{_ident(role)}"')
    return note or "login exists"


@dataclass(frozen=True, slots=True)
class World:
    """A migrated, granted database and the label by which it may be named out loud."""

    admin: Target
    target: Target
    database: str
    label: str
    owned: bool
    chain_tail: str
    statements: int
    absent_grants: tuple[str, ...]
    login_note: str


@contextmanager
def world(
    admin: Target,
    *,
    database: str | None,
    role: str,
    migrations: Path,
    matrix: Path,
    keep: bool = False,
) -> Iterator[World]:
    """Build (or borrow) a database, apply the tree and the matrix, and yield it.

    When *database* is given the database is BORROWED: nothing is created and nothing is
    dropped, and the tree is not applied over it. That is the mode an operator uses against
    a database ``apply_chain.py --keep`` left behind. Otherwise one is created here, named
    like every other scratch database on the node, and dropped again on the way out unless
    *keep* says so.
    """
    owned = database is None
    name = database or ephemeral_name()
    chain_tail = ""
    if owned:
        create_database(admin, name)
    target = admin.at(name)
    try:
        if owned:
            code, chain_tail = apply_chain(target, migrations)
            if code != 0:
                raise RuntimeError(f"the migration tree did not apply (exit {code}): {chain_tail}")
        applied, files, dirty = chain_state(target, migrations)
        if applied != files or dirty:
            raise RuntimeError(
                f"this database holds {applied} applied migration(s) against {files} file(s) "
                f"on disk{' and a DIRTY version' if dirty else ''}. A probe over a "
                "part-migrated database reports most of the matrix as ABSENT and prints a "
                "green that means 'there was almost nothing here'. Build a fresh one (drop "
                "--database), or point at one `apply_chain.py --keep` finished."
            )
        if not owned:
            chain_tail = f"borrowed, {applied}/{files} applied and no dirty version"
        statements, absent = apply_matrix(target, matrix)
        note = ensure_login(target, role, name)
        yield World(
            admin=admin,
            target=target,
            database=name,
            label=target.label,
            owned=owned,
            chain_tail=chain_tail,
            statements=statements,
            absent_grants=absent,
            login_note=note,
        )
    finally:
        if owned and not keep:
            drop_database(admin, name)


# ═════════════════════════════════════════════════════════════════════════════════════
# the report
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Report:
    """Everything one probe found, in a shape both the table and the test read."""

    role: str
    label: str
    reach: Reach
    plan: Plan
    outcomes: tuple[Outcome, ...]
    absent_grants: tuple[str, ...]
    login_note: str
    relations: int
    #: The schemas actually enumerated — the matrix's own ``schemas:`` list plus any schema
    #: the role's closure grants in. ``trappoint`` arrives that way and would otherwise be
    #: probed by nothing while appearing in the grant plan.
    schemas: tuple[str, ...]
    notes: tuple[str, ...] = field(default=())

    @property
    def unprobeable(self) -> tuple[Pair, ...]:
        """Granted pairs that have no zero-row statement shape, carried from the plan."""
        return self.plan.unprobeable

    @property
    def differences(self) -> tuple[Outcome, ...]:
        """Every outcome where the cluster and the matrix disagreed."""
        return tuple(o for o in self.outcomes if not o.agreed)

    @property
    def positives(self) -> tuple[Outcome, ...]:
        """Every outcome for a pair the matrix names."""
        return tuple(o for o in self.outcomes if o.check.expected == OK)

    @property
    def negatives(self) -> tuple[Outcome, ...]:
        """Every outcome for a pair the matrix does not name."""
        return tuple(o for o in self.outcomes if o.check.expected == DENY)

    @property
    def absent(self) -> tuple[Outcome, ...]:
        """Every outcome whose object this migration tree does not create."""
        return tuple(o for o in self.outcomes if o.absent)

    def summary(self) -> str:
        """One line: what was asked, and what disagreed."""
        reachable = sum(1 for o in self.positives if o.agreed and not o.absent)
        refused = sum(1 for o in self.negatives if o.agreed)
        return (
            f"{self.role} on {self.label}: {reachable}/{len(self.positives) - len(self.absent)} "
            f"granted pairs reachable, {refused}/{len(self.negatives)} ungranted pairs refused "
            f"with {DENY} (of {self.plan.complement} in the complement, across "
            f"{len(self.plan.strata)} schema/verb strata), {len(self.absent)} absent from the "
            f"tree, {len(self.differences)} difference(s)"
        )

    def table(self) -> str:
        """The probe as a table an operator reads. ASCII only.

        ASCII because this is printed to a console whose encoding is not ours to choose: a
        Windows ``cp1252`` terminal raises ``UnicodeEncodeError`` on box-drawing characters,
        and a report that cannot be printed is a report nobody reads. ``grants.py`` learned
        the same lesson about ``GrantPlan.render``.
        """
        rows = [
            f"{'dir':<6} {'expect':<6} {'saw':<6} {'ok':<3} {'verb':<6} {'object':<44} why",
            "-" * 140,
        ]
        for outcome in self.outcomes:
            mark = "--" if outcome.absent else ("ok" if outcome.agreed else "!!")
            why = outcome.exhibit or outcome.check.provenance
            if outcome.absent:
                why = "ABSENT from this tree; skipped with a warning per GRANTS.yaml's contract"
            rows.append(
                f"{outcome.check.direction:<6} {outcome.check.expected:<6} "
                f"{outcome.observed:<6} {mark:<3} {outcome.check.pair.verb:<6} "
                f"{outcome.check.pair.obj:<44} {why}"
            )
        return "\n".join(rows)

    def failure_message(self) -> str:
        """Every difference, named, with the statement that found it. Empty when there is none.

        The message is written for somebody who has not read the plan: it names the pair,
        the verb, what was expected, what the cluster said, where the matrix says the
        privilege comes from, and — for a refusal — the ``grant:`` exhibit that identifies
        it in the corpus.
        """
        if not self.differences:
            return ""
        lines = [
            f"{len(self.differences)} privilege difference(s) for {self.role} on {self.label}.",
            "",
            "A GRANT is a claim about intent; a 42501 is evidence about behaviour. These are",
            "the pairs where the two disagreed. Each line is a statement that was run AS the",
            "login and touched zero rows, so the SQLSTATE is the grant graph and nothing else.",
            "",
        ]
        for outcome in self.differences:
            direction = (
                "the matrix GRANTS this and the cluster refused it"
                if outcome.check.expected == OK
                else "the matrix does NOT grant this and the cluster allowed it"
            )
            lines.extend(
                (
                    f"  {outcome.check.pair}",
                    f"      {direction}",
                    f"      expected {outcome.check.expected}, observed {outcome.observed}",
                    f"      matrix    {outcome.check.provenance}",
                    f"      statement {outcome.check.sql}",
                    f"      detail    {outcome.detail[:160]}",
                )
            )
            if outcome.exhibit:
                lines.append(f"      exhibit   {outcome.exhibit}")
            lines.append("")
        return "\n".join(lines)


def probe_world(
    built: World, role: str, *, matrix: Path, sample: int, schemas: Sequence[str]
) -> Report:
    """Ask the built database every question, as the role, and return the report."""
    with psycopg.connect(built.target.dsn, autocommit=True) as admin:
        catalogue = relations_in(admin, schemas)
    reach = matrix_reach(matrix, role, catalogue)

    # A schema named only by the closure's grants — `trappoint`, if the matrix grants there
    # — would be invisible to the catalogue read above. Re-read once with the full set so a
    # grant outside the matrix's declared `schemas:` is probed rather than silently absent.
    enumerated = tuple(schemas)
    extra = sorted({pair.schema for pair in reach.granted} - set(schemas))
    if extra:
        enumerated = (*schemas, *extra)
        with psycopg.connect(built.target.dsn, autocommit=True) as admin:
            catalogue = relations_in(admin, list(enumerated))
        reach = matrix_reach(matrix, role, catalogue)

    plan = checks_for(reach, catalogue, sample=sample)
    outcomes = run_probe(as_role(built.admin, role, built.database), plan.checks, role)
    notes = tuple(
        f"{verb}: {len(objs)} object(s) named by the matrix, not executed here - {why}"
        for verb, why in UNPROBED_VERBS.items()
        for objs in (reach.unprobed.get(verb, ()),)
        if objs
    )
    return Report(
        role=role,
        label=built.label,
        reach=reach,
        plan=plan,
        outcomes=tuple(outcomes),
        absent_grants=built.absent_grants,
        login_note=built.login_note,
        relations=len(catalogue),
        schemas=enumerated,
        notes=notes,
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# the command
# ═════════════════════════════════════════════════════════════════════════════════════


def matrix_schemas(matrix: Path) -> tuple[str, ...]:
    """The schemas the matrix itself declares. Not a list in this file."""
    from trappoint_migrate.grants import load_matrix

    declared = load_matrix(matrix).get("schemas")
    if not isinstance(declared, list) or not declared:
        raise ValueError(
            f"{matrix} declares no `schemas:` list. This probe enumerates relations from the "
            "schemas the matrix names; a matrix that names none gives it nothing to ask about."
        )
    return tuple(_ident(str(s)) for s in declared)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="privilege_conformance",
        description=(
            "Connect AS a login and assert both directions of GRANTS.yaml: every pair the "
            "matrix names is reachable, and a sample of the pairs it does not name returns "
            "42501. Never prints a DSN, a userinfo or a password."
        ),
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="admin DSN (default: $LOCAL_DSN, $TRAPPOINT_DSN, then the local node). Never echoed.",
    )
    parser.add_argument("--role", default=DEFAULT_ROLE)
    parser.add_argument(
        "--database",
        default=None,
        help="probe an EXISTING migrated database; nothing is created and nothing is dropped",
    )
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--migrations", type=Path, default=DEFAULT_MIGRATIONS)
    parser.add_argument(
        "--negative-sample",
        type=int,
        default=0,
        help=(
            "how many ungranted pairs to probe. 0 (the default) probes EVERY one, which is "
            "what 0009e and GRANTS.yaml's header both ask for; a positive number caps it "
            "with a deterministic, stratified sample and is for a much larger schema"
        ),
    )
    parser.add_argument("--keep", action="store_true", help="do not drop the scratch database")
    parser.add_argument("--quiet", action="store_true", help="print the verdict, not the table")
    return parser


def matrix_errors() -> tuple[type[BaseException], ...]:
    """Every exception class a malformed ``GRANTS.yaml`` can raise, resolved at call time.

    ``trappoint_migrate.grants`` refuses a structural mistake with ``UsageError`` and
    imports PyYAML dynamically, so a *syntactic* mistake surfaces as ``yaml.YAMLError``
    from inside it. Both are the same event for an operator — "the matrix does not parse" —
    and neither is a defect in this program, so both produce a sentence naming the file
    rather than a traceback that reads like a crash in the probe.
    """
    classes: list[type[BaseException]] = [ValueError]
    from trappoint_migrate.errors import UsageError

    classes.append(UsageError)
    try:
        import yaml
    except ImportError:  # pragma: no cover - PyYAML absent; UsageError already says so
        return tuple(classes)
    classes.append(yaml.YAMLError)
    return tuple(classes)


def resolve_dsn(explicit: str | None) -> Target:
    """The cluster to probe: ``--dsn``, then the four names a session publishes, then local.

    The order is the one every other cluster-aware program in this repository uses, and the
    result is a :class:`Target` rather than a string so that no caller of this function ever
    holds a DSN it could print by accident.
    """
    candidates = (
        explicit,
        os.environ.get("LOCAL_DSN"),
        os.environ.get("TRAPPOINT_DSN"),
        os.environ.get("MAINLINE_TEST_DSN"),
        os.environ.get("COCKROACH_URL"),
        os.environ.get("CRDB_URL"),
    )
    for value in candidates:
        if value:
            return Target(value)
    return Target(DEFAULT_DSN)


def render(report: Report, *, quiet: bool) -> None:
    """Print the probe: the table, then everything that was NOT asked and why.

    The lines after the table are the honest part. A report that printed only what it asked
    would let a verb with no statement shape, an object the tree does not create, and a
    privilege class this leg cannot execute all disappear into a green — and each of those
    is a different fact somebody may need. They are counted and named.
    """
    print(f"relations     {report.relations} in {', '.join(report.schemas)}")
    print(f"membership    {', '.join(report.reach.members_of) or '(none)'}")
    if not quiet:
        print()
        print(report.table())
    for note in report.notes:
        print(f"  note        {note}")
    for pair in report.unprobeable:
        print(f"  unprobed    {pair} - no zero-row statement shape (view, or no writable column)")
    if report.absent_grants:
        print(f"  absent      {len(report.absent_grants)} matrix row(s) whose object this tree")
        print("              does not create; skipped with a warning per GRANTS.yaml's contract")
    print()
    print(report.summary())


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911 - one branch per exit reason
    args = build_parser().parse_args(argv)
    admin = resolve_dsn(args.dsn)

    if not args.matrix.is_file():
        print(f"privilege_conformance: no grant matrix at {args.matrix}", file=sys.stderr)
        return EXIT_UNUSABLE
    if args.database is None and not args.migrations.is_dir():
        print(f"privilege_conformance: no migration tree at {args.migrations}", file=sys.stderr)
        return EXIT_UNUSABLE

    print(f"cluster       {admin.label}")
    print(f"role          {args.role}")
    print(f"matrix        {args.matrix.name}")

    # Asked BEFORE anything is built, and before any login is created. A role the matrix
    # does not declare has nothing to probe, and creating a cluster-wide login for it — on
    # a shared development node, where roles outlive the database that occasioned them —
    # would leave a principal behind to answer a question that was never asked. The
    # relations argument is empty because `declared` is a property of the matrix alone.
    try:
        declared = matrix_reach(args.matrix, args.role, {}).declared
    except matrix_errors() as exc:
        print(
            f"privilege_conformance: {args.matrix} does not parse, so there is no matrix to "
            f"probe against: {safe(str(exc))}",
            file=sys.stderr,
        )
        return EXIT_UNUSABLE
    if not declared:
        print()
        print(f"NO SUBJECT    {args.role} is not declared anywhere in {args.matrix.name}.")
        print("              The matrix grants it nothing, so every negative probe would pass")
        print("              and prove nothing. That is the vacuity this control exists to end.")
        return EXIT_NO_SUBJECT

    try:
        with world(
            admin,
            database=args.database,
            role=args.role,
            migrations=args.migrations,
            matrix=args.matrix,
            keep=args.keep,
        ) as built:
            built_or_borrowed = "built here" if built.owned else "borrowed"
            print(f"database      {built.database}  ({built_or_borrowed})")
            print(f"chain         {built.chain_tail[:100]}")
            print(f"grants        {built.statements} statement(s) asserted, ", end="")
            print(f"{len(built.absent_grants)} skipped (object absent from this tree)")
            print(f"login         {args.role}: {built.login_note}")
            report = probe_world(
                built,
                args.role,
                matrix=args.matrix,
                sample=args.negative_sample,
                schemas=matrix_schemas(args.matrix),
            )
    except psycopg.OperationalError as exc:
        print(
            f"privilege_conformance: could not reach the cluster: {safe(one_line(exc))}",
            file=sys.stderr,
        )
        return EXIT_UNUSABLE
    except RuntimeError as exc:
        print(f"privilege_conformance: {safe(str(exc))}", file=sys.stderr)
        return EXIT_UNUSABLE
    except matrix_errors() as exc:
        print(
            f"privilege_conformance: {args.matrix} does not parse, so there is no matrix to "
            f"probe against: {safe(str(exc))}",
            file=sys.stderr,
        )
        return EXIT_UNUSABLE

    render(report, quiet=args.quiet)
    if report.differences:
        print()
        print(report.failure_message())
        print("VERDICT       PRIVILEGE CONFORMANCE FAILED")
        return EXIT_DIFFERENCE
    print("VERDICT       PRIVILEGE CONFORMANCE HOLDS")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
