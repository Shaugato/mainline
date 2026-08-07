# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The committed seed, and rule R2 arithmetic on top of it.

The seed tests are about the *file*: it loads, it is internally consistent, and
every entry can become a clause the loader can read back.  A half-loading seed
is worse than one that does not load at all, because the half that is missing
abstains, and an abstention looks like ordinary under-coverage rather than like
a broken build.

The R2 tests are about the sign.  Every one of them is a two-line story that
ends in a merge being refused or not, so getting the sign backwards is not a
test failure, it is the product failing.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from mainline_domain.canon import canon_digest
from mainline_domain.contracts import ControlDelta
from mainline_domain.quantity import quantity
from mainline_domain.registry import (
    AbstentionReason,
    ClauseVersionRow,
    EntryStatus,
    SafeDirection,
    SafeDirectionRegistry,
    clause_uuid_for,
    decode,
    encode,
    load_registry,
    load_seed,
    ratified_variant,
    seed_clause_rows,
    seed_source,
    setpoint_delta,
    tolerance_delta,
)

SITE = uuid.UUID("9f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f")
HEAD = hashlib.sha256(b"mainline-directrix-test/seeded-head").digest()


def _commit(label: str) -> bytes:
    return hashlib.sha256(f"mainline-directrix-test/{label}".encode()).digest()


@pytest.fixture(scope="module")
def registry() -> SafeDirectionRegistry:
    source = seed_source(site_id=SITE, commit_id=HEAD)
    return load_registry(source, site_id=SITE, as_of_commit=HEAD)


# ── the seed file ────────────────────────────────────────────────────────────


def test_the_seed_carries_at_least_sixty_real_parameters() -> None:
    parameters = load_seed()
    assert len(parameters) >= 60
    assert len({p.key for p in parameters}) == len(parameters)


def test_every_seeded_direction_is_ratifiable_and_every_dimension_resolves() -> None:
    for parameter in load_seed():
        assert parameter.direction is not SafeDirection.ABSTAIN
        assert parameter.dimensionality
        assert len(parameter.rationale) > 30, (
            f"{parameter.key!r} has a rationale too short to disagree with"
        )


def test_intervals_are_lower_is_safer_and_the_naming_convention_holds() -> None:
    """The direction people get backwards.

    "Test more often" is safer, and more often is a SHORTER interval.  A seeded
    ``*_interval`` marked ``higher_is_safer`` would classify every lengthening of
    a test interval as a tightening — which is the single most common real
    weakening in a procedure library.
    """
    for parameter in load_seed():
        if parameter.key.endswith("_interval") or parameter.key.endswith("_period"):
            if parameter.key.startswith("min_"):
                assert parameter.direction is SafeDirection.HIGHER_IS_SAFER, parameter.key
            else:
                assert parameter.direction is SafeDirection.LOWER_IS_SAFER, parameter.key
            assert parameter.dimension_label == "time", parameter.key


def test_the_min_and_max_prefixes_agree_with_their_directions() -> None:
    """A cheap consistency net over a hand-written file.

    ``max_*`` names a ceiling, so raising it weakens; ``min_*`` names a floor, so
    lowering it weakens.  The convention is not enforced by the code — a
    parameter is free to be named anything — but a seed entry that violates it is
    overwhelmingly more likely to be a typo than a considered exception, and a
    typo here inverts a verdict.
    """
    for parameter in load_seed():
        if parameter.direction is SafeDirection.TIGHTER_TOLERANCE_IS_SAFER:
            continue
        if parameter.key.startswith("max_"):
            assert parameter.direction is SafeDirection.LOWER_IS_SAFER, parameter.key
        elif parameter.key.startswith("min_"):
            assert parameter.direction is SafeDirection.HIGHER_IS_SAFER, parameter.key


def test_the_seeder_writes_proposed_and_unsigned_by_default() -> None:
    """A program does not ratify a safety decision.

    ``seed_clause_rows`` defaults to ``PROPOSED`` on an unsigned commit, so a
    freshly seeded site answers nothing until a human signs the ratification.
    That is inconvenient by design: it is the difference between a registry a
    person stands behind and one a build step produced.
    """
    rows = seed_clause_rows(
        site_id=SITE, commit_id=HEAD, author_sub="sub-bootstrap"
    )
    assert rows
    for row in rows:
        assert decode(row.canon_text).status is EntryStatus.PROPOSED
        assert row.ratification_signed is False

    ratified = ratified_variant(rows)
    for row in ratified:
        assert decode(row.canon_text).status is EntryStatus.RATIFIED
        assert row.ratification_signed is True

    # The ratified clause is a DIFFERENT clause: the text moved, so the digest
    # moved with it.  Two different texts sharing one canon_sha256 would break
    # the identity claim the whole document rests on.
    assert {r.canon_sha256 for r in rows}.isdisjoint({r.canon_sha256 for r in ratified})


