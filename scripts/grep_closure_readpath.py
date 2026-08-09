#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""DM-9, enforced over the tree: ``mainline.clause_blame_current`` is the ONLY read path.

``mainline.clause_blame_closure`` is append-only and generation-versioned (migration ``0038``,
adversarial finding S2). Recomputing a closure writes a NEW ``(clause_uuid, as_of_commit,
closure_gen)`` row and overwrites nothing, which is what keeps last year's closure — the one that
armed last year's refusal — readable this year. The price of that property is that every reader
now owes the discipline ``max(closure_gen)``.

A discipline owed by every call site is a discipline one of them will forget, and **the forgetting
is silent**. No error, no warning, no wrong-looking result: the query returns a real row from a
real generation, just not the current one. An older generation is by construction the generation
computed with LESS ancestry, so its ``max_severity`` is lower or equal — which means the failure is
always in the direction of *understating ancestral severity*, the one error direction in this
product with physical consequences.

``docs/leads/datamodel.md`` DM-9 therefore rules that the discipline is structural: one view carries
it, and no migration, committed query, view or service reads the closure table directly. This
script is that rule's enforcement, because DM-9 is a rule about a NAME and a name cannot be
constrained inside the cluster.

WHY THIS IS NOT ``grep -r clause_blame_closure``
------------------------------------------------
Because a bare substring scan is a check that reports false positives, and a check that reports
false positives is a check somebody eventually relaxes the wrong way. Three of the tree's most
correct files would fail one:

* ``mainline-cherrypick`` holds ``"clause_blame_closure"`` in a ``FORBIDDEN_TARGETS`` frozenset —
  a DENY-LIST naming the table, which is the exact opposite of a read path;
* ``mainline-fixity`` holds it in ``GATE_TABLES`` for the same reason;
* half the repository names it in prose, in a docstring, explaining why not to read it.

So every occurrence is CLASSIFIED by the SQL context immediately before it, after comments and
docstrings have been removed, and only four classes are reported at all:

===========  ===================================================================================
 class        the text immediately before the identifier
===========  ===================================================================================
 ``DEFINE``   ``CREATE TABLE [IF NOT EXISTS] <qual>.``
 ``WRITE``    ``INSERT INTO`` / ``UPSERT INTO`` / ``UPDATE`` / ``DELETE FROM`` ``<qual>.``
 ``READ``     ``FROM`` / ``JOIN`` ``<qual>.``
 ``WELD``     ``ON`` / ``TABLE`` ``<qual>.`` — ``CREATE TRIGGER … ON``, ``ALTER TABLE …``
===========  ===================================================================================

Anything else is a MENTION and is ignored. Each class has its own allowlist below, each entry
carries the reason it is there, and an occurrence in a class whose allowlist does not name the file
fails the run.

WHAT THE ALLOWLISTS ARE FOR, AND WHAT THEY ARE NOT FOR
------------------------------------------------------
They are not exemptions. Each one names a file that must touch the raw relation *in order for the
view to work at all*: the file that creates the table, the file that creates the view over it, the
guard that must see raw generations to prove they are dense, the two triggers welded onto it, and
the one committed statement that writes it. Adding an entry is a deliberate edit to this file with
a reason on the same line — which is the point. A DM-9 amendment should cost a review, not a quiet
rewrite of somebody's query.

RUNNING IT
----------
    python scripts/grep_closure_readpath.py            # report, exit 0 or 1
    python scripts/grep_closure_readpath.py --json     # machine-readable, same exit code
    python scripts/grep_closure_readpath.py --selftest # prove the classifier before trusting it

``--selftest`` runs the classifier over synthetic snippets covering every class and every known
false-positive shape. It runs first in CI, because a scanner that has never been shown to
distinguish ``FROM mainline.clause_blame_closure`` from ``BEFORE UPDATE OR DELETE ON
mainline.clause_blame_closure`` is a scanner whose green result means nothing.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The relation DM-9 protects.
RELATION = "clause_blame_closure"

