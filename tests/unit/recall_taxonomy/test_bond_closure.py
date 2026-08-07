# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Channel B: bonding to a file implies bonds to its series and its fonds.

The gate asks *"is this event bonded to the permit's activity node or an ancestor"* as set
membership.  A bond set that is not closed under ancestry answers that question wrongly and
produces no error, no score and no log line — so the writer's posture is all-or-nothing, and
these tests assert both halves of it: the closure it does produce, and the refusal to
produce a partial one.
"""

from __future__ import annotations

import pytest
from mainline_recall_agent.taxonomy import (
    LEVEL_FILE,
    LEVEL_FONDS,
    LEVEL_SERIES,
    ActivityNode,
    ArchivalPath,
    ArchivalPathError,
    BondClosureError,
    BondRow,
    BondWriter,
    InMemoryNodeSource,
    assert_ancestor_closure,
    bond_params,
    build_bond_rows,
    derive_scope_id,
)
from mainline_recall_agent.taxonomy.sql import INSERT_EVENT_BOND

SITE = "11111111-1111-4111-8111-111111111111"
EVENT = "44444444-4444-4444-8444-444444444444"
ROOT = "MUE-04"
VER = 3

FONDS_LABEL = "restraining people working at height"
SERIES_LABEL = "securing people against falls from elevated work"
FILE_LABEL = "anchoring fall-arrest to a rated point"


def _chain() -> tuple[ActivityNode, ActivityNode, ActivityNode]:
    def node(level: int, label: str, path: list[str], parent: str | None) -> ActivityNode:
        return ActivityNode(
            scope_id=derive_scope_id(
                site_id=SITE, taxonomy_ver=VER, level=level, label_path=path
            ),
            site_id=SITE,
            level=level,
            parent_scope=parent,
            label=label,
            activity_root=ROOT,
            taxonomy_ver=VER,
            induced_by="icmm_mue" if level == LEVEL_FONDS else "llm_induced",
            frozen=level == LEVEL_FONDS,
        )

    fonds = node(LEVEL_FONDS, FONDS_LABEL, [FONDS_LABEL], None)
    series = node(LEVEL_SERIES, SERIES_LABEL, [FONDS_LABEL, SERIES_LABEL], fonds.scope_id)
    leaf = node(
        LEVEL_FILE,
        FILE_LABEL,
        [FONDS_LABEL, SERIES_LABEL, FILE_LABEL],
        series.scope_id,
    )
    return fonds, series, leaf


def test_bonding_to_a_file_bonds_its_series_and_its_fonds() -> None:
    fonds, series, leaf = _chain()
    source = InMemoryNodeSource([fonds, series, leaf])
    emission = BondWriter(source=source).emit(
        event_id=EVENT, scope_id=leaf.scope_id, bond_basis="coded"
    )
    assert len(emission.rows) == 3
    assert set(emission.scope_ids()) == {fonds.scope_id, series.scope_id, leaf.scope_id}
    assert sorted(emission.levels()) == [LEVEL_FONDS, LEVEL_SERIES, LEVEL_FILE]
    assert {row.taxonomy_ver for row in emission.rows} == {VER}
    assert {row.bond_basis for row in emission.rows} == {"coded"}


def test_bonding_to_a_series_bonds_only_up_to_the_fonds() -> None:
    fonds, series, _ = _chain()
    source = InMemoryNodeSource([fonds, series])
    emission = BondWriter(source=source).emit(
        event_id=EVENT, scope_id=series.scope_id, bond_basis="human"
    )
    assert len(emission.rows) == 2
    assert set(emission.scope_ids()) == {fonds.scope_id, series.scope_id}


def test_bonding_to_a_fonds_bonds_exactly_one_scope() -> None:
    fonds, _, _ = _chain()
    emission = BondWriter(source=InMemoryNodeSource([fonds])).emit(
        event_id=EVENT, scope_id=fonds.scope_id, bond_basis="llm_induced"
    )
    assert len(emission.rows) == 1


def test_ancestor_bonds_inherit_the_leaf_basis_and_never_upgrade_it() -> None:
    fonds, series, leaf = _chain()
    path = ArchivalPath((fonds, series, leaf))
    rows = [
        BondRow(EVENT, fonds.scope_id, VER, "human", LEVEL_FONDS),
        BondRow(EVENT, series.scope_id, VER, "coded", LEVEL_SERIES),
        BondRow(EVENT, leaf.scope_id, VER, "coded", LEVEL_FILE),
    ]
    with pytest.raises(BondClosureError) as excinfo:
        assert_ancestor_closure(rows, path)
    assert excinfo.value.context["bases"] == ["coded", "human"]


def test_a_missing_ancestor_is_refused_rather_than_written() -> None:
    fonds, series, leaf = _chain()
    path = ArchivalPath((fonds, series, leaf))
    partial = [
        BondRow(EVENT, series.scope_id, VER, "coded", LEVEL_SERIES),
        BondRow(EVENT, leaf.scope_id, VER, "coded", LEVEL_FILE),
    ]
    with pytest.raises(BondClosureError) as excinfo:
        assert_ancestor_closure(partial, path)
    assert excinfo.value.context["missing"] == [fonds.scope_id]


def test_a_bond_outside_the_path_is_refused_too() -> None:
    fonds, series, leaf = _chain()
    path = ArchivalPath((fonds, series, leaf))
    inflated = [
        BondRow(EVENT, fonds.scope_id, VER, "coded", LEVEL_FONDS),
        BondRow(EVENT, series.scope_id, VER, "coded", LEVEL_SERIES),
        BondRow(EVENT, leaf.scope_id, VER, "coded", LEVEL_FILE),
        BondRow(EVENT, "99999999-9999-4999-8999-999999999999", VER, "coded", LEVEL_FILE),
    ]
    with pytest.raises(BondClosureError) as excinfo:
        assert_ancestor_closure(inflated, path)
    assert excinfo.value.context["unexpected"] == [
        "99999999-9999-4999-8999-999999999999"
    ]


def test_bond_rows_disagreeing_about_taxonomy_version_are_refused() -> None:
    fonds, series, leaf = _chain()
    path = ArchivalPath((fonds, series, leaf))
    rows = [
        BondRow(EVENT, fonds.scope_id, VER + 1, "coded", LEVEL_FONDS),
        BondRow(EVENT, series.scope_id, VER, "coded", LEVEL_SERIES),
        BondRow(EVENT, leaf.scope_id, VER, "coded", LEVEL_FILE),
    ]
    with pytest.raises(BondClosureError):
        assert_ancestor_closure(rows, path)


def test_an_unknown_bond_basis_is_refused() -> None:
    fonds, series, leaf = _chain()
    with pytest.raises(BondClosureError):
        build_bond_rows(
            event_id=EVENT,
            path=ArchivalPath((fonds, series, leaf)),
            bond_basis="model_rated",
        )


def test_a_broken_ancestry_chain_emits_nothing_at_all() -> None:
    """Half a closure looks like an answer, so the writer produces none of it."""
    fonds, series, leaf = _chain()
    writer = BondWriter(source=InMemoryNodeSource([fonds, leaf]))
    with pytest.raises(ArchivalPathError) as excinfo:
        writer.emit(event_id=EVENT, scope_id=leaf.scope_id, bond_basis="coded")
    assert excinfo.value.context["missing_scope_id"] == series.scope_id


def test_bond_parameters_match_the_statement_and_omit_scope_level() -> None:
    fonds, series, leaf = _chain()
    emission = build_bond_rows(
        event_id=EVENT, path=ArchivalPath((fonds, series, leaf)), bond_basis="coded"
    )
    placeholders = INSERT_EVENT_BOND.count("%s")
    assert placeholders == 4
    for row in emission.rows:
        assert len(bond_params(row)) == placeholders
    assert "scope_level" not in INSERT_EVENT_BOND
    assert "ON CONFLICT" not in INSERT_EVENT_BOND


def test_primary_keys_are_distinct_across_the_closure() -> None:
    fonds, series, leaf = _chain()
    emission = build_bond_rows(
        event_id=EVENT, path=ArchivalPath((fonds, series, leaf)), bond_basis="coded"
    )
    assert len({row.primary_key for row in emission.rows}) == 3
