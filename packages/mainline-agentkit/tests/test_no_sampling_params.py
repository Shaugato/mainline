# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Decision A6: no sampling parameter, anywhere, ever.

``temperature``/``top_p``/``top_k`` return 400 on this model generation, and the honest
claim was never reproducibility (§8.2) — it is *replayability* plus *arithmetic
reproducibility*. **A parameter that cannot exist cannot be blamed for drift.**

The grep is an AST walk rather than a text search on purpose: a text search cannot tell
the ban list from a violation, and a ban list that has to be exempted by regex is a ban
list one refactor away from exempting the thing it bans.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from mainline_agentkit import (
    PROFILES,
    ForbiddenRequestField,
    UntrustedText,
    assert_no_sampling_params,
    build_request,
)
from mainline_agentkit.transport import BANNED_SAMPLING_KEYS

SRC = Path(__file__).resolve().parent.parent / "src" / "mainline_agentkit"


def _sampling_sites(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    sites: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            sites.extend(
                f"{path.name}:{key.lineno} dict key {key.value!r}"
                for key in node.keys
                if isinstance(key, ast.Constant) and key.value in BANNED_SAMPLING_KEYS
            )
        elif isinstance(node, ast.keyword) and node.arg in BANNED_SAMPLING_KEYS:
            sites.append(f"{path.name}:{node.lineno} keyword {node.arg}=")
    return sites


def test_no_module_sets_a_sampling_parameter():
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        offenders.extend(_sampling_sites(path))
    assert offenders == [], f"a sampling parameter is constructed somewhere: {offenders}"


@pytest.mark.parametrize("profile_id", sorted(PROFILES))
def test_every_profile_builds_a_body_with_no_sampling_parameter(
    profile_id, model_id, sentinel, ctx_site
):
    document = UntrustedText(text="Oxygen shall be at least 19.5 %.", source_sha256="0" * 64)
    request = build_request(
        PROFILES[profile_id], document, ctx_site, model_id=model_id, sentinel=sentinel
    )
    flat = repr(request.body)
    for banned in sorted(BANNED_SAMPLING_KEYS):
        assert f"'{banned}'" not in flat, f"{profile_id} body carries {banned}"
    assert_no_sampling_params(request.body)


def test_the_guard_fires_on_every_banned_key_and_names_the_path():
    # The violating bodies are BUILT from the ban list rather than written as literals.
    # Two reasons, and the second is the interesting one: it covers every banned key
    # instead of two hand-picked ones, and it keeps this file clean under
    # `mainline-boundary`'s repo-wide GREP-SAMPLING-PARAM scan, which reads dict-key
    # constants and cannot tell a test fixture from a request builder.
    for banned in sorted(BANNED_SAMPLING_KEYS):
        with pytest.raises(ForbiddenRequestField) as excinfo:
            assert_no_sampling_params({"max_tokens": 10, banned: 0})
        assert excinfo.value.field == banned
        assert excinfo.value.path == banned

        with pytest.raises(ForbiddenRequestField) as nested:
            assert_no_sampling_params({"inference_config": {banned: 0}})
        assert nested.value.path == f"inference_config.{banned}"

        with pytest.raises(ForbiddenRequestField) as deep:
            assert_no_sampling_params({"messages": [{"content": [{banned: 0}]}]})
        assert deep.value.path == f"messages[0].content[0].{banned}"


def test_a_document_field_named_for_a_sampling_parameter_is_not_one():
    # A furnace procedure has a temperature setpoint, and an extraction model with a
    # `temperature` field is reading the corpus, not configuring the decoder. If the
    # guard descended into the output schema it would fire on the corpus, and a guard
    # that fires on the corpus gets disabled within a week.
    for field_name in sorted(BANNED_SAMPLING_KEYS):
        assert_no_sampling_params(
            {
                "max_tokens": 10,
                "output_config": {
                    "format": {
                        "type": "json_schema",
                        "schema": {"properties": {field_name: {"type": "integer"}}},
                    }
                },
            }
        )


def test_bodies_carry_the_pinned_request_shape(model_id, sentinel, ctx_site):
    document = UntrustedText(
        text="Re-test at intervals not exceeding 30 min.", source_sha256="0" * 64
    )
    request = build_request(
        PROFILES["adjudication"], document, ctx_site, model_id=model_id, sentinel=sentinel
    )
    body = request.body
    assert body["anthropic_version"] == "bedrock-2023-05-31"
    # Decision A5: written explicitly on every call, never omitted, never disabled.
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "high"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["max_tokens"] == PROFILES["adjudication"].max_tokens
    assert list(body["messages"][0]) == ["role", "content"]
    assert body["messages"][0]["role"] == "user"