def test_clause_ids_are_derived_and_therefore_reseeding_is_idempotent() -> None:
    """A random UUID would fork every parameter on the second seed run.

    Two clauses for one parameter load as ``duplicate_parameter``, which abstains,
    which blocks — a self-inflicted outage indistinguishable from a governance
    dispute.
    """
    a = clause_uuid_for(SITE, "max_operating_pressure")
    b = clause_uuid_for(SITE, "max_operating_pressure")
    c = clause_uuid_for(uuid.uuid4(), "max_operating_pressure")
    assert a == b
    assert a != c


def test_the_whole_seed_loads_as_a_registry(registry: SafeDirectionRegistry) -> None:
    assert len(registry.entries) == len(load_seed())
    assert registry.abstentions == {}


def test_the_seed_registry_reconstructs_differently_at_an_earlier_commit() -> None:
    """The done-when, end to end on the real seed rather than on constructed rows.

    Ratify the whole seed at ``c1``; flip one direction at ``c2``; read at both.
    The registry is a different object with a different answer at each, because
    it is reconstructed from the clause rows reachable from the commit it was
    asked about and nothing is cached between the two calls.
    """
    c1 = _commit("seed-at-c1")
    c2 = _commit("flip-at-c2")

    source = seed_source(site_id=SITE, commit_id=c1)
    source.add_commit(c2, parents=(c1,), author_sub="sub-reviser", signed=True)

    flipped = encode(
        parameter="max_operating_pressure",
        dimension_label="pressure",
        direction=SafeDirection.HIGHER_IS_SAFER,
        status=EntryStatus.RATIFIED,
        rationale="a later and, one hopes, well-argued reversal of the original entry",
    )
    source.add_version(
        ClauseVersionRow(
            clause_uuid=clause_uuid_for(SITE, "max_operating_pressure"),
            commit_id=c2,
            gen=2,
            canon_text=flipped,
            canon_sha256=canon_digest(flipped),
            ratified_by_sub="sub-reviser",
            ratification_signed=True,
        )
    )

    at_c1 = load_registry(source, site_id=SITE, as_of_commit=c1)
    at_c2 = load_registry(source, site_id=SITE, as_of_commit=c2)

    assert at_c1.parameters() == at_c2.parameters() == {p.key for p in load_seed()}
    assert at_c1.safe_direction("max_operating_pressure") is SafeDirection.LOWER_IS_SAFER
    assert at_c2.safe_direction("max_operating_pressure") is SafeDirection.HIGHER_IS_SAFER

    # And the ruling that hangs off it inverts with the registry, which is the
    # whole reason the loader is parameterised by a commit: the same edit is a
    # weakening under the registry that existed then and a tightening under the
    # one that exists now, and only one of those is the answer to "was this
    # permit safe to merge in March".
    before = setpoint_delta(
        at_c1,
        "max_operating_pressure",
        ancestor=quantity("400", "kPa"),
        descendant=quantity("600", "kPa"),
    )
    after = setpoint_delta(
        at_c2,
        "max_operating_pressure",
        ancestor=quantity("400", "kPa"),
        descendant=quantity("600", "kPa"),
    )
    assert before.delta is ControlDelta.WEAKEN
    assert after.delta is ControlDelta.STRENGTHEN


# ── rule R2 ──────────────────────────────────────────────────────────────────


def test_a_raised_ceiling_is_a_weakening(registry: SafeDirectionRegistry) -> None:
    ruling = setpoint_delta(
        registry,
        "max_operating_pressure",
        ancestor=quantity("400", "kPa"),
        descendant=quantity("600", "kPa"),
    )
    assert ruling.delta is ControlDelta.WEAKEN
    assert ruling.comparison == 1
    assert "LOWER_IS_SAFER" in ruling.reason


def test_a_lowered_ceiling_is_a_strengthening(registry: SafeDirectionRegistry) -> None:
    ruling = setpoint_delta(
        registry,
        "max_operating_pressure",
        ancestor=quantity("400", "kPa"),
        descendant=quantity("300", "kPa"),
    )
    assert ruling.delta is ControlDelta.STRENGTHEN


