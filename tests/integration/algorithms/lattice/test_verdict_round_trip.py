# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The join nothing else makes: a verdict the lattice computed, written past the guard.

``test_witness_or_refuse`` proves the trigger refuses a hand-written INSERT.  The
unit suite proves :func:`mainline_domain.lattice.decide` returns the right verdict
with the right minimal witness set.  Neither proves the thing a projector
actually does, which is **take the output of the first and write it through the
second**, and that seam is where a real deployment breaks:

* a witness whose ``rule_id`` the Python side emits and the ``rule_id_closed``
  ``CHECK`` does not admit is ``23514`` on every weakening, which the guard then
  reports as *no witnesses at all* — a lattice that found nothing, in the console;
* a witness whose ``note`` or ``field`` is empty is ``23514`` for the same reason
  and reads the same way;
* a ``DeltaVerdict`` whose ``minimal`` set is empty would trip the second P0001,
  which is supposed to be unreachable for a verdict this package produced.

Each of those is invisible from either side alone.  This file drives real CATs
through :func:`~mainline_domain.lattice.decide.explain`, writes what comes out,
and checks that the row landed — with the witness rows a person deciding whether
to sign a permit would be shown.

WHAT A PROJECTOR IS EXPECTED TO WRITE
--------------------------------------
Both sets, flagged.  ``LatticeDecision.minimal`` is the minimal unsatisfiable
subset — *why the answer is no* — and gets ``minimal = true``.
``LatticeDecision.findings`` is everything the nine rules said, and the rest of it
gets ``minimal = false``: I14 asks for the irreducible reason set *and*, where
computable, the nearest admissible alternative, and storing only the singleton
would make the refusal truthful and useless.  :func:`witness_rows` below is the
reference implementation of that mapping and is deliberately about ten lines
long.
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal
from typing import Final

import pytest
from _lattice_sql_support import (
    Commit,
    insert_clause,
    insert_clause_version,
    insert_commit,
    insert_doc,
    rows,
)
from mainline_domain.cat.schema import EMPTY_CAT
from mainline_domain.contracts import CAT, ControlDelta, DeltaWitness
from mainline_domain.lattice import explain
from mainline_domain.lattice.decide import LatticeDecision
from mainline_domain.quantity.algebra import quantity
from mainline_domain.registry.model import (
    EntryStatus,
    RegistryEntry,
    SafeDirection,
    SafeDirectionRegistry,
)

psycopg = pytest.importorskip(
    "psycopg", reason="psycopg 3 is required to talk to CockroachDB; `uv sync --extra db`"
)

pytestmark = pytest.mark.schema

SITE_SEED: Final[uuid.UUID] = uuid.UUID("00000000-0000-0000-0000-000000000000")
AS_OF: Final[bytes] = hashlib.sha256(b"mainline-deltalattice/round-trip/as-of").digest()


# --------------------------------------------------------------------------- #
# Building the two tuples and the registry, without importing the unit suite   #
# --------------------------------------------------------------------------- #
#
# `tests/unit/domain/lattice/_lattice_fixtures.py` builds the same objects, and
# importing it from here would work only when both directories happen to be
# collected in one run. A suite whose fixtures appear and vanish depending on
# what else was selected is a suite that is red for reasons nobody can reproduce.


def cat(**overrides: object) -> CAT:
    fields = {name: getattr(EMPTY_CAT, name) for name in CAT.__dataclass_fields__}
    fields.update(overrides)
    return CAT(**fields)  # type: ignore[arg-type]


def registry(*entries: tuple[str, SafeDirection, str]) -> SafeDirectionRegistry:
    """A DIRECTRIX registry holding exactly the parameters named, ratified and signed."""
    built: dict[str, RegistryEntry] = {}
    for parameter, direction, unit in entries:
        probe = quantity(Decimal("1"), unit)
        built[parameter] = RegistryEntry(
            parameter=parameter,
            dimension_label=probe.dimension,
            dimensionality=probe.dimension,
            direction=direction,
            status=EntryStatus.RATIFIED,
            rationale=f"round-trip fixture direction for {parameter}",
            clause_uuid=uuid.uuid5(SITE_SEED, f"clause/{parameter}"),
            ratification_commit=hashlib.sha256(f"ratify/{parameter}".encode()).digest(),
            ratified_by_sub="sub-fixture-principal-engineer",
            ratification_signed=True,
            gen=1,
            canon_sha256=hashlib.sha256(f"canon/{parameter}".encode()).digest(),
        )
    return SafeDirectionRegistry(
        site_id=SITE_SEED,
        as_of_commit=AS_OF,
        doc_code="REG-SAFE-DIRECTION",
        entries=built,
        abstentions={},
        encoding_version=1,
        document_present=True,
    )


