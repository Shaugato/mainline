#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The judge pack's command line.

    python verticals/mainline/demo/judge/cli.py validate
    python verticals/mainline/demo/judge/cli.py validate --require-cross-check
    python verticals/mainline/demo/judge/cli.py render            # rewrite PACK.md
    python verticals/mainline/demo/judge/cli.py render --check    # fail if PACK.md drifted
    python verticals/mainline/demo/judge/cli.py list
    python verticals/mainline/demo/judge/cli.py envelope
    python verticals/mainline/demo/judge/cli.py run --via sql     # needs a DSN
    python verticals/mainline/demo/judge/cli.py run --via mcp     # needs a published key

**Exit codes are three-valued on purpose.** ``0`` checked and correct · ``1`` checked and
wrong · ``2`` the pack could not be loaded · ``3`` NOT RUN, nothing was checked. A judge, a
CI job and an operator all need "we could not check" to be distinguishable from "we
checked and it is wrong", and one non-zero code makes that impossible.

Runs with nothing installed but PyYAML. ``psycopg`` is needed only for ``run --via sql``
and ``packages/mainline-mcp`` only for ``run --via mcp``; both report their absence as a
NOT-RUN rather than as a pass.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # pragma: no cover - exercised by running this file directly
    # A judge runs `python verticals/mainline/demo/judge/cli.py`, with nothing installed
    # and no package context. Put the parent directory on the path and name the package so
    # the relative imports below resolve exactly as they do under `-m`.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "judge"

from . import drift as drift_mod
from . import envelope as env
from . import pack as pack_mod
from . import render as render_mod
from . import runner as runner_mod

JUDGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = JUDGE_DIR.parents[3]
PACK_MD = JUDGE_DIR / "PACK.md"

EXIT_OK = 0
EXIT_WRONG = 1
EXIT_UNLOADABLE = 2
EXIT_NOT_RUN = 3


def _load(path: Path | None) -> pack_mod.Pack:
    return pack_mod.load_pack(path)


def _print_findings(findings: list[pack_mod.Finding], *, verbose: bool) -> dict[str, int]:
    counts = drift_mod.severities(findings)
    for finding in findings:
        if finding.severity == "info" and not verbose:
            continue
        print(f"  {finding.render()}")
    return counts


def cmd_validate(args: argparse.Namespace) -> int:
    pack = _load(args.pack)
    print(
        f"judge pack: {pack.source} — {len(pack)} questions "
        f"({len(pack.positives())} positive, {len(pack.negatives())} negative)"
    )

    print("\nenvelope and structure")
    structural = pack_mod.validate_pack(pack, repo_root=args.root)
    counts = _print_findings(structural, verbose=args.verbose)

    print("\nagreement with the repository")
    drifted = drift_mod.check_drift(pack, repo_root=args.root, judge_dir=JUDGE_DIR)
    drift_counts = _print_findings(drifted, verbose=args.verbose)
    for key, value in drift_counts.items():
        counts[key] = counts.get(key, 0) + value

    print("\nsecond implementation of the envelope")
    cross = env.crosscheck_with_mainline_mcp()
    if not cross.ran:
        print(f"  NOT RUN  {cross.reason}")
        if args.require_cross_check:
            print("  --require-cross-check was given and the cross-check did not run")
            return EXIT_WRONG
    elif cross.disagreements:
        for line in cross.disagreements:
            print(f"  FAIL   {line}")
        counts["fail"] = counts.get("fail", 0) + len(cross.disagreements)
    else:
        print(f"  OK     {cross.reason}; every modelled limit agrees")

    print(
        f"\n{counts.get('fail', 0)} failures, {counts.get('warn', 0)} warnings, "
        f"{counts.get('info', 0)} notes"
    )
    if counts.get("fail", 0):
        return EXIT_WRONG
    if counts.get("warn", 0) and args.strict:
        print("--strict was given and at least one authority was absent, so a check did not run")
        return EXIT_WRONG
    return EXIT_OK


def cmd_self_test(args: argparse.Namespace) -> int:
    """Plant one violation per family and require the validator to fire on every one."""
    from . import selftest as selftest_mod

    source = args.pack or pack_mod.pack_path(JUDGE_DIR)
    result = selftest_mod.self_test(repo_root=args.root, source=source, judge_dir=JUDGE_DIR)
    print(f"planted {len(result.caught) + len(result.missed)} violations\n")
    for line in result.caught:
        print(f"  RED    {line}")
    for line in result.missed:
        print(f"  MISSED {line}")
    if result.missed:
        print("\nA validator that cannot go red asserts nothing about the pack it validates.")
        return EXIT_WRONG
    print("\nself-test OK — every planted violation was caught")
    return EXIT_OK


def cmd_render(args: argparse.Namespace) -> int:
    pack = _load(args.pack)
    text = render_mod.render_pack(pack, repo_root=args.root)
    if args.check:
        if not PACK_MD.is_file():
            print(f"{PACK_MD} does not exist; run `render` without --check")
            return EXIT_WRONG
        current = PACK_MD.read_text(encoding="utf-8")
        if current == text:
            print(f"{PACK_MD.name} is current ({len(text)} bytes)")
            return EXIT_OK
        print(f"{PACK_MD.name} has DRIFTED from {pack.source.name}. Re-run without --check.")
        _print_first_difference(current, text)
        return EXIT_WRONG
    PACK_MD.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {PACK_MD} ({len(text)} bytes)")
    return EXIT_OK


