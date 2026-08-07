# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
r"""``trappoint migrate lint`` — the sequence ban and the citation rule.

Two rules, one of them the reason this command exists at all.

**THE SEQUENCE BAN (ruling D10).** ``CREATE SEQUENCE``, ``nextval(``, ``SERIAL`` and
``unique_rowid()`` are refused in every migration file and every rendered template.

The claim the ban protects is precise and it is worth stating in full, because it is
the thing that stops being true the moment one migration slips through. The event
ledger is gap-free **by compare-and-swap** — ``UNIQUE (subject, prev_seq)`` — and not
by a sequence. A sequence in CockroachDB is allowed to leave gaps: a rolled-back
transaction consumes a value, and ``unique_rowid()`` is not dense by construction. So
under a sequence, a gap in the ledger means *nothing*: it might be tampering or it
might be Tuesday. Under CAS, **a gap MEANS tampering**, and that sentence is the whole
evidentiary value of the ledger. One reintroduced sequence anywhere in the schema and
the sentence has to be withdrawn.

A convention cannot hold that. A lint can.

**THE CITATION RULE (ARCHITECTURE.md §18).** Every migration file cites at least one
``MI\\d\\d`` or ``I\\d\\d`` in its header comment. The repository becomes an instance of
its own thesis: every clause carries a pointer to what wrote it, including the clauses
of the schema.

The lint is run over code with comments stripped (see ``sqltext``), so this docstring
and the explanatory comments in a migration file are free to name the banned tokens —
which they must be, or the rule cannot be explained where it applies.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .discovery import MIGRATION_SUFFIXES, statement_count
from .sqltext import header_comment, strip_sql_comments

__all__ = ["Finding", "LintReport", "lint_paths", "lint_text"]

# Template sources are linted too: a banned token in a `.j2` becomes a banned token in
# every rendered vertical, and catching it at the template is catching it once.
LINTED_SUFFIXES: tuple[str, ...] = (*MIGRATION_SUFFIXES, ".sql.j2", ".j2")

_BANNED: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "create-sequence",
        re.compile(r"\bCREATE\s+(?:TEMP\s+|TEMPORARY\s+|UNLOGGED\s+)*SEQUENCE\b", re.IGNORECASE),
        "a sequence makes a gap ambiguous; the ledger is gap-free by CAS so a gap MEANS tampering",
    ),
    (
        "nextval",
        re.compile(r"\bnextval\s*\(", re.IGNORECASE),
        (
            "nextval() reads a sequence, and a rolled-back transaction consumes a value "
            "without producing a row"
        ),
    ),
    (
        "serial",
        re.compile(r"\b(?:BIG|SMALL)?SERIAL[248]?\b", re.IGNORECASE),
        "SERIAL is a sequence with a friendlier name",
    ),
    (
        "unique-rowid",
        re.compile(r"\bunique_rowid\s*\(", re.IGNORECASE),
        "unique_rowid() is unique but not dense, so it cannot carry a gap-free claim",
    ),
)

_CITATION = re.compile(r"\b(?:MI\d{2}|I\d{2})\b")


@dataclass(frozen=True, slots=True)
class Finding:
    """One refusal, located precisely enough to fix without searching."""

    path: Path
    line: int
    rule: str
    detail: str

    def render(self) -> str:
        """Format the finding as a single ``path:line: rule — detail`` line."""
        return f"{self.path}:{self.line}: {self.rule} — {self.detail}"


@dataclass(frozen=True, slots=True)
class LintReport:
    """The outcome of a lint run."""

    files_checked: int
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        """True when nothing was refused."""
        return not self.findings


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def lint_text(path: Path, text: str, *, require_citation: bool) -> list[Finding]:
    """Lint one file's *text*, returning every finding.

    *require_citation* is False for template sources: a `.j2` renders into files that
    each carry their own header, and requiring the citation in both places would make
    the template's header the one nobody updates.
    """
    findings: list[Finding] = []
    code = strip_sql_comments(text)

    for rule, pattern, detail in _BANNED:
        for match in pattern.finditer(code):
            findings.append(
                Finding(
                    path=path,
                    line=_line_of(code, match.start()),
                    rule=f"banned-token:{rule}",
                    detail=f"{match.group(0)!r} — {detail}",
                )
            )

    if require_citation:
        header = header_comment(text)
        if not _CITATION.search(header):
            findings.append(
                Finding(
                    path=path,
                    line=1,
                    rule="missing-invariant-citation",
                    detail=(
                        "the header comment cites no MInn or Inn identifier; "
                        "ARCHITECTURE.md §18 requires every migration to declare which "
                        "invariant it realises, where a reviewer reads it"
                    ),
                )
            )

        count = statement_count(text)
        if count > 1:
            findings.append(
                Finding(
                    path=path,
                    line=1,
                    rule="multiple-statements",
                    detail=(
                        f"{count} statements in one file. CockroachDB DDL is not "
                        "transactional across statements, so a failure here leaves a "
                        "half-applied file and an undiagnosable dirty marker. Split it, "
                        "using a lowercase letter suffix (ruling D7)."
                    ),
                )
            )

    return findings


def _iter_files(roots: Sequence[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file():
            yield root
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and any(path.name.endswith(s) for s in LINTED_SUFFIXES):
                yield path


def lint_paths(roots: Sequence[Path]) -> LintReport:
    """Lint every migration and template under *roots*.

    An empty tree passes with zero findings and zero files checked. That is the correct
    answer, not a vacuous one: the ban is a statement about what the tree may contain,
    and an empty tree contains nothing banned. The count is reported so a run that
    checked nothing is never mistaken for a run that checked everything.
    """
    findings: list[Finding] = []
    checked = 0
    for path in _iter_files(roots):
        checked += 1
        text = path.read_text(encoding="utf-8")
        is_template = path.name.endswith(".j2")
        findings.extend(lint_text(path, text, require_citation=not is_template))
    return LintReport(files_checked=checked, findings=tuple(findings))
