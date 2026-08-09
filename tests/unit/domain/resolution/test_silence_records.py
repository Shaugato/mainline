# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""P5 — the row that answers "your system said nothing".

The silence ledger's whole value is that it is a *complete* list of the warnings
that were not given, with arithmetic attached.  Two ways to destroy that value:
omit a row that should be there, and add one that should not.  Both are asserted
here, along with the two database ``CHECK`` vocabularies, which are enforced in
Python so that a row the database would refuse cannot be built in the first place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from mainline_domain.contracts import ControlDelta, DeltaVerdict, DeltaWitness, OracleVerdict
from mainline_domain.resolution import (
    ABSTENTION_CODES,
    REASON_FOR_ABSTENTION_CODE,
    SILENCE_REASONS,
    SILENCE_SOURCES,
    abstention_code_of,
    explain,
    requires_silence_record,
    silence_record,
    stamp_rationale,
)

_SITE = UUID("11111111-1111-1111-1111-111111111111")
_SUBJECT = UUID("22222222-2222-2222-2222-222222222222")
_THETA = 0.75
_AT = datetime(2026, 8, 8, 3, 0, tzinfo=UTC)
_WITNESS = DeltaWitness("R7_FREQUENCY", "frequency", "30 min", "120 min", "interval lengthened")


def _a(delta=ControlDelta.RESTATE, witnesses=()):
    return DeltaVerdict(delta=delta, basis="lattice", witnesses=witnesses, minimal=bool(witnesses))


def _b(label, confidence, *, abstained=False, rationale="relation=neutral band=high"):
    return OracleVerdict(
        label=label,
        confidence=confidence,
        rationale=rationale,
        cited_spans=((0, 4),),
        model_id="au.anthropic.claude-opus-5",
        prompt_version="adjudication.v1+rubric.v1",
        abstained=abstained,
    )


def _record(resolution, severity=5):
    return silence_record(
        resolution,
        site_id=_SITE,
        subject_id=_SUBJECT,
        max_ancestral_severity=severity,
        policy_version="identity-policy-v1",
        policy_sha256="c0ffee" * 10 + "abcd",
        at=_AT,
    )


# ── which resolutions get a row ─────────────────────────────────────────────────


def test_a_neutral_is_recorded() -> None:
    resolution = explain(_a(), _b(ControlDelta.RESTATE, 0.85), theta=_THETA)
    assert requires_silence_record(resolution)
    assert _record(resolution).reason == "bounded_negative"


def test_an_abstention_is_recorded() -> None:
    resolution = explain(
        _a(),
        _b(
            ControlDelta.WEAKEN,
            0.0,
            abstained=True,
            rationale=stamp_rationale("model_abstained", "x"),
        ),
        theta=_THETA,
    )
    assert requires_silence_record(resolution)
    assert _record(resolution).reason == "abstained"


def test_a_below_theta_disagreement_is_recorded_as_below_tau() -> None:
    resolution = explain(_a(), _b(ControlDelta.STRENGTHEN, 0.4), theta=_THETA)
    assert _record(resolution).reason == "below_tau"


def test_a_weakening_is_not_silence_and_is_refused() -> None:
    """The rule that keeps the ledger meaning what it says."""
    resolution = explain(_a(), _b(ControlDelta.WEAKEN, 0.85), theta=_THETA)
    assert not requires_silence_record(resolution)
    with pytest.raises(ValueError, match="not silence"):
        _record(resolution)


def test_an_absent_path_b_is_unreachable_not_abstained() -> None:
    """An outage must never present as a model that could not decide."""
    resolution = explain(_a(), None, theta=_THETA)
    record = _record(resolution)
    assert record.reason == "unreachable"
    assert record.arithmetic["abstention_code"] == "not_run"


