#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim of its own. It runs pytest and reads the
#     JUnit XML pytest writes; every database claim in the results belongs to the test
#     that made it.
# I: QA-ORDER-1 — a suite that passes in exactly one order has not been shown to pass.
#    A red under a PRINTED seed is reproducible; a red "in the suite" is folklore, and
#    folklore is what three successive NO-GO verdicts were built on.
# RATIONALE: `verticals/mainline/apps/demo-api/tests` shares one cluster, one module-scope
#    connection (`db._conn`), one DSN cache (`db._dsn_cache`) and four process environment
#    variables that a session-scoped fixture rewrites (`w4_database`, test_gate_run.py).
#    Every one of those is a channel through which test N can change what test N+1 sees.
#    pytest's default order is file order then definition order, so a dependency along that
#    order is invisible for exactly as long as nobody reorders anything.

"""Run the demo-api suite in seeded random orders, and each module alone, and diff.

WHY THIS IS A SCRIPT AND NOT A PLUGIN
--------------------------------------
``pytest-randomly`` and ``pytest-random-order`` are not in ``.venv`` and are not in
``uv.lock``. ``uv lock --check`` in ``ci.yml`` is what makes "a stranger resolves the same
dependency graph" a true sentence about this repository, so adding a development
dependency to shuffle a list is a change with CI consequences out of all proportion to
the thing it buys. :func:`random.Random(seed).shuffle` is in the standard library, needs
no lockfile edit, and — unlike either plugin — the order it produces is a FILE this
script writes and pytest reads back with ``@argfile``, so a red order can be re-run
verbatim months later even if the seeding algorithm changes.

WHAT IT DOES
------------
``shuffle``   collect node ids with ``--collect-only -q``, shuffle them under a printed
              seed, write them to ``out/order/seed-<n>.args``, and run ``pytest @<file>``.
              The seed is printed BEFORE the run starts and again in the summary, because
              a seed printed only on success is a seed you do not have when it matters.

``modules``   run each test module alone, one pytest process per module, and write one
              JUnit XML per module.

``diff``      compare a whole-suite XML against the per-module XMLs and classify every
              disagreement:

                * ``CONTAMINATION`` — passes alone, not-passing in suite. Some earlier
                  test changed state this one reads.
                * ``HIDDEN-DEPENDENCE`` — passes in suite, not-passing alone. This test
                  needs a neighbour's side effect and does not say so. It is the more
                  dangerous of the two, because it looks green today and dies the moment
                  anyone runs a subset — which is what ``-k``, ``--lf`` and a sharded CI
                  lane all do.

              Both are defects. Neither is fixed by pinning the order: an order pin is a
              green that certifies itself.

``timings``   the per-case ``time`` attribute, aggregated by module and ranked, so a CI
              lane can budget a timeout from a measurement instead of a guess.

WHAT IT DELIBERATELY DOES NOT DO
---------------------------------
It does not write, delete or reorder a single test. It does not pass ``-p no:randomly``,
``-x``, ``--lf`` or any selector that would make one run a different population from
another: every run is the same node ids in a different sequence, so a difference in
the results is a difference in the PRODUCT and not in what was asked of it.

USAGE
-----
::

    $env:TRAPPOINT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
    py scripts/qa/demo_suite_order.py shuffle  --seed 1 --seed 2 --seed 3
    py scripts/qa/demo_suite_order.py modules
    py scripts/qa/demo_suite_order.py diff --suite out/demo-suite-w5-before.xml
    py scripts/qa/demo_suite_order.py timings out/demo-suite-w5-before.xml

Exit status is ``0`` when every run was green and every diff empty, ``1`` otherwise. A
non-zero exit always has the seed on the last line.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "tests"
OUT_DIR = REPO_ROOT / "out" / "order"

#: The interpreter that has psycopg and the workspace packages installed. Resolved rather
#: than assumed to be ``sys.executable`` so the script behaves the same whether it is run
#: as ``py scripts/qa/...`` from the repo root or by the venv's own python.
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():  # pragma: no cover - POSIX layout
    VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

#: Every run in this script uses these and nothing else. ``--timeout`` is the per-test
#: ceiling the lead's command uses; ``-p no:cacheprovider`` keeps a shuffled run from
#: writing a ``.pytest_cache`` ``lastfailed`` that a later run would inherit — which would
#: be this script introducing the very cross-run state it exists to detect.
COMMON_ARGS = ("--crdb=reuse", "-q", "--tb=line", "-rN", "--timeout=180", "-p", "no:cacheprovider")


def _python() -> str:
    return str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable)


def collect() -> list[str]:
    """Every node id pytest would run, in pytest's own default order.

    ``--collect-only -q`` prints one node id per line and then a summary line; the summary
    is dropped by requiring ``::`` in the line, which every node id has and no summary line
    does. ``--crdb=none`` is used deliberately: collection must not need a cluster, and if
    it ever does, that is a defect this script should surface rather than hide behind a
    live DSN.
    """
    proc = subprocess.run(
        [_python(), "-m", "pytest", str(TESTS_DIR), "--collect-only", "-q", "--crdb=none"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    ids = [line.strip() for line in proc.stdout.splitlines() if "::" in line]
    if not ids:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit("collection produced no node ids")
    # MEASURED, and it is the difference between an args file that runs and one that
    # collects nothing: pytest prints node ids relative to ROOTDIR, and rootdir for this
    # directory is `verticals/mainline/apps/demo-api` (it carries its own pyproject), so
    # every id arrives spelled `tests/test_x.py::y`. Fed back from the repository root
    # that names `D:/…/mainline/tests/test_x.py`, a real directory holding different
    # tests. Re-anchoring here rather than running pytest from another cwd keeps every
    # run in this script identical to the one §4 of the plan specifies.
    prefix = TESTS_DIR.parent.relative_to(REPO_ROOT).as_posix()
    return [f"{prefix}/{node}" if not node.startswith(prefix) else node for node in ids]


@dataclass(frozen=True)
class Totals:
    """The four numbers off a JUnit ``<testsuite>`` root, plus wall clock."""

    tests: int
    failures: int
    errors: int
    skipped: int
    seconds: float

    @property
    def passed(self) -> int:
        return self.tests - self.failures - self.errors - self.skipped

    @property
    def green(self) -> bool:
        return self.failures == 0 and self.errors == 0

    def line(self) -> str:
        return (
            f"{self.tests} tests · {self.passed} passed · {self.failures} failed · "
            f"{self.skipped} skipped · {self.errors} errors · {self.seconds:.1f}s"
        )


def _suite_element(path: Path) -> ET.Element:
    root = ET.parse(path).getroot()  # noqa: S314 - pytest writes this file
    return root if root.tag == "testsuite" else root[0]


def totals(path: Path) -> Totals:
    element = _suite_element(path)
    return Totals(
        tests=int(element.get("tests", 0)),
        failures=int(element.get("failures", 0)),
        errors=int(element.get("errors", 0)),
        skipped=int(element.get("skipped", 0)),
        seconds=float(element.get("time", 0.0)),
    )


@dataclass
class Case:
    """One test case's outcome, keyed the way a node id keys it."""

    module: str
    name: str
    outcome: str  # passed | failed | error | skipped
    message: str
    seconds: float

    @property
    def key(self) -> str:
        return f"{self.module}::{self.name}"


