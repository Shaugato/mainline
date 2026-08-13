# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The credential resolver, against the seed that is actually deployed.

WHY THIS SUITE BUILDS ITS OWN DATABASE FROM ``demo_world.sql``
--------------------------------------------------------------
The defect this module exists to keep closed was invisible to 291 green tests for one
reason: **none of them ran against the file that is deployed.** ``tests/conftest.py``
seeds a parallel ``w3`` world in Python using the same ``_sha("cred", …)`` helper that
``gate_run`` used, so the test and the code agreed with each other and both diverged from
``verticals/mainline/db/seeds/demo/demo_world.sql`` — the file
``scripts/deploy/seed_demo.py`` applies to the cloud. Beat 4 failed
``23503 disposition_signer_credential_id_fkey`` in front of a judge while the suite was
green. **A test that cannot disagree with the code it tests proves nothing.**

So the fixture below applies the seed FILE. Not a Python re-statement of it, not a
fixture that shares a constant with the module under test: the bytes that are deployed,
read off disk and executed. If ``demo_world.sql`` and this API ever disagree again about
which credential ``demo.signer`` holds, these tests go red — which is the only mechanism
that makes the agreement mean anything.

The database is this module's own, named for the migration tree's fingerprint the way
``conftest.demo_database`` names its own, and it is REUSED between sessions. That is the
same choice ``test_gate_run.py`` made and for the same two reasons: applying the chain
costs ~50 s, and this suite must not append rows to a database other modules are counting.
Every test that writes does so in a transaction it rolls back — ``signing_credential``
carries an ``append_only`` weld (``0128h``) that refuses UPDATE and DELETE with ``P0001``,
so a row committed here could never be cleaned up.

WHAT EACH TEST WOULD CATCH
--------------------------
* ``test_resolves_the_credential_the_deployed_seed_enrolled`` — the instance: the demo's
  signer resolves to the row ``demo_world.sql`` wrote, and NOT to ``sha256(b"credsigner")``.
* ``test_resolution_is_not_derivation`` — the class: the credential id is random, so no
  derivation of any kind can produce it. This test cannot be passed by agreeing with the
  code; it can only be passed by reading the table.
* ``test_gate_run_derives_no_credential_id`` — the regression: an AST walk over
  ``gate_run.py`` that fails if ``_sha("cred", …)`` comes back, and if the resolution ever
  moves after the beats' transaction opens. It needs no cluster, so it is enforced in every
  lane including ``--crdb=none``.
* the refusal tests — a missing or ambiguous credential is a typed refusal naming the
  subject and the table, not a foreign-key violation the demo would report as a refusal
  the gate never made.

NO TEST BELOW PRINTS A CREDENTIAL VALUE. Comparisons are reduced to a bool before they are
asserted so that a failure reports ``assert False`` and the sentence explaining it, rather
than dumping the bytes it was comparing into a CI log.
"""

from __future__ import annotations

import ast
import hashlib
import secrets
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import psycopg
import pytest
from mainline_demo_api.credentials import (
    CREDENTIAL_ID_SOURCE,
    CredentialAmbiguous,
    CredentialNotEnrolled,
    CredentialUnresolvable,
    resolve_credential_id,
)
from mainline_demo_api.scenario import ScenarioNotSeeded
from psycopg.rows import dict_row, tuple_row

from conftest import MIGRATIONS_DIR, REPO_ROOT, _apply_chain, _dsn_for, _fingerprint

#: The file ``scripts/deploy/seed_demo.py`` applies to the cloud database, in the order it
#: applies them (``SEED_FILES``). ``demo_permit.sql`` is here because the admission beat
#: needs the obligation and the exposure receipt it seeds; ``demo_world.sql`` alone would
#: prove the resolver and not the wiring.
SEED_FILES: Final = ("demo_world.sql", "demo_permit.sql")
SEEDS_DIR: Final = REPO_ROOT / "verticals/mainline/db/seeds/demo"

#: The subjects ``demo_world.sql`` enrols. Written here as the literals the seed contains,
#: not imported from anything the API also reads — this file's job is to disagree.
DEMO_SIGNER: Final = "demo.signer"
DEMO_COUNTERSIGNER: Final = "demo.countersigner"

#: The permit ``demo_permit.sql`` seeds, likewise copied from the seed rather than derived.
DEMO_PERMIT_ID: Final = uuid.UUID("dec0de00-0006-4000-8000-000000000001")
DEMO_SITE_ID: Final = uuid.UUID("dec0de00-0001-4000-8000-000000000001")

#: What ``gate_run`` used to bind as ``signer_credential_id``: ``_sha("cred", "signer")``.
#: Spelled out rather than imported, because importing the helper is precisely the mistake
#: that made four files agree with each other and with nothing that ships.
DERIVED_SIGNER_CREDENTIAL: Final = hashlib.sha256(b"credsigner").digest()

PACKAGE_SOURCE: Final = REPO_ROOT / "verticals/mainline/apps/demo-api/src/mainline_demo_api"

GATE_RUN_SOURCE: Final = PACKAGE_SOURCE / "gate_run.py"

_ENROL_SQL: Final = """
INSERT INTO mainline.signing_credential
       (credential_id, signer_sub, public_key_cose, aaguid, transports, attachment,
        enrolment_assurance, revoked_at, revoke_reason)
