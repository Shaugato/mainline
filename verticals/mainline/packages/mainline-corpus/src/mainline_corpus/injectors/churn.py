# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Injector 5 — author churn: thirty per cent of authors have left, consumed and not produced.

**Proves:** why you cannot simply ask someone.

Stage 1 already separates roughly 30 % of its people and sets ``person.separated_at``, including
D. Okonjo, who lowered the spine's setpoint in 2013 and left the company in July 2021.  This
module therefore *measures* rather than injects: it counts how much of the corpus's authored
causality is held by people who are no longer there to be asked, and it names the one that
matters on camera.

Re-deriving the churn here would give the corpus two numbers for one fact, and the honesty card
quotes one of them.  A generator that produced its own separation rate would also have to be
kept in step with stage 1's people every time either changed, and the failure mode of that is
silent: the numbers drift apart and both keep passing their own tests.

The measurement that matters is not the headline percentage — it is ``orphan_edges_by_departed``
and ``severe_edges_by_departed``: the blame edges whose only human witness has left.  A clause
whose origin is unrecorded and whose author is unreachable is the exact case the product exists
for, and this file is where the corpus says how many of them it contains.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..skeleton import clock
from ..skeleton.build import Skeleton

__all__ = ["CAMERA_AUTHOR_DISPLAY", "report"]

#: The one departure the film names.  Asserted here so that a change to stage 1's people is a
#: red build in this module rather than a silent hole in beat 3.
CAMERA_AUTHOR_DISPLAY: str = "D. Okonjo"
CAMERA_AUTHOR_SEPARATION_MONTH: str = "2021-07"


def report(
    skeleton: Skeleton,
    revisions: Sequence[Any],
    edges: Sequence[Any],
    orphan_clause_keys: frozenset[str],
) -> dict[str, Any]:
    """Measure the churn stage 1 produced, against the causality this stage authored."""
    people = skeleton.people
    separated = {
        person.signer_sub
        for person in people.people
        if person.separated_at is not None and person.separated_at <= clock.NOW
    }
    total_people = len(people.people)

    camera = [person for person in people.people if person.display_name == CAMERA_AUTHOR_DISPLAY]
    if not camera:
        raise RuntimeError(
            f"{CAMERA_AUTHOR_DISPLAY} is not in the corpus. The 2013 commit's author is named on "
            "camera and the beat is that she cannot be asked."
        )
    if not any(
        person.separated_at is not None
        and clock.iso(person.separated_at).startswith(CAMERA_AUTHOR_SEPARATION_MONTH)
        for person in camera
    ):
        raise RuntimeError(
            f"{CAMERA_AUTHOR_DISPLAY} has no separation in {CAMERA_AUTHOR_SEPARATION_MONTH}; "
            "beat 3 says the person who wrote the clause has left"
        )

    author_of_revision: Mapping[str, str] = {
        f"{revision.revision_key}#{revision.clause_key}": revision.author_sub
        for revision in revisions
    }

    departed_edges = 0
    severe_departed = 0
    orphan_departed = 0
    for edge in edges:
        author = author_of_revision.get(f"{edge.revision_key}#{edge.clause_key}")
        if author is None or author not in separated:
            continue
        departed_edges += 1
        if edge.severity_gate >= 4:
            severe_departed += 1
        if edge.clause_key in orphan_clause_keys:
            orphan_departed += 1

    touched_by_departed = sum(1 for revision in revisions if revision.author_sub in separated)

    return {
        "camera_author": CAMERA_AUTHOR_DISPLAY,
        "camera_author_separation_month": CAMERA_AUTHOR_SEPARATION_MONTH,
        "clause_revisions_by_departed": touched_by_departed,
        "clause_revisions_total": len(revisions),
        "consumed_from": "stage 1 person.separated_at; this module measures and never re-derives",
        "edges_by_departed": departed_edges,
        "edges_total": len(edges),
        "orphan_edges_by_departed": orphan_departed,
        "separated_fraction": round(len(separated) / total_people, 4) if total_people else 0.0,
        "separated_people": len(separated),
        "severe_edges_by_departed": severe_departed,
        "total_people": total_people,
    }
