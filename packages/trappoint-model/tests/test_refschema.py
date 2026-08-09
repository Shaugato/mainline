# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The stand-ins are bounded, and the gap they fill is measured rather than asserted.

Two tests, and the second is the one that matters. A harness that supplies missing
relations can drift into a harness that supplies missing *mechanisms*, and the difference
is invisible in a diff. So the stand-in list is locked by count and by content, and the
gap it exists for is re-measured against the live tree on every run.
"""

from __future__ import annotations

import re

import pytest
from trappoint_model.refschema import SCHEMA, STANDINS, tree_files

# Every relation the stand-ins create, in the order they are created.
EXPECTED_STANDIN_RELATIONS = (
    "trappoint",  # the bootstrap SCHEMA, not a relation — `trappoint migrate bootstrap`'s job
    f"{SCHEMA}.event",
    f"{SCHEMA}.clause",
    f"{SCHEMA}.site",
    f"{SCHEMA}.ledger_intake",
    f"{SCHEMA}.event_severity_revision",
    f"{SCHEMA}_meas.recall_policy",
)


def test_standins_are_exactly_the_relations_the_tree_names_and_does_not_ship() -> None:
    """The list is locked. Growing it is a decision, not a convenience."""
    assert len(STANDINS) == len(EXPECTED_STANDIN_RELATIONS), (
        f"{len(STANDINS)} stand-ins for {len(EXPECTED_STANDIN_RELATIONS)} expected relations. "
        "A stand-in is a DEPENDENCY of a mechanism, never a mechanism: adding one is how a "
        "differential quietly starts testing its own SQL."
    )
    for sql, name in zip(STANDINS, EXPECTED_STANDIN_RELATIONS, strict=True):
        assert name in sql, f"expected a stand-in for {name}, got: {sql[:80]}"


def test_no_standin_carries_a_mechanism() -> None:
    """No CHECK, no trigger, no foreign key. A stand-in that refuses is a second gate."""
    for sql in STANDINS:
        for forbidden in ("CHECK", "REFERENCES", "TRIGGER", "UNIQUE"):
            assert forbidden not in sql.upper(), (
                f"a stand-in carries {forbidden}: {sql[:100]}. Stand-ins exist so the tree "
                "applies; a stand-in that constrains anything is a mechanism this package "
                "wrote, and the differential would be judging its own work."
            )


def test_the_reference_vertical_still_names_every_standin_relation() -> None:
    """Re-measure the gap. When the render worker ships these, this test says so.

    It is written to FAIL LOUDLY on the good news: the day
    ``packages/trappoint-sql/refvertical/sql/`` gains its own ``site`` or ``event``, this
    test fails and the stand-in must be removed. A harness that keeps shadowing a relation
    the tree now ships is a harness testing the shadow.
    """
    tree = "\n".join(path.read_text(encoding="utf-8") for path in tree_files())
    created = set(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?([a-z_0-9.]+)", tree))
    for name in EXPECTED_STANDIN_RELATIONS[1:]:
        assert name in tree, (
            f"{name} is no longer referenced by the reference vertical — the stand-in for it "
            "is dead code and must be deleted."
        )
        assert name not in created, (
            f"the reference vertical now CREATEs {name} itself. Delete its stand-in from "
            "refschema.STANDINS: two definitions of one relation is exactly the failure "
            "mode the migration reconciliation ruling exists to end."
        )


@pytest.mark.requires_cluster
def test_the_whole_tree_applies_and_the_gate_objects_exist(conn: object) -> None:
    """The session fixture already applied it; this asserts what that produced.

    Named objects rather than a file count: 109 files applied is a fact about the runner,
    and ``fn_permit_merge_gate`` existing is a fact about the gate.
    """
    wanted = {
        "permit",
        "change_request",
        "blocking_check",
        "disposition",
        "merge_record",
        "permit_event",
        "exposure_receipt",
        "exposure_line",
        "override_ledger",
        "refusal_ledger",
        "clause_blame_closure",
    }
    with conn.cursor() as cur:  # type: ignore[attr-defined]
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
            (SCHEMA,),
        )
        present = {row[0] for row in cur.fetchall()}
        cur.execute(
            "SELECT routine_name FROM information_schema.routines WHERE routine_schema = %s",
            (SCHEMA,),
        )
        routines = {row[0] for row in cur.fetchall()}
    assert wanted <= present, f"missing tables: {sorted(wanted - present)}"
    assert {"fn_permit_merge_gate", "fn_check_materialised", "merge_permit"} <= routines, (
        f"missing gate routines: {sorted({'fn_permit_merge_gate', 'merge_permit'} - routines)}"
    )
