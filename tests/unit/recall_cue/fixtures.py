# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Committed inputs and committed model bodies for the cue-synthesis suite.

Shared by ``make_cue_cassettes.py`` (which drives the real judge with a scripted transport
and writes the cassettes) and by the tests (which replay them).  Both sides therefore build
byte-identical requests, which is the only way a digest-keyed cassette can hit.

The narratives are written as single lines on purpose.  ``source_text.canonicalise``
preserves newlines — it is an offset-bearing canonicaliser, not an embedding normaliser — so
a fixture with wrapped prose would make every evidence quote depend on where the wrap fell.

**Provenance.**  The model bodies below are *authored*, not recorded.  AWS credentials are
not valid on the build machine, so no live Claude response exists to record, and the
cassettes are marked ``handwritten``.  They are evidence about **our pipeline** — that the
per-facet escape round-trips, that an absent anchor is rejected before insert, that offsets
are computed and unique, that a refusal becomes a silence record — and about nothing else.
No test here may claim anything about how a real model behaves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SRC = (
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-recall-agent" / "src"
)
if str(PACKAGE_SRC) not in sys.path:  # pragma: no cover - import-time bootstrap
    sys.path.insert(0, str(PACKAGE_SRC))

from mainline_recall_agent.cue.models import (  # noqa: E402
    ActivityNode,
    ActivityPath,
    ClauseDiff,
    ClauseDiffEntry,
    ControlFailureHint,
    EventInput,
    IsolationPlan,
    IsolationPoint,
    PermitInput,
)
from mainline_recall_agent.providers.types import ResolvedModel  # noqa: E402

CASSETTE_ROOT = Path(__file__).resolve().parent / "cassettes"

#: The identity the fixtures were built under.  ``profile_id`` is honest about what it is:
#: no ``bedrock:ListInferenceProfiles`` call has ever succeeded on this machine, so the
#: cassette identity says "cassette", and ``gen_model`` on every fixture row says so too.
CASSETTE_MODEL = ResolvedModel(
    requested_tier="claude-opus-5",
    resolved_tier="claude-opus-5",
    profile_id="cassette://au-profile-unresolved",
    profile_arn=None,
    region="ap-southeast-2",
    source="cassette",
)

# --------------------------------------------------------------------------------------
# Deterministic identifiers.  Version-5 style constants, written out so the fixtures are
# reproducible without a UUID generator in the loop.
# --------------------------------------------------------------------------------------

SITE_ID = UUID("11111111-1111-4111-8111-111111111111")
FONDS_SCOPE = UUID("22222222-2222-4222-8222-222222222201")
SERIES_SCOPE = UUID("22222222-2222-4222-8222-222222222202")
FILE_SCOPE = UUID("22222222-2222-4222-8222-222222222203")

ASSET_CLASS_TYRE = "haul truck wheel assembly"
ASSET_CLASS_CRUSHER = "secondary crushing"
ASSET_CLASS_ACID = "acid unloading"

ACTIVITY_PATH = ActivityPath(
    nodes=(
        ActivityNode(
            scope_id=FONDS_SCOPE,
            level=1,
            label="isolating stored energy before intrusive work",
        ),
        ActivityNode(
            scope_id=SERIES_SCOPE,
            level=2,
            label="maintaining pressurised assemblies",
        ),
        ActivityNode(
            scope_id=FILE_SCOPE,
            level=3,
            label="inflating and seating multi-piece rims",
        ),
    )
)

CRUSHER_PATH = ActivityPath(
    nodes=(
        ActivityNode(
            scope_id=FONDS_SCOPE,
            level=1,
            label="isolating stored energy before intrusive work",
        ),
        ActivityNode(
            scope_id=SERIES_SCOPE,
            level=2,
            label="entering machine envelopes for maintenance",
        ),
    )
)

ACID_PATH = ActivityPath(
    nodes=(
        ActivityNode(
            scope_id=FONDS_SCOPE,
            level=1,
            label="isolating stored energy before intrusive work",
        ),
        ActivityNode(
            scope_id=SERIES_SCOPE,
            level=2,
            label="breaking containment on reagent lines",
        ),
    )
)

