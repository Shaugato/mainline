#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim. It reads `.github/workflows/` as raw text.
# I: QA-RATCHET-3 (Contract A) — every pytest invocation in `.github/workflows/` declares
#    which side of the cluster line it is on, with a `# trappoint:pytest-lane=` comment.
#    The number that declare nothing is a published ceiling that may only FALL, and a
#    declaration that contradicts its own `--crdb=` flag is a hard failure.
# RATIONALE: measured 2026-08-13 by the ci-runs-cluster lead, 30 of the then-32 pytest
#    invocations in this directory passed no `--crdb` mode at all and therefore ran at the
#    testkit default `auto` — "reuse a cluster that answers, start one if none does". A
#    lane whose cluster posture is implicit cannot be audited: nothing in the file says
#    whether the step reused the shared node, started its own container, or ran hermetic
#    and skipped every cluster-backed test while exiting 0. `ci.yml` names this program in
#    its checker registry and asserts exactly this contract of it; until now the program
#    did not exist, so the assertion was a claim the lane had silently stopped making.
"""Contract A: every pytest step says which side of the cluster line it is on.

Reads every `.github/workflows/*.yml` as RAW TEXT — the marker is a COMMENT and PyYAML
discards comments; these files are roughly 60% comment by volume — and pairs each pytest
invocation with the `# trappoint:pytest-lane=` marker above it.

    an unknown marker value                                    -> exit 1, by file:line
    `unlanded` with no non-empty reason="…"                     -> exit 1, by file:line
    a marker with no pytest invocation under it                 -> exit 1, by file:line
    a marker that contradicts the invocation's own `--crdb=`    -> exit 1, by file:line
    a lane's UNDECLARED count above its ceiling                 -> exit 1, by lane
    a lane's UNDECLARED count BELOW its ceiling                 -> exit 1, demanding the
                                                                   ceiling be lowered
    fewer invocations or markers than the floor                 -> exit 1, scanner blind
    anything else                                               -> exit 0

WHY A DECREASE IS ALSO A FAILURE, unlike `scripts/qa/ruff_ratchet.py`. A ruff count moves
with every unrelated edit across hundreds of files, so slack there is noise. This census
has 38 items in total and moves only when a human deliberately edits a workflow step. A
ceiling left standing above its measured value is a ratchet that refuses nothing — the
exact defect this checker was written to end — so slack is reported as a finding with the
literal replacement block, and a human pastes it. This program never writes to a file.

The invocation scanner is IMPORTED from `scripts/qa/skip_ratchet.py` on purpose. Two
programs in the same registry answering "what is a pytest invocation?" differently is how
one of them goes quietly blind; there is one definition and both checkers use it.

Exit codes: 0 clean, 1 contract/ratchet failure, 2 tooling or usage failure.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skip_ratchet import WORKFLOWS, Invocation, scan_workflows

REPO_ROOT = Path(__file__).resolve().parents[2]

# The marker, as Contract A fixes it (docs/leads/ci-runs-cluster-plan.md §3.0). It is a
# COMMENT, either inside the step's `run:` block or in the comment block immediately above
# the step's `- name:`, which is why both the search and the binding below are line-based.
MARKER = re.compile(r"#\s*trappoint:pytest-lane=([A-Za-z][A-Za-z0-9_-]*)(?P<rest>[^\n]*)")
REASON = re.compile(r'reason\s*=\s*"([^"]*)"')
# `--crdb=none` and `--crdb none` both; only a LITERAL mode is cross-checked, because a
# mode that arrives through `${{ }}` or a shell variable is not knowable from the text.
CRDB = re.compile(r"--crdb[= ]([A-Za-z]+)")

LANES: dict[str, str | None] = {
    # marker value -> the literal `--crdb` mode it claims, or None when the contract does
    # not fix one. Taken verbatim from Contract A; do not add a value without amending it.
    "hermetic": "none",
    "cluster": "reuse",
    "spawn": "auto",
    "unlanded": None,
}

# ---------------------------------------------------------------------------------------
# MEASURED, not chosen. Reproduce with `python scripts/qa/check_pytest_lanes.py --measure`.
#
# 2026-08-14, tree at HEAD 538193b plus this wave's uncommitted work:
#   38 pytest invocations in .github/workflows/, 12 declared, 26 undeclared.
#   Cross-checked against a dumb raw grep: 130 lines in the directory contain the word
#   `pytest`; every non-comment one the scanner did NOT claim is prose, an `echo`, a
#   `pip install`, or a backslash continuation of a block the scanner already claimed
#   (`mutation-ratchet.yml:388`, `nightly-differential.yml:341`). The scanner has no blind
#   spot on this tree, which is the only reason a floor drawn under it means anything.
#
# The ceiling is per LANE, not a single total, and that is the point: a bare total of 26
# would let somebody delete a marker from `ci.yml` and add one in `schema.yml` with no net
# change. A per-lane count catches that.
# ---------------------------------------------------------------------------------------
UNDECLARED_CEILING: dict[str, int] = {
    "boundary.yml#ci-greps": 1,
    "boundary.yml#e1-iam": 1,
    "boundary.yml#e2-network": 1,
    "boundary.yml#e3-code": 1,
    "boundary.yml#e4-egress": 1,
    "boundary.yml#fleet-matrix": 1,
    "boundary.yml#package-unit-tests": 1,
    "custody-chain.yml#algebra-and-verifier": 3,
    "custody-chain.yml#nemesis": 2,
    "custody-chain.yml#policy-and-spec": 1,
    "custody-chain.yml#sequencer-concurrency": 1,
    "db-schema.yml#catalogue": 2,
    "mutation-ratchet.yml#ratchet": 1,
    "nightly-differential.yml#concurrency-64": 1,
    "nightly-differential.yml#differential": 2,
    "release-proof.yml#prove": 2,
    "schema.yml#coverage-artefacts": 1,
    "schema.yml#gate-source": 1,
    "schema.yml#unweld": 1,
    "supply-chain.yml#gate-svc-has-no-model-sdk": 1,
}

# `unlanded` is Contract A's escape hatch: "known to skip, no lane runs them". It is
# honest and it is declared, but it is still a pytest step nobody executes, so it gets its
# own ceiling. Measured today: ZERO invocations use it. Without this line, driving
# UNDECLARED_CEILING to nothing by marking all 26 `unlanded` would read as a win.
UNLANDED_CEILING = 0

# Floors. A checker that finds nothing passes trivially; these are what stop that. Both
# were measured on this tree in the same sitting as the ceiling above. A floor may RISE
# with a fresh measurement and may never FALL to meet a disappointing run — if a workflow
# is legitimately deleted, that is a conversation, not an edit to this line.
INVOCATION_FLOOR = 38
DECLARED_FLOOR = 12

# The furthest a real marker sits above the invocation it governs is 33 lines
# (`cluster-tests.yml:258` governing the pytest at line 291 — the marker is in the comment
# block above the step's `- name:`, which Contract A permits). 40 is that measurement plus
# headroom; beyond it a marker is reported as an ORPHAN rather than silently annexing some
# distant step.
MARKER_REACH = 40


@dataclass(frozen=True)
class Marker:
    """One `# trappoint:pytest-lane=` comment, and where it sits."""

    file: str
    line: int
    value: str
    reason: str


@dataclass
class Finding:
    """One refusal, with the place that produced it."""

    where: str
    text: str

    def __str__(self) -> str:
        return f"{self.where}: {self.text}"


@dataclass
class Report:
    """Everything one pass over the directory established."""

    invocations: list[Invocation] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    bound: dict[tuple[str, int], Marker] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    @property
    def declared(self) -> list[Invocation]:
        return [i for i in self.invocations if (i.file, i.line) in self.bound]

    @property
    def undeclared(self) -> list[Invocation]:
        return [i for i in self.invocations if (i.file, i.line) not in self.bound]

    def undeclared_by_lane(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for inv in self.undeclared:
            counts[inv.lane] = counts.get(inv.lane, 0) + 1
        return counts

    def unlanded_count(self) -> int:
        return sum(1 for m in self.bound.values() if m.value == "unlanded")


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def read_markers(root: Path) -> list[Marker]:
    """Every lane marker in the directory, as raw text. No YAML parser touches this."""
    out: list[Marker] = []
    for path in sorted(root.glob("*.yml")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = MARKER.search(line)
            if match is None:
                continue
            reason_match = REASON.search(match.group("rest"))
            reason = reason_match.group(1).strip() if reason_match else ""
            out.append(Marker(path.name, n, match.group(1), reason))
    return out


def bind(markers: list[Marker], invocations: list[Invocation]) -> dict[tuple[str, int], Marker]:
    """Bind each marker to the FIRST pytest invocation below it, within `MARKER_REACH`.

    One marker governs at most one invocation. Two steps that both invoke pytest therefore
    need two markers — which is what stops a single declaration at the top of a job from
    covering a step somebody added underneath it three months later.
    """
    by_file: dict[str, list[Invocation]] = {}
    for inv in invocations:
        by_file.setdefault(inv.file, []).append(inv)
    for items in by_file.values():
        items.sort(key=lambda i: i.line)

    taken: dict[tuple[str, int], Marker] = {}
    for marker in sorted(markers, key=lambda m: (m.file, m.line)):
        for inv in by_file.get(marker.file, []):
            key = (inv.file, inv.line)
            if inv.line <= marker.line or key in taken:
                continue
            if inv.line - marker.line <= MARKER_REACH:
                taken[key] = marker
            break
    return taken


def analyse(root: Path) -> Report:
    """One pass: scan, bind, and record every structural refusal. Pure; no ratchets."""
    report = Report(invocations=scan_workflows(root), markers=read_markers(root))
    report.bound = bind(report.markers, report.invocations)
    check_marker_values(report)
    check_orphans(report)
    check_posture(report)
    return report


# ---------------------------------------------------------------------------------------
# The structural contract
# ---------------------------------------------------------------------------------------
def check_marker_values(report: Report) -> None:
    """A marker must carry a value Contract A fixes, and `unlanded` must carry a reason."""
    for marker in report.markers:
        where = f"{marker.file}:{marker.line}"
        if marker.value not in LANES:
            report.findings.append(
                Finding(
                    where,
                    f"`trappoint:pytest-lane={marker.value}` is not a value Contract A "
                    f"defines. It fixes exactly {sorted(LANES)}. A marker nobody can read "
                    f"declares nothing.",
                )
            )
            continue
        if marker.value == "unlanded" and not marker.reason:
            report.findings.append(
                Finding(
                    where,
                    'an `unlanded` marker must carry reason="<one sentence>". `unlanded` '
                    "says this step's cluster-backed tests are known to skip and no lane "
                    "runs them; without the sentence it is an unexplained hole.",
                )
            )


def check_orphans(report: Report) -> None:
    """A marker that governs no invocation is a declaration about nothing."""
    governed = {(m.file, m.line) for m in report.bound.values()}
    for marker in report.markers:
        if (marker.file, marker.line) in governed:
            continue
        report.findings.append(
            Finding(
                f"{marker.file}:{marker.line}",
                f"`trappoint:pytest-lane={marker.value}` has no pytest invocation within "
                f"{MARKER_REACH} lines below it. Either the step it described was deleted "
                f"and the marker outlived it, or the invocation is written in a shape the "
                f"scanner does not recognise — both are worth a human's attention, and "
                f"neither may pass as a declaration.",
            )
        )


def check_posture(report: Report) -> None:
    """A marker must agree with the invocation's own literal `--crdb=` mode."""
    for inv in report.invocations:
        marker = report.bound.get((inv.file, inv.line))
        if marker is None or marker.value not in LANES:
            continue
        found = CRDB.search(inv.command)
        mode = found.group(1) if found else None
        expected = LANES[marker.value]
        where = f"{inv.file}:{inv.line}"
        if marker.value == "unlanded":
            if mode is not None:
                report.findings.append(
                    Finding(
                        where,
                        f"declared `unlanded` at {marker.file}:{marker.line} while the "
                        f"command passes `--crdb={mode}`. An invocation that states a "
                        f"cluster posture has one; declare it.",
                    )
                )
            continue
        if mode is None:
            report.findings.append(
                Finding(
                    where,
                    f"declared `{marker.value}` at {marker.file}:{marker.line} but the "
                    f"command passes no `--crdb` mode, so it runs at the testkit default "
                    f"`auto`. The declaration and the command disagree; the command wins "
                    f"at runtime.",
                )
            )
        elif mode != expected:
            report.findings.append(
                Finding(
                    where,
                    f"declared `{marker.value}` at {marker.file}:{marker.line}, which "
                    f"Contract A binds to `--crdb={expected}`, but the command passes "
                    f"`--crdb={mode}`. Fix whichever is wrong — do not delete the marker.",
                )
            )


