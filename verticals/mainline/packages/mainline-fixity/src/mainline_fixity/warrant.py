# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Discordance warrants — the obligation an undetermined finding still creates.

MI21 says an ``UNDETERMINED`` fixity result never blocks, and that is right: a
permit must not be refused because a historian tag was out of service. But *never
blocks* is one step away from *never matters*, and an attacker who can make a
comparison undetermined would otherwise have found a laundering path around the
drift gate.

The answer is that an absence does not go to the drift gate at all. It opens an
**A6 discordance warrant** — "verification obligation window elapsed with no
evidence row", S27's addition and, in §5.8's words, *the class most real drift
belongs to* — and MI05 makes an open warrant blocking at merge through a different
mechanism, with a different constraint name, closed by a different human. The
finding is advisory; the obligation is not.

This package proposes exactly two of the six classes:

===  =========================================================================
A2   as-operated has drifted from as-documented
A6   verification obligation window elapsed with no evidence row — the ABSENCE
===  =========================================================================

A1 (back-dated document), A3 (training acknowledgement of a revision that did not
yet exist), A4 (impossible lineage) and A5 (materialised precursor with no
disposition inside the Max Disposition Delay) are other components' findings.
:func:`propose_warrant` refuses to construct them — not because it could not, but
because two components proposing the same warrant class is how a warrant ends up
opened twice and closed once.

**Nothing here closes a warrant.** ``agent_patroller`` holds ``INSERT`` on
``discordance_warrant`` and no ``UPDATE``, so ``closed_at``, ``closed_by`` and
``close_disposition_id`` are unreachable from this package by grant as well as by
code. The component that opens an obligation is not the component that discharges
it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .compare import Reason
from .types import WARRANT_CLASSES, WarrantClass, require_aware

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from uuid import UUID

    from .compare import FixityComparison

__all__ = [
    "PATROL_WARRANT_CLASSES",
    "WARRANT_NAMESPACE",
    "DiscordanceWarrant",
    "propose_warrant",
]

#: The only classes this component may open. Enumerated rather than assumed.
PATROL_WARRANT_CLASSES: Final[frozenset[str]] = frozenset({"A2", "A6"})

#: Namespace for the deterministic ``warrant_id``. A fixed UUID5 namespace means a
#: redelivered schedule occurrence produces the same primary key and the insert
#: collides instead of opening a second warrant for the same discordance —
#: §8.5's rule that *the real idempotency is always a database primary key*.
WARRANT_NAMESPACE: Final[uuid.UUID] = uuid.UUID("6f3f9d1e-0c2a-5b7e-9c41-2f7d5a8e13b4")

_CLASS_FOR_REASON: Final[Mapping[Reason, WarrantClass]] = {
    Reason.DRIFT: "A2",
    Reason.UNDOCUMENTED_CONTROL: "A2",
    Reason.EVIDENCE_ABSENT: "A6",
}


@dataclass(frozen=True, slots=True)
class DiscordanceWarrant:
    """One row of ``mainline.discordance_warrant``, open by construction.

    There is no ``closed_at`` field on this type. The role that writes it cannot
    close it, so a Python object that could carry a closure would be modelling a
    state this component can never produce — and someone would eventually write
    code that assumed it could.
    """

    warrant_id: UUID
    site_id: UUID
    clause_uuid: UUID | None
    warrant_class: WarrantClass
    detail: Mapping[str, Any]
    opened_at: datetime

    def __post_init__(self) -> None:
        """Refuse a class this component may not open."""
        if self.warrant_class not in WARRANT_CLASSES:
            raise ValueError(
                f"warrant_class {self.warrant_class!r} is not one of {WARRANT_CLASSES}"
            )
        if self.warrant_class not in PATROL_WARRANT_CLASSES:
            raise ValueError(
                f"the fixity patrol may open {sorted(PATROL_WARRANT_CLASSES)} and nothing "
                f"else; {self.warrant_class!r} belongs to another component. Two components "
                f"opening one warrant class is how a warrant gets opened twice and closed once"
            )
        require_aware(self.opened_at, "discordance_warrant.opened_at")


def propose_warrant(
    comparison: FixityComparison,
    *,
    run_id: UUID,
    site_id: UUID,
    clause_uuid: UUID,
    asset_tag: str | None,
    opened_at: datetime,
) -> DiscordanceWarrant | None:
    """Open the warrant a comparison implies, or return ``None``.

    ``None`` for agreement, and ``None`` for a bounded negative. The second is the
    interesting one: *"we looked and the archive cannot resolve it"* is a recorded
    limitation of the instrument, not a discordance of the record, and opening a
    warrant for it would fill a superintendent's queue with the historian's
    compression settings until they stopped reading the queue.

    The ``detail`` payload carries the comparison's own arithmetic — including the
    bounded negative's sentence when there is one — so the warrant can be
    understood without joining back to the finding.
    """
    warrant_class = _CLASS_FOR_REASON.get(comparison.reason)
    if warrant_class is None:
        return None

    detail: dict[str, Any] = {
        "reason": comparison.reason.value,
        "run_id": str(run_id),
        "asset_tag": asset_tag,
        "confidence_milli": comparison.confidence_milli,
        "registry_abstained": comparison.registry_abstained,
        "undetermined": comparison.undetermined,
        "direction": comparison.direction.value if comparison.direction else None,
        "witnesses": [
            {
                "rule_id": witness.rule_id,
                "field": witness.field,
                "from": witness.from_repr,
                "to": witness.to_repr,
                "note": witness.note,
            }
            for witness in comparison.witnesses
        ],
    }
    if comparison.bounded_negative is not None:
        detail["bounded_negative"] = comparison.bounded_negative.to_json()
        detail["bounded_negative_statement"] = comparison.bounded_negative.statement()
    if warrant_class == "A6":
        detail["note"] = (
            "no observation arrived for a bound control. The finding is advisory "
            "(MI21) and this warrant is not: an open discordance warrant blocks the "
            "merge under MI05, closed by a person rather than by a patrol."
        )

    return DiscordanceWarrant(
        warrant_id=uuid.uuid5(
            WARRANT_NAMESPACE,
            f"{run_id}|{clause_uuid}|{asset_tag or ''}|{warrant_class}",
        ),
        site_id=site_id,
        clause_uuid=clause_uuid,
        warrant_class=warrant_class,
        detail=detail,
        opened_at=require_aware(opened_at, "discordance_warrant.opened_at"),
    )
