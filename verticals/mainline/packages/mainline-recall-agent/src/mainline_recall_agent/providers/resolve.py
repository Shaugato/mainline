# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Runtime resolution of the Claude inference profile.  Nothing here is hard-coded.

recall.md D5 and ARCHITECTURE §10.1 / GT-11: the judge runs on a Claude **cross-region
inference profile whose id begins ``au.``**, and which profile that is must be discovered
at process start-up with ``bedrock:ListInferenceProfiles`` rather than written into the
source.  Three reasons, and only the third is about tidiness:

1. **PL-3 — no unproven capability on a dated path.**  AWS credentials are not valid on
   this machine.  A model id written here today would be a claim nobody has checked.
2. **Residency is the argument we cannot lose.**  ``global.*`` routes to every commercial
   Region; ``apac.*`` can take Queensland fatality narratives offshore.  A resolver that
   *asserts* the ``au.`` prefix refuses those; a constant in a file only hopes.
3. **The profile that served the run belongs in the record.**  The resolved id and ARN go
   into ``recall_policy.gen_model``, ``agent_action.model_id`` and the ``agent_identity``
   digest (ARCHITECTURE §8.2), so a later run against a different profile is visibly a
   different run rather than a silent one.

Degradation is explicit: if the requested tier carries no ``au.`` profile, the resolver
walks a declared ladder and returns ``degraded=True`` with the tier it actually got —
ARCHITECTURE §10.1's *"ship the previous generation and say so"*, as a field rather than a
README sentence.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any, Final

from .errors import ProfileResolutionFailed, ProviderUnavailable, ResidencyViolation
from .types import ResolvedModel

__all__ = [
    "AU_PROFILE_PREFIX",
    "BANNED_PROFILE_PREFIXES",
    "DEFAULT_TIER",
    "TIER_LADDER",
    "pinned_model",
    "resolve_inference_profile",
    "select_profile",
]

#: The only inference-profile prefix this deployment may use.
AU_PROFILE_PREFIX: Final[str] = "au."

#: Prefixes that are a residency failure, named so the refusal message can say which.
BANNED_PROFILE_PREFIXES: Final[tuple[str, ...]] = (
    "global.",
    "apac.",
    "us.",
    "eu.",
    "jp.",
    "ca.",
)

#: First-party tier names (NOT Bedrock model ids).  The requested tier is matched against
#: whatever ``ListInferenceProfiles`` reports; the ladder is walked only on a miss.
DEFAULT_TIER: Final[str] = "claude-opus-5"
TIER_LADDER: Final[tuple[str, ...]] = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
)

REQUIRED_REGION: Final[str] = "ap-southeast-2"

_NON_ALNUM: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")


def _squash(text: str) -> str:
    return _NON_ALNUM.sub("", text.lower())


def _profile_fields(summary: dict[str, Any]) -> tuple[str, str | None, str]:
    profile_id = str(
        summary.get("inferenceProfileId") or summary.get("inference_profile_id") or ""
    )
    arn = summary.get("inferenceProfileArn") or summary.get("inference_profile_arn")
    name = str(summary.get("inferenceProfileName") or summary.get("inference_profile_name") or "")
    return profile_id, (str(arn) if arn else None), name


def _assert_residency(profile_id: str) -> None:
    lowered = profile_id.lower()
    if lowered.startswith(AU_PROFILE_PREFIX):
        return
    for banned in BANNED_PROFILE_PREFIXES:
        if lowered.startswith(banned):
            raise ResidencyViolation(
                "refusing a non-Australian inference profile; Queensland fatality "
                "narratives may not leave the residency boundary",
                profile_id=profile_id,
                prefix=banned,
            )
    raise ResidencyViolation(
        "inference profile does not carry the required au. prefix",
        profile_id=profile_id,
    )