# ---------------------------------------------------------------------------------------
# The ratchets, and the floors that stop the whole thing passing on an empty scan
# ---------------------------------------------------------------------------------------
def check_floors(report: Report, root: Path) -> list[Finding]:
    """Refuse a pass produced by a scanner that found nothing."""
    out: list[Finding] = []
    stray = sorted(p.name for p in root.glob("*.yaml"))
    if stray:
        out.append(
            Finding(
                str(root),
                f"{stray} end in `.yaml`; this checker and `skip_ratchet.py` both glob "
                f"`*.yml` only, so those files are invisible to both. Rename them or "
                f"widen the glob in `skip_ratchet.scan_workflows`.",
            )
        )
    if len(report.invocations) < INVOCATION_FLOOR:
        out.append(
            Finding(
                str(root),
                f"{len(report.invocations)} pytest invocation(s) found against a floor of "
                f"{INVOCATION_FLOOR}. Either workflows were deleted or the scanner has "
                f"gone blind. A checker that finds nothing passes trivially, so this is a "
                f"refusal and not a notice.",
            )
        )
    if len(report.bound) < DECLARED_FLOOR:
        out.append(
            Finding(
                str(root),
                f"{len(report.bound)} declared invocation(s) against a floor of "
                f"{DECLARED_FLOOR}. Declarations may be ADDED; removing one un-audits a "
                f"lane that was audited.",
            )
        )
    return out


