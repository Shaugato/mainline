# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The command line: ``verify``, ``receipt-audit`` and ``explain-check``.

.. code-block:: console

    $ uvx trappoint-verify verify --bundle bundle.json
    $ uvx trappoint-verify receipt-audit --bundle bundle.json
    $ uvx trappoint-verify explain-check 14

Exit codes, and why there are four of them
------------------------------------------
==== ==========================================================================
``0`` every selected check ran and held.
``1`` at least one check ran and did not hold.
``2`` nothing failed **and something was not looked at**. Distinct from ``0``
      on purpose: a CI lane that treats non-zero as failure cannot go green on
      a verifier that skipped half its checks, and a lane that wants to
      tolerate skips has to say so in writing.
``3`` the bundle could not be read, or the command line was wrong. Not a
      verdict about the log — a verdict about the input.
==== ==========================================================================

``argparse`` exits ``2`` for a usage error by default, which would be indistinguishable
from *"verified, but N checks did not run"*. :class:`_Parser` overrides that to ``3``.

Every online capability is opt-in
---------------------------------
``--s3``, ``--kms-pubkey`` and ``--tile-url`` are the only paths that could touch a
network, they are off by default, and their absence downgrades the affected check to
``SKIP(offline)``. Nothing on the default path opens a socket, and
``tests/test_no_network.py`` proves it by patching ``socket.socket`` to raise.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from typing import IO, NoReturn

from trappoint_verify import __version__
from trappoint_verify.bundle import BundleError, load_bundle
from trappoint_verify.checks import (
    CHECK_IDS,
    SPEC_STATUS_LAG,
    LoadReport,
    VerifyOptions,
    load_all,
    registered,
    run_all,
    spec_for,
)
from trappoint_verify.report import (
    EXIT_UNUSABLE,
    Report,
    want_colour,
)

__all__ = ["main"]

_RECEIPT_AUDIT_CHECKS: tuple[int, ...] = (4, 15)


