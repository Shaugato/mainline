# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The cluster, the schema, the seeded history, and a validator for the console's contracts.

FOUR THINGS THIS FILE PROVIDES, AND THE REASON EACH IS SHAPED THE WAY IT IS.

**1. A shared cluster, obtained the way the rest of the repository obtains one.**
``packages/trappoint-testkit`` publishes the session's DSN under four environment names
and skips with a written reason when there is none. This file reads those names and then
``127.0.0.1:26257``, and it never starts a container of its own — ``--crdb=reuse`` is the
convention, and thirteen private nodes is what happens when a module decides it is
special. **Every skip carries the reason it skipped.** A skip with no reason is
indistinguishable from a deleted test, which is the failure mode that lets a suite go
green while asserting nothing.

**2. A migrated database, cached by the fingerprint of everything that builds it.**
Applying 271 files takes 46.7 s on this machine, which is fine once and intolerable per
run. The database is named for the SHA-256 of every migration's name and bytes **and of
the seed files' names and bytes**, so a second run reuses it while a single edited
migration — or a single edited line of ``demo_world.sql`` — builds a new one. The marker
table ``w3_fixture.ready`` carries the fingerprint AND the seeded identifiers, so a reused
database hands back the same permit id it was seeded with rather than being re-seeded.
**A marker is a claim that the database was built, never that it is still usable**, so it
is checked against the rows before it is believed: the seeded history's one perishable row
is the exposure receipt, and a database adopted after its window closed carries a dead one.

**3. The seeded history is THE SEED THE DEPLOYMENT APPLIES, and nothing else.**
``scripts/deploy/seed_demo.py`` applies ``demo_world.sql`` then ``demo_permit.sql`` to
CockroachDB Cloud. This fixture applies the same two files, in the same order, through
the same ``cloud_chain.Applier`` and its ``40001`` retry loop, and it obtains the file
list by **importing** ``SEED_FILES`` rather than restating it. Every identifier the
``seed`` dict hands out is then read back out of the seeded database with a query.

This file used to build a parallel world instead: its own site, its own signer, and a
credential id it computed as a SHA-256 over two hardcoded words — by *the same helper the
code under test used*. The test and the code agreed because they read one constant;
neither had ever met the file the deployment applies, which derives that credential from
``digest('mainline-demo/credential/demo.signer', 'sha256')``. So beat 4 of the demo failed
``23503 disposition_signer_credential_id_fkey`` against the deployed database while 291
tests here stayed green. That is the third recurrence of one shape — the permit-id
near-miss and the ``dict_row`` 500 were the first two. **A test that cannot disagree with
the code it tests proves nothing**, and the only way to make disagreement possible is for
the fixture's world and the deployed world to be one world.

**WHAT THIS FIXTURE MAY THEREFORE NOT DO: add a row the deployed seed does not carry.**
``demo_permit.sql`` says the database holds *exactly one gated subject*, and
``demo_world.sql``'s closing census enumerates the rest. Where a read surface has no rows
in the deployed database it has none here either, and the test that wanted them fails —
loudly, naming the table. That failure is the fixture working: it is a gap in what the
demo deploys, and it belongs to the seed's owner, not to a fixture quietly minting the
row so the suite stays green. ``_Seed.__missing__`` below says so at the point of use.

