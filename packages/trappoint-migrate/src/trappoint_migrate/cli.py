# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint`` — the substrate's command line.

One verb-first entry point. ``trappoint migrate …`` lives in this distribution;
``trappoint render …`` lives in ``packages/trappoint-sql`` and is dispatched to by
import. A verb whose distribution is not installed produces a sentence naming the
distribution, not an argparse error about an invalid choice — the reader of that
message is usually someone who has just cloned the repository.

Exit codes, and they are load-bearing for CI:

* ``0`` — the command did what it said.
* ``1`` — the runner **refused**, or the database did. This is the normal outcome of a
  red conformance run and of a lint that found something.
* ``2`` — the invocation was wrong. Distinguished from 1 so a wrapper cannot mistake
  "you typed it wrong" for "the schema is dirty" and retry forever.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg

from . import bookkeeping, fingerprint, grants, header, lockfile, runner
from .attest import SINK_FAILURES, chain_head, stable_fingerprint, verify_chain
from .attest import append as append_attestation
from .bootstrap import bootstrap, is_bootstrapped
from .crdb import pinned_image
from .db import connect
from .discovery import discover
from .errors import ClusterUnreachable, MigrateError, UsageError
from .lint import lint_paths

__all__ = ["main", "main_migrate"]

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

# Verbs owned by other distributions. Listed here so `trappoint --help` shows the whole
# surface even when only part of it is installed, which is the state a fresh clone is in.
_DELEGATES: dict[str, tuple[str, str, str]] = {
    "render": (
        "trappoint_sql.cli",
        "trappoint-sql",
        "render the kernel templates for a vertical binding",
    ),
}


def _repo_root(start: Path | None = None) -> Path:
    """Find the workspace root: the nearest ancestor holding both `spec/` and `compose.yaml`.

    Both, not either. `spec/` alone matches a checkout of the spec; `compose.yaml` alone
    matches half the repositories on a developer's laptop.
    """
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    return here


def _dsn(explicit: str | None) -> str:
    """Resolve the DSN: ``--dsn``, then ``TRAPPOINT_DSN``, then ``LOCAL_DSN``."""
    for value in (explicit, os.environ.get("TRAPPOINT_DSN"), os.environ.get("LOCAL_DSN")):
        if value:
            return value
    raise UsageError(
        "no DSN. Pass --dsn, or set TRAPPOINT_DSN or LOCAL_DSN. For the local "
        "single-node cluster: postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
    )