#: The relation every reader is supposed to use instead.
VIEW = "clause_blame_current"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SCOPE — what is scanned, and what is deliberately not
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: (glob root, suffixes). DM-9 names "any migration, query or view"; the Python and TypeScript
#: roots extend it to the services, because a Lambda that reads the raw table is the same defect
#: wearing a different file extension.
SCAN_ROOTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("verticals/mainline/db", (".sql", ".j2")),
    ("packages/trappoint-sql", (".sql", ".j2")),
    ("verticals/mainline/packages", (".py",)),
    ("verticals/mainline/apps", (".ts", ".tsx")),
    ("packages", (".py",)),
    ("scripts", (".py",)),
    ("services", (".py",)),
    ("infra", (".py",)),
)

#: Path fragments that end the scan for a file, each with the reason it is excluded. These are
#: printed by ``--json`` so that "what was not looked at" is part of the result rather than a
#: property of the reader's memory.
EXCLUSIONS: dict[str, str] = {
    "scripts/grep_closure_readpath.py": (
        "this file. `SELFTEST_CASES` below holds one synthetic snippet per class — including "
        "`UPDATE {s}.clause_blame_closure SET max_severity = 0` — because a classifier that has "
        "never been shown to separate a weld from a write is a classifier whose green result "
        "means nothing. Those strings are the rule's own test fixtures, not SQL anyone can run."
    ),
    "packages/trappoint-conformance": (
        "the illegal-history corpus. Its entire job is to name the raw relation and attempt the "
        "write the database must refuse (CF-08 is literally `UPDATE clause_blame_closure SET "
        "max_severity = 0`), so scanning it would fail on the file that proves DM-9's sibling "
        "invariant."
    ),
    "/tests/": (
        "a test that proves the closure is append-only, or that a superseded generation is not "
        "returned, MUST name the raw relation — that is the assertion. Tests are outside DM-9 by "
        "construction; DM-9 governs what SHIPS."
    ),
    "/__pycache__/": "build detritus",
    "/node_modules/": "vendored dependencies",
    "/.git/": "version control internals",
    "/.venv/": "virtual environment",
}

