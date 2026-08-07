# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Golden vectors for ``bedrock_schema`` (decision A7).

The load-bearing assertion is the first one: **the stripped keyword set is exactly this
set**. A platform change that starts supporting ``maxLength``, or that starts rejecting
something we currently keep, must break a test rather than silently change a control —
because the control here is a promise about a safety record ("cues are at most 60
tokens"), and an unenforced promise in a safety record is worse than an absent one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest
from mainline_agentkit import (
    OPTIONAL_STRIPPED_KEYWORDS,
    PROFILES,
    STRIPPED_KEYWORDS,
    UnsupportedSchema,
    bedrock_schema,
)
from pydantic import BaseModel, ConfigDict, Field

GOLDEN = Path(__file__).resolve().parent / "golden" / "stripped_schema.json"

EXPECTED_STRIPPED = {
    "exclusiveMaximum",
    "exclusiveMinimum",
    "maxItems",
    "maxLength",
    "maximum",
    "minItems",
    "minLength",
    "minimum",
    "multipleOf",
    "uniqueItems",
}


class GoldenLeaf(BaseModel):
    """Exercises every stripped keyword in one place."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=2, max_length=24)
    reading_milli: int = Field(ge=-1000, le=1000, multiple_of=5)
    strictly_between: int = Field(gt=0, lt=100)
    tags: list[str] = Field(default_factory=list, min_length=1, max_length=3)
    unique_codes: set[str] = Field(default_factory=set)
    kind: Literal["a", "b"] = "a"


class GoldenVector(BaseModel):
    """The golden model. Its JSON Schema is committed under ``tests/golden``."""

    model_config = ConfigDict(extra="forbid")

    leaves: list[GoldenLeaf] = Field(default_factory=list, max_length=4)
    optional_note: str | None = Field(default=None, max_length=40)


class SelfReferential(BaseModel):
    """A recursive model. Refused, never truncated."""

    model_config = ConfigDict(extra="forbid")

    name: str
    child: SelfReferential | None = None


def test_the_stripped_keyword_set_is_exactly_this():
    assert set(STRIPPED_KEYWORDS) == EXPECTED_STRIPPED
    assert set(OPTIONAL_STRIPPED_KEYWORDS) == {"pattern"}


def test_golden_vector_schema_matches_the_committed_file():
    built = bedrock_schema(GoldenVector)
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert built.schema == expected["schema"]
    assert built.schema_version == expected["schema_version"]
    assert [
        {"pointer": c.pointer, "keyword": c.keyword, "value": c.value, "checkable": c.checkable}
        for c in built.stripped
    ] == expected["stripped"]


def test_every_stripped_keyword_is_actually_exercised_by_the_golden_model():
    built = bedrock_schema(GoldenVector)
    assert {c.keyword for c in built.stripped} == EXPECTED_STRIPPED, (
        "the golden model no longer exercises every stripped keyword, so the vector "
        "stopped proving the strip happens"
    )


def test_no_stripped_keyword_survives_into_the_wire_schema():
    for profile in PROFILES.values():
        flat = json.dumps(profile.schema.schema)
        for keyword in EXPECTED_STRIPPED:
            assert f'"{keyword}"' not in flat, f"{profile.profile_id} leaked {keyword}"


def test_every_object_forbids_additional_properties():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" or "properties" in node:
                assert node.get("additionalProperties") is False, node.get("title")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for profile in PROFILES.values():
        walk(profile.schema.schema)


def test_refs_are_inlined_and_defs_removed():
    built = bedrock_schema(GoldenVector)
    flat = json.dumps(built.schema)
    assert "$ref" not in flat
    assert "$defs" not in flat
    leaf = built.schema["properties"]["leaves"]["items"]
    assert leaf["title"] == "GoldenLeaf"
    assert leaf["additionalProperties"] is False


def test_recursion_is_refused_not_truncated():
    with pytest.raises(UnsupportedSchema, match="recursive schema"):
        bedrock_schema(SelfReferential)


def test_stripped_constraints_are_re_imposed_independently_of_pydantic():
    built = bedrock_schema(GoldenVector)
    payload = {
        "leaves": [
            {
                "label": "x",  # minLength 2
                "reading_milli": 5000,  # maximum 1000
                "strictly_between": 0,  # exclusiveMinimum 0
                "tags": [],  # minItems 1
                "unique_codes": ["dup", "dup"],  # uniqueItems
                "kind": "a",
            }
        ],
        "optional_note": None,
    }
    complaints = built.check_stripped(payload)
    joined = " | ".join(complaints)
    assert "minLength" in joined
    assert "maximum" in joined
    assert "exclusiveMinimum" in joined
    assert "minItems" in joined
    assert "duplicate items" in joined


def test_a_conforming_payload_produces_no_complaints():
    built = bedrock_schema(GoldenVector)
    payload = {
        "leaves": [
            {
                "label": "oxygen",
                "reading_milli": 500,
                "strictly_between": 50,
                "tags": ["confined_space"],
                "unique_codes": ["THK3", "PU-4021"],
                "kind": "b",
            }
        ],
        "optional_note": "fine",
    }
    assert built.check_stripped(payload) == ()
    assert built.validate_payload(payload, profile_id="golden").leaves[0].label == "oxygen"


def test_constraints_under_a_union_are_recorded_but_not_double_checked():
    built = bedrock_schema(GoldenVector)
    under_union = [c for c in built.stripped if not c.checkable]
    assert under_union, "optional_note's maxLength sits under an anyOf and must be recorded"
    assert all(c.keyword == "maxLength" for c in under_union)


def test_require_all_properties_is_off_by_default_and_available_for_strict_tool_form():
    lenient = bedrock_schema(GoldenVector)
    strict = bedrock_schema(GoldenVector, require_all_properties=True)
    assert set(strict.schema["required"]) == {"leaves", "optional_note"}
    assert set(lenient.schema.get("required", [])) != set(strict.schema["required"])


def test_pattern_is_kept_by_default_and_strippable_by_flag():
    class Patterned(BaseModel):
        model_config = ConfigDict(extra="forbid")
        tag: str = Field(pattern=r"^[A-Z]{2,4}-\d{3,5}$")

    kept = bedrock_schema(Patterned)
    assert "pattern" in json.dumps(kept.schema)
    stripped = bedrock_schema(Patterned, strip_pattern=True)
    assert "pattern" not in json.dumps(stripped.schema)
    assert stripped.check_stripped({"tag": "nope"})
    assert stripped.check_stripped({"tag": "PU-4021"}) == ()
