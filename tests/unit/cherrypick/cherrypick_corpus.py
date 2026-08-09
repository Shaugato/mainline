# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A lesson learned at one plant, offered to two others.

The lesson is real in shape: after a fatality at the origin site, the confined-space
procedure was tightened to require a second isolation point and a countersignature.
That is a ``strengthen``, so it may travel. One receiving site has the hazard and no
such control; the other decommissioned the vessel class years ago and answers with a
falsifiable ``mechanism_absent``.

Every value is a fixed literal: no ``now()``, no ``uuid4()``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from mainline_cherrypick import (
    SCORER_VERSION,
    ClauseDelta,
    Declination,
    Lesson,
    MergeConflict,
    Propagation,
    PropState,
    digest_lines,
    patch_digest,
)
from mainline_domain.contracts import ControlDelta

ORIGIN_SITE = uuid.UUID("11111111-1111-1111-1111-111111111111")
SITE_APPLIES = uuid.UUID("22222222-2222-2222-2222-222222222222")
SITE_NO_MECHANISM = uuid.UUID("33333333-3333-3333-3333-333333333333")

LESSON_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
ANCHOR_EVENT = uuid.UUID("55555555-5555-5555-5555-555555555555")
CLAUSE_ISOLATION = uuid.UUID("66666666-6666-6666-6666-666666666666")
CONFLICT_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
LOCAL_CLAUSE = uuid.UUID("88888888-8888-8888-8888-888888888888")
PREDICATE_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")

ORIGIN_COMMIT = bytes.fromhex("a1" * 32)
MERGE_BASE = bytes.fromhex("b2" * 32)

PROPOSED_AT = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
OPENED_AT = datetime(2026, 7, 1, 9, 5, tzinfo=UTC)
WAIVER_EXPIRY = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)

#: The delta set, keyed on `cat_key` so it is recognisable at a plant whose document
#: numbers the same obligation differently.
DELTA_SET = (
    ClauseDelta(
        before="cat1:9f2c1a4d",
        after="cat1:0b73e51a",
        delta=ControlDelta.STRENGTHEN,
    ),
    ClauseDelta(before=None, after="cat1:7d90c4e2", delta=ControlDelta.INTRODUCE),
)

BASE_TEXT = (
    "7.3 Isolation",
    "Isolation shall be applied at the upstream isolation point.",
    "A gas test shall be recorded before entry.",
)
FLEET_TEXT = (
    "7.3 Isolation",
    "Isolation shall be applied at every upstream isolation point and locked.",
    "A gas test shall be recorded before entry.",
    "The isolation shall be countersigned by the permit issuer.",
)
SITE_TEXT = (
    "7.3 Isolation",
    "Isolation shall be applied at the upstream isolation point and tagged.",
    "A gas test shall be recorded before entry.",
)

APPLIES_FACTS = frozenset(
    {
        "hazard_energy:flammable_atmosphere",
        "hazard_energy:stored_pressure",
        "control_class:energy_isolation",
        "asset:TK-2201",
    }
)
NO_MECHANISM_FACTS = frozenset({"hazard_energy:stored_pressure", "control_class:permit_control"})
LESSON_FACTS = frozenset(
    {
        "hazard_energy:flammable_atmosphere",
        "control_class:energy_isolation",
        "control_class:isolation_verification",
        "asset:TK-2201",
    }
)

#: Applies only where a flammable atmosphere is present and the vessel class has
#: not been decommissioned. Written by the ORIGINATING site, in data.
ENVELOPE = {
    "all": [
        {"has": "hazard_energy:flammable_atmosphere"},
        {"absent": "decommissioned:thickener_underflow"},
    ]
}


def lesson(**overrides) -> Lesson:
    """The fleet-standard lesson, eligible to travel."""
    import dataclasses

    base = Lesson(
        lesson_id=LESSON_ID,
        origin_site=ORIGIN_SITE,
        origin_commit=ORIGIN_COMMIT,
        anchor_event=ANCHOR_EVENT,
        max_severity=5,
        control_delta=ControlDelta.STRENGTHEN,
        patch_digest=patch_digest(DELTA_SET),
        merge_base=MERGE_BASE,
        envelope=ENVELOPE,
    )
    return dataclasses.replace(base, **overrides)


def propagation(**overrides) -> Propagation:
    """A proposal to the site the lesson applies at."""
    import dataclasses

    base = Propagation(
        lesson_id=LESSON_ID,
        site_id=SITE_APPLIES,
        state=PropState.PROPOSED,
        score_milli=850,
        model_version=SCORER_VERSION,
        proposed_at=PROPOSED_AT,
        due_by=datetime(2026, 7, 8, 9, 0, tzinfo=UTC),
    )
    return dataclasses.replace(base, **overrides)


def conflict(**overrides) -> MergeConflict:
    """The three-way merge that did not resolve."""
    import dataclasses

    base = MergeConflict(
        conflict_id=CONFLICT_ID,
        lesson_id=LESSON_ID,
        site_id=SITE_APPLIES,
        clause_uuid=CLAUSE_ISOLATION,
        base_digest=digest_lines(BASE_TEXT),
        ours_digest=digest_lines(SITE_TEXT),
        theirs_digest=digest_lines(FLEET_TEXT),
        opened_at=OPENED_AT,
    )
    return dataclasses.replace(base, **overrides)


def mechanism_absent() -> Declination:
    """A falsifiable 'not applicable': it names the predicate that would falsify it."""
    return Declination(kind="mechanism_absent", predicate_id=PREDICATE_ID)


def waiver() -> Declination:
    """A bounded 'not yet': MI28 says bounded means bounded."""
    return Declination(kind="waiver", expires_at=WAIVER_EXPIRY)


def mitigated() -> Declination:
    """'We already do this, here': convergent evolution, and it names the clause."""
    return Declination(kind="mitigated", already_present_clause=LOCAL_CLAUSE)
