# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Decision A9: one breakpoint, a warmed prefix, and a cache read that is asserted.

The two assertions the domain plan names explicitly are here:
``cache_read_input_tokens > 0`` on call #2, and *a cold fan-out is impossible*.
"""

from __future__ import annotations

import make_cassettes as recipes
import pytest
from mainline_agentkit import (
    ADJUDICATION,
    EXTRACTION,
    TRIAGE,
    CachePrefixTooSmall,
    ColdFanout,
    FanoutInput,
    UntrustedText,
    place_cache_breakpoint,
    warm_then_fanout,
)
from mainline_agentkit.cache import estimate_tokens, min_cacheable_tokens, prefix_digest
from mainline_agentkit.call import WARM_REGISTRY, _fanout_one, build_request


def test_exactly_one_breakpoint_and_it_is_on_the_last_block():
    for profile in (TRIAGE, EXTRACTION, ADJUDICATION):
        blocks = profile.build_system()
        with_control = [index for index, block in enumerate(blocks) if "cache_control" in block]
        assert with_control == [len(blocks) - 1], profile.profile_id
        assert blocks[-1]["cache_control"] == {"type": "ephemeral"}


def test_a_prefix_below_the_generation_minimum_is_refused():
    with pytest.raises(CachePrefixTooSmall) as excinfo:
        place_cache_breakpoint(["too short"], profile_id="toy", model_key="claude-opus-5")
    assert excinfo.value.minimum == 512
    # And it is permitted only when a profile says so out loud.
    blocks = place_cache_breakpoint(
        ["too short"],
        profile_id="toy",
        model_key="claude-opus-5",
        allow_uncacheable_prefix=True,
    )
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}


def test_the_generation_minimum_is_why_triage_is_not_on_haiku():
    # Decision A4, as a number rather than an opinion: the shared rubric prefix is over
    # Opus 5's minimum and under Haiku 4.5's, so moving triage to Haiku would silently
    # stop the cache working.
    estimated = estimate_tokens(TRIAGE.system_text())
    assert estimated >= min_cacheable_tokens("claude-opus-5")
    assert estimated < min_cacheable_tokens("claude-haiku-4-5")


def test_unknown_generations_get_the_most_conservative_minimum():
    assert min_cacheable_tokens("claude-nonesuch-9") == 4096


def test_warm_then_fanout_reads_the_cache_on_call_two(transport, settings, model_id, ctx_site):
    inputs = [
        FanoutInput(untrusted=recipes.DOC_PROCEDURE, trusted_context=ctx_site),
        FanoutInput(untrusted=recipes.DOC_INCIDENT, trusted_context=ctx_site),
        FanoutInput(untrusted=recipes.DOC_SIGNAL, trusted_context=ctx_site),
    ]
    results = warm_then_fanout(
        EXTRACTION, inputs, transport=transport, model_id=model_id, settings=settings
    )
    assert len(results) == 3
    # Call #1 pays for the prefix and writes the cache entry.
    assert results[0].cache.warmed is True
    assert results[0].cache.creation_tokens > 0
    assert results[0].cache.read_tokens == 0
    # Calls #2 and #3 read it. This is the assertion decision A9 exists for.
    for later in results[1:]:
        assert later.cache.read_tokens > 0, "the fan-out did not read the cache"
        assert later.cache.read_hit is True
    assert {result.cache.prefix_digest for result in results} == {results[0].cache.prefix_digest}


def test_a_cold_fanout_is_impossible(transport, model_id, ctx_site, sentinel):
    WARM_REGISTRY.clear()
    item = FanoutInput(untrusted=recipes.DOC_INCIDENT, trusted_context=ctx_site)
    digest = prefix_digest(EXTRACTION.build_system())
    with pytest.raises(ColdFanout) as excinfo:
        _fanout_one(EXTRACTION, item, transport, model_id, sentinel, digest)
    assert excinfo.value.prefix_digest == digest


def test_the_registry_is_marked_only_after_a_warm(transport, settings, model_id, ctx_site):
    digest = prefix_digest(EXTRACTION.build_system())
    assert WARM_REGISTRY.is_warm(digest) is False
    warm_then_fanout(
        EXTRACTION,
        [FanoutInput(untrusted=recipes.DOC_PROCEDURE, trusted_context=ctx_site)],
        transport=transport,
        model_id=model_id,
        settings=settings,
    )
    assert WARM_REGISTRY.is_warm(digest) is True


def test_fanout_refuses_an_empty_input_list(transport, settings, model_id):
    with pytest.raises(ValueError, match="at least one input"):
        warm_then_fanout(EXTRACTION, [], transport=transport, model_id=model_id, settings=settings)


def test_the_prefix_digest_moves_when_the_prompt_moves(model_id, sentinel, ctx_site):
    document = UntrustedText(
        text="A clause long enough that the untrusted-in-system guard looks at it.",
        source_sha256="0" * 64,
    )
    baseline = build_request(
        EXTRACTION, document, ctx_site, model_id=model_id, sentinel=sentinel
    ).prefix_digest
    edited = prefix_digest(
        [{"type": "text", "text": EXTRACTION.system_text() + " "}, {"type": "text", "text": "x"}]
    )
    assert baseline != edited
