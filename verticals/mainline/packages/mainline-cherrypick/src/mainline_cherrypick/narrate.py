# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The one model call here explains a conflict and structurally cannot resolve one.

§8.3's sentence about the site adopter is the specification, and it is enforced in
four independent places. None of them is a prompt instruction, because a prompt
instruction is a request and the untrusted input here is two customer safety
documents.

1. **The schema.** ``ConflictNarration.resolution_proposed`` is
   ``Literal["none"]``, so a constrained decoder cannot emit anything else. An
   injection inside a procedure can at worst change a field *value* that is
   already restricted to one value.
2. **The call shape.** :func:`~mainline_agentkit.call.quarantined_call` has no
   ``tools`` parameter. The component reading two hostile documents holds no
   capability to act on them.
3. **The grant.** ``agent_fleet`` holds no ``UPDATE`` on ``merge_conflict``, so
   ``resolved_commit``, ``resolved_by`` and ``resolution_sig`` are unreachable from
   this package by privilege as well as by code.
4. **The type.** :class:`~mainline_cherrypick.types.HumanResolution` refuses an
   empty signature and refuses a subject that looks like a service identity.

One more choice, and it is the least obvious: **the recalled resolution is
deliberately withheld from the prompt.** :mod:`mainline_cherrypick.rerere` may
have a remembered resolution for exactly this conflict shape, and putting it in
the trusted context would make echoing it the easiest completion the model could
produce — a recommendation, arriving in prose, from a component forbidden to
recommend. The narration explains the disagreement; the recall is shown to the
person beside it, labelled as what it is.

**Refusal is expected here.** The corpus is cyanide leaching, H₂S and
confined-space chemistry, so ``stop_reason: "refusal"`` on a clean document is
plausible. It is not a memory gap: the ``merge_conflict`` row already exists, and
``CHECK conflicts_resolved_when_issued`` (MI04) already refuses the merge. A
conflict the model declined to describe still blocks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit import (
    NARRATION,
    ModelRefused,
    UntrustedText,
    quarantined_call,
    silence_row_for_refusal,
)

from .errors import AgentWouldResolve

if TYPE_CHECKING:
    from mainline_agentkit import AgentkitSettings, SilenceRow, Transport, Validated
    from mainline_agentkit.profiles import ConflictNarration

    from .types import MergeConflict

__all__ = [
    "CONFLICT_SILENCE_SOURCE",
    "compose_renderings",
    "conflict_silence_row",
    "narrate_conflict",
    "trusted_context_for",
]

#: ``mainline_meas.silence_ledger.source`` for a narration the model declined.
#: Verbatim from migration ``0084``'s closed vocabulary.
CONFLICT_SILENCE_SOURCE: Final[str] = "fleet_appraisal"

_BASE_LABEL: Final[str] = "COMMON ANCESTOR"
_OURS_LABEL: Final[str] = "SITE"
_THEIRS_LABEL: Final[str] = "FLEET"


def compose_renderings(
    base: str,
    ours: str,
    theirs: str,
    *,
    source_sha256: str,
) -> UntrustedText:
    """Compose the three renderings into the single untrusted block.

    All three are customer document text and all three go into a **user** turn,
    never a system block. :func:`~mainline_agentkit.call.build_request` refuses a
    body where document text reached a system block, so this is checked rather
    than remembered.

    ``source_sha256`` should be the digest of the receiving site's own rendering —
    that is the one whose bytes are under Object Lock in that site's tenancy, and
    it is what ties this call back to a custody record.
    """
    return UntrustedText(
        text=(
            f"[{_BASE_LABEL}]\n{base}\n\n[{_OURS_LABEL}]\n{ours}\n\n[{_THEIRS_LABEL}]\n{theirs}\n"
        ),
        source_sha256=source_sha256,
        media_type="text/plain",
    )


def trusted_context_for(conflict: MergeConflict) -> dict[str, Any]:
    """Build the operator-supplied framing: identifiers and digests, nothing persuasive.

    Carries no severity, no score, no prior resolution and no adoption deadline.
    Each of those would give the model a reason to lean, and a T2 narrator with a
    reason to lean is a recommendation with a disclaimer on it.
    """
    return {
        "conflict_id": str(conflict.conflict_id),
        "clause_uuid": str(conflict.clause_uuid),
        "labels": {
            "base": _BASE_LABEL,
            "ours": _OURS_LABEL,
            "theirs": _THEIRS_LABEL,
        },
        "base_digest": conflict.base_digest.hex(),
        "ours_digest": conflict.ours_digest.hex(),
        "theirs_digest": conflict.theirs_digest.hex(),
    }


def narrate_conflict(
    conflict: MergeConflict,
    base: str,
    ours: str,
    theirs: str,
    *,
    transport: Transport | None = None,
    model_id: str | None = None,
    settings: AgentkitSettings | None = None,
) -> Validated[ConflictNarration]:
    """Ask for a plain-English account of what the disagreement is.

    Returns the validated narration together with agentkit's replayability record
    — input hash, output hash, model id, profile ARN, prompt version and usage —
    which the caller writes into ``agent_action_provenance``.

    Raises:
        ModelRefused: the model declined. Convert it with
            :func:`conflict_silence_row` and show the conflict without a narrative.
            Do **not** treat it as an empty result: the conflict still blocks.
        AgentWouldResolve: the narration came back proposing a resolution. This is
            unreachable through the schema, which is precisely why it is asserted —
            an unreachable branch that is checked is a guarantee, and one that is
            not is an assumption.
    """
    validated = quarantined_call(
        NARRATION,
        compose_renderings(base, ours, theirs, source_sha256=conflict.ours_digest.hex()),
        trusted_context_for(conflict),
        transport=transport,
        model_id=model_id,
        settings=settings,
    )
    if validated.value.resolution_proposed != "none":  # pragma: no cover - schema-blocked
        raise AgentWouldResolve(
            f"narration for conflict {conflict.conflict_id} returned "
            f"resolution_proposed={validated.value.resolution_proposed!r}"
        )
    return validated


def conflict_silence_row(
    refusal: ModelRefused,
    conflict: MergeConflict,
    *,
    severity: int,
    input_sha256: str,
    inference_profile_arn: str,
) -> SilenceRow:
    """Build the ``silence_ledger`` row for a narration the model declined.

    **This package cannot write this row.** ``verticals/mainline/db/GRANTS.yaml``
    grants ``INSERT`` on ``mainline_meas.silence_ledger`` to ``agent_recaller``
    alone, so the caller must route it through the role that holds it. Returning
    the row rather than writing it is the same discipline the rest of this package
    follows, and here it also surfaces a real grant boundary instead of hiding it
    behind a helper that would fail at run time with a `42501`.

    The row is worth writing even so: it records that a human was shown a conflict
    with no explanation attached, which is a fact about what the system did and did
    not surface. It is *not* a record that anything was suppressed — the conflict
    row exists and MI04 refuses the merge regardless.
    """
    return silence_row_for_refusal(
        refusal,
        site_id=str(conflict.site_id),
        source=CONFLICT_SILENCE_SOURCE,
        subject_kind="merge_conflict",
        subject_id=str(conflict.conflict_id),
        severity=severity,
        profile_id=NARRATION.profile_id,
        prompt_version=NARRATION.prompt_version,
        model_id=NARRATION.model_key,
        inference_profile_arn=inference_profile_arn,
        input_sha256=input_sha256,
    )
