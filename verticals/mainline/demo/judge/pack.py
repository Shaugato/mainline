# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``QUESTIONS.yaml`` loaded, made strict, and checked against the Managed-MCP envelope.

This module knows nothing about the database or about ``demo/VERIFY.md``. It answers one
question — *is this pack internally well-formed and legal to send?* — and it answers it
with no network, no cluster and no credential. ``judge/drift.py`` answers the other
question: *does it still agree with the rest of the repository?*

Three of the checks here are the ones that earn the file:

* **Every negative must actually be refused.** ``N01`` to ``N04`` declare which refusal they
  expect by its stable machine name, and the validator asserts that exact class fired.
  A negative that quietly stopped being negative is the worst artefact in the
  repository, because a green negative suite reads as the strongest evidence in it.
* **The envelope in the data must equal the envelope in the code.** Loosening a limit in
  ``QUESTIONS.yaml`` to make a prompt fit fails the build rather than shipping a prompt
  the server will truncate.
* **Every positive must say what it does not prove.** A question with an empty
  ``does_not_prove`` block is a finding. The pack's whole value to a stranger is that its
  claims are bounded, and an unbounded claim is the one thing a judge has already seen
  forty times this week.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

from . import envelope as env

PACK_FILENAME: Final = "QUESTIONS.yaml"

#: The truncation guards ``judge/runner.py`` implements. A question naming a guard that is
#: not in this set is a question whose completeness claim nothing enforces.
IMPLEMENTED_GUARDS: Final = frozenset({"row_count_equals_limit", "plan_substrings"})

#: Channels a question can run on. ``mcp_only`` marks the negatives: over a pgwire
#: connection as cluster admin they would SUCCEED, so running them there and reporting a
#: pass would invert their meaning.
CHANNELS: Final = frozenset({"mcp", "mcp_only"})

EXPECTATIONS: Final = frozenset({"answers", "refused"})

_SELECT_LIST: Final = re.compile(r"\bSELECT\b(.*?)\bFROM\b", re.IGNORECASE | re.DOTALL)
_TRAILING_NAME: Final = re.compile(r"([A-Za-z_][A-Za-z0-9_$]*)\s*$")
_INDEX_HINT: Final = re.compile(r"([A-Za-z_][\w.$]*)@([A-Za-z_][\w$]*)")


class PackError(Exception):
    """The pack is absent, malformed, or disagrees with itself in a way that stops loading."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One validation result, located precisely enough to fix without a conversation."""

    where: str
    check: str
    severity: str
    message: str

    def render(self) -> str:
        return f"{self.severity.upper():5} [{self.check}] {self.where}: {self.message}"


def fail(where: str, check: str, message: str) -> Finding:
    return Finding(where=where, check=check, severity="fail", message=message)


def warn(where: str, check: str, message: str) -> Finding:
    return Finding(where=where, check=check, severity="warn", message=message)


def info(where: str, check: str, message: str) -> Finding:
    return Finding(where=where, check=check, severity="info", message=message)


@dataclass(frozen=True, slots=True)
class Completeness:
    """How a question is guarded against reading a truncated answer as a complete one."""

    columns: tuple[str, ...]
    guard: str
    why_no_columns: str | None


@dataclass(frozen=True, slots=True)
class PlanExpectation:
    """What an ``EXPLAIN`` question expects to see in the plan, and what must be bound first."""

    index: str
    prefix_columns: tuple[str, ...]
    required_substrings_from: str | None
    hint_is_mandatory: bool
    substitutions: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class Question:
    """One judge question: the ask, the exact statement, and the bounds on what it shows."""

    qid: str
    ask: str
    verb: str
    channel: str
    expectation: str
    sql: str
    view: str | None
    defined_in: str | None
    transcribed_from: str | None
    beat: int | None
    shot_id: str | None
    proves: str
    does_not_prove: tuple[str, ...]
    completeness: Completeness | None
    plan: PlanExpectation | None
    client_refusal: str | None
    refused_by: str | None
    must_fail_because: str | None
    honest_notes: tuple[str, ...]

    @property
    def is_negative(self) -> bool:
        return self.expectation == "refused"

    @property
    def qualified_view(self) -> str | None:
        return None if self.view is None else f"{env.AUDIT_SCHEMA}.{self.view}"

    def selected_columns(self) -> tuple[str, ...]:
        """Return the column names the outermost ``SELECT`` list asks for.

        Used to check that a question's declared completeness columns are columns the
        statement actually selects — a pack that promises ``rows_complete`` in a prompt
        that never selects it is a pack whose guard is decorative.
        """
        return selected_columns(self.sql)


