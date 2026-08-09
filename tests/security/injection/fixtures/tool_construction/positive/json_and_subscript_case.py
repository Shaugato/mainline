# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Two more ways to build a tool surface without writing a Python dict literal.

A JSON body in a string literal, a subscript assignment onto an existing body, and a
module-level binding that *defines* a tool list. All three MUST make the AST scan fail;
the third is the one the same-name-derivation exception deliberately does not cover.
"""

from __future__ import annotations

import json
from typing import Any

RAW_BODY = """
{
  "anthropic_version": "bedrock-2023-05-31",
  "max_tokens": 512,
  "tools": [{"name": "merge_permit", "input_schema": {"type": "object"}}]
}
"""

tools = [{"name": "suspend_permit", "input_schema": {"type": "object"}}]


def from_json() -> dict[str, Any]:
    """Parse a request body that already carries tools."""
    parsed: dict[str, Any] = json.loads(RAW_BODY)
    return parsed


def bolt_on(body: dict[str, Any]) -> dict[str, Any]:
    """Attach a tool surface to a body that did not have one."""
    body["tool_choice"] = {"type": "any"}
    return body
