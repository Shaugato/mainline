# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""The producer-existence census — *every relation a tree names, some file in it CREATEs*.

This module exists because of a defect that shipped seven times in one schema and was
found by a deployment rather than by a check.

Five tables — later seven — had their **triggers, views and RLS policies written and
nobody wrote the ``CREATE TABLE``**. Every one of those consumer files linted clean:
they cite an invariant, they carry one statement, they use no sequence, their number
falls in a band whose mode is right. Rules A, B, C and the sequence ban are all
statements about *a file*. Not one of them can see that the file names an object that
does not exist anywhere in the tree, because that is a statement about the *tree*.

The cost was measured on 2026-08-10: ``trappoint migrate up`` applied 155 of 261 files
and then refused ``0121_trg_check_materialised`` with ``[42P01] relation
"mainline_ops.outbox" does not exist``. Forward-only means the 105 files below the halt
had never been executed by the runner that a deployment uses. One absent ``CREATE
TABLE`` made two fifths of the schema unreachable.

**So the rule is: subtract what the tree produces from what the tree references, and
whatever is left is a gap.** It is a whole-tree rule, it is cheap, it is textual, and it
would have refused all seven the day they were written.

WHY THE PRODUCER SET COVERS NINE OBJECT KINDS AND NOT JUST TABLES
-----------------------------------------------------------------

The naive version of this check — collect ``CREATE TABLE``, subtract from every
``schema.name`` in the text — is *wrong in the noisy direction*, and noise is how a lint
dies. ``mainline.subject_state`` is a ``CREATE TYPE`` and appears as a cast
(``::mainline.subject_state``); ``mainline.fn_refuse_mutation`` is a ``CREATE FUNCTION``
and appears as a call (``mainline.fn_refuse_mutation()``); ``mainline.v_blame_origin`` is
a ``CREATE VIEW``. A table-only producer set reports all three as absent relations, an
author adds a lookahead for ``::`` and ``(``, the lookahead is fragile, and two releases
later the rule is off.

Collecting **every** ``CREATE`` of a schema-qualified object — table, view, materialized
view, function, procedure, type, trigger, policy, index, schema — removes the whole
problem without a single heuristic: a type that is cast to is a type that was created, so
it is in the producer set and it never reaches the findings. There is no syntax
special-casing anywhere in this module, and that is the design, not an accident of it.

WHAT IS DELIBERATELY NOT REPORTED
---------------------------------

``trappoint.*`` is the substrate's own bookkeeping schema — ``schema_migration``,
``schema_lock``, ``schema_attestation`` — created by ``trappoint migrate bootstrap``
*before* any migration runs, so no migration produces it and every migration may name it.
``pg_catalog.*``, ``information_schema.*``, ``crdb_internal.*`` and ``system.*`` are the
engine's. Those five are allowlisted by name rather than by pattern, because "looks like
a catalog" is exactly the kind of guess that later hides a real gap.

References are read from **comment-stripped** SQL (:mod:`trappoint_migrate.sqltext`), so
a ``-- requires: mainline_ops.outbox`` header does not create a reference and this
docstring does not either — while a name inside a dollar-quoted PL/pgSQL body *does*,
which is the case that matters: ``0101_fn_check_materialised`` names
``mainline_ops.outbox`` only inside its body, and that body is what CockroachDB resolves
when the trigger in ``0121`` binds it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .sqltext import strip_sql_comments

__all__ = [
    "ALLOWLISTED_SCHEMAS",
    "GOVERNED_SCHEMAS",
    "PRODUCER_ABSENT_RULE",
    "AbsentProducer",
    "ProducerCensus",
    "Reference",
    "absent_detail",
    "census",
    "producers_in",
    "references_in",
]

#: The rule name reported by ``trappoint migrate lint``.
PRODUCER_ABSENT_RULE = "producer-absent"

#: The schemas a MAINLINE migration tree is responsible for creating. A reference into
#: one of these must have a producer in the same tree; a reference anywhere else is not
#: this tree's business.
GOVERNED_SCHEMAS: tuple[str, ...] = (
    "mainline",
    "mainline_meas",
    "mainline_audit",
    "mainline_qa",
    "mainline_ops",
    "trappoint_ref",
)

#: Schemas that exist before the first migration runs and are therefore never produced by
#: one. ``trappoint`` is created by ``trappoint migrate bootstrap``; the other four are
#: the engine's. Listed literally — a pattern such as "ends in ``_catalog``" is a guess,
#: and a guess in an allowlist is how a real gap stops being reported.
ALLOWLISTED_SCHEMAS: tuple[str, ...] = (
    "trappoint",
    "pg_catalog",
    "information_schema",
    "crdb_internal",
    "system",
)

#: ``NNNN[a-z]_…​.sql`` (MR-5). Deliberately permissive about the slug: a file the naming
#: rule condemns is still a file whose references are real, and excluding it here would
#: mean a badly-named migration could name an absent relation invisibly.
_MIGRATION_FILE_RE = re.compile(r"^\d{4}[a-z]?_.*\.sql$")

# The modifiers CockroachDB accepts between CREATE and the object kind, listed literally
# rather than matched as "any run of words". A loose `(?:\w+\s+)*?` would let a stray
# keyword three clauses downstream be read as an object kind and so admit a producer that
# does not exist — the one failure mode of this module that is silent. An unknown
# modifier fails the other way: a producer is missed, a finding is raised, and somebody
# reads it.
_CREATE_MODIFIER = r"(?:OR\s+REPLACE|UNIQUE|INVERTED|VECTOR|TEMP|TEMPORARY|UNLOGGED|GLOBAL|LOCAL)"

# MATERIALIZED VIEW precedes VIEW: alternation is ordered, and the shorter branch would
# otherwise win and leave `VIEW` unconsumed.
_OBJECT_KIND = (
    r"(?:TABLE|MATERIALIZED\s+VIEW|VIEW|FUNCTION|PROCEDURE|TYPE|TRIGGER|POLICY|INDEX|SCHEMA)"
)

_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_$]*"