def _print_first_difference(current: str, expected: str) -> None:
    current_lines = current.splitlines()
    expected_lines = expected.splitlines()
    for index in range(max(len(current_lines), len(expected_lines))):
        here = current_lines[index] if index < len(current_lines) else "<end of file>"
        there = expected_lines[index] if index < len(expected_lines) else "<end of file>"
        if here != there:
            print(f"  first difference at line {index + 1}")
            print(f"    committed: {here[:120]}")
            print(f"    generated: {there[:120]}")
            return


def cmd_list(args: argparse.Namespace) -> int:
    pack = _load(args.pack)
    for question in pack:
        badge = "NEG" if question.is_negative else "   "
        camera = f" [beat {question.beat}]" if question.beat is not None else ""
        view = question.qualified_view or "—"
        print(f"{badge} {question.qid:5} {question.verb:14} {view:48}{camera}")
        print(f"      {question.ask}")
    return EXIT_OK


def cmd_envelope(args: argparse.Namespace) -> int:
    pack = _load(args.pack)
    print("the Managed-MCP envelope this pack is validated against\n")
    for key, value in env.DECLARED_ENVELOPE.items():
        declared = pack.declared_envelope.get(key, "<absent from the pack>")
        agreement = "ok" if declared == value else f"DISAGREES (pack says {declared!r})"
        print(f"  {key:28} {value!r:70} {agreement}")
    print("\nbound EXPLAIN statements, measured against the character cap\n")
    for bound in drift_mod.bound_statements(pack, repo_root=args.root):
        verdict = "fits" if bound.fits else "DOES NOT FIT"
        print(
            f"  {bound.qid:5} {bound.vector_column:12} dim={bound.dimension:5} "
            f"chars={bound.statement_chars:6} headroom={bound.headroom_chars:6} {verdict}"
        )
    cross = env.crosscheck_with_mainline_mcp()
    print(f"\ncross-check: {'ran' if cross.ran else 'NOT RUN'} — {cross.reason}")
    for line in cross.disagreements:
        print(f"  DISAGREEMENT  {line}")
    return EXIT_WRONG if cross.disagreements else EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    pack = _load(args.pack)
    if args.via == "sql":
        report = runner_mod.run_via_sql(pack, repo_root=args.root, dsn=args.dsn)
    else:
        report = runner_mod.run_via_mcp(pack, repo_root=args.root)
    print(f"channel: {report.channel}")
    if not report.ran:
        print(f"NOT RUN — {report.reason}")
        print("Reporting this as a pass would assert nothing, and for the negatives it would")
        print("assert the opposite of what they claim. Exit 3.")
        return report.exit_code()
    print(f"{report.reason}\n")
    for result in report.results:
        print(f"  {result.render()}")
    counts = report.counts()
    print(
        f"\n{counts['answered']} answered, {counts['refused']} refused, "
        f"{counts['skipped']} skipped, {counts['error']} errors"
    )
    return report.exit_code()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="judge",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Shared options live on a parent parser attached to every subcommand rather than on
    # the top-level one, so `judge validate -v` works. Options only accepted BEFORE the
    # subcommand are options nobody types on the first attempt.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    common.add_argument("--pack", type=Path, default=None, help="path to QUESTIONS.yaml")
    common.add_argument("-v", "--verbose", action="store_true", help="show informational notes")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser(
        "validate",
        parents=[common],
        help="envelope, negatives, and agreement with the repo",
    )
    validate.add_argument(
        "--strict",
        action="store_true",
        help="treat a check that could not run (a missing authority) as a failure",
    )
    validate.add_argument(
        "--require-cross-check",
        action="store_true",
        help="fail when packages/mainline-mcp is not importable to confirm the limits",
    )
    validate.set_defaults(func=cmd_validate)

    self_test = sub.add_parser(
        "self-test",
        parents=[common],
        help="prove the validator can go red, one planted violation per family",
    )
    self_test.set_defaults(func=cmd_self_test)

    rendered = sub.add_parser(
        "render", parents=[common], help="write PACK.md, or check that it has not drifted"
    )
    rendered.add_argument("--check", action="store_true", help="fail instead of rewriting")
    rendered.set_defaults(func=cmd_render)

    listing = sub.add_parser("list", parents=[common], help="one line per question")
    listing.set_defaults(func=cmd_list)

    envelope = sub.add_parser(
        "envelope", parents=[common], help="the limits, the bound lengths, the cross-check"
    )
    envelope.set_defaults(func=cmd_envelope)

    run = sub.add_parser(
        "run",
        parents=[common],
        help="execute the pack; exits 3 when there was nothing to talk to",
    )
    run.add_argument("--via", choices=("mcp", "sql"), default="sql")
    run.add_argument("--dsn", default=None, help="override the DSN from the environment")
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except pack_mod.PackError as exc:
        print(f"the judge pack could not be loaded: {exc}")
        return EXIT_UNLOADABLE


if __name__ == "__main__":
    raise SystemExit(main())