@dataclass(frozen=True, slots=True)
class Exemption:
    """A statement in ``demo/VERIFY.md`` that is deliberately not a question in this pack."""

    statement_contains: str
    reason: str


@dataclass(frozen=True, slots=True)
class Pack:
    """The whole judge pack, loaded and typed."""

    version: int
    authority: tuple[str, ...]
    declared_envelope: Mapping[str, Any]
    reading_notes: Mapping[str, str]
    questions: tuple[Question, ...]
    related_assertions: tuple[Mapping[str, Any], ...]
    exemptions: tuple[Exemption, ...]
    source: Path
    raw: Mapping[str, Any] = field(repr=False, default_factory=dict)

    def by_id(self, qid: str) -> Question:
        for question in self.questions:
            if question.qid == qid:
                return question
        raise PackError(f"{qid!r} is not a question in this pack; have {[q.qid for q in self]}")

    def positives(self) -> tuple[Question, ...]:
        return tuple(q for q in self.questions if not q.is_negative)

    def negatives(self) -> tuple[Question, ...]:
        return tuple(q for q in self.questions if q.is_negative)

    def __iter__(self) -> Iterator[Question]:
        return iter(self.questions)

    def __len__(self) -> int:
        return len(self.questions)


# ── Parsing ──────────────────────────────────────────────────────────────────────


def selected_columns(sql: str) -> tuple[str, ...]:
    """Column names in the first ``SELECT`` list, comments and literals already blanked.

    Deliberately simple, and correct for the shape this pack allows: a flat list of bare
    or dotted column names against one relation. A statement whose select list this cannot
    read produces an empty tuple, which makes the completeness-column check fail loudly
    rather than pass vacuously.
    """
    code = env.blank_noncode(sql)
    match = _SELECT_LIST.search(code)
    if match is None:
        return ()
    depth = 0
    current: list[str] = []
    items: list[str] = []
    for ch in match.group(1):
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

    names: list[str] = []
    for item in items:
        trimmed = item.strip()
        if not trimmed or trimmed == "*":
            continue
        name = _TRAILING_NAME.search(trimmed)
        if name is not None:
            names.append(name.group(1))
    return tuple(names)


