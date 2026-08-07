# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The registry clause grammar: it round-trips, and canonicalisation does not move it.

The canon-stability test is the load-bearing one.  A registry entry is stored as
a clause, so its ``canon_sha256`` is the digest of its canonicalised text.  If
canonicalisation altered a byte of what the encoder emitted, the digest on the
row would not be the digest of the text this module wrote, and every identity,
blame and residue claim about the registry document would be built on that
mismatch — quietly, because nothing checks it anywhere else.
"""

from __future__ import annotations

import pytest
from mainline_domain.canon import canonicalise
from mainline_domain.registry import (
    RATIFIABLE_DIRECTIONS,
    EntryStatus,
    RegistryEncodingError,
    SafeDirection,
    decode,
    encode,
    load_seed,
)


def test_round_trip_over_the_whole_committed_seed() -> None:
    for parameter in load_seed():
        for status in EntryStatus:
            text = encode(
                parameter=parameter.key,
                dimension_label=parameter.dimension_label,
                direction=parameter.direction,
                status=status,
                rationale=parameter.rationale,
            )
            decoded = decode(text)
            assert decoded.parameter == parameter.key
            assert decoded.dimension_label == parameter.dimension_label
            assert decoded.dimensionality == parameter.dimensionality
            assert decoded.direction is parameter.direction
            assert decoded.status is status
            assert decoded.rationale == parameter.rationale


def test_canonicalisation_does_not_move_a_registry_clause() -> None:
    """``canonicalise(encode(x)).canon_text == encode(x)`` for every seeded entry.

    Four specific traps are avoided by construction and all four are exercised
    by running the real canonicaliser over the real seed: the line starts with a
    letter so no numbering prefix is excised; it is pure ASCII so NFKC folding is
    a no-op; it has no double spaces so whitespace collapse is a no-op; and no
    token starts with a digit so numeric OCR repair cannot reach it.
    """
    for parameter in load_seed():
        text = encode(
            parameter=parameter.key,
            dimension_label=parameter.dimension_label,
            direction=parameter.direction,
            status=EntryStatus.RATIFIED,
            rationale=parameter.rationale,
        )
        result = canonicalise(text)
        assert result.canon_text == text, (
            f"canonicalisation moved the clause for {parameter.key!r}:\n"
            f"  encoded: {text!r}\n"
            f"  canon:   {result.canon_text!r}"
        )
        assert result.numbering_prefix is None
        assert result.ocr_repairs == ()


def test_abstain_cannot_be_written_to_a_clause() -> None:
    """Nobody gets to ratify "this parameter is permanently unanswerable".

    ``ABSTAIN`` is what the system answers when it has no ratified entry.  A
    clause asserting it would be indistinguishable, downstream, from the
    coverage gap it was hiding — and it would carry a signature, which would make
    the gap look like a decision.
    """
    with pytest.raises(RegistryEncodingError) as raised:
        encode(
            parameter="max_operating_pressure",
            dimension_label="pressure",
            direction=SafeDirection.ABSTAIN,
            status=EntryStatus.RATIFIED,
            rationale="because",
        )
    assert "ABSTAIN" in str(raised.value)
    assert SafeDirection.ABSTAIN not in RATIFIABLE_DIRECTIONS


def test_a_direction_with_no_rationale_is_refused() -> None:
    """The rationale is what a later reader disagrees with.

    A direction with no stated reason is a number somebody typed, and the blame
    edges attached to this clause point at incidents whose lesson is precisely
    the reason.
    """
    with pytest.raises(RegistryEncodingError):
        encode(
            parameter="max_operating_pressure",
            dimension_label="pressure",
            direction=SafeDirection.LOWER_IS_SAFER,
            status=EntryStatus.RATIFIED,
            rationale="   ",
        )


def test_a_rationale_that_canonicalisation_would_collapse_is_refused() -> None:
    """Refused at encode time, because the alternative is a silent digest mismatch."""
    for bad in ("two  spaces", "a\ttab", "a\nnewline"):
        with pytest.raises(RegistryEncodingError):
            encode(
                parameter="max_operating_pressure",
                dimension_label="pressure",
                direction=SafeDirection.LOWER_IS_SAFER,
                status=EntryStatus.RATIFIED,
                rationale=bad,
            )


def test_a_malformed_parameter_key_is_refused() -> None:
    for bad in ("Max_Operating_Pressure", "max operating pressure", "ab", "9lives"):
        with pytest.raises(RegistryEncodingError):
            encode(
                parameter=bad,
                dimension_label="pressure",
                direction=SafeDirection.LOWER_IS_SAFER,
                status=EntryStatus.RATIFIED,
                rationale="reason enough",
            )


def test_an_unknown_dimension_label_is_refused() -> None:
    with pytest.raises(RegistryEncodingError):
        encode(
            parameter="max_operating_pressure",
            dimension_label="vibes",
            direction=SafeDirection.LOWER_IS_SAFER,
            status=EntryStatus.RATIFIED,
            rationale="reason enough",
        )


def test_the_decoder_is_total_or_refuses_and_never_guesses() -> None:
    """No lenient mode.  A clause that nearly matches is not nearly a registry entry."""
    good = encode(
        parameter="max_operating_pressure",
        dimension_label="pressure",
        direction=SafeDirection.LOWER_IS_SAFER,
        status=EntryStatus.RATIFIED,
        rationale="reason enough",
    )
    assert decode(good).parameter == "max_operating_pressure"

    near_misses = (
        good.replace("SAFE-DIRECTION", "SAFE DIRECTION"),
        good.replace("Parameter:", "parameter:"),
        good.replace("Direction: LOWER_IS_SAFER", "Direction: DOWNWARDS"),
        good.replace("Status: RATIFIED", "Status: APPROVED"),
        good.replace("Dimension: pressure", "Dimension: vibes"),
        good.split(" Rationale:")[0],
        "The vessel shall not exceed 50 psig.",
        "",
    )
    for text in near_misses:
        with pytest.raises(RegistryEncodingError):
            decode(text)


def test_a_rationale_cannot_forge_a_field_separator() -> None:
    """The fields before the rationale are literal, so prose cannot impersonate one."""
    text = encode(
        parameter="max_operating_pressure",
        dimension_label="pressure",
        direction=SafeDirection.LOWER_IS_SAFER,
        status=EntryStatus.RATIFIED,
        rationale="See Direction: HIGHER_IS_SAFER in the superseded revision.",
    )
    decoded = decode(text)
    assert decoded.direction is SafeDirection.LOWER_IS_SAFER
    assert "HIGHER_IS_SAFER" in decoded.rationale
