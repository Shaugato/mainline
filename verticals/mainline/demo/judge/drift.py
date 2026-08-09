# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Whether the judge pack still agrees with the repository it claims to describe.

The question this module answers is exactly that one, and it answers it by reading files.

``pack.py`` proves the prompts are *legal*. This module proves they are still *true*, by
reading the artefacts the pack is a copy of and refusing to disagree with them:

======================================  ===========================================
Authority                               What is checked against it
======================================  ===========================================
``db/migrations/0156…0164_v_*.sql``     every column a prompt selects exists in the
                                        view, read out of the shipped ``CREATE VIEW``
``db/migrations/0041, 0042``            the vector width, so the bound EXPLAIN can be
                                        measured against the character cap
``demo/VERIFY.md``                      every SQL statement in the judge-facing file
                                        is a question here or a stated exemption
``demo/REFUSAL-STRINGS.yaml``           the index name, the prefix columns and the
                                        substrings the plan must contain
``scripts/demo/claim_hygiene.py``       the pack's own prose, under the same rules as
                                        the rest of the published surface
======================================  ===========================================

**Absence is never a pass.** Every authority above is owned by another worker in the
fleet. When one is missing this module emits a ``warn`` that says the check did not run
and names the file — it never emits silence, and it never emits ``ok``. "Nothing was
checked" and "it passed" are different results and conflating them is exactly the defect
the pack exists to catch in the product.

**This module never writes to another owner's file.** It reads them, and when they
disagree it says which file is the authority and which is the copy. For a statement
carrying ``transcribed_from``, the named file wins and ``QUESTIONS.yaml`` is what changes.

**One measurement recorded here rather than assumed.** On 2026-08-10 both bound ``EXPLAIN``
statements were run against a local CockroachDB CCL **v26.2.5** node. Three facts came out
of it and all three are load-bearing for the pack:

* the index hint written **before** the alias — ``mainline.event_cue_embedding@cue_scoped_idx
  AS c`` — parses;
* the 10 526-character bound statement is accepted, and the plan is ``top-k -> render ->
  lookup join -> vector search`` with a **non-empty** ``prefix spans:`` line naming every
  prefix value;
* binding every non-vector placeholder to a UUID literal — which an earlier version of
  :func:`_literal_for` did, on the theory that the longest literal is the safest to measure
  — produces ``22023 unsupported comparison operator: <string> = <uuid>`` on ``facet``. A
  length model that yields an unexecutable statement hides the failure it exists to catch,
  so the literals are drawn from the declared column type.

None of that settles whether ``explain_query`` renders the same fragment over the Managed
MCP endpoint. That is day-1 check ``GT-07``, it is settled by
``tests/integration/mcp/test_explain_index_truth.py`` against the live endpoint, and until
then the claim is stated at pgwire strength.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

from . import envelope as env
from .pack import Finding, Pack, Question, fail, info, warn

VERIFY_RELPATH: Final = Path("verticals/mainline/demo/VERIFY.md")
REFUSAL_STRINGS_RELPATH: Final = Path("verticals/mainline/demo/REFUSAL-STRINGS.yaml")
CLAIM_HYGIENE_RELPATH: Final = Path("scripts/demo/claim_hygiene.py")

_SQL_FENCE: Final = re.compile(r"```sql\n(.*?)```", re.DOTALL)
_CREATE_VIEW: Final = re.compile(r"CREATE\s+VIEW\s+([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)", re.I)
_VECTOR_COLUMN: Final = re.compile(r"\b([A-Za-z_][\w$]*)\s+VECTOR\s*\(\s*(\d+)\s*\)", re.I)
_DISTANCE_PLACEHOLDER: Final = re.compile(r"<=>\s*(\$\d+)")
_PLACEHOLDER: Final = re.compile(r"\$\d+")
_ORDER_VECTOR_COLUMN: Final = re.compile(
    r"ORDER\s+BY\s+(?:[A-Za-z_][\w$]*\.)?([A-Za-z_][\w$]*)\s*<=>", re.I
)
_EQUALITY_PLACEHOLDER: Final = re.compile(r"(?:[A-Za-z_][\w$]*\.)?([A-Za-z_][\w$]*)\s*=\s*(\$\d+)")
_COLUMN_TYPE: Final = re.compile(
    r"^\s{2,}([a-z_][\w$]*)\s+"
    r"(UUID|STRING|TEXT|INT2|INT4|INT8|INT|BOOL|FLOAT4|FLOAT8|DECIMAL|"
    r"TIMESTAMPTZ|TIMESTAMP|DATE|JSONB|BYTES|VECTOR)\b",
    re.MULTILINE,
)

