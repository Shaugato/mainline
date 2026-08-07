# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The disposition assistant cannot fill a field, and the check runs at import time.

§8.2's first hard prohibition and §8.4 row 5. The interesting assertion is
``test_adding_a_forbidden_field_fails_at_import_time``: adding ``defeater_code`` to the
display model does not produce a bad disposition, it produces a failed import. A
prohibition that only fires when the wrong thing is about to be written has already lost.
"""

from __future__ import annotations

import inspect
import json

import make_cassettes as recipes
import pytest
from mainline_agentkit import DISPOSITION_ASSISTANT, NARRATION, Tier, quarantined_call
from mainline_agentkit.profiles import disposition_assistant as module
from mainline_agentkit.profiles._model import (
    DISPOSITION_FORBIDDEN_TOKENS,
    CallProfile,
    Effort,
)
from mainline_agentkit.profiles._rubric import COMMON_RUBRIC
from pydantic import BaseModel, ConfigDict, Field


def test_the_profile_is_t2_and_writes_nothing_the_gate_reads():
    assert DISPOSITION_ASSISTANT.tier is Tier.T2
    assert DISPOSITION_ASSISTANT.may_write_gate_field is False
    assert DISPOSITION_ASSISTANT.describe()["tools"] == []


def test_no_output_field_could_hold_a_disposition():
    flat = json.dumps(DISPOSITION_ASSISTANT.schema.schema).lower()
    for token in sorted(DISPOSITION_FORBIDDEN_TOKENS):
        assert f'"{token}' not in flat, f"the display schema exposes a {token} field"
    assert set(DISPOSITION_ASSISTANT.schema.schema["properties"]) == {
        "precursor_summary",
        "vocabulary_terms",
        "precursor_ids",
    }


def test_the_module_exports_no_writer():
    assert set(module.__all__) == {"DISPOSITION_ASSISTANT", "DisplayOnlyText"}
    # Only symbols DEFINED here count; imported helpers belong to their own module.
    defined = {
        name: value
        for name, value in vars(module).items()
        if not name.startswith("_")
        and (inspect.isfunction(value) or inspect.isclass(value))
        and getattr(value, "__module__", None) == module.__name__
    }
    assert [name for name, value in defined.items() if inspect.isfunction(value)] == [], (
        "the disposition assistant module defines a function. §8.4 row 5: it is invoked "
        "as a pure function and returns display text; it exports no writer."
    )
    assert set(defined) == {"DisplayOnlyText"}


def test_adding_a_forbidden_field_fails_at_import_time():
    class LeakyDisplay(BaseModel):
        model_config = ConfigDict(extra="forbid")
        precursor_summary: str = Field(min_length=1)
        defeater_code: str = Field(min_length=1)

    with pytest.raises(ValueError, match="forbidden token 'defeater'"):
        CallProfile(
            profile_id="leaky",
            agent="disposition_assistant",
            tier=Tier.T2,
            effort=Effort.LOW,
            model_key="claude-opus-5",
            prompt_version="leaky.v1",
            system_blocks=(COMMON_RUBRIC,),
            max_tokens=2000,
            thinking_floor_tokens=1000,
            output_model=LeakyDisplay,
            forbidden_output_tokens=DISPOSITION_FORBIDDEN_TOKENS,
        )


def test_a_nested_forbidden_field_is_caught_too():
    class Inner(BaseModel):
        model_config = ConfigDict(extra="forbid")
        rationale_draft: str = ""

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        items: list[Inner] = Field(default_factory=list)

    with pytest.raises(ValueError, match="forbidden token 'rationale'"):
        CallProfile(
            profile_id="nested",
            agent="disposition_assistant",
            tier=Tier.T2,
            effort=Effort.LOW,
            model_key="claude-opus-5",
            prompt_version="nested.v1",
            system_blocks=(COMMON_RUBRIC,),
            max_tokens=2000,
            thinking_floor_tokens=1000,
            output_model=Outer,
            forbidden_output_tokens=DISPOSITION_FORBIDDEN_TOKENS,
        )


def test_no_profile_may_claim_a_gate_write_or_tier_zero():
    with pytest.raises(ValueError, match="may_write_gate_field"):
        CallProfile(
            profile_id="overreach",
            agent="archivist",
            tier=Tier.T1,
            effort=Effort.LOW,
            model_key="claude-opus-5",
            prompt_version="overreach.v1",
            system_blocks=(COMMON_RUBRIC,),
            max_tokens=2000,
            thinking_floor_tokens=1000,
            output_model=module.DisplayOnlyText,
            may_write_gate_field=True,
        )
    with pytest.raises(ValueError, match="tier T0"):
        CallProfile(
            profile_id="kernel",
            agent="gate",
            tier=Tier.T0,
            effort=Effort.LOW,
            model_key="claude-opus-5",
            prompt_version="kernel.v1",
            system_blocks=(COMMON_RUBRIC,),
            max_tokens=2000,
            thinking_floor_tokens=1000,
            output_model=module.DisplayOnlyText,
        )


def test_a_budget_that_leaves_no_room_for_the_answer_is_refused():
    with pytest.raises(ValueError, match="no budget is left"):
        CallProfile(
            profile_id="starved",
            agent="archivist",
            tier=Tier.T1,
            effort=Effort.LOW,
            model_key="claude-opus-5",
            prompt_version="starved.v1",
            system_blocks=(COMMON_RUBRIC,),
            max_tokens=1000,
            thinking_floor_tokens=1000,
            output_model=module.DisplayOnlyText,
        )


def test_the_call_returns_display_text_and_nothing_else(transport, model_id, sentinel, ctx_site):
    result = quarantined_call(
        DISPOSITION_ASSISTANT,
        recipes.DOC_INCIDENT,
        ctx_site,
        transport=transport,
        model_id=model_id,
        sentinel=sentinel,
    )
    assert isinstance(result.value, module.DisplayOnlyText)
    assert not hasattr(result.value, "defeater_code")
    assert not hasattr(result.value, "rationale")
    assert result.value.vocabulary_terms == [
        "different_substance",
        "control_now_engineered",
        "geometry_differs",
    ]


def test_the_narrator_cannot_propose_a_resolution(transport, model_id, sentinel, ctx_site):
    enum = NARRATION.schema.schema["properties"]["resolution_proposed"]
    assert enum.get("const") == "none" or enum.get("enum") == ["none"]
    result = quarantined_call(
        NARRATION,
        recipes.DOC_CONFLICT,
        ctx_site,
        transport=transport,
        model_id=model_id,
        sentinel=sentinel,
    )
    assert result.value.resolution_proposed == "none"