# --------------------------------------------------------------------------- #
# The mapping a projector performs.  Reference implementation, ~10 lines.      #
# --------------------------------------------------------------------------- #


def witness_rows(decision: LatticeDecision) -> list[tuple[int, DeltaWitness, bool]]:
    """``(witness_ord, witness, minimal)`` for every finding, MUS members first.

    Ordinals are assigned over the **whole** finding set in rule order R1 → R9,
    with the minimal members flagged — not over the minimal set alone.  Two runs
    of the same comparison must produce the same ordinals, because a refusal that
    renumbers its own reasons between renderings is a refusal an operator learns
    to distrust.
    """
    minimal = {id(finding) for finding in decision.minimal}
    return [
        (ordinal, finding.witness, id(finding) in minimal)
        for ordinal, finding in enumerate(decision.findings)
    ]


def write_verdict(
    cur, *, clause_uuid: uuid.UUID, commit: Commit, decision: LatticeDecision
) -> None:
    """The ordering contract, as a projector would implement it: witnesses, then the row."""
    for ordinal, witness, minimal in witness_rows(decision):
        cur.execute(
            """
            INSERT INTO mainline.delta_witness
              (clause_uuid, commit_id, witness_ord, rule_id, field, from_repr, to_repr,
               note, minimal)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                clause_uuid,
                commit.commit_id,
                ordinal,
                witness.rule_id,
                witness.field,
                witness.from_repr,
                witness.to_repr,
                witness.note,
                minimal,
            ),
        )


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


class Subject:
    def __init__(self, schema, site_id: uuid.UUID) -> None:
        self.schema = schema
        self.site_id = site_id
        tag = uuid.uuid4().hex[:8]
        with schema.connect() as conn:
            self.birth = insert_commit(conn, site_id=site_id, label=f"rt/{tag}/c0", gen=0)
            self.edit = insert_commit(conn, site_id=site_id, label=f"rt/{tag}/c1", gen=1)
            self.doc_id = insert_doc(conn, site_id=site_id, doc_code=f"PROC-RT-{tag}")
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

    def store(self, decision: LatticeDecision) -> None:
        """Write the verdict the way §5.11's ordering contract requires."""
        with self.schema.connect(autocommit=False) as tx:
            with tx.cursor() as cur:
                write_verdict(
                    cur, clause_uuid=self.clause_uuid, commit=self.edit, decision=decision
                )
                insert_clause_version(
                    cur,
                    site_id=self.site_id,
                    doc_id=self.doc_id,
                    clause_uuid=self.clause_uuid,
                    commit=self.edit,
                    control_delta=decision.verdict.delta.value,
                    delta_basis=decision.verdict.basis,
                    parent_version=self.birth.commit_id,
                )
            tx.commit()


@pytest.fixture
def subject(guarded_schema, site_id: uuid.UUID) -> Subject:
    return Subject(guarded_schema, site_id)


# --------------------------------------------------------------------------- #
# The round trip                                                               #
# --------------------------------------------------------------------------- #


def test_the_canonical_weakening_survives_the_whole_path(subject: Subject) -> None:
    """``MUST`` → ``SHOULD``, everything else identical: one witness, ``R1_DEONTIC``, stored.

    This is the worker's first red test (brief case (a)) taken all the way to the
    cluster.  The unit suite proves the verdict; this proves the verdict is
    *storable*, which is a different claim and the one a demo depends on.
    """
    decision = explain(
        cat(deontic="MUST", action="verify_isolation"),
        cat(deontic="SHOULD", action="verify_isolation"),
        registry(),
        AS_OF,
    )
    assert decision.verdict.delta is ControlDelta.WEAKEN
    assert [w.rule_id for w in decision.verdict.witnesses] == ["R1_DEONTIC"]

    subject.store(decision)

    with subject.schema.connect() as conn:
        stored = rows(
            conn,
            "SELECT control_delta, delta_basis FROM mainline.clause_version "
            "WHERE clause_uuid = %s AND commit_id = %s",
            (subject.clause_uuid, subject.edit.commit_id),
        )
        witnesses = rows(
            conn,
            "SELECT witness_ord, rule_id, field, from_repr, to_repr, minimal "
            "FROM mainline.delta_witness WHERE clause_uuid = %s AND commit_id = %s "
            "ORDER BY witness_ord",
            (subject.clause_uuid, subject.edit.commit_id),
        )

    assert stored == [("weaken", "lattice")]
    assert witnesses == [(0, "R1_DEONTIC", "deontic", "MUST", "SHOULD", True)]


def test_a_four_rule_weakening_stores_one_reason_and_the_whole_repair_list(
    subject: Subject,
) -> None:
    """I14's two sets, in two columns, on one commit.

    Four rules each independently force ``weaken``.  The irreducible reason is any
    one of them — the minimiser cites the lowest-numbered — and the repair list is
    all four, because undoing one changes nothing.  A refusal that showed only the
    singleton would be truthful and useless; one that showed four undifferentiated
    rows would be a dump.  ``minimal`` is the column that keeps them apart.
    """
    decision = explain(
        cat(
            deontic="MUST",
            action="verify_isolation",
            exceptions=(),
            verification=("second_person_check", "hold_point"),
            coverage_quantifier="all",
        ),
        cat(
            deontic="SHOULD",
            action="verify_isolation",
            exceptions=("where reasonably practicable",),
            verification=("second_person_check",),
            coverage_quantifier="selected",
        ),
        registry(),
        AS_OF,
    )
    assert decision.verdict.delta is ControlDelta.WEAKEN
    assert len(decision.minimal) == 1, "the join makes the MUS a singleton; see witness.py"
    assert len(decision.repair) >= 4, [f.rule_id for f in decision.repair]

    subject.store(decision)

    with subject.schema.connect() as conn:
        stored = rows(
            conn,
            "SELECT rule_id, minimal FROM mainline.delta_witness "
            "WHERE clause_uuid = %s AND commit_id = %s ORDER BY witness_ord",
            (subject.clause_uuid, subject.edit.commit_id),
        )

    assert [rule for rule, _ in stored] == [f.rule_id for f in decision.findings]
    assert sum(1 for _, minimal in stored if minimal) == 1
    assert stored[0] == ("R1_DEONTIC", True), (
        "the minimal member is not the first row; a refusal whose irreducible reason is "
        "buried under its repair list reads as a dump"
    )


def test_a_setpoint_weakening_carries_the_registry_s_direction_into_the_witness(
    subject: Subject,
) -> None:
    """R2 through the registry, stored: the pressure cap was raised on a lower-is-safer parameter.

    The witness's ``from_repr``/``to_repr`` are what the refusal prints, so they
    have to survive the round trip byte-for-byte — including the reference frame,
    because ``50 psi_gauge`` and ``50 psi_absolute`` must never look identical in
    a refusal (decision D5).
    """
    decision = explain(
        cat(
            deontic="MUST",
            action="limit_pressure",
            parameter="max_operating_pressure",
            comparator="<=",
            value=quantity(Decimal("1750"), "kPa"),
        ),
        cat(
            deontic="MUST",
            action="limit_pressure",
            parameter="max_operating_pressure",
            comparator="<=",
            value=quantity(Decimal("2100"), "kPa"),
        ),
        registry(("max_operating_pressure", SafeDirection.LOWER_IS_SAFER, "kPa")),
        AS_OF,
    )
    assert decision.verdict.delta is ControlDelta.WEAKEN
    assert [w.rule_id for w in decision.verdict.witnesses] == ["R2_SETPOINT"]

    subject.store(decision)

    with subject.schema.connect() as conn:
        stored = rows(
            conn,
            "SELECT field, from_repr, to_repr FROM mainline.delta_witness "
            "WHERE clause_uuid = %s AND commit_id = %s ORDER BY witness_ord",
            (subject.clause_uuid, subject.edit.commit_id),
        )

    emitted = decision.verdict.witnesses[0]
    assert stored == [(emitted.field, emitted.from_repr, emitted.to_repr)]
    assert "1750" in stored[0][1], stored[0][1]
    assert "2100" in stored[0][2], stored[0][2]


def test_an_unratified_parameter_reaches_the_database_as_a_weakening(subject: Subject) -> None:
    """Decision D6, end to end: unknown parameter ⇒ abstain ⇒ ``weaken``, with a witness.

    Fail-closed is only a product characteristic if the block is *storable*.  An
    abstention that produced no witness would be refused by the guard and the
    adoption ratchet — ratify the parameter to un-block — would never start.
    """
    decision = explain(
        cat(
            deontic="MUST",
            action="limit_temperature",
            parameter="bearing_temperature_trip",
            comparator="<=",
            value=quantity(Decimal("85"), "degC"),
        ),
        cat(
            deontic="MUST",
            action="limit_temperature",
            parameter="bearing_temperature_trip",
            comparator="<=",
            value=quantity(Decimal("95"), "degC"),
        ),
        registry(),  # the parameter is in no registry entry at all
        AS_OF,
    )
    assert decision.verdict.delta is ControlDelta.WEAKEN
    assert decision.verdict.witnesses, "an abstention with no witness cannot be stored"

    subject.store(decision)

    with subject.schema.connect() as conn:
        assert rows(
            conn,
            "SELECT count(*) FROM mainline.clause_version WHERE commit_id = %s "
            "AND control_delta = 'weaken'",
            (subject.edit.commit_id,),
        ) == [(1,)]


def test_a_restatement_writes_no_witness_and_is_still_accepted(subject: Subject) -> None:
    """The common case.  A gate that made ordinary edits expensive is a gate that goes."""
    decision = explain(
        cat(deontic="MUST", action="verify_isolation"),
        cat(deontic="MUST", action="verify_isolation"),
        registry(),
        AS_OF,
    )
    assert decision.verdict.delta is ControlDelta.RESTATE
    assert decision.verdict.witnesses == ()

    subject.store(decision)

    with subject.schema.connect() as conn:
        assert rows(
            conn,
            "SELECT control_delta FROM mainline.clause_version WHERE commit_id = %s "
            "AND clause_uuid = %s",
            (subject.edit.commit_id, subject.clause_uuid),
        ) == [("restate",)]
        # Scoped to this clause: the schema is session-scoped, so every test in the
        # module shares the database. Sharing a database is fine; asserting over a
        # global count would make this test's result depend on its neighbours.
        assert rows(
            conn,
            "SELECT count(*) FROM mainline.delta_witness WHERE clause_uuid = %s",
            (subject.clause_uuid,),
        ) == [(0,)]


def test_a_strengthening_writes_its_findings_and_needs_none_of_them(subject: Subject) -> None:
    """Force 0, but the arithmetic is still kept.

    The guard does not ask for a witness on a strengthening, and the projector
    writes one anyway: "this edit tightened the control, here is what moved" is
    the same evidence read the other way round, and it is what makes an audit view
    over ``delta_witness`` a history rather than a complaints file.
    """
    decision = explain(
        cat(deontic="SHOULD", action="verify_isolation"),
        cat(deontic="MUST", action="verify_isolation"),
        registry(),
        AS_OF,
    )
    assert decision.verdict.delta is ControlDelta.STRENGTHEN

    subject.store(decision)

    with subject.schema.connect() as conn:
        assert rows(
            conn,
            "SELECT rule_id FROM mainline.delta_witness WHERE commit_id = %s",
            (subject.edit.commit_id,),
        ) == [("R1_DEONTIC",)]


# --------------------------------------------------------------------------- #
# The seam itself: everything the lattice can emit is storable                 #
# --------------------------------------------------------------------------- #

#: One edit per rule, chosen so the rule fires alone or nearly alone.  The point
#: is coverage of the *witness vocabulary*, not of the verdicts — those are the
#: unit suite's business.
_EDITS: Final[tuple[tuple[str, CAT, CAT, SafeDirectionRegistry], ...]] = (
    (
        "R1_DEONTIC",
        cat(deontic="MUST", action="isolate"),
        cat(deontic="MAY", action="isolate"),
        registry(),
    ),
    (
        "R2_SETPOINT",
        cat(
            action="limit_pressure",
            parameter="max_operating_pressure",
            comparator="<=",
            value=quantity(Decimal("1750"), "kPa"),
        ),
        cat(
            action="limit_pressure",
            parameter="max_operating_pressure",
            comparator="<=",
            value=quantity(Decimal("2100"), "kPa"),
        ),
        registry(("max_operating_pressure", SafeDirection.LOWER_IS_SAFER, "kPa")),
    ),
    (
        "R3_COMPARATOR",
        cat(action="limit_pressure", parameter="p", comparator="<="),
        cat(action="limit_pressure", parameter="p", comparator="<"),
        registry(),
    ),
    (
        "R4_EXCEPTION",
        cat(action="isolate", exceptions=()),
        cat(action="isolate", exceptions=("where reasonably practicable",)),
        registry(),
    ),
    (
        "R5_QUANTIFIER",
        cat(action="isolate", coverage_quantifier="all"),
        cat(action="isolate", coverage_quantifier="selected"),
        registry(),
    ),
    (
        "R6_VERIFICATION",
        cat(action="isolate", verification=("second_person_check",)),
        cat(action="isolate", verification=()),
        registry(),
    ),
    (
        "R7_FREQUENCY",
        cat(action="test_trip", frequency=quantity(Decimal("30"), "day")),
        cat(action="test_trip", frequency=quantity(Decimal("180"), "day")),
        registry(),
    ),
    (
        "R9_COVERAGE",
        cat(action="isolate", deontic="MUST"),
        None,  # type: ignore[arg-type]
        registry(),
    ),
)


@pytest.mark.parametrize(
    ("rule_id", "reference", "descendant", "reg"),
    _EDITS,
    ids=[edit[0] for edit in _EDITS],
)
def test_every_rule_s_witness_satisfies_the_tables_checks(
    guarded_schema,
    site_id: uuid.UUID,
    rule_id: str,
    reference: CAT,
    descendant: CAT | None,
    reg: SafeDirectionRegistry,
) -> None:
    """The seam, one rule at a time.

    ``rule_id_closed``, ``field_stated`` and ``note_stated`` are three ways for a
    perfectly correct verdict to be unstorable, and all three fail the same way in
    the console: the version row is refused for having no witnesses, which reads
    as a lattice that found nothing.  R8 is absent from the list because it needs
    anchor sets and is exercised by the unit suite; its witness is built by the
    same ``_finding`` constructor as the other eight.
    """
    decision = explain(reference, descendant, reg, AS_OF)
    emitted = [finding for finding in decision.findings if finding.rule_id == rule_id]
    assert emitted, f"{rule_id} produced no finding on the edit chosen for it"

    subject = Subject(guarded_schema, site_id)
    subject.store(decision)

    with guarded_schema.connect() as conn:
        stored = rows(
            conn,
            "SELECT rule_id, field, note FROM mainline.delta_witness "
            "WHERE clause_uuid = %s AND commit_id = %s ORDER BY witness_ord",
            (subject.clause_uuid, subject.edit.commit_id),
        )
    assert rule_id in {row[0] for row in stored}
    for _, field, note in stored:
        assert field, "field_stated would have refused this row"
        assert note, "note_stated would have refused this row"


def test_the_second_refusal_is_unreachable_for_a_verdict_this_package_produced(
    subject: Subject,
) -> None:
    """A lattice verdict always has a minimal member, so the "none minimal" P0001 never fires.

    That refusal exists for a *writer*, not for this package: it catches a
    projector that flagged everything ``false``.  Asserting the invariant here is
    what makes it safe to say the second message is a writer error rather than a
    state the lattice can reach.
    """
    decision = explain(
        cat(deontic="MUST", action="isolate", verification=("hold_point",)),
        cat(deontic="MAY", action="isolate", verification=()),
        registry(),
        AS_OF,
    )
    assert decision.verdict.delta is ControlDelta.WEAKEN
    assert any(minimal for _, _, minimal in witness_rows(decision)), (
        "explain() produced a weakening with no minimal witness; the guard's second "
        "P0001 would fire on a verdict this package computed"
    )
    subject.store(decision)

    with subject.schema.connect() as conn:
        assert rows(
            conn,
            "SELECT count(*) FROM mainline.delta_witness "
            "WHERE clause_uuid = %s AND commit_id = %s AND minimal",
            (subject.clause_uuid, subject.edit.commit_id),
        ) == [(1,)]