#: The literal bound to a ``UUID`` placeholder. A fixed value rather than a generated one:
#: the bound statement is measured, printed into ``PACK.md`` and diffed, so a fresh UUID on
#: every render would make the page unstable and the drift check meaningless.
_UUID_LITERAL: Final = "'00000000-0000-4000-8000-000000000001'::UUID"


# ── Reading the shipped view definitions ─────────────────────────────────────────


def _top_level_select_span(code: str) -> tuple[int, int] | None:
    """Character span of the outermost ``SELECT`` list, or ``None`` if there is not one.

    The audit views are ``WITH … SELECT … FROM g CROSS JOIN t ORDER BY … LIMIT 25``, so the
    outer projection is the last ``SELECT`` at parenthesis depth zero and it ends at the
    next ``FROM`` at the same depth. Reading the projection this way rather than by regex
    is what lets the check see ``(t.group_count <= 25) AS rows_complete`` as one item.
    """
    depth = 0
    select_at: int | None = None
    for match in re.finditer(r"[()]|\bSELECT\b|\bFROM\b", code, re.IGNORECASE):
        word = match.group(0)
        if word == "(":
            depth += 1
        elif word == ")":
            depth -= 1
        elif depth == 0 and word.upper() == "SELECT":
            select_at = match.end()
        elif depth == 0 and word.upper() == "FROM" and select_at is not None:
            return select_at, match.start()
    return None


def _split_top_level(text: str) -> list[str]:
    depth = 0
    current: list[str] = []
    items: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append("".join(current))
            current = []
            continue
        current.append(ch)
    items.append("".join(current))
    return items


def view_columns(sql_text: str) -> tuple[str, ...]:
    """Column names a ``CREATE VIEW`` statement projects, in declaration order."""
    code = env.blank_noncode(sql_text)
    span = _top_level_select_span(code)
    if span is None:
        return ()
    names: list[str] = []
    for item in _split_top_level(code[span[0] : span[1]]):
        trimmed = item.strip()
        if not trimmed:
            continue
        alias = re.search(r"\bAS\s+([A-Za-z_][\w$]*)\s*$", trimmed, re.IGNORECASE)
        if alias is not None:
            names.append(alias.group(1))
            continue
        bare = re.search(r"([A-Za-z_][\w$]*)\s*$", trimmed)
        if bare is not None:
            names.append(bare.group(1))
    return tuple(names)


def _view_projection(
    question: Question, *, repo_root: Path
) -> tuple[frozenset[str] | None, list[Finding]]:
    """Read the shipped projection, or say precisely why it could not be read."""
    migration = repo_root / str(question.defined_in)
    if not migration.is_file():
        return None, [
            warn(
                question.qid,
                "view-columns",
                f"{question.defined_in} is absent, so the columns this prompt selects were NOT "
                "checked against the shipped view. This is not a pass.",
            )
        ]
    text = migration.read_text(encoding="utf-8", errors="replace")
    declared = _CREATE_VIEW.search(text)
    if declared is None:
        return None, [
            fail(
                question.qid,
                "view-columns",
                f"{question.defined_in} contains no CREATE VIEW; `defined_in` points at the "
                "wrong file",
            )
        ]
    if declared.group(2) != question.view:
        return None, [
            fail(
                question.qid,
                "view-columns",
                f"`view` is {question.view!r} but {question.defined_in} defines "
                f"{declared.group(1)}.{declared.group(2)}",
            )
        ]
    available = frozenset(view_columns(text))
    if not available:
        return None, [
            fail(
                question.qid,
                "view-columns",
                f"could not read a projection out of {question.defined_in}; the check cannot "
                "be trusted and is reported as a failure rather than skipped",
            )
        ]
    return available, []