def check_ceiling(measured: dict[str, int], ceiling: dict[str, int]) -> list[Finding]:
    """Per-lane undeclared counts: above the ceiling refuses, below it demands a lowering."""
    out: list[Finding] = []
    for lane in sorted(set(measured) | set(ceiling)):
        now, was = measured.get(lane, 0), ceiling.get(lane, 0)
        if now > was:
            out.append(
                Finding(
                    lane,
                    f"{now} pytest invocation(s) declare no lane, against a ceiling of "
                    f"{was}. A step whose cluster posture is implicit runs at `auto` and "
                    f"nothing in the file says whether it reused the shared node, started "
                    f"a container, or skipped every cluster-backed test and exited 0. Add "
                    f"`# trappoint:pytest-lane=…` above it.",
                )
            )
        elif now < was:
            out.append(
                Finding(
                    lane,
                    f"{now} undeclared against a ceiling of {was}: the ceiling has "
                    f"{was - now} slack, which is {was - now} step(s) that could be added "
                    f"undeclared for free. Lower it — `--measure` prints the block.",
                )
            )
    return out


def check_unlanded(report: Report) -> list[Finding]:
    """`unlanded` is Contract A's declared hole; it has its own ceiling."""
    now = report.unlanded_count()
    if now > UNLANDED_CEILING:
        return [
            Finding(
                "unlanded",
                f"{now} invocation(s) declared `unlanded` against a ceiling of "
                f"{UNLANDED_CEILING}. `unlanded` is honest and it is still a pytest step "
                f"nobody executes; it may not be used to empty UNDECLARED_CEILING.",
            )
        ]
    if now < UNLANDED_CEILING:
        return [
            Finding(
                "unlanded",
                f"{now} declared `unlanded` against a ceiling of {UNLANDED_CEILING}; "
                f"lower UNLANDED_CEILING to {now}.",
            )
        ]
    return []