_PRODUCER_RE = re.compile(
    rf"\bCREATE\s+(?:{_CREATE_MODIFIER}\s+)*{_OBJECT_KIND}\s+"
    rf"(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>{_IDENTIFIER}(?:\.{_IDENTIFIER})?)",
    re.IGNORECASE,
)


def _reference_re(schemas: Sequence[str]) -> re.Pattern[str]:
    """Compile the schema-qualified-reference pattern for *schemas*.

    Alternatives are ordered longest-first so ``mainline_meas.standing`` is read as one
    reference into ``mainline_meas`` rather than a failed attempt at ``mainline``. Python
    would backtrack into the longer branch anyway; ordering it makes the intent legible
    and the match independent of that.
    """
    alternatives = "|".join(re.escape(s) for s in sorted(schemas, key=len, reverse=True))
    return re.compile(
        rf"\b(?P<schema>{alternatives})\.(?P<object>[A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    )


@dataclass(frozen=True, slots=True)
class Reference:
    """One mention of a schema-qualified relation, located in the file that made it."""

    relation: str
    path: Path
    line: int


@dataclass(frozen=True, slots=True)
class AbsentProducer:
    """A relation this tree names and does not create, with every site that names it."""

    relation: str
    references: tuple[Reference, ...]

    @property
    def first(self) -> Reference:
        """The earliest reference in apply order — where the chain will halt."""
        return self.references[0]


@dataclass(frozen=True, slots=True)
class ProducerCensus:
    """The whole subtraction: what a tree produces, what it references, what is missing."""

    root: Path
    files: tuple[Path, ...]
    produced: Mapping[str, Path]
    referenced: tuple[Reference, ...]
    absent: tuple[AbsentProducer, ...]

    @property
    def ok(self) -> bool:
        """True when every governed relation the tree names is created inside it."""
        return not self.absent


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def producers_in(sql: str) -> set[str]:
    """Return every schema-qualified object *sql* creates, lowercased.

    Unqualified names — ``CREATE TRIGGER trg_x ON mainline.permit``, ``CREATE POLICY
    p ON …``, ``CREATE SCHEMA mainline_ops`` — produce nothing here by design: the
    reference pattern only ever yields ``schema.object``, so an unqualified producer
    could not match one anyway, and inventing a qualification for it would be a guess.

    *sql* is expected to be comment-stripped; passing raw SQL would let a commented-out
    ``CREATE TABLE`` satisfy the rule, which is the exact inverse of its purpose.
    """
    found: set[str] = set()
    for match in _PRODUCER_RE.finditer(sql):
        name = match.group("name").lower()
        if "." in name:
            found.add(name)
    return found


def references_in(
    sql: str,
    *,
    governed_schemas: Sequence[str] = GOVERNED_SCHEMAS,
) -> list[tuple[str, int]]:
    """Return ``(relation, offset)`` for every governed schema-qualified name in *sql*.

    Offsets are into *sql* itself; the caller converts them to line numbers against the
    same string. ``strip_sql_comments`` preserves newlines, so a line number computed on
    stripped text is the line number in the file a reader will open.
    """
    pattern = _reference_re(governed_schemas)
    hits: list[tuple[str, int]] = []
    for match in pattern.finditer(sql):
        schema = match.group("schema").lower()
        if schema in ALLOWLISTED_SCHEMAS:
            continue
        hits.append((f"{schema}.{match.group('object').lower()}", match.start()))
    return hits


def migration_files(root: Path) -> list[Path]:
    """Return every ``NNNN[a-z]_*.sql`` under *root*, in apply order.

    Sorted by name, which for a tree obeying MR-5 is apply order, which is the order the
    findings should be read in: the first absent relation is the one the runner halts on.
    """
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.rglob("*.sql") if p.is_file() and _MIGRATION_FILE_RE.match(p.name)),
        key=lambda p: (p.name, str(p)),
    )


def census(
    root: Path,
    *,
    governed_schemas: Sequence[str] = GOVERNED_SCHEMAS,
) -> ProducerCensus:
    """Take the producer/reference census of the migration tree at *root*.

    Both halves are read from the same comment-stripped text, so the rule cannot be
    satisfied by a comment and cannot be tripped by one either.
    """
    files = migration_files(root)
    produced: dict[str, Path] = {}
    referenced: list[Reference] = []

    for path in files:
        code = strip_sql_comments(path.read_text(encoding="utf-8"))
        for relation in sorted(producers_in(code)):
            produced.setdefault(relation, path)
        for relation, offset in references_in(code, governed_schemas=governed_schemas):
            referenced.append(Reference(relation=relation, path=path, line=_line_of(code, offset)))

    by_relation: dict[str, list[Reference]] = {}
    for reference in referenced:
        if reference.relation in produced:
            continue
        by_relation.setdefault(reference.relation, []).append(reference)

    absent = tuple(
        AbsentProducer(relation=relation, references=tuple(sites))
        for relation, sites in sorted(
            by_relation.items(),
            key=lambda item: (item[1][0].path.name, item[1][0].line, item[0]),
        )
    )
    return ProducerCensus(
        root=root,
        files=tuple(files),
        produced=dict(sorted(produced.items())),
        referenced=tuple(referenced),
        absent=absent,
    )


def _cite(reference: Reference) -> str:
    return f"{reference.path.name}:{reference.line}"


def absent_detail(absent: AbsentProducer, *, root: Path | str) -> str:
    """Render the sentence a ``producer-absent`` finding carries.

    It names the relation, the site that will halt the chain, every other site that
    names it, and the remedy — because the remedy for this defect is never "delete the
    reference": seven consumers were right and one ``CREATE TABLE`` was missing.

    *root* is interpolated as written, so a caller producing an evidence artefact can
    pass a repository-relative path and keep a developer's home directory out of it.
    """
    others = [_cite(r) for r in absent.references[1:]]
    tail = f"; also {', '.join(others)}" if others else ""
    return (
        f"{absent.relation} is referenced here and no migration under {root} CREATEs it. "
        f"A relation with consumers and no producer applies clean until the first "
        f"statement that resolves it, and then refuses with 'relation "
        f'"{absent.relation}" does not exist\' and stops the forward-only chain dead — '
        f"every file below the halt goes unapplied. "
        f"Referenced by {len(absent.references)} site(s): {_cite(absent.first)}{tail}. "
        f"Write the producer; do not delete the reference."
    )


def absent_producers(
    root: Path,
    *,
    governed_schemas: Sequence[str] = GOVERNED_SCHEMAS,
) -> tuple[AbsentProducer, ...]:
    """Return only the gaps for *root* — the census without the bookkeeping."""
    return census(root, governed_schemas=governed_schemas).absent


def census_payload(report: ProducerCensus, *, relative_to: Path | None = None) -> dict[str, object]:
    """Render *report* as a JSON-ready mapping, for the evidence artefact.

    Every number in the payload is derived from the files walked in this run; nothing is
    asserted. *relative_to* rewrites paths against a repository root so the artefact does
    not carry a developer's home directory.
    """

    def _rel(path: Path) -> str:
        if relative_to is None:
            return path.as_posix()
        try:
            return path.resolve().relative_to(relative_to.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    root_label = _rel(report.root)
    return {
        "tree": root_label,
        "files": len(report.files),
        "produced": len(report.produced),
        "references": len(report.referenced),
        "absent_relations": [a.relation for a in report.absent],
        "absent": [
            {
                "relation": a.relation,
                # Null, always, and the field is present so that it is a stated fact
                # rather than an omission: this rule reads files. Nothing was executed,
                # no server answered, so there is no SQLSTATE to quote — which is the
                # whole point of catching the defect here instead of at file 156.
                "sqlstate": None,
                "references": [
                    {"file": r.path.name, "line": r.line, "path": _rel(r.path)}
                    for r in a.references
                ],
                "finding": (
                    f"{_rel(a.first.path)}:{a.first.line}: {PRODUCER_ABSENT_RULE} — "
                    f"{absent_detail(a, root=root_label)}"
                ),
            }
            for a in report.absent
        ],
    }


def iter_absent_relations(reports: Iterable[ProducerCensus]) -> list[str]:
    """Return the sorted union of absent relation names across *reports*."""
    names: set[str] = set()
    for report in reports:
        names.update(a.relation for a in report.absent)
    return sorted(names)