def test_an_unmoved_setpoint_is_a_restatement(registry: SafeDirectionRegistry) -> None:
    ruling = setpoint_delta(
        registry,
        "max_operating_pressure",
        ancestor=quantity("4", "bar"),
        descendant=quantity("400", "kPa"),
    )
    assert ruling.delta is ControlDelta.RESTATE
    assert ruling.comparison == 0


def test_a_lowered_floor_is_a_weakening(registry: SafeDirectionRegistry) -> None:
    ruling = setpoint_delta(
        registry,
        "min_ppe_level",
        ancestor=quantity("4", "levels"),
        descendant=quantity("2", "levels"),
    )
    assert ruling.delta is ControlDelta.WEAKEN
    assert ruling.direction is SafeDirection.HIGHER_IS_SAFER


def test_a_lengthened_test_interval_is_a_weakening(registry: SafeDirectionRegistry) -> None:
    """Six months to twelve is a weakening, and this is the one people argue about.

    Lengthening a test interval is the commonest real weakening in a procedure
    library and the one most often defended as administrative.  It is caught
    because ``*_interval`` parameters are seeded ``lower_is_safer``: more often
    is safer, and more often is a shorter interval.
    """
    ruling = setpoint_delta(
        registry,
        "gas_detector_calibration_interval",
        ancestor=quantity("6", "months"),
        descendant=quantity("12", "months"),
    )
    assert ruling.delta is ControlDelta.WEAKEN

    # ... and it survives being restated in a different time unit.
    ruling = setpoint_delta(
        registry,
        "gas_detector_calibration_interval",
        ancestor=quantity("26", "weeks"),
        descendant=quantity("52", "weeks"),
    )
    assert ruling.delta is ControlDelta.WEAKEN


def test_a_calendar_month_is_not_thirty_days_and_the_gate_says_so(
    registry: SafeDirectionRegistry,
) -> None:
    """``180 days`` -> ``6 months`` reports ``weaken``, and that is the right answer.

    A month here is the calendar average, 365.25/12 = 30.4375 days, so six months
    is 182.625 days — two and a half days longer than the interval it replaced.
    The comparison is exact, so the lattice reports the lengthening.

    This is over-blocking by two and a half days and it is deliberate.  The
    alternative is a tolerance on time comparisons, which is a policy about how
    much an interval may quietly grow before anybody is told — and that policy
    belongs in a clause somebody signed, not in an arithmetic helper.  Rewriting
    "180 days" as "6 months" IS a change to the control; the disposition is one
    sentence, and the record of it is the point.
    """
    ruling = setpoint_delta(
        registry,
        "gas_detector_calibration_interval",
        ancestor=quantity("180", "days"),
        descendant=quantity("6", "months"),
    )
    assert ruling.delta is ControlDelta.WEAKEN
    assert ruling.comparison == 1

    # The reverse restatement is a tightening, by the same two and a half days.
    reverse = setpoint_delta(
        registry,
        "gas_detector_calibration_interval",
        ancestor=quantity("6", "months"),
        descendant=quantity("180", "days"),
    )
    assert reverse.delta is ControlDelta.STRENGTHEN


def test_a_removed_isolation_point_is_a_weakening(registry: SafeDirectionRegistry) -> None:
    ruling = setpoint_delta(
        registry,
        "isolation_point_count",
        ancestor=quantity("3", "points"),
        descendant=quantity("2", "points"),
    )
    assert ruling.delta is ControlDelta.WEAKEN


def test_a_gauge_crossing_reaches_the_gate_as_a_weakening(
    registry: SafeDirectionRegistry,
) -> None:
    """Decision D5 meeting decision D6: the refusal becomes a blocking verdict.

    This is the join the whole worker exists to make.  The quantity algebra
    refuses to compare 400 kPa (frame unstated) with 50 psig; the ruling does not
    treat "no comparison" as "no change"; the result is ``weaken``, which the
    lattice turns into a blocking check that somebody has to dispose of by
    writing down which frame the clause meant.
    """
    ruling = setpoint_delta(
        registry,
        "max_operating_pressure",
        ancestor=quantity("400", "kPa"),
        descendant=quantity("50", "psig"),
    )
    assert ruling.delta is ControlDelta.WEAKEN
    assert ruling.abstained
    assert "reference frames" in ruling.reason


def test_an_unreadable_value_on_one_side_is_a_weakening(
    registry: SafeDirectionRegistry,
) -> None:
    """A setpoint that became unreadable is not a setpoint that stayed the same."""
    ruling = setpoint_delta(
        registry,
        "max_operating_pressure",
        ancestor=quantity("400", "kPa"),
        descendant=None,
    )
    assert ruling.delta is ControlDelta.WEAKEN