def select_profile(
    summaries: Iterable[dict[str, Any]],
    *,
    requested_tier: str = DEFAULT_TIER,
    ladder: Sequence[str] = TIER_LADDER,
    region: str = REQUIRED_REGION,
) -> ResolvedModel:
    """Pick the ``au.*`` profile for ``requested_tier``, or the best rung below it.

    Pure: takes the raw ``inferenceProfileSummaries`` list so it is testable without AWS.
    """
    active: list[tuple[str, str | None, str]] = []
    for summary in summaries:
        status = str(summary.get("status", "ACTIVE")).upper()
        if status not in {"ACTIVE", ""}:
            continue
        profile_id, arn, name = _profile_fields(summary)
        if not profile_id:
            continue
        if not profile_id.lower().startswith(AU_PROFILE_PREFIX):
            # Non-au profiles are not an error to *see* — the account may hold many.
            # They are an error to USE, which _assert_residency enforces on the winner.
            continue
        active.append((profile_id, arn, name))

    if not active:
        raise ProfileResolutionFailed(
            "no ACTIVE au.* inference profile is visible to this principal; the judge "
            "cannot run and recall must degrade to channels A+B",
            region=region,
            requested_tier=requested_tier,
        )

    tiers: list[str] = [requested_tier, *[t for t in ladder if t != requested_tier]]
    for rung, tier in enumerate(tiers):
        needle = _squash(tier)
        for profile_id, arn, name in active:
            haystack = _squash(profile_id) + "\x00" + _squash(name)
            if needle in haystack:
                _assert_residency(profile_id)
                return ResolvedModel(
                    requested_tier=requested_tier,
                    resolved_tier=tier,
                    profile_id=profile_id,
                    profile_arn=arn,
                    region=region,
                    source="bedrock:ListInferenceProfiles",
                    resolved_at=datetime.now(UTC),
                    degraded=rung > 0,
                )

    raise ProfileResolutionFailed(
        "au.* profiles exist but none matches the requested tier or any declared rung "
        "below it; refusing to guess which model is acceptable",
        requested_tier=requested_tier,
        ladder=list(tiers),
        seen=[profile_id for profile_id, _, _ in active],
    )


def resolve_inference_profile(
    *,
    requested_tier: str = DEFAULT_TIER,
    region: str | None = None,
    client: Any | None = None,
    ladder: Sequence[str] = TIER_LADDER,
) -> ResolvedModel:
    """Call ``bedrock:ListInferenceProfiles`` and select.  Requires live credentials.

    Raises ``ProviderUnavailable`` when there is no client, no credentials or no route —
    which is the state of this build machine, and is why the cassette provider is the CI
    and demo default.
    """
    resolved_region = region or os.environ.get("AWS_REGION") or REQUIRED_REGION
    bedrock = client
    if bedrock is None:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - boto3 is a declared dependency
            raise ProviderUnavailable("boto3 is not installed") from exc
        try:
            bedrock = boto3.client("bedrock", region_name=resolved_region)
        except Exception as exc:  # pragma: no cover - requires a live AWS session
            raise ProviderUnavailable(
                "cannot construct a bedrock control-plane client",
                region=resolved_region,
            ) from exc

    summaries: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {"typeEquals": "SYSTEM_DEFINED", "maxResults": 100}
    try:
        while True:
            page = bedrock.list_inference_profiles(**kwargs)
            summaries.extend(page.get("inferenceProfileSummaries", []))
            token = page.get("nextToken")
            if not token:
                break
            kwargs["nextToken"] = token
    except Exception as exc:  # pragma: no cover - requires a live endpoint
        raise ProviderUnavailable(
            "bedrock:ListInferenceProfiles failed; the judge identity cannot be resolved "
            "and no hard-coded fallback exists by design",
            region=resolved_region,
            error=type(exc).__name__,
        ) from exc

    return select_profile(
        summaries, requested_tier=requested_tier, ladder=ladder, region=resolved_region
    )


def pinned_model(
    *,
    profile_id: str,
    profile_arn: str | None,
    requested_tier: str,
    resolved_tier: str,
    region: str = REQUIRED_REGION,
    degraded: bool = False,
) -> ResolvedModel:
    """Rebuild a ``ResolvedModel`` from a ``recall_policy`` row, re-asserting residency.

    A run replayed from a pinned policy must be refused just as hard as a fresh one if the
    pinned profile is not Australian — a policy row is not a bypass.
    """
    _assert_residency(profile_id)
    return ResolvedModel(
        requested_tier=requested_tier,
        resolved_tier=resolved_tier,
        profile_id=profile_id,
        profile_arn=profile_arn,
        region=region,
        source="pinned",
        resolved_at=None,
        degraded=degraded,
    )