@pytest.mark.parametrize("code", sorted(ABSTENTION_CODES))
def test_every_abstention_code_maps_to_a_legal_reason(code: str) -> None:
    resolution = explain(
        _a(),
        _b(ControlDelta.WEAKEN, 0.0, abstained=True, rationale=stamp_rationale(code, "detail")),
        theta=_THETA,
    )
    record = _record(resolution)
    assert record.reason == REASON_FOR_ABSTENTION_CODE[code]
    assert record.reason in SILENCE_REASONS


def test_an_unstamped_rationale_falls_back_to_the_generic_reason() -> None:
    """No word is invented for a producer this vocabulary does not describe."""
    resolution = explain(
        _a(), _b(ControlDelta.WEAKEN, 0.0, abstained=True, rationale="who knows"), theta=_THETA
    )
    assert abstention_code_of("who knows") is None
    assert _record(resolution).reason == "abstained"


# ── the row itself ──────────────────────────────────────────────────────────────


def test_the_vocabularies_are_the_database_check_lists() -> None:
    assert "delta_neutral" in SILENCE_SOURCES
    assert {"below_tau", "abstained", "bounded_negative", "unreachable", "model_refusal"} <= (
        SILENCE_REASONS
    )


def test_the_row_carries_the_whole_arithmetic() -> None:
    resolution = explain(_a(witnesses=(_WITNESS,)), _b(ControlDelta.RESTATE, 0.85), theta=_THETA)
    record = _record(resolution)
    arithmetic = record.arithmetic
    assert record.source == "delta_neutral"
    assert record.score == 0.85
    assert record.threshold == _THETA
    assert arithmetic["path_a_delta"] == "restate"
    assert arithmetic["oracle_label"] == "restate"
    assert arithmetic["theta"] == _THETA
    assert arithmetic["model_id"] == "au.anthropic.claude-opus-5"
    assert arithmetic["prompt_version"] == "adjudication.v1+rubric.v1"
    assert arithmetic["resolution_rule"] == "CONCUR"
    assert arithmetic["resolution_table_version"] == "ratchet.v1"
    assert len(arithmetic["resolution_table_sha256"]) == 64
    assert arithmetic["policy_sha256"].startswith("c0ffee")
    assert arithmetic["witnesses"] == [
        {
            "rule_id": "R7_FREQUENCY",
            "field": "frequency",
            "from": "30 min",
            "to": "120 min",
            "note": "interval lengthened",
        }
    ]


def test_the_row_is_shaped_like_the_table() -> None:
    resolution = explain(_a(), _b(ControlDelta.RESTATE, 0.85), theta=_THETA)
    mapping = _record(resolution).to_mapping()
    assert set(mapping) == {
        "site_id",
        "source",
        "reason",
        "subject_kind",
        "subject_id",
        "severity",
        "score",
        "threshold",
        "arithmetic",
        "policy_version",
        "at",
    }
    assert mapping["subject_kind"] == "clause_version"
    assert mapping["site_id"] == str(_SITE)


@pytest.mark.parametrize("severity", [-1, 6])
def test_a_severity_outside_the_coded_scale_is_refused(severity: int) -> None:
    resolution = explain(_a(), _b(ControlDelta.RESTATE, 0.85), theta=_THETA)
    with pytest.raises(ValueError, match="projection of"):
        _record(resolution, severity=severity)


def test_the_timestamp_is_timezone_aware() -> None:
    resolution = explain(_a(), _b(ControlDelta.RESTATE, 0.85), theta=_THETA)
    assert _record(resolution).at.tzinfo is not None
    assert (
        silence_record(
            resolution,
            site_id=_SITE,
            subject_id=_SUBJECT,
            max_ancestral_severity=4,
            policy_version="identity-policy-v1",
        ).at.tzinfo
        is not None
    )


def test_stamping_refuses_an_unknown_code() -> None:
    with pytest.raises(ValueError, match="not an abstention code"):
        stamp_rationale("made_up", "detail")


def test_every_code_round_trips_through_the_rationale() -> None:
    for code in ABSTENTION_CODES:
        assert abstention_code_of(stamp_rationale(code, "some detail: with a colon")) == code
