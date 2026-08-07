# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Channel B: bonds to the node **and every ancestor**, so a fatality never decays.

ARCHITECTURE §5.4 introduces ``mainline.event_bond`` with one line of intent — *"a fatality
never decays — structurally, not as a score hack"* — and the structure is the whole
argument.  A recency decay constant that happens to be small is a tuning parameter; a
tuning parameter is something a future engineer adjusts in a sprint, in a config file,
without a migration, and a 1998 fatality quietly stops blocking a 2026 permit.  A bond is a
row.  MI16 (``bonded_fatalities_all_blocking``) quantifies over that table, the CHECK on
``mainline_meas.recall_run`` refuses a run whose two bonded counters disagree, and no
threshold, calibrator or model call appears anywhere on the path.

That reduction only works if the bond set is **closed under ancestry**.  The gate asks
*"is this event bonded to the permit's activity node or an ancestor of it"*, and it asks
it as set membership.  If an event is bonded to a file but not to that file's series and
fonds, then a permit scoped at the series does not see it — and there is no error, no
score, no log line: the event simply is not in the set.  So this module has exactly one
posture: build the full closure, verify it against the resolved path, and emit **nothing**
if it cannot be completed.  A half-closed bond set is worse than no bond set, because it
looks like an answer.

``bond_basis`` is not ``induced_by``.  ``activity_node.induced_by`` records how the *node*
came to exist (``icmm_mue`` / ``llm_induced`` / ``human``); ``event_bond.bond_basis``
records how *this event* came to be attached to it (``coded`` / ``llm_induced`` /
``human``).  An event attached by an MSHA coded accident class is ``coded`` even when the
node it lands on was induced by a model.  The ancestor bonds inherit the leaf's basis
deliberately: a bond to the fonds derived from a file-level assignment is exactly as good,
and exactly as weak, as that assignment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .errors import BondClosureError
from .models import BOND_BASES, ArchivalPath, BondRow
from .sources import ActivityNodeSource, resolve_path

__all__ = ["BondEmission", "BondWriter", "assert_ancestor_closure", "build_bond_rows"]


@dataclass(frozen=True, slots=True)
class BondEmission:
    """The closed bond set for one event, with the path it was closed over."""

    rows: tuple[BondRow, ...]
    path: ArchivalPath
    bond_basis: str

    def __len__(self) -> int:
        return len(self.rows)

    def scope_ids(self) -> tuple[str, ...]:
        return tuple(row.scope_id for row in self.rows)

    def levels(self) -> tuple[int, ...]:
        return tuple(row.scope_level for row in self.rows)


def assert_ancestor_closure(rows: Sequence[BondRow], path: ArchivalPath) -> None:
    """Refuse a bond set that does not cover every node on ``path``.

    Checked as a set comparison in *both* directions.  A missing ancestor is the silent
    failure this module exists to prevent; a bond to a scope that is not on the path is a
    different defect — an event bonded somewhere its classification does not put it —
    and it inflates channel B's blocking set with an obligation nobody can justify.
    """
    expected = set(path.scope_ids())
    found = {row.scope_id for row in rows}
    if found != expected:
        raise BondClosureError(
            "bond set is not the ancestry closure of the event's archival path; channel B "
            "answers 'is this fatality bonded here' as set membership, and an incomplete "
            "set answers it wrongly with no error anywhere",
            missing=sorted(expected - found),
            unexpected=sorted(found - expected),
            depth=path.depth,
        )
    versions = {row.taxonomy_ver for row in rows}
    if versions != {path.taxonomy_ver}:
        raise BondClosureError(
            "bond rows disagree with the path about taxonomy_ver; a re-induction changes "
            "what the gate would have recalled and every bond records which taxonomy it "
            "was written under",
            path_version=path.taxonomy_ver,
            bond_versions=sorted(versions),
        )
    bases = {row.bond_basis for row in rows}
    if len(bases) != 1:
        raise BondClosureError(
            "ancestor bonds must carry the same basis as the leaf assignment; a fonds bond "
            "that claims a stronger basis than the file bond it was derived from is a "
            "provenance upgrade nobody performed",
            bases=sorted(bases),
        )


def build_bond_rows(
    *, event_id: str, path: ArchivalPath, bond_basis: str
) -> BondEmission:
    """Bond ``event_id`` to every node on ``path`` — leaf and all ancestors."""
    if not event_id:
        raise BondClosureError("an event id is required to write a bond")
    if bond_basis not in BOND_BASES:
        raise BondClosureError(
            "event_bond.bond_basis outside the declared vocabulary",
            bond_basis=bond_basis,
            allowed=sorted(BOND_BASES),
        )
    rows = tuple(
        BondRow(
            event_id=event_id,
            scope_id=node.scope_id,
            taxonomy_ver=node.taxonomy_ver,
            bond_basis=bond_basis,
            scope_level=node.level,
        )
        for node in path
    )
    assert_ancestor_closure(rows, path)
    return BondEmission(rows=rows, path=path, bond_basis=bond_basis)


class BondWriter:
    """Resolve a scope's ancestry from the node table, then bond the whole chain."""

    def __init__(self, *, source: ActivityNodeSource) -> None:
        self._source = source

    def emit(self, *, event_id: str, scope_id: str, bond_basis: str) -> BondEmission:
        path = resolve_path(self._source, scope_id)
        return build_bond_rows(event_id=event_id, path=path, bond_basis=bond_basis)