# --------------------------------------------------------------------------------------
# Event fixtures.
# --------------------------------------------------------------------------------------

RIM_NARRATIVE = (
    "During inflation of a multi-piece wheel assembly on haul truck TF-12 the lock ring "
    "was displaced and the rim components separated axially, striking the fitter who was "
    "standing beside the assembly. The assembly had been inflated to 620 kPa at the time "
    "of separation. The workshop held no inflation cage and no remote inflation line. The "
    "task instruction required the fitter to observe seating of the lock ring during "
    "inflation."
)

EVENT_FULL = EventInput(
    event_id=UUID("33333333-3333-4333-8333-333333333301"),
    site_id=SITE_ID,
    taxonomy_ver=3,
    kind="incident",
    title="Multi-piece rim separation during inflation in the tyre bay",
    narrative=RIM_NARRATIVE,
    external_ref="FIX-EVT-0001",
    control_failures=(
        ControlFailureHint(
            control_class="engineered_exclusion_zone",
            barrier_role="preventive",
            failure_mode="absent",
            hazard_energy="pressure",
        ),
    ),
)

FIRE_NARRATIVE = (
    "A fire was reported in the reagent store shortly after the shift change and the store "
    "was heavily damaged. Incompatible reagents were held in a single store without "
    "physical segregation. The cause of ignition could not be determined by the "
    "investigation."
)

EVENT_INSUFFICIENT = EventInput(
    event_id=UUID("33333333-3333-4333-8333-333333333302"),
    site_id=SITE_ID,
    taxonomy_ver=3,
    kind="incident",
    title="Fire in the reagent store, cause undetermined",
    narrative=FIRE_NARRATIVE,
    external_ref="FIX-EVT-0002",
)

CONVEYOR_NARRATIVE = (
    "A maintainer entered the drive guard of an inclined conveyor to clear spillage while "
    "the belt remained loaded above the drive. The isolation certificate named the "
    "electrical supply only and said nothing about the loaded belt. The belt rolled back "
    "through the drive when the brake was released."
)

EVENT_ANCHOR_FABRICATION = EventInput(
    event_id=UUID("33333333-3333-4333-8333-333333333303"),
    site_id=SITE_ID,
    taxonomy_ver=3,
    kind="incident",
    title="Belt rollback through a conveyor drive during spillage clearing",
    narrative=CONVEYOR_NARRATIVE,
    external_ref="FIX-EVT-0003",
)

EVENT_REFUSAL = EventInput(
    event_id=UUID("33333333-3333-4333-8333-333333333304"),
    site_id=SITE_ID,
    taxonomy_ver=3,
    kind="incident",
    title="Hydrogen cyanide liberation in a barren solution circuit",
    narrative=(
        "Acidic wash water met cyanide-bearing solution in a shared return header while the "
        "low pH interlock was in bypass, and hydrogen cyanide was liberated in the pump "
        "room. Two operators were exposed before the room was evacuated."
    ),
    external_ref="FIX-EVT-0004",
)

EVENT_DEADLETTER = EventInput(
    event_id=UUID("33333333-3333-4333-8333-333333333305"),
    site_id=SITE_ID,
    taxonomy_ver=3,
    kind="near_miss",
    title="Uncontrolled descent of a suspended load during a lift",
    narrative=(
        "A suspended load descended without command when the hoist brake failed to hold, "
        "and the load came to rest on a walkway that had not been cleared of people."
    ),
    external_ref="FIX-EVT-0005",
)

# --------------------------------------------------------------------------------------
# Permit fixtures.
# --------------------------------------------------------------------------------------

PERMIT_EXPOSED = PermitInput(
    permit_id=UUID("44444444-4444-4444-8444-444444444401"),
    site_id=SITE_ID,
    taxonomy_ver=3,
    activity_path=CRUSHER_PATH,
    asset_class=ASSET_CLASS_CRUSHER,
    work_type="confined_space_entry",
    scope_of_work=(
        "Replace liner bolts inside the shell of secondary crusher CR-201 with two fitters "
        "working inside the machine envelope."
    ),
    external_ref="FIX-PTW-0001",
)

