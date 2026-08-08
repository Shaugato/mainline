# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-recall-verify-per`` — check a silence receipt with nothing installed.

The command a stranger runs::

    python -m trappoint_recall.per receipt.json
    python -m trappoint_recall.per receipt.json --candidates recall_candidate.json
    python -m trappoint_recall.per receipt.json --json

Exit status is the finding: ``0`` when every check passed, ``1`` when any failed, ``2`` when
the input could not be read at all. That is deliberate — a CI lane, a nightly patrol and a
person all consume the same three answers, and "could not read the file" must never be
confused with "the proof does not hold".

The whole import graph of this command is the standard library plus this subpackage. If that
ever stops being true, the verifier has become something the defendant controls.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from trappoint_recall.per.verify import verify_receipt

__all__ = ["build_parser", "main"]

_EXIT_OK = 0
_EXIT_FAILED_VERIFICATION = 1
_EXIT_UNREADABLE = 2


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, exposed so a test can assert the surface without running it."""
    parser = argparse.ArgumentParser(
        prog="trappoint-recall-verify-per",
        description=(
            "Verify a MAINLINE Proof of Exhausted Recall receipt. With --candidates, "
            "recomputes the commitment from the disclosed candidate set; without it, checks "
            "the boundary disclosure alone."
        ),
    )
    parser.add_argument("receipt", type=Path, help="path to the receipt JSON document")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=None,
        help=(
            "path to the disclosed candidate set: a JSON array of recall_candidate rows "
            "(event_id, p_relevant, tau_applied, outcome) or of committed leaves"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit the report as JSON instead of text",
    )
    return parser


def _load(path: Path) -> Any:
    """Read one JSON document, or raise ``OSError``/``ValueError`` for the caller to report."""
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the process exit status rather than calling ``sys.exit``."""
    args = build_parser().parse_args(argv)

    try:
        receipt = _load(args.receipt)
    except (OSError, ValueError) as exc:
        print(f"cannot read receipt {args.receipt}: {exc}", file=sys.stderr)
        return _EXIT_UNREADABLE
    if not isinstance(receipt, dict):
        print(f"{args.receipt} does not hold a JSON object", file=sys.stderr)
        return _EXIT_UNREADABLE

    candidates = None
    if args.candidates is not None:
        try:
            loaded = _load(args.candidates)
        except (OSError, ValueError) as exc:
            print(f"cannot read candidate set {args.candidates}: {exc}", file=sys.stderr)
            return _EXIT_UNREADABLE
        if isinstance(loaded, dict) and isinstance(loaded.get("candidates"), list):
            loaded = loaded["candidates"]
        if not isinstance(loaded, list):
            print(
                f"{args.candidates} must hold a JSON array of candidates, or an object with "
                "a 'candidates' array",
                file=sys.stderr,
            )
            return _EXIT_UNREADABLE
        candidates = [entry for entry in loaded if isinstance(entry, dict)]
        if len(candidates) != len(loaded):
            print(f"{args.candidates} holds non-object entries", file=sys.stderr)
            return _EXIT_UNREADABLE

    report = verify_receipt(receipt, candidates)
    if args.as_json:
        print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    else:
        print(report.to_text())
    return _EXIT_OK if report.ok else _EXIT_FAILED_VERIFICATION


if __name__ == "__main__":  # pragma: no cover - exercised through __main__.py
    raise SystemExit(main())
