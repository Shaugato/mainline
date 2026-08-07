# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""AR-1: written, unused, switched off — and asserted to be all three.

A pre-committed fallback is only worth having if it works on the day it is needed and
cannot arrive before then. So this suite proves both halves: the shape is correct
(forced ``tool_choice``, ``strict: true``, one turn, no ``tool_result``), and nothing in
the package reaches it without a deliberate environment variable.
"""

from __future__ import annotations

import ast
from pathlib import Path

import make_cassettes as recipes
import pytest
from mainline_agentkit import EXTRACTION, AgentkitSettings, ToolFormDisabled
from mainline_agentkit.fallback_toolform import (
    AR1_STATUS,
    build_toolform_request,
    toolform_call,
)

SRC = Path(__file__).resolve().parent.parent / "src" / "mainline_agentkit"
MODULE = "fallback_toolform"


@pytest.fixture
def enabled(cassette_dir):
    return AgentkitSettings(
        provider="cassette", cassette_dir=cassette_dir, cassette_mode="replay", ar1_enabled=True
    )


def test_it_says_what_it_is():
    assert AR1_STATUS == "written, unused"


def test_it_is_off_by_default(model_id, sentinel, ctx_site):
    with pytest.raises(ToolFormDisabled, match="MAINLINE_AR1_FALLBACK"):
        build_toolform_request(
            EXTRACTION,
            recipes.DOC_PROCEDURE,
            ctx_site,
            model_id=model_id,
            sentinel=sentinel,
        )


def test_nothing_in_the_package_imports_it():
    importers: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.stem == MODULE:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and MODULE in node.module:
                importers.append(f"{path.name}:{node.lineno}")
            elif isinstance(node, ast.Import):
                importers.extend(
                    f"{path.name}:{node.lineno}" for alias in node.names if MODULE in alias.name
                )
    assert importers == [], (
        f"{MODULE} is imported by {importers}. It is the AR-1 format fallback: a "
        "fallback that quietly becomes reachable is a capability change nobody reviewed."
    )


def test_the_package_root_does_not_re_export_it():
    import mainline_agentkit

    assert not hasattr(mainline_agentkit, "toolform_call")
    assert MODULE not in mainline_agentkit.__all__


def test_the_shape_is_a_forced_single_turn(enabled, model_id, sentinel, ctx_site):
    request = build_toolform_request(
        EXTRACTION,
        recipes.DOC_PROCEDURE,
        ctx_site,
        model_id=model_id,
        sentinel=sentinel,
        settings=enabled,
    )
    body = request.body
    tools = body["tools"]
    assert len(tools) == 1, "more than one tool would be a choice, and a choice is a loop"
    assert tools[0]["strict"] is True
    assert tools[0]["name"] == "ExtractionResult"
    # Forced: the model cannot select, cannot decline, cannot call anything else.
    assert body["tool_choice"] == {"type": "tool", "name": "ExtractionResult"}
    # One turn, and no tool_result is ever sent back, so the loop terminates here.
    assert len(body["messages"]) == 1
    assert body["messages"][0]["role"] == "user"
    # Decision A6 still applies on this path.
    assert "temperature" not in repr(body)
    assert body["thinking"] == {"type": "adaptive"}


def test_the_strict_schema_requires_every_property(enabled, model_id, sentinel, ctx_site):
    request = build_toolform_request(
        EXTRACTION,
        recipes.DOC_PROCEDURE,
        ctx_site,
        model_id=model_id,
        sentinel=sentinel,
        settings=enabled,
    )
    schema = request.body["tools"][0]["input_schema"]
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False


def test_it_validates_a_tool_use_response(enabled, transport, model_id, sentinel, ctx_site):
    result = toolform_call(
        EXTRACTION,
        recipes.DOC_PROCEDURE,
        ctx_site,
        transport=transport,
        model_id=model_id,
        settings=enabled,
        sentinel=sentinel,
    )
    assert result.stop_reason == "tool_use"
    assert result.attempts == 1
    assert len(result.value.quantities) == 3
    assert result.value.quantities[0].value_milli == 19500
