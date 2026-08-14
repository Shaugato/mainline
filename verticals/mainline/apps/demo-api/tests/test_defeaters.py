# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The defeater vocabulary a signature pins, and the ``40001`` loop the handler carries.

WHAT WENT WRONG, MEASURED RATHER THAN RECOUNTED
------------------------------------------------
``gate_run.py:608`` and ``transitions.py:1065`` both bound ``_sha("defeater-vocab")``.
That is ``sha256(b"defeater-vocab")`` = :data:`CONSTANT_THAT_PINNED_NOTHING`, and it is
byte-for-byte the value the DEPLOYED CockroachDB Cloud recorded on its one signed
disposition — decode ``response.body_b64`` of
``console/fixtures/bundles/demo-cloud/frames/GET-f116fc2724f1b968.json`` and read
``signed.defeater_vocab_sha256``. The same frame carries ``"defeater_options": []``. So the
judge-facing deployment recorded the digest of an ASCII string as the digest of a
vocabulary that did not exist.

``0064_defeater_option.sql`` says the column *"digests the whole option set, not the row,
so a signature that pins it pins the ALTERNATIVES the signer declined as well as the one
they chose"*. ``disposition.schema.json`` says *"A disposition records the same digest, so
a later regeneration cannot silently reinterpret a past signature"*. Both were false of
that code, and seeding the option rows without closing this would have left them false.

WHY THESE TESTS CAN DISAGREE WITH THE CODE
-------------------------------------------
The digest this suite expects is **32 bytes from ``secrets``**, committed into this
module's own database and unknowable to the module under test. No derivation of any kind
can produce it; the only way to return it is to have read the row. That is the shape
``test_credentials.py::test_resolution_is_not_derivation`` established after four files
agreed with each other about a credential id and with no seed that ships, and it is the
only shape in which "the application resolves rather than computes" is a claim a test can
falsify.

The vocabulary's own *derivation* — what ``demo_world.sql`` digests to produce
``vocab_sha256`` — is the SEED's business and W1's file. Nothing here asserts anything
about it, and nothing here would notice if it changed. What is asserted is narrower and is
the whole of this worker's half: whatever the database holds, the application records THAT
and never a constant.

THE DATABASE
------------
This module's own, named for the migration-and-seed fingerprint the way
``conftest.demo_database`` and ``test_credentials.demo_world_dsn`` name theirs, and reused
between sessions. It is not the shared ``w3_demo_api_…`` world, because exactly ONE write
is committed into it and that write would change what every other module observes: the
defeater vocabulary, **and only when the deployed seed does not already carry one**.

That is stated out loud rather than buried in a fixture, because it is the seam between
this worker's half of blocker 1 and W1's. The seed owes those rows; until it carries them,
this suite has to be able to prove the RUNTIME half against a tree where the debt is still
outstanding, and it must step aside the moment the debt is paid — so if the check already
offers options, nothing is written and every assertion runs against the seed's own values.
Injecting them into the shared world instead would have turned another worker's failing
test green from a fixture, which is the parallel-world defect ``conftest`` was rewritten to
delete.

Nothing else is committed. Every other write — a second generation, an emptied vocabulary,
a signature — happens inside a transaction that is rolled back, so the seeded obligation
stays open and the gate-run test can keep proving that the whole judge path completes.
"""

from __future__ import annotations

import ast
import hashlib
import random
import secrets
import uuid
from collections.abc import Iterator
from typing import Any, Final

import psycopg
import pytest
from mainline_demo_api.defeaters import (
    DEFEATER_VOCABULARY_SOURCE,
    DefeaterNotOffered,
    DefeaterVocabularyAbsent,
    DefeaterVocabularyAmbiguous,
    DefeaterVocabularyUnresolvable,
    resolve_defeater_vocabulary,
)
from mainline_demo_api.scenario import Scenario, ScenarioNotSeeded, from_env
from psycopg.rows import dict_row, tuple_row

from conftest import MIGRATIONS_DIR, REPO_ROOT, _apply_chain, _apply_seeds, _dsn_for, _fingerprint

#: ``sha256(b"defeater-vocab")``. Spelled as a literal, never computed from the expression
#: the code used: importing or re-deriving the old constant is precisely the mistake that
#: let four files agree with each other about a credential id. This value must never be
#: recorded by this API again, and ``test_the_constant_that_pinned_nothing_is_recorded_by_nobody``
#: is what makes "never" a property of the suite rather than a resolution.
CONSTANT_THAT_PINNED_NOTHING: Final = bytes.fromhex(
    "7ad8d49c2edd93f0a8fd3cd6b2a5d6cd225810805527a1a3f2f497aec819db3f"
)

#: The code the demo's one signature names. Written here as the literal the authorities
#: carry — ``demo-cloud/sql/beat-4-merge-admitted-00000.txt`` (outcome ADMITTED) and
#: ``GET-f116fc2724f1b968.json``'s ``signed.defeater_code`` — rather than imported from
#: ``gate_run``, so that this file can DISAGREE with the module it tests.
#: ``test_the_demo_names_the_code_the_captures_carry`` is where the two are compared.
DEMO_DEFEATER_CODE: Final = "MECHANISM_PRESENT_AND_VERIFIED"

PACKAGE_SOURCE: Final = REPO_ROOT / "verticals/mainline/apps/demo-api/src/mainline_demo_api"

#: A rationale long enough for ``CONSTRAINT substantive CHECK (length(rationale) >= 120)``
#: and for the API's own 120-character floor. A one-word clearance is not a clearance.
_RATIONALE: Final = (
    "The recalled precursor is answered by a verified zero-energy isolation procedure "
    "re-issued after the incident, and this permit's scope is covered by that procedure in "
    "full, witnessed at zero before any intrusive work begins."
)

_INSERT_OPTION_SQL: Final = """
INSERT INTO mainline.defeater_option (check_id, defeater_code, prompt, vocab_sha256)
VALUES (%s, %s, %s, %s)
"""

_OPTIONS_SQL: Final = """
SELECT defeater_code, vocab_sha256
  FROM mainline.defeater_option
 WHERE check_id = %s
 ORDER BY defeater_code
"""

_LIVE_DISPOSITION_SQL: Final = """
SELECT defeater_code, defeater_vocab_sha256
  FROM mainline.disposition
 WHERE check_id = %s AND retracted_by IS NULL
 ORDER BY signed_at DESC
 LIMIT 1