# ---------------------------------------------------------------------------------------
# The negative control — this checker proving, in CI, that it can still say no
# ---------------------------------------------------------------------------------------
_SYNTHETIC = """\
name: synthetic
jobs:
  good:
    steps:
      - name: a declared hermetic step
        run: |
          # trappoint:pytest-lane=hermetic
          python -m pytest tests/x.py --crdb=none -q
  bad:
    steps:
      - name: an UNDECLARED step
        run: |
          python -m pytest tests/y.py --crdb=reuse -q
      - name: a step whose marker contradicts its command
        run: |
          # trappoint:pytest-lane=hermetic
          python -m pytest tests/z.py --crdb=reuse -q
      - name: a marker nobody defined
        run: |
          # trappoint:pytest-lane=whenever
          python -m pytest tests/w.py --crdb=none -q
      - name: unlanded with no reason
        run: |
          # trappoint:pytest-lane=unlanded
          python -m pytest tests/v.py -q
  orphan:
    steps:
      - name: a marker with no pytest under it
        run: |
          # trappoint:pytest-lane=cluster
          echo "nothing here invokes anything"
"""

# label, what it is, and the phrase the finding for it must contain. One planted defect
# per row, and each must produce EXACTLY one finding — "at least one" would pass for a
# program that emitted the same finding five times.
_EXPECTED: tuple[tuple[str, str, str], ...] = (
    ("posture", "contradiction", "Contract A binds"),
    ("value", "undefined marker", "Contract A defines"),
    ("reason", "unlanded, no reason", "one sentence"),
    ("orphan", "marker governs nothing", "no pytest invocation"),
)