def cases(path: Path) -> dict[str, Case]:
    """Every case in a JUnit XML, keyed ``module::name``.

    Parametrised names keep their ``[...]`` suffix, so ``test_x[silence]`` and
    ``test_x[ledger]`` are two cases and not one — which they are, and which matters
    because a contamination can hit one parameter and not its siblings.
    """
    found: dict[str, Case] = {}
    for element in _suite_element(path).iter("testcase"):
        outcome, message = "passed", ""
        for child in element:
            if child.tag in ("failure", "error", "skipped"):
                outcome = "error" if child.tag == "error" else child.tag
                if child.tag == "failure":
                    outcome = "failed"
                message = (child.get("message") or "").replace("\n", " ")[:200]
                break
        module = (element.get("classname") or "").split(".")[-1]
        case = Case(
            module=module,
            name=element.get("name") or "",
            outcome=outcome,
            message=message,
            seconds=float(element.get("time", 0.0)),
        )
        found[case.key] = case
    return found


# ── shuffle ─────────────────────────────────────────────────────────────────────────


def run_shuffled(seed: int, *, tag: str) -> tuple[Totals | None, Path, Path]:
    """One whole-suite run in the order ``random.Random(seed)`` produces.

    The order is written to disk BEFORE pytest starts. That is the point of the file: a
    seed reproduces the order only for as long as the collection is unchanged and the
    shuffling algorithm is unchanged, whereas the file reproduces it forever. Both are
    printed, so a red can be re-run either way.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ids = collect()
    order = list(ids)
    # S311: the shuffle is an EXPERIMENTAL ORDER, not a secret. A reproducible order is
    # the whole point — `random.Random(seed)` is deterministic across runs and machines,
    # which `secrets` deliberately is not.
    random.Random(seed).shuffle(order)  # noqa: S311

    args_file = OUT_DIR / f"{tag}-seed-{seed}.args"
    xml_file = OUT_DIR / f"{tag}-seed-{seed}.xml"
    log_file = OUT_DIR / f"{tag}-seed-{seed}.log"
    args_file.write_text("\n".join(order) + "\n", encoding="utf-8")

    # ASCII only in what this script prints. Windows consoles default to cp1252 and a
    # `UnicodeEncodeError` in the reporting line would destroy a run that had already
    # cost its full wall clock — measured, on the first invocation of this script.
    print(f"[seed {seed}] {len(order)} node ids -> {args_file}", flush=True)
    print(f"[seed {seed}] first three: {order[:3]}", flush=True)

    command = [
        _python(),
        "-u",
        "-m",
        "pytest",
        f"@{args_file}",
        *COMMON_ARGS,
        f"--junitxml={xml_file}",
    ]
    with log_file.open("w", encoding="utf-8") as handle:
        subprocess.run(command, cwd=REPO_ROOT, stdout=handle, stderr=handle, check=False)

    if not xml_file.exists():
        print(f"[seed {seed}] FAILED BEFORE WRITING XML — see {log_file}", flush=True)
        return None, args_file, xml_file
    result = totals(xml_file)
    verdict = "GREEN" if result.green else "RED"
    print(f"[seed {seed}] {verdict}: {result.line()}", flush=True)
    if not result.green:
        # Said twice on purpose. The first line above scrolls; this is the line a reader
        # who scrolled to the bottom of a 25-minute log actually sees.
        print(f"[seed {seed}] REPRODUCE WITH: pytest @{args_file}  (seed={seed})", flush=True)
    return result, args_file, xml_file


# ── modules ─────────────────────────────────────────────────────────────────────────


def modules() -> list[Path]:
    return sorted(TESTS_DIR.glob("test_*.py"))


def run_modules(*, tag: str) -> dict[str, Path]:
    """One pytest process per module. Nothing else is in that process's session.

    A separate PROCESS, not a separate session in one process: ``db._conn``,
    ``db._dsn_cache`` and the four ``MAINLINE_DEMO_*`` environment variables are all
    process state, so a second session in the same interpreter would inherit exactly the
    thing being controlled for.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for path in modules():
        xml_file = OUT_DIR / f"{tag}-alone-{path.stem}.xml"
        log_file = OUT_DIR / f"{tag}-alone-{path.stem}.log"
        command = [
            _python(),
            "-u",
            "-m",
            "pytest",
            str(path),
            *COMMON_ARGS,
            f"--junitxml={xml_file}",
        ]
        with log_file.open("w", encoding="utf-8") as handle:
            subprocess.run(command, cwd=REPO_ROOT, stdout=handle, stderr=handle, check=False)
        if xml_file.exists():
            print(f"[alone] {path.stem:32s} {totals(xml_file).line()}", flush=True)
            written[path.stem] = xml_file
        else:  # pragma: no cover - pytest crashed before writing
            print(f"[alone] {path.stem:32s} NO XML — see {log_file}", flush=True)
    return written