VALUES (%s, %s, %s, %s, ARRAY['usb'], 'cross-platform', 'hr_system_of_record', %s, %s)
"""


def _enrol(
    conn: psycopg.Connection[Any],
    signer_sub: str,
    credential_id: bytes,
    *,
    revoked: bool = False,
) -> None:
    """Enrol one credential on *conn*, revoked at INSERT time when asked.

    Revocation is expressed on the INSERT because ``mainline.signing_credential`` is
    append-only: ``0128h_trg_refuse_mutation_signing_credential`` refuses every UPDATE and
    every DELETE with ``P0001``, so a row cannot be revoked after the fact by this or any
    other client. ``revoked_at`` and ``revoke_reason`` travel together — constraint
    ``credential_revocation_reasoned`` — so the fixture sets both or neither.
    """
    conn.execute(
        _ENROL_SQL,
        (
            credential_id,
            signer_sub,
            hashlib.sha256(b"cose/" + signer_sub.encode()).digest(),
            hashlib.sha256(b"aaguid/" + signer_sub.encode()).digest()[:16],
            datetime(2026, 1, 7, tzinfo=UTC) if revoked else None,
            "superseded by re-enrolment" if revoked else None,
        ),
    )


def _subject() -> str:
    """A signer_sub no seed has ever enrolled, unique per call."""
    return f"w1.probe.{uuid.uuid4()}"


# ── The database: the migration chain, then the seed FILES that are deployed ─────────


def _demo_world_ready(dsn: str) -> bool:
    """Does this database already carry the seed, with one live credential per subject?"""
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as probe:
            # tuple_row is psycopg's default and is what this reads: `count(*)` is one
            # column CockroachDB names `count`, and both subqueries would collide under
            # a dict row.
            row = probe.execute(
                "SELECT (SELECT count(*) FROM mainline.signing_credential "
                "         WHERE signer_sub IN (%s, %s) AND revoked_at IS NULL),"
                "       (SELECT count(*) FROM mainline.permit WHERE permit_id = %s)",
                (DEMO_SIGNER, DEMO_COUNTERSIGNER, DEMO_PERMIT_ID),
            ).fetchone()
    except psycopg.Error:
        return False
    return bool(row) and row[0] == 2 and row[1] == 1


@pytest.fixture(scope="session")
def demo_world_dsn(admin_dsn: str) -> str:
    """A migrated database carrying ``demo_world.sql`` and ``demo_permit.sql`` themselves.

    Named for the migration tree's fingerprint, so an edited migration builds a new
    database rather than adopting one built against a schema that no longer exists. Adopted
    when the two demo subjects each hold exactly one live credential and the demo permit is
    present — the predicate is the thing the tests actually need, so "usable" is decided by
    asking rather than by a marker's say-so.
    """
    database = f"w1_credentials_{_fingerprint()}"
    dsn = _dsn_for(admin_dsn, database)
    if _demo_world_ready(dsn):
        return dsn

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{database}" CASCADE')
        admin.execute(f'CREATE DATABASE "{database}"')
        # The cloud runs gc.ttlseconds = 4500; pinning the stricter value locally means an
        # `AS OF SYSTEM TIME` that works here works there.
        admin.execute(f'ALTER DATABASE "{database}" CONFIGURE ZONE USING gc.ttlseconds = 4500')

    applied, failures = _apply_chain(dsn)
    if failures:
        pytest.skip(
            f"{len(failures)} of {applied + len(failures)} migrations under {MIGRATIONS_DIR} "
            f"did not apply into {database}, so the deployed seed cannot be applied on top "
            "of them and the credential resolver cannot be exercised against it. First "
            "three: " + "; ".join(failures[:3])
        )

    for name in SEED_FILES:
        path = SEEDS_DIR / name
        if not path.is_file():  # pragma: no cover - the seed is committed
            pytest.skip(
                f"{path} is absent, so this suite cannot run against the seed the deploy "
                "applies, and running it against a re-typed copy would test the copy"
            )
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute(path.read_text(encoding="utf-8"))  # type: ignore[arg-type]

    if not _demo_world_ready(dsn):  # pragma: no cover - the seed applied but said nothing
        pytest.skip(
            f"{', '.join(SEED_FILES)} applied into {database} without raising, and the two "
            "demo subjects still do not each hold exactly one live credential. The seed and "
            "this suite disagree about what it seeds; that is a finding, not a fixture bug."
        )
    return dsn


@pytest.fixture
def demo_world_conn(demo_world_dsn: str) -> Iterator[psycopg.Connection[Any]]:
    """A rolled-back connection carrying ``dict_row`` — the factory ``db.py`` opens with.

    Every test that writes writes here, and nothing it writes survives: the append-only
    weld on ``signing_credential`` means a committed probe row could never be removed.
    """
    conn = psycopg.connect(demo_world_dsn, autocommit=False, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


# ── The instance: the credential the DEPLOYED seed enrolled ─────────────────────────


@pytest.mark.requires_cluster
@pytest.mark.parametrize("factory", [dict_row, tuple_row], ids=["dict_row", "tuple_row"])
def test_resolves_the_credential_the_deployed_seed_enrolled(
    demo_world_dsn: str, factory: Any
) -> None:
    """The resolver returns the row ``demo_world.sql`` wrote, under either row factory."""
    with psycopg.connect(demo_world_dsn, autocommit=True, row_factory=factory) as conn:
        resolved = resolve_credential_id(conn, DEMO_SIGNER)
        # Read back by an INDEPENDENT statement, with the cursor asked for tuples, so the
        # expectation comes from the database and not from the function under test.
        held = (
            conn.cursor(row_factory=tuple_row)
            .execute(
                "SELECT credential_id FROM mainline.signing_credential "
                "WHERE signer_sub = %s AND revoked_at IS NULL",
                (DEMO_SIGNER,),
            )
            .fetchone()
        )

    assert held is not None
    # Reduced to a bool BEFORE the assert: pytest's rewriting prints the operands of a
    # comparison it evaluates, and a credential id has no business in a CI log.
    matches = bytes(held[0]) == resolved
    assert matches, (
        f"resolve_credential_id returned a value {CREDENTIAL_ID_SOURCE} does not hold for "
        f"signer_sub {DEMO_SIGNER!r}"
    )
    assert len(resolved) == 32


@pytest.mark.requires_cluster
def test_the_deployed_seed_does_not_enrol_the_value_gate_run_used_to_derive(
    demo_world_dsn: str,
) -> None:
    """``sha256(b"credsigner")`` is enrolled by nobody, which is why beat 4 used to fail.

    This is the measured premise of the whole change, pinned so that a future seed edit
    that "fixed" the mismatch by making the DATABASE imitate the old constant would be
    caught. A database fact must not be reshaped to match an application constant; the
    application must read the fact.
    """
    with psycopg.connect(demo_world_dsn, autocommit=True, row_factory=tuple_row) as conn:
        resolved = resolve_credential_id(conn, DEMO_SIGNER)
        row = conn.execute(
            "SELECT count(*) FROM mainline.signing_credential WHERE credential_id = %s",
            (DERIVED_SIGNER_CREDENTIAL,),
        ).fetchone()

    assert row is not None
    assert row[0] == 0, (
        f"{CREDENTIAL_ID_SOURCE} enrols the value gate_run used to DERIVE. The seed has "
        "been reshaped to match an application constant, which is the reconciliation "
        "docs/leads/demo-truth-plan.md §1 rejected on the merits."
    )
    derived = resolved == DERIVED_SIGNER_CREDENTIAL
    assert not derived, "the resolver returned the derived constant rather than the enrolled row"


# ── The class: a value no derivation can produce ────────────────────────────────────


@pytest.mark.requires_cluster
def test_resolution_is_not_derivation(demo_world_conn: psycopg.Connection[Any]) -> None:
    """A random credential id resolves exactly, so no derivation of any kind can pass.

    This is the test the previous three waves did not have. Every earlier fixture built
    its credential id with the same expression the code used, so the assertion held for a
    reason that had nothing to do with the database. Here the id is 32 bytes from
    ``secrets`` — unknowable to the module under test — and the only way to return it is to
    have read the row.
    """
    subject = _subject()
    unpredictable = secrets.token_bytes(32)
    _enrol(demo_world_conn, subject, unpredictable)

    matches = resolve_credential_id(demo_world_conn, subject) == unpredictable

    assert matches, (
        f"resolve_credential_id did not return the credential enrolled for {subject!r}; a "
        "value this subject's credential could not have been derived from is exactly what "
        "this test enrolled"
    )


@pytest.mark.requires_cluster
def test_a_revoked_credential_is_not_a_candidate(
    demo_world_conn: psycopg.Connection[Any],
) -> None:
    """``revoked_at IS NULL`` is the filter, and a revoked key is refused by name.

    The revoked rows stay in the table forever — a 2029 signature must still verify in
    2036 (migration 0023's rationale) — so "present" and "usable" are different questions
    and only the second one may answer a signing path.
    """
    subject = _subject()
    _enrol(demo_world_conn, subject, secrets.token_bytes(32), revoked=True)

    with pytest.raises(CredentialNotEnrolled) as raised:
        resolve_credential_id(demo_world_conn, subject)

    assert raised.value.live == 0
    assert subject in str(raised.value)


@pytest.mark.requires_cluster
def test_a_live_credential_beside_a_revoked_one_is_still_resolved(
    demo_world_conn: psycopg.Connection[Any],
) -> None:
    """Revocation removes a candidate; it does not make the subject unresolvable."""
    subject = _subject()
    live = secrets.token_bytes(32)
    _enrol(demo_world_conn, subject, secrets.token_bytes(32), revoked=True)
    _enrol(demo_world_conn, subject, live)

    matches = resolve_credential_id(demo_world_conn, subject) == live
    assert matches, f"the live credential enrolled for {subject!r} was not the one resolved"


@pytest.mark.requires_cluster
def test_two_live_credentials_are_refused_rather_than_chosen_between(
    demo_world_conn: psycopg.Connection[Any],
) -> None:
    """A disposition names one credential, so an ambiguous subject is a refusal.

    ``pk_signing_credential`` is on ``credential_id`` alone, so two live credentials for
    one subject is a legal state of the database. Picking the first would make the
    signature depend on scan order, and a demo whose exhibit depends on scan order is not
    an exhibit.
    """
    subject = _subject()
    _enrol(demo_world_conn, subject, secrets.token_bytes(32))
    _enrol(demo_world_conn, subject, secrets.token_bytes(32))

    with pytest.raises(CredentialAmbiguous) as raised:
        resolve_credential_id(demo_world_conn, subject)

    assert raised.value.live == 2
    assert raised.value.signer_sub == subject
    message = str(raised.value)
    assert subject in message
    assert CREDENTIAL_ID_SOURCE in message
    assert "2" in message


# ── The refusal is typed, names the subject, and is a 422 rather than a 500 ─────────


@pytest.mark.requires_cluster
def test_an_unenrolled_subject_is_refused_by_name(
    demo_world_conn: psycopg.Connection[Any],
) -> None:
    """The message names the subject AND the table, so the failure is actionable at sight.

    Before this module existed the same condition arrived as ``23503
    disposition_signer_credential_id_fkey`` from an INSERT nested in beat 4's savepoint,
    where the demo diagnosed it as a refusal and reported it as though the gate had
    spoken. The constraint name told a reader which column was wrong and nothing about
    which SUBJECT had no credential, which is the only fact that leads to a fix.
    """
    subject = _subject()

    with pytest.raises(CredentialNotEnrolled) as raised:
        resolve_credential_id(demo_world_conn, subject)

    message = str(raised.value)
    assert subject in message
    assert CREDENTIAL_ID_SOURCE in message
    assert raised.value.signer_sub == subject
    assert raised.value.table == CREDENTIAL_ID_SOURCE
    assert "MAINLINE_DEMO_SIGNER_SUB" in message
    assert "demo_world.sql" in message


@pytest.mark.requires_cluster
def test_the_refusal_is_the_class_the_handler_already_answers_with_422(
    demo_world_conn: psycopg.Connection[Any],
) -> None:
    """Both refusals are ``ScenarioNotSeeded``, which ``handle_transition`` maps to 422.

    Not decoration: ``transitions.handle_transition`` catches ``ScenarioNotSeeded`` and
    returns ``422 demo_history_not_seeded`` carrying ``exc.detail``. An exception outside
    that class would fall through to the generic arm and reach a judge as a 500 — a
    transport failure where the truth is "this database has not enrolled that signer".
    """
    subject = _subject()
    with pytest.raises(ScenarioNotSeeded) as absent:
        resolve_credential_id(demo_world_conn, subject)
    assert isinstance(absent.value, CredentialUnresolvable)
    assert absent.value.detail == str(absent.value)

    _enrol(demo_world_conn, subject, secrets.token_bytes(32))
    _enrol(demo_world_conn, subject, secrets.token_bytes(32))
    with pytest.raises(ScenarioNotSeeded):
        resolve_credential_id(demo_world_conn, subject)


# ── The regression guard, which needs no cluster and therefore runs in every lane ────


def _gate_run_function() -> ast.FunctionDef:
    """The ``gate_run`` function's AST, parsed from the shipped source file."""
    tree = ast.parse(GATE_RUN_SOURCE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "gate_run":
            return node
    raise AssertionError(f"{GATE_RUN_SOURCE} defines no top-level function `gate_run`")


def test_no_module_derives_a_credential_id() -> None:
    """``_sha("cred", …)`` must not come back into ANY module of this package.

    WIDENED 2026-08-13, from ``gate_run.py`` alone to the whole package, because scoping it
    to one file is precisely how the defect it guards survived being fixed. ``gate_run.py``
    was corrected; ``transitions.py`` bound the identical derived constant twenty lines into
    ``_sign_disposition`` and this ratchet — watching one file — stayed green over it. The
    endpoint a judge reaches by signing a disposition directly would have failed ``23503``
    exactly as beat 4 did, for exactly the same reason, after the reason was understood and
    written down. A ratchet narrower than the class it guards certifies the instance and
    licenses the twin.

    An AST walk rather than a substring search, deliberately: several modules here quote the
    old expression in their docstrings in order to explain why it went, and a grep would
    either flag the explanation or be loosened until it flagged nothing. The walk asks the
    only question that matters — is there a CALL to ``_sha`` whose first argument is the
    string ``"cred"`` — and it is indifferent to prose.

    The other ``_sha`` call sites are left alone and are not in scope: the defeater
    vocabulary, the evidence digest, the authenticator data and the competency digest are
    synthetic values with no foreign key. Nothing in the database owns them, so nothing
    there can be read instead.
    """
    derived: dict[str, list[int]] = {}
    for source in sorted(PACKAGE_SOURCE.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_sha"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "cred"
        ]
        if hits:
            derived[source.name] = hits

    assert derived == {}, (
        f"{len(derived)} module(s) in {PACKAGE_SOURCE.name} derive a credential id: "
        f"{derived}. signer_credential_id is a FOREIGN KEY onto {CREDENTIAL_ID_SOURCE}: the "
        "table owns the value and mainline_demo_api.credentials.resolve_credential_id reads "
        "it. A derived constant agrees with whatever fixture shares the expression and with "
        "no seed that is deployed — that is how 23503 reached a judge on 2026-08-13, and "
        "how it then survived its own fix in a second module."
    )


def test_gate_run_resolves_the_credentials_it_binds() -> None:
    """``gate_run`` calls the resolver, once per signing subject."""
    calls = [
        node
        for node in ast.walk(_gate_run_function())
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_credential_id"
    ]
    assert len(calls) == 2, (
        "gate_run must resolve exactly two credential ids — the signer's and the "
        f"countersigner's — from {CREDENTIAL_ID_SOURCE}; found {len(calls)} call(s)"
    )


def test_the_credentials_are_resolved_before_the_beats_transaction_opens() -> None:
    """Resolution precedes ``SET TRANSACTION ISOLATION LEVEL SERIALIZABLE``.

    Order is the requirement, not an implementation detail. Resolving inside the beats'
    transaction would put a missing credential back where it started: a ``23503`` caught by
    beat 4's savepoint, diagnosed, and reported as a refusal on a run that still answers
    200 and still says ``NOT PROVEN`` in a field nobody reads. Resolving first makes it a
    precondition that fails while there is nothing to roll back.
    """
    function = _gate_run_function()
    resolved_at = min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_credential_id"
    )
    opened_at = min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("SET TRANSACTION ISOLATION LEVEL")
    )
    assert resolved_at < opened_at, (
        f"gate_run resolves its credential ids at line {resolved_at}, after the beats' "
        f"transaction opens at line {opened_at}. A credential that is missing must be a "
        "precondition failure naming the subject, not a foreign-key violation inside beat "
        "4's savepoint that the demo would report as a refusal the gate never made."
    )