def _check_view_columns(question: Question, *, repo_root: Path) -> list[Finding]:
    if question.view is None or question.defined_in is None:
        return []
    available, problems = _view_projection(question, repo_root=repo_root)
    if available is None:
        return problems
    missing = [c for c in question.selected_columns() if c not in available]
    if missing:
        return [
            fail(
                question.qid,
                "view-columns",
                f"selects {missing}, which {question.qualified_view} does not project. A judge "
                f"pasting this gets an error, not an answer. Available: {sorted(available)}",
            )
        ]
    return [
        info(
            question.qid,
            "view-columns",
            f"{len(question.selected_columns())} columns checked against {question.defined_in}",
        )
    ]


# ── The bound-statement size model ───────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class BoundStatement:
    """The measured length of an EXPLAIN question once its placeholders carry literals."""

    qid: str
    vector_column: str
    dimension: int
    statement_chars: int
    headroom_chars: int
    fits: bool
    sql: str = field(repr=False, default="")


def _vector_dimension(text: str, column: str) -> int | None:
    for match in _VECTOR_COLUMN.finditer(text):
        if match.group(1).lower() == column.lower():
            return int(match.group(2))
    return None


def _column_types(text: str) -> dict[str, str]:
    """Column name to declared type, read out of a ``CREATE TABLE``."""
    return {match.group(1).lower(): match.group(2).upper() for match in _COLUMN_TYPE.finditer(text)}


def _literal_for(column: str, sql_type: str | None) -> str:
    """Return a type-valid literal for a non-vector placeholder.

    **Type-valid, not merely long.** An earlier version of this bound every non-vector
    placeholder to a UUID literal on the theory that the longest literal is the safest one
    to measure. It measured correctly and produced a statement CockroachDB refuses with
    ``22023 unsupported comparison operator: <string> = <uuid>``, because ``facet`` is a
    ``STRING``. Measured on a local v26.2.5 node — see the module docstring. The runner
    executes this statement, so a length model that produces an unexecutable statement is
    a model that hides the one failure it exists to catch.

    The literals are therefore drawn from the declared type. The vector literal is four
    orders of magnitude larger than any of them, so the length verdict does not turn on
    this choice; executability does.
    """
    if sql_type is None or sql_type == "UUID":
        return _UUID_LITERAL
    if sql_type.startswith(("INT", "FLOAT")) or sql_type == "DECIMAL":
        return "0"
    if sql_type == "BOOL":
        return "true"
    if sql_type.startswith("TIMESTAMP"):
        return "'2026-08-04T09:14:00+10:00'::TIMESTAMPTZ"
    # STRING and everything else that compares against text. `control_failure` is a real
    # member of `event_cue.facet`'s CHECK list, so the literal is one the column could
    # actually hold rather than a placeholder shaped like one.
    return "'control_failure'" if column.lower() == "facet" else "'x'"


@dataclass(frozen=True, slots=True)
class _Binding:
    """The vector column, its declared width, and the literal each placeholder carries."""

    column: str
    dimension: int
    placeholder: str
    others: dict[str, str]


def _other_bindings(
    question: Question, ddl_text: str, *, vector_placeholder: str
) -> dict[str, str]:
    """Every non-vector placeholder, bound to a literal of its column's declared type."""
    types = _column_types(ddl_text)
    by_placeholder = {
        match.group(2): match.group(1).lower()
        for match in _EQUALITY_PLACEHOLDER.finditer(env.blank_noncode(question.sql))
    }
    bindings: dict[str, str] = {}
    for placeholder in set(_PLACEHOLDER.findall(question.sql)):
        if placeholder == vector_placeholder:
            continue
        column = by_placeholder.get(placeholder, "")
        bindings[placeholder] = _literal_for(column, types.get(column))
    return bindings


