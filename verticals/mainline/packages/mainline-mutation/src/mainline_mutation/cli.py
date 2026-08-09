# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``mainline-mutation`` — run the ratchet and publish the artefact.

    mainline-mutation run --seed 0 --out evidence/mutation
    mainline-mutation run --seed 0 --disable R1_DEONTIC --out evidence/mutation
    mainline-mutation catalogue

**The exit code is 0 whatever the kill rate is.**  A non-zero exit on a low
figure would make this a gate, and the brief is explicit: it measures, it does
not block.  The only non-zero exits are for conditions that mean the measurement
did not happen — an unpopulated class, a drifted cassette, a catalogue that does
not match its operators.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .catalogue import confidence, load_catalogue, operator_fingerprint
from .metrics import summarise, surviving_classes
from .model import KILL, SURVIVE
from .report import write_report
from .resources import catalogue_sha256
from .runner import RunOutput, run
from .version import HARNESS_VERSION

__all__ = ["main"]


def _print_headline(output: RunOutput) -> None:
    level = confidence()
    kill = summarise(output.results, kind=KILL, confidence=level)
    survive = summarise(output.results, kind=SURVIVE, confidence=level)
    arm = "CRIPPLED " + ",".join(output.disabled_rules) if output.disabled_rules else "INTACT"

    print(f"arm                : {arm}")
    print(f"seed               : {output.seed}")
    print(f"harness            : {HARNESS_VERSION}")
    print(f"catalogue_sha256   : {catalogue_sha256()}")
    print(f"operator_fingerprint: {operator_fingerprint()}")
    print()
    print(
        f"KILL     wilson_lower={kill.interval.lower:.6f}  "
        f"(point {kill.interval.point:.6f})  {kill.successes}/{kill.trials} killed"
    )
    print(
        f"SURVIVE  wilson_lower={survive.interval.lower:.6f}  "
        f"(point {survive.interval.point:.6f})  {survive.successes}/{survive.trials} preserved"
    )
    named = surviving_classes(output.results)
    print(f"surviving KILL classes: {list(named) if named else '(none)'}")
    print(f"skipped pairings      : {len(output.skips)}")


def _cmd_run(args: argparse.Namespace) -> int:
    output = run(seed=args.seed, disabled_rules=frozenset(args.disable or ()))
    _print_headline(output)
    if args.out:
        target = write_report(output, Path(args.out))
        print(f"\nartefact: {target}")
    return 0


def _cmd_catalogue(args: argparse.Namespace) -> int:
    del args
    payload = [
        {
            "class_id": c.class_id,
            "kind": c.kind,
            "title": c.title,
            "magnitude": c.magnitude,
            "expected": c.expected,
        }
        for c in load_catalogue()
    ]
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point.  Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="mainline-mutation",
        description=(
            "MUTATION RATCHET: KILL/SURVIVE catalogues and a Wilson-bounded residual-risk "
            "figure. Measures; never gates."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    runner = sub.add_parser("run", help="run the catalogues and print the headline")
    runner.add_argument("--seed", type=int, default=0, help="master seed (recorded)")
    runner.add_argument(
        "--disable",
        action="append",
        metavar="RULE_ID",
        help="disable a lattice rule (the crippled arm); repeatable",
    )
    runner.add_argument("--out", help="directory to write the dated JSON artefact into")
    runner.set_defaults(func=_cmd_run)

    catalogue = sub.add_parser("catalogue", help="print the declared catalogue as JSON")
    catalogue.set_defaults(func=_cmd_catalogue)

    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