# ── The wiring, end to end, on the database the deploy actually seeds ────────────────


@pytest.mark.requires_cluster
def test_beat_four_admits_against_the_deployed_seed(demo_world_dsn: str) -> None:
    """The whole reason this change exists: four beats, ``PROVEN``, on ``demo_world.sql``.

    Measured through :func:`mainline_demo_api.gate_run.gate_run` on a connection carrying
    ``db.py``'s own row factory, against a database seeded from the two files
    ``scripts/deploy/seed_demo.py`` applies — which is the configuration that returned
    ``23503 disposition_signer_credential_id_fkey`` and ``verdict: NOT PROVEN`` before the
    resolver existed. The run rolls itself back, so this test may be repeated forever
    against the same database.
    """
    from mainline_demo_api.gate_run import gate_run
    from mainline_demo_api.scenario import from_env

    scenario = from_env(
        {
            "MAINLINE_DEMO_PERMIT_ID": str(DEMO_PERMIT_ID),
            "MAINLINE_DEMO_SITE_ID": str(DEMO_SITE_ID),
            "MAINLINE_DEMO_SIGNER_SUB": DEMO_SIGNER,
            "MAINLINE_DEMO_COUNTERSIGNER_SUB": DEMO_COUNTERSIGNER,
        }
    )
    # dict_row: `db.connection()` opens every production connection with it, and beat 4's
    # INSERT has to be correct under the factory the Lambda actually runs.
    conn = psycopg.connect(demo_world_dsn, autocommit=False, row_factory=dict_row)
    try:
        payload = gate_run(conn, scenario)
    finally:
        conn.rollback()
        conn.close()

    admission = payload["beats"][3]
    assert admission["name"] == "admit"
    assert admission["outcome"] == "admitted", (
        f"beat 4 did not admit: sqlstate={admission['sqlstate']!r} "
        f"constraint={admission['constraint']!r} note={admission['note']!r}"
    )
    assert admission["sqlstate"] == "00000"
    assert payload["failures"] == []
    assert payload["verdict"] == "PROVEN"
    assert payload["persistence_check"]["identical"] is True