def _build_parser() -> argparse.ArgumentParser:  # noqa: PLR0915 - see the note below
    # One `add_parser` block per subcommand, in the order `--help` prints them. This
    # is long by construction and splitting it would be worse: a reader who wants to
    # know what `--strict-invariants` does should find it beside the command it
    # belongs to, not in a helper three functions away. The statement budget is the
    # only thing being exceeded; the cyclomatic complexity is one.
    parser = argparse.ArgumentParser(
        prog="trappoint migrate",
        description=(
            "Forward-only CockroachDB migrations: a real lock table, a dirty marker "
            "that refuses to advance, and a gap-free-by-CAS schema attestation chain."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def with_dsn(p: argparse.ArgumentParser) -> None:
        p.add_argument("--dsn", default=None, help="pgwire DSN (or $TRAPPOINT_DSN / $LOCAL_DSN)")

    def with_tree(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--tree",
            default="default",
            help="migration stream name, so two bindings can share one cluster",
        )
        p.add_argument(
            "--migrations",
            type=Path,
            default=None,
            help="directory of migration files (default: ./db/migrations under the repo root)",
        )

    p_boot = sub.add_parser(
        "bootstrap",
        help="create the `trappoint` bookkeeping schema (idempotent)",
        description=(
            "Creates schema_migration, schema_lock and schema_attestation in the "
            "`trappoint` schema, outside the numbered sequence (ruling D6), plus the "
            "immutable genesis attestation row."
        ),
    )
    with_dsn(p_boot)

    # `up` and `apply` are one command under two names. `docs/leads/datamodel.md` §1.3
    # publishes the interface as `apply · verify · fingerprint · attest · lint ·
    # grants apply`; the kernel shipped `up`, and every workflow in the repository and
    # every cluster's bookkeeping already names it. Renaming would be a breaking change
    # to a published surface in exchange for a synonym, so both spellings exist and
    # `apply` is documented as the alias rather than as a second implementation.
    for verb, blurb in (
        ("up", "apply every pending migration, forward only"),
        ("apply", "alias of `up` (docs/leads/datamodel.md §1.3 names the verb `apply`)"),
    ):
        p_up = sub.add_parser(verb, help=blurb)
        with_dsn(p_up)
        with_tree(p_up)
        p_up.add_argument(
            "--attest",
            choices=("each", "final"),
            default="each",
            help="append an attestation per file (default) or one for the whole run",
        )
        p_up.add_argument(
            "--plan-only",
            action="store_true",
            help="print what would be applied and exit without touching the schema",
        )
        p_up.add_argument(
            "--grants",
            type=Path,
            default=None,
            help=(
                "assert this GRANTS.yaml in the same invocation (DR-8: a restored "
                "cluster's schema is right and its privileges are absent until this runs)"
            ),
        )
        p_up.add_argument(
            "--allow-missing-grants",
            action="store_true",
            help="with --grants: report a grant whose object does not exist yet, do not refuse",
        )

    p_status = sub.add_parser("status", help="what is applied, pending, dirty, and attested")
    with_dsn(p_status)
    with_tree(p_status)

    p_attest = sub.add_parser(
        "attest",
        help="recompute the schema fingerprint and compare it with the chain head",
        description=(
            "Exits non-zero when the live schema disagrees with what the ledger says "
            "was applied. That is drift, and drift is an alarm rather than a warning."
        ),
    )
    with_dsn(p_attest)
    p_attest.add_argument(
        "--record-drift",
        action="store_true",
        help="append an `attest` row recording the drifted fingerprint (still exits non-zero)",
    )
    p_attest.add_argument(
        "--expect",
        default=None,
        help="assert the fingerprint equals this hex digest (the environment-parity gate)",
    )

    p_lint = sub.add_parser(
        "lint",
        help="the sequence ban (D10), the invariant-citation rule (§18), the header block",
    )
    p_lint.add_argument(
        "--root",
        type=Path,
        action="append",
        default=None,
        dest="roots",
        help="a migration or template tree; repeatable (default: every known tree)",
    )
    p_lint.add_argument(
        "--no-headers",
        action="store_true",
        help="skip the mandatory header block check (MI:/I:/COUNSEL-GATED:/RATIONALE:)",
    )
    p_lint.add_argument(
        "--strict-invariants",
        action="store_true",
        help=(
            "additionally refuse an `-- I:` citation outside I01-I16. Off by default: two "
            "files in this repository cite I17, and turning another lane red is that "
            "lane owner's decision"
        ),
    )

    p_verify = sub.add_parser(
        "verify",
        help="every hermetic and cluster-side check this runner can make, in one exit code",
        description=(
            "Lint the trees, assert the manifest is current, and — when a DSN is "
            "reachable — assert the bookkeeping is clean and the live schema matches the "
            "attestation head. Exit 1 on the first class of failure that would make a "
            "deploy dishonest."
        ),
    )
    with_dsn(p_verify)
    with_tree(p_verify)
    p_verify.add_argument(
        "--offline",
        action="store_true",
        help="file checks only; never open a connection",
    )

    p_fp = sub.add_parser(
        "fingerprint",
        help="the schema fingerprint: --tree (inputs, no cluster) or --live (the schema)",
        description=(
            "Two fingerprints. The TREE fingerprint hashes the migration and seed files "
            "and needs no database — DM-12's dev/demo/prod parity gate. The LIVE "
            "fingerprint hashes SHOW CREATE ALL SCHEMAS/TYPES/TABLES plus "
            "pg_get_triggerdef and pg_get_functiondef. Both are computed twice and "
            "refuse when the two computations disagree."
        ),
    )
    with_dsn(p_fp)
    p_fp.add_argument(
        "--live",
        action="store_true",
        help="fingerprint the live schema instead of the files (needs a DSN)",
    )
    p_fp.add_argument(
        "--root",
        type=Path,
        action="append",
        default=None,
        dest="roots",
        help="a tree of schema inputs; repeatable (default: every migration and seed tree)",
    )
    p_fp.add_argument(
        "--expect",
        default=None,
        help="assert the fingerprint equals this hex digest — the parity gate itself",
    )
    p_fp.add_argument(
        "--per-file",
        action="store_true",
        help="also print each input file's digest, so a divergence names a file",
    )

    p_lock = sub.add_parser(
        "lock",
        help="generate or check migrations.lock.json (MR-6: it is derived, never authored)",
    )
    p_lock.add_argument(
        "--migrations",
        type=Path,
        default=None,
        help="the migration tree (default: every verticals/*/db/migrations)",
    )
    p_lock.add_argument(
        "--write",
        action="store_true",
        help="regenerate the manifest in place",
    )

    p_grants = sub.add_parser(
        "grants",
        help="assert GRANTS.yaml: roles and grants are re-asserted state, not history (DM-7)",
    )
    p_grants.add_argument(
        "action",
        choices=("apply", "plan", "denials"),
        help="apply the matrix, print the SQL it would issue, or print the denial set",
    )
    with_dsn(p_grants)
    p_grants.add_argument(
        "--matrix",
        type=Path,
        default=None,
        help="path to GRANTS.yaml (default: every verticals/*/db/GRANTS.yaml)",
    )
    p_grants.add_argument(
        "--allow-missing",
        action="store_true",
        help=(
            "report, instead of refusing, a grant whose object does not exist yet. "
            "Legitimate while the tree is mid-build; a defect on a finished cluster"
        ),
    )

    p_force = sub.add_parser(
        "force",
        help="resolve a dirty version under a named incident",
        description=(
            "Refuses without --incident. A dirty schema is a custody event, so clearing "
            "one writes an attestation row that names who decided it was fine."
        ),
    )
    with_dsn(p_force)
    with_tree(p_force)
    p_force.add_argument("version", help="the version to resolve, e.g. 0071a_merge_record")
    p_force.add_argument(
        "--incident",
        required=True,
        help="incident identifier; this flag is the whole point of the subcommand",
    )
    p_force.add_argument(
        "--resolve",
        choices=("applied", "pending"),
        required=True,
        help="'applied' if the statement did take effect; 'pending' to re-apply it",
    )

    p_image = sub.add_parser(
        "image",
        help="print the pinned CockroachDB image (the one version constant)",
    )
    p_image.add_argument(
        "--compose",
        type=Path,
        default=None,
        help="path to compose.yaml (default: the repo root's)",
    )

    return parser


def _default_roots(root: Path) -> list[Path]:
    candidates = [
        root / "packages" / "trappoint-sql" / "refvertical" / "sql",
        root / "packages" / "trappoint-sql" / "templates",
    ]
    candidates.extend(sorted(root.glob("verticals/*/db/migrations")))
    return [c for c in candidates if c.exists()]


def _default_input_roots(root: Path) -> list[Path]:
    """Every tree the parity fingerprint covers: migrations and their seeds.

    Templates are deliberately absent. A template is an input to a *rendered file*, and
    the rendered file is already hashed here; including both would make a template edit
    move the digest twice and a re-render move it once, so the two would disagree in the
    window between them.
    """
    candidates = [
        *sorted(root.glob("verticals/*/db/migrations")),
        *sorted(root.glob("verticals/*/db/seeds")),
        root / "packages" / "trappoint-sql" / "refvertical" / "sql",
    ]
    return [c for c in candidates if c.exists()]


def _default_matrices(root: Path) -> list[Path]:
    return sorted(root.glob("verticals/*/db/GRANTS.yaml"))


def _default_migration_trees(root: Path) -> list[Path]:
    return sorted(root.glob("verticals/*/db/migrations"))


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    with connect(_dsn(args.dsn)) as conn:
        ensured = bootstrap(
            conn,
            applied_by=runner.actor(),
            schema_prefixes=runner.DEFAULT_SCHEMA_PREFIXES,
        )
    print("bootstrapped: " + ", ".join(ensured))
    return EXIT_OK


def _cmd_up(args: argparse.Namespace, root: Path) -> int:
    migrations = args.migrations or (root / "db" / "migrations")
    # DM-14, before anything opens a socket. A down migration discovered halfway through
    # an apply has already dropped something.
    runner.assert_above_protected_floor(migrations)
    with connect(_dsn(args.dsn)) as conn:
        if args.plan_only:
            current = runner.plan(conn, tree=args.tree, root=migrations)
            print(f"tree {current.tree} · {migrations}")
            print(f"applied: {sum(1 for r in current.applied if r.state == 'applied')}")
            for row in current.unresolved:
                print(f"  UNRESOLVED {row.version} [{row.state}] {row.failure or ''}")
            for migration in current.pending:
                print(f"  pending   {migration.version}  sha256={migration.sha256.hex()[:16]}…")
            if current.is_noop:
                print("nothing to apply")
            return EXIT_OK

        result = runner.apply(
            conn,
            tree=args.tree,
            root=migrations,
            attest_each=args.attest == "each",
        )
        # DR-8: a RESTORE carries the schema and not the grants, so `apply` must be able
        # to assert the matrix in the SAME invocation. Opt-in rather than implicit,
        # because the reference-vertical lane applies a tree that has no matrix beside it.
        asserted: grants.ApplyResult | None = None
        if args.grants is not None:
            asserted = grants.apply(
                conn, grants.plan(args.grants), allow_missing=args.allow_missing_grants
            )

    if not result.applied:
        print(f"tree {result.tree}: nothing to apply ({migrations})")
    else:
        print(f"tree {result.tree}: applied {len(result.applied)} migration(s)")
        for version in result.applied:
            print(f"  + {version}")
        if result.final_fingerprint is not None:
            print(
                f"fingerprint {result.final_fingerprint.hex()} "
                f"(grade {result.grade}, attestation ordinal "
                f"{result.attestation_ordinals[-1]})"
            )
    if asserted is not None:
        print(f"grants: {len(asserted.applied)} statement(s) asserted from {args.grants}")
        for skipped in asserted.missing_objects:
            print(f"  skipped (object absent) {skipped}")
    for failure in SINK_FAILURES:
        print(f"  ! ledger sink failed: {failure}")
    return EXIT_OK


def _cmd_status(args: argparse.Namespace, root: Path) -> int:
    migrations = args.migrations or (root / "db" / "migrations")
    with connect(_dsn(args.dsn)) as conn:
        if not is_bootstrapped(conn):
            print("not bootstrapped: run `trappoint migrate bootstrap`")
            return EXIT_REFUSED
        current = runner.plan(conn, tree=args.tree, root=migrations)
        head = chain_head(conn)
        findings = verify_chain(conn)

    applied = [r for r in current.applied if r.state == "applied"]
    print(f"tree {current.tree} · {migrations}")
    print(f"  applied     {len(applied)}")
    print(f"  pending     {len(current.pending)}")
    print(f"  unresolved  {len(current.unresolved)}")
    for row in current.unresolved:
        print(f"    ! {row.version} [{row.state}] {row.failure_sqlstate or ''} {row.failure or ''}")
    for migration in current.pending:
        print(f"    + {migration.version}")
    print(
        f"  attestation head: ordinal {head.ordinal} kind {head.kind} "
        f"grade {head.grade} · {head.fingerprint.hex()}"
    )
    for failure in SINK_FAILURES:
        print(f"  ! ledger sink failed: {failure}")
    if findings:
        print("  CHAIN FINDINGS:")
        for finding in findings:
            print(f"    ! {finding}")
        return EXIT_REFUSED
    print("  chain intact (dense, and every prev_fingerprint matches its predecessor)")
    return EXIT_OK if not current.unresolved else EXIT_REFUSED


def _cmd_attest(args: argparse.Namespace) -> int:
    with connect(_dsn(args.dsn)) as conn:
        computed = stable_fingerprint(conn, schema_prefixes=runner.DEFAULT_SCHEMA_PREFIXES)
        head = chain_head(conn)
        drifted = computed.digest != head.fingerprint
        if drifted and args.record_drift:
            append_attestation(
                conn,
                kind="attest",
                tree="-",
                version="drift",
                attestation=computed,
                applied_by=runner.actor(),
            )

    print(f"fingerprint {computed.digest.hex()}")
    print(f"grade       {computed.grade} (covers: {', '.join(computed.parts)})")
    print(f"chain head  ordinal {head.ordinal} · {head.fingerprint.hex()}")

    if args.expect is not None and args.expect.lower() != computed.digest.hex():
        print(f"PARITY FAILED: expected {args.expect.lower()}")
        return EXIT_REFUSED
    if drifted:
        print(
            "DRIFT: the live schema does not match the attestation head. Something "
            "changed the schema outside this runner, or the chain was edited."
        )
        return EXIT_REFUSED
    print("no drift")
    return EXIT_OK


def _header_findings(roots: Sequence[Path], *, strict: bool) -> list[str]:
    """Return header-block findings per tree, resolved against that tree's MI catalogue."""
    rendered: list[str] = []
    for tree in roots:
        if not tree.is_dir():
            continue
        catalogue = header.find_catalogue(tree)
        known = header.catalogue_ids(catalogue) if catalogue is not None else None
        for path in sorted(tree.rglob("*.sql")):
            if not path.is_file() or path.name.endswith(".j2"):
                continue
            findings = header.header_findings(
                path,
                path.read_text(encoding="utf-8"),
                known_mi_ids=known or None,
                strict_trappoint_ids=strict,
            )
            rendered.extend(finding.render() for finding in findings)
    return rendered


def _cmd_lint(args: argparse.Namespace, root: Path) -> int:
    roots: list[Path] = list(args.roots or _default_roots(root))
    report = lint_paths(roots)
    for finding in report.findings:
        print(finding.render())

    header_lines: list[str] = []
    if not args.no_headers:
        header_lines = _header_findings(roots, strict=args.strict_invariants)
        for line in header_lines:
            print(line)

    scanned = ", ".join(str(r) for r in roots) or "(no tree exists yet)"
    print(f"lint: {report.files_checked} file(s) checked in {scanned}")
    total = len(report.findings) + len(header_lines)
    if total == 0:
        print(
            "lint: no findings — no sequence, every migration cites an invariant, and "
            "every header answers MI/I/COUNSEL-GATED/RATIONALE"
        )
        return EXIT_OK
    print(f"lint: {total} finding(s)")
    return EXIT_REFUSED


def _cmd_fingerprint(args: argparse.Namespace, root: Path) -> int:
    if args.live:
        with connect(_dsn(args.dsn)) as conn:
            computed = fingerprint.live_fingerprint(
                conn, schema_prefixes=runner.DEFAULT_SCHEMA_PREFIXES
            )
        digest = computed.digest.hex()
        print(f"live fingerprint {digest}")
        print(f"grade            {computed.grade} (covers: {', '.join(computed.parts)})")
    else:
        roots = list(args.roots or _default_input_roots(root))
        if not roots:
            raise UsageError(
                "no schema input tree exists yet. Pass --root, or render a binding first: "
                "the parity gate hashes files, and there are none."
            )
        tree = fingerprint.stable_tree_fingerprint(roots)
        digest = tree.hex
        print(f"tree fingerprint {digest}")
        print(f"inputs           {len(tree.files)} file(s) in {', '.join(tree.roots)}")
        if args.per_file:
            for entry in tree.files:
                print(f"  {entry.digest.hex()[:16]}… {entry.relpath}")

    if args.expect is not None and args.expect.lower() != digest:
        print(f"PARITY FAILED: expected {args.expect.lower()}")
        return EXIT_REFUSED
    if args.expect is not None:
        print("parity holds")
    return EXIT_OK


def _cmd_lock(args: argparse.Namespace, root: Path) -> int:
    trees = [args.migrations] if args.migrations is not None else _default_migration_trees(root)
    if not trees:
        raise UsageError(
            "no migration tree found. Pass --migrations, or run from the repository root."
        )
    findings: list[str] = []
    for tree in trees:
        path = lockfile.lock_path_for(tree)
        if args.write:
            document = lockfile.build_lock(tree, repo_root=root)
            lockfile.write_lock(path, document)
            counts = document["counts"]
            print(
                f"wrote {path} — {counts['files']} file(s), {counts['rendered']} rendered, "
                f"{counts['authored']} authored, {counts['counsel_gated']} counsel-gated"
            )
            continue
        tree_findings = lockfile.verify_lock(path, tree, repo_root=root)
        for finding in tree_findings:
            print(f"  ! {finding}")
        findings.extend(tree_findings)
        if not tree_findings:
            print(f"{path} is current")
    return EXIT_OK if not findings else EXIT_REFUSED


def _cmd_grants(args: argparse.Namespace, root: Path) -> int:
    matrices = [args.matrix] if args.matrix is not None else _default_matrices(root)
    if not matrices:
        raise UsageError(
            "no GRANTS.yaml found. Pass --matrix, or run from the repository root. Roles "
            "and grants are cluster state a RESTORE does not carry (DM-7)."
        )

    if args.action == "denials":
        for matrix in matrices:
            print(f"# {matrix}")
            for denial in grants.denials(matrix):
                print(
                    f"{denial.role}: {', '.join(denial.forbidden)} on {denial.scope} "
                    f"-> expect {denial.expect_sqlstate}"
                )
        return EXIT_OK

    if args.action == "plan":
        for matrix in matrices:
            plan_for = grants.plan(matrix)
            print(f"# {matrix}")
            print(plan_for.render())
            for line in grants.describe(plan_for):
                print(f"# {line}")
        return EXIT_OK

    with connect(_dsn(args.dsn)) as conn:
        for matrix in matrices:
            plan_for = grants.plan(matrix)
            result = grants.apply(conn, plan_for, allow_missing=args.allow_missing)
            print(f"{matrix}: {len(result.applied)} statement(s) asserted")
            for skipped in result.missing_objects:
                print(f"  skipped (object absent) {skipped}")
            for line in grants.describe(plan_for):
                print(f"  {line}")
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace, root: Path) -> int:  # noqa: PLR0912
    """Run every check this runner can make, and return one exit code.

    The branch count is one `if` per *class of failure*, and each of them prints a
    different sentence. Collapsing them into a loop over a table of checks would make
    the failure messages generic, and the failure message is the product here.

    Ordered cheapest-and-most-fundamental first. A tree that does not lint is not a tree
    whose manifest is worth comparing, and a manifest that is stale makes a fingerprint
    a statement about files nobody has enumerated.
    """
    failures: list[str] = []

    report = lint_paths(_default_roots(root))
    header_lines = _header_findings(_default_roots(root), strict=False)
    print(f"lint         {report.files_checked} file(s), {len(report.findings)} finding(s)")
    for finding in report.findings:
        print(f"  ! {finding.render()}")
    for line in header_lines:
        print(f"  ! {line}")
    if report.findings or header_lines:
        failures.append("lint")

    for tree in _default_migration_trees(root):
        lock_findings = lockfile.verify_lock(lockfile.lock_path_for(tree), tree, repo_root=root)
        print(f"manifest     {tree}: {len(lock_findings)} finding(s)")
        for stale in lock_findings:
            print(f"  ! {stale}")
        if lock_findings:
            failures.append("manifest")

    for tree in _default_migration_trees(root):
        floor = runner.protected_floor_violations(tree)
        for violation in floor:
            print(f"  ! {violation}")
        if floor:
            failures.append("protected-floor")
    print(f"floor        {runner.PROTECTED_FLOOR[0]:04d}{runner.PROTECTED_FLOOR[1]} (DM-14)")

    if not args.offline:
        with connect(_dsn(args.dsn)) as conn:
            status = bookkeeping.inspect(conn, tree=args.tree)
            for line in status.render():
                print(line)
            if not status.is_clean:
                failures.append("bookkeeping")
            if status.bootstrapped:
                computed = stable_fingerprint(conn, schema_prefixes=runner.DEFAULT_SCHEMA_PREFIXES)
                head = chain_head(conn)
                print(f"  live        {computed.digest.hex()} (grade {computed.grade})")
                if computed.digest != head.fingerprint:
                    print("  ! DRIFT: the live schema does not match the attestation head")
                    failures.append("drift")

    if failures:
        print(f"verify: REFUSED — {', '.join(sorted(set(failures)))}")
        return EXIT_REFUSED
    print("verify: every check this runner can make passes")
    return EXIT_OK


def _cmd_force(args: argparse.Namespace, root: Path) -> int:
    migrations = args.migrations or (root / "db" / "migrations")
    _ = discover(migrations)  # validate the tree before mutating bookkeeping
    with connect(_dsn(args.dsn)) as conn:
        ordinal = runner.force(
            conn,
            tree=args.tree,
            version=args.version,
            incident_id=args.incident,
            resolve_to=args.resolve,
        )
    print(
        f"forced {args.tree}/{args.version} -> {args.resolve} under incident "
        f"{args.incident}; attestation ordinal {ordinal}"
    )
    return EXIT_OK


def _cmd_image(args: argparse.Namespace, root: Path) -> int:
    compose = args.compose or (root / "compose.yaml")
    print(pinned_image(compose))
    return EXIT_OK


def main_migrate(argv: Sequence[str] | None = None) -> int:  # noqa: PLR0911, PLR0912, RET503
    """Entry point for ``trappoint migrate`` (and the ``trappoint-migrate`` alias).

    One return per subcommand plus one per failure class. Replacing the chain with a
    dispatch table would move the branching into a dictionary literal without removing
    any of it, and would hide which failures map to which exit code — and the exit code
    is what CI branches on.
    """
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    root = _repo_root()
    try:
        if args.command == "bootstrap":
            return _cmd_bootstrap(args)
        if args.command in {"up", "apply"}:
            return _cmd_up(args, root)
        if args.command == "status":
            return _cmd_status(args, root)
        if args.command == "attest":
            return _cmd_attest(args)
        if args.command == "lint":
            return _cmd_lint(args, root)
        if args.command == "verify":
            return _cmd_verify(args, root)
        if args.command == "fingerprint":
            return _cmd_fingerprint(args, root)
        if args.command == "lock":
            return _cmd_lock(args, root)
        if args.command == "grants":
            return _cmd_grants(args, root)
        if args.command == "force":
            return _cmd_force(args, root)
        if args.command == "image":
            return _cmd_image(args, root)
    except UsageError as exc:
        print(f"trappoint migrate: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except ClusterUnreachable as exc:
        # Not a refusal by the gate. Saying so keeps "the database said no" distinct
        # from "there was no database" — a distinction a red-before-green lane needs.
        print(f"trappoint migrate: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except MigrateError as exc:
        print(f"trappoint migrate: REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except psycopg.Error as exc:
        state = exc.diag.sqlstate if exc.diag is not None else None
        print(
            f"trappoint migrate: the database refused [{state or 'no-sqlstate'}]: "
            f"{str(exc).strip()}",
            file=sys.stderr,
        )
        return EXIT_REFUSED
    except OSError as exc:
        print(f"trappoint migrate: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    # argparse was configured with `required=True`, so an unrecognised subcommand never
    # reaches here; `parser.error` exits with status 2 and does not return.
    parser.error(f"unhandled command {args.command!r}")


def _top_level_help() -> str:
    lines = [
        "usage: trappoint <verb> [...]",
        "",
        "The TRAPPOINT substrate command line.",
        "",
        "verbs:",
        "  migrate   apply schema migrations and write the schema attestation",
    ]
    for verb, (_, dist, summary) in sorted(_DELEGATES.items()):
        lines.append(f"  {verb:<9} {summary}  [{dist}]")
    lines += [
        "",
        "Run `trappoint <verb> --help` for a verb's own options.",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``trappoint`` console script."""
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args or args[0] in {"-h", "--help", "help"}:
        print(_top_level_help())
        return EXIT_OK

    verb, rest = args[0], args[1:]
    if verb == "migrate":
        return main_migrate(rest)

    delegate = _DELEGATES.get(verb)
    if delegate is not None:
        module_name, distribution, _ = delegate
        try:
            module = __import__(module_name, fromlist=["main"])
        except ImportError:
            print(
                f"trappoint: the `{verb}` verb lives in the `{distribution}` "
                f"distribution, which is not installed in this environment.\n"
                f"  uv sync --package {distribution}",
                file=sys.stderr,
            )
            return EXIT_USAGE
        delegate_main = module.main
        return int(delegate_main(rest))

    print(f"trappoint: unknown verb {verb!r}\n", file=sys.stderr)
    print(_top_level_help(), file=sys.stderr)
    return EXIT_USAGE
