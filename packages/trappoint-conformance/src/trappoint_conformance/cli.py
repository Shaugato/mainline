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

**Nothing runs until the corpus is imported.** ``cases.load_all()`` is what turns a
directory of modules into entries in the runner's registry, and until 2026-08-10 this
file never called it: seventy implementations existed, imported cleanly, and reported
``PENDING`` — ``implemented 1 / 71`` — because nothing had imported them. A tool that
reports "not implemented" for code that is sitting in the tree is worse than one that
crashes, so an import failure here is now a **fatal, named error** and never a silent
seventy PENDINGs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

# `capability` imports the standard library and nothing else — no driver — so importing it
# here keeps the promise two paragraphs up: `--list` and `--help` must work in an
# environment where psycopg's binary wheel is unavailable.
from .capability import CapabilityReport
from .manifest import Manifest, ManifestError, load_manifest
from .runner import PROFILE_SCHEMA, Status, resolve_schema, run

__all__ = ["main"]

EXIT_OK = 0
EXIT_RED = 1
EXIT_USAGE = 2


class CorpusUnimportable(Exception):
    """``import cases`` failed, or a case module raised on import.

    Fatal, and reported as itself. The alternative — carrying on with an empty registry —
    prints a report in which every unimplemented-looking case is actually an unimported
    one, and the two are indistinguishable to a reader.
    """


def _load_corpus() -> frozenset[str]:
    """Import every case module and return the ids now implemented.

    Raises:
        CorpusUnimportable: the corpus package is not installed, or a case module raised.
    """
    try:
        # `cases` ships no `py.typed` — it is the corpus, not a library anyone type-checks
        # against — so mypy is told the import is untyped rather than left to guess.
        import cases  # type: ignore[import-untyped]
    except ImportError as exc:
        raise CorpusUnimportable(
            f"cannot import the conformance corpus: {exc}. The `cases` package ships with "
            f"the `trappoint-conformance` distribution — check "
            f"[tool.hatch.build.targets.wheel].packages in its pyproject.toml lists "
            f"`cases`, and reinstall (`pip install -e packages/trappoint-conformance`). "
            f"Without it the registry holds one case and every other case reports PENDING."
        ) from exc
    try:
        return frozenset(cases.load_all())
    except Exception as exc:  # any import-time failure is the same fatality; re-raised below
        raise CorpusUnimportable(
            f"the conformance corpus failed to load: {type(exc).__name__}: {exc}. One case "
            f"module raised while being imported, so the corpus is incomplete and the "
            f"registry cannot be trusted to say what is implemented."
        ) from exc


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
        "--autodetect-requires",
        action="store_true",
        dest="autodetect",
        help=(
            "resolve every `requires` token against the live database (pg_class, "
            "pg_roles, pg_policies) instead of taking a human's word for it. Any "
            "--requires you also pass still wins and is additive. An unsatisfied token "
            "becomes CANNOT RUN with the missing object named, never a bare `requires X`."
        ),
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
    # THE LOADER CALL. Without it `implemented_case_ids()` returns the one case the runner
    # registers itself and the listing is a lie about the tree it was run in.
    implemented = _load_corpus()
    if args.autodetect:
        print(
            "trappoint-conform: --autodetect-requires needs a database and --list does "
            "not open one; capability tokens are listed unresolved.",
            file=sys.stderr,
        )
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


def _probe(args: argparse.Namespace, manifest: Manifest, conn: object) -> CapabilityReport:
    """Resolve every capability token the selected cases declare, against *conn*.

    Tokens a human passed with ``--requires`` are probed too, and deliberately: if the
    cluster disagrees with the declaration the probe still records what it found, and the
    declaration still wins (it is unioned into the satisfied set by the caller). Somebody
    who insists a token is satisfied gets to insist; nobody gets to make the report
    silent about the object.
    """
    from .capability import probe

    selected = manifest.for_profile(args.profile)
    only = frozenset(args.cases) if args.cases else None
    tokens = sorted(
        {token for case in selected if only is None or case.id in only for token in case.requires}
    )
    return probe(conn, tokens, schema=resolve_schema(args.profile, args.schema))


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
        _load_corpus()
    except ManifestError as exc:
        print(f"trappoint-conform: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except CorpusUnimportable as exc:
        # Not a red gate and not a usage error: the runner is broken. Named, fatal, and
        # never dressed up as seventy unimplemented cases.
        print(f"trappoint-conform: CORPUS NOT LOADED — {exc}", file=sys.stderr)
        return EXIT_RED

    return _execute(args, manifest)


def _execute(args: argparse.Namespace, manifest: Manifest) -> int:
    """Connect, probe, run, print. Split out of :func:`main` so each half stays readable."""
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

    declared = tuple(args.satisfied or ())
    try:
        capabilities = _probe(args, manifest, conn) if args.autodetect else None
        satisfied = declared + tuple(sorted(capabilities.satisfied)) if capabilities else declared
        report = run(
            manifest,
            profile=args.profile,
            conn=conn,
            schema=args.schema,
            only=frozenset(args.cases) if args.cases else None,
            satisfied_requirements=satisfied,
            requirement_reasons=capabilities.reasons() if capabilities else None,
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
                    "capabilities": (
                        None
                        if capabilities is None
                        else {
                            "database": capabilities.database,
                            "schema": capabilities.schema,
                            "probed": [
                                {
                                    "token": c.token,
                                    "kind": c.kind,
                                    "object": c.object_name,
                                    "satisfied": c.satisfied,
                                    "detail": c.detail,
                                    "reason": c.reason,
                                }
                                for c in capabilities.capabilities
                            ],
                        }
                    ),
                    "declared_requires": list(declared),
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
        if capabilities is not None:
            print(capabilities.summary())
            for capability in capabilities.unsatisfied:
                print(f"  CAP-  {capability.token}  {capability.reason}")
            print("")
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


if __name__ == "__main__":  # pragma: no cover — exercised by tests/test_runner_wiring.py
    # `python -m trappoint_conformance.cli` and the `trappoint-conform` console script are
    # the same entry point. The module form is what a test can invoke without depending on
    # a script shim existing on PATH, and what a reader can invoke when it does not.
    sys.exit(main())
