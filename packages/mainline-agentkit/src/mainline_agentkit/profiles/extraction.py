# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Extraction — quote-or-abstain CAT and quantity extraction, at ``effort: low``.

Pass 2 of the CAT pipeline (§8.6 I1). Pass 1 is deterministic; this call is the second
opinion, and a verifier downstream *hard-rejects* any numeric, unit or comparator
disagreement between the two. That is why the schema below is shaped the way it is:
every quantity carries the span it came from, and *we* compute the offsets by exact
string search into ``canon_text``. **We never trust a model-reported offset.**

Quantities are integer milli-units plus a unit symbol, never decimals. Two reasons, both
load-bearing: the record is hashed and IEEE-754 has no stable byte form (see
:mod:`mainline_agentkit._canon`), and a comparator lattice over rationals is exact where
a lattice over floats is a source of silent weakenings.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._model import CallProfile, Effort, Tier
from ._rubric import COMMON_RUBRIC, RUBRIC_VERSION

__all__ = ["EXTRACTION", "ExtractedQuantity", "ExtractionResult"]

_TASK = """\
TASK: CONDITION-ACTION-TRIGGER AND QUANTITY EXTRACTION

A deterministic pass has already run over this text. Your output is a second, \
independent reading, and a verifier compares the two: any disagreement about a number, \
a unit or a comparator causes BOTH readings to be rejected and the clause to be routed \
to a human. You therefore gain nothing by agreeing with what you think the first pass \
found, and you lose nothing by abstaining.

quantities
  Every measurable threshold, limit, setpoint, interval or duration the text states as \
a requirement. Not every number: a page number, a document revision, a phone number, a \
tag number and a date are not quantities. A quantity is something a person could be \
measured against.

  value_milli   The value multiplied by one thousand, as an integer. 19.5 % becomes \
19500. 2 metres becomes 2000. 30 minutes becomes 30000 with unit "min". Negative values \
are permitted. If the multiplication would lose precision, abstain on that quantity.
  unit          The SI or plant symbol exactly as a machine would write it: "m", "mm", \
"%", "ppm", "min", "h", "kPa", "degC", "V", "A", "kg", "L", "m3", "lx", "dB". If the \
text uses a unit outside this vocabulary, copy the text's own symbol.
  comparator    "lt" (less than), "lte" (at most, not exceeding, maximum), "eq" \
(exactly, shall be), "gte" (at least, minimum, no less than), "gt" (greater than), \
"between" (a range; emit the lower bound as this quantity and the upper bound as a \
second quantity), "none" (a bare stated value with no relational sense).
  quantity_kind A short lowercase underscored name for what is measured: \
oxygen_concentration, h2s_concentration, gas_test_interval, harness_anchor_height, \
isolation_verification_interval, minimum_illuminance, maximum_wind_speed.
  quote         The verbatim span containing the number AND its comparator words. Not \
the number alone: "at least 19.5 %" carries information "19.5 %" does not.

anchors
  Hard anchors present in the text, copied verbatim: equipment tags (PU-4021, \
VLV-119A), regulatory citations (WHS Reg 2011 s.49, AS/NZS 2865), CAS numbers \
(7783-06-4), standard numbers, and substance names. These are checked against the \
document's own extracted anchor set before anything is inserted, so an anchor you did \
not read in the text will cause the whole extraction to be discarded.

abstained / abstain_reason
  "no_quantity"         the text states no measurable requirement. Common and correct.
  "ambiguous_unit"      a number whose unit cannot be determined from the text.
  "conflicting_values"  the text states two different values for the same thing.
  "none"                only when abstained is false.
"""

_SYSTEM = (COMMON_RUBRIC, _TASK)

_MILLI_BOUND = 1_000_000_000


class ExtractedQuantity(BaseModel):
    """One measurable requirement, in integer milli-units, with the span it came from."""

    model_config = ConfigDict(extra="forbid")

    quantity_kind: str = Field(
        min_length=1, max_length=64, description="Lowercase underscored name of what is measured."
    )
    value_milli: int = Field(
        ge=-_MILLI_BOUND,
        le=_MILLI_BOUND,
        description="The value times one thousand, as an integer. Never a decimal.",
    )
    unit: str = Field(min_length=1, max_length=32, description="SI or plant unit symbol.")
    comparator: Literal["lt", "lte", "eq", "gte", "gt", "between", "none"] = Field(
        description="Named comparator; never a symbol."
    )
    quote: str = Field(
        min_length=1,
        max_length=400,
        description="Verbatim span containing the number and its comparator words.",
    )


class ExtractionResult(BaseModel):
    """The second, independent reading of one clause."""

    model_config = ConfigDict(extra="forbid")

    abstained: bool = Field(description="True when no reliable extraction was possible.")
    abstain_reason: Literal["no_quantity", "ambiguous_unit", "conflicting_values", "none"] = Field(
        description="Why the extraction abstained; 'none' when it did not."
    )
    anchors: list[str] = Field(
        default_factory=list,
        max_length=32,
        description="Verbatim hard anchors: tags, citations, CAS numbers, substances.",
    )
    quantities: list[ExtractedQuantity] = Field(
        default_factory=list, max_length=16, description="Measurable requirements found."
    )


EXTRACTION: CallProfile[ExtractionResult] = CallProfile(
    profile_id="extraction",
    agent="archivist",
    tier=Tier.T1,
    effort=Effort.LOW,
    model_key="claude-opus-5",
    prompt_version=f"extraction.v1+{RUBRIC_VERSION}",
    system_blocks=_SYSTEM,
    # Sixteen quantities with quotes is a large object, and adaptive thinking runs
    # first. 8000 is the committed budget for both.
    max_tokens=8000,
    thinking_floor_tokens=4000,
    output_model=ExtractionResult,
)
