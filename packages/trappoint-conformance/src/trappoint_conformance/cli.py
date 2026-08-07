# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-conform`` — run the suite and say exactly what happened.

```bash
trappoint-conform --profile trappoint-ref --list          # no database needed
trappoint-conform --dsn "$LOCAL_DSN" --profile trappoint-ref
```

The exit code is the claim. Non-zero means at least one history was not refused the way
the specification says it must be, and today that is the correct and expected state:
``CF-01`` is red because the schema that would satisfy it does not exist yet.

A claim of conformance **must cite version and profile**. The summary line always
carries both, so a screenshot of it is a complete claim rather than half of one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .manifest import ManifestError, load_manifest
from .runner import PROFILE_SCHEMA, Status, implemented_case_ids, resolve_schema, run

__all__ = ["main"]

EXIT_OK = 0
EXIT_RED = 1
EXIT_USAGE = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trappoint-conform",
        description=(
            "Run the TRAPPOINT conformance suite: illegal histories, each asserting an "
            "exact SQLSTATE and an exact exhibit name."
        ),
        epilog=(
            "A green run entitles you to say the database refused every history the "
            "specification says it must, by the exact mechanism it names, at the named "
            "profile and version. It entitles you to say nothing else. "
            "See spec/conformance/README.md §9."
        ),
    )
    parser.add_argument("--dsn", default=None, help="pgwire DSN (or $TRAPPOINT_DSN / $LOCAL_DSN)")
    parser.add_argument(
        "--profile",
        default="trappoint-ref",
        help=f"binding profile ({', '.join(sorted(PROFILE_SCHEMA))})",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="override the SQL schema the profile maps to",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="path to spec/conformance/manifest.toml (default: the nearest one above cwd)",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=None,
        dest="cases",
        help="run only this case id; repeatable",
    )
    parser.add_argument(
        "--requires",
        action="append",
        default=None,
        dest="satisfied",
        help="declare a capability token as satisfied; repeatable",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="pin the tenancy scope so a re-run lands on the same rows",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the cases selected for the profile and exit, without a database",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable results")
    return parser


def _dsn(explicit: str | None) -> str | None:
    for value in (explicit, os.environ.get("TRAPPOINT_DSN"), os.environ.get("LOCAL_DSN")):
        if value:
            return value
    return None


def _list(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    selected = manifest.for_profile(args.profile)
    implemented = implemented_case_ids()
    if args.json:
        print(
            json.dumps(
                {
                    "profile": args.profile,
                    "spec_version": manifest.spec_version,
                    "selected": len(selected),
                    "implemented": sorted(c.id for c in selected if c.id in implemented),
                    "pending": sorted(c.id for c in selected if c.id not in implemented),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return EXIT_OK

    print(f"manifest {manifest.path}")
    print(f"spec {manifest.spec_version} · profile {args.profile} · {len(selected)} case(s)")
    for case in selected:
        mark = "impl" if case.id in implemented else "pend"
        requires = f"  requires={','.join(case.requires)}" if case.requires else ""
        print(
            f"  [{mark}] {case.id}  {case.expect_sqlstate:<6} {case.expect_constraint}"
            f"  depth>={case.refusal_depth_min}{requires}"
        )
        print(f"         {case.title}")
    print(f"implemented {sum(1 for c in selected if c.id in implemented)} / {len(selected)}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``trappoint-conform``."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])

    try:
        resolve_schema(args.profile, args.schema)
    except ValueError as exc:
        print(f"trappoint-conform: {exc}", file=sys.stderr)
        return EXIT_USAGE

    try:
        if args.list:
            return _list(args)
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"trappoint-conform: {exc}", file=sys.stderr)
        return EXIT_USAGE

    dsn = _dsn(args.dsn)
    if dsn is None:
        print(
            "trappoint-conform: no DSN. Pass --dsn, or set TRAPPOINT_DSN or LOCAL_DSN.\n"
            '  just up && trappoint-conform --dsn "$(just dsn)" --profile trappoint-ref',
            file=sys.stderr,
        )
        return EXIT_USAGE

    # Imported here so `--list` and `--help` work in an environment where the driver's
    # binary wheel is unavailable. Listing the suite is a documentation act; it must not
    # need a database driver.
    import psycopg

    try:
        conn = psycopg.connect(dsn, autocommit=True, application_name="trappoint-conform")
    except psycopg.Error as exc:
        # Not a refusal. "There was no database" and "the database said no" are
        # different sentences and the exit path says which one happened.
        print(f"trappoint-conform: cannot connect: {exc}".strip(), file=sys.stderr)
        return EXIT_RED

    try:
        report = run(
            manifest,
            profile=args.profile,
            conn=conn,
            schema=args.schema,
            only=frozenset(args.cases) if args.cases else None,
            satisfied_requirements=args.satisfied or (),
            run_id=args.run_id,
        )
    finally:
        conn.close()

    if args.json:
        print(
            json.dumps(
                {
                    "profile": report.profile,
                    "schema": report.schema,
                    "spec_version": report.spec_version,
                    "run_id": report.run_id,
                    "summary": report.summary(),
                    "green": report.is_green,
                    "results": [
                        {
                            "id": r.case.id,
                            "status": r.status.value,
                            "expect_sqlstate": r.case.expect_sqlstate,
                            "expect_constraint": r.case.expect_constraint,
                            "observed_sqlstate": (
                                r.observed.sqlstate if r.observed is not None else None
                            ),
                            "observed_constraint": (
                                r.observed.constraint if r.observed is not None else None
                            ),
                            "exhibit_weakened": (
                                r.observed.exhibit_weakened if r.observed is not None else False
                            ),
                            "detail": r.detail,
                        }
                        for r in report.results
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for result in report.results:
            if result.status is Status.PENDING:
                continue
            print(result.render())
        pending = report.count(Status.PENDING)
        if pending:
            print(
                f"PEND  {pending} case(s) declared in the manifest have no implementation "
                "yet; the conformance corpus owns them and test_manifest_totality will "
                "make their absence fatal."
            )
        print("")
        print(report.summary())

    return EXIT_OK if report.is_green else EXIT_RED
