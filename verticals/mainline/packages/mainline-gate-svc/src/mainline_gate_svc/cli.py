# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A thin entry point. Argument parsing, JSON in, JSON out, and an exit code.

Deliberately thin: nothing here decides anything. Every refusal this command reports was
decided by the database and classified by ``trappoint_core``; every refusal to start was
decided by :mod:`mainline_gate_svc.config`. A CLI that made its own judgements would be a
second place where a merge could be refused, and the second place is always the one
nobody audits.

**The exit codes are the interface**, because an operator's shell reads them and a CI
step reads nothing else:

======  ==========================================================================
Code    Meaning
======  ==========================================================================
``0``   the merge committed, or the requested report was produced
``2``   the service refused to START — a model/cloud credential, or no DSN, or a
        request for another vertical's binding. Nothing was attempted.
``3``   the GATE refused: ``23514``/``23503``/``23505``/``P0001``. A decision.
``4``   ``42501`` — the writer never reached the gate. A fact about the writer.
``5``   undecided: the retry budget was exhausted, or the cluster was unreachable.
        **Not** a refusal, and the difference is the product.
``6``   an unmodelled SQLSTATE. A defect (``spec/errors.md`` §1.1), not an edge case.
======  ==========================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from trappoint_core import (
    ISOLATION_STATEMENT,
    AuthorisationDenied,
    GateRefused,
    RetryBudgetExhausted,
    UnmodelledRefusal,
)

from . import __version__
from .config import GateConfig, GateServiceError, load_config
from .service import ConnectionUnavailable, merge_permit, merge_request_from_mapping

__all__ = ["EXIT_CODES", "build_parser", "main"]

EXIT_OK: Final = 0
EXIT_REFUSED_TO_START: Final = 2
EXIT_GATE_REFUSED: Final = 3
EXIT_DENIED: Final = 4
EXIT_UNDECIDED: Final = 5
EXIT_UNMODELLED: Final = 6

#: Published so a test, a runbook and a CI step read the same table.
EXIT_CODES: Final[dict[str, int]] = {
    "ok": EXIT_OK,
    "refused_to_start": EXIT_REFUSED_TO_START,
    "gate_refused": EXIT_GATE_REFUSED,
    "denied": EXIT_DENIED,
    "undecided": EXIT_UNDECIDED,
    "unmodelled": EXIT_UNMODELLED,
}


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser. Separate from :func:`main` so a test can read it."""
    parser = argparse.ArgumentParser(
        prog="mainline-gate",
        description=(
            "Call the MAINLINE merge gate. One SERIALIZABLE transaction, one CALL, one verdict."
        ),
    )
    parser.add_argument("--version", action="version", version=f"mainline-gate-svc {__version__}")
    parser.add_argument(
        "--schema", default=None, help="override the binding schema (default: mainline)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "preflight",
        help=(
            "report the configuration this process would start with, without opening a "
            "connection. Exits 2 if the environment holds a model or cloud credential."
        ),
    )
    sub.add_parser(
        "isolation",
        help="print the isolation statement issued on every gate transaction, verbatim",
    )
    merge = sub.add_parser("merge", help="merge one permit from a JSON merge request")
    merge.add_argument(
        "request", help="path to the JSON merge request, or '-' to read it from standard input"
    )
    return parser


def _read_request_body(source: str) -> dict[str, Any]:
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    body: dict[str, Any] = json.loads(text)
    return body


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _preflight_report(config: GateConfig) -> dict[str, Any]:
    return {
        "ready": True,
        "dsn": config.redacted_dsn(),
        "schema": config.schema,
        "subject_kind": config.subject_kind,
        "application_name": config.application_name,
        "connect_timeout_s": config.connect_timeout_s,
        "statement_timeout_ms": config.statement_timeout_ms,
        "isolation_statement": ISOLATION_STATEMENT,
    }


def _merge_and_classify(body: dict[str, Any], config: GateConfig) -> tuple[dict[str, Any], int]:
    """Run one merge and turn whatever left it into (payload, exit code).

    The classification is a lookup, not a judgement: every branch below corresponds to a
    row of the table in this module's docstring and to a class in ``spec/errors.md`` §1.
    """
    request = merge_request_from_mapping(
        body, schema=config.schema, subject_kind=config.subject_kind
    )
    try:
        outcome = merge_permit(request, config=config)
    except GateRefused as refusal:
        payload = {"merged": False, "outcome": "gate_refused", "refusal": refusal.as_dict()}
        return payload, EXIT_GATE_REFUSED
    except AuthorisationDenied as denied:
        return {
            "merged": False,
            "outcome": "denied",
            "sqlstate": denied.sqlstate,
            "message": denied.message,
        }, EXIT_DENIED
    except (RetryBudgetExhausted, ConnectionUnavailable) as undecided:
        return {"merged": False, "outcome": "undecided", "message": str(undecided)}, EXIT_UNDECIDED
    except UnmodelledRefusal as unmodelled:
        return {
            "merged": False,
            "outcome": "unmodelled",
            "sqlstate": unmodelled.sqlstate,
            "message": unmodelled.message,
        }, EXIT_UNMODELLED
    return outcome.as_dict(), EXIT_OK


def _command_merge(source: str, config: GateConfig) -> int:
    try:
        body = _read_request_body(source)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read the merge request: {exc}", file=sys.stderr)
        return EXIT_REFUSED_TO_START
    try:
        payload, code = _merge_and_classify(body, config)
    except (KeyError, TypeError, ValueError) as exc:
        print(f"malformed merge request: {exc}", file=sys.stderr)
        return EXIT_REFUSED_TO_START
    except GateServiceError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_REFUSED_TO_START
    _emit(payload)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return its exit code.

    Returns rather than calls :func:`sys.exit`, so the whole command is testable in
    process and the console-script wrapper stays one line.
    """
    args = build_parser().parse_args(argv)

    if args.command == "isolation":
        print(ISOLATION_STATEMENT)
        return EXIT_OK

    try:
        config = load_config() if args.schema is None else load_config(schema=str(args.schema))
    except GateServiceError as exc:
        print(f"{exc}", file=sys.stderr)
        return EXIT_REFUSED_TO_START

    if args.command == "preflight":
        _emit(_preflight_report(config))
        return EXIT_OK

    return _command_merge(str(args.request), config)


if __name__ == "__main__":  # pragma: no cover - exercised by `python -m`
    raise SystemExit(main())