def test_the_seed_files_this_suite_runs_against_are_the_ones_the_deploy_applies() -> None:
    """``SEED_FILES`` here is the list ``scripts/deploy/seed_demo.py`` applies.

    Needs no cluster. If the deploy ever seeds a third file, or renames one, this suite
    would silently go on proving things about a seed nobody ships — which is the exact
    shape of the defect it was written to close.
    """
    source = (REPO_ROOT / "scripts/deploy/seed_demo.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    declared: tuple[str, ...] | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign | ast.Assign):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            names = {t.id for t in targets if isinstance(t, ast.Name)}
            if "SEED_FILES" in names and node.value is not None:
                declared = tuple(ast.literal_eval(node.value))
    assert declared is not None, "scripts/deploy/seed_demo.py declares no SEED_FILES"
    assert declared == SEED_FILES, (
        f"the deploy applies {declared} and this suite seeds {SEED_FILES}. Fix the suite — "
        "a test that runs against a seed nobody deploys is what let 23503 reach a judge."
    )


def test_every_seed_file_this_suite_names_exists() -> None:
    """Needs no cluster: a renamed seed must be a red test, not a skip nobody reads."""
    missing = [name for name in SEED_FILES if not (SEEDS_DIR / name).is_file()]
    assert missing == [], f"{missing} are named by this suite and absent from {SEEDS_DIR}"


def test_the_migrations_directory_this_suite_builds_from_is_present() -> None:
    """Needs no cluster: the fixture's chain source, asserted where it is cheap to assert."""
    assert Path(MIGRATIONS_DIR).is_dir()


def test_the_resolver_reads_the_table_its_refusals_name() -> None:
    """The statement's table and the name every refusal prints are the same table.

    ``_CREDENTIAL_SQL`` spells the table out — an f-string over a constant is a real
    ``S608`` shape and a statement assembled from variables is one a reader cannot check by
    reading. That leaves two literals in one module, so their agreement is asserted here
    rather than trusted: a refusal that named a table the query never read would send its
    reader to the wrong place, which is the failure this whole module exists to end.
    """
    from mainline_demo_api import credentials

    assert CREDENTIAL_ID_SOURCE in credentials._CREDENTIAL_SQL
    assert "revoked_at IS NULL" in credentials._CREDENTIAL_SQL
    assert "ORDER BY credential_id" in credentials._CREDENTIAL_SQL
