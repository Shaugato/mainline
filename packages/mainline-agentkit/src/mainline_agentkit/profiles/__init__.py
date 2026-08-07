# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The call-profile register.

Five profiles, one model generation, differentiated by ``output_config.effort``
(decision A4). Importing this package validates every one of them — schema derivation,
forbidden-field refusal, token-budget sanity and cacheable-prefix length all run in the
import — so a profile that could not have been called correctly cannot be imported at
all.

``spec/agents/fleet.yaml`` references these ids in its ``call_profiles`` column. The
canonical set is:

============================ ======= ======== =========================================
``profile_id``               tier    effort   agent (§8.4)
============================ ======= ======== =========================================
``triage``                   T1      low      archivist
``extraction``               T1      low      archivist
``adjudication``             T1      high     cartographer
``narration``                T2      high     cherry_pick_worker
``disposition_assistant``    T2      low      disposition_assistant
============================ ======= ======== =========================================

``xhigh`` is reserved for the recall domain's listwise rerank profile, which the recall
lead owns; it is deliberately absent here rather than stubbed, because a profile nobody
calls is a profile nobody maintains.

**None of these profiles holds a tool, and none may write a gate-visible field.**
:meth:`CallProfile.describe` emits ``"tools": []`` so the fleet-matrix test reads an
explicit empty list rather than inferring one from an absent key.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import ProfileUnknown
from ._model import DISPOSITION_FORBIDDEN_TOKENS, CallProfile, Effort, Tier
from ._rubric import COMMON_RUBRIC, RUBRIC_VERSION
from .adjudication import ADJUDICATION, Adjudication
from .disposition_assistant import DISPOSITION_ASSISTANT, DisplayOnlyText
from .extraction import EXTRACTION, ExtractedQuantity, ExtractionResult
from .narration import NARRATION, ConflictNarration
from .triage import TRIAGE, TriageVerdict

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "ADJUDICATION",
    "COMMON_RUBRIC",
    "DISPOSITION_ASSISTANT",
    "DISPOSITION_FORBIDDEN_TOKENS",
    "EXTRACTION",
    "NARRATION",
    "PROFILES",
    "RUBRIC_VERSION",
    "TRIAGE",
    "Adjudication",
    "CallProfile",
    "ConflictNarration",
    "DisplayOnlyText",
    "Effort",
    "ExtractedQuantity",
    "ExtractionResult",
    "Tier",
    "TriageVerdict",
    "describe_fleet",
    "get_profile",
]

#: Every profile MAINLINE ships, keyed by the id ``fleet.yaml`` references.
PROFILES: Mapping[str, CallProfile[Any]] = {
    profile.profile_id: profile
    for profile in (TRIAGE, EXTRACTION, ADJUDICATION, NARRATION, DISPOSITION_ASSISTANT)
}


def get_profile(profile_id: str) -> CallProfile[Any]:
    """Look up a profile by id.

    Raises:
        ProfileUnknown: naming the profiles that do exist. A silent ``None`` here
            becomes an ``AttributeError`` three frames away from the typo.
    """
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise ProfileUnknown(profile_id, tuple(PROFILES)) from exc


def describe_fleet() -> list[dict[str, Any]]:
    """Every profile in register shape, sorted by id.

    Consumed by ``spec/agents/fleet.yaml``'s conformance test and by
    ``mainline-boundary``'s fleet-capability matrix, so that the register and the code
    are checked against each other rather than maintained in parallel.
    """
    return [PROFILES[key].describe() for key in sorted(PROFILES)]
