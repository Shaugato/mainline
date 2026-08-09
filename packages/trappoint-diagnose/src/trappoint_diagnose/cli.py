# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-diagnose`` — explain a refusal that already happened, from the command line.

Exit codes, and they are the substrate's three:

* ``0`` — the diagnosis was produced.
* ``1`` — the diagnoser **refused**: the database declined to diagnose (drift, or a
  refusal that is no longer reproducible), or the payload did not validate.
* ``2`` — the invocation was wrong. Distinguished from ``1`` so a wrapper cannot mistake
  "you typed it wrong" for "the projection has drifted" and retry forever.

The command **never causes a refusal in order to diagnose one**. It takes a refusal that
has already been observed — its SQLSTATE, its exhibit and its message — and explains it.
A tool that could provoke the refusal it then explains would be a tool that writes to the
gate on the diagnosis path, and I14 says the diagnosis must never be able to do that.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from .binding import load_gate_binding
from .diagnose import Diagnoser
from .errors import DiagnoseRefused
from .model import RefusalContext
from .oracle import Connection
from .udf import UdfSource

__all__ = ["main"]

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2


def _connect_factory(dsn: str) -> Callable[[], Connection]:
    """Build a zero-argument connection factory, importing the driver only if used.

    The import is inside the function on purpose. ``trappoint_diagnose`` declares no
    runtime dependency on a driver so that a verifier can import it to check a payload
    without pulling a binary wheel; this command is the one place a driver is needed, and
    the error when it is missing names the extra to install rather than a traceback.
    """
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise DiagnoseRefused(
            "this command needs a PostgreSQL driver: install `trappoint-diagnose[pg]`. "
            "The base distribution declares no driver so that checking a payload does not "
            "require one."
        ) from exc

    def connect() -> Connection:
        # psycopg's Connection satisfies the structural `Connection` protocol; the cast is
        # the seam between a typed driver and a package that declines to depend on one.
        return cast("Connection", psycopg.connect(dsn))

    return connect


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trappoint-diagnose",
        description=(
            "Explain a gate refusal: the irreducible reason set and, where computable, "
            "the nearest admissible alternative. Reads only; never writes to the gate."
        ),
    )
    parser.add_argument("--dsn", required=True, help="connection string for the diagnosis read")
    parser.add_argument("--binding", type=Path, required=True, help="path to a vertical.toml")
    parser.add_argument("--subject-kind", required=True, help="permit, change_request, ...")
    parser.add_argument("--subject-id", required=True, help="the subject's UUID")
    parser.add_argument("--gate-epoch", type=int, required=True, help="epoch at refusal time")
    parser.add_argument("--constraint", required=True, help="the exhibit name, verbatim")
    parser.add_argument(
        "--sqlstate",
        default="23514",
        help="the refusal code the database reported (23514, 23503, 23505, P0001)",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="the database message, verbatim; defaults to naming the constraint",
    )
    parser.add_argument(
        "--constraint-source",
        choices=("reported", "parsed"),
        default="reported",
        help="reported = from driver diagnostics; parsed = recovered from the message",
    )
    parser.add_argument("--attempt-kind", default=None, help="the verdict kind that was tried")
    parser.add_argument("--attempt-check", default=None, help="the check it was tried against")
    parser.add_argument(
        "--function",
        default="trappoint.explain_refusal",
        help="the in-database decomposition to call",
    )
    parser.add_argument("--indent", type=int, default=2, help="JSON indent; 0 for one line")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``trappoint-diagnose`` console script."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    attempt: dict[str, object] = {}
    if args.attempt_kind:
        attempt["kind"] = args.attempt_kind
    if args.attempt_check:
        attempt["check_id"] = args.attempt_check
    try:
        binding = load_gate_binding(args.binding)
        context = RefusalContext(
            sqlstate=args.sqlstate,
            constraint=args.constraint,
            message=args.message or f"refused by {args.constraint}",
            subject_kind=args.subject_kind,
            subject_id=args.subject_id,
            gate_epoch=args.gate_epoch,
            constraint_source=args.constraint_source,
            attempt=attempt,
        )
    except (OSError, ValueError) as exc:
        print(f"trappoint-diagnose: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        source = UdfSource(_connect_factory(args.dsn), function=args.function)
        payload = Diagnoser(binding).explain(context, source=source)
    except DiagnoseRefused as exc:
        print(f"trappoint-diagnose: REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except Exception as exc:  # noqa: BLE001 - the driver's errors are not ours to model
        print(f"trappoint-diagnose: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    print(json.dumps(payload.to_wire(), indent=args.indent or None, sort_keys=True))
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    raise SystemExit(main())
