# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The symmetry that makes cosine mean something: one facet-definitions block, two sides.

If the event side and the permit side drift apart in what ``mechanism`` means, nothing
raises.  The vectors keep being produced, the searches keep returning results, the scores
keep looking like scores — and the system quietly goes back to retrieving documents written
the same way.  The byte-for-byte assertion below is the only thing standing between us and
that outcome, which is why it is a test rather than a convention.
"""

from __future__ import annotations

from fixtures import (
    ASSET_CLASS_CRUSHER,
    ASSET_CLASS_TYRE,
    DIFF_EXPOSED,
    EVENT_FULL,
    ISOLATION_EXPOSED,
    PERMIT_EXPOSED,
)
from mainline_recall_agent.cue.prompts import (
    FACET_DEFINITIONS,
    PROMPT_VERSION,
    build_event_prefix,
    build_exposure_prefix,
    event_payload,
    exposure_payload,
)
from mainline_recall_agent.cue.schema import SYNTHESISED_FACETS, FacetSynthesis
from mainline_recall_agent.cue.source_text import (
    event_source_document,
    exposure_source_document,
)
from mainline_recall_agent.providers.schema import output_config, to_strict_json_schema


def test_both_prompts_share_the_facet_definitions_block_byte_for_byte() -> None:
    event = build_event_prefix()
    exposure = build_exposure_prefix()
    event_block = next(b for b in event.blocks if b.label == "facet_definitions")
    exposure_block = next(b for b in exposure.blocks if b.label == "facet_definitions")
    assert event_block.text == exposure_block.text
    assert event_block.text == FACET_DEFINITIONS
    assert event_block.text.encode("utf-8") == exposure_block.text.encode("utf-8")


def test_the_shared_block_comes_first_in_both_prefixes() -> None:
    """Shared bytes first is the only ordering under which a second cache breakpoint helps.

    Honest scope: ``SystemPrefix.wire()`` emits exactly one breakpoint, on the last block,
    so today the two sides are two cache entries that share an opening block rather than one
    shared cached segment.  The ordering costs nothing now and the reverse forecloses the
    improvement, so it is pinned here rather than left to whoever edits the file next.
    """
    for prefix in (build_event_prefix(), build_exposure_prefix()):
        assert [block.label for block in prefix.blocks] == [
            "facet_definitions",
            "rubric",
            "examples",
        ]


def test_the_two_rubrics_are_not_the_same_block() -> None:
    """Symmetry is in the definitions, not in the instructions: the inputs differ."""
    event = build_event_prefix()
    exposure = build_exposure_prefix()
    event_rubric = next(b for b in event.blocks if b.label == "rubric").text
    exposure_rubric = next(b for b in exposure.blocks if b.label == "rubric").text
    assert event_rubric != exposure_rubric
    assert event.prefix_digest() != exposure.prefix_digest()


def test_the_cached_prefix_carries_exactly_one_breakpoint_on_the_last_block() -> None:
    for prefix in (build_event_prefix(), build_exposure_prefix()):
        wire = prefix.wire()
        marked = [i for i, block in enumerate(wire) if "cache_control" in block]
        assert marked == [len(wire) - 1]
        assert prefix.likely_cacheable, "prefix fell below the vendor's cacheable minimum"


def test_the_prefix_contains_no_per_request_content() -> None:
    """``SystemPrefix`` refuses volatile blocks; constructing both is the assertion.

    A UUID, a timestamp or a format placeholder that crept into the rubric would break the
    cache on every call in the fleet, and nobody would notice until the bill did.
    """
    assert build_event_prefix().prompt_version == PROMPT_VERSION
    assert build_exposure_prefix().prompt_version == PROMPT_VERSION


def test_both_payloads_have_identical_shape() -> None:
    """A payload that differs in shape is a prompt that differs in kind."""
    event_doc = event_source_document(EVENT_FULL)
    exposure_doc = exposure_source_document(PERMIT_EXPOSED, ISOLATION_EXPOSED, DIFF_EXPOSED)
    left = event_payload(event_doc, activity_path="a / b", asset_class=ASSET_CLASS_TYRE)
    right = exposure_payload(exposure_doc, activity_path="a / b", asset_class=ASSET_CLASS_CRUSHER)
    assert set(left) == set(right)
    assert set(left["source_document"]) == set(right["source_document"])
    assert left["populate_facets"] == right["populate_facets"] == list(SYNTHESISED_FACETS)
    assert left["task"] == "event_cue"
    assert right["task"] == "exposure_cue"


def test_both_sides_declare_the_same_strict_output_schema() -> None:
    """One schema, or the two sides are not producing the same kind of object."""
    schema = to_strict_json_schema(FacetSynthesis)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(SYNTHESISED_FACETS)
    for definition in schema["$defs"].values():
        assert definition["additionalProperties"] is False
    config = output_config(FacetSynthesis)
    assert config["format"]["strict"] is True
    assert config["format"]["name"] == "FacetSynthesis"


def test_every_declared_property_is_required() -> None:
    """Strict mode requires it, and so does the escape.

    A field the model may omit is a field whose absence and whose emptiness are
    indistinguishable — at exactly the point where that distinction is the feature.
    """
    facet_schema = to_strict_json_schema(FacetSynthesis)["$defs"]["FacetAnswer"]
    assert set(facet_schema["required"]) == set(facet_schema["properties"])
    assert set(facet_schema["properties"]) == {
        "cue_text",
        "evidence_quote",
        "insufficient",
        "insufficient_reason",
    }