def _as_str_tuple(value: Any, *, where: str, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise PackError(f"{where}: `{field_name}` must be a list of strings, got {value!r}")
    return tuple(str(item) for item in value)


def _parse_completeness(body: Mapping[str, Any], *, where: str) -> Completeness | None:
    raw = body.get("completeness")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise PackError(f"{where}: `completeness` must be a mapping")
    guard = raw.get("guard")
    if not isinstance(guard, str) or not guard:
        raise PackError(f"{where}: `completeness.guard` is required and must be a string")
    why = raw.get("why_no_columns")
    return Completeness(
        columns=_as_str_tuple(raw.get("columns"), where=where, field_name="completeness.columns"),
        guard=guard,
        why_no_columns=None if why is None else str(why),
    )


def _parse_plan(body: Mapping[str, Any], *, where: str) -> PlanExpectation | None:
    raw = body.get("plan")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise PackError(f"{where}: `plan` must be a mapping")
    index = raw.get("index")
    if not isinstance(index, str) or "@" not in index:
        raise PackError(f"{where}: `plan.index` must be a `table@index` string, got {index!r}")
    placeholders = raw.get("placeholders") or {}
    if not isinstance(placeholders, Mapping):
        raise PackError(f"{where}: `plan.placeholders` must be a mapping")
    substitute = _as_str_tuple(
        placeholders.get("substitute"), where=where, field_name="plan.placeholders.substitute"
    )
    required_from = raw.get("required_substrings_from")
    return PlanExpectation(
        index=index,
        prefix_columns=_as_str_tuple(
            raw.get("prefix_columns"), where=where, field_name="plan.prefix_columns"
        ),
        required_substrings_from=None if required_from is None else str(required_from),
        hint_is_mandatory=bool(raw.get("hint_is_mandatory", False)),
        substitutions=substitute,
        note=str(placeholders.get("note", "")),
    )


def _parse_question(body: Mapping[str, Any], *, index: int) -> Question:
    qid = body.get("id")
    if not isinstance(qid, str) or not qid:
        raise PackError(f"questions[{index}] has no usable `id`")
    where = f"questions[{qid}]"
    sql = body.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise PackError(f"{where}: `sql` is required and must be a non-empty string")
    beat = body.get("beat")
    if beat is not None and not isinstance(beat, int):
        raise PackError(f"{where}: `beat` must be an integer or absent, got {beat!r}")
    view = body.get("view")
    return Question(
        qid=qid,
        ask=str(body.get("ask", "")).strip(),
        verb=str(body.get("verb", "")),
        channel=str(body.get("channel", "mcp")),
        expectation=str(body.get("expectation", "answers")),
        sql=sql.strip(),
        view=None if view is None else str(view),
        defined_in=None if body.get("defined_in") is None else str(body["defined_in"]),
        transcribed_from=(
            None if body.get("transcribed_from") is None else str(body["transcribed_from"])
        ),
        beat=beat,
        shot_id=None if body.get("shot_id") is None else str(body["shot_id"]),
        proves=str(body.get("proves", "")).strip(),
        does_not_prove=_as_str_tuple(
            body.get("does_not_prove"), where=where, field_name="does_not_prove"
        ),
        completeness=_parse_completeness(body, where=where),
        plan=_parse_plan(body, where=where),
        client_refusal=(
            None if body.get("client_refusal") is None else str(body["client_refusal"])
        ),
        refused_by=None if body.get("refused_by") is None else str(body["refused_by"]),
        must_fail_because=(
            None
            if body.get("must_fail_because") is None
            else str(body["must_fail_because"]).strip()
        ),
        honest_notes=_as_str_tuple(
            body.get("honest_notes"), where=where, field_name="honest_notes"
        ),
    )


def _parse_exemptions(document: Mapping[str, Any]) -> tuple[Exemption, ...]:
    raw = document.get("verify_md_exemptions") or []
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise PackError("`verify_md_exemptions` must be a list")
    out: list[Exemption] = []
    for index, body in enumerate(raw):
        if not isinstance(body, Mapping):
            raise PackError(f"verify_md_exemptions[{index}] must be a mapping")
        needle = body.get("statement_contains")
        reason = body.get("reason")
        if not isinstance(needle, str) or not needle.strip():
            raise PackError(f"verify_md_exemptions[{index}] has no `statement_contains`")
        if not isinstance(reason, str) or not reason.strip():
            raise PackError(
                f"verify_md_exemptions[{index}] has no `reason`. An exemption without a stated "
                "reason is a hole in the drift check, not an exemption."
            )
        out.append(Exemption(statement_contains=needle.strip(), reason=reason.strip()))
    return tuple(out)


def parse_pack(document: Mapping[str, Any], *, source: Path) -> Pack:
    """Build a :class:`Pack` from an already-parsed YAML document."""
    questions_raw = document.get("questions")
    if not isinstance(questions_raw, Sequence) or isinstance(questions_raw, str):
        raise PackError("the pack has no `questions` list")
    questions = tuple(
        _parse_question(body, index=index)
        for index, body in enumerate(questions_raw)
        if _require_mapping(body, index)
    )
    declared = document.get("envelope")
    if not isinstance(declared, Mapping):
        raise PackError("the pack has no `envelope` block; there is nothing to validate against")
    notes = document.get("reading_notes") or {}
    if not isinstance(notes, Mapping):
        raise PackError("`reading_notes` must be a mapping")
    related = document.get("related_assertions") or []
    if not isinstance(related, Sequence) or isinstance(related, str):
        raise PackError("`related_assertions` must be a list")
    return Pack(
        version=int(document.get("version", 0)),
        authority=_as_str_tuple(document.get("authority"), where="pack", field_name="authority"),
        declared_envelope=declared,
        reading_notes={str(k): str(v).strip() for k, v in notes.items()},
        questions=questions,
        related_assertions=tuple(r for r in related if isinstance(r, Mapping)),
        exemptions=_parse_exemptions(document),
        source=source,
        raw=document,
    )


def _require_mapping(body: object, index: int) -> bool:
    if not isinstance(body, Mapping):
        raise PackError(f"questions[{index}] must be a mapping, got {type(body).__name__}")
    return True


def pack_path(judge_dir: Path | None = None) -> Path:
    """Absolute path to ``QUESTIONS.yaml``."""
    return (judge_dir or Path(__file__).resolve().parent) / PACK_FILENAME


def load_pack(path: Path | None = None) -> Pack:
    """Load and type the judge pack."""
    resolved = path or pack_path()
    if not resolved.is_file():
        raise PackError(f"judge pack not found at {resolved}")
    try:
        document = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackError(f"{resolved} is not valid YAML: {exc}") from exc
    if not isinstance(document, Mapping):
        raise PackError(f"{resolved} must contain a mapping at the top level")
    return parse_pack(document, source=resolved)


# ── Validation ───────────────────────────────────────────────────────────────────


def _check_declared_envelope(pack: Pack) -> list[Finding]:
    findings: list[Finding] = []
    for key, expected in env.DECLARED_ENVELOPE.items():
        if key not in pack.declared_envelope:
            findings.append(
                fail("envelope", "envelope-agreement", f"`{key}` is missing from the pack")
            )
            continue
        actual = pack.declared_envelope[key]
        if actual != expected:
            findings.append(
                fail(
                    "envelope",
                    "envelope-agreement",
                    f"`{key}` is {actual!r} in {PACK_FILENAME} and {expected!r} in envelope.py. "
                    "The code is the authority; a limit loosened in data to make a prompt fit "
                    "ships a prompt the server truncates.",
                )
            )
    extra = set(pack.declared_envelope) - set(env.DECLARED_ENVELOPE)
    if extra:
        findings.append(
            warn(
                "envelope",
                "envelope-agreement",
                f"the pack declares limits envelope.py does not model: {sorted(extra)}",
            )
        )
    return findings


def _check_shape(question: Question) -> list[Finding]:
    findings: list[Finding] = []
    where = question.qid
    if question.channel not in CHANNELS:
        findings.append(
            fail(
                where,
                "channel",
                f"unknown channel {question.channel!r}; use one of {sorted(CHANNELS)}",
            )
        )
    if question.expectation not in EXPECTATIONS:
        findings.append(fail(where, "expectation", f"unknown expectation {question.expectation!r}"))
    if not question.ask:
        findings.append(
            fail(where, "ask", "a question with no plain-English ask is not a question")
        )
    if not question.proves:
        findings.append(fail(where, "proves", "`proves` is empty"))
    if not question.is_negative and not question.does_not_prove:
        findings.append(
            fail(
                where,
                "does-not-prove",
                "a positive question with no `does_not_prove` block is an unbounded claim, "
                "which is the one thing a judge has already seen forty times this week",
            )
        )
    if question.is_negative and not question.must_fail_because:
        findings.append(fail(where, "must-fail-because", "a negative must say why it has to fail"))
    return findings


def _check_envelope(question: Question) -> list[Finding]:
    """Positives must pass the envelope; negatives must be refused, by the named refusal."""
    where = question.qid
    if question.is_negative:
        expected = env.REFUSAL_BY_NAME.get(question.client_refusal or "")
        if expected is None:
            return [
                fail(
                    where,
                    "negative-refusal",
                    f"`client_refusal` is {question.client_refusal!r}, which is not a refusal "
                    f"envelope.py can raise; have {sorted(env.REFUSAL_BY_NAME)}",
                )
            ]
        try:
            env.enforce(question.sql, verb=question.verb)
        except env.EnvelopeRefusal as exc:
            if isinstance(exc, expected):
                return []
            return [
                fail(
                    where,
                    "negative-refusal",
                    f"expected {expected.__name__} ({expected.limit}) but the scanner raised "
                    f"{type(exc).__name__} ({exc.limit})",
                )
            ]
        return [
            fail(
                where,
                "negative-refusal",
                "this statement MUST be refused and the scanner accepted it. A negative that has "
                "quietly stopped being negative is the worst artefact in the repository.",
            )
        ]
    try:
        env.enforce(question.sql, verb=question.verb)
    except env.EnvelopeRefusal as exc:
        return [fail(where, "envelope", str(exc))]
    return []


def _check_completeness(question: Question) -> list[Finding]:
    findings: list[Finding] = []
    where = question.qid
    if question.is_negative:
        return findings
    completeness = question.completeness
    if completeness is None:
        return [
            fail(
                where,
                "completeness",
                "no `completeness` block: nothing states how a truncated answer is told apart "
                "from a complete one",
            )
        ]
    if completeness.guard not in IMPLEMENTED_GUARDS:
        findings.append(
            fail(
                where,
                "completeness",
                f"guard {completeness.guard!r} is not implemented by judge/runner.py; "
                f"implemented guards are {sorted(IMPLEMENTED_GUARDS)}",
            )
        )
    selected = set(question.selected_columns())
    missing = [c for c in completeness.columns if c not in selected]
    if missing:
        findings.append(
            fail(
                where,
                "completeness",
                f"declares completeness columns the statement does not select: {missing}",
            )
        )
    silent = not completeness.columns and not completeness.why_no_columns
    if question.verb == "select_query" and silent:
        findings.append(
            fail(
                where,
                "completeness",
                "selects no completeness column and gives no reason. Either name the view's "
                "completeness columns or say in `why_no_columns` why this statement cannot.",
            )
        )
    return findings


def _check_plan(question: Question) -> list[Finding]:
    findings: list[Finding] = []
    where = question.qid
    if question.verb != "explain_query":
        if question.plan is not None:
            findings.append(fail(where, "plan", "a `plan` block on a non-EXPLAIN question"))
        return findings
    plan = question.plan
    if plan is None:
        return [fail(where, "plan", "an EXPLAIN question with no `plan` block asserts nothing")]

    code = env.blank_noncode(question.sql)
    hints = {f"{m.group(1)}@{m.group(2)}" for m in _INDEX_HINT.finditer(code)}
    if plan.index not in hints:
        findings.append(
            fail(
                where,
                "plan-index-hint",
                f"the statement does not name {plan.index!r}. At demo corpus scale the optimizer "
                "does not choose the vector index on its own (ADR 0002 F1), so an unhinted "
                "statement proves the opposite of what this question claims.",
            )
        )
    code = env.blank_noncode(question.sql)
    for column in plan.prefix_columns:
        single = re.search(rf"\b{re.escape(column)}\s*=", code)
        listed = re.search(rf"\b{re.escape(column)}\s+IN\s*\(", code, re.IGNORECASE)
        if listed is not None:
            findings.append(
                fail(
                    where,
                    "plan-prefix",
                    f"prefix column {column!r} is constrained with IN (...). Every prefix column "
                    "must be constrained to a single value or the index is not traversed.",
                )
            )
        elif single is None:
            findings.append(
                fail(
                    where,
                    "plan-prefix",
                    f"prefix column {column!r} is not constrained to a single value",
                )
            )
    if not plan.substitutions:
        findings.append(
            fail(
                where,
                "plan-placeholders",
                "the statement carries placeholders and the pack does not say what to substitute; "
                "the managed verbs take a statement, not a parameter list",
            )
        )
    return findings


def _check_paths(question: Question, *, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for label, value in (
        ("defined_in", question.defined_in),
        ("transcribed_from", question.transcribed_from),
    ):
        if value is None:
            continue
        target = repo_root / value
        if not target.is_file():
            findings.append(
                fail(question.qid, "path", f"`{label}` points at {value}, which does not exist")
            )
    return findings


def _check_ids(pack: Pack) -> list[Finding]:
    seen: set[str] = set()
    findings: list[Finding] = []
    for question in pack:
        if question.qid in seen:
            findings.append(fail(question.qid, "id", "duplicate question id"))
        seen.add(question.qid)
    if not pack.negatives():
        findings.append(
            fail(
                "pack",
                "negatives",
                "a pack with no negatives is a pack whose green means nothing",
            )
        )
    return findings


def validate_pack(pack: Pack, *, repo_root: Path) -> list[Finding]:
    """Check the pack against itself and against the Managed-MCP envelope.

    Returns every finding rather than raising on the first, so one run of the validator
    tells the whole truth about the pack instead of the first sentence of it.
    """
    findings: list[Finding] = []
    findings.extend(_check_declared_envelope(pack))
    findings.extend(_check_ids(pack))
    for question in pack:
        findings.extend(_check_shape(question))
        findings.extend(_check_envelope(question))
        findings.extend(_check_completeness(question))
        findings.extend(_check_plan(question))
        findings.extend(_check_paths(question, repo_root=repo_root))
    return findings


def worst_severity(findings: Sequence[Finding]) -> str:
    """Return the most serious severity present, or ``"ok"`` when there is nothing wrong."""
    for severity in ("fail", "warn", "info"):
        if any(f.severity == severity for f in findings):
            return severity
    return "ok"
