#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim.
# I: QA-RATCHET-1 — the repository's lint debt is a counted, published number that may
#    fall and may not rise. A rule/tree pair recorded at 0 is a hard gate.
# RATIONALE: `ruff check .` reports findings in the high hundreds and
#    `ruff format --check .` around 240 unformatted files (the live totals are in
#    qa/ruff-ratchet.json under `lint.total` and `format.unformatted_files`). Fixing
#    them in one wave would rewrite files owned by nine other workers and every domain
#    lead, and would make the wave unmergeable. Deleting the rules would be a lie. The
#    third option is the honest one: freeze the real number per rule per tree, publish
#    it, and refuse an increase. A truthful large number that cannot grow beats a
#    fabricated 0. (Quality-repair plan, decision D4.)
"""Counted lint/format ratchet for the MAINLINE repository.

Runs `ruff check` and `ruff format --check`, buckets every finding by
(rule code, tree), and compares the result against `qa/ruff-ratchet.json`.

    increase  -> exit 1, naming the rule, the tree, the old count and the new count
    decrease  -> exit 0; `--update` rewrites the baseline downwards
    unchanged -> exit 0

A (rule, tree) pair that is absent from the baseline has an implicit count of 0, so a
rule that has never fired in a tree is a hard gate there the first time it does.

The script NEVER writes to a source file. It does not run `ruff format` (without
`--check`) and it does not run `ruff check --fix`. Its only possible write is
`qa/ruff-ratchet.json`, and only under `--update` or `--rebaseline`.

Exit codes: 0 clean, 1 ratchet regression, 2 tooling/usage failure.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "qa" / "ruff-ratchet.json"
SCHEMA = "mainline.qa.ruff-ratchet/1"

# Ordered longest-intent-first: the first rule whose test passes names the tree.
# `other/` is the deliberate catch-all — `skills/`, `infra/`, `spec/` and root-level
# modules land there rather than being silently dropped from the count.
TREES: tuple[str, ...] = (
    "packages/trappoint-*",
    "packages/mainline-*",
    "verticals/",
    "tests/",
    "scripts/",
    "other/",
)


@dataclass(frozen=True)
class Measurement:
    """One observation of the tree: lint findings per (code, tree), and unformatted files."""

    lint_counts: dict[str, dict[str, int]]
    lint_total: int
    fmt_by_tree: dict[str, int]
    fmt_total: int


_TOP_LEVEL = {"verticals": "verticals/", "tests": "tests/", "scripts": "scripts/"}


def classify(rel_posix: str) -> str:
    """Map a repo-relative POSIX path to exactly one tree name from TREES."""
    parts = rel_posix.split("/")
    head = parts[0]
    if head == "packages":
        sub = parts[1] if len(parts) > 1 else ""
        for prefix in ("trappoint-", "mainline-"):
            if sub.startswith(prefix):
                return f"packages/{prefix}*"
        return "other/"
    return _TOP_LEVEL.get(head, "other/")


def find_ruff() -> str:
    """Locate the ruff the repository actually uses, preferring the venv over PATH."""
    candidates = [
        REPO_ROOT / ".venv" / "Scripts" / "ruff.exe",
        REPO_ROOT / ".venv" / "bin" / "ruff",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("ruff")
    if found:
        return found
    msg = (
        "ruff not found. Looked for .venv/Scripts/ruff.exe, .venv/bin/ruff, then PATH. "
        "Install the dev group, or put ruff on PATH."
    )
    raise RuntimeError(msg)


def run(ruff: str, args: list[str]) -> tuple[int, str]:
    """Run ruff and return (returncode, stdout decoded as UTF-8).

    ruff emits U+2018-class punctuation in its messages; on Windows the default
    console codepage is cp1252 and decoding blows up on the first curly quote. The
    decode is pinned to UTF-8 here on purpose.
    """
    proc = subprocess.run(  # fixed argv, no shell; ruff path resolved by find_ruff()
        [ruff, *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        check=False,
    )
    out = proc.stdout.decode("utf-8", errors="replace")
    if proc.returncode > 1:
        err = proc.stderr.decode("utf-8", errors="replace")
        msg = f"ruff {' '.join(args)} failed with exit {proc.returncode}:\n{err.strip()}"
        raise RuntimeError(msg)
    return proc.returncode, out


def ruff_version(ruff: str) -> str:
    """Return the bare version string, e.g. '0.16.1'."""
    _, out = run(ruff, ["--version"])
    return out.strip().removeprefix("ruff").strip()


def rel(filename: str) -> str:
    """Repo-relative POSIX path for a ruff `filename` field (absolute, Windows-slashed)."""
    path = Path(filename)
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def measure_lint(ruff: str) -> tuple[dict[str, dict[str, int]], int]:
    """Return ({code: {tree: count}}, total)."""
    _, out = run(ruff, ["check", ".", "--output-format", "json"])
    findings: list[dict[str, Any]] = json.loads(out) if out.strip() else []
    counts: dict[str, dict[str, int]] = {}
    for finding in findings:
        code = finding.get("code") or "UNKNOWN"
        tree = classify(rel(finding["filename"]))
        counts.setdefault(code, {})[tree] = counts.setdefault(code, {}).get(tree, 0) + 1
    return counts, len(findings)


def measure_format(ruff: str) -> tuple[dict[str, int], int]:
    """Return ({tree: unformatted files}, total unformatted files). Never reformats."""
    _, out = run(ruff, ["format", "--check", "--output-format", "json", "."])
    diagnostics: list[dict[str, Any]] = json.loads(out) if out.strip() else []
    files = {rel(d["filename"]) for d in diagnostics}
    by_tree: dict[str, int] = {}
    for path in files:
        tree = classify(path)
        by_tree[tree] = by_tree.get(tree, 0) + 1
    return by_tree, len(files)


def sort_counts(counts: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """Sort by descending total then code, and trees in TREES order, for a stable diff."""
    order = {tree: i for i, tree in enumerate(TREES)}
    ranked = sorted(counts.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
    return {
        code: dict(sorted(trees.items(), key=lambda kv: order.get(kv[0], 99)))
        for code, trees in ranked
    }


def merge_declared_zeros(
    counts: dict[str, dict[str, int]],
    baseline: dict[str, Any],
) -> dict[str, dict[str, int]]:
    """Materialise the hard gates as explicit `0` entries so they stay visible.

    Two sources, both `setdefault` so a MEASURED count always wins over a declared
    zero — a rule that has started firing is never recorded as 0:

      1. `policy.zero_tolerance.at_zero_today` — the load-bearing families that are
         genuinely at zero in `packages/trappoint-*` today. Declaring them here is what
         turns "the preamble says these matter" into "the first one fails the build".
      2. any `0` already written into `lint.rules` by a previous run.

    Ruff reports nothing for a rule that does not fire, so a measured-only baseline
    would silently drop every hard gate the moment the tree became clean.
    """
    merged = {code: dict(trees) for code, trees in counts.items()}
    policy = baseline.get("policy", {}).get("zero_tolerance", {})
    gated_tree = policy.get("tree")
    if gated_tree:
        for code in policy.get("at_zero_today", []):
            merged.setdefault(code, {}).setdefault(gated_tree, 0)
    for code, trees in baseline.get("lint", {}).get("rules", {}).items():
        for tree, value in trees.items():
            if value == 0:
                merged.setdefault(code, {}).setdefault(tree, 0)
    return merged


def compare(
    measured: dict[str, dict[str, int]],
    recorded: dict[str, dict[str, int]],
    label: str,
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements) as human-readable lines."""
    regressions: list[str] = []
    improvements: list[str] = []
    codes = sorted(set(measured) | set(recorded))
    for code in codes:
        trees = sorted(set(measured.get(code, {})) | set(recorded.get(code, {})))
        for tree in trees:
            new = measured.get(code, {}).get(tree, 0)
            old = recorded.get(code, {}).get(tree, 0)
            if new > old:
                gate = " [HARD GATE: baseline is 0]" if old == 0 else ""
                regressions.append(
                    f"{label} REGRESSION  rule={code}  tree={tree}  "
                    f"baseline={old}  measured={new}  (+{new - old}){gate}"
                )
            elif new < old:
                improvements.append(
                    f"{label} improved     rule={code}  tree={tree}  "
                    f"baseline={old}  measured={new}  (-{old - new})"
                )
    return regressions, improvements