**4. A JSON Schema validator, over the contract files the CONSOLE loads.**
``jsonschema`` is not installed in this repository's virtualenv and installing it would
change shared state no worker owns. So the subset of draft 2020-12 that
``console/contracts/*.schema.json`` actually uses is implemented here — twenty-four
keywords, enumerated by walking the sixteen documents — and it reads the very files
``src/data/schema.ts`` reads. Validating against a re-typed copy would be testing the
copy.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import sys
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final
from urllib.parse import urldefrag, urljoin

import pytest

# The distribution is not installed — `verticals/*/apps/*` is deliberately absent from
# the root workspace's member globs, because the console beside it is a pnpm workspace
# and mixing a TypeScript SPA into `uv.lock` would make the Python resolution depend on
# a toolchain that has nothing to do with it. So `src` goes on the path here rather than
# into the shared virtualenv, which no worker owns.
_TESTS = Path(__file__).resolve().parent
_SRC = _TESTS.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

# ── `from conftest import …`, and why this file has to defend that name ─────────────
#
# `test_envelope.py`, `test_reads.py` and `test_routes_gate_run.py` each open with a
# bare `from conftest import …`. That is a top-level absolute import, so it resolves
# through `sys.modules["conftest"]` — ONE slot, shared by all 55 conftest.py files in
# this repository, none of which sits in a package. pytest knows this and handles it
# for the ordinary case: `PytestPluginManager._importconftest` does
# `del sys.modules["conftest"]` before importing the next one, so the module a test
# imports is the one pytest loaded a moment earlier for that test's own directory.
#
# THAT GUARANTEE HOLDS ONLY FOR A CONFTEST LOADED DURING DESCENT. When this directory
# is named in `testpaths` — which, as of 2026-08-13, it is — it becomes an *initial
# argument*, and pytest loads its conftest up front via `_try_load_conftest`. By the
# time collection actually reaches these modules, `_importconftest` short-circuits on
# `self.get_plugin(str(conftestpath))` and returns the cached plugin WITHOUT touching
# `sys.modules` again, while every conftest imported during the intervening descent
# through `tests/` and `packages/` has taken the slot in turn. Measured the moment the
# testpath landed, before this hook existed:
#
#     ImportError: cannot import name 'RESOURCES_TS' from 'conftest'
#         (D:\...\packages\trappoint-sql\tests\conftest.py)
#
# — three collection errors, in a suite that collects clean when invoked by path.
# `packages/mainline-mcp/tests`, `tests/unit/moc_stream` and
# `tests/integration/recall_lexical` do the same bare import and carry the same latent
# fault; it is invisible to them only because they are reached by descent. Naming any
# two of them on one command line reproduces it today.
#
# So the name is claimed for exactly as long as a collector under this directory is
# being collected, and handed straight back. `pytest_collectstart` and
# `pytest_collectreport` bracket `collector.collect()` in `runner.collect_one_node`,
# which is where a Module's import happens, and a conftest's collection hooks fire only
# for nodes beneath its own directory — so the window is precisely the import of this
# directory's modules and nothing else in the session. Setting the name once at import time
# would not survive the descent; leaving it set afterwards would inflict this same
# defect on whatever collects next.
_THIS_MODULE: Final = sys.modules[__name__]

#: A stack, not a scalar: `Dir` and each `Module` under it are bracketed in turn.
_DISPLACED_CONFTEST: Final[list[Any]] = []


def pytest_collectstart(collector: pytest.Collector) -> None:  # noqa: ARG001 - hook signature
    """Claim ``sys.modules["conftest"]`` for the duration of one node's collection."""
    _DISPLACED_CONFTEST.append(sys.modules.get("conftest"))
    sys.modules["conftest"] = _THIS_MODULE


def pytest_collectreport(report: pytest.CollectReport) -> None:  # noqa: ARG001 - hook signature
    """Hand the name back to whoever held it, so no later suite inherits this problem."""
    if not _DISPLACED_CONFTEST:  # pragma: no cover - only if collection was interrupted
        return
    displaced = _DISPLACED_CONFTEST.pop()
    if displaced is None:
        sys.modules.pop("conftest", None)
    else:
        sys.modules["conftest"] = displaced


def _repo_root(start: Path) -> Path:
    """The workspace root: the nearest ancestor holding both ``spec/`` and ``compose.yaml``."""
    for candidate in (start, *start.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    raise RuntimeError(f"no workspace root above {start}")


REPO_ROOT: Final = _repo_root(_TESTS)
CONTRACTS_DIR: Final = REPO_ROOT / "verticals/mainline/apps/console/contracts"
MIGRATIONS_DIR: Final = REPO_ROOT / "verticals/mainline/db/migrations"
RESOURCES_TS: Final = REPO_ROOT / "verticals/mainline/apps/console/src/data/resources.ts"

#: The directory ``scripts/deploy/seed_demo.py`` reads its seed files out of, and the
#: deployer itself. The FILE NAMES are not stated here — they are read off the deployer's
#: ``SEED_FILES`` — because a second copy of that tuple is the same class of defect this
#: fixture was rewritten to close.
SEEDS_DIR: Final = REPO_ROOT / "verticals/mainline/db/seeds/demo"
SEED_DEMO_PY: Final = REPO_ROOT / "scripts/deploy/seed_demo.py"

#: The four names ``trappoint_testkit.cluster`` publishes a shared DSN under.
_DSN_ENV_NAMES: Final = ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN")

#: Cloud runs ``gc.ttlseconds = 4500``; the local node defaults to 14400. Pinning the
#: stricter value locally means a `AS OF SYSTEM TIME` that works here works there.
_CLOUD_GC_TTL_SECONDS: Final = 4500


# ── The cluster ─────────────────────────────────────────────────────────────────────


def _candidate_dsns() -> list[tuple[str, str]]:
    import os

    found = [(name, os.environ[name]) for name in _DSN_ENV_NAMES if os.environ.get(name)]
    found.append(("default", "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"))
    return found


def _probe(dsn: str) -> str | None:
    try:
        with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conn:
            row = conn.execute("SELECT version()").fetchone()
            return str(row[0]) if row else "unknown"
    except psycopg.Error:
        return None


def _testkit_state(config: pytest.Config) -> Any | None:
    """The ``trappoint-testkit`` plugin's decision for this session, or ``None``.

    The plugin resolves ``--crdb`` once in ``pytest_configure``, before collection, and
    stashes what it decided. Reading that stash is what makes ``--crdb=none`` mean
    something here: without it this module would probe ``127.0.0.1:26257`` directly and
    quietly use a node the session had explicitly declined to obtain — thirteen private
    containers is exactly the failure the convention exists to prevent, and a module that
    routes around the decision is the first of them.
    """
    try:
        from trappoint_testkit.plugin import STATE_KEY
    except ImportError:  # pragma: no cover - the plugin is a workspace dependency
        return None
    return config.stash.get(STATE_KEY, None)


@pytest.fixture(scope="session")
def admin_dsn(request: pytest.FixtureRequest) -> str:
    """A DSN for a CockroachDB this session may create databases in, or a skip that says why."""
    state = _testkit_state(request.config)
    if state is not None:
        if state.cluster is not None:
            return str(state.cluster.dsn)
        pytest.skip(
            "the session obtained no CockroachDB, so the twelve read resources cannot be "
            f"exercised against a real schema. trappoint-testkit says: {state.skip_reason}"
        )

    tried: list[str] = []
    for name, dsn in _candidate_dsns():
        if _probe(dsn) is not None:
            return dsn
        tried.append(f"{name}={dsn.split('@')[-1]}")
    pytest.skip(
        "trappoint-testkit is not loaded and no CockroachDB answered, so the twelve read "
        "resources cannot be exercised against a real schema. Tried, in order: "
        + ", ".join(tried)
        + ". Start the compose node (`docker compose up -d crdb`) or export MAINLINE_TEST_DSN. "
        "This session will NOT start a container of its own: the repository convention is "
        "--crdb=reuse and one shared node per session (packages/trappoint-testkit)."
    )


# ── The session's decision, made binding for every item under this directory ────────
#
# `admin_dsn` above consults `_testkit_state` and skips with the testkit's own reason,
# which is correct — for the items that consume `admin_dsn`. It is not a property of
# the SUITE, and two modules here do not consume it: `test_gate_run.py:383` and
# `test_row_factory_contract.py:198` each build their own DSN from the four environment
# names and then fall back to a hardcoded `127.0.0.1:26257`.
#
# Under `--crdb=none` the testkit clears those four names and installs
# `cluster.ProcessGuard`, which blocks `docker`/`cockroach` from being SPAWNED. It does
# not — and cannot — block a `psycopg.connect` to a node that is already listening. So
# on any machine where the compose node happens to be up, those two modules dial it and
# use a cluster the session explicitly declined to obtain.
#
# MEASURED 2026-08-13, the run in which this directory first reached the root
# `testpaths`, with `cockroachdb/cockroach:v26.2.5` answering on 127.0.0.1:26257:
#
#     $ pytest --crdb=none -q
#     …  [ 99%]
#     +++++++++++++++++++++++++ Timeout +++++++++++++++++++++++++
#     File ".../test_row_factory_contract.py", line 220, in w1_database
#       report = proof.apply_chain(…)          # 271 migrations, inside a 120 s budget
#     EXIT=1
#
# `pyproject.toml` sets `timeout = 120` and `timeout_method = "thread"`, and the thread
# method ends the process with `os._exit`. So the whole 9583-test run died at 99% —
# after twelve minutes — because a suite that had just become collectable ignored
# `--crdb=none`. That is the thirteen-clusters failure mode in the repository-root
# `conftest.py` docstring, re-entered through a newly-collected directory, and it is
# exactly what the brief for this change meant by "no hang".
#
# The rule is therefore enforced where it can be stated once for the whole directory
# rather than remembered per module. A conftest's `pytest_runtest_setup` fires only for
# items beneath its own directory, so this binds this directory's modules and nothing
# else in the session. A module added here later inherits it without knowing it exists,
# which is the difference between a fixed instance and a closed class.
#
# It removes no coverage: `requires_cluster` items still run in every lane that HAS a
# cluster (`--crdb=auto|reuse|spawn`), which is where they are supposed to prove things.
# It converts "silently uses a node the session refused, then hangs" into "skipped, with
# the reason named" — which is the property `ci.yml`'s step *"The suite, with every
# cluster test SKIPPED FOR A NAMED REASON"* claims, and `release-proof.yml:296` already
# treats a test that runs when something answers on a closed port as a control FAILURE.
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip a cluster-backed item, by name, when the session obtained no cluster."""
    if item.get_closest_marker("requires_cluster") is None:
        return
    state = _testkit_state(item.config)
    if state is None or state.cluster is not None:
        # No testkit (the standalone `admin_dsn` probe ladder still applies), or a real
        # cluster was obtained and the item must run against it.
        return
    pytest.skip(
        "the session obtained no CockroachDB, so this cluster-backed test is skipped "
        "rather than allowed to reach a node the session declined to obtain. "
        f"trappoint-testkit says: {state.skip_reason}"
    )


def _deployer() -> Any:
    """``scripts/deploy/seed_demo``, loaded by path, with ``sys.path`` handed straight back.

    IMPORTED, NEVER RESTATED. The seed file list, the order they go in, the one-batch-per-
    file rule and the ``40001`` retry loop are all read off this module, so a change to what
    the deployment applies is a change to what this fixture applies. That is the whole point
    of the rewrite: the deployment and the fixture must not be able to disagree.

    Loaded by path rather than by ``import scripts.deploy.seed_demo`` because that name
    resolves only with the repository ROOT on ``sys.path``, and this conftest is imported
    into a session that collects 9600 tests. A repository root left on the path makes eight
    top-level directories — ``tests``, ``packages``, ``docs``, ``spec``, ``scripts``,
    ``infra``, ``evidence``, ``verticals`` — importable as namespace packages for everything
    that collects afterwards, which is a session-wide change no worker owns. ``seed_demo``
    inserts the root itself so that its own sibling import of ``cloud_chain`` resolves; the
    insertion is undone here the moment the module has finished loading, and the loaded
    module is cached under a private name so nothing else can be shadowed by it either.
    """
    import importlib.util

    name = "mainline_seed_demo_for_tests"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, SEED_DEMO_PY)
    if spec is None or spec.loader is None:  # pragma: no cover - the file is committed
        raise RuntimeError(f"no importable module at {SEED_DEMO_PY}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    restore = list(sys.path)
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    finally:
        sys.path[:] = restore
    return module


def _fingerprint() -> str:
    """SHA-256 over everything that BUILDS this database: the migrations AND the seed.

    The seed is in the key because the seed is now part of the build. While the history was
    Python in this file, an edit to it changed the fixture's own module and nothing else
    could be stale; now that ``demo_world.sql`` is what populates the database, a cached
    database built from an older copy of it would be adopted silently. That is the same
    "the marker says BUILT, never that it is USABLE" failure the adoption probe below exists
    to catch, one layer further up, and the cheapest place to catch it is the name.
    """
    digest = hashlib.sha256()
    for path in sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    for name in _deployer().SEED_FILES:
        digest.update(name.encode("utf-8"))
        digest.update((SEEDS_DIR / name).read_bytes())
    return digest.hexdigest()[:12]


def _dsn_for(admin: str, database: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(admin)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _apply_chain(dsn: str) -> tuple[int, list[str]]:
    """Bootstrap, then apply every migration in allocation order, each in its own transaction.

    Autocommit per file rather than one enclosing transaction: CockroachDB DDL inside a
    multi-statement transaction can fail at COMMIT even when every statement succeeded,
    so a shared transaction would retroactively un-apply files already counted.
    """
    from trappoint_migrate.bootstrap import bootstrap
    from trappoint_migrate.discovery import discover
    from trappoint_migrate.runner import DEFAULT_SCHEMA_PREFIXES, actor

    with psycopg.connect(dsn, autocommit=True) as conn:
        bootstrap(conn, applied_by=actor(), schema_prefixes=DEFAULT_SCHEMA_PREFIXES)

    applied = 0
    failures: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        for migration in discover(MIGRATIONS_DIR):
            try:
                conn.execute(migration.path.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            except psycopg.Error as exc:
                failures.append(
                    f"{migration.path.name} [{exc.sqlstate}] {str(exc).splitlines()[0][:120]}"
                )
            else:
                applied += 1
    return applied, failures


# ── The seeded history: the seed the DEPLOYMENT applies, read back out of the database ─
#
# THE FIXTURE APPLIES `demo_world.sql` AND `demo_permit.sql`. It does not build a world of
# its own, and it does not add a row to theirs. Everything below is either the deployer's
# own code being called, or a query that reads the deployer's result back.


class _Seed(dict[str, str]):
    """The identifiers the deployed seed produced — and a ``KeyError`` that says why not.

    A plain ``dict`` answers a name the deployed seed does not carry with ``KeyError:
    'cr_id'``, which reads like a typo. It is not a typo: it is the deployed demo not
    having a change request at all, surfacing at the first line of a test that assumed one.
    The message below is that diagnosis, delivered where the assumption is made, because a
    fixture that fails obscurely is a fixture somebody patches by inventing the row.
    """

    def __missing__(self, key: str) -> str:
        raise KeyError(
            f"{key!r} is not an identifier the deployed demo seed produces. This database "
            "was built by applying verticals/mainline/db/seeds/demo/{demo_world,"
            "demo_permit}.sql — the two files scripts/deploy/seed_demo.py applies to "
            "CockroachDB Cloud — and every name below was read back out of it with a "
            "query. A name that is absent is therefore a ROW THE DEPLOYED DEMO DOES NOT "
            "CARRY, not a gap in this fixture. It offers: " + ", ".join(sorted(self)) + ". "
            "Do NOT mint the row here: a fixture that invents a subject the deployment "
            "does not have is the parallel world this file was rewritten to delete, and it "
            "is how beat 4 reached a judge behind 291 green tests. Seed it in "
            "demo_world.sql so the deployment carries it too, or assert the 404."
        )


def _apply_seeds(dsn: str) -> list[str]:
    """Apply the deployment's seed files, in its order, through its own applier.

    ``seed_demo.apply_seeds`` is CALLED, not copied. It is the function that puts the demo
    into CockroachDB Cloud: it reads its file list from ``SEED_FILES``, applies each file as
    ONE statement batch — ``demo_permit.sql``'s second ``permit_event`` reads the first
    one's trigger-computed ``chain_digest``, so splitting a file would change *what* is
    seeded and not merely how — and runs each batch through ``cloud_chain.Applier``, whose
    loop retries ``40001`` with backoff and rebuilds a socket the cluster dropped. Calling
    it is what makes "this fixture applies what the deployment applies" a property of the
    code rather than a claim in a comment: there is no second list, no second order, and no
    second retry loop to fix and forget.

    Returns one line per file that did not apply, and an empty list when all of them did.
    """
    deployer = _deployer()
    applier = deployer.Applier(dsn)
    try:
        rows = deployer.apply_seeds(applier, SEEDS_DIR)
    finally:
        applier.close()
    return [
        f"{row['file']} did not apply [{row['sqlstate']}]: {row['error']}"
        for row in rows
        if row["error"]
    ]


def _sole(
    conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...], subject: str
) -> dict[str, Any]:
    """The one row *sql* must return, or a refusal saying how many it actually returned.

    EXACTLY ONE, never "the first". ``scripts/deploy/seed_demo.py`` makes the same claim
    about the deployed database — it counts permits three ways and treats a second one as a
    failure — because "the seed is present" and "the seed is the only thing present" are
    different sentences, and only the second says the ``seed`` dict names the subject a test
    is about to drive. A ``LIMIT 1`` here would turn leftovers from a half-finished rebuild
    into a silently different subject, which is the failure mode this whole file is about.
    """
    rows = conn.execute(sql, params).fetchall()
    if len(rows) != 1:
        raise AssertionError(
            f"{subject}: the seeded database holds {len(rows)} such rows where exactly one "
            f"is required. This database was built by applying "
            f"{', '.join(_deployer().SEED_FILES)} out of {SEEDS_DIR}; if those files no "
            "longer produce this row then the DEPLOYED demo no longer carries it either, "
            "and that is the defect — not this assertion."
        )
    return dict(rows[0])


#: EVERY permit in the database. No predicate and no ``LIMIT``: the fixture database holds
#: the seed and nothing else, so "exactly one row" is an assertion about the whole database
#: rather than about whichever row a scan reached first.
_PERMIT_SQL: Final = """
SELECT p.permit_id::STRING AS permit_id,
       p.site_id::STRING   AS site_id,
       p.site_role::STRING AS site_role,
       p.external_ref      AS permit_external_ref,
       p.state::STRING     AS permit_state,
       s.site_code         AS site_code
  FROM mainline.permit AS p
  JOIN mainline.site   AS s ON s.site_id = p.site_id
"""

#: THE SECOND GATED SUBJECT, and — like the permit above — EVERY one of them in the
#: database, for the same reason: no predicate and no ``LIMIT``, so "exactly one row" is an
#: assertion about the whole database rather than about whichever row a scan reached first.
#:
#: ``demo_world.sql`` §10 seeds it because the console DECLARES it: ``change_request`` is in
#: ``RESOURCE_KEYS`` and ``GET /v1/change-requests/{cr_id}`` is routed at it against a
#: committed contract, over a table, a nine-edge transition alphabet and a reader that all
#: ship. The seed fixes ``cr_id`` as a literal so the DEPLOYED demo and this fixture name the
#: same row; this query is how the fixture LEARNS what that literal is, and the reasoning is
#: in ``docs/decisions/demo-change-request.md``. Nothing here computes an identifier — for
#: the same reason nothing here computes a credential id.
_CR_SQL: Final = """
SELECT cr.cr_id::STRING  AS cr_id,
       cr.external_ref   AS cr_external_ref,
       cr.state::STRING  AS cr_state,
       cr.target_ref     AS cr_target_ref
  FROM mainline.change_request AS cr
"""

#: The obligation, and the four things the seed hangs off it. ``commit_id`` is taken from
#: the CHECK rather than from ``permit_clause.relation = 'relies_on'`` so that no string
#: literal out of the seed file is restated here: the check already names the commit it was
#: projected against, and reading it is one fewer place for the two to disagree.
_CHECK_SQL: Final = """
SELECT c.check_id::STRING           AS check_id,
       c.clause_uuid::STRING        AS clause_uuid,
       encode(c.commit_id, 'hex')   AS commit_id,
       c.precursor_event_id::STRING AS event_id,
       c.recall_run_id::STRING      AS run_id
  FROM mainline.blocking_check AS c
 WHERE c.permit_id = %s
"""

#: WHO THE SEED PUT IN FRONT OF THE OBLIGATION, and the authority for saying so.
#: ``mainline.exposure_receipt.actor_sub`` records the person the evidence was actually
#: shown to, and ``fn_disposition_project`` will not accept a signature from anybody else.
#: Reading the signer off this row rather than matching a name means this file never spells
#: ``'demo.signer'`` at all — which is the point: a fixture that spells it has re-declared
#: it, and a re-declared constant is what put a `23503` in front of a judge.
_RECEIPT_SQL: Final = """
SELECT r.receipt_id::STRING         AS receipt_id,
       r.actor_sub                  AS signer_sub,
       r.silence_receipt_id::STRING AS silence_receipt_id,
       r.policy_version             AS policy_version
  FROM mainline.exposure_receipt AS r
 WHERE r.permit_id = %s
"""

#: The second person. A ``blood_major`` obligation takes a countersignature, so the seed
#: enrols two people and the one who is not the receipt's actor is the other one. Written as
#: a query rather than a name so that a seed which grows a third person is a refusal here
#: instead of an arbitrary choice made silently.
_OTHER_PERSON_SQL: Final = """
SELECT DISTINCT p.signer_sub AS countersigner_sub
  FROM mainline.person AS p
 WHERE p.signer_sub <> %s
"""

#: THE ROW BLOCKER 1 WAS ABOUT. ``mainline.signing_credential`` is where a credential id
#: comes from: it is the FK target of ``mainline.disposition.signer_credential_id``, and in
#: the real product the value arrives from a WebAuthn enrolment and is derivable by nobody.
#: So this fixture READS it. It must never compute it — four files agreeing on a SHA-256
#: over two hardcoded words, while the deployed seed wrote
#: ``digest('mainline-demo/credential/demo.signer', 'sha256')``, is precisely how beat 4 came
#: to fail ``23503 disposition_signer_credential_id_fkey`` against a database that 291 green
#: tests had never once been pointed at.
_CREDENTIAL_SQL: Final = """
SELECT encode(c.credential_id, 'hex') AS credential_id
  FROM mainline.signing_credential AS c
 WHERE c.signer_sub = %s AND c.revoked_at IS NULL
"""

#: The clause version the check cites, and the document it was printed from.
_CLAUSE_VERSION_SQL: Final = """
SELECT v.doc_id::STRING AS doc_id,
       v.gen::STRING    AS clause_gen
  FROM mainline.clause_version AS v
 WHERE v.clause_uuid = %s AND v.commit_id = decode(%s, 'hex')
"""


def _identifiers(conn: psycopg.Connection[Any]) -> _Seed:
    """Read the seeded world's identifiers OUT OF the seeded world.

    Not parsed out of the SQL, and not restated from it. Parsing would make this file a
    second reader of the seed's syntax; restating would make it a second DEFINITION of the
    seed's values, which is the defect being closed rather than a smaller version of it. A
    query is the only form that cannot drift: when the database does not hold the row there
    is no value to hand out, and the refusal names the table instead of handing back a
    plausible identifier for a row that is not there.
    """
    seed = _Seed()
    permit = _sole(conn, _PERMIT_SQL, (), "mainline.permit — the demo's one gated subject")
    seed.update({key: str(value) for key, value in permit.items()})

    change_request = _sole(
        conn, _CR_SQL, (), "mainline.change_request — the demo's second gated subject"
    )
    seed.update({key: str(value) for key, value in change_request.items()})

    check = _sole(
        conn,
        _CHECK_SQL,
        (seed["permit_id"],),
        f"mainline.blocking_check for permit {seed['permit_id']}",
    )
    seed.update({key: str(value) for key, value in check.items()})

    receipt = _sole(
        conn,
        _RECEIPT_SQL,
        (seed["permit_id"],),
        f"mainline.exposure_receipt for permit {seed['permit_id']}",
    )
    seed.update({key: str(value) for key, value in receipt.items()})

    other = _sole(
        conn,
        _OTHER_PERSON_SQL,
        (seed["signer_sub"],),
        f"the one row in mainline.person that is not {seed['signer_sub']!r}",
    )
    seed["countersigner_sub"] = str(other["countersigner_sub"])

    version = _sole(
        conn,
        _CLAUSE_VERSION_SQL,
        (seed["clause_uuid"], seed["commit_id"]),
        f"mainline.clause_version {seed['clause_uuid']} at the commit the check cites",
    )
    seed.update({key: str(value) for key, value in version.items()})

    for role in ("signer", "countersigner"):
        sub = seed[f"{role}_sub"]
        credential = _sole(
            conn, _CREDENTIAL_SQL, (sub,), f"mainline.signing_credential for {sub!r}"
        )
        seed[f"{role}_credential_id"] = str(credential["credential_id"])
    return seed


# ── Adopting a database somebody else's session built ───────────────────────────────
#
# THE MARKER SAYS THE DATABASE WAS BUILT. IT DOES NOT SAY IT IS STILL USABLE.
# `w3_fixture.ready` carries the build fingerprint and the seeded identifiers, so a second
# run reuses the database rather than paying 46.7 s to apply 271 files again. Every row the
# seed files write lands in an append-only table and cannot drift — except one. The exposure
# receipt has a window, and a database adopted after that window closed carries a dead one.
# Nothing about the marker changes when that happens.
#
# `demo_permit.sql` §4 dates its receipt `2027-01-01`, and says in the file why: the
# admission beat has to keep working for every judge for the whole judging period rather
# than for two hours after somebody ran the deploy. That is a longer fuse than the two-hour
# window this fixture used to seed, not the absence of one — so the probe stays, and the
# repair stays, and they will matter on the first run after that date.
#
# The cost of missing it is not hypothetical: the sibling fixture in `tests/test_gate_run.py`
# had the same shape, and on 2026-08-12 five tests there reported `observed outcome='skipped'`
# for beat 4 — a FIXTURE failure presented as a product failure, against a gate that was
# working perfectly. Measured then, and pinned here before it can be measured again.


_ADOPTION_SQL: Final = """
SELECT (SELECT count(*) FROM mainline.permit WHERE permit_id = %(permit)s) AS permits,
       (SELECT count(*) FROM mainline.exposure_receipt WHERE receipt_id = %(receipt)s)
         AS receipts,
       (SELECT r.expires_at FROM mainline.exposure_receipt r
         WHERE r.receipt_id = %(receipt)s) AS expires_at,
       now() AS observed_at
"""

#: ``INSERT … SELECT``, so every column of the replacement except the identifier, the digest
#: and the two timestamps is COPIED from the receipt it replaces. ``mainline.exposure_receipt``
#: carries an ``append_only`` weld (``0128d_trg_refuse_mutation_exposure_receipt``) that
#: refuses UPDATE and DELETE with ``P0001``, so extending the window in place is not merely
#: discouraged — it is refused by the schema, and a new receipt is the only repair there is.
#:
#: The replacement's digest is computed BY THE DATABASE, with ``digest(...)`` over a string
#: that says what it is — the naming scheme every other digest in ``demo_world.sql`` uses.
#: The fixture no longer owns a hashing helper at all. The one it had is what computed the
#: credential id that beat 4 died on, and a test file keeping a private SHA-256 helper
#: around keeps the means to re-declare a value the database is the authority for.
_REISSUE_RECEIPT_SQL: Final = """
INSERT INTO mainline.exposure_receipt
       (receipt_id, subject_kind, permit_id, actor_sub, issued_at, issued_hlc, expires_at,
        corpus_root, silence_receipt_id, policy_version, total_tokens, receipt_digest)
SELECT %(new)s, r.subject_kind, r.permit_id, r.actor_sub,
       now() - INTERVAL '10 minutes', r.issued_hlc, now() + INTERVAL '2 hours',
       r.corpus_root, r.silence_receipt_id, r.policy_version, r.total_tokens,
       digest('mainline-demo/receipt/reissued/' || %(new)s::STRING, 'sha256')
  FROM mainline.exposure_receipt r
 WHERE r.receipt_id = %(old)s
"""

_REISSUE_LINES_SQL: Final = """
INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens)
SELECT %(new)s, l.check_id, l.payload_digest, l.tokens
  FROM mainline.exposure_line l
 WHERE l.receipt_id = %(old)s
"""


def _adoption_state(conn: psycopg.Connection[Any], seed: Mapping[str, str]) -> dict[str, Any]:
    """One statement: does the seeded subject still exist, and is its receipt still live?"""
    row = conn.execute(
        _ADOPTION_SQL, {"permit": seed["permit_id"], "receipt": seed["receipt_id"]}
    ).fetchone()
    assert row is not None  # a scalar SELECT with no FROM always returns one row
    return dict(row)


def _reissue_receipt(conn: psycopg.Connection[Any], seed: dict[str, str]) -> str:
    """Issue a fresh receipt cloning the seeded one, carrying its exposure lines forward."""
    receipt_id = uuid.uuid4()
    conn.execute(_REISSUE_RECEIPT_SQL, {"new": receipt_id, "old": seed["receipt_id"]})
    conn.execute(_REISSUE_LINES_SQL, {"new": receipt_id, "old": seed["receipt_id"]})
    return str(receipt_id)


def _adoption_refusal(state: Mapping[str, Any]) -> str | None:
    """Why this database may not be adopted as it stands, or ``None`` when it may be."""
    if not state["permits"]:
        return "the seeded permit is gone"
    if not state["receipts"]:
        return "the seeded exposure receipt is gone"
    if state["expires_at"] <= state["observed_at"]:
        return (
            f"the seeded exposure receipt expired {state['expires_at'].isoformat()} "
            f"(now {state['observed_at'].isoformat()})"
        )
    return None


def _live_receipt(conn: psycopg.Connection[Any], seed: dict[str, str]) -> str | None:
    """Reissue the seeded receipt if it has aged out; return why it is still unusable.

    Run on the FRESH-BUILD path as well as the adoption path, and that is not belt and
    braces. ``demo_permit.sql`` pins ``expires_at`` to a literal ``2027-01-01``, so a
    database seeded from it on 2027-01-02 is born with a dead receipt — the one state a
    freshly-built database was previously assumed to be incapable of. The probe and the
    repair are the same two calls on both paths, so neither path can acquire a fix the
    other one misses.
    """
    state = _adoption_state(conn, seed)
    if state["receipts"] and state["expires_at"] <= state["observed_at"]:
        seed["receipt_id"] = _reissue_receipt(conn, seed)
        state = _adoption_state(conn, seed)
    return _adoption_refusal(state)


@pytest.fixture(scope="session")
def demo_database(admin_dsn: str) -> tuple[str, dict[str, str]]:
    """A migrated database carrying THE DEPLOYED SEED, cached by the build's fingerprint.

    The database name is left as ``w3_demo_api_…``. It names the worker whose fixture this
    is, not the world inside it — the world is now ``demo_world.sql`` — and
    ``test_reads.py`` asserts the prefix when it checks what ``/v1/health`` reports about
    the database it is on. Renaming it would break an assertion about something else
    entirely, which is not a thing a rename gets to do.
    """
    fingerprint = _fingerprint()
    database = f"w3_demo_api_{fingerprint}"
    dsn = _dsn_for(admin_dsn, database)

    # Existence is decided by CONNECTING, not by querying `information_schema.schemata`:
    # that view describes the schemas of the database you are connected to, so it reports
    # nothing about a sibling database and the check silently said "absent" for one that
    # was there. A connect that raises `3D000` is unambiguous.
    marker: dict[str, Any] | None = None
    try:
        with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as probe:
            try:
                marker = probe.execute(
                    "SELECT seed, migrations FROM w3_fixture.ready WHERE fingerprint = %s",
                    (fingerprint,),
                ).fetchone()
            except psycopg.Error:
                marker = None
    except psycopg.Error:
        marker = None
    if marker is not None:
        # `_Seed`, not `dict`: the marker's JSONB comes back as a plain mapping, and a plain
        # mapping answers an absent name with a bare `KeyError` instead of the diagnosis.
        # An adopted database must behave exactly like a freshly built one.
        seed = _Seed(marker["seed"])
        with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as adopt:
            # The one repair worth attempting: the history is intact and only its exposure
            # has aged out. Anything else falls through to a rebuild, because a fixture that
            # patches a database it does not understand is worse than one that rebuilds.
            refusal = _live_receipt(adopt, seed)
            if refusal is None:
                # The marker carries the identifiers a LATER session will adopt, so the
                # re-issued receipt has to land in it. Without this the repair would be
                # redone on every run and the seed dict would disagree with the marker.
                adopt.execute(
                    "UPSERT INTO w3_fixture.ready (fingerprint, migrations, seed) "
                    "VALUES (%s, %s, %s)",
                    (fingerprint, marker["migrations"], Jsonb(seed)),
                )
                return dsn, seed

    with psycopg.connect(admin_dsn, autocommit=True, row_factory=dict_row) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {database} CASCADE")
        admin.execute(f"CREATE DATABASE {database}")
        admin.execute(
            f"ALTER DATABASE {database} CONFIGURE ZONE USING "
            f"gc.ttlseconds = {_CLOUD_GC_TTL_SECONDS}"
        )

    applied, failures = _apply_chain(dsn)
    if failures:
        pytest.skip(
            f"{len(failures)} of {applied + len(failures)} migrations did not apply into "
            f"{database}, so the read surface cannot be exercised against the real schema. "
            "First three: " + "; ".join(failures[:3])
        )

    # THE SEED IS THE DEPLOYMENT'S SEED, APPLIED BY THE DEPLOYMENT'S CODE.
    # A seed file that does not apply is a FAILURE and not a skip: `demo_world.sql` and
    # `demo_permit.sql` are committed files against a schema this session has just built
    # from the committed migration chain, so nothing about the environment can explain one
    # of them refusing. Skipping here would mean the demo's own seed breaking silently,
    # which is the shape of defect this fixture exists to make impossible.
    seed_failures = _apply_seeds(dsn)
    if seed_failures:
        pytest.fail(
            f"the deployed demo seed did not apply into {database}. This is the seed "
            "scripts/deploy/seed_demo.py applies to CockroachDB Cloud, so a failure here is "
            "a failure there. " + "; ".join(seed_failures)
        )

    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        seed = _identifiers(conn)
        refusal = _live_receipt(conn, seed)
        if refusal is not None:
            pytest.fail(
                f"the freshly seeded database in {database} is not usable: {refusal}. The "
                "seed applied, so this is what the seed files produce today — not a stale "
                "cache and not an adoption problem."
            )
        conn.execute("CREATE SCHEMA IF NOT EXISTS w3_fixture")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS w3_fixture.ready ("
            "  fingerprint STRING PRIMARY KEY,"
            "  built_at    TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "  migrations  INT8 NOT NULL,"
            "  seed        JSONB NOT NULL)"
        )
        conn.execute(
            "UPSERT INTO w3_fixture.ready (fingerprint, migrations, seed) VALUES (%s, %s, %s)",
            (fingerprint, applied, Jsonb(seed)),
        )
    return dsn, seed


@pytest.fixture(scope="session")
def demo_dsn(demo_database: tuple[str, dict[str, str]]) -> str:
    """The DSN of the migrated, seeded database."""
    return demo_database[0]


@pytest.fixture(scope="session")
def seed(demo_database: tuple[str, dict[str, str]]) -> dict[str, str]:
    """The identifiers the DEPLOYED seed produced, read back out of the database.

    Not minted here. Every value was obtained with a query after ``demo_world.sql`` and
    ``demo_permit.sql`` were applied, so naming one of them in a test names the row a judge
    will drive. A name this mapping does not carry is a row the deployment does not carry;
    ``_Seed.__missing__`` says which, and what to do about it.
    """
    return demo_database[1]


@pytest.fixture
def conn(demo_dsn: str) -> Iterator[psycopg.Connection[Any]]:
    """One connection per test, through the module under test, so its caching is exercised."""
    from mainline_demo_api import db as demo_db

    demo_db.reset_dsn_cache()
    try:
        yield demo_db.connection(dsn=demo_dsn)
    finally:
        demo_db.reset_dsn_cache()


# ── A validator for the console's contracts ─────────────────────────────────────────

#: Keywords whose value is a single subschema rather than a list or a mapping of them.
_SUBSCHEMA_KEYWORDS: Final = frozenset(
    {"not", "if", "then", "else", "items", "additionalProperties"}
)

_DATE_TIME = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2}):(\d{2})(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def _is_date_time(value: str) -> bool:
    """RFC 3339 §5.6, as strictly as ``console/src/data/schema.ts`` asserts it.

    A real calendar date and a real clock time, so ``2026-02-30T00:00:00Z`` is refused —
    a contract that accepts an impossible date has not checked the date.
    """
    match = _DATE_TIME.match(value)
    if match is None:
        return False
    year, month, day, hour, minute, second = (int(match.group(index)) for index in range(1, 7))
    if not (1 <= month <= 12) or hour > 23 or minute > 59 or second > 60:
        return False
    try:
        _dt.date(year, month, day)
    except ValueError:
        return False
    return True


class SchemaRegistry:
    """Draft 2020-12, restricted to the keywords ``console/contracts/`` actually uses.

    The set was not guessed: it is the result of walking all sixteen documents and
    counting keys. An unimplemented keyword is a hard error rather than a silent pass —
    the same rule ``src/data/schema.ts`` states for itself, and for the same reason. A
    validator that ignores a keyword it never implemented turns every conformance test
    green while asserting less than it claims.
    """

    SUPPORTED: Final = frozenset(
        {
            "$ref",
            "allOf",
            "anyOf",
            "oneOf",
            "not",
            "if",
            "then",
            "else",
            "properties",
            "additionalProperties",
            "items",
            "required",
            "type",
            "enum",
            "const",
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "minLength",
            "maxLength",
            "pattern",
            "minItems",
            "maxItems",
            "minProperties",
            "maxProperties",
            "format",
        }
    )
    ANNOTATIONS: Final = frozenset(
        {"$schema", "$id", "$comment", "title", "description", "default", "examples", "$defs"}
    )

    def __init__(self, directory: Path) -> None:
        self.documents: dict[str, Any] = {}
        for path in sorted(directory.glob("*.schema.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            self.documents[str(document["$id"])] = document
        for identifier, document in self.documents.items():
            self._audit(document, identifier)

    def _audit(self, node: Any, identifier: str, path: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in self.ANNOTATIONS:
                    if key == "$defs":
                        for name, child in value.items():
                            self._audit(child, identifier, f"{path}/$defs/{name}")
                    continue
                if key not in self.SUPPORTED:
                    raise AssertionError(
                        f"{identifier}{path}: keyword {key!r} is not implemented by this "
                        "validator. Implement it in tests/conftest.py rather than letting a "
                        "contract assert something nothing checks."
                    )
                if key in {"properties"}:
                    for name, child in value.items():
                        self._audit(child, identifier, f"{path}/properties/{name}")
                elif key in {"allOf", "anyOf", "oneOf"}:
                    for index, child in enumerate(value):
                        self._audit(child, identifier, f"{path}/{key}/{index}")
                elif key in _SUBSCHEMA_KEYWORDS and isinstance(value, dict):
                    self._audit(value, identifier, f"{path}/{key}")

    def _resolve(self, ref: str, base: str) -> tuple[Any, str]:
        absolute = urljoin(base, ref)
        document_id, fragment = urldefrag(absolute)
        document = self.documents.get(document_id)
        if document is None:
            raise AssertionError(f"$ref {ref!r} from {base} names unknown document {document_id!r}")
        node: Any = document
        for segment in (part for part in fragment.split("/") if part):
            node = node[segment.replace("~1", "/").replace("~0", "~")]
        return node, document_id

    def validate(self, schema_id: str, instance: Any) -> list[str]:
        """Return the list of violations. Empty means the payload satisfies the contract."""
        schema = self.documents.get(schema_id)
        if schema is None:
            return [
                f"$: no contract with $id {schema_id!r} is held (have {sorted(self.documents)})"
            ]
        errors: list[str] = []
        self._check(schema, instance, schema_id, "$", errors)
        return errors

    def _check(self, schema: Any, value: Any, base: str, path: str, errors: list[str]) -> None:  # noqa: PLR0912
        if schema is True or schema == {}:
            return
        if schema is False:
            errors.append(f"{path}: schema is false; nothing validates")
            return
        if not isinstance(schema, dict):
            return

        if "$ref" in schema:
            target, new_base = self._resolve(str(schema["$ref"]), base)
            self._check(target, value, new_base, path, errors)

        if "type" in schema:
            names = schema["type"]
            names = [names] if isinstance(names, str) else list(names)
            if not any(self._is_type(value, name) for name in names):
                errors.append(f"{path}: expected type {names}, got {self._type_of(value)}")
                return
        if "enum" in schema and not any(value == option for option in schema["enum"]):
            errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: expected const {schema['const']!r}, got {value!r}")

        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append(f"{path}: shorter than minLength {schema['minLength']}")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                errors.append(f"{path}: longer than maxLength {schema['maxLength']} ({len(value)})")
            if "pattern" in schema and re.search(schema["pattern"], value) is None:
                errors.append(f"{path}: {value[:60]!r} does not match {schema['pattern']}")
            if schema.get("format") == "date-time" and not _is_date_time(value):
                errors.append(f"{path}: {value!r} is not an RFC 3339 date-time")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append(f"{path}: {value} < minimum {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                errors.append(f"{path}: {value} > maximum {schema['maximum']}")
            if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
                errors.append(f"{path}: {value} <= exclusiveMinimum {schema['exclusiveMinimum']}")
            if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
                errors.append(f"{path}: {value} >= exclusiveMaximum {schema['exclusiveMaximum']}")

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path}: {len(value)} items < minItems {schema['minItems']}")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append(f"{path}: {len(value)} items > maxItems {schema['maxItems']}")
            if "items" in schema:
                for position, item in enumerate(value):
                    self._check(schema["items"], item, base, f"{path}/{position}", errors)

        if isinstance(value, dict):
            for name in schema.get("required", []):
                if name not in value:
                    errors.append(f"{path}: required property {name!r} is absent")
            if "minProperties" in schema and len(value) < schema["minProperties"]:
                errors.append(
                    f"{path}: {len(value)} properties < minProperties {schema['minProperties']}"
                )
            if "maxProperties" in schema and len(value) > schema["maxProperties"]:
                errors.append(
                    f"{path}: {len(value)} properties > maxProperties {schema['maxProperties']}"
                )
            declared = schema.get("properties", {})
            for name, child in declared.items():
                if name in value:
                    self._check(child, value[name], base, f"{path}/{name}", errors)
            extra = schema.get("additionalProperties")
            if extra is False:
                for name in value:
                    if name not in declared:
                        errors.append(f"{path}: additional property {name!r} is not permitted")
            elif isinstance(extra, dict):
                for name, item in value.items():
                    if name not in declared:
                        self._check(extra, item, base, f"{path}/{name}", errors)

        for child in schema.get("allOf", []):
            self._check(child, value, base, path, errors)
        if "anyOf" in schema and not any(
            not self._collect(child, value, base) for child in schema["anyOf"]
        ):
            errors.append(f"{path}: satisfies none of the {len(schema['anyOf'])} anyOf branches")
        if "oneOf" in schema:
            passing = [
                index
                for index, child in enumerate(schema["oneOf"])
                if not self._collect(child, value, base)
            ]
            if len(passing) != 1:
                errors.append(
                    f"{path}: matched {len(passing)} of {len(schema['oneOf'])} oneOf branches "
                    f"(exactly one is required); value={_preview(value)}"
                )
        if "not" in schema and not self._collect(schema["not"], value, base):
            errors.append(f"{path}: matched a schema it must not match")
        if "if" in schema:
            if not self._collect(schema["if"], value, base):
                if "then" in schema:
                    self._check(schema["then"], value, base, path, errors)
            elif "else" in schema:
                self._check(schema["else"], value, base, path, errors)

    def _collect(self, schema: Any, value: Any, base: str) -> list[str]:
        errors: list[str] = []
        self._check(schema, value, base, "$", errors)
        return errors

    @staticmethod
    def _is_type(value: Any, name: str) -> bool:  # noqa: PLR0911 - one return per JSON type
        if name == "null":
            return value is None
        if name == "boolean":
            return isinstance(value, bool)
        if name == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if name == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if name == "string":
            return isinstance(value, str)
        if name == "array":
            return isinstance(value, list)
        if name == "object":
            return isinstance(value, dict)
        raise AssertionError(f"unknown JSON Schema type {name!r}")

    @staticmethod
    def _type_of(value: Any) -> str:  # noqa: PLR0911 - one return per JSON type
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        return "object"


def _preview(value: Any) -> str:
    text = json.dumps(value, default=str)
    return text if len(text) <= 120 else f"{text[:117]}..."


@pytest.fixture(scope="session")
def registry() -> SchemaRegistry:
    """The console's own contract files, compiled once."""
    if not CONTRACTS_DIR.is_dir():
        pytest.skip(
            f"the console's contracts are not present at {CONTRACTS_DIR}, so no payload emitted "
            "by this API can be checked against the schema its client will enforce"
        )
    return SchemaRegistry(CONTRACTS_DIR)