ISOLATION_EXPOSED = IsolationPlan(
    plan_ref="ISOPLAN-7742",
    points=(
        IsolationPoint(
            tag="CR-201",
            energy="electrical",
            method="racked out at the switchboard and locked",
            verified_by="electrical supervisor",
        ),
    ),
    residual_energy_notes="Charge in the shell has not been removed.",
)

DIFF_EXPOSED = ClauseDiff(
    entries=(
        ClauseDiffEntry(
            clause_uuid=UUID("55555555-5555-4555-8555-555555555501"),
            clause_ref="MEM 4.3 machine envelope entry",
            control_delta="weaken",
            before_text=(
                "Stored mechanical energy shall be dissipated and proven at zero before any "
                "person enters the machine envelope."
            ),
            after_text=(
                "A visual check that the shell is stationary shall be recorded before entry."
            ),
            rationale=(
                "The dedicated rotation lock required for a zero energy proof is not "
                "available this shutdown."
            ),
        ),
        ClauseDiffEntry(
            clause_uuid=UUID("55555555-5555-4555-8555-555555555502"),
            clause_ref="MEM 9.1 lighting",
            control_delta="strengthen",
            before_text="Task lighting shall be provided at the work face.",
            after_text=(
                "Task lighting shall be provided at the work face and proven before entry."
            ),
        ),
    )
)

PERMIT_ROUTINE = PermitInput(
    permit_id=UUID("44444444-4444-4444-8444-444444444402"),
    site_id=SITE_ID,
    taxonomy_ver=3,
    activity_path=ACID_PATH,
    asset_class=ASSET_CLASS_ACID,
    work_type="instrument_maintenance",
    scope_of_work=(
        "Replace the pressure transmitter on the sulfuric acid unloading line. The line is "
        "drained and depressurised, and depressurisation is verified at the coupling before "
        "it is broken."
    ),
    external_ref="FIX-PTW-0002",
)

ISOLATION_ROUTINE = IsolationPlan(
    plan_ref="ISOPLAN-7743",
    points=(
        IsolationPoint(
            tag="AC-118",
            energy="chemical",
            method="line drained, flushed, and depressurisation verified at the coupling",
        ),
    ),
)

DIFF_ROUTINE = ClauseDiff()


# --------------------------------------------------------------------------------------
# Model bodies.  Authored contract fixtures — see the module docstring.
# --------------------------------------------------------------------------------------


def _facet(cue_text: str, quote: str) -> dict[str, Any]:
    return {
        "cue_text": cue_text,
        "evidence_quote": quote,
        "insufficient": False,
        "insufficient_reason": None,
    }


def _insufficient(reason: str) -> dict[str, Any]:
    return {
        "cue_text": None,
        "evidence_quote": None,
        "insufficient": True,
        "insufficient_reason": reason,
    }


BODY_EVENT_FULL = json.dumps(
    {
        "mechanism": _facet(
            "Stored pneumatic energy released axially when a multi-piece rim assembly "
            "separates during inflation.",
            "the rim components separated axially, striking the fitter",
        ),
        "precondition": _facet(
            "A person occupies the trajectory of a pressurised multi-piece assembly while "
            "it is being inflated to 620 kPa.",
            "The assembly had been inflated to 620 kPa at the time of separation.",
        ),
        "control_failure": _facet(
            "Engineered exclusion from the trajectory zone was absent and the task relied "
            "on procedural judgement to keep the person clear.",
            "The workshop held no inflation cage and no remote inflation line.",
        ),
        "recurrence_test": _facet(
            "Recurs wherever a person can occupy the trajectory of a pressurised "
            "multi-piece rim during inflation.",
            "The task instruction required the fitter to observe seating of the lock ring",
        ),
    }
)