def compare_format(
    measured: dict[str, int],
    total: int,
    baseline: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Ratchet the formatter: total first, then per tree so a regression is attributable."""
    recorded = baseline.get("format", {})
    rec_total = int(recorded.get("unformatted_files", 0))
    regressions: list[str] = []
    improvements: list[str] = []
    if total > rec_total:
        regressions.append(
            f"FORMAT REGRESSION  rule=unformatted  tree=<repo>  "
            f"baseline={rec_total}  measured={total}  (+{total - rec_total})"
        )
    elif total < rec_total:
        improvements.append(
            f"FORMAT improved     rule=unformatted  tree=<repo>  "
            f"baseline={rec_total}  measured={total}  (-{rec_total - total})"
        )
    rec_by_tree = recorded.get("unformatted_by_tree", {})
    per_tree_r, per_tree_i = compare(
        {"unformatted": measured},
        {"unformatted": {k: int(v) for k, v in rec_by_tree.items()}},
        "FORMAT",
    )
    return regressions + per_tree_r, improvements + per_tree_i


def build_baseline(
    version: str,
    lint_counts: dict[str, dict[str, int]],
    lint_total: int,
    fmt_by_tree: dict[str, int],
    fmt_total: int,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the on-disk baseline document, preserving hand-written policy prose."""
    prior = previous or {}
    order = {tree: i for i, tree in enumerate(TREES)}
    lint_by_tree: dict[str, int] = {}
    for trees in lint_counts.values():
        for tree, n in trees.items():
            lint_by_tree[tree] = lint_by_tree.get(tree, 0) + n
    return {
        "schema": SCHEMA,
        "note": prior.get(
            "note",
            "Honest counts, not aspirations. See qa/README.md. Regenerate with "
            "`python scripts/qa/ruff_ratchet.py --update`.",
        ),
        "generated_utc": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ruff_version": version,
        "ruff_config": "ruff.toml",
        "commands": {
            "lint": "ruff check . --output-format json",
            "format": "ruff format --check --output-format json .",
        },
        "trees": list(TREES),
        "policy": prior.get("policy", {}),
        "lint": {
            "total": lint_total,
            "total_by_tree": dict(
                sorted(lint_by_tree.items(), key=lambda kv: order.get(kv[0], 99))
            ),
            "rules": sort_counts(lint_counts),
        },
        "format": {
            "unformatted_files": fmt_total,
            "unformatted_by_tree": dict(
                sorted(fmt_by_tree.items(), key=lambda kv: order.get(kv[0], 99))
            ),
        },
    }


def load_baseline(path: Path) -> dict[str, Any]:
    if not path.is_file():
        msg = f"baseline not found: {path}. Create it with --rebaseline."
        raise RuntimeError(msg)
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ruff_ratchet",
        description="Counted ruff ratchet: a count may fall, it may not rise.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite the baseline DOWNWARDS when counts have improved (never upwards)",
    )
    parser.add_argument(
        "--rebaseline",
        action="store_true",
        help="write whatever is measured, INCLUDING increases; a deliberate act, justify it",
    )
    parser.add_argument(
        "--allow-ruff-version-drift",
        action="store_true",
        help="proceed when the installed ruff differs from the one the baseline was taken with",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=BASELINE_PATH,
        help=f"baseline path (default {BASELINE_PATH.relative_to(REPO_ROOT).as_posix()})",
    )
    parser.add_argument("--quiet", action="store_true", help="print only regressions")
    return parser.parse_args(argv)