#: File-name shapes excluded for the same reason as ``/tests/``.
TEST_FILENAME = re.compile(r"(^test_|_test\.py$|\.test\.tsx?$|\.spec\.tsx?$|^conftest\.py$)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE ALLOWLISTS — four classes, one reason per entry
# ══════════════════════════════════════════════════════════════════════════════════════════════

DEFINE_ALLOWLIST: dict[str, str] = {
    "verticals/mainline/db/migrations/0038_clause_blame_closure.sql": (
        "creates the table. DM-9 names this file explicitly."
    ),
    "packages/trappoint-sql/refvertical/sql/0038_clause_blame_closure.sql": (
        "the reference vertical's isomorphic twin. `trappoint-conform --profile trappoint-ref` "
        "runs the kernel's projection triggers against it, so it must declare the same relation "
        "under its own schema."
    ),
}

READ_ALLOWLIST: dict[str, str] = {
    "verticals/mainline/db/migrations/0039_clause_blame_current.sql": (
        "creates the view. It is the one file whose job is to read the table so that nothing else "
        "has to. DM-9 names it explicitly."
    ),
    "packages/trappoint-sql/refvertical/sql/0039_clause_blame_current.sql": (
        "the reference vertical's twin of the view, statement for statement."
    ),
    "verticals/mainline/db/migrations/0108_fn_closure_guard.sql": (
        "fn_closure_guard MUST see RAW generations. Its job (MI26) is to prove that generations "
        "are dense — `closure_gen = prev + 1` — and the view shows exactly one generation per "
        "clause version, which is the information the guard needs to not have. Reading the view "
        "here would make the guard structurally unable to detect the gap it exists to detect."
    ),
    "packages/trappoint-sql/refvertical/sql/0108_fn_closure_guard.sql": (
        "the rendered guard for the reference binding; same argument."
    ),
    "packages/trappoint-sql/templates/0107_fn_closure_guard.sql.j2": (
        "the TEMPLATE that renders both of the above. A change to a rendered file is a change to "
        "its template (MR-1), so the template must carry the same permission as its output."
    ),
}

WRITE_ALLOWLIST: dict[str, str] = {
    "verticals/mainline/db/queries/closure_write.sql": (
        "the projector's one statement. DM-9 names it explicitly. It is INSERT-only; there is no "
        "UPDATE and no DELETE against this relation anywhere in the tree, and no role holds either "
        "privilege on it (GRANTS.yaml)."
    ),
    "packages/trappoint-model/src/trappoint_model/refschema.py": (
        "the reference model's schema stand-in seeds a closure row so the differential state "
        "machine has an authority source to project from. It is an oracle, not a service, and it "
        "writes rather than reads."
    ),
}

WELD_ALLOWLIST: dict[str, str] = {
    "verticals/mainline/db/migrations/0127_trg_closure_guard.sql": (
        "CREATE TRIGGER closure_guard BEFORE INSERT ON the relation. A trigger cannot be welded "
        "onto a view."
    ),
    "verticals/mainline/db/migrations/0128j_trg_refuse_mutation_clause_blame_closure.sql": (
        "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON the relation — the weld that makes "
        "the append-only half of MI26 true for every writer including a DBA."
    ),
    "packages/trappoint-sql/refvertical/sql/0127_trg_closure_guard.sql": (
        "the rendered weld for the reference binding."
    ),
    "packages/trappoint-sql/refvertical/sql/0128j_trg_refuse_mutation_clause_blame_closure.sql": (
        "the rendered append-only weld for the reference binding."
    ),
    "packages/trappoint-sql/templates/0120_triggers_projection.sql.j2": (
        "the template that renders both welds into both bindings (MR-1)."
    ),
}

ALLOWLISTS: dict[str, dict[str, str]] = {
    "DEFINE": DEFINE_ALLOWLIST,
    "READ": READ_ALLOWLIST,
    "WRITE": WRITE_ALLOWLIST,
    "WELD": WELD_ALLOWLIST,
}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE CLASSIFIER
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: A schema qualifier chain: `mainline.`, `trappoint_ref.`, `{s}.`, `{{ binding.schema }}.`,
#: `defaultdb.trappoint_ref.`, `"mainline".`. Zero or more parts, each followed by a dot.
#: Crucially it does NOT match arbitrary words, which is what keeps `BEFORE UPDATE OR DELETE ON
#: mainline.` from being read as an UPDATE of the relation.
_QUAL = r"(?:(?:\{\{[^{}]*\}\}|\{[A-Za-z_]\w*\}|\"[A-Za-z_]\w*\"|[A-Za-z_]\w*)\s*\.\s*)*"

#: Order matters and is not alphabetical: `DELETE FROM x.` contains `FROM`, and `CREATE TABLE x.`
#: contains `TABLE`, so the more specific class is tried first in both pairs.
_CLASSIFIERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DEFINE", re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?" + _QUAL + r"$", re.I)),
    (
        "WRITE",
        re.compile(
            r"\b(?:INSERT\s+INTO|UPSERT\s+INTO|DELETE\s+FROM|UPDATE)\s+" + _QUAL + r"$",
            re.I,
        ),
    ),
    ("READ", re.compile(r"\b(?:FROM|JOIN)\s+" + _QUAL + r"$", re.I)),
    ("WELD", re.compile(r"\b(?:ON|TABLE)\s+" + _QUAL + r"$", re.I)),
)

#: How much text before the identifier the classifier looks at. Long enough for
#: `CREATE TABLE IF NOT EXISTS {{ binding.schema }}.`, short enough that an unrelated `FROM`
#: three clauses earlier cannot reach.
_LOOKBACK = 96