class _Parser(argparse.ArgumentParser):
    """An ``ArgumentParser`` whose usage errors exit ``3``, not ``2``.

    ``2`` means *"verified, but something was not checked"* in this tool. A misspelt flag
    must not be able to produce that number.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        raise SystemExit(EXIT_UNUSABLE)


def _build_parser() -> _Parser:
    parser = _Parser(
        prog="trappoint-verify",
        description=(
            "Verify a TRAPPOINT evidence bundle offline. This bundle records the "
            "preconditions the database enforced before work was permitted to start."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"trappoint-verify {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    verify = subcommands.add_parser("verify", help="run every registered check over a bundle")
    _add_bundle_argument(verify)
    _add_output_arguments(verify)
    verify.add_argument(
        "--log-key",
        default="",
        help="a C2SP vkey supplied out of band; without it a key carried by the bundle "
        "itself yields PASS(self-asserted-key), which proves nothing about the log",
    )
    verify.add_argument(
        "--kms-pubkey",
        default="",
        help="ONLINE: KMS key id or ARN to fetch the public key from (default: offline)",
    )
    verify.add_argument(
        "--tile-url",
        default="",
        help="ONLINE: base URL for tlog-tiles fetches (default: offline)",
    )
    verify.add_argument(
        "--s3",
        action="store_true",
        help="ONLINE: compare the archive section against live object versions "
        "(default: offline, and check 8 reports SKIP(offline))",
    )
    verify.add_argument(
        "--redact-webauthn",
        action="store_true",
        help="treat the webauthn section as redacted; check 12 becomes SKIP(redacted) "
        "rather than vanishing",
    )

    audit = subcommands.add_parser(
        "receipt-audit",
        help="audit Signed Disposition Receipts against the bundle (checks 4 and 15)",
    )
    _add_bundle_argument(audit)
    _add_output_arguments(audit)
    audit.add_argument("--log-key", default="", help="a C2SP vkey supplied out of band")

    explain = subcommands.add_parser(
        "explain-check", help="print a check's registry row: what it proves, what it defeats"
    )
    explain.add_argument("check_id", type=int, help=f"one of {', '.join(map(str, CHECK_IDS))}")
    return parser


def _add_bundle_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bundle", required=True, help="path to an evidence bundle JSON file")


def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--colour",
        "--color",
        dest="colour",
        choices=("auto", "always", "never"),
        default="auto",
        help="FAIL and SKIP always share one colour weight; this only decides whether "
        "colour is emitted at all",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit the report as JSON instead of text"
    )


def _resolve_stream(stream: IO[str] | None) -> IO[str]:
    """Return the output stream, upgrading a real stdout to UTF-8 where the platform allows.

    A verifier that dies with ``UnicodeEncodeError`` on a legacy console has refused to
    report, which is indistinguishable from having found nothing. On Windows the default
    console encoding is still frequently cp1252 and this report — like the bundles it
    reads — carries em dashes, and may carry any Unicode at all in an ``origin`` or an
    ``actor``.
    """
    if stream is not None:
        return stream
    target = sys.stdout
    reconfigure = getattr(target, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(ValueError, OSError, AttributeError):
            reconfigure(encoding="utf-8", errors="replace")
    return target


def _write(stream: IO[str], text: str) -> None:
    """Write *text*, degrading unrepresentable characters rather than raising.

    The bundle is adversary-controlled input. A hostile ``origin`` full of astral
    characters must not be able to stop this tool from printing its findings.
    """
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, "replace").decode(encoding, "replace"))


def _preamble(load_report: LoadReport) -> tuple[str, ...]:
    """Say, above the rule, which check modules this build does not have."""
    missing = load_report.missing()
    if not missing:
        return ()
    lines = ["check modules absent from this build (their checks report SKIP below):"]
    lines.extend(f"  {entry.module} — {entry.reason}" for entry in missing)
    return tuple(lines)


def _emit(report: Report, *, as_json: bool, colour_choice: str, stream: IO[str]) -> int:
    if as_json:
        _write(stream, report.as_json_text())
    else:
        _write(stream, report.render(colour=want_colour(colour_choice, stream)))
    return report.exit_code


def _run_bundle_command(
    arguments: argparse.Namespace,
    *,
    only: tuple[int, ...] | None,
    stream: IO[str],
) -> int:
    load_report = load_all()
    try:
        bundle = load_bundle(arguments.bundle)
    except BundleError as exc:
        _write(stream, f"UNUSABLE  {exc}\n")
        _write(
            stream,
            "This is a finding about the file handed to the verifier, not about the log. "
            "No check ran, so no check passed.\n",
        )
        return EXIT_UNUSABLE

    options = VerifyOptions(
        log_key=getattr(arguments, "log_key", ""),
        kms_pubkey=getattr(arguments, "kms_pubkey", ""),
        tile_url=getattr(arguments, "tile_url", ""),
        s3=getattr(arguments, "s3", False),
        redact_webauthn=getattr(arguments, "redact_webauthn", False),
    )
    report = run_all(bundle, options, only=only, tool_version=__version__)
    report.preamble = _preamble(load_report)
    return _emit(report, as_json=arguments.json, colour_choice=arguments.colour, stream=stream)


def _explain(check_id: int, stream: IO[str]) -> int:
    load_all()
    try:
        spec = spec_for(check_id)
    except KeyError as exc:
        _write(stream, f"UNUSABLE  {exc}\n")
        return EXIT_UNUSABLE

    bound = check_id in registered()
    reach = "yes — needs no access to our database" if spec.offline else "no — needs --s3"
    binding = "RUNNER BOUND" if bound else "NO RUNNER — reports SKIP(not-implemented)"
    _write(
        stream,
        f"check {spec.id} — {spec.name}\n"
        f"  proves     {spec.proves}\n"
        f"  defeats    {spec.defeats}\n"
        f"  offline    {reach}\n"
        f"  module     {spec.module}\n"
        f"  test       {spec.test}\n"
        f"  owner      {spec.owner}\n"
        f"  registry   status={spec.status}, target={spec.target_status}\n"
        f"  this build {binding}\n",
    )
    if bound and check_id in SPEC_STATUS_LAG:
        _write(
            stream,
            "  note      spec/custody/checks.yaml still declares this check `deferred`. "
            "That file has one owner\n"
            "            and this package does not edit it; the discrepancy is recorded in "
            "checks.SPEC_STATUS_LAG\n"
            "            and asserted by tests/test_checks_totality.py rather than resolved "
            "by whichever answer looks better.\n",
        )
    return 0


def main(argv: list[str] | None = None, stream: IO[str] | None = None) -> int:
    """Parse *argv*, run the requested command, and return the process exit code."""
    out = _resolve_stream(stream)
    arguments = _build_parser().parse_args(argv)
    if arguments.command == "verify":
        return _run_bundle_command(arguments, only=None, stream=out)
    if arguments.command == "receipt-audit":
        return _run_bundle_command(arguments, only=_RECEIPT_AUDIT_CHECKS, stream=out)
    return _explain(arguments.check_id, out)


if __name__ == "__main__":  # pragma: no cover - exercised through `main` in tests
    sys.exit(main())
