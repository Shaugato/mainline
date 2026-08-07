# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The embedding text template (recall.md D3) and the digest callers pin.

One template, implemented once, used by both sides::

    "{activity_path} | {asset_class} | {facet}: {cue_text}"

It lives in ``providers.base`` — the layer both sides already depend on — and is re-exported
here so that a cue-side caller never has a reason to write its own.  Contextual retrieval is
the cheapest available win, and query/document genre symmetry is the reason cues exist at
all: if this template drifts between the event side and the permit side, the whole design
degrades to narrative search with nothing raising an error.

:data:`EMBED_TEMPLATE_SHA256` is what makes that drift a CI failure rather than a slow
regression.  It digests the template **and** the facet-definitions block, because those two
together are what determines whether two vectors are comparable: the template fixes the
string that is embedded, and the definitions fix what the words in it mean.  Callers pin the
value into ``mainline_meas.recall_policy`` alongside ``prompt_version``, so a run can be
re-derived against the exact contract that produced its index.

What the digest does **not** cover, said plainly: the embedding model, its revision, and the
coarse-projection artefact.  Those are ``embed_model`` and ``index_gen`` on the sidecar rows
and are the providers' to pin.  A digest that claimed to cover them would be a promise this
module cannot keep.
"""

from __future__ import annotations

from typing import Final

from mainline_recall_agent.providers.base import EMBED_TEMPLATE, embed_text
from mainline_recall_agent.providers.canonical import canonical_json, sha256_hex
from mainline_recall_agent.providers.types import FACETS as PROVIDER_FACETS

from .errors import CueError
from .prompts import FACET_DEFINITIONS, PROMPT_VERSION
from .schema import FACETS

__all__ = [
    "EMBED_TEMPLATE",
    "EMBED_TEMPLATE_DIGEST_INPUT",
    "EMBED_TEMPLATE_SHA256",
    "TEMPLATE_DIGEST_VERSION",
    "embed_text_for",
    "policy_pin",
]

#: Bump only when the *shape* of the digest input changes — not when its contents do.  A
#: content change is exactly what the digest exists to detect.
TEMPLATE_DIGEST_VERSION: Final[int] = 1

if tuple(FACETS) != tuple(PROVIDER_FACETS):  # pragma: no cover - both are literals
    raise CueError(
        "the cue facet vocabulary and the provider facet vocabulary have diverged; one of "
        "them no longer matches mainline.event_cue's CHECK constraint",
        cue_facets=list(FACETS),
        provider_facets=list(PROVIDER_FACETS),
    )

EMBED_TEMPLATE_DIGEST_INPUT: Final[dict[str, object]] = {
    "digest_version": TEMPLATE_DIGEST_VERSION,
    "embed_template": EMBED_TEMPLATE,
    "facet_definitions": FACET_DEFINITIONS,
    "facets": list(FACETS),
}

#: sha256 over RFC 8785 canonical JSON of the input above.  Pinned by a golden test.
EMBED_TEMPLATE_SHA256: Final[str] = sha256_hex(canonical_json(EMBED_TEMPLATE_DIGEST_INPUT))


def embed_text_for(*, activity_path: str, asset_class: str, facet: str, cue_text: str) -> str:
    """Compose the exact string that gets embedded, identically on both sides.

    A thin pass-through to ``providers.base.embed_text`` on purpose: the validation that
    refuses an unknown facet lives there, next to the batch validation that refuses a blank
    cue, and duplicating either here would create a second place for them to disagree.
    """
    return embed_text(
        activity_path=activity_path,
        asset_class=asset_class,
        facet=facet,
        cue_text=cue_text,
    )


def policy_pin() -> dict[str, object]:
    """The three values a caller writes into ``recall_policy`` for this contract."""
    return {
        "prompt_version": PROMPT_VERSION,
        "embed_template_sha256": EMBED_TEMPLATE_SHA256,
        "embed_template": EMBED_TEMPLATE,
    }
