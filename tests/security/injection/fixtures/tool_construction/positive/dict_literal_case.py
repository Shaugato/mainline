# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A deliberately-added tool surface. This file MUST make the AST scan fail.

PL-2: a scanner that has never been red asserts nothing. Nothing imports this module and
it lives outside every scanned package root, so it reaches the scanner only when
``tests/security/injection/test_layers.py`` points ``--root`` at this directory.
"""

from __future__ import annotations

from typing import Any


def build_body(prompt: str) -> dict[str, Any]:
    """The shape `quarantined_call` refuses to have: a request body carrying tools."""
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [
            {
                "name": "write_blocking_check",
                "description": "materialise a blocking check on a permit",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
    }