def self_control(verbose: bool) -> list[str]:
    """Refuse five planted defects and pass a clean tree. Returns what went wrong.

    Every other assertion about this program is of the form "it must exit non-zero". A
    program hard-wired to `return 1` would satisfy all of them and would make `ci.yml`
    permanently, unfalsifiably red — the mirror image of a green that cannot fail. So this
    control checks BOTH directions: each of the five planted defects must produce exactly
    one finding, and a directory of only well-formed steps must produce none.

    It runs on EVERY invocation, not only under `--prove`. A negative control that has to
    be asked for is a negative control nobody runs: `ci.yml` invokes this program bare, and
    a dormant control is the same shape of nothing as the greens this file exists to find.
    It costs two temporary directories and no network.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "synthetic.yml").write_text(_SYNTHETIC, encoding="utf-8")
        report = analyse(root)

    failures: list[str] = []
    if report.undeclared_by_lane().get("synthetic.yml#good"):
        failures.append("the DECLARED step was reported undeclared — the binding is broken")
    undeclared = report.undeclared_by_lane().get("synthetic.yml#bad", 0)
    if verbose:
        print(f"  {'synthetic.yml#bad':<24} {'undeclared':<22} -> {undeclared}")
    if undeclared != 1:
        failures.append(f"expected exactly 1 undeclared step in job `bad`, measured {undeclared}")
    for name, what, needle in _EXPECTED:
        count = sum(needle in f.text for f in report.findings)
        if verbose:
            print(f"  {name:<24} {what:<22} -> {count}")
        if count != 1:
            failures.append(f"{name}: expected exactly 1 {what}, measured {count}")

    # And the positive half: a directory of only well-formed steps must yield NOTHING.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "clean.yml").write_text(
            "\n".join(_SYNTHETIC.splitlines()[:8]) + "\n", encoding="utf-8"
        )
        clean = analyse(root)
    if verbose:
        print(f"  {'clean directory':<24} {'findings':<22} -> {len(clean.findings)}")
    if clean.findings:
        failures.append(
            f"a directory whose only step is correctly declared produced "
            f"{len(clean.findings)} finding(s): {[str(f) for f in clean.findings]}"
        )
    if len(clean.declared) != 1:
        failures.append(f"the clean directory declared {len(clean.declared)} of 1 invocation")
    return failures


def prove() -> int:
    """`--prove`: the self-control alone, with every probe's count printed."""
    failures = self_control(verbose=True)
    if failures:
        print("\ncheck_pytest_lanes --prove: REFUSED — this checker cannot be trusted.")
        for line in failures:
            print("  " + line)
        return 1
    print("\ncheck_pytest_lanes --prove: OK — refuses five planted defects, passes a clean tree.")
    return 0


