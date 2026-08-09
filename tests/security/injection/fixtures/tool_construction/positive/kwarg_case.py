# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A tool surface passed as a keyword argument, plus a forced ``tool_choice``.

The AR-1 shape without AR-1's exemption: this is what the fallback would look like if
someone copied it into an ingest package. It MUST make the AST scan fail.
"""

from __future__ import annotations

from typing import Any


def invoke(client: Any, prompt: str) -> Any:
    """Call a model with a forced tool. Exactly the thing layer 1 forbids in ingest."""
    return client.invoke_model(
        modelId="au.anthropic.claude-opus-5",
        messages=[{"role": "user", "content": prompt}],
        tools=[{"name": "sign_disposition", "input_schema": {"type": "object"}}],
        tool_choice={"type": "tool", "name": "sign_disposition"},
    )


def with_mcp(client: Any, prompt: str) -> Any:
    """The MCP variant of the same mistake."""
    return client.invoke_model(
        modelId="au.anthropic.claude-opus-5",
        messages=[{"role": "user", "content": prompt}],
        mcp_servers=[{"type": "url", "url": "https://cockroachlabs.cloud/mcp"}],
    )