def check_version(baseline: dict[str, Any], version: str, args: argparse.Namespace) -> int:
    """A ratchet taken with a different ruff is not a ratchet. Refuse unless told to."""
    recorded = baseline.get("ruff_version")
    if not recorded or recorded == version:
        return 0
    print(
        f"RUFF VERSION DRIFT  baseline={recorded}  installed={version}\n"
        "  Rule sets and default fixes differ between ruff releases, so the counts are "
        "not comparable.\n"
        "  Re-take the baseline with --rebaseline, or pass --allow-ruff-version-drift "
        "to compare anyway."
    )
    if not (args.rebaseline or args.allow_ruff_version_drift):
        return 2
    return 0


def load_or_empty(args: argparse.Namespace) -> dict[str, Any]:
    """Load the baseline; return {} only when --rebaseline is bootstrapping a new file."""
    if args.baseline.is_file():
        return load_baseline(args.baseline)
    if args.rebaseline:
        return {}
    return load_baseline(args.baseline)  # raises, with the remedy in the message


def save(args: argparse.Namespace, version: str, m: Measurement, baseline: dict[str, Any]) -> None:
    doc = build_baseline(
        version,
        merge_declared_zeros(m.lint_counts, baseline),
        m.lint_total,
        m.fmt_by_tree,
        m.fmt_total,
        baseline,
    )
    write_baseline(args.baseline, doc)


