# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A small, real corpus: confined-space entry at a gold-processing plant.

Everything here is a fixed literal. No ``now()``, no ``uuid4()``, no seeded
generator — a fixity finding is a record about a moment, and a fixture whose
moment moves cannot test one.

The clause under test is the one the whole product is about: an atmospheric-testing
threshold before confined-space entry, bound to a thickener underflow vessel. The
document says 10 % LEL; what the plant does is what the patrol is for.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from mainline_domain.contracts import CAT, Quantity
from mainline_domain.registry.model import (
    EntryStatus,
    RegistryEntry,
    SafeDirection,
    SafeDirectionRegistry,
)
from mainline_fixity import ClauseBinding, ErrorBar, ObservedAssertion, PatrolScope

SITE = uuid.UUID("11111111-1111-1111-1111-111111111111")
COMMIT = bytes.fromhex("ab" * 32)
CLAUSE_GAS_TEST = uuid.UUID("22222222-2222-2222-2222-222222222222")
CLAUSE_ISOLATION = uuid.UUID("33333333-3333-3333-3333-333333333333")
ASSET = "TK-2201"
OCCURRENCE = datetime(2026, 8, 4, 1, 0, tzinfo=UTC)
STARTED = datetime(2026, 8, 4, 1, 0, 12, tzinfo=UTC)
FINISHED = datetime(2026, 8, 4, 1, 3, 44, tzinfo=UTC)
EFFECTIVE = datetime(2026, 8, 3, 22, 15, tzinfo=UTC)
AS_OF_HLC = Decimal("1785873600000000000.0000000001")

#: An arbitrary but fixed 32-byte leaf hash. Fixed so the emitted parameters are
#: comparable across runs; arbitrary because nothing under test reads its value.
LEAF = bytes.fromhex("cd" * 32)


def build_registry() -> SafeDirectionRegistry:
    """Four ratified parameters and one that is deliberately absent.

    ``mystery_parameter`` has no entry, so the registry abstains on it and the
    lattice resolves that abstention to ``weaken``. That is the ``abstain ⇒
    weaken`` rule, and having a parameter in the corpus that triggers it is what
    keeps the rule tested rather than described.
    """
    entries = {
        "lel_test_threshold": _entry("lel_test_threshold", SafeDirection.LOWER_IS_SAFER),
        "max_operating_pressure": _entry(
            "max_operating_pressure",
            SafeDirection.LOWER_IS_SAFER,
            dimension_label="pressure",
            dimensionality="[mass] / [length] / [time] ** 2",
        ),
        "min_oxygen_concentration": _entry(
            "min_oxygen_concentration", SafeDirection.HIGHER_IS_SAFER
        ),
        "flange_torque_target": _entry(
            "flange_torque_target", SafeDirection.TIGHTER_TOLERANCE_IS_SAFER
        ),
    }
    return SafeDirectionRegistry(
        site_id=SITE,
        as_of_commit=COMMIT,
        doc_code="DIRECTRIX",
        entries=entries,
        abstentions={},
        encoding_version=1,
        document_present=True,
    )


def _entry(
    parameter: str,
    direction: SafeDirection,
    *,
    dimension_label: str = "dimensionless",
    dimensionality: str = "dimensionless",
) -> RegistryEntry:
    return RegistryEntry(
        parameter=parameter,
        dimension_label=dimension_label,
        dimensionality=dimensionality,
        direction=direction,
        status=EntryStatus.RATIFIED,
        rationale=f"safe direction for {parameter}, ratified on a signed commit",
        clause_uuid=uuid.uuid5(uuid.NAMESPACE_OID, parameter),
        ratification_commit=COMMIT,
        ratified_by_sub="person:hse-manager",
        ratification_signed=True,
        gen=1,
        canon_sha256=bytes(32),
    )


def gas_test_cat(threshold: str, *, parameter: str = "lel_test_threshold") -> CAT:
    """The atmospheric-testing obligation, at a stated threshold."""
    return CAT(
        actor="authorised gas tester",
        deontic="shall",
        action="verify atmosphere",
        object_class="confined space",
        hazard_energy="flammable_atmosphere",
        parameter=parameter,
        comparator="<=",
        value=Quantity(
            value=Decimal(threshold),
            unit="percent",
            dimension="dimensionless",
            reference="none",
        ),
        conditions=("before entry",),
        exceptions=(),
        verification=("gas test record countersigned by the permit issuer",),
        frequency=None,
        coverage_quantifier="every",
    )


def observation(
    cat: CAT | None,
    *,
    source_kind: str = "historian",
    err_bar: ErrorBar | None = None,
    obs_seed: str = "obs-1",
) -> ObservedAssertion:
    """One plant export row for :data:`ASSET`."""
    return ObservedAssertion(
        obs_id=uuid.uuid5(uuid.NAMESPACE_OID, obs_seed),
        site_id=SITE,
        source_kind=source_kind,  # type: ignore[arg-type]
        source_ref="s3://mainline-ot-landing/pi/2026-08-03.parquet#v.9f1c",
        asset_tag=ASSET,
        observed_cat=cat,
        effective_at=EFFECTIVE,
        leaf_hash=LEAF,
        err_bar=err_bar,
    )


def binding(
    clause_uuid: uuid.UUID = CLAUSE_GAS_TEST,
    *,
    bind_kind: str = "explicit",
    confidence_milli: int = 940,
) -> ClauseBinding:
    """The SME-reviewed clause ⇄ asset link."""
    return ClauseBinding(
        clause_uuid=clause_uuid,
        asset_tag=ASSET,
        site_id=SITE,
        bind_kind=bind_kind,  # type: ignore[arg-type]
        bound_by="person:process-safety-engineer",
        confidence_milli=confidence_milli,
    )


def scope() -> PatrolScope:
    """One L2 (as-operated) occurrence, at 01:00 AEST as §8.5 schedules it."""
    return PatrolScope(
        site_id=SITE,
        patrol_class="L2",
        schedule_id="fixity-patrol-l2-nightly",
        occurrence_ts=OCCURRENCE,
        scope_pred={"asset_tags": [ASSET], "hazard_energy": "flammable_atmosphere"},
    )


#: The corridor a PI tag actually carries: 0.25 % exception plus 0.5 % compression.
#: They compose in series, so the corridor is 0.75 % and not 0.559 %.
HISTORIAN_BAR = ErrorBar(exc_dev=Decimal("0.25"), comp_dev=Decimal("0.5"), unit="percent")
