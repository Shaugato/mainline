#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fail the build when a recall metric appears in prose without its interval.

    python scripts/recall/no_bare_point_estimates.py            # docs/, README.md, the deck
    python scripts/recall/no_bare_point_estimates.py --paths X  # anything else
    python scripts/recall/no_bare_point_estimates.py --selftest # prove the rule bites

Why this exists
---------------
``Retro-Recall@3 = 0.91`` is not a fact. With ~200 adjudicated pairs the interval is
wide, and a point estimate that escapes into a README, a deck or a customer conversation
acquires a confidence the sample never supported. Inside the code
:class:`trappoint_recall.eval.measurement.Measurement` makes dropping the interval
impossible; prose has no type system, so it gets a grep.

What counts as acceptable
-------------------------
A number adjacent to a recall metric is acceptable when it is any of:

* **a target or a floor** — introduced by ``>=``, ``<=``, ``<``, ``>``, "at least",
  "target", "floor", "ceiling", "threshold", "cap", "tau". A floor is a commitment,
  not a measurement, and commitments have no confidence interval.
* **accompanied by an interval** — the line also carries ``[lo, hi]``, "Wilson", "CI",
  "lower bound", "LB" or a plus/minus sign.
* **structural** — a cut-off in ``@k``, a sample size ``n=...``, a year, a section
  reference.
* **explicitly allowed** — the line, or the line above it, carries
  ``no-bare-point-estimates: allow - <reason>``. The reason is mandatory: an
  unexplained exemption is how the rule dies.

Anything else is a bare point estimate and fails the build with a file:line:column.

Standard library only, so the check runs in any lane, including one that has installed
nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

DEFAULT_TARGETS: Final[tuple[str, ...]] = ("README.md", "docs")
"""docs/ and README.md, per the rule's charter. The deck lives under docs/ when it exists."""

TEXT_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".markdown", ".rst", ".txt", ".html"})

# Metric vocabulary. Deliberately explicit: a lexicon of "any number near any word"
# would produce noise nobody reads, and a rule nobody reads is not a control.
METRIC_PATTERN: Final = re.compile(
    r"""
    (?<![\w-])                      # not inside an identifier: trappoint-recall, recall_policy
    (?P<metric>
        retro[-\s]?recall(?:\s*@\s*\d+)?
      | recall\s*@\s*\d+
      | recall\s+at\s+\d+
      | p\s*@\s*block
      | precision\s*@\s*block
      | n?dcg(?:\s*@\s*\d+)?
      | \bmrr\b
      | mean\s+reciprocal\s+rank
      | nuisance\s+rate
      | mean\s+blocking\s+checks(?:\s*(?:/|per)\s*permit)?
      | blocking\s+checks\s*(?:/|per)\s*permit
      | \bprecision\b
      | \brecall\b
    )
    (?![\w-])                       # ditto on the right: recall-taxonomy-lmb, recall_run
    """,
    re.IGNORECASE | re.VERBOSE,
)

# The lookarounds exclude version strings and identifiers: Apache-2.0, FSL-1.1-ALv2,
# v26.2, K-401. A number welded to a hyphen or a letter is not a measurement.
NUMBER_PATTERN: Final = re.compile(
    r"(?<![\w.@/-])(?P<number>\d{1,3}(?:\.\d+)?)(?![\w/-])\s*(?P<pct>%)?"
)

INTERVAL_MARKERS: Final[tuple[str, ...]] = (
    "wilson",
    "lower bound",
    "upper bound",
    " lb ",
    "(lb",
    "lb ",
    "confidence interval",
    " ci ",
    "(ci",
    "95%",
    "interval",
    "±",
    "+/-",
)

TARGET_MARKERS: Final[tuple[str, ...]] = (
    ">=",
    "<=",
    "≥",
    "≤",
    ">",
    "<",
    "at least",
    "at most",
    "below",
    "above",
    "under",
    "over",
    "beneath",
    "sits below",
    "drops below",
    "falls below",
    "no fewer than",
    "no more than",
    "target",
    "floor",
    "ceiling",
    "threshold",
    "cap ",
    "cap of",
    "hard cap",
    "budget",
    "tau",
    "τ",
    "gate on",
    "gated on",
    "must reach",
    "required",
)