# ---------------------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------------------
def emit_measured(report: Report) -> None:
    """Print the literal block a human pastes over `UNDECLARED_CEILING`. Never writes it."""
    print("UNDECLARED_CEILING: dict[str, int] = {")
    for lane, count in sorted(report.undeclared_by_lane().items()):
        print(f'    "{lane}": {count},')
    print("}")
    print(f"UNLANDED_CEILING = {report.unlanded_count()}")
    print(f"INVOCATION_FLOOR = {len(report.invocations)}")
    print(f"DECLARED_FLOOR = {len(report.bound)}")


def summarise(report: Report) -> None:
    """The one-screen census, printed whether the verdict is a pass or a refusal."""
    print(
        f"pytest invocations {len(report.invocations)}  ->  "
        f"{len(report.bound)} declared  ·  {len(report.undeclared)} undeclared  "
        f"(ceiling {sum(UNDECLARED_CEILING.values())}, floor {INVOCATION_FLOOR})"
    )
    for value in sorted(LANES):
        count = sum(1 for m in report.bound.values() if m.value == value)
        if count:
            print(f"    declared {count:>3}  {value}")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflows",
        type=Path,
        default=WORKFLOWS,
        help="directory of workflow files to read (default: .github/workflows)",
    )
    parser.add_argument(
        "--measure",
        action="store_true",
        help="print the measured ceiling block and exit 0; writes nothing",
    )
    parser.add_argument(
        "--prove",
        action="store_true",
        help="negative control: refuse five planted defects, pass a clean tree",
    )
    parser.add_argument("--quiet", action="store_true", help="findings only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.prove:
        return prove()
    root = args.workflows
    if not root.is_dir():
        print(f"check_pytest_lanes: {root} is not a directory")
        return 2

    report = analyse(root)
    if args.measure:
        emit_measured(report)
        return 0

    # The control first. If this program can no longer say no to a planted defect, its
    # verdict about the real tree is worth nothing and must not be printed as if it were.
    broken = self_control(verbose=False)
    if broken:
        print("check_pytest_lanes: the self-control FAILED; this program cannot be trusted")
        for line in broken:
            print("  " + line)
        return 2

    findings = list(report.findings)
    if root == WORKFLOWS:
        findings += check_floors(report, root)
        findings += check_ceiling(report.undeclared_by_lane(), UNDECLARED_CEILING)
        findings += check_unlanded(report)

    if not args.quiet:
        summarise(report)

    if findings:
        print(f"\ncheck_pytest_lanes: REFUSED — {len(findings)} finding(s).")
        for finding in findings[:60]:
            print("  " + str(finding))
        if len(findings) > 60:
            print(f"  … and {len(findings) - 60} more")
        print(
            "\n  A pytest step with no lane marker runs at the testkit default `auto`, and\n"
            "  `pytest` exits 0 when every test skips. On the Actions tab a lane that\n"
            "  reached no cluster and a lane that passed are the same green tick. Declare\n"
            "  the step, or enumerate it with `# trappoint:pytest-lane=unlanded reason=…`.\n"
            "  Raising a ceiling in this file is not a documentation edit; argue it in the\n"
            "  commit message."
        )
        return 1

    if not args.quiet:
        print(
            "\ncheck_pytest_lanes: OK — every declared step agrees with its own command "
            "line, and the self-control refused five planted defects on the way past."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
