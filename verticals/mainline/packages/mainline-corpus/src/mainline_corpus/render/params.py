# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Every constant stage 2 is allowed to have an opinion about.

Kept in one file so that the answer to "what produced this text?" is a diff against a
twenty-line table rather than an archaeology exercise across nine modules.

The three that carry a decision:

``BEDROCK_MODEL_ID``
    ``au.anthropic.claude-sonnet-4-5-20250929-v1:0``.  The ``au.*`` prefix is not cosmetic:
    ARCHITECTURE §2.2 finding **S26** changed the corpus generator off ``apac.*`` because an
    ``apac.*`` profile can route a Queensland fatality narrative offshore, and §19 **GT-11**
    forbids ``global.*`` outright — it routes to *all* commercial regions.  ADR 0002 measured
    eight ``au.*`` Claude profiles ACTIVE in ``ap-southeast-2`` on 2026-08-07, so the family
    exists; **this specific profile id has not been verified on this account** and nothing on a
    dated path depends on it (ADR 0032).

``TIER_POLICY``
    The tier a node gets is a property of the node, decided here, not a runtime branch inside a
    renderer.  ``offline`` (the default) is: camera-facing → ``authored``, everything else →
    ``template``.  ``model-rendered`` moves the bulk to ``bedrock``.  Naming the policy makes
    the renderer census in ``corpus.lock.json`` a consequence of a committed decision rather
    than of whichever flag someone happened to pass.

``CAMERA_OWNER``
    Camera-facing nodes belong to ``corpus-spine-authored``.  When a fixture is missing, the
    refusal names that worker, because "the film has no authored text for beat 1" is a
    scheduling fact somebody must act on and not a rendering error to be worked around.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "AWS_REGION",
    "BEDROCK_MODEL_ID",
    "CACHE_RELPATH",
    "CACHE_VERSION",
    "CAMERA_OWNER",
    "DEFAULT_POLICY",
    "GENERATOR",
    "KEY_SEPARATOR",
    "NODE_KINDS",
    "NODE_PROMPT",
    "POLICIES",
    "TIERS",
    "TIER_MODEL_ID",
    "TIER_POLICY",
    "camera_owner_hint",
    "tier_for",
]

#: Written into every cache entry and into ``INDEX.json``.  Bump when the *entry shape*
#: changes; it does not participate in the key, so bumping it is a manifest-level event.
CACHE_VERSION: Final[int] = 1

#: Identifies the producer in ``INDEX.json``.  Not a package version — this is the render
#: stage's own contract number, and it moves when the deterministic tier's output rules move.
GENERATOR: Final[str] = "mainline-corpus/render/1"

#: Where the committed cache lives, relative to the repository root.
CACHE_RELPATH: Final[str] = "verticals/mainline/fixtures/corpus/cache"

#: The Bedrock inference profile.  ``au.*``, never ``apac.*`` (S26), never ``global.*`` (GT-11).
BEDROCK_MODEL_ID: Final[str] = "au.anthropic.claude-sonnet-4-5-20250929-v1:0"

#: Bedrock lives in Sydney.  ADR 0002 finding F5: the *database* is in Singapore, so no
#: end-to-end Australian residency claim may be made anywhere in this repository.
AWS_REGION: Final[str] = "ap-southeast-2"

#: The three tiers, in census order.
TIERS: Final[tuple[str, ...]] = ("authored", "bedrock", "template")

#: The model identity that goes into the cache key alongside the prompt.  For the two offline
#: tiers it is a *producer* identity rather than a model: two different producers must never
#: collide on one key, and a change to how a producer works must invalidate its entries.
TIER_MODEL_ID: Final[dict[str, str]] = {
    "authored": "authored/verbatim-1",
    "bedrock": BEDROCK_MODEL_ID,
    "template": "template/deterministic-1",
}

#: The four render nodes, in a fixed order, and the prompt each one uses.
NODE_KINDS: Final[tuple[str, ...]] = (
    "clause_text",
    "event_narrative",
    "moc_justification",
    "revision_reason",
)

NODE_PROMPT: Final[dict[str, str]] = {
    "clause_text": "clause",
    "event_narrative": "icam",
    "moc_justification": "moc",
    "revision_reason": "revreason",
}

#: Tier assignment, by policy, as ``(camera_facing_tier, bulk_tier)``.
TIER_POLICY: Final[dict[str, tuple[str, str]]] = {
    "offline": ("authored", "template"),
    "model-rendered": ("authored", "bedrock"),
}

POLICIES: Final[tuple[str, ...]] = tuple(sorted(TIER_POLICY))

#: D2: offline is the default, because AWS credentials are not valid on the founder's machine
#: and PL-3 forbids putting an unproven capability on a dated path.
DEFAULT_POLICY: Final[str] = "offline"

#: The worker who owns ``verticals/mainline/fixtures/corpus/authored/``.
CAMERA_OWNER: Final[str] = "corpus-spine-authored"

#: ``sha256(prompt ‖ model_id ‖ prompt_version)`` with an explicit separator, so that the
#: concatenation is injective.  Without it, ``("ab", "c")`` and ``("a", "bc")`` hash alike and
#: two different renders could quietly share one cache entry.  NUL cannot occur in any of the
#: three inputs, all of which are UTF-8 text this package produced.
KEY_SEPARATOR: Final[bytes] = b"\x00"


def tier_for(*, policy: str, camera_facing: bool) -> str:
    """Return the tier a node gets under ``policy``."""
    try:
        camera_tier, bulk_tier = TIER_POLICY[policy]
    except KeyError:
        raise ValueError(f"unknown render policy {policy!r}; known: {list(POLICIES)}") from None
    return camera_tier if camera_facing else bulk_tier


def camera_owner_hint(node_id: str) -> str:
    """Return the refusal text for a camera-facing node with no authored fixture."""
    return (
        f"camera-facing node {node_id!r} has no authored fixture. "
        f"verticals/mainline/fixtures/corpus/authored/ is owned by {CAMERA_OWNER}; every word "
        "that appears on camera comes from there and no tier may substitute for it. "
        "Pass --camera=defer to build the rest of the corpus and record this node as deferred."
    )