"""


# ── The database: migrations, the deployed seed, and a vocabulary if the seed lacks one ─


def _sole_check(conn: psycopg.Connection[Any]) -> uuid.UUID:
    """The one obligation on the seeded PERMIT, read back out of the database.

    EXACTLY ONE, never "the first". ``conftest._sole`` makes the same argument for the same
    reason: "the seed is present" and "the seed is the only thing present" are different
    sentences, and a ``LIMIT 1`` would turn leftovers from a half-finished rebuild into a
    silently different subject.

    Scoped to the permit because the deployed seed carries TWO obligations and they belong
    to different subjects — ``mainline.blocking_check`` holds one row whose ``permit_id`` is
    the demo permit and one whose ``permit_id`` is NULL because it hangs off the change
    request instead (``CONSTRAINT exactly_one_subject``). Measured on the seeded database:
    ``dec0de00-0007-…`` on permit ``dec0de00-0006-…``, and ``dec0de00-000d-…`` on neither.
    The unscoped query returned both, which is a fixture reading the world wrongly rather
    than a seed carrying too much.
    """
    permits = (
        conn.cursor(row_factory=tuple_row)
        .execute("SELECT permit_id FROM mainline.permit")
        .fetchall()
    )
    assert len(permits) == 1, (
        f"the seeded database holds {len(permits)} mainline.permit rows where exactly one "
        "is required. This database was built from the two files "
        "scripts/deploy/seed_demo.py applies to CockroachDB Cloud."
    )
    rows = (
        conn.cursor(row_factory=tuple_row)
        .execute(
            "SELECT check_id FROM mainline.blocking_check WHERE permit_id = %s",
            (permits[0][0],),
        )
        .fetchall()
    )
    assert len(rows) == 1, (
        f"the seeded database holds {len(rows)} mainline.blocking_check rows for permit "
        f"{permits[0][0]} where exactly one is required. If the seed no longer produces one "
        "obligation on the demo permit then the DEPLOYED demo no longer carries one either, "
        "and that is the defect rather than this assertion."
    )
    return uuid.UUID(str(rows[0][0]))


def _seed_vocabulary_if_absent(conn: psycopg.Connection[Any], check_id: uuid.UUID) -> None:
    """Commit a vocabulary for *check_id* when the deployed seed carries none.

    THIS IS A FIXTURE STEP AND IT IS NOT A SEED EDIT. ``verticals/mainline/db/seeds/demo/
    demo_world.sql`` owes these rows — the console declares the vocabulary
    (``surfaces.ts:84``, ``a11y/contract.ts`` step ``defeater``),
    ``disposition.schema.json`` puts ``defeater_options`` in ``required``, and 0064 says the
    set is generated per check. Landing them there is W1's file and W1's ruling. What this
    function does is make the RUNTIME half provable while that debt is outstanding, in a
    database nothing deploys from, and it stands aside the instant the seed carries the
    rows: if the check already has options, nothing is written and every assertion below
    runs against the seed's own values instead.

    The digest is ``secrets.token_bytes(32)``. That is the point of it: the resolver cannot
    guess it, cannot derive it, and can only return it by having read the row.
    """
    held = conn.cursor(row_factory=tuple_row).execute(_OPTIONS_SQL, (check_id,)).fetchall()
    if held:
        return

    vocab = secrets.token_bytes(32)
    for code, prompt in (
        (DEMO_DEFEATER_CODE, "Is the isolation mechanism present and verified at zero?"),
        ("PRECLUDES_HAZARD", "Which property of this scope precludes the hazard entirely?"),
        ("MECHANISM_ABSENT_PROVED", "Which precondition of this mechanism is absent?"),
    ):
        conn.execute(_INSERT_OPTION_SQL, (check_id, code, prompt, vocab))


def _apply_chain_once_more(dsn: str) -> tuple[int, list[str]]:
    """``conftest._apply_chain``, with the files that failed attempted once more.

    MEASURED, not defensive programming. Building this database on 2026-08-14 returned
    ``105 of 271 migrations did not apply``, every one of them ``3F000 cannot create
    "<schema>.<object>" because the target database or schema does not exist`` — against a
    database whose ``information_schema.schemata`` listed ``mainline``, ``mainline_meas``,
    ``mainline_audit``, ``mainline_qa``, ``mainline_ops`` and ``trappoint``. Re-executing
    the first-named file by hand a minute later applied it without complaint, and two
    fresh builds immediately afterwards — one with the zone configuration, one without —
    applied all 271 with zero failures. So the condition is transient descriptor
    visibility on this cluster and not a defect in the chain.

    Which is exactly why the retry is BOUNDED and reported. Only the files that failed are
    re-attempted, once, on a new connection; a file that fails twice is returned as a
    failure and this module skips with the reason. A fixture that looped until green would
    convert a real broken migration into a hang, and a fixture that swallowed the second
    failure would convert it into a lie.
    """
    applied, failures = _apply_chain(dsn)
    if not failures:
        return applied, failures

    names = [line.split(" ", 1)[0] for line in failures]
    still: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as conn:
        for name in names:
            path = MIGRATIONS_DIR / name
            try:
                conn.execute(path.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            except psycopg.Error as exc:
                still.append(f"{name} [{exc.sqlstate}] {str(exc).splitlines()[0][:120]}")
            else:
                applied += 1
    return applied, still


@pytest.fixture(scope="session")
def defeater_dsn(admin_dsn: str) -> tuple[str, uuid.UUID]:
    """A migrated, seeded database whose one obligation offers a defeater vocabulary.

    Returns ``(dsn, check_id)``. Named for the fingerprint over every migration and every
    seed file, so an edited seed builds a NEW database rather than adopting one built
    against bytes that no longer exist — which is the failure ``conftest._fingerprint``
    exists to prevent and the reason W1's seed change cannot silently be read against this
    module's cache.
    """
    database = f"w2_defeaters_{_fingerprint()}"
    dsn = _dsn_for(admin_dsn, database)

    def prepared() -> uuid.UUID | None:
        """The check this database is ready to be asked about, or ``None`` to rebuild.

        ``AssertionError`` is caught beside ``psycopg.Error`` on purpose: a database left
        half-built by an interrupted session answers ``_sole_check`` with the wrong number
        of rows, and "this cache is unusable" is a reason to rebuild rather than a finding
        about the seed. On the freshly-built path the same call is allowed to fail loudly,
        below, because there it IS a finding about the seed.
        """
        try:
            with psycopg.connect(dsn, autocommit=True, connect_timeout=5) as probe:
                check_id = _sole_check(probe)
                _seed_vocabulary_if_absent(probe, check_id)
        except (psycopg.Error, AssertionError):
            return None
        return check_id

    ready = prepared()
    if ready is not None:
        return dsn, ready

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{database}" CASCADE')
        admin.execute(f'CREATE DATABASE "{database}"')
        # Cloud runs gc.ttlseconds = 4500; pinning the stricter value locally means an
        # `AS OF SYSTEM TIME` that works here works there.
        admin.execute(f'ALTER DATABASE "{database}" CONFIGURE ZONE USING gc.ttlseconds = 4500')

    applied, failures = _apply_chain_once_more(dsn)
    if failures:
        pytest.skip(
            f"{len(failures)} of {applied + len(failures)} migrations under {MIGRATIONS_DIR} "
            f"did not apply into {database} — twice, on two connections — so the deployed "
            "seed cannot be applied on top of them and the defeater resolver cannot be "
            "exercised against it. First three: " + "; ".join(failures[:3])
        )

    seed_failures = _apply_seeds(dsn)
    if seed_failures:
        # A FAILURE, not a skip: these are committed files against a schema this session
        # has just built from the committed migration chain, so nothing about the
        # environment can explain one of them refusing.
        pytest.fail(
            f"the deployed demo seed did not apply into {database}. This is the seed "
            "scripts/deploy/seed_demo.py applies to CockroachDB Cloud, so a failure here "
            "is a failure there. " + "; ".join(seed_failures)
        )

    # NOT through `prepared()`: that swallows the reason in order to decide "rebuild", and
    # on this path there is nothing left to rebuild. A seed that applied and then could not
    # be read back is a finding about the seed, and it is allowed to say what it was.
    with psycopg.connect(dsn, autocommit=True) as fresh:
        built = _sole_check(fresh)
        _seed_vocabulary_if_absent(fresh, built)
    return dsn, built


def _scenario_for(conn: psycopg.Connection[Any]) -> Scenario:
    """The scenario naming the subjects THIS database seeded, read rather than assumed.

    ``scenario.from_env({})`` falls back to a uuid5 derivation of ``permit`` that nothing in
    the deployed seed mints — the seed's permit is ``dec0de00-0006-…`` — so a scenario built
    from an empty environment names a permit this database does not hold, and
    ``_demo_guard`` refuses with ``423 demo_subject_unidentified``. That refusal is correct
    and is another worker's finding (``test_gate_run.py`` pins the same gap); it is not
    something this module may route around by pretending, so the identifiers are read out
    of the database the way ``conftest._identifiers`` reads them.
    """
    permit = (
        conn.cursor(row_factory=tuple_row)
        .execute("SELECT permit_id, site_id FROM mainline.permit")
        .fetchall()
    )
    assert len(permit) == 1
    return from_env(
        {
            "MAINLINE_DEMO_PERMIT_ID": str(permit[0][0]),
            "MAINLINE_DEMO_SITE_ID": str(permit[0][1]),
        }
    )


@pytest.fixture
def offered(defeater_dsn: tuple[str, uuid.UUID]) -> Iterator[psycopg.Connection[Any]]:
    """A rolled-back connection carrying ``dict_row`` — the factory ``db.py`` opens with.

    Every test that writes writes here, and nothing it writes survives.
    """
    conn = psycopg.connect(defeater_dsn[0], autocommit=False, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


# ── The resolver returns what the table offers, and could not have guessed it ────────


@pytest.mark.requires_cluster
@pytest.mark.parametrize("factory", [dict_row, tuple_row], ids=["dict_row", "tuple_row"])
def test_the_resolver_returns_exactly_what_the_table_offers(
    defeater_dsn: tuple[str, uuid.UUID], factory: Any
) -> None:
    """Codes and digest come back verbatim, under either row factory.

    The expectation is built by an INDEPENDENT statement asked of the same database, so it
    comes from the rows rather than from the function under test. The digest is 32 bytes of
    ``secrets`` (or, once W1 has landed, whatever ``demo_world.sql`` generated); either way
    it is a value no derivation in ``mainline_demo_api`` can produce, which is what makes
    this test one the code can fail.
    """
    dsn, check_id = defeater_dsn
    with psycopg.connect(dsn, autocommit=True, row_factory=factory) as conn:
        resolved = resolve_defeater_vocabulary(conn, check_id)
        rows = conn.cursor(row_factory=tuple_row).execute(_OPTIONS_SQL, (check_id,)).fetchall()

    assert rows, f"{DEFEATER_VOCABULARY_SOURCE} offers nothing for check {check_id}"
    assert resolved.check_id == check_id
    assert resolved.codes == tuple(str(row[0]) for row in rows)
    assert resolved.vocab_sha256 == bytes(rows[0][1])
    assert len(resolved.vocab_sha256) == 32
    assert resolved.vocab_sha256 != CONSTANT_THAT_PINNED_NOTHING


@pytest.mark.requires_cluster
def test_the_resolver_reads_the_row_rather_than_deriving_it(
    offered: psycopg.Connection[Any], defeater_dsn: tuple[str, uuid.UUID]
) -> None:
    """A digest drawn from ``secrets`` resolves exactly, so no derivation can pass.

    The rows already there are deleted first, inside a transaction that is rolled back, so
    the only generation in view is the unpredictable one this test just wrote. This is the
    test the previous shape of the code could not have had: every value it might have
    computed is knowable from the source, and this one is not.
    """
    check_id = defeater_dsn[1]
    unpredictable = secrets.token_bytes(32)
    offered.execute("DELETE FROM mainline.defeater_option WHERE check_id = %s", (check_id,))
    offered.execute(
        _INSERT_OPTION_SQL, (check_id, "SCOPE_EXCLUDES_HAZARD", "Which scope?", unpredictable)
    )

    resolved = resolve_defeater_vocabulary(offered, check_id)

    matches = resolved.vocab_sha256 == unpredictable
    assert matches, (
        "resolve_defeater_vocabulary did not return the digest this test committed to "
        f"{DEFEATER_VOCABULARY_SOURCE}; a value it cannot derive is exactly what was written"
    )
    assert resolved.codes == ("SCOPE_EXCLUDES_HAZARD",)


# ── An empty vocabulary refuses. It does not default, and it does not return None ────


@pytest.mark.requires_cluster
def test_an_empty_vocabulary_raises_rather_than_defaulting(
    offered: psycopg.Connection[Any], defeater_dsn: tuple[str, uuid.UUID]
) -> None:
    """No rows is a refusal with a stated reason — never a constant, never ``None``.

    This is the assertion that keeps the shipped defect shut. A resolver that answered
    "nothing, carry on" would be asked to, and the caller would substitute something; the
    something it substituted last time was ``sha256(b"defeater-vocab")``, and because
    ``mainline.disposition`` has no foreign key onto ``mainline.defeater_option`` nothing in
    the database noticed for as long as the demo has existed.
    """
    check_id = defeater_dsn[1]
    offered.execute("DELETE FROM mainline.defeater_option WHERE check_id = %s", (check_id,))

    with pytest.raises(DefeaterVocabularyAbsent) as raised:
        resolve_defeater_vocabulary(offered, check_id)

    assert raised.value.options == 0
    assert raised.value.generations == 0
    assert raised.value.check_id == check_id
    assert raised.value.table == DEFEATER_VOCABULARY_SOURCE
    message = str(raised.value)
    assert str(check_id) in message
    assert DEFEATER_VOCABULARY_SOURCE in message
    assert "this check offers no defeater vocabulary" in message
    assert "signature cannot pin one" in message
    assert "demo_world.sql" in message


@pytest.mark.requires_cluster
def test_the_empty_refusal_is_the_class_the_handler_already_answers_with_422(
    offered: psycopg.Connection[Any], defeater_dsn: tuple[str, uuid.UUID]
) -> None:
    """``ScenarioNotSeeded``, which ``handle_transition`` maps to 422, not to a 500.

    Not decoration, and the same argument ``test_credentials.py`` makes for the credential
    refusals: an exception outside that class falls through to the generic arm and reaches
    a judge as a transport failure, where the truth is "this database has not seeded the
    options this check must offer".
    """
    check_id = defeater_dsn[1]
    offered.execute("DELETE FROM mainline.defeater_option WHERE check_id = %s", (check_id,))

    with pytest.raises(ScenarioNotSeeded) as raised:
        resolve_defeater_vocabulary(offered, check_id)

    assert isinstance(raised.value, DefeaterVocabularyUnresolvable)
    assert raised.value.detail == str(raised.value)


@pytest.mark.requires_cluster
def test_two_generations_are_refused_rather_than_chosen_between(
    offered: psycopg.Connection[Any], defeater_dsn: tuple[str, uuid.UUID]
) -> None:
    """Several distinct digests is a corrupt generation, and the refusal names the count.

    0064: the digest "IS THE SAME VALUE ON EVERY ROW OF ONE GENERATION". Two of them mean
    two generations are interleaved, and a signature pinning either would pin an option set
    that was never on one screen. Picking the first would make the demo's exhibit depend on
    scan order, which is the same reason ``credentials.resolve_credential_id`` refuses a
    subject holding two live keys.
    """
    check_id = defeater_dsn[1]
    offered.execute("DELETE FROM mainline.defeater_option WHERE check_id = %s", (check_id,))
    offered.execute(_INSERT_OPTION_SQL, (check_id, "A_CODE", "a?", secrets.token_bytes(32)))
    offered.execute(_INSERT_OPTION_SQL, (check_id, "B_CODE", "b?", secrets.token_bytes(32)))

    with pytest.raises(DefeaterVocabularyAmbiguous) as raised:
        resolve_defeater_vocabulary(offered, check_id)

    assert raised.value.options == 2
    assert raised.value.generations == 2
    message = str(raised.value)
    assert "2 distinct vocab_sha256" in message
    assert "A_CODE" in message and "B_CODE" in message


# ── A code that was never offered is refused, because no foreign key will refuse it ──


@pytest.mark.requires_cluster
def test_a_code_that_was_never_offered_is_refused_by_name(
    defeater_dsn: tuple[str, uuid.UUID],
) -> None:
    """``require`` is the foreign key ``mainline.disposition`` does not have.

    Verified in the schema rather than assumed: ``0066_disposition.sql`` declares
    ``defeater_code STRING NOT NULL`` under one constraint,
    ``disposition_defeater_code_stated CHECK (defeater_code <> '')``, and no ``REFERENCES
    mainline.defeater_option`` anywhere. RULING R9 forbids adding that key four days from a
    deadline because migrations are rendered under a zero-diff assertion; this is the
    assertion that closes the gap instead, so it has to be able to fail.
    """
    dsn, check_id = defeater_dsn
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        vocabulary = resolve_defeater_vocabulary(conn, check_id)

    invented = "A_CODE_NO_SCREEN_EVER_SHOWED"
    assert not vocabulary.offers(invented)
    with pytest.raises(DefeaterNotOffered) as raised:
        vocabulary.require(invented)

    assert raised.value.defeater_code == invented
    assert raised.value.check_id == check_id
    assert raised.value.offered == vocabulary.codes
    message = str(raised.value)
    assert invented in message
    assert DEFEATER_VOCABULARY_SOURCE in message
    for code in vocabulary.codes:
        assert code in message

    # And the offered ones are accepted, so the guard is not simply refusing everything.
    for code in vocabulary.codes:
        assert vocabulary.require(code) == code


def test_the_disposition_table_still_has_no_foreign_key_onto_the_vocabulary() -> None:
    """The measured premise of ``require``, pinned where it is cheap to pin.

    Needs no cluster. If a later migration DOES add the key, this test goes red and its
    reader is told to relax the application check rather than leaving two enforcements that
    can disagree — which is a better failure than a silent duplication nobody revisits.
    """
    source = (REPO_ROOT / "verticals/mainline/db/migrations/0066_disposition.sql").read_text(
        encoding="utf-8"
    )
    assert "CONSTRAINT disposition_defeater_code_stated CHECK (defeater_code <> '')" in source
    assert "REFERENCES mainline.defeater_option" not in source, (
        "0066_disposition.sql now has a foreign key onto mainline.defeater_option, so the "
        "database refuses an unoffered code by itself and defeaters.DefeaterVocabulary."
        "require duplicates it. Two enforcements of one rule can disagree; decide which "
        "one is authoritative and delete the other."
    )


# ── The recorded digest is the offered set's, and is never the constant ──────────────


@pytest.mark.requires_cluster
def test_the_recorded_digest_is_the_offered_sets_and_not_the_constant(
    defeater_dsn: tuple[str, uuid.UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A signature through the real sign path pins the vocabulary the database offered.

    ``fn_disposition_project`` overwrites most of this row from authoritative sources;
    ``defeater_code`` and ``defeater_vocab_sha256`` are two of the four columns it does not
    touch (``0102_fn_disposition_project.sql`` assigns 27 members of ``NEW`` and neither of
    them is among them), which is exactly why they had to be got right in the application.

    THE COMMIT IS SUPPRESSED, AND THAT IS THE ONLY THING THAT IS. ``_sign_disposition``
    ends with ``conn.commit()``; a committed signature closes this obligation for good —
    ``mainline.disposition`` is retract-only, ``fn_disposition_close`` fires AFTER INSERT
    and there is no trigger to undo it — and the gate-run test below needs the obligation
    still open. So ``commit`` is replaced with a no-op for the length of the call and the
    row is read back INSIDE the same transaction, which then rolls back. Everything the
    assertion is about is real: the statement, its parameter list, the value bound into
    ``defeater_vocab_sha256`` and the projection trigger that ran over it. What is not
    exercised is durability, and durability is not what this test claims.

    Called directly rather than through ``handle_transition`` for the same reason:
    ``_borrowed``'s ``finally`` rolls the connection back on the way out, which would
    discard the row before it could be read. The routing and the envelope are asserted by
    the 422 test below, which does go through the front door.
    """
    from mainline_demo_api import transitions

    dsn, check_id = defeater_dsn
    monkeypatch.setenv("MAINLINE_DEMO_ALLOW_MUTATION", "1")

    conn = psycopg.connect(dsn, autocommit=False, row_factory=dict_row)
    conn.commit = lambda: None  # type: ignore[method-assign]
    try:
        vocabulary = resolve_defeater_vocabulary(conn, check_id)
        status, payload = transitions._sign_disposition(
            conn,
            check_id,
            {"defeater_code": DEMO_DEFEATER_CODE, "rationale": _RATIONALE},
            _scenario_for(conn),
        )
        assert status == 200, f"sign_disposition answered {status}: {payload}"
        recorded = (
            conn.cursor(row_factory=tuple_row).execute(_LIVE_DISPOSITION_SQL, (check_id,))
        ).fetchone()
    finally:
        del conn.commit
        conn.rollback()
        conn.close()

    assert recorded is not None, "no live disposition was recorded for the demo obligation"
    assert str(recorded[0]) == DEMO_DEFEATER_CODE
    pinned = bytes(recorded[1])
    assert pinned == vocabulary.vocab_sha256, (
        "the disposition pinned a digest that is not the one "
        f"{DEFEATER_VOCABULARY_SOURCE} carries for check {check_id}"
    )
    assert pinned != CONSTANT_THAT_PINNED_NOTHING, (
        "the signature recorded sha256(b'defeater-vocab') — the constant the deployed Cloud "
        "recorded on its one signed disposition, which pins the SHA-256 of an ASCII string "
        "and not a vocabulary. That is the defect this module exists to keep shut."
    )


