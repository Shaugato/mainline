# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Prove the judge pack's validator can go red.

A validator that has only ever been green asserts nothing about the pack it validates.
That is PL-2 applied to a checker rather than to a product, and it matters more here than
almost anywhere else in the repository: this pack's job is to catch a judge-facing prompt
that has silently stopped being true, and a checker that silently stopped checking is the
same defect one level up.

So each family of check gets one planted violation, applied to a **copy** of the real pack
so the fault is attributable, and :func:`self_test` fails when any planted violation is not
reported. The mutations are deliberately the realistic ones — a renamed column, a negative
that stopped being negative, a dropped index hint, a prefix widened to ``IN (...)`` — not
synthetic garbage, because a scanner tuned on garbage catches garbage.
"""

from __future__ import annotations

import copy
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from . import drift as drift_mod
from . import envelope as env
from .pack import Finding, parse_pack, validate_pack

#: A markdown page planted in a scratch judge directory so the claim-hygiene family has
#: something to fire on. Two violations from the repository's own must-not-claim table.
PLANTED_PAGE = """\
# A deliberately non-compliant judge page

Row-level security protects the record from a rogue admin, end to end.
Our contribution was merged into upstream last week.
"""


@dataclass(frozen=True, slots=True)
class Planted:
    """One planted violation: what was broken, and which check must notice."""

    name: str
    check: str
    describe: str


def _mutate_view_columns(document: dict[str, Any]) -> None:
    question = _question(document, "Q01")
    question["sql"] = question["sql"].replace("site_id, state,", "site_id, state, no_such_column,")


def _mutate_negative(document: dict[str, Any]) -> None:
    question = _question(document, "N02")
    question["sql"] = "SELECT count(*) AS n FROM mainline_audit.v_open_gate_summary LIMIT 25;"


def _mutate_does_not_prove(document: dict[str, Any]) -> None:
    _question(document, "Q03")["does_not_prove"] = []


def _mutate_envelope(document: dict[str, Any]) -> None:
    document["envelope"]["max_statement_chars"] = 999_999


def _mutate_plan_hint(document: dict[str, Any]) -> None:
    question = _question(document, "Q10")
    question["sql"] = question["sql"].replace("@cue_scoped_idx", "")


def _mutate_plan_prefix(document: dict[str, Any]) -> None:
    question = _question(document, "Q10C")
    question["sql"] = question["sql"].replace("c.tenant_id = $1", "c.tenant_id IN ($1)")


def _mutate_completeness(document: dict[str, Any]) -> None:
    _question(document, "Q02")["completeness"]["columns"].append("column_never_selected")


def _mutate_path(document: dict[str, Any]) -> None:
    _question(document, "Q06")["defined_in"] = "verticals/mainline/db/migrations/9999_absent.sql"


def _mutate_verify_drift(document: dict[str, Any]) -> None:
    document["questions"] = [q for q in document["questions"] if q.get("id") != "Q04"]


PLANTED: tuple[tuple[Planted, Any], ...] = (
    (
        Planted(
            "renamed column",
            "view-columns",
            "a prompt selects a column the shipped view does not project",
        ),
        _mutate_view_columns,
    ),
    (
        Planted(
            "negative gone green",
            "negative-refusal",
            "a statement that must fail was replaced by one that succeeds",
        ),
        _mutate_negative,
    ),
    (
        Planted(
            "unbounded claim",
            "does-not-prove",
            "a positive question ships with nothing it declines to claim",
        ),
        _mutate_does_not_prove,
    ),
    (
        Planted(
            "limit loosened in data",
            "envelope-agreement",
            "the character cap was raised in YAML to make a prompt fit",
        ),
        _mutate_envelope,
    ),
    (
        Planted(
            "index hint dropped",
            "plan-index-hint",
            "the EXPLAIN stopped naming the index, so the optimizer chooses the plan",
        ),
        _mutate_plan_hint,
    ),
    (
        Planted(
            "prefix widened",
            "plan-prefix",
            "a prefix column was constrained with IN (...), which does not traverse the index",
        ),
        _mutate_plan_prefix,
    ),
    (
        Planted(
            "decorative guard",
            "completeness",
            "a completeness column is declared that the statement never selects",
        ),
        _mutate_completeness,
    ),
    (
        Planted(
            "dangling authority",
            "path",
            "`defined_in` points at a migration that is not in the repository",
        ),
        _mutate_path,
    ),
    (
        Planted(
            "prompt dropped",
            "verify-md-drift",
            "a statement a judge reads in VERIFY.md is no longer carried or exempted here",
        ),
        _mutate_verify_drift,
    ),
)


def _question(document: Mapping[str, Any], qid: str) -> dict[str, Any]:
    for question in document["questions"]:
        if question.get("id") == qid:
            return cast("dict[str, Any]", question)
    raise KeyError(f"the real pack no longer contains {qid}; the self-test needs updating")


def _fired(findings: list[Finding], check: str) -> bool:
    return any(f.check == check and f.severity == "fail" for f in findings)


def _run_one(
    raw: Mapping[str, Any], mutate: Any, *, source: Path, repo_root: Path, judge_dir: Path
) -> list[Finding]:
    document = copy.deepcopy(dict(raw))
    mutate(document)
    pack = parse_pack(document, source=source)
    findings = validate_pack(pack, repo_root=repo_root)
    findings.extend(drift_mod.check_drift(pack, repo_root=repo_root, judge_dir=judge_dir))
    return findings


def _claim_hygiene_fires(repo_root: Path) -> bool:
    """Plant a non-compliant page in a scratch directory and see the scanner fire on it."""
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        (scratch / "planted.md").write_text(PLANTED_PAGE, encoding="utf-8")
        findings = drift_mod._check_claim_hygiene(repo_root=repo_root, judge_dir=scratch)
    return any(f.check == "claim-hygiene" and f.severity == "fail" for f in findings)


def _size_model_refuses() -> bool:
    """Bind a statement to an absurd vector width and require the size model to refuse it."""
    model = env.model_vector_statement(
        "EXPLAIN SELECT 1 FROM t ORDER BY emb <=> $1 LIMIT 10;",
        placeholder="$1",
        dimension=4096,
    )
    return not model.fits


@dataclass(frozen=True, slots=True)
class SelfTestResult:
    """Which planted violations were caught, and which were not."""

    caught: tuple[str, ...]
    missed: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missed


def self_test(*, repo_root: Path, source: Path, judge_dir: Path) -> SelfTestResult:
    """Plant one violation per family and report which ones the validator noticed."""
    from .pack import load_pack

    raw = load_pack(source).raw
    caught: list[str] = []
    missed: list[str] = []
    for planted, mutate in PLANTED:
        findings = _run_one(raw, mutate, source=source, repo_root=repo_root, judge_dir=judge_dir)
        (caught if _fired(findings, planted.check) else missed).append(
            f"{planted.check}: {planted.describe}"
        )
    (caught if _claim_hygiene_fires(repo_root) else missed).append(
        "claim-hygiene: a page in the judge directory carries a forbidden claim"
    )
    (caught if _size_model_refuses() else missed).append(
        "bound-length-model: a 4096-dimension literal overflows the statement cap"
    )
    return SelfTestResult(caught=tuple(caught), missed=tuple(missed))