# ── diff ────────────────────────────────────────────────────────────────────────────


@dataclass
class Disagreement:
    key: str
    alone: str
    in_suite: str
    verdict: str
    detail: str = ""


@dataclass
class Report:
    disagreements: list[Disagreement] = field(default_factory=list)
    missing_alone: list[str] = field(default_factory=list)
    missing_in_suite: list[str] = field(default_factory=list)


def diff(suite_xml: Path, alone_xmls: dict[str, Path]) -> Report:
    """Classify every case whose outcome differs alone and in suite.

    "Not-passing" rather than "failed": an ERROR alone and a PASS in suite is the same
    defect as a FAILURE alone and a PASS in suite — the test needed something a neighbour
    did — and a comparison that only looked at ``failed`` would miss the whole 63-error
    family this suite currently carries.
    """
    in_suite = cases(suite_xml)
    report = Report()
    for stem, path in sorted(alone_xmls.items()):
        for key, case in cases(path).items():
            other = in_suite.get(key)
            if other is None:
                report.missing_in_suite.append(key)
                continue
            if case.outcome == other.outcome:
                continue
            alone_ok = case.outcome == "passed"
            suite_ok = other.outcome == "passed"
            if alone_ok and not suite_ok:
                verdict = "CONTAMINATION"
            elif suite_ok and not alone_ok:
                verdict = "HIDDEN-DEPENDENCE"
            else:
                # Both non-passing but differently — a skip alone and an error in suite,
                # say. Still a difference the environment made, still worth a line.
                verdict = "DIVERGENT-FAILURE"
            report.disagreements.append(
                Disagreement(
                    key=f"{stem}::{case.name}",
                    alone=case.outcome,
                    in_suite=other.outcome,
                    verdict=verdict,
                    detail=(case.message or other.message)[:200],
                )
            )
    alone_keys = {k for path in alone_xmls.values() for k in cases(path)}
    report.missing_alone = sorted(set(in_suite) - alone_keys)
    return report