@pytest.mark.requires_cluster
def test_a_body_naming_an_unoffered_code_is_422_and_names_what_is_offered(
    defeater_dsn: tuple[str, uuid.UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint refuses before the INSERT, and says which codes it would accept.

    ``422 unprocessable_request`` rather than a gate refusal, deliberately: the database
    refused nothing — it has no constraint to refuse with — so reporting this as a refusal
    would put an exhibit in front of a reader that no constraint produced.
    """
    from mainline_demo_api.transitions import handle_transition

    dsn, check_id = defeater_dsn
    monkeypatch.setenv("MAINLINE_DEMO_ALLOW_MUTATION", "1")

    conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    try:
        vocabulary = resolve_defeater_vocabulary(conn, check_id)
        permit = (
            conn.cursor(row_factory=tuple_row)
            .execute("SELECT permit_id FROM mainline.permit")
            .fetchone()
        )
        assert permit is not None
        monkeypatch.setenv("MAINLINE_DEMO_PERMIT_ID", str(permit[0]))
        status, payload = handle_transition(
            "sign_disposition",
            {"check_id": str(check_id)},
            {"defeater_code": "NEVER_ON_ANY_SCREEN", "rationale": _RATIONALE},
            conn,
        )
    finally:
        conn.rollback()
        conn.close()

    assert status == 422
    assert payload["error"] == "unprocessable_request"
    assert "NEVER_ON_ANY_SCREEN" in payload["detail"]
    for code in vocabulary.codes:
        assert code in payload["detail"]
    # Nothing was written: the refusal happens before the INSERT, so a caller who names a
    # code that was never offered has not left a half-signed obligation behind.
    with psycopg.connect(dsn, autocommit=True, row_factory=tuple_row) as after:
        assert (
            after.execute(
                "SELECT count(*) FROM mainline.disposition WHERE check_id = %s", (check_id,)
            ).fetchone()
            or (None,)
        )[0] == 0


@pytest.mark.requires_cluster
def test_the_gate_run_admits_and_is_proven_when_the_vocabulary_exists(
    defeater_dsn: tuple[str, uuid.UUID],
) -> None:
    """The whole judge path, through the real ``gate_run``, against an offered vocabulary.

    This is the measurement that separates "this change broke the demo" from "this change
    made a seed debt visible". Beat 4 resolves the digest from ``mainline.defeater_option``,
    checks its own defeater code for membership, signs, and the run reports ``PROVEN`` — on
    a database whose only difference from the deployed one is that the vocabulary
    ``demo_world.sql`` owes is present. Everywhere it is absent, the sign paths refuse with
    a stated reason, which is what RULING R4 requires of them.

    The run persists nothing, so this test may be repeated against the same database
    forever — and the persistence check is asserted rather than assumed, because a beat
    that left a row behind would close the obligation the tests above depend on.
    """
    from mainline_demo_api.gate_run import gate_run

    dsn, check_id = defeater_dsn
    conn = psycopg.connect(dsn, autocommit=False, row_factory=dict_row)
    try:
        vocabulary = resolve_defeater_vocabulary(conn, check_id)
        conn.rollback()
        payload = gate_run(conn, _scenario_for(conn))
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
    assert DEMO_DEFEATER_CODE in vocabulary.codes, (
        "beat 4 signs with this code, so a vocabulary that does not offer it must refuse "
        "the run rather than admit a signature naming a code no screen ever showed"
    )


@pytest.mark.requires_cluster
def test_the_constant_that_pinned_nothing_is_recorded_by_nobody(
    defeater_dsn: tuple[str, uuid.UUID],
) -> None:
    """No row in this database carries ``sha256(b"defeater-vocab")``, in either column.

    Both tables are checked because the constant can come back two ways: an application
    that binds it again, and a SEED that "fixes" the mismatch by making the DATABASE
    imitate the old constant. The second is the reconciliation the credential incident's
    plan rejected on the merits — a database fact must not be reshaped to match an
    application constant — and it would otherwise turn every assertion above green.
    """
    dsn, _check_id = defeater_dsn
    with psycopg.connect(dsn, autocommit=True, row_factory=tuple_row) as conn:
        row = conn.execute(
            "SELECT (SELECT count(*) FROM mainline.defeater_option WHERE vocab_sha256 = %s),"
            "       (SELECT count(*) FROM mainline.disposition "
            "         WHERE defeater_vocab_sha256 = %s)",
            (CONSTANT_THAT_PINNED_NOTHING, CONSTANT_THAT_PINNED_NOTHING),
        ).fetchone()

    assert row is not None
    assert row[0] == 0, (
        f"{DEFEATER_VOCABULARY_SOURCE} carries sha256(b'defeater-vocab') as a generation's "
        "digest. The seed has been reshaped to match an application constant."
    )
    assert row[1] == 0, (
        "a disposition in this database pins sha256(b'defeater-vocab'). The signature is "
        "recording the digest of an ASCII string again."
    )


# ── The ratchets. No cluster, so they run in every lane including --crdb=none ────────


def _package_trees() -> Iterator[tuple[str, ast.Module]]:
    for source in sorted(PACKAGE_SOURCE.rglob("*.py")):
        yield source.name, ast.parse(source.read_text(encoding="utf-8"))


def test_no_module_derives_a_defeater_vocabulary_digest() -> None:
    """``_sha("defeater-vocab")`` must not come back into ANY module of this package.

    An AST walk rather than a substring search, and for the reason
    ``test_credentials.py::test_no_module_derives_a_credential_id`` gives: three modules
    here quote the old expression in prose in order to explain why it went, and a grep
    would either flag the explanation or be loosened until it flagged nothing. The walk
    asks the only question that matters — is there a CALL to ``_sha`` whose first argument
    is the string ``"defeater-vocab"`` — and it is indifferent to comments.

    Widened past the two known sites on purpose. Scoping the credential ratchet to
    ``gate_run.py`` is exactly how that defect survived its own fix in ``transitions.py``:
    a ratchet narrower than the class it guards certifies the instance and licenses the
    twin.
    """
    derived: dict[str, list[int]] = {}
    for name, tree in _package_trees():
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_sha"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "defeater-vocab"
        ]
        if hits:
            derived[name] = hits

    assert derived == {}, (
        f"{len(derived)} module(s) derive a defeater vocabulary digest: {derived}. "
        f"defeater_vocab_sha256 digests the option set a signer was SHOWN and "
        f"{DEFEATER_VOCABULARY_SOURCE} owns it; "
        "mainline_demo_api.defeaters.resolve_defeater_vocabulary reads it. A constant "
        "pins nothing, and the deployed Cloud recorded exactly that on its one signed "
        "disposition."
    )


def test_no_module_hashes_the_literal_the_old_constant_was_built_from() -> None:
    """The bytes ``b"defeater-vocab"`` appear in no expression this package evaluates.

    The walk above catches the exact call that shipped. This one catches the same value
    arriving under another name — ``hashlib.sha256(b"defeater-vocab")``, a module constant,
    a differently-spelled helper — by asking whether the string is a CONSTANT anywhere in
    the package's syntax tree at all. Docstrings are constants too, so they are excluded by
    node position rather than by pattern: every module's, class's and function's docstring
    is removed from the tree before the walk, which is what lets the prose explaining this
    defect stay in the files that carry it.
    """
    literals: dict[str, list[int]] = {}
    for name, tree in _package_trees():
        hits = [
            node.lineno
            for node in ast.walk(_without_docstrings(tree))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str | bytes)
            and node.value in ("defeater-vocab", b"defeater-vocab")
        ]
        if hits:
            literals[name] = hits

    assert literals == {}, (
        f"the literal 'defeater-vocab' is evaluated by {sorted(literals)}. It is the string "
        "whose SHA-256 the demo used to record as the digest of a vocabulary; nothing in "
        "this package has a legitimate reason to hash it."
    )


def _without_docstrings(tree: ast.Module) -> ast.Module:
    """Return *tree* with every docstring removed, leaving executable expressions alone."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.fix_missing_locations(tree)


def test_both_sign_paths_resolve_the_vocabulary_they_pin() -> None:
    """``gate_run`` and ``transitions`` each call the resolver, and neither is exempt.

    The credential ratchet watched one file while the identical defect sat twenty lines
    into a second one. Both signing paths are named here for that reason: the endpoint a
    judge reaches by signing directly and the beat the demo button plays are the same
    write, and a guard on one of them is a guard on half a class.
    """
    calls = {
        name: [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "resolve_defeater_vocabulary"
        ]
        for name, tree in _package_trees()
    }
    assert len(calls.get("gate_run.py", [])) == 1, (
        f"gate_run.py must resolve the defeater vocabulary exactly once; found {calls}"
    )
    assert len(calls.get("transitions.py", [])) == 1, (
        f"transitions.py must resolve the defeater vocabulary exactly once; found {calls}"
    )


def test_gate_run_resolves_the_vocabulary_before_the_beats_transaction_opens() -> None:
    """Resolution precedes ``SET TRANSACTION ISOLATION LEVEL SERIALIZABLE``.

    Order is the requirement. There is no foreign key here, so an absent vocabulary raises
    NOTHING inside the transaction: beat 4 would sign, admit and report ``PROVEN`` over a
    digest of nothing. Resolving first makes it a precondition that fails while there is
    still nothing to roll back, which is the shape ``test_credentials.py`` asserts for the
    credential ids and the shape the credential incident's repair established.
    """
    source = (PACKAGE_SOURCE / "gate_run.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "gate_run"
    )
    resolved_at = min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_defeater_vocabulary"
    )
    opened_at = min(
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("SET TRANSACTION ISOLATION LEVEL")
    )
    assert resolved_at < opened_at, (
        f"gate_run resolves the defeater vocabulary at line {resolved_at}, after the beats' "
        f"transaction opens at line {opened_at}. Nothing in the database refuses an absent "
        "vocabulary, so the only place the condition can be caught is before the signature."
    )


def test_the_resolver_reads_the_table_its_refusals_name() -> None:
    """The statement's table and the name every refusal prints are the same table.

    ``_DEFEATER_SQL`` spells the table out — an f-string over a constant is a real ``S608``
    shape and a statement assembled from variables is one a reader cannot check by reading.
    That leaves two literals in one module, so their agreement is asserted here rather than
    trusted.
    """
    from mainline_demo_api import defeaters

    assert DEFEATER_VOCABULARY_SOURCE in defeaters._DEFEATER_SQL
    assert "ORDER BY defeater_code" in defeaters._DEFEATER_SQL
    assert "LIMIT" not in defeaters._DEFEATER_SQL


def test_the_demo_names_the_code_the_captures_carry() -> None:
    """``gate_run.DEMO_DEFEATER_CODE`` is the code the deployed exhibits actually record.

    The literal above was copied from ``GET-f116fc2724f1b968.json``'s
    ``signed.defeater_code`` and from the captured Cloud SQL exhibit, not from the module —
    so this comparison is one the module can lose.
    """
    from mainline_demo_api import gate_run as gate_run_mod

    assert gate_run_mod.DEMO_DEFEATER_CODE == DEMO_DEFEATER_CODE


def test_the_captured_cloud_frame_still_shows_the_defect_this_module_closed() -> None:
    """The measured premise: the deployment recorded the constant over an empty vocabulary.

    Needs no cluster and asserts nothing about the code. It pins the FACT the change was
    made from, so that a future reader can see the evidence rather than the claim — and so
    that a capture regenerated after the fix does not quietly remove the only record of
    what was wrong.
    """
    import base64
    import json

    frame = json.loads(
        (
            REPO_ROOT
            / "verticals/mainline/apps/console/fixtures/bundles/demo-cloud/frames"
            / "GET-f116fc2724f1b968.json"
        ).read_text(encoding="utf-8")
    )
    body = json.loads(base64.b64decode(frame["response"]["body_b64"]).decode("utf-8"))
    data = body["data"]
    assert data["defeater_options"] == []
    assert data["signed"]["defeater_code"] == DEMO_DEFEATER_CODE
    assert data["signed"]["defeater_vocab_sha256"] == CONSTANT_THAT_PINNED_NOTHING.hex()
    assert hashlib.sha256(b"defeater-vocab").digest() == CONSTANT_THAT_PINNED_NOTHING


# ── The local retry, and its agreement with the specification's implementation ───────


class _Ladder:
    """A sleep that records what it was asked to spend instead of spending it."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, delay_s: float) -> None:
        self.delays.append(delay_s)


def _always_raises(sqlstate: str) -> Any:
    """An operation that fails with *sqlstate* every time it is called."""

    def operation() -> Any:
        raise _error(sqlstate)

    return operation


def _error(sqlstate: str) -> psycopg.Error:
    """A driver exception carrying *sqlstate* and a message with a recoverable exhibit.

    ``psycopg.errors.lookup`` returns the driver's own class for the code, so the taxonomy
    is exercised against the exception type a real refusal arrives as rather than against
    a stub that merely has the attribute.
    """
    return psycopg.errors.lookup(sqlstate)(
        f"MAINLINE: merge refused by mainline.fn_permit_merge_gate — synthetic {sqlstate}"
    )


#: Every code either loop has an opinion about, plus one that neither models.
_TAXONOMY: Final = ("40001", "23514", "23503", "23505", "P0001", "42501", "22P02")


def test_the_local_retry_and_trappoint_core_agree_on_the_taxonomy() -> None:
    """Both loops classify every SQLSTATE the same way, asserted by RUNNING both.

    ``trappoint_core.retry`` is the specification's implementation and this package may not
    import it — ``pyproject.toml`` pins the deployment to psycopg and nothing else, and
    ``test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported`` enforces that by
    importing every shipped module in a fresh interpreter. So the two are held together by
    this test instead of by an import, and it is a behavioural comparison rather than a
    comparison of constants: each loop is driven over the same synthetic errors and what it
    DID is recorded.

    The one intended difference is stated rather than hidden. ``trappoint_core`` converts a
    decided outcome into ``GateRefused``/``AuthorisationDenied``/``UnmodelledRefusal``
    because it has no caller downstream; the local loop re-raises the driver's exception
    unchanged, because ``mainline_demo_api.refusal.diagnose`` is already this package's one
    diagnosis and a second one could disagree with it. What must not differ is WHICH codes
    are retried, and that is what is compared.
    """
    from mainline_demo_api import retry as local

    from trappoint_core import errors as core_errors
    from trappoint_core import retry as core

    budget = 3
    for sqlstate in _TAXONOMY:
        expected = local.classify_for_retry(sqlstate)

        # trappoint_core: the fine-grained class it raises IS its classification, so the
        # word is recovered from the exception rather than from anything this file decides.
        core_spy = core.RecordingObserver()
        core_outcome = "succeeded"
        try:
            core.run_gate(
                _always_raises(sqlstate),
                policy=core.RetryPolicy(max_attempts=budget, base_delay_s=0.0, cap_delay_s=0.0),
                observer=core_spy,
                sleep=lambda _s: None,
                rng=random.Random(7),
            )
        except core_errors.GateRefused:
            core_outcome = "refused"
        except core_errors.AuthorisationDenied:
            core_outcome = "denied"
        except core_errors.UnmodelledRefusal:
            core_outcome = "unmodelled"
        except core_errors.RetryBudgetExhausted:
            core_outcome = "retry"

        # The local loop re-raises the driver's exception for every decided outcome, so its
        # word cannot be read off an exception type. It is read off BEHAVIOUR instead —
        # was the code retried, and how many attempts did it cost — which is the property
        # the two must actually share and the only one this package's callers can observe.
        local_spy = local.RecordingObserver()
        local_raised: BaseException | None = None
        try:
            local.run_transaction(
                _always_raises(sqlstate),
                policy=local.RetryPolicy(max_attempts=budget, base_delay_s=0.0, cap_delay_s=0.0),
                observer=local_spy,
                sleep=lambda _s: None,
                rng=random.Random(7),
            )
        except BaseException as exc:  # noqa: BLE001 - the raised type is the measurement
            local_raised = exc
        local_retried = bool(local_spy.retries)

        assert core_outcome == expected, (
            f"trappoint_core.retry treated {sqlstate} as {core_outcome!r} and "
            f"mainline_demo_api.retry.classify_for_retry says {expected!r}"
        )
        assert local_retried == (expected == "retry"), (
            f"{sqlstate}: classify_for_retry says {expected!r} and the local loop "
            f"{'retried' if local_retried else 'did not retry'} it"
        )
        assert local_retried == bool(core_spy.retries), (
            f"{sqlstate}: trappoint_core "
            f"{'retried' if core_spy.retries else 'did not retry'} it and the local loop "
            f"{'did' if local_retried else 'did not'}"
        )
        assert local_spy.attempts == core_spy.attempts, (
            f"{sqlstate}: trappoint_core made attempts {core_spy.attempts} and the local "
            f"loop made {local_spy.attempts}"
        )

        if expected == "retry":
            assert isinstance(local_raised, local.RetryBudgetExhausted)
            assert local_spy.attempts == list(range(budget))
        else:
            # Attempted exactly once, ever — and re-raised UNCHANGED, so this package's one
            # diagnosis (`refusal.diagnose`) still sees the driver's own error object.
            assert isinstance(local_raised, psycopg.Error)
            assert local_raised.sqlstate == sqlstate
            assert local_spy.attempts == [0]
            assert local_spy.decisions == [(0, sqlstate)]


def test_a_refusal_is_attempted_exactly_once_in_both_loops() -> None:
    """``spec/errors.md`` §4, asserted directly rather than inferred from a passing test.

    Not once per budget; once. The refusal ledger records decisions the gate made, and a
    client that retries a ``23514`` writes five identical refusals for one attempted
    history — at which point the count of refusals stops being a count of anything.
    """
    from mainline_demo_api import retry as local

    from trappoint_core import errors as core_errors
    from trappoint_core import retry as core

    assert local.REFUSAL_SQLSTATES == core_errors.REFUSAL_SQLSTATES, (
        "the two modules disagree about which codes MEAN the gate decided. "
        "mainline_demo_api.retry imports the set from mainline_demo_api.refusal so this "
        "package has one taxonomy; trappoint_core.errors is spec/errors.md's other "
        "executable form, and a divergence here is a divergence from the specification."
    )

    for sqlstate in sorted(local.REFUSAL_SQLSTATES):
        local_spy = local.RecordingObserver()
        with pytest.raises(psycopg.Error):
            local.run_transaction(
                _always_raises(sqlstate),
                observer=local_spy,
                sleep=lambda _s: None,
                rng=random.Random(1),
            )
        assert local_spy.attempts == [0]
        assert local_spy.retries == []
        assert local_spy.attempts_for(sqlstate) == 1

        core_spy = core.RecordingObserver()
        with pytest.raises(core_errors.GateRefused):
            core.run_gate(
                _always_raises(sqlstate),
                observer=core_spy,
                sleep=lambda _s: None,
                rng=random.Random(1),
            )
        assert core_spy.attempts_for(sqlstate) == 1


def test_the_ladder_is_capped_exponential_with_full_jitter_and_is_never_spent() -> None:
    """Every delay lies in ``[0, min(cap, base·2ⁿ))`` and the last attempt does not sleep.

    ``sleep`` and ``rng`` are injected so the ladder can be asserted without waiting for
    it. The upper bound is checked per attempt rather than in aggregate: an implementation
    that used the cap on every attempt would produce a total inside any aggregate bound
    while having no exponential in it at all.
    """
    from mainline_demo_api.retry import RetryBudgetExhausted, RetryPolicy, run_transaction

    policy = RetryPolicy(max_attempts=5, base_delay_s=0.02, cap_delay_s=0.5)
    ladder = _Ladder()
    with pytest.raises(RetryBudgetExhausted) as raised:
        run_transaction(
            _always_raises("40001"),
            policy=policy,
            sleep=ladder,
            rng=random.Random(20260814),
            now=lambda: 0.0,
        )

    assert raised.value.attempts == 5
    assert "undecided, not refused" in str(raised.value)
    # Four sleeps for five attempts: the loop does not pay for a retry it will not make.
    assert len(ladder.delays) == policy.max_attempts - 1
    for attempt, delay in enumerate(ladder.delays):
        ceiling = min(policy.cap_delay_s, policy.base_delay_s * (2**attempt))
        assert 0.0 <= delay <= ceiling, (
            f"attempt {attempt} slept {delay}s against a ceiling of {ceiling}s"
        )
    assert sum(ladder.delays) < 0.31, (
        "the whole ladder must stay inside a gate run's latency budget; the worst case for "
        "this policy is 0.30 s of sleep"
    )


def test_the_retried_unit_is_the_whole_transaction_and_a_second_attempt_can_succeed() -> None:
    """One ``40001`` then success: the operation is re-run in full, not resumed."""
    from mainline_demo_api.retry import run_transaction

    calls: list[int] = []

    def operation() -> str:
        calls.append(len(calls))
        if len(calls) == 1:
            raise _error("40001")
        return "committed"


    assert (
        run_transaction(operation, sleep=lambda _s: None, rng=random.Random(3)) == "committed"
    )
    assert calls == [0, 1]


def test_an_undecided_payload_is_retried_and_the_last_one_is_returned() -> None:
    """``gate_run`` reports 40001 in its payload, so the predicate is how it is recognised.

    And when the budget is spent the payload comes back as it stands. An exception has
    nothing to surface; a payload already records which beats completed and which SQLSTATE
    stopped them, which is what ``spec/errors.md`` §5 wants surfaced. Replacing it with an
    exception would discard the evidence to report the same fact less precisely.
    """
    from mainline_demo_api.retry import RetryPolicy, run_transaction

    attempts: list[int] = []

    def operation() -> dict[str, Any]:
        attempts.append(len(attempts))
        return {"outcome": "retry", "attempt": len(attempts)}

    result = run_transaction(
        operation,
        undecided=lambda payload: bool(payload["outcome"] == "retry"),
        policy=RetryPolicy(max_attempts=3, base_delay_s=0.0, cap_delay_s=0.0),
        sleep=lambda _s: None,
        rng=random.Random(5),
    )

    assert attempts == [0, 1, 2]
    assert result == {"outcome": "retry", "attempt": 3}


def test_a_defect_inside_the_operation_propagates_as_itself() -> None:
    """``psycopg.Error``, never ``Exception``: a blanket catch is how a refusal goes silent."""
    from mainline_demo_api.retry import run_transaction

    def operation() -> None:
        raise KeyError("a payload builder bug, not a database verdict")

    with pytest.raises(KeyError):
        run_transaction(operation, sleep=lambda _s: None, rng=random.Random(0))


def test_a_policy_that_cannot_hold_the_property_is_refused() -> None:
    """Zero attempts would make the loop report an exhausted budget without ever running."""
    from mainline_demo_api.retry import RetryPolicy

    with pytest.raises(ValueError, match="at least 1"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="base_delay_s <= cap_delay_s"):
        RetryPolicy(base_delay_s=1.0, cap_delay_s=0.5)


def test_the_runtime_does_not_import_trappoint_core() -> None:
    """RULING R11, as a property of the source rather than of one green run.

    ``tests/test_envelope.py`` measures the import closure of the built package in a fresh
    interpreter; this asserts the narrower thing at the syntax level, where it names the
    module that would have broken the deployment and why. The tests above import
    ``trappoint_core`` freely — they are not shipped.

    ``trappoint_core`` ONLY, and that boundary is measured rather than assumed.
    ``gate_run.canonical_json`` imports ``trappoint_jcs`` inside a ``try`` with a documented
    ``ImportError`` fallback, and returns WHICH implementation ran in the response — an
    optional import that degrades in the open is a different thing from a hard dependency,
    it predates this change, and it is not this worker's to remove. What R11 forbids, and
    what this asserts, is the retry taxonomy arriving by import instead of by conformance.
    """
    offenders: dict[str, list[int]] = {}
    for name, tree in _package_trees():
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.Import)
                and any(a.name.split(".")[0] == "trappoint_core" for a in node.names)
            )
            or (
                isinstance(node, ast.ImportFrom)
                and (node.module or "").split(".")[0] == "trappoint_core"
                and node.level == 0
            )
        ]
        if hits:
            offenders[name] = hits

    assert offenders == {}, (
        f"{offenders} import a trappoint workspace package. "
        "verticals/mainline/apps/demo-api/pyproject.toml pins the deployment package to "
        "psycopg and psycopg-binary and nothing else, so this import either fails at cold "
        "start or drags the workspace into the zip. mainline_demo_api.retry conforms to "
        "spec/errors.md §2.1 and trappoint_core.retry without importing either."
    )


def test_the_local_retry_names_its_specification() -> None:
    """The docstring names both authorities it conforms to, so the reader can check it."""
    from mainline_demo_api import retry as local

    doc = local.__doc__ or ""
    assert "spec/errors.md" in doc
    assert "§2.1" in doc
    assert "trappoint_core.retry" in doc


def test_the_gate_run_endpoint_is_the_only_transition_wrapped_in_the_retry() -> None:
    """``run_transaction`` guards the run that persists nothing, and no committing path.

    A retry around ``merge_permit`` would re-send a merge on a caller's behalf, which is
    how a permit gets issued twice — the sentence ``transitions``' module docstring has
    carried since it was written. The demo gate run is the exception because it rolls
    everything back and proves it did, not because retrying is convenient there.
    """
    tree = ast.parse((PACKAGE_SOURCE / "transitions.py").read_text(encoding="utf-8"))
    enclosing = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "run_transaction"
            for inner in ast.walk(node)
        )
    }
    assert enclosing == {"_demo_gate_run"}, (
        f"run_transaction is called from {sorted(enclosing)}. Only the demo gate run may be "
        "retried: it is the one transaction in this module that persists nothing."
    )