BODY_EVENT_INSUFFICIENT = json.dumps(
    {
        "mechanism": _insufficient(
            "The investigation did not establish how ignition occurred, so any mechanism "
            "written here would be invented rather than recorded."
        ),
        "precondition": _facet(
            "Incompatible reagents held in one store without physical segregation between "
            "storage classes.",
            "Incompatible reagents were held in a single store without physical segregation.",
        ),
        "control_failure": _insufficient(
            "The record does not state which control was relied on to keep the incompatible "
            "reagents apart."
        ),
        "recurrence_test": _facet(
            "Recurs wherever incompatible reagents are held in one store without physical "
            "segregation.",
            "Incompatible reagents were held in a single store without physical segregation.",
        ),
    }
)

#: The fabrication.  ``K-401`` appears nowhere in the conveyor record.
BODY_EVENT_ANCHOR_FABRICATION = json.dumps(
    {
        "mechanism": _facet(
            "Release of stored gravitational energy when a loaded incline belt rolls back "
            "through drive K-401.",
            "The belt rolled back through the drive when the brake was released.",
        ),
        "precondition": _facet(
            "A person is inside a drive guard while the belt above the drive remains "
            "loaded.",
            "A maintainer entered the drive guard of an inclined conveyor to clear spillage",
        ),
        "control_failure": _facet(
            "The isolation scope named supply only and was silent on the stored energy in "
            "the loaded belt.",
            "The isolation certificate named the electrical supply only",
        ),
        "recurrence_test": _facet(
            "Recurs wherever a person enters a conveyor drive guard while the belt above it "
            "remains loaded.",
            "said nothing about the loaded belt",
        ),
    }
)

BODY_EXPOSURE_EXPOSED = json.dumps(
    {
        "mechanism": _facet(
            "Release of stored gravitational and rotational energy when an unbalanced "
            "charge rotates a crusher shell with people inside it.",
            "Replace liner bolts inside the shell of secondary crusher CR-201 with two "
            "fitters working inside the machine envelope.",
        ),
        "precondition": _facet(
            "Entry into a machine envelope under an isolation whose scope names electrical "
            "supply and is silent on stored mechanical energy.",
            "residual energy: Charge in the shell has not been removed.",
        ),
        "control_failure": _facet(
            "Proof of zero stored energy is replaced by a visual check that cannot detect "
            "an unbalanced charge.",
            "after: A visual check that the shell is stationary shall be recorded before "
            "entry.",
        ),
        "recurrence_test": _facet(
            "Recurs wherever people enter a machine envelope isolated against supply but "
            "not against stored energy.",
            "before: Stored mechanical energy shall be dissipated and proven at zero before "
            "any person enters the machine envelope.",
        ),
    }
)

BODY_EXPOSURE_ROUTINE = json.dumps(
    {
        "mechanism": _facet(
            "Loss of containment of a corrosive liquid at a coupling being broken on an "
            "unloading line.",
            "Replace the pressure transmitter on the sulfuric acid unloading line.",
        ),
        "precondition": _insufficient(
            "The scope specifies verification of depressurisation at the point of breaking "
            "containment, so the residual pressure state this mechanism needs is not created."
        ),
        "control_failure": _insufficient(
            "No control is being stood down; the permit waives and weakens no clause."
        ),
        "recurrence_test": _insufficient(
            "Without a precondition or a stood down control, any test written here would "
            "recall every acid line job in the corpus."
        ),
    }
)

#: Schema-invalid: an extra field the strict schema forbids.  Drives the repair path.
BODY_INVALID_EXTRA_FIELD = json.dumps(
    {
        "mechanism": {
            **_facet(
                "A suspended load descends without command when the hoist brake fails to "
                "hold it.",
                "A suspended load descended without command when the hoist brake failed",
            ),
            "confidence": 0.91,
        },
        "precondition": _insufficient("not established"),
        "control_failure": _insufficient("not established"),
        "recurrence_test": _insufficient("not established"),
    }
)

#: Schema-invalid a second way: a populated facet with no evidence quote.
BODY_INVALID_NO_QUOTE = json.dumps(
    {
        "mechanism": {
            "cue_text": "A suspended load descends without command when the hoist brake "
            "fails to hold it.",
            "evidence_quote": None,
            "insufficient": False,
            "insufficient_reason": None,
        },
        "precondition": _insufficient("not established"),
        "control_failure": _insufficient("not established"),
        "recurrence_test": _insufficient("not established"),
    }
)