def test_a_parameter_whose_dimension_moved_abstains(
    registry: SafeDirectionRegistry,
) -> None:
    """``test_interval`` ratified in ``[time]``, now measured in shifts.

    A change of control disguised as a change of units, and the one place the
    registry can notice it.
    """
    ruling = setpoint_delta(
        registry,
        "gas_detector_calibration_interval",
        ancestor=quantity("6", "points"),
        descendant=quantity("12", "points"),
    )
    assert ruling.delta is ControlDelta.WEAKEN
    assert ruling.resolution.reason is AbstentionReason.DIMENSION_MISMATCH


def test_a_tolerance_parameter_refuses_the_value_question(
    registry: SafeDirectionRegistry,
) -> None:
    """Asking the wrong question gets a fail-closed answer, not a wrong one."""
    ruling = setpoint_delta(
        registry,
        "bolt_torque_specification",
        ancestor=quantity("100", "Nm"),
        descendant=quantity("120", "Nm"),
    )
    assert ruling.delta is ControlDelta.WEAKEN
    assert "tolerance_delta" in ruling.reason


def test_a_widened_tolerance_band_is_a_weakening(registry: SafeDirectionRegistry) -> None:
    widened = tolerance_delta(
        registry,
        "bolt_torque_specification",
        ancestor_band=quantity("5", "Nm"),
        descendant_band=quantity("15", "Nm"),
    )
    assert widened.delta is ControlDelta.WEAKEN

    narrowed = tolerance_delta(
        registry,
        "bolt_torque_specification",
        ancestor_band=quantity("15", "Nm"),
        descendant_band=quantity("5", "Nm"),
    )
    assert narrowed.delta is ControlDelta.STRENGTHEN

    removed = tolerance_delta(
        registry,
        "bolt_torque_specification",
        ancestor_band=quantity("5", "Nm"),
        descendant_band=None,
    )
    assert removed.delta is ControlDelta.WEAKEN
    assert "unbounded" in removed.reason


def test_tolerance_delta_refuses_a_value_governed_parameter(
    registry: SafeDirectionRegistry,
) -> None:
    ruling = tolerance_delta(
        registry,
        "max_operating_pressure",
        ancestor_band=quantity("5", "kPa"),
        descendant_band=quantity("1", "kPa"),
    )
    assert ruling.delta is ControlDelta.WEAKEN
    assert "setpoint_delta" in ruling.reason


def test_no_ruling_in_the_whole_seed_can_produce_introduce_or_remove(
    registry: SafeDirectionRegistry,
) -> None:
    """R2 decides direction, not existence.

    ``introduce`` and ``remove`` are decided by whether the CAT is there at all,
    which is W4's call over the extracted tuples.  A setpoint rule that could
    emit them would be making a claim about coverage from a comparison of two
    numbers.
    """
    for parameter in load_seed():
        for before, after in (("10", "20"), ("20", "10"), ("10", "10")):
            unit = _sample_unit(parameter.dimension_label)
            if unit is None:
                continue
            ruling = setpoint_delta(
                registry,
                parameter.key,
                ancestor=quantity(before, unit),
                descendant=quantity(after, unit),
            )
            assert ruling.delta in {
                ControlDelta.WEAKEN,
                ControlDelta.STRENGTHEN,
                ControlDelta.RESTATE,
            }, parameter.key


_SAMPLE_UNITS = {
    "pressure": "kPa",
    "temperature": "degC",
    "time": "months",
    "length": "m",
    "mass": "kg",
    "count": "points",
    "ordinal": "levels",
    "ratio": "%",
    "lel_fraction": "%LEL",
    "uel_fraction": "%UEL",
    "volume_fraction": "%vol",
    "sound_level": "dBA",
    "illuminance": "lux",
    "radiation_dose": "mSv",
    "voltage": "V",
    "current": "mA",
    "velocity": "m/s",
    "volumetric_flow": "m3/h",
    "mass_concentration": "mg/m3",
    "angle": "deg",
    "torque": "Nm",
}


def _sample_unit(dimension_label: str) -> str | None:
    return _SAMPLE_UNITS.get(dimension_label)


def test_every_seeded_dimension_label_has_a_sample_unit() -> None:
    """Keeps the coverage loop above from silently skipping half the seed."""
    missing = {
        parameter.dimension_label
        for parameter in load_seed()
        if _sample_unit(parameter.dimension_label) is None
    }
    assert not missing, f"no sample unit for {sorted(missing)}"