def seed(args: argparse.Namespace, version: str, m: Measurement, baseline: dict[str, Any]) -> int:
    """Bootstrap path: no counts on disk yet.

    Comparing against nothing would report every rule in the repository as a
    regression, which is noise rather than a finding.
    """
    if not args.rebaseline:
        print(f"ruff_ratchet: {args.baseline} carries no `lint` block. Seed it with --rebaseline.")
        return 2
    save(args, version, m, baseline)
    print(
        f"ruff_ratchet: seeded {args.baseline} with ruff {version}, "
        f"{m.lint_total} lint findings, {m.fmt_total} unformatted files."
    )
    return 0


def print_refusal(regressions: list[str]) -> None:
    print(f"\nruff_ratchet: REFUSED - {len(regressions)} ratchet regression(s).")
    for line in regressions:
        print("  " + line)
    print(
        "\n  Fix the finding, or - if the increase is genuinely correct - say so in review\n"
        "  and re-take the baseline with `python scripts/qa/ruff_ratchet.py --rebaseline`.\n"
        "  Raising the number is allowed. Raising it silently is not."
    )


def verdict(
    args: argparse.Namespace, version: str, m: Measurement, baseline: dict[str, Any]
) -> int:
    """Compare, report, and (only under --update/--rebaseline) rewrite the baseline."""
    recorded: dict[str, dict[str, int]] = {
        code: {tree: int(n) for tree, n in trees.items()}
        for code, trees in baseline.get("lint", {}).get("rules", {}).items()
    }
    regressions, improvements = compare(m.lint_counts, recorded, "LINT")
    fmt_reg, fmt_imp = compare_format(m.fmt_by_tree, m.fmt_total, baseline)
    regressions += fmt_reg
    improvements += fmt_imp

    if not args.quiet:
        header = f"ruff {version}  |  lint findings {m.lint_total}"
        print(f"{header}  |  unformatted files {m.fmt_total}")
        for line in improvements:
            print("  " + line)

    if regressions:
        print_refusal(regressions)
        if not args.rebaseline:
            return 1

    if args.update and not (improvements or regressions):
        print("\nruff_ratchet: nothing to tighten; baseline unchanged.")
        return 0

    if args.update or args.rebaseline:
        save(args, version, m, baseline)
        print(f"\nruff_ratchet: wrote {args.baseline}")
        return 0

    if not args.quiet:
        tail = (
            f"; {len(improvements)} entries can be tightened with --update" if improvements else ""
        )
        print(f"\nruff_ratchet: OK - no rule/tree count increased{tail}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        ruff = find_ruff()
        version = ruff_version(ruff)
        baseline = load_or_empty(args)
        lint_counts, lint_total = measure_lint(ruff)
        fmt_by_tree, fmt_total = measure_format(ruff)
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"ruff_ratchet: {exc}")
        return 2

    m = Measurement(lint_counts, lint_total, fmt_by_tree, fmt_total)
    if baseline and check_version(baseline, version, args) == 2:
        return 2
    if "lint" not in baseline:
        return seed(args, version, m, baseline)
    return verdict(args, version, m, baseline)


if __name__ == "__main__":
    sys.exit(main())
