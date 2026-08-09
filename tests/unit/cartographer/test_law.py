# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The laws this package cannot be talked out of.

`inference_never_blocks` is a CHECK constraint in the DDL, which is the enforcement.
These tests assert the two *additional* places the same law holds: the type cannot be
constructed in violation of it, and the statement builder cannot express a violation of
it. Three independent refusals for one rule, because the rule is the one that keeps a
model error from becoming a rubber stamp.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest
from corpus import CLAUSE_ISOLATION, COMMIT_HEX, FATALITY_ID, SITE
from mainline_agentkit import quarantined_call
from mainline_cartographer import (
    BLAME_LINK,
    INSERT_BLAME_EDGE_SQL,
    BlameBasis,
    BlameState,
    FloatInEvidentiaryPayload,
    InferenceActivated,
    ProvisionalBlameEdge,
    assert_float_free,
    insert_blame_edge,
)

UNTIL = datetime(2026, 12, 1, tzinfo=UTC)


def an_edge(**overrides) -> ProvisionalBlameEdge:
    payload = {
        "event_id": FATALITY_ID,
        "clause_uuid": CLAUSE_ISOLATION,
        "site_id": SITE,
        "commit_id": COMMIT_HEX,
        "p_link_milli": 800,
        "features": {"link_kind": "control_named", "p_link_milli": 800},
        "attribution": "Proposed link, high confidence. PROVISIONAL.",
        "evidence_span": (10, 40),
        "evidence_quote_sha256": "ab" * 32,
        "provisional_until": UNTIL,
        "model_id": "au.anthropic.claude-opus-5",
        "prompt_version": "blame_link.v1+rubric.v1",
    }
    payload.update(overrides)
    return ProvisionalBlameEdge(**payload)


def test_an_inferred_edge_cannot_be_constructed_active():
    with pytest.raises(InferenceActivated):
        an_edge(state=BlameState.ACTIVE)


def test_this_type_cannot_carry_another_basis():
    with pytest.raises(InferenceActivated):
        an_edge(basis=BlameBasis.ASSERTED_DOCUMENT)


def test_the_statement_builder_refuses_an_edge_forced_active_through_a_back_door():
    edge = an_edge()
    object.__setattr__(edge, "state", BlameState.ACTIVE)
    with pytest.raises(InferenceActivated):
        insert_blame_edge(edge)


def test_state_and_basis_are_literals_in_the_statement_not_parameters():
    """A parameter is a value a caller chooses; a literal is a value nobody chooses."""
    assert "'inferred_semantic'" in INSERT_BLAME_EDGE_SQL
    assert "'provisional'" in INSERT_BLAME_EDGE_SQL
    assert "'active'" not in INSERT_BLAME_EDGE_SQL


def test_p_link_reaches_the_wire_as_an_exact_decimal_never_a_float():
    _sql, params = insert_blame_edge(an_edge(p_link_milli=500))
    p_link = params[4]
    assert not isinstance(p_link, float)
    assert str(p_link) == "0.500"


def test_a_certainty_nobody_inferred_is_refused():
    with pytest.raises(ValueError, match="p_link_milli"):
        an_edge(p_link_milli=1000)
    with pytest.raises(ValueError, match="p_link_milli"):
        an_edge(p_link_milli=0)


def test_a_float_in_features_is_refused_because_the_row_is_hashed():
    with pytest.raises(FloatInEvidentiaryPayload):
        an_edge(features={"p_link": 0.8})


def test_float_free_check_walks_nested_structures():
    assert_float_free({"a": [1, {"b": True}], "c": "text"})
    with pytest.raises(FloatInEvidentiaryPayload) as caught:
        assert_float_free({"a": [1, {"b": 2.5}]})
    assert caught.value.path == "$.a[1].b"


def test_an_empty_attribution_is_refused():
    """The DDL comment: prose a human is shown, never a bare number."""
    with pytest.raises(ValueError, match="attribution"):
        an_edge(attribution="   ")


def test_the_blame_link_call_has_no_tool_surface():
    """Layer 1 is a call shape, not a convention about how to use one."""
    parameters = inspect.signature(quarantined_call).parameters
    assert "tools" not in parameters
    assert "tool_choice" not in parameters
    assert BLAME_LINK.describe()["tools"] == []


def test_the_proposal_schema_exposes_no_field_a_model_could_decide_with():
    """No severity, no likelihood, no state, no disposition — checked, not remembered."""
    properties = set(_property_names(BLAME_LINK.schema.schema))
    forbidden = {"severity", "rationale", "disposition", "state", "clearance", "defeater"}
    for name in properties:
        assert not any(token in name.lower() for token in forbidden), name
    # The two identity fields the model must not be able to invent are equally absent.
    assert "clause_uuid" not in properties
    assert "event_id" not in properties


def test_the_profile_is_tier_one_and_cannot_write_a_gate_field():
    assert str(BLAME_LINK.tier) == "T1"
    assert BLAME_LINK.may_write_gate_field is False
    assert BLAME_LINK.agent == "cartographer"


def _property_names(schema):
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, sub in properties.items():
            yield str(name)
            if isinstance(sub, dict):
                yield from _property_names(sub)
    items = schema.get("items")
    if isinstance(items, dict):
        yield from _property_names(items)
    for key in ("anyOf", "oneOf", "allOf"):
        for branch in schema.get(key) or ():
            if isinstance(branch, dict):
                yield from _property_names(branch)
