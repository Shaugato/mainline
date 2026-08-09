# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The vocabulary the corpus and the controls share: layers, attack classes, outcomes.

Three enumerations, and the reason all three are enumerations rather than strings is
the same: **a corpus case asserts a NAMED outcome**, not "an exception was raised". A
test that only proves something went wrong cannot tell a reviewer whether the right
control fired, and in a six-layer posture the identity of the layer that caught an
attack is most of the information.

:class:`Layer` is written in FIRING order, which is not the same as defence-in-depth
order and is worth saying out loud. Layer 5 (capability starvation) is numbered fifth in
ARCHITECTURE.md 8.4 but is a **precondition**, not a stage: a process that discovers it
holds the wrong SQL role after it has already read the attacker's bytes has discovered
it too late. :func:`mainline_quarantine.pipeline.intake` therefore evaluates the
capability guard first and says so, and :data:`FIRING_ORDER` records the temporal
sequence separately from the numbering.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

__all__ = [
    "FIRING_ORDER",
    "OUTCOME_LAYER",
    "AttackClass",
    "Layer",
    "Outcome",
]


class Layer(StrEnum):
    """The six layers of ARCHITECTURE.md 8.4, by their numbers in that section."""

    L1_STRUCTURAL_QUARANTINE = "L1_structural_quarantine"
    L2_DELIMIT_AND_DATAMARK = "L2_delimit_and_datamark"
    L3_OUTPUT_SCHEMA_CONTAINMENT = "L3_output_schema_containment"
    L4_SEMANTIC_ANCHORING = "L4_semantic_anchoring"
    L5_CAPABILITY_STARVATION = "L5_capability_starvation"
    L6_INJECTION_IS_EVIDENCE = "L6_injection_is_evidence"


#: The order in which the controls actually run, which differs from the numbering.
#:
#: L5 first: capability starvation is a property of the process, checked before the
#: process is allowed to read anything. L1 is not in this tuple at all because it is not
#: a step — it is the shape of :func:`mainline_agentkit.call.quarantined_call`, proved by
#: ``scripts/agents/assert_no_tool_construction.py`` over the whole tree rather than by a
#: branch at run time. L6 is last because it is what every other layer writes into.
FIRING_ORDER: Final[tuple[Layer, ...]] = (
    Layer.L5_CAPABILITY_STARVATION,
    Layer.L2_DELIMIT_AND_DATAMARK,
    Layer.L3_OUTPUT_SCHEMA_CONTAINMENT,
    Layer.L4_SEMANTIC_ANCHORING,
    Layer.L6_INJECTION_IS_EVIDENCE,
)


class AttackClass(StrEnum):
    """The named hostile-document classes the committed corpus covers.

    Named classes rather than a bag of documents, because "40 hostile PDFs" is a number
    and "four independent ways of forging an equipment tag, each refused by a different
    control" is an argument. Every file under ``tests/security/injection/corpus/``
    declares exactly one of these, and a corpus test fails if any class is empty — a
    class with no case is a claim with no evidence.
    """

    DIRECT_INSTRUCTION_OVERRIDE = "direct_instruction_override"
    ROLE_PLAY_FRAMING = "role_play_framing"
    ENCODED_PAYLOAD = "encoded_payload"
    HOMOGLYPH_INJECTION = "homoglyph_injection"
    ZERO_WIDTH_INJECTION = "zero_width_injection"
    FAKE_SYSTEM_REMINDER = "fake_system_reminder"
    TOOL_NAME_MENTION = "tool_name_mention"
    CREDENTIAL_EXFILTRATION = "credential_exfiltration"
    SEVERITY_INFLATION = "severity_inflation"
    SEVERITY_DEFLATION = "severity_deflation"
    FORGED_EQUIPMENT_TAG = "forged_equipment_tag"
    PDF_TABLE_CELL = "pdf_table_cell"


class Outcome(StrEnum):
    """What a control did with a document, as a corpus case asserts it.

    ``VALUE_ONLY_DISTORTION`` is the honest residual and the reason this enumeration is
    not a list of successes. It means: no layer refused, and the most an attacker
    achieved was a wrong value in a field the schema already declared. That is a defect
    in the record, routed to a human by layer 6 — it is not a clean document.
    """

    CLEAN = "clean"
    CAPABILITY_REFUSED = "capability_refused"
    BLOCKED_PROMPT_ATTACK = "blocked_prompt_attack"
    FLAGGED_OBFUSCATION = "flagged_obfuscation"
    CONTAINED_UNKNOWN_FIELD = "contained_unknown_field"
    CONTAINED_TYPE_VIOLATION = "contained_type_violation"
    ANCHOR_REJECTED = "anchor_rejected"
    VALUE_ONLY_DISTORTION = "value_only_distortion"


#: Which layer produces which outcome. A corpus case that names an outcome has
#: therefore also named the layer, and a test asserts the two agree — so a case cannot
#: silently start passing because a *different* control caught it.
OUTCOME_LAYER: Final[dict[Outcome, Layer | None]] = {
    Outcome.CLEAN: None,
    Outcome.CAPABILITY_REFUSED: Layer.L5_CAPABILITY_STARVATION,
    Outcome.BLOCKED_PROMPT_ATTACK: Layer.L2_DELIMIT_AND_DATAMARK,
    Outcome.FLAGGED_OBFUSCATION: Layer.L2_DELIMIT_AND_DATAMARK,
    Outcome.CONTAINED_UNKNOWN_FIELD: Layer.L3_OUTPUT_SCHEMA_CONTAINMENT,
    Outcome.CONTAINED_TYPE_VIOLATION: Layer.L3_OUTPUT_SCHEMA_CONTAINMENT,
    Outcome.ANCHOR_REJECTED: Layer.L4_SEMANTIC_ANCHORING,
    Outcome.VALUE_ONLY_DISTORTION: Layer.L3_OUTPUT_SCHEMA_CONTAINMENT,
}