# ── timings ─────────────────────────────────────────────────────────────────────────


def timings(path: Path, top: int = 12) -> str:
    per_module: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    ranked: list[tuple[float, str]] = []
    for key, case in cases(path).items():
        per_module[case.module] += case.seconds
        counts[case.module] += 1
        ranked.append((case.seconds, key))
    ranked.sort(reverse=True)

    lines = [f"{'module':34s} {'tests':>5s} {'seconds':>9s} {'s/test':>7s}"]
    for module in sorted(per_module, key=lambda m: -per_module[m]):
        seconds, n = per_module[module], counts[module]
        lines.append(f"{module:34s} {n:5d} {seconds:9.1f} {seconds / max(n, 1):7.2f}")
    lines.append(f"{'TOTAL':34s} {sum(counts.values()):5d} {sum(per_module.values()):9.1f}")
    lines.append("")
    lines.append(f"slowest {top}:")
    lines.extend(f"  {seconds:7.2f}s  {key}" for seconds, key in ranked[:top])
    return "\n".join(lines)


# ── command line ────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912 - one branch per subcommand
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    shuffle_cmd = sub.add_parser("shuffle", help="run the whole suite in seeded random orders")
    shuffle_cmd.add_argument("--seed", type=int, action="append", required=True)
    shuffle_cmd.add_argument("--tag", default="w5")

    modules_cmd = sub.add_parser("modules", help="run each test module alone")
    modules_cmd.add_argument("--tag", default="w5")

    diff_cmd = sub.add_parser("diff", help="diff per-module results against a whole-suite XML")
    diff_cmd.add_argument("--suite", type=Path, required=True)
    diff_cmd.add_argument("--tag", default="w5")
    diff_cmd.add_argument("--json", type=Path, default=None)

    timings_cmd = sub.add_parser("timings", help="per-module and slowest-case timing table")
    timings_cmd.add_argument("xml", type=Path)
    timings_cmd.add_argument("--top", type=int, default=12)

    args = parser.parse_args(argv)

    if args.command == "shuffle":
        failed_seeds: list[int] = []
        for seed in args.seed:
            result, _args_file, _ = run_shuffled(seed, tag=args.tag)
            if result is None or not result.green:
                failed_seeds.append(seed)
        if failed_seeds:
            print(f"\nRED SEEDS: {failed_seeds}", flush=True)
            for seed in failed_seeds:
                print(f"  pytest @{OUT_DIR / f'{args.tag}-seed-{seed}.args'}   # seed={seed}")
            return 1
        print(f"\nALL SEEDS GREEN: {args.seed}", flush=True)
        return 0

    if args.command == "modules":
        written = run_modules(tag=args.tag)
        return 0 if written else 1

    if args.command == "diff":
        alone = {
            path.stem.replace(f"{args.tag}-alone-", ""): path
            for path in sorted(OUT_DIR.glob(f"{args.tag}-alone-*.xml"))
        }
        if not alone:
            print(f"no per-module XMLs under {OUT_DIR} — run `modules` first")
            return 1
        report = diff(args.suite, alone)
        for item in sorted(report.disagreements, key=lambda d: (d.verdict, d.key)):
            print(f"{item.verdict:18s} {item.key}")
            print(f"{'':18s}   alone={item.alone} in-suite={item.in_suite}")
            if item.detail:
                print(f"{'':18s}   {item.detail}")
        if report.missing_alone:
            print(f"\nin suite but in no per-module run ({len(report.missing_alone)}):")
            for key in report.missing_alone[:20]:
                print(f"  {key}")
        if report.missing_in_suite:
            print(f"\nrun alone but absent from the suite XML ({len(report.missing_in_suite)}):")
            for key in report.missing_in_suite[:20]:
                print(f"  {key}")
        if args.json is not None:
            args.json.write_text(
                json.dumps(
                    {
                        "suite": str(args.suite),
                        "disagreements": [vars(d) for d in report.disagreements],
                        "missing_alone": report.missing_alone,
                        "missing_in_suite": report.missing_in_suite,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return 1 if report.disagreements else 0

    if args.command == "timings":
        print(timings(args.xml, args.top))
        return 0

    raise AssertionError(args.command)  # pragma: no cover - argparse rejects it first


if __name__ == "__main__":
    raise SystemExit(main())