def classify(text: str, at: int) -> str | None:
    """Classify the occurrence of :data:`RELATION` that starts at ``at``.

    Returns one of ``DEFINE`` / ``WRITE`` / ``READ`` / ``WELD``, or ``None`` for a mere mention —
    a string in a deny-list, a name in prose, a key in a dict literal.
    """
    prefix = " ".join(text[max(0, at - _LOOKBACK) : at].split())
    for name, pattern in _CLASSIFIERS:
        if pattern.search(prefix):
            return name
    return None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# COMMENT AND DOCSTRING REMOVAL
#
# Half this repository names the relation in prose in order to explain why not to read it, so a
# scanner that cannot tell code from commentary reports the schema's own documentation as a
# violation. Every stripper below REPLACES WITH SPACES rather than deleting, so byte offsets — and
# therefore reported line numbers — survive exactly.
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _blank(chars: list[str], start: int, end: int) -> None:
    for i in range(start, min(end, len(chars))):
        if chars[i] != "\n":
            chars[i] = " "


def strip_sql(text: str) -> str:
    """Blank ``--`` and ``/* */`` comments, preserving string and identifier literals.

    The band's migrations are mostly prose, and the prose is full of apostrophes ("the operator's
    permit"). A scanner that looks for quotes before comment markers reads ``operator's`` as the
    start of a literal and swallows the rest of the file.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "'":
            i += 1
            while i < n:
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if ch == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 1
            i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            start = i
            while i < n and text[i] != "\n":
                i += 1
            _blank(out, start, i)
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            start = i
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(i + 2, n)
            _blank(out, start, i)
            continue
        i += 1
    return "".join(out)


def strip_c_style(text: str) -> str:
    """Blank ``//`` and ``/* */`` in TypeScript, preserving `'`, `"` and template literals."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "'\"`":
            quote = ch
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            start = i
            while i < n and text[i] != "\n":
                i += 1
            _blank(out, start, i)
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            start = i
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(i + 2, n)
            _blank(out, start, i)
            continue
        i += 1
    return "".join(out)