def _resolve_binding(
    question: Question, *, repo_root: Path
) -> tuple[_Binding | None, list[Finding]]:
    """Work out what to substitute, or say precisely which authority did not answer."""
    ddl = repo_root / str(question.defined_in)
    if not ddl.is_file():
        return None, [
            warn(
                question.qid,
                "bound-length",
                f"{question.defined_in} is absent, so the bound length of this statement was "
                "NOT measured against the 16 384-character cap. This is not a pass.",
            )
        ]
    ordered = _ORDER_VECTOR_COLUMN.search(question.sql)
    if ordered is None:
        return None, [fail(question.qid, "bound-length", "no `ORDER BY <column> <=> …` to measure")]
    column = ordered.group(1)
    text = ddl.read_text(encoding="utf-8", errors="replace")
    dimension = _vector_dimension(text, column)
    if dimension is None:
        return None, [
            fail(
                question.qid,
                "bound-length",
                f"{question.defined_in} declares no VECTOR width for column {column!r}",
            )
        ]
    placeholder = _DISTANCE_PLACEHOLDER.search(question.sql)
    if placeholder is None:
        return None, [
            fail(question.qid, "bound-length", "the distance operator has no placeholder to bind")
        ]
    vector_placeholder = placeholder.group(1)
    return (
        _Binding(
            column=column,
            dimension=dimension,
            placeholder=vector_placeholder,
            others=_other_bindings(question, text, vector_placeholder=vector_placeholder),
        ),
        [],
    )


def bind_and_measure(
    question: Question, *, repo_root: Path
) -> tuple[BoundStatement | None, list[Finding]]:
    """Substitute worst-case literals into an EXPLAIN question and measure the result.

    The vector width is read from the ``CREATE TABLE`` the question names, never assumed:
    a table whose embedding is widened from 1024 to 1536 makes the on-camera statement too
    long for the character cap, and the only acceptable place to discover that is here.
    """
    if question.plan is None or question.defined_in is None:
        return None, []
    binding, problems = _resolve_binding(question, repo_root=repo_root)
    if binding is None:
        return None, problems
    column = binding.column
    dimension = binding.dimension
    vector_placeholder = binding.placeholder
    others = binding.others
    model = env.model_vector_statement(
        question.sql,
        placeholder=vector_placeholder,
        dimension=dimension,
        other_bindings=others,
    )
    bound = BoundStatement(
        qid=question.qid,
        vector_column=column,
        dimension=dimension,
        statement_chars=model.statement_chars,
        headroom_chars=model.headroom_chars,
        fits=model.fits,
        sql=model.bound_sql,
    )
    if not model.fits:
        return bound, [
            fail(
                question.qid,
                "bound-length",
                f"bound to a {dimension}-dimension literal at six significant figures the "
                f"statement is {model.statement_chars} characters against a "
                f"{env.MAX_STATEMENT_CHARS} cap. The server truncates rather than raising, so "
                "this would answer a different question in front of the judge.",
            )
        ]
    return bound, [
        info(
            question.qid,
            "bound-length",
            f"bound to a {dimension}-dimension literal: {model.statement_chars} characters, "
            f"{model.headroom_chars} of headroom under the cap",
        )
    ]


# ── Agreement with demo/VERIFY.md ────────────────────────────────────────────────


def normalise_statement(sql: str) -> str:
    """Comments removed, whitespace collapsed, trailing semicolon dropped.

    Two statements that differ only in how they were wrapped in Markdown are the same
    statement, and a drift check that fired on line wrapping would be turned off within a
    week. Everything else — a renamed column, a changed ``LIMIT``, a dropped ``ORDER BY``
    — still differs.
    """
    code = re.sub(r"--[^\n]*", " ", sql)
    code = re.sub(r"\s+", " ", code).strip()
    return code.rstrip(";").strip()