ALLOW_PATTERN: Final = re.compile(
    r"no-bare-point-estimates:\s*allow\s*[-–—:]\s*(?P<reason>\S.*?)\s*(?:-->|\*/|$)",
    re.IGNORECASE,
)

FENCE_PATTERN: Final = re.compile(r"^\s*(```|~~~)")

INTERVAL_BRACKET: Final = re.compile(r"\[\s*\d+(?:\.\d+)?\s*[,;]\s*\d+(?:\.\d+)?\s*\]")

STRUCTURAL_PREFIX: Final = re.compile(r"(?:@|n\s*=|k\s*=|§|section\s|v|MI|G)\s*$", re.IGNORECASE)

YEAR_RANGE: Final = range(1900, 2101)


@dataclass(frozen=True)
class Violation:
    """One bare point estimate, located precisely enough to fix without searching."""

    path: Path
    line_number: int
    column: int
    metric: str
    number: str
    line: str

    def render(self, *, root: Path) -> str:
        try:
            shown = self.path.relative_to(root)
        except ValueError:
            shown = self.path
        return (
            f"{shown}:{self.line_number}:{self.column}: bare point estimate "
            f"{self.number!r} beside metric {self.metric!r}\n"
            f"    {self.line.strip()}\n"
            f"    fix: quote the interval (e.g. '{self.number} [lo, hi], 95% Wilson, n=N'), "
            f"state it as a target ('>= {self.number}'), or add "
            f"'no-bare-point-estimates: allow - <reason>'"
        )


def _is_allowed_line(line: str, previous: str) -> bool:
    return bool(ALLOW_PATTERN.search(line) or ALLOW_PATTERN.search(previous))


def _has_interval(line: str) -> bool:
    lowered = f" {line.lower()} "
    if INTERVAL_BRACKET.search(line):
        return True
    return any(marker in lowered for marker in INTERVAL_MARKERS)


def _is_target(line: str, start: int) -> bool:
    """True when the number at ``start`` is introduced as a target rather than a result."""
    window = line[max(0, start - 24) : start].lower()
    return any(marker in window for marker in TARGET_MARKERS)


def _is_structural(line: str, start: int, number: str, is_percent: bool) -> bool:
    if STRUCTURAL_PREFIX.search(line[max(0, start - 6) : start]):
        return True
    # An ordered-list marker at the head of a line: "1. The bet may lose."
    if line[:start].strip() == "" and line[start + len(number) :].startswith((". ", ") ", ".	")):
        return True
    if not is_percent and "." not in number:
        value = int(number)
        if value in YEAR_RANGE:
            return True
        # Bare small integers next to a metric are cut-offs and counts ("top 3",
        # "3 blocking checks"), not point estimates. A precision of "3" is not a thing.
        if value > 1:
            return True
    return False


def scan_text(path: Path, text: str) -> list[Violation]:
    """Return every bare point estimate in ``text``. Fenced code blocks are skipped."""
    violations: list[Violation] = []
    in_fence = False
    previous = ""
    for line_number, line in enumerate(text.splitlines(), start=1):
        if FENCE_PATTERN.match(line):
            in_fence = not in_fence
            previous = line
            continue
        if in_fence:
            previous = line
            continue
        metric_spans = [
            (m.group("metric"), m.start(), m.end()) for m in METRIC_PATTERN.finditer(line)
        ]
        if not metric_spans:
            previous = line
            continue
        if _is_allowed_line(line, previous) or _has_interval(line):
            previous = line
            continue
        for number_match in NUMBER_PATTERN.finditer(line):
            start = number_match.start("number")
            number = number_match.group("number")
            is_percent = bool(number_match.group("pct"))
            # Skip numbers that belong to a metric token itself, e.g. the 3 in Recall@3.
            if any(m_start <= start < m_end for _, m_start, m_end in metric_spans):
                continue
            if _is_structural(line, start, number, is_percent):
                continue
            if _is_target(line, start):
                continue
            nearest = min(
                metric_spans,
                key=lambda span: min(abs(start - span[1]), abs(start - span[2])),
            )
            distance = min(abs(start - nearest[1]), abs(start - nearest[2]))
            if distance > 80:
                continue
            violations.append(
                Violation(
                    path=path,
                    line_number=line_number,
                    column=start + 1,
                    metric=nearest[0].strip(),
                    number=number + ("%" if is_percent else ""),
                    line=line,
                )
            )
        previous = line
    return violations


