# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The golden digest.  Drift in the embedding contract is a CI failure, not a regression.

``EMBED_TEMPLATE_SHA256`` covers the embedding template **and** the facet-definitions block,
because those two together decide whether two vectors are comparable: the template fixes the
string that is embedded and the definitions fix what the words in it mean.  Callers pin the
value into ``recall_policy`` next to ``prompt_version``.

If either changes, this test goes red and the fix is a **commit**: bump ``PROMPT_VERSION``,
regenerate the cassettes, update the golden, and accept that the corpus must be re-embedded.
Silently editing the golden to match is the one wrong move, because every cue already in the
index was written under the old contract and nothing else would ever say so.
"""

from __future__ import annotations

from mainline_recall_agent.cue.prompts import PROMPT_VERSION
from mainline_recall_agent.cue.schema import FACETS
from mainline_recall_agent.cue.template import (
    EMBED_TEMPLATE,
    EMBED_TEMPLATE_DIGEST_INPUT,
    EMBED_TEMPLATE_SHA256,
    TEMPLATE_DIGEST_VERSION,
    embed_text_for,
    policy_pin,
)
from mainline_recall_agent.providers.base import EMBED_TEMPLATE as PROVIDER_TEMPLATE
from mainline_recall_agent.providers.canonical import canonical_json, sha256_hex
from mainline_recall_agent.providers.types import FACETS as PROVIDER_FACETS

#: Committed golden.  Regenerate deliberately, never reflexively.
GOLDEN_EMBED_TEMPLATE_SHA256 = "ef37153a481a7c734cd4d97597219d8d887ebf2b0f5c08653d18a0ad1f2693b6"

GOLDEN_EMBED_TEMPLATE = "{activity_path} | {asset_class} | {facet}: {cue_text}"

GOLDEN_PROMPT_VERSION = "mainline-cue-1"


def test_the_template_digest_matches_the_committed_golden() -> None:
    assert EMBED_TEMPLATE_SHA256 == GOLDEN_EMBED_TEMPLATE_SHA256


def test_the_template_string_itself_is_the_one_recall_md_d3_specifies() -> None:
    assert EMBED_TEMPLATE == GOLDEN_EMBED_TEMPLATE
    assert EMBED_TEMPLATE is PROVIDER_TEMPLATE, "the cue side re-exports; it does not re-declare"


def test_the_prompt_version_is_pinned() -> None:
    """``event_cue`` is UNIQUE on (event_id, scope_id, facet, prompt_version)."""
    assert PROMPT_VERSION == GOLDEN_PROMPT_VERSION


def test_the_digest_is_recomputable_by_a_stranger() -> None:
    """No hidden inputs: sha256 over RFC 8785 canonical JSON of a dict anyone can print."""
    assert EMBED_TEMPLATE_SHA256 == sha256_hex(canonical_json(EMBED_TEMPLATE_DIGEST_INPUT))
    assert set(EMBED_TEMPLATE_DIGEST_INPUT) == {
        "digest_version",
        "embed_template",
        "facets",
        "facet_definitions",
    }
    assert EMBED_TEMPLATE_DIGEST_INPUT["digest_version"] == TEMPLATE_DIGEST_VERSION


def test_the_digest_moves_when_the_facet_definitions_move() -> None:
    """The assertion that the block is actually covered, rather than nominally covered."""
    drifted = dict(EMBED_TEMPLATE_DIGEST_INPUT)
    drifted["facet_definitions"] = str(drifted["facet_definitions"]) + " "
    assert sha256_hex(canonical_json(drifted)) != EMBED_TEMPLATE_SHA256


def test_the_facet_vocabulary_agrees_with_the_provider_layer() -> None:
    """One of these lists is written into a CHECK constraint.  They may not diverge."""
    assert tuple(FACETS) == tuple(PROVIDER_FACETS)


def test_the_embedded_text_is_identical_on_both_sides_for_the_same_inputs() -> None:
    """One template, implemented once — the whole reason the digest is worth pinning."""
    kwargs = {
        "activity_path": "isolating stored energy / entering machine envelopes",
        "asset_class": "secondary crushing",
        "facet": "mechanism",
        "cue_text": "release of stored rotational energy with people inside the envelope",
    }
    assert embed_text_for(**kwargs) == (
        "isolating stored energy / entering machine envelopes | secondary crushing | "
        "mechanism: release of stored rotational energy with people inside the envelope"
    )


def test_policy_pin_carries_what_recall_policy_needs() -> None:
    pin = policy_pin()
    assert pin["prompt_version"] == PROMPT_VERSION
    assert pin["embed_template_sha256"] == EMBED_TEMPLATE_SHA256
    assert pin["embed_template"] == EMBED_TEMPLATE