def verify_md_statements(text: str) -> list[str]:
    """Every SQL statement inside a ```` ```sql ```` fence in ``demo/VERIFY.md``."""
    out: list[str] = []
    for block in _SQL_FENCE.findall(text):
        stripped = re.sub(r"--[^\n]*", " ", block)
        for piece in stripped.split(";"):
            if piece.strip():
                out.append(normalise_statement(piece))
    return out


def _check_verify_md(pack: Pack, *, repo_root: Path) -> list[Finding]:
    target = repo_root / VERIFY_RELPATH
    if not target.is_file():
        return [
            warn(
                "pack",
                "verify-md-drift",
                f"{VERIFY_RELPATH.as_posix()} is absent, so the judge-facing prompts were NOT "
                "compared against the file a judge actually reads. This is not a pass.",
            )
        ]
    text = target.read_text(encoding="utf-8", errors="replace")
    in_pack = {normalise_statement(q.sql): q.qid for q in pack}
    in_verify = frozenset(verify_md_statements(text))
    findings: list[Finding] = []
    matched = 0
    for statement in verify_md_statements(text):
        if statement in in_pack:
            matched += 1
            continue
        exemption = next(
            (e for e in pack.exemptions if e.statement_contains in statement),
            None,
        )
        if exemption is not None:
            continue
        findings.append(
            fail(
                "pack",
                "verify-md-drift",
                f"{VERIFY_RELPATH.as_posix()} contains a statement this pack does not carry and "
                f"does not exempt: {statement[:140]!r}. That file is the authority; add the "
                "question here or add an exemption with a reason.",
            )
        )
    for question in pack:
        if question.transcribed_from is None:
            continue
        if normalise_statement(question.sql) not in in_verify:
            findings.append(
                fail(
                    question.qid,
                    "verify-md-drift",
                    f"claims to be transcribed from {question.transcribed_from} but no statement "
                    "there matches it. The named file is the authority and this copy is stale.",
                )
            )
    findings.append(
        info(
            "pack",
            "verify-md-drift",
            f"{matched} statements matched between the pack and VERIFY.md",
        )
    )
    return findings


# ── Agreement with demo/REFUSAL-STRINGS.yaml ─────────────────────────────────────


def _explain_fragment(repo_root: Path) -> dict[str, Any] | None:
    target = repo_root / REFUSAL_STRINGS_RELPATH
    if not target.is_file():
        return None
    document = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        return None
    fragment = document.get("explain_fragment")
    return fragment if isinstance(fragment, dict) else None


def _check_refusal_strings(pack: Pack, *, repo_root: Path) -> list[Finding]:
    fragment = _explain_fragment(repo_root)
    plan_questions = [q for q in pack if q.plan is not None]
    if fragment is None:
        return [
            warn(
                "pack",
                "refusal-strings",
                f"{REFUSAL_STRINGS_RELPATH.as_posix()} has no readable `explain_fragment`, so the "
                "index name and the plan substrings were NOT cross-checked. This is not a pass.",
            )
        ]
    findings: list[Finding] = []
    camera_index = str(fragment.get("index", ""))
    prefix = [str(c) for c in (fragment.get("prefix_columns") or [])]
    substrings = [str(s) for s in (fragment.get("required_substrings") or [])]
    if not substrings:
        findings.append(
            fail(
                "pack",
                "refusal-strings",
                "`explain_fragment.required_substrings` is empty, so a plan question would assert "
                "nothing about the plan it printed",
            )
        )
    on_camera = [q for q in plan_questions if q.plan is not None and q.plan.index == camera_index]
    if not on_camera:
        findings.append(
            fail(
                "pack",
                "refusal-strings",
                f"REFUSAL-STRINGS.yaml names {camera_index!r} as the filmed index and no question "
                "in this pack asks for its plan",
            )
        )
    for question in on_camera:
        if question.plan is None:
            continue
        if list(question.plan.prefix_columns) != prefix:
            findings.append(
                fail(
                    question.qid,
                    "refusal-strings",
                    f"prefix columns {list(question.plan.prefix_columns)} disagree with "
                    f"REFUSAL-STRINGS.yaml's {prefix}. That file is the authority.",
                )
            )
        if bool(fragment.get("hint_is_mandatory")) and not question.plan.hint_is_mandatory:
            findings.append(
                fail(
                    question.qid,
                    "refusal-strings",
                    "REFUSAL-STRINGS.yaml records that the index hint is mandatory and this "
                    "question does not",
                )
            )
    findings.append(
        info("pack", "refusal-strings", f"plan substrings required by the film: {substrings}")
    )
    return findings


