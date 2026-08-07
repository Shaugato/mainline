# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``cat_confidence='opaque'`` — the representation-failure product state.

Risk R-A3, stated as a product characteristic rather than hidden: some controls
live in tables, P&IDs, figures and cross-references that a rule-based extractor
cannot parse.  The extractor's answer is ``opaque``, which maps to
``identity_residue.reason='opaque_control'``, and any edit to an opaque clause
with severity ≥ 4 ancestry defaults to ``weaken``.  The system deliberately
over-blocks here.  These tests pin *when* it does, so the over-blocking is a
bounded, described behaviour rather than a mood.
"""

from __future__ import annotations

import pytest
from mainline_domain.cat import OPACITY_REASONS, ClauseHint, extract_cat, opacity_reason


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        # A table row that survived ingest as prose.  canon() collapses every
        # whitespace run to one space, so column gutters are gone by the time we
        # see the text and the pipe is the only in-band marker left.
        ("P-101A | 1750 kPa | 12 months", "pipe_delimited_row"),
        ("Vessel | MAWP | Test interval", "pipe_delimited_row"),
        # A bare cross-reference: the whole clause is a pointer elsewhere.
        ("See clause 7.3.2.", "bare_cross_reference"),
        ("Refer to AS 2865 Section 4.", "bare_cross_reference"),
        ("As specified in the site isolation standard.", "bare_cross_reference"),
        # The control itself is delegated to a drawing.
        ("The relief valve shall be set as shown in Figure 3.", "control_delegated_to_figure"),
        ("Isolation points shall be as detailed in Drawing 4471-A.", "control_delegated_to_figure"),
        # A row-shaped fragment: no modality, several quantities, few words.
        ("1750 kPa 12 months", "row_shaped_fragment"),
    ],
)
def test_opacity_reasons(text: str, reason: str) -> None:
    assert opacity_reason(text) == reason
    assert extract_cat(text).confidence == "opaque"


@pytest.mark.parametrize("kind", ["table_cell", "table_row"])
def test_layout_hint_beats_every_string_heuristic(kind: str) -> None:
    """A layout model's verdict is strictly better evidence than a pipe count.

    Textract's ``LAYOUT_TABLE`` knows a cell is a cell even after the gutters
    have been normalised away.  A caller that has the hint should pass it, and
    prose that reads perfectly well must still be opaque when the layout says it
    came out of a table.
    """
    text = "The maximum operating pressure shall not exceed 1750 kPa (g)."
    assert extract_cat(text).confidence == "ok"
    hinted = extract_cat(text, hint=ClauseHint(layout_kind=kind))  # type: ignore[arg-type]
    assert hinted.confidence == "opaque"
    assert opacity_reason(text, ClauseHint(layout_kind=kind)) == "layout_hint_table"  # type: ignore[arg-type]


def test_figure_caption_hint_is_opaque() -> None:
    assert (
        opacity_reason("Figure 3 - relief valve settings", ClauseHint(layout_kind="figure_caption"))
        == "layout_hint_figure"
    )


@pytest.mark.parametrize(
    "text",
    [
        "The supervisor shall verify the isolation.",
        "The pressure shall not exceed 1750 kPa (g).",
        # A citation inside a real obligation is NOT a bare cross-reference: the
        # clause carries its own modality, so the control is in the prose.
        "In accordance with AS 2865, the isolation shall be verified by a second person.",
        # A figure mentioned alongside a setpoint the clause states itself.
        "The relief valve shall be set to 1750 kPa (g) as shown in Figure 3.",
    ],
)
def test_readable_clauses_are_not_opaque(text: str) -> None:
    """Over-blocking is the correct direction of error, not a licence to over-block."""
    assert opacity_reason(text) is None
    assert extract_cat(text).confidence in ("ok", "low")


def test_opaque_result_still_carries_a_cat_and_therefore_a_key() -> None:
    """``opaque`` is not ``None``.

    "We looked and could not read it" is a different and louder fact than "there
    was nothing to look at", and only the first carries a ``cat_key`` that an
    edit to the opaque clause can be pinned to.
    """
    result = extract_cat("P-101A | 1750 kPa | 12 months")
    assert result.cat is not None
    assert result.confidence == "opaque"
    assert extract_cat("   ").cat is None


def test_every_declared_reason_is_reachable() -> None:
    """No dead reason in the catalogue: each one is produced by some input."""
    produced = {
        opacity_reason("P-101A | 1750 kPa | 12 months"),
        opacity_reason("See clause 7.3.2."),
        opacity_reason("The relief valve shall be set as shown in Figure 3."),
        opacity_reason("1750 kPa 12 months"),
        opacity_reason("anything", ClauseHint(layout_kind="table_cell")),
        opacity_reason("anything", ClauseHint(layout_kind="figure_caption")),
    }
    assert produced == set(OPACITY_REASONS)
