# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The structural quarantine, asserted three ways.

Layer 1 of the six-layer posture (§8.4) is not a rule about how to call the model — it
is the shape of the call. These tests are what make that sentence checkable:

1. ``quarantined_call`` has no ``tools`` parameter and no ``tool_choice`` parameter;
2. no module in this package constructs a tool surface, except the one AR-1 module that
   exists for it and is exempted **by exact path**;
3. the runtime guard refuses a body that carries one anyway.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from mainline_agentkit import (
    EXTRACTION,
    TRIAGE,
    ToolSurfaceConstructed,
    UntrustedText,
    assert_no_tool_surface,
    build_request,
    quarantined_call,
    warm_then_fanout,
)
from mainline_agentkit.transport import BANNED_TOOL_KEYS

SRC = Path(__file__).resolve().parent.parent / "src" / "mainline_agentkit"

#: The one module permitted to construct a tool surface. Exempted by exact path, never
#: by pattern — see fallback_toolform's module docstring.
AR1_EXEMPT = SRC / "fallback_toolform.py"

FORBIDDEN_PARAMETERS = {"tools", "tool_choice", "toolConfig", "toolchoice", "tool_config"}


@pytest.mark.parametrize("function", [quarantined_call, warm_then_fanout, build_request])
def test_no_tool_parameter_in_the_public_call_path(function):
    names = {name.lower() for name in inspect.signature(function).parameters}
    assert not (names & FORBIDDEN_PARAMETERS), (
        f"{function.__name__} grew a tool parameter: {sorted(names & FORBIDDEN_PARAMETERS)}. "
        "That absence IS the CaMeL quarantine (ARCHITECTURE.md §8.4 layer 1)."
    )


def test_quarantined_call_signature_is_exactly_the_documented_shape():
    signature = inspect.signature(quarantined_call)
    positional = [
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]
    assert positional == ["profile", "untrusted", "trusted_context"]
    assert set(signature.parameters) == {
        "profile",
        "untrusted",
        "trusted_context",
        "transport",
        "model_id",
        "settings",
        "sentinel",
    }


def _tool_surface_sites(path: Path) -> list[str]:
    """Every place in ``path`` that builds a ``tools``-shaped key or kwarg."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sites: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if not isinstance(key, ast.Constant) or key.value not in BANNED_TOOL_KEYS:
                    continue
                # Declaring `"tools": []` is the OPPOSITE of constructing a tool
                # surface: it is the fleet register stating that this agent holds none.
                if isinstance(value, ast.List) and not value.elts:
                    continue
                sites.append(f"{path.name}:{key.lineno} dict key {key.value!r}")
        elif isinstance(node, ast.keyword) and node.arg in BANNED_TOOL_KEYS:
            sites.append(f"{path.name}:{node.lineno} keyword {node.arg}=")
    return sites


def test_no_module_constructs_a_tool_surface():
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path == AR1_EXEMPT:
            continue
        offenders.extend(_tool_surface_sites(path))
    assert offenders == [], (
        f"a module outside the AR-1 fallback constructs a tool surface: {offenders}"
    )


def test_the_ar1_module_is_the_one_that_does_construct_one():
    # A negative test that never fires against anything is a test that has stopped
    # asserting. This is the positive control for the scan above.
    assert _tool_surface_sites(AR1_EXEMPT), (
        "fallback_toolform no longer builds a tool surface, so the scan above has "
        "nothing to exempt and no longer proves anything"
    )


def test_built_body_carries_no_tool_key(model_id, sentinel, ctx_site):
    document = UntrustedText(text="4.2 Test the atmosphere.", source_sha256="0" * 64)
    for profile in (TRIAGE, EXTRACTION):
        request = build_request(profile, document, ctx_site, model_id=model_id, sentinel=sentinel)
        assert not (set(request.body) & BANNED_TOOL_KEYS)
        assert_no_tool_surface(request.body)


def test_runtime_guard_refuses_a_tool_surface_at_any_depth():
    with pytest.raises(ToolSurfaceConstructed) as top:
        assert_no_tool_surface({"tools": [{"name": "x"}]})
    assert top.value.field == "tools"

    with pytest.raises(ToolSurfaceConstructed) as nested:
        assert_no_tool_surface({"messages": [{"content": [{"tool_choice": {"type": "any"}}]}]})
    assert nested.value.path == "messages[0].content[0].tool_choice"


def test_a_schema_property_named_tools_is_not_a_tool_surface():
    # The guard must fire on the request, not on the corpus. A document model with a
    # field called `tools` is a mining procedure listing hand tools.
    assert_no_tool_surface(
        {
            "output_config": {
                "format": {"schema": {"properties": {"tools": {"type": "array"}}}},
            }
        }
    )