def required_plan_substrings(repo_root: Path) -> tuple[str, ...]:
    """Return the substrings a plan must contain, read from the file the film reads."""
    fragment = _explain_fragment(repo_root)
    if fragment is None:
        return ()
    return tuple(str(s) for s in (fragment.get("required_substrings") or []))


# ── The pack's own prose, under the repository's claim rules ─────────────────────


def _load_claim_hygiene(repo_root: Path) -> Any | None:
    target = repo_root / CLAIM_HYGIENE_RELPATH
    if not target.is_file():
        return None
    name = "_judge_claim_hygiene"
    spec = importlib.util.spec_from_file_location(name, target)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution: `@dataclass(slots=True)` rebuilds the class and looks
    # its own module up in `sys.modules`, so a module executed while unregistered dies with
    # an AttributeError that has nothing to do with the code being loaded.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _check_claim_hygiene(*, repo_root: Path, judge_dir: Path) -> list[Finding]:
    module = _load_claim_hygiene(repo_root)
    if module is None:
        return [
            warn(
                "pack",
                "claim-hygiene",
                f"{CLAIM_HYGIENE_RELPATH.as_posix()} is absent, so the pack's prose was NOT "
                "scanned for forbidden claims. This is not a pass.",
            )
        ]
    targets = sorted(
        p for pattern in ("*.md", "*.yaml") for p in judge_dir.glob(pattern) if p.is_file()
    )
    if not targets:
        return [warn("pack", "claim-hygiene", "no prose file in the judge directory to scan")]
    findings = [
        fail(
            Path(f.path).name,
            "claim-hygiene",
            f"line {f.line_no} [{f.rule_id}] {f.excerpt}",
        )
        for f in module.scan_paths(targets)
    ]
    if findings:
        return findings
    return [
        info(
            "pack",
            "claim-hygiene",
            f"{len(targets)} files scanned under the must-not-claim table with no findings",
        )
    ]


# ── The whole drift check ────────────────────────────────────────────────────────


def check_drift(pack: Pack, *, repo_root: Path, judge_dir: Path | None = None) -> list[Finding]:
    """Compare the pack against every authority it copies from."""
    directory = judge_dir or pack.source.parent
    findings: list[Finding] = []
    for question in pack:
        findings.extend(_check_view_columns(question, repo_root=repo_root))
        _, measured = bind_and_measure(question, repo_root=repo_root)
        findings.extend(measured)
    findings.extend(_check_verify_md(pack, repo_root=repo_root))
    findings.extend(_check_refusal_strings(pack, repo_root=repo_root))
    findings.extend(_check_claim_hygiene(repo_root=repo_root, judge_dir=directory))
    return findings


def bound_statements(pack: Pack, *, repo_root: Path) -> tuple[BoundStatement, ...]:
    """Every EXPLAIN question, bound to worst-case literals and measured."""
    out: list[BoundStatement] = []
    for question in pack:
        bound, _ = bind_and_measure(question, repo_root=repo_root)
        if bound is not None:
            out.append(bound)
    return tuple(out)


def severities(findings: Sequence[Finding]) -> dict[str, int]:
    """Count of findings by severity."""
    counts = {"fail": 0, "warn": 0, "info": 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts
