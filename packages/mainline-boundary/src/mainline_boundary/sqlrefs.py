# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""LEG A — what the demo-api's SQL demands of the role it connects as.

``docs/leads/grants-in-migrations-plan.md`` **R7**. The public Function URL is
``authorization_type = NONE``, so every anonymous caller executes as ``mainline_api``.
Two documents therefore have to agree and until now nothing compared them: the SQL this
application issues, and the privileges that role holds. This module reads the first of
those two documents. ``verticals/mainline/apps/demo-api/tests/test_privilege_census.py``
reads the second and prints the difference.

The plan's R4 is what this is for. Eleven relations the shipping app references are named
nowhere in ``scripts/deploy/cloud_roles.py``; they were hand-granted against the live
cluster on 2026-08-14 and the repository was never told. A comparison that runs in
milliseconds, in any lane, with no cluster, would have been red before the first deploy.

THREE LEGS, THE SAME SHAPE AS :mod:`mainline_boundary.astscan`
--------------------------------------------------------------
* **a direct scan** — every ``.py`` under the demo-api source root is parsed, its string
  constants collected (f-string literal parts and ``textwrap.dedent`` bodies included,
  because both are ordinary ``ast.Constant`` values once the parser has folded them), and
  every schema-qualified name following ``FROM``, ``JOIN``, ``INSERT INTO``,
  ``UPSERT INTO``, ``DELETE FROM``, ``INTO``, ``UPDATE``, ``CALL`` or ``EXECUTE`` is
  extracted **with the verb it was issued under**, plus one shape the keyword list does
  not reach — a routine invoked inside a ``SELECT`` list, which is how ``refusal.py:141``
  calls ``trappoint.explain_refusal`` and is an ``EXECUTE`` demand like any other;
* **a second, independent extraction** — a regex sweep over the raw bytes of the same
  files, which knows nothing about Python. The two sets must be equal.
  :data:`RULE_PATHS_DISAGREE` is a violation, not a merge: a scanner whose one extraction
  path silently stops matching reports an empty set, and an empty set is indistinguishable
  from a clean result at the call site;
* **unparseable is a violation** — a ``.py`` the scanner cannot parse has not been
  cleared, and "not cleared" is not "clean". The same sentence as E3, for the same reason.

WHY THE VERB IS CARRIED AND NOT JUST THE NAME
---------------------------------------------
R4b. ``transitions.py`` issues ``INSERT INTO mainline.exposure_receipt`` and
``INSERT INTO mainline.exposure_line``. Both relations appear in ``cloud_roles.API_READ``,
which grants ``SELECT``, and in no write list. A census that compared names only would
call that pair satisfied. Granting ``SELECT`` where an ``INSERT`` is issued is a ``42501``
waiting for the first judge who drives the path, so the unit of comparison is
``(relation, verb)`` and never ``relation``.

WHAT IS EXCLUDED, BY NAME, AND WHY
----------------------------------
:data:`NOT_PRIVILEGE_DEMANDS` holds ``information_schema``, ``pg_catalog`` and
``crdb_internal``. Every login can read them: they are the SQL standard's and
CockroachDB's own catalogs, readable by any user with ``CONNECT``, and no ``GRANT`` in
``GRANTS.yaml`` or ``cloud_roles.py`` mentions them or could. ``reads.py`` legitimately
reads all three — ``information_schema.views`` at ``reads.py:2262`` is how the audit
surface discovers its own views — so they are excluded by name rather than by a predicate,
and they are RECORDED in the report as exemptions so the exclusion is a decision a
reviewer can argue with rather than a hole.

THE DYNAMIC REFERENCE IS RESOLVED, NEVER DROPPED
------------------------------------------------
``reads.py:2331`` builds ``f"SELECT * FROM mainline_audit.{name} LIMIT …"`` where ``name``
came from ``information_schema.views`` a few lines earlier. The literal parts of that
f-string name a schema and no relation. Dropping it would make fourteen granted views look
like fourteen over-grants; inventing a list of them here would be a second copy of a list
that already exists. So the f-string hole is rendered as :data:`DYNAMIC_RELATION`, the
reference is carried as a demand on the WHOLE SCHEMA, and it is resolved against the
authority that decides what is in that schema — the ``CREATE VIEW`` statements in
``verticals/mainline/db/migrations/``. A dynamic reference into a schema whose relations
cannot be enumerated is :data:`RULE_UNRESOLVED_DYNAMIC`, a violation: a demand this census
cannot measure has not been measured, and "not measured" is not "nothing".

THE FLOORS
----------
Three, one per mechanism, because each has its own regex and each can rot alone:
:data:`MINIMUM_LITERAL_RELATIONS` (39, R4's count), :data:`MINIMUM_RESOLVED_RELATIONS`
(14, the audit views behind the one dynamic reference) and
:data:`MINIMUM_ROUTINE_DEMANDS` (2, ``mainline.merge_permit`` and
``trappoint.explain_refusal``). A scanner that finds three must be red. They are floors
and never ceilings — the tree measures **40** distinct names written out today, one more
than R4's 39, because the routine rule reaches ``trappoint.explain_refusal`` and a
keyword-only sweep does not — so a relation added tomorrow raises the count and nothing
here needs editing. Lowering one to make a run green is the single move this module
exists to prevent.

THE ESCAPE HATCH IS VISIBLE
---------------------------
A string constant naming ``<schema>.<relation>`` in a schema this census has no ruling for
is :data:`RULE_UNRULED_SCHEMA`. Any line may carry ``# mainline-boundary: not-sql
<reason>`` to say the text is prose rather than a statement, and every use appears in the
report's exemptions with its reason. The rule is applied on the AST leg only, because
``from collections.abc import Iterator`` is indistinguishable from ``FROM collections.abc``
to a sweep that does not parse Python — five such lines exist in this very tree.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .findings import Report
from .repo import expand_roots, iter_files, iter_python_files, rel

ENFORCEMENT = "SQLREF"

AUTHORITY = "docs/leads/grants-in-migrations-plan.md R7 (Leg A)"

#: The shipping demo-api source. Not the tests: a test may name a relation in order to
#: assert something about it, and a test's connection is not the Lambda's connection.
DEMO_API_ROOTS: tuple[str, ...] = ("verticals/mainline/apps/demo-api/src/mainline_demo_api",)

#: Where a schema's relations are DECLARED, and therefore the only place a dynamic
#: reference into a schema may be resolved from. The migration set is the authority for
#: what exists; ``cloud_roles.AUDIT_VIEWS`` and ``GRANTS.yaml`` are claims about what may
#: be reached, which is the other document and the thing being compared against.
MIGRATION_ROOTS: tuple[str, ...] = ("verticals/mainline/db/migrations",)

#: The schemas whose objects need a ``GRANT``. Five are this vertical's own
#: (``GRANTS.yaml``'s ``schemas:`` key); ``trappoint`` is the bookkeeping schema
#: ``trappoint migrate bootstrap`` creates, which is why the vertical's matrix does not
#: list it and why R6 records ``USAGE ON SCHEMA trappoint`` as missing. ``mainline_qa`` is
#: scanned even though no demo-api statement may ever name it: a reference to it is a
#: finding in its own right (S14), and a schema that is not scanned cannot produce one.
#: ``test_privilege_census.py`` asserts this tuple against ``GRANTS.yaml``'s own
#: declaration, so it is checked against its authority rather than trusted.
PRIVILEGED_SCHEMAS: tuple[str, ...] = (
    "mainline",
    "mainline_audit",
    "mainline_meas",
    "mainline_ops",
    "mainline_qa",
    "trappoint",
)

#: NOT privilege demands. See this module's docstring: these are the standard and
#: CockroachDB catalogs, readable by every login that can connect, named by no grant in
#: this repository and grantable by none. Excluded BY NAME so that the exclusion is one
#: line a reviewer can read, and recorded as exemptions so that it is not silence.
NOT_PRIVILEGE_DEMANDS: frozenset[str] = frozenset(
    {"information_schema", "pg_catalog", "crdb_internal"}
)

#: What an f-string hole, or any other interpolation, is rendered as. A valid lower_snake
#: identifier so that one regex serves both the literal and the dynamic case.
DYNAMIC_RELATION = "__interpolated__"

#: Measured on 2026-08-15 over ``DEMO_API_ROOTS``: 39 distinct schema-qualified names
#: reached through a statement keyword (the plan's R4 count), 14 ``mainline_audit`` views
#: resolved behind the one dynamic reference, and 2 routines invoked —
#: ``mainline.merge_permit`` by ``CALL`` and ``trappoint.explain_refusal`` inside a
#: ``SELECT``. FLOORS, never ceilings. See this module's docstring.
MINIMUM_LITERAL_RELATIONS = 39
MINIMUM_RESOLVED_RELATIONS = 14
MINIMUM_ROUTINE_DEMANDS = 2

PRAGMA_NOT_SQL = "mainline-boundary: not-sql"

RULE_UNPARSEABLE = "SQLREF-UNPARSEABLE"
RULE_UNREADABLE = "SQLREF-UNREADABLE"
RULE_PATHS_DISAGREE = "SQLREF-PATHS-DISAGREE"
RULE_LITERAL_FLOOR = "SQLREF-LITERAL-FLOOR"
RULE_RESOLVED_FLOOR = "SQLREF-RESOLVED-FLOOR"
RULE_ROUTINE_FLOOR = "SQLREF-ROUTINE-FLOOR"
RULE_UNRESOLVED_DYNAMIC = "SQLREF-UNRESOLVED-DYNAMIC"
RULE_UNRULED_SCHEMA = "SQLREF-UNRULED-SCHEMA"
RULE_ROOT_ABSENT = "SQLREF-ROOT-ABSENT"

#: Keyword → the privilege(s) that keyword's statement needs on the relation that follows
#: it. ``UPSERT INTO`` carries two because CockroachDB's ``UPSERT`` may write either way
#: and a census that named only one of them would understate the demand.
VERBS_BY_KEYWORD: Mapping[str, tuple[str, ...]] = {
    "FROM": ("SELECT",),
    "JOIN": ("SELECT",),
    "INSERT INTO": ("INSERT",),
    "UPSERT INTO": ("INSERT", "UPDATE"),
    "INTO": ("INSERT",),
    "UPDATE": ("UPDATE",),
    "DELETE FROM": ("DELETE",),
    "CALL": ("EXECUTE",),
    "EXECUTE": ("EXECUTE",),
}

# Longest forms first: leftmost-first alternation is what stops `DELETE FROM x` being
# read as a SELECT on x, which would turn the one privilege no role in this system holds
# (MI01) into the one every role holds.
_REFERENCE = re.compile(
    r"\b(?P<keyword>INSERT\s+INTO|UPSERT\s+INTO|DELETE\s+FROM|FROM|JOIN|INTO|UPDATE|CALL|EXECUTE)"
    r"\s+(?P<schema>[a-z_][a-z0-9_]*)\.(?P<relation>[a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)

# A ROUTINE INVOKED INSIDE A SELECT LIST, which no statement keyword precedes.
# `refusal.py:141` issues `SELECT trappoint.explain_refusal(%s, %s, %s, %s)`, and that is
# an EXECUTE demand as surely as `CALL mainline.merge_permit(…)` is. The rule is kept
# narrow — the name must follow `SELECT` and must be followed by `(` — because the general
# shape `<qualified>(` also matches an INSERT's column list: `INSERT INTO
# mainline.disposition (disposition_id, …)` would be read as a routine call by anything
# looser. Measured over the shipping tree, this pattern matches exactly one site.
_ROUTINE_CALL = re.compile(
    r"\bSELECT\s+(?P<schema>[a-z_][a-z0-9_]*)\.(?P<relation>[a-z_][a-z0-9_]*)\s*\(",
    re.IGNORECASE,
)

# One line's interpolations, for the raw leg. Purely lexical — it does not know what an
# f-string is, only that `{…}` on one line stands for something the source computes — so
# the second extraction path stays independent of the first.
_RAW_HOLE = re.compile(r"\{[^{}\n]*\}")

# `CREATE [OR REPLACE] [MATERIALIZED] VIEW|TABLE [IF NOT EXISTS] <schema>.<relation>`.
# The authority for what a schema contains, read off the migrations that create it.
_DECLARATION = re.compile(
    r"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?(?:VIEW|TABLE)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?(?P<schema>[a-z_][a-z0-9_]*)\.(?P<relation>[a-z_][a-z0-9_]*)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Demand:
    """One statement's claim on one relation: the name, the verb, and where it is issued."""

    schema: str
    relation: str
    verb: str
    keyword: str
    path: str
    lineno: int
    origin: str
    """``literal`` (written out), ``interpolated`` (a hole), ``resolved`` (a hole, named)."""

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.relation}"

    @property
    def where(self) -> str:
        return f"{self.path}:{self.lineno}"

    @property
    def pair(self) -> tuple[str, str]:
        """Return the unit of comparison: the fully-qualified name and the verb."""
        return (self.qualified, self.verb)

    def __str__(self) -> str:
        return f"{self.qualified} {self.verb} ({self.keyword} at {self.where})"


@dataclass(frozen=True, slots=True)
class FileScan:
    """Everything one ``.py`` told both extraction legs. Immutable, so it can be diffed."""

    path: str
    ast_demands: tuple[Demand, ...] = ()
    raw_demands: tuple[Demand, ...] = ()
    catalog_references: tuple[Demand, ...] = ()
    unruled: tuple[Demand, ...] = ()
    exempted_unruled: tuple[Demand, ...] = ()
    syntax_error: str | None = None


@dataclass(frozen=True, slots=True)
class RefScan:
    """The whole census of what the demo-api source demands."""

    files: tuple[FileScan, ...] = ()
    resolved: tuple[Demand, ...] = ()
    unresolvable: tuple[Demand, ...] = ()
    declared_by_schema: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    # -- the two legs ----------------------------------------------------

    @property
    def ast_demands(self) -> tuple[Demand, ...]:
        return tuple(d for f in self.files for d in f.ast_demands)

    @property
    def raw_demands(self) -> tuple[Demand, ...]:
        return tuple(d for f in self.files for d in f.raw_demands)

    def ast_pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset(d.pair for d in self.ast_demands)

    def raw_pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset(d.pair for d in self.raw_demands)

    def disagreement(self) -> tuple[frozenset[tuple[str, str]], frozenset[tuple[str, str]]]:
        """Return (AST-only, raw-only). Both empty is the only acceptable answer."""
        left, right = self.ast_pairs(), self.raw_pairs()
        return (left - right, right - left)

    # -- the census ------------------------------------------------------

    @property
    def demands(self) -> tuple[Demand, ...]:
        """Every demand the census asserts against the grant matrix, dynamics resolved."""
        literal = [d for d in self.ast_demands if d.relation != DYNAMIC_RELATION]
        return tuple(
            sorted([*literal, *self.resolved], key=lambda d: (d.qualified, d.verb, d.where))
        )

    def pairs(self) -> frozenset[tuple[str, str]]:
        return frozenset(d.pair for d in self.demands)

    def relations(self) -> frozenset[str]:
        return frozenset(d.qualified for d in self.demands)

    def literal_relations(self) -> frozenset[str]:
        return frozenset(d.qualified for d in self.ast_demands if d.relation != DYNAMIC_RELATION)

    def resolved_relations(self) -> frozenset[str]:
        return frozenset(d.qualified for d in self.resolved)

    def verbs_for(self, qualified: str) -> frozenset[str]:
        return frozenset(d.verb for d in self.demands if d.qualified == qualified)

    def routines(self) -> frozenset[str]:
        """Every routine the source invokes — an ``EXECUTE`` demand, not a table privilege."""
        return frozenset(d.qualified for d in self.demands if d.verb == "EXECUTE")

    def sites_for(self, qualified: str, verb: str | None = None) -> tuple[str, ...]:
        """Return every ``file:line`` that demands *qualified*, from BOTH legs.

        Both legs, because the AST leg knows a multi-line SQL constant by the line its
        opening quote is on and the raw leg knows the line the name is actually written
        on. An operator reading a failure wants the second; an operator reading a
        disagreement wants both.
        """
        seen = {
            d.where
            for d in (*self.ast_demands, *self.raw_demands, *self.resolved)
            if d.qualified == qualified and (verb is None or d.verb == verb)
        }
        return tuple(sorted(seen))

    @property
    def parse_failures(self) -> tuple[FileScan, ...]:
        return tuple(f for f in self.files if f.syntax_error is not None)


# ---------------------------------------------------------------------------
# extraction leg 1: the AST
# ---------------------------------------------------------------------------


class _LiteralCollector(ast.NodeVisitor):
    """Collect every string the module builds out of literals, with its start line.

    A ``textwrap.dedent(...)`` body needs no special case: its argument is an ordinary
    ``ast.Constant``, triple-quoted or not, and the parser has already folded
    implicitly-concatenated pieces into one. F-strings DO need one, because their literal
    parts arrive as separate ``Constant``
    nodes and a name split across a hole would otherwise be invisible to this leg while
    remaining visible to the other — which is a disagreement, and correctly red, but a
    confusing one. Rendering the hole as :data:`DYNAMIC_RELATION` states the truth
    instead: something is interpolated there.
    """

    def __init__(self) -> None:
        self.literals: list[tuple[str, int]] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.literals.append((node.value, node.lineno))
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append(DYNAMIC_RELATION)
                if isinstance(value, ast.FormattedValue):
                    # The expression inside the hole is still code and may itself hold
                    # SQL literals; only the f-string's own Constant parts are skipped.
                    self.visit(value.value)
        self.literals.append(("".join(parts), node.lineno))


def _demand(
    match: re.Match[str], keyword: str, verb: str, path: str, lineno: int, origin: str
) -> Demand:
    relation = match.group("relation").lower()
    return Demand(
        schema=match.group("schema").lower(),
        relation=relation,
        verb=verb,
        keyword=keyword,
        path=path,
        lineno=lineno,
        origin="interpolated" if relation == DYNAMIC_RELATION else origin,
    )


def _matches(text: str, path: str, lineno: int, origin: str) -> Iterator[Demand]:
    for match in _REFERENCE.finditer(text):
        keyword = re.sub(r"\s+", " ", match.group("keyword")).upper()
        for verb in VERBS_BY_KEYWORD[keyword]:
            yield _demand(match, keyword, verb, path, lineno, origin)
    for match in _ROUTINE_CALL.finditer(text):
        yield _demand(match, "SELECT <routine>(", "EXECUTE", path, lineno, origin)


def _pragma_on(lines: Sequence[str], lineno: int) -> bool:
    index = lineno - 1
    return 0 <= index < len(lines) and PRAGMA_NOT_SQL in lines[index]


def scan_source(path: str, source: str) -> FileScan:
    """Run both extraction legs over one file's text. A parse failure is returned, never raised."""
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return FileScan(path=path, syntax_error=f"{type(exc).__name__}: {exc}")

    collector = _LiteralCollector()
    collector.visit(tree)

    ast_demands: list[Demand] = []
    catalog: list[Demand] = []
    unruled: list[Demand] = []
    exempted: list[Demand] = []
    for text, lineno in collector.literals:
        for demand in _matches(text, path, lineno, "literal"):
            if demand.schema in PRIVILEGED_SCHEMAS:
                ast_demands.append(demand)
            elif demand.schema in NOT_PRIVILEGE_DEMANDS:
                catalog.append(demand)
            elif _pragma_on(lines, lineno):
                exempted.append(demand)
            else:
                unruled.append(demand)

    # Leg 2. Line by line over the bytes, knowing nothing about Python. It is filtered to
    # the ruled schemas because `from collections.abc import Iterator` is `FROM
    # collections.abc` to a sweep that does not parse — the schemas this census rules on
    # are the set the two legs are required to agree about.
    raw_demands = [
        demand
        for number, line in enumerate(lines, 1)
        for demand in _matches(_RAW_HOLE.sub(DYNAMIC_RELATION, line), path, number, "literal")
        if demand.schema in PRIVILEGED_SCHEMAS
    ]

    return FileScan(
        path=path,
        ast_demands=tuple(ast_demands),
        raw_demands=tuple(raw_demands),
        catalog_references=tuple(catalog),
        unruled=tuple(unruled),
        exempted_unruled=tuple(exempted),
    )


def scan_file(path: Path, repo_root: Path) -> FileScan:
    where = rel(path, repo_root)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return FileScan(path=where, syntax_error=f"unreadable: {exc}")
    return scan_source(where, source)


# ---------------------------------------------------------------------------
# resolving the dynamic references
# ---------------------------------------------------------------------------


def declared_relations(
    repo_root: Path, *, roots: Sequence[str] = MIGRATION_ROOTS
) -> dict[str, tuple[str, ...]]:
    """Return schema → the relations the migration set CREATEs in it.

    The migrations are the authority for what exists. Reading the answer out of
    ``cloud_roles.AUDIT_VIEWS`` or ``GRANTS.yaml`` instead would resolve one side of this
    census using the other side, which is the drift that made the census necessary.
    """
    found: dict[str, set[str]] = {}
    for paths in expand_roots(repo_root, roots).values():
        for root in paths:
            for sql in iter_files(root, (".sql",)):
                try:
                    text = sql.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):  # pragma: no cover - unreadable DDL
                    continue
                for match in _DECLARATION.finditer(text):
                    schema = match.group("schema").lower()
                    found.setdefault(schema, set()).add(match.group("relation").lower())
    return {schema: tuple(sorted(names)) for schema, names in sorted(found.items())}


def _resolve(
    dynamic: Iterable[Demand], declared: Mapping[str, tuple[str, ...]]
) -> tuple[tuple[Demand, ...], tuple[Demand, ...]]:
    resolved: list[Demand] = []
    unresolvable: list[Demand] = []
    for demand in dynamic:
        names = declared.get(demand.schema, ())
        if not names:
            unresolvable.append(demand)
            continue
        resolved.extend(
            Demand(
                schema=demand.schema,
                relation=name,
                verb=demand.verb,
                keyword=demand.keyword,
                path=demand.path,
                lineno=demand.lineno,
                origin="resolved",
            )
            for name in names
        )
    return tuple(resolved), tuple(unresolvable)


# ---------------------------------------------------------------------------
# the scan, and the enforcement over it
# ---------------------------------------------------------------------------


def scan_demo_api(
    repo_root: Path,
    *,
    roots: Sequence[str] = DEMO_API_ROOTS,
    migration_roots: Sequence[str] = MIGRATION_ROOTS,
) -> RefScan:
    """Scan every ``.py`` under *roots* and resolve what the dynamic references reach."""
    files: list[FileScan] = []
    for paths in expand_roots(repo_root, roots).values():
        for root in paths:
            files.extend(scan_file(py, repo_root) for py in iter_python_files(root))

    declared = declared_relations(repo_root, roots=migration_roots)
    dynamic = [d for f in files for d in f.ast_demands if d.relation == DYNAMIC_RELATION]
    resolved, unresolvable = _resolve(dynamic, declared)
    return RefScan(
        files=tuple(files),
        resolved=resolved,
        unresolvable=unresolvable,
        declared_by_schema=declared,
    )


def check_sql_reference_census(
    repo_root: Path,
    *,
    roots: Sequence[str] = DEMO_API_ROOTS,
    migration_roots: Sequence[str] = MIGRATION_ROOTS,
    minimum_literal: int = MINIMUM_LITERAL_RELATIONS,
    minimum_resolved: int = MINIMUM_RESOLVED_RELATIONS,
    minimum_routines: int = MINIMUM_ROUTINE_DEMANDS,
) -> tuple[RefScan, Report]:
    """Scan, then assert the scan is worth believing. Returns the scan and its report.

    The report is about the SCANNER, not about the grants: it goes red when a file cannot
    be parsed, when the two extraction legs disagree, when a dynamic reference cannot be
    resolved, when a string names a schema this census has no ruling for, or when the
    count falls below the floor. Only a scan whose report is clean is worth diffing
    against ``GRANTS.yaml``, which is why the census test asserts this first.
    """
    report = Report(enforcement=ENFORCEMENT)
    matched = expand_roots(repo_root, roots)
    for pattern, paths in matched.items():
        if not paths:
            report.skip(
                rule=RULE_ROOT_ABSENT,
                subject=pattern,
                reason=(
                    "no path matches this demo-api source root, so nothing was scanned. "
                    "This is NOT a pass: the census becomes enforcing with zero edits the "
                    "moment the path exists."
                ),
            )
    scan = scan_demo_api(repo_root, roots=roots, migration_roots=migration_roots)

    for file_scan in scan.files:
        report.examine()
        _record_file(report, file_scan)

    _record_disagreement(report, scan)
    _record_dynamics(report, scan)
    _record_floors(report, scan, minimum_literal, minimum_resolved, minimum_routines)
    return scan, report


def _record_file(report: Report, file_scan: FileScan) -> None:
    if file_scan.syntax_error is not None:
        rule = RULE_UNREADABLE if "unreadable" in file_scan.syntax_error else RULE_UNPARSEABLE
        report.violate(
            rule=rule,
            subject=file_scan.path,
            detail=(
                f"demo-api source could not be read as Python ({file_scan.syntax_error}); "
                "its SQL was therefore never enumerated, and a file that was not "
                "enumerated has not been cleared"
            ),
            authority=AUTHORITY,
        )
        return
    for demand in file_scan.unruled:
        report.violate(
            rule=RULE_UNRULED_SCHEMA,
            subject=demand.where,
            detail=(
                f"a string constant names {demand.qualified!r} after {demand.keyword}, and "
                f"schema {demand.schema!r} is neither one this census grants "
                f"({', '.join(PRIVILEGED_SCHEMAS)}) nor one it excludes by name "
                f"({', '.join(sorted(NOT_PRIVILEGE_DEMANDS))}). Rule on it, or mark the "
                f"line `# {PRAGMA_NOT_SQL} <reason>` if the text is prose"
            ),
            authority=AUTHORITY,
        )
    for demand in file_scan.catalog_references:
        report.exempt(
            rule=RULE_UNRULED_SCHEMA,
            subject=demand.where,
            reason=(
                f"{demand.qualified} is a catalog read, not a privilege demand: "
                f"{demand.schema} is readable by every login that can connect and is "
                "named by no grant in this repository"
            ),
        )
    for demand in file_scan.exempted_unruled:
        report.exempt(
            rule=RULE_UNRULED_SCHEMA,
            subject=demand.where,
            reason=f"{demand.qualified}: explicit `{PRAGMA_NOT_SQL}` pragma on the line",
        )


def _record_disagreement(report: Report, scan: RefScan) -> None:
    ast_only, raw_only = scan.disagreement()
    for label, difference in (("AST leg only", ast_only), ("raw-byte leg only", raw_only)):
        for qualified, verb in sorted(difference):
            report.violate(
                rule=RULE_PATHS_DISAGREE,
                subject=f"{qualified} {verb}",
                detail=(
                    f"found by the {label}. The two extraction legs exist so that one of "
                    "them silently ceasing to match is a red rather than a shorter list; "
                    "reconcile them, do not take the union. Sites: "
                    + ", ".join(scan.sites_for(qualified, verb))
                ),
                authority=AUTHORITY,
            )


def _record_dynamics(report: Report, scan: RefScan) -> None:
    for demand in scan.unresolvable:
        report.violate(
            rule=RULE_UNRESOLVED_DYNAMIC,
            subject=demand.where,
            detail=(
                f"a relation name in schema {demand.schema!r} is interpolated at runtime "
                f"({demand.keyword} {demand.schema}.<computed>) and no migration under "
                f"{', '.join(MIGRATION_ROOTS)} declares any relation in that schema, so "
                "the census cannot say what is reached. A demand it cannot measure has "
                "not been measured"
            ),
            authority=AUTHORITY,
        )
    for demand in sorted({d.where: d for d in scan.resolved}.values(), key=lambda d: d.where):
        report.exempt(
            rule=RULE_UNRESOLVED_DYNAMIC,
            subject=demand.where,
            reason=(
                f"{demand.schema}.<computed> resolved to "
                f"{len(scan.declared_by_schema.get(demand.schema, ()))} relation(s) "
                f"declared by the migration set"
            ),
        )


def _record_floors(
    report: Report,
    scan: RefScan,
    minimum_literal: int,
    minimum_resolved: int,
    minimum_routines: int,
) -> None:
    routines = scan.routines()
    if len(routines) < minimum_routines:
        report.violate(
            rule=RULE_ROUTINE_FLOOR,
            subject=f"{len(routines)} < {minimum_routines}",
            detail=(
                f"{len(routines)} routine invocation(s) were found; {minimum_routines} were "
                "measurable on 2026-08-15 — mainline.merge_permit (CALL, gate_run.py:169) "
                "and trappoint.explain_refusal (inside a SELECT, refusal.py:141). The "
                "second is reached by a pattern no statement keyword precedes, so it is the "
                "one this floor exists to protect. Found: " + ", ".join(sorted(routines))
            ),
            authority=AUTHORITY,
        )
    literal = scan.literal_relations()
    if len(literal) < minimum_literal:
        report.violate(
            rule=RULE_LITERAL_FLOOR,
            subject=f"{len(literal)} < {minimum_literal}",
            detail=(
                f"the scan found {len(literal)} schema-qualified relation(s) written out "
                f"in demo-api SQL; {minimum_literal} were measurable on 2026-08-15. A "
                "scanner that stops matching reports a short list, and a short list makes "
                "every missing grant invisible. This is a FLOOR: raise it when the count "
                "rises, never lower it to obtain a green. Found: " + ", ".join(sorted(literal))
            ),
            authority=AUTHORITY,
        )
    resolved = scan.resolved_relations()
    if len(resolved) < minimum_resolved:
        report.violate(
            rule=RULE_RESOLVED_FLOOR,
            subject=f"{len(resolved)} < {minimum_resolved}",
            detail=(
                f"{len(resolved)} relation(s) were resolved behind the demo-api's dynamic "
                f"references; {minimum_resolved} mainline_audit views were resolvable on "
                "2026-08-15. Fewer means the resolution stopped working, which would make "
                "every audit view look like an over-grant. Found: " + ", ".join(sorted(resolved))
            ),
            authority=AUTHORITY,
        )