def iter_files(targets: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            if target.suffix.lower() in TEXT_SUFFIXES:
                files.append(target)
        elif target.is_dir():
            files.extend(
                p
                for p in sorted(target.rglob("*"))
                if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES
            )
    return files


SELFTEST_CASES: Final[tuple[tuple[str, bool], ...]] = (
    ("Retro-Recall@3 on severity-5 is 0.91.", True),
    ("P@block reached 0.82 on the adjudicated subset.", True),
    ("The nuisance rate was 2.4% over the replay.", True),
    ("Precision of 0.75 was observed.", True),
    ("Retro-Recall@3 >= 0.90 is the release floor.", False),
    ("Target: P@block >= 0.75 at Retro-Recall@3 >= 0.90.", False),
    ("Retro-Recall@3 = 0.91 [0.84, 0.95], 95% Wilson, n=214.", False),
    ("P@block 0.82, Wilson lower bound 0.71, n=204.", False),
    ("nuisance rate 0.024 (95% CI [0.008, 0.061])", False),
    ("Recall@10 came back 0.9 <!-- no-bare-point-estimates: allow - worked example -->", False),
    ("The nuisance ceiling is 3% and a rule that breaches it is rejected.", False),
    ("Recall was measured over 250 permits per week.", False),
)
"""Each case is (line, is_a_violation). The rule is only a control if it bites and only
usable if it does not bite the sentences the design documents actually contain."""


def run_selftest() -> int:
    failures: list[str] = []
    for line, expected in SELFTEST_CASES:
        found = bool(scan_text(Path("<selftest>"), line))
        if found != expected:
            failures.append(
                f"  expected {'a violation' if expected else 'no violation'}, got "
                f"{'a violation' if found else 'none'}: {line!r}"
            )
    if failures:
        sys.stderr.write("no_bare_point_estimates selftest FAILED:\n" + "\n".join(failures) + "\n")
        return 1
    sys.stdout.write(f"selftest ok: {len(SELFTEST_CASES)} cases\n")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="no_bare_point_estimates",
        description=(
            "Fail when a recall metric appears in docs/, README.md or the deck without "
            "an interval alongside it."
        ),
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        type=Path,
        default=None,
        help=f"files or directories to scan (default: {' '.join(DEFAULT_TARGETS)})",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root, used to shorten reported paths",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="check the rule against its own cases"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    root: Path = args.root.resolve()
    targets = (
        [p if p.is_absolute() else root / p for p in args.paths]
        if args.paths
        else [root / t for t in DEFAULT_TARGETS]
    )
    files = iter_files(targets)
    if not files:
        sys.stderr.write(
            "no_bare_point_estimates: no files matched. Refusing to pass on an empty scan: "
            "a check that scanned nothing has checked nothing.\n"
        )
        return 2

    violations: list[Violation] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        violations.extend(scan_text(path, text))

    if violations:
        sys.stderr.write(
            f"no_bare_point_estimates: {len(violations)} bare point estimate(s) across "
            f"{len(files)} file(s)\n\n"
        )
        for violation in violations:
            sys.stderr.write(violation.render(root=root) + "\n\n")
        sys.stderr.write(
            "Every recall number published outside the code must carry its interval, its "
            "sample size and its split policy. See packages/trappoint-recall/README.md.\n"
        )
        return 1

    sys.stdout.write(f"no_bare_point_estimates: clean across {len(files)} file(s)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
