# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Decision D8 against a real cluster: an unexplainable weakening cannot be stored.

This file is the worker's exit criterion.  Everything else in the domain is a
Python function that *computes* a verdict; this is the statement that proves the
**database** refuses to hold one it cannot check.

::

    BEGIN;
      INSERT INTO mainline.delta_witness (...);   -- FIRST
      INSERT INTO mainline.clause_version (...);  -- SECOND, and the trigger fires here
    COMMIT;

Skip the first statement and the second raises ``P0001``:

    ``MAINLINE: a lattice weakening must carry its minimal witness set``

WHY EVERY REFUSAL HERE IS PAIRED WITH AN ACCEPTANCE
---------------------------------------------------
PL-2: for a product whose deliverable is a refusal, a suite that has never been
red asserts nothing — and a suite that is red for the *wrong* reason is worse,
because it is green-looking evidence of a mechanism that is not there.  "The
INSERT was refused" is equally consistent with a ``NOT NULL``, a foreign key, a
CHECK, or a typo in this file's own SQL.

So every refusal in this module is asserted three ways at once:

1. the **same** INSERT is accepted by ``unguarded_schema`` — the identical stack
   with migration ``0145`` withheld, so the function exists and nothing calls it.
   That is the permanent red half, kept as a fixture rather than performed once
   in a commit message;
2. the SQLSTATE is ``P0001`` specifically — a ``RAISE`` from our function, not a
   constraint the schema lead happens to own;
3. the message is the exact pinned string, compared against a literal defined in
   ``_lattice_sql_support`` rather than read back out of the migration.