def _offsets(text: str) -> list[int]:
    """Byte offset at which each 1-based line begins (index 0 unused)."""
    starts = [0, 0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def strip_python(text: str) -> str:
    """Blank ``#`` comments and DOCSTRINGS ONLY — never an ordinary string.

    The distinction is the whole value of using ``tokenize`` and ``ast`` instead of a regex: a SQL
    statement held in a module-level triple-quoted constant is CODE and must be scanned, while the
    triple-quoted string directly under a ``def`` is prose and must not be. Blanking every
    triple-quoted string would hide a raw-table read inside a query constant, which is precisely
    the defect this script exists to find.

    A file that does not parse is returned unchanged — the conservative direction, because an
    unparsed file produces more candidate matches, never fewer.
    """
    out = list(text)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                starts = _offsets(text)
                _blank(
                    out,
                    starts[tok.start[0]] + tok.start[1],
                    starts[tok.end[0]] + tok.end[1],
                )
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "".join(out)

    starts = _offsets(text)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        if value.end_lineno is None or value.end_col_offset is None:
            continue
        _blank(
            out,
            starts[value.lineno] + value.col_offset,
            starts[value.end_lineno] + value.end_col_offset,
        )
    return "".join(out)


def strip_for(path: Path, text: str) -> str:
    suffix = path.suffix.lower()
    if suffix in {".sql", ".j2"}:
        return strip_sql(text)
    if suffix == ".py":
        return strip_python(text)
    if suffix in {".ts", ".tsx"}:
        return strip_c_style(text)
    return text


# ══════════════════════════════════════════════════════════════════════════════════════════════
# THE SCAN
# ══════════════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Occurrence:
    path: str
    line: int
    kind: str
    excerpt: str
    allowed: bool
    reason: str


def _posix(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def excluded_because(relative: str) -> str | None:
    guarded = f"/{relative}/"
    for fragment, reason in EXCLUSIONS.items():
        if fragment in guarded:
            return reason
    if TEST_FILENAME.search(Path(relative).name):
        return EXCLUSIONS["/tests/"]
    return None


def candidate_files(root: Path = REPO_ROOT) -> Iterator[Path]:
    seen: set[Path] = set()
    for sub, suffixes in SCAN_ROOTS:
        base = root / sub
        if not base.is_dir():
            continue
        for suffix in suffixes:
            for path in base.rglob(f"*{suffix}"):
                if not path.is_file() or path in seen:
                    continue
                if excluded_because(_posix(path)) is not None:
                    continue
                seen.add(path)
                yield path


def scan_text(relative: str, text: str, *, suffix: str) -> list[Occurrence]:
    stripped = strip_for(Path(relative), text) if suffix else text
    found: list[Occurrence] = []
    starts = _offsets(text)
    for match in re.finditer(re.escape(RELATION), stripped):
        kind = classify(stripped, match.start())
        if kind is None:
            continue
        line = max(1, sum(1 for s in starts[1:] if s <= match.start()))
        allowlist = ALLOWLISTS[kind]
        reason = allowlist.get(relative, "")
        line_text = text.splitlines()[line - 1] if line - 1 < len(text.splitlines()) else ""
        found.append(
            Occurrence(
                path=relative,
                line=line,
                kind=kind,
                excerpt=" ".join(line_text.split())[:160],
                allowed=relative in allowlist,
                reason=reason,
            )
        )
    return found


def scan(root: Path = REPO_ROOT) -> list[Occurrence]:
    occurrences: list[Occurrence] = []
    for path in sorted(candidate_files(root)):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if RELATION not in text:
            continue
        occurrences.extend(scan_text(_posix(path), text, suffix=path.suffix))
    return occurrences


# ══════════════════════════════════════════════════════════════════════════════════════════════
# SELF-TEST — the classifier is proved before it is trusted
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: (snippet, expected class or None). Every shape that exists in the tree today, plus every
#: false-positive shape that was actually observed while this script was written.
SELFTEST_CASES: tuple[tuple[str, str | None], ...] = (
    ("CREATE TABLE mainline.clause_blame_closure (", "DEFINE"),
    ("CREATE TABLE IF NOT EXISTS {{ binding.schema }}.clause_blame_closure (", "DEFINE"),
    ("  FROM mainline.clause_blame_closure c", "READ"),
    ("SELECT * FROM defaultdb.trappoint_ref.clause_blame_closure AS c", "READ"),
    ("JOIN mainline.clause_blame_closure USING (clause_uuid)", "READ"),
    ("INSERT INTO mainline.clause_blame_closure (clause_uuid, as_of_commit)", "WRITE"),
    ('f"INSERT INTO {SCHEMA}.clause_blame_closure (clause_uuid, "', "WRITE"),
    ("UPDATE {s}.clause_blame_closure SET max_severity = 0", "WRITE"),
    ("DELETE FROM mainline.clause_blame_closure WHERE closure_gen = 0", "WRITE"),
    ("CREATE TRIGGER closure_guard BEFORE INSERT ON mainline.clause_blame_closure", "WELD"),
    (
        "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON mainline.clause_blame_closure",
        "WELD",
    ),
    ("ALTER TABLE {s}.clause_blame_closure DISABLE TRIGGER append_only", "WELD"),
    # ── shapes that must NOT be reported ──────────────────────────────────────────────────
    ('    "clause_blame_closure",', None),
    ("FORBIDDEN_TARGETS = frozenset({'clause_blame_closure'})", None),
    ("projections written by the Projector from ``clause_blame_closure``;", None),
    ("-- reads: mainline.clause_blame_current ONLY, never clause_blame_closure", None),
    ("{'suffix': 'j', 'table': 'clause_blame_closure', 'why': 'MI26'}", None),
    ("* `clause_blame_closure` bands `max_severity` into `virulence` exactly once", None),
)


def selftest() -> int:
    failures: list[str] = []
    for snippet, expected in SELFTEST_CASES:
        at = snippet.index(RELATION)
        actual = classify(snippet, at)
        if actual != expected:
            failures.append(f"  {snippet!r}\n    expected {expected!r}, got {actual!r}")

    # The Python stripper must blank a docstring and must NOT blank a SQL constant.
    sample = (
        '"""A docstring that says FROM mainline.clause_blame_closure in prose."""\n'
        "# a comment that says FROM mainline.clause_blame_closure\n"
        'SQL = """SELECT 1 FROM mainline.clause_blame_closure"""\n'
    )
    hits = scan_text("scripts/_selftest_sample.py", sample, suffix=".py")
    if len(hits) != 1 or hits[0].line != 3:
        failures.append(
            "  the Python stripper must blank docstrings and comments but never a SQL constant; "
            f"got {[(h.line, h.kind) for h in hits]}"
        )

    if failures:
        print("classifier self-test FAILED:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"classifier self-test passed ({len(SELFTEST_CASES)} snippets + 1 stripper case)")
    return 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# REPORTING
# ══════════════════════════════════════════════════════════════════════════════════════════════

_FAILURE_EXPLANATION = f"""
DM-9 — `mainline.{VIEW}` is the ONLY read path to `mainline.{RELATION}`.

`{RELATION}` is append-only and generation-versioned: a recomputation writes a NEW
`closure_gen` and overwrites nothing. Every reader therefore owes `max(closure_gen)`, and a
reader that forgets it gets a REAL row from a SUPERSEDED generation — computed with LESS
ancestry, so a LOWER `max_severity` — with no error and no warning. The failure is always in
the direction of understating ancestral severity, which is the one error direction in this
product with physical consequences.

Read `mainline.{VIEW}` instead. If the file genuinely must touch the raw relation, that is a
DM-9 amendment: add an entry to the matching allowlist in this script WITH ITS REASON, and
record it in docs/leads/datamodel.md. It should cost a review.
""".strip()


def report(occurrences: Iterable[Occurrence]) -> int:
    violations = [o for o in occurrences if not o.allowed]
    allowed = [o for o in occurrences if o.allowed]

    print(f"scanned for `{RELATION}` in an executable position (DM-9)")
    print(f"  allowlisted uses : {len(allowed)}")
    print(f"  violations       : {len(violations)}")
    if allowed:
        print("\nallowlisted:")
        for occ in sorted(allowed, key=lambda o: (o.path, o.line)):
            print(f"  {occ.kind:<6} {occ.path}:{occ.line}")
    if not violations:
        print("\nOK — every read of the blame closure goes through the view.")
        return 0

    sys.stdout.flush()
    print("\nVIOLATIONS:", file=sys.stderr)
    for occ in sorted(violations, key=lambda o: (o.path, o.line)):
        print(f"  {occ.kind:<6} {occ.path}:{occ.line}", file=sys.stderr)
        print(f"         {occ.excerpt}", file=sys.stderr)
    print("\n" + _FAILURE_EXPLANATION, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", action="store_true", help="emit the result as JSON")
    parser.add_argument("--selftest", action="store_true", help="prove the classifier, then exit")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root to scan")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    occurrences = scan(args.root)
    if args.json:
        violations = [o for o in occurrences if not o.allowed]
        print(
            json.dumps(
                {
                    "relation": RELATION,
                    "view": VIEW,
                    "rule": "DM-9",
                    "scanned_roots": [{"root": r, "suffixes": list(s)} for r, s in SCAN_ROOTS],
                    "exclusions": EXCLUSIONS,
                    "occurrences": [o.__dict__ for o in occurrences],
                    "violations": len(violations),
                },
                indent=2,
            )
        )
        return 1 if violations else 0
    return report(occurrences)


if __name__ == "__main__":
    raise SystemExit(main())