WHAT THIS FILE DOES NOT CLAIM
-----------------------------
The guard makes a weakening carry **an** explanation.  It cannot make the
explanation **true**: a writer who inserts a fabricated witness and then the
version row satisfies it, and ``test_a_fabricated_witness_satisfies_the_guard``
demonstrates exactly that rather than leaving it for a reviewer to find.  What
that writer cannot do is claim a ``weaken`` with no reasons at all, and what they
cannot do either is dodge the gate by declaring ``restate`` — the matcher and the
CONSERVATION OF BLAME MASS ledger (workers W8/W9) account for every blood-written
obligation across the commit independently.  D8 closes one hole and names the
others.
"""

from __future__ import annotations

import re
import uuid

import pytest
from _lattice_sql_support import (
    NO_MINIMAL_WITNESS_MESSAGE,
    WITNESSLESS_WEAKEN_MESSAGE,
    Commit,
    insert_clause,
    insert_clause_version,
    insert_commit,
    insert_doc,
    insert_witness,
    rows,
)
from mainline_domain.contracts import RULE_IDS

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync --extra db`"
)

pytestmark = pytest.mark.schema


# --------------------------------------------------------------------------- #
# A clause with a birth version, in whichever schema the caller names.         #
# --------------------------------------------------------------------------- #


class Fixture:
    """One site, one doc, one clause, one birth version, and two later commits.

    Built per test rather than per session: these tests share a database, and
    sharing a *history* would let one test's refused write change another's
    preconditions.
    """

    def __init__(self, schema, site_id: uuid.UUID) -> None:
        self.schema = schema
        self.site_id = site_id
        tag = uuid.uuid4().hex[:8]
        with schema.connect() as conn:
            self.birth = insert_commit(conn, site_id=site_id, label=f"{tag}/c0", gen=0)
            self.edit = insert_commit(conn, site_id=site_id, label=f"{tag}/c1", gen=1)
            self.second_edit = insert_commit(conn, site_id=site_id, label=f"{tag}/c2", gen=2)
            self.doc_id = insert_doc(conn, site_id=site_id, doc_code=f"PROC-{tag}")
            self.clause_uuid = insert_clause(conn, site_id=site_id, birth=self.birth)
            insert_clause_version(
                conn,
                site_id=site_id,
                doc_id=self.doc_id,
                clause_uuid=self.clause_uuid,
                commit=self.birth,
                control_delta="introduce",
                delta_basis="lattice",
            )

    def version(
        self,
        cur,
        commit: Commit,
        *,
        control_delta: str = "weaken",
        delta_basis: str = "lattice",
        delta_model: str | None = None,
        parent: bytes | None = None,
    ) -> None:
        insert_clause_version(
            cur,
            site_id=self.site_id,
            doc_id=self.doc_id,
            clause_uuid=self.clause_uuid,
            commit=commit,
            control_delta=control_delta,
            delta_basis=delta_basis,
            delta_model=delta_model,
            parent_version=self.birth.commit_id if parent is None else parent,
            canon_text=("The isolation should be verified by a second person before work begins."),
        )

    def witness(
        self,
        cur,
        commit: Commit,
        *,
        witness_ord: int = 0,
        rule_id: str = "R1_DEONTIC",
        minimal: bool = True,
    ) -> None:
        insert_witness(
            cur,
            clause_uuid=self.clause_uuid,
            commit=commit,
            witness_ord=witness_ord,
            rule_id=rule_id,
            field="deontic",
            from_repr="MUST",
            to_repr="SHOULD",
            note=(
                "the obligation became a recommendation: MUST -> SHOULD on the "
                "second-person verification of isolation"
            ),
            minimal=minimal,
        )


@pytest.fixture
def guarded(guarded_schema, site_id: uuid.UUID) -> Fixture:
    return Fixture(guarded_schema, site_id)


@pytest.fixture
def unguarded(unguarded_schema, site_id: uuid.UUID) -> Fixture:
    return Fixture(unguarded_schema, site_id)


# --------------------------------------------------------------------------- #
# THE EXIT CRITERION                                                           #
# --------------------------------------------------------------------------- #


def test_a_weaken_with_no_witness_is_refused_with_p0001_and_the_exact_message(
    guarded: Fixture,
) -> None:
    """The refusal the product turns on.

    ``control_delta='weaken'``, ``delta_basis='lattice'``, no ``delta_witness``
    row for ``(clause_uuid, commit_id)`` — the version row does not get to exist.
    """
    with (
        pytest.raises(psycopg.errors.RaiseException) as caught,
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.version(cur, guarded.edit)

    assert caught.value.sqlstate == "P0001"
    assert caught.value.diag.message_primary == WITNESSLESS_WEAKEN_MESSAGE


def test_the_same_insert_with_witnesses_first_succeeds(guarded: Fixture) -> None:
    """The ordering contract, executed: witnesses, then the version row, one transaction.

    This is the other half of the exit criterion, and it has to be the *same*
    INSERT — a guard that refused everything would pass the test above.
    """
    with guarded.schema.connect(autocommit=False) as tx:
        with tx.cursor() as cur:
            guarded.witness(cur, guarded.edit)
            guarded.version(cur, guarded.edit)
        tx.commit()

    with guarded.schema.connect() as conn:
        stored = rows(
            conn,
            "SELECT control_delta, delta_basis FROM mainline.clause_version "
            "WHERE clause_uuid = %s AND commit_id = %s",
            (guarded.clause_uuid, guarded.edit.commit_id),
        )
    assert stored == [("weaken", "lattice")]


def test_the_refused_insert_is_accepted_when_0145_is_withheld(unguarded: Fixture) -> None:
    """PL-2, kept permanently: the identical statement, on the identical stack minus the trigger.

    Without this, the refusal above is indistinguishable from a foreign key, a
    ``NOT NULL``, or a mistake in this file.  With it, the difference between the
    two schemas is exactly one migration, and that migration is the mechanism.
    """
    with unguarded.schema.connect(autocommit=False) as tx:
        with tx.cursor() as cur:
            unguarded.version(cur, unguarded.edit)
        tx.commit()

    with unguarded.schema.connect() as conn:
        stored = rows(
            conn,
            "SELECT count(*) FROM mainline.clause_version "
            "WHERE clause_uuid = %s AND commit_id = %s",
            (unguarded.clause_uuid, unguarded.edit.commit_id),
        )
        witnesses = rows(conn, "SELECT count(*) FROM mainline.delta_witness")
    assert stored == [(1,)], (
        "the unguarded schema refused the row too, so the guarded schema's P0001 does "
        "not isolate the trigger and this suite proves nothing about 0145"
    )
    assert witnesses == [(0,)], "the unguarded run wrote a witness; the comparison is not clean"

    with unguarded.schema.connect() as conn:
        installed = rows(
            conn,
            "SELECT count(*) FROM information_schema.triggers "
            "WHERE event_object_table = 'clause_version'",
        )
    assert installed == [(0,)], "0145 was applied to the unguarded schema after all"


# --------------------------------------------------------------------------- #
# The rest of the guard's decision surface                                     #
# --------------------------------------------------------------------------- #


def test_a_remove_is_refused_on_the_same_terms_as_a_weaken(guarded: Fixture) -> None:
    """``remove`` is force 3.  Deleting a control unexplained is the loudest version of this."""
    with (
        pytest.raises(psycopg.errors.RaiseException) as caught,
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.version(cur, guarded.edit, control_delta="remove")
    assert caught.value.diag.message_primary == WITNESSLESS_WEAKEN_MESSAGE


@pytest.mark.parametrize("delta", ["introduce", "strengthen", "restate"])
def test_a_force_zero_delta_needs_no_witness(guarded: Fixture, delta: str) -> None:
    """A guard that demanded an explanation for a strengthening is a guard somebody disables.

    Force 0 is the gate not reacting.  There is nothing to explain, and the
    nuisance ceiling (risk R-A7) is a real constraint on this design: a rule that
    breaches it is *rejected, not tuned*.
    """
    with guarded.schema.connect(autocommit=False) as tx:
        with tx.cursor() as cur:
            guarded.version(cur, guarded.edit, control_delta=delta)
        tx.commit()
    with guarded.schema.connect() as conn:
        stored = rows(
            conn,
            "SELECT control_delta FROM mainline.clause_version WHERE commit_id = %s "
            "AND clause_uuid = %s",
            (guarded.edit.commit_id, guarded.clause_uuid),
        )
    assert stored == [(delta,)]


def test_lattice_plus_model_is_in_scope_because_p7_says_so(guarded: Fixture) -> None:
    """A ``lattice+model`` weaken with no lattice witness rests entirely on a model.

    Principle P7 does not permit a model to decide a state transition, so raising
    a verdict's force with an oracle does not buy an exemption from explaining the
    lattice's own half.
    """
    with (
        pytest.raises(psycopg.errors.RaiseException) as caught,
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.version(
            cur,
            guarded.edit,
            delta_basis="lattice+model",
            delta_model="au.anthropic.claude-sonnet-5",
        )
    assert caught.value.diag.message_primary == WITNESSLESS_WEAKEN_MESSAGE


@pytest.mark.parametrize("basis", ["abstain_to_weaken", "human"])
def test_the_two_exemptions_are_real(guarded: Fixture, basis: str) -> None:
    """The ratchet fires when Path A could *not* decide; a human's reason is their signature.

    Demanding a lattice witness for an abstention demands an explanation that does
    not exist, and a guard that cannot be satisfied is a guard that gets dropped.
    The abstention's own arithmetic goes to the logged-silence ledger instead.
    """
    with guarded.schema.connect(autocommit=False) as tx:
        with tx.cursor() as cur:
            guarded.version(cur, guarded.edit, delta_basis=basis)
        tx.commit()
    with guarded.schema.connect() as conn:
        stored = rows(
            conn,
            "SELECT delta_basis FROM mainline.clause_version WHERE commit_id = %s "
            "AND clause_uuid = %s",
            (guarded.edit.commit_id, guarded.clause_uuid),
        )
    assert stored == [(basis,)]


def test_witnesses_present_but_none_minimal_is_a_different_refusal(guarded: Fixture) -> None:
    """I14 asks for an irreducible reason set, not a repair list.

    A weakening whose witnesses are all flagged ``minimal = false`` has supplied
    the nearest admissible alternative and no reason.  Because ``minimal``
    defaults to ``true``, only a writer that set every row false can reach this.
    """
    # Two statements inside the `raises` block, deliberately (PT012 waived below).
    # The thing under test IS a two-statement transaction: a witness written first
    # and a version row written second. Reducing it to one statement would remove
    # the precondition the guard is checking.
    with (  # noqa: PT012
        pytest.raises(psycopg.errors.RaiseException) as caught,
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.witness(cur, guarded.edit, minimal=False)
        guarded.version(cur, guarded.edit)
    assert caught.value.sqlstate == "P0001"
    assert caught.value.diag.message_primary == NO_MINIMAL_WITNESS_MESSAGE


def test_a_witness_for_a_different_commit_does_not_satisfy_the_guard(guarded: Fixture) -> None:
    """The guard matches on ``(clause_uuid, commit_id)``, both of them.

    Otherwise one honest weakening early in a branch's life would license every
    later one on the same clause — which is precisely the salami defence ORIGINDIFF
    exists to close, defeated at the storage layer instead.
    """
    with guarded.schema.connect(autocommit=False) as tx:
        with tx.cursor() as cur:
            guarded.witness(cur, guarded.edit)
            guarded.version(cur, guarded.edit)
        tx.commit()

    with (
        pytest.raises(psycopg.errors.RaiseException) as caught,
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.version(cur, guarded.second_edit, parent=guarded.edit.commit_id)
    assert caught.value.diag.message_primary == WITNESSLESS_WEAKEN_MESSAGE


def test_a_witness_for_a_different_clause_does_not_satisfy_the_guard(
    guarded: Fixture, guarded_schema
) -> None:
    """A second clause weakened in the same commit does not explain this one."""
    with guarded_schema.connect() as conn:
        other = insert_clause(conn, site_id=guarded.site_id, birth=guarded.birth)
        insert_witness(
            conn,
            clause_uuid=other,
            commit=guarded.edit,
            witness_ord=0,
            rule_id="R6_VERIFICATION",
            field="verification",
            from_repr="['second_person_check']",
            to_repr="[]",
            note="the independent check was deleted from a different clause entirely",
        )

    with (
        pytest.raises(psycopg.errors.RaiseException) as caught,
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.version(cur, guarded.edit)
    assert caught.value.diag.message_primary == WITNESSLESS_WEAKEN_MESSAGE


def test_witnesses_written_after_the_version_row_are_witnesses_the_guard_never_saw(
    guarded: Fixture,
) -> None:
    """The ordering contract is normative and this is why.

    A BEFORE INSERT trigger sees rows already written in its own transaction and
    nothing else.  There is no ordering in which a version row reaches ``COMMIT``
    having been checked against witnesses that did not yet exist — so writing them
    second does not "also work", it fails.
    """
    # Two statements, and their ORDER is the whole assertion (PT012 waived).
    with (  # noqa: PT012
        pytest.raises(psycopg.errors.RaiseException) as caught,
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.version(cur, guarded.edit)
        guarded.witness(cur, guarded.edit)
    assert caught.value.diag.message_primary == WITNESSLESS_WEAKEN_MESSAGE


def test_the_refusal_leaves_nothing_behind(guarded: Fixture) -> None:
    """MI22: the state never forms.  BEFORE, not AFTER, is what buys this."""
    with (
        pytest.raises(psycopg.errors.RaiseException),
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.version(cur, guarded.edit)
    with guarded.schema.connect() as conn:
        assert rows(
            conn,
            "SELECT count(*) FROM mainline.clause_version WHERE commit_id = %s",
            (guarded.edit.commit_id,),
        ) == [(0,)]


# --------------------------------------------------------------------------- #
# The table's own structural refusals — they survive DISABLE TRIGGER           #
# --------------------------------------------------------------------------- #


def test_an_empty_note_is_refused_by_the_table_itself(guarded: Fixture) -> None:
    """``note_stated`` is D8 one level down, and it is a CHECK rather than a trigger.

    A witness row that satisfies the guard and explains nothing is the shape the
    guard exists to refuse.  ``ALTER TABLE ... DISABLE TRIGGER`` removes the
    trigger; it does not remove this.

    MEASURED, v26.2.5: a CockroachDB ``23514`` names the **expression**, not the
    constraint — ``failed to satisfy CHECK constraint (note != '':::STRING)``.
    PostgreSQL names the constraint.  Every refusal exhibit in this domain that
    quotes a ``23514`` message must therefore quote the predicate, and any UI that
    renders one for an operator has to supply the name itself.  Asserting on the
    name here would have been green on PostgreSQL and red on the target platform.
    """
    with (
        pytest.raises(psycopg.errors.CheckViolation) as caught,
        guarded.schema.connect() as conn,
    ):
        insert_witness(
            conn,
            clause_uuid=guarded.clause_uuid,
            commit=guarded.edit,
            witness_ord=0,
            rule_id="R1_DEONTIC",
            field="deontic",
            from_repr="MUST",
            to_repr="SHOULD",
            note="",
        )
    assert caught.value.sqlstate == "23514"
    assert "note !=" in str(caught.value), str(caught.value)


def test_a_rule_id_outside_the_nine_is_refused(guarded: Fixture) -> None:
    """``rule_id_closed`` is the SQL half of the vocabulary ``contracts.RULE_IDS`` fixes.

    ``test_0049a_shape`` holds the two sets equal by parsing the migration; this
    is the cluster confirming that the ``CHECK`` it parsed is the ``CHECK`` that
    got created — the error text echoes all nine literals back, so the assertion
    is over the *installed* vocabulary and not over the file.

    (Same measured detail as ``test_an_empty_note_is_refused_by_the_table_itself``:
    v26.2.5 reports the expression, not the constraint name.)
    """
    with (
        pytest.raises(psycopg.errors.CheckViolation) as caught,
        guarded.schema.connect() as conn,
    ):
        insert_witness(
            conn,
            clause_uuid=guarded.clause_uuid,
            commit=guarded.edit,
            witness_ord=0,
            rule_id="R10_VIBES",
            field="deontic",
            from_repr="MUST",
            to_repr="SHOULD",
            note="a rule that does not exist",
        )
    installed = tuple(literal for literal in re.findall(r"'(R\d_[A-Z]+)'", str(caught.value)))
    assert installed == RULE_IDS, (
        f"the CHECK on the cluster admits {installed}, which is not "
        f"mainline_domain.contracts.RULE_IDS {RULE_IDS}"
    )


def test_two_witnesses_cannot_share_an_ordinal(guarded: Fixture) -> None:
    """``witness_ord`` is part of the primary key: the citation order is stable, not incidental."""
    with guarded.schema.connect() as conn:
        guarded.witness(conn, guarded.edit, witness_ord=0)
        with pytest.raises(psycopg.errors.UniqueViolation):
            guarded.witness(conn, guarded.edit, witness_ord=0, rule_id="R4_EXCEPTION")


def test_a_witness_must_cite_a_clause_and_a_commit_that_exist(guarded: Fixture) -> None:
    """``fk_clause`` and ``fk_commit`` — the two halves of the pairing that *can* be enforced.

    The pairing itself cannot: ``FOREIGN KEY (clause_uuid, commit_id) REFERENCES
    clause_version`` is incompatible with the ordering contract, because
    CockroachDB checks foreign keys per statement and does not implement
    ``DEFERRABLE``.  0049a's header records that as the measured platform limit it
    is.
    """
    ghost = Commit(commit_id=bytes(range(32)), gen=9)
    with pytest.raises(psycopg.errors.ForeignKeyViolation), guarded.schema.connect() as conn:
        guarded.witness(conn, ghost)
    with pytest.raises(psycopg.errors.ForeignKeyViolation), guarded.schema.connect() as conn:
        insert_witness(
            conn,
            clause_uuid=uuid.uuid4(),
            commit=guarded.edit,
            witness_ord=0,
            rule_id="R1_DEONTIC",
            field="deontic",
            from_repr="MUST",
            to_repr="SHOULD",
            note="a clause that was never minted",
        )


# --------------------------------------------------------------------------- #
# The honest limit, demonstrated rather than described                         #
# --------------------------------------------------------------------------- #


def test_a_fabricated_witness_satisfies_the_guard(guarded: Fixture) -> None:
    """Stated where somebody will read it: this makes a weakening carry AN explanation.

    It cannot make the explanation TRUE.  A writer who invents a witness row and
    then writes the version row gets past this trigger, and no trigger on this
    table could tell the difference — the truth of the witness is a fact about two
    CATs, which is another row's business (§4.1 law 1).

    What the same writer cannot do is claim a ``weaken`` with no reasons at all,
    and what they cannot do either is dodge by declaring ``restate``: the matcher
    and the CBM ledger account for every blood-written obligation across the
    commit independently, so an evaded weakening surfaces as an orphaned
    obligation — a louder gate than the one it was hiding from.
    """
    with guarded.schema.connect(autocommit=False) as tx:
        with tx.cursor() as cur:
            insert_witness(
                cur,
                clause_uuid=guarded.clause_uuid,
                commit=guarded.edit,
                witness_ord=0,
                rule_id="R7_FREQUENCY",
                field="frequency",
                from_repr="totally",
                to_repr="made up",
                note="this witness describes an edit that did not happen",
            )
            guarded.version(cur, guarded.edit)
        tx.commit()

    with guarded.schema.connect() as conn:
        assert rows(
            conn,
            "SELECT count(*) FROM mainline.clause_version WHERE commit_id = %s "
            "AND control_delta = 'weaken'",
            (guarded.edit.commit_id,),
        ) == [(1,)]


def test_the_guard_can_be_disabled_and_the_disabling_is_the_record(
    guarded: Fixture, guarded_schema
) -> None:
    """Refusal depth 1, stated honestly.

    This is a trigger and it cannot be a ``CHECK``: §4.1 law 1 forbids a ``CHECK``
    expression from seeing another row, and every witness is another row.  So
    ``DISABLE TRIGGER`` works, and the file says so rather than claiming a
    structural second layer it does not have.  Admin can remove the guard; the
    custodian patrol makes it so that admin cannot remove the *record* that they
    removed it.

    Re-enabled at the end, because the schema is session-scoped and a test that
    leaves a gate off is a test that silences its neighbours.
    """
    with guarded_schema.connect() as conn:
        conn.execute("ALTER TABLE mainline.clause_version DISABLE TRIGGER z_delta_witness_required")
        try:
            with guarded.schema.connect(autocommit=False) as tx:
                with tx.cursor() as cur:
                    guarded.version(cur, guarded.edit)
                tx.commit()
            stored = rows(
                conn,
                "SELECT count(*) FROM mainline.clause_version WHERE commit_id = %s",
                (guarded.edit.commit_id,),
            )
        finally:
            conn.execute(
                "ALTER TABLE mainline.clause_version ENABLE TRIGGER z_delta_witness_required"
            )
    assert stored == [(1,)]

    # and the guard is back, on the same connection pool, for everyone else
    with (
        pytest.raises(psycopg.errors.RaiseException),
        guarded.schema.connect(autocommit=False) as tx,
        tx.cursor() as cur,
    ):
        guarded.version(cur, guarded.second_edit, parent=guarded.edit.commit_id)
