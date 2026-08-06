# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Provider exceptions, each carrying the silence-ledger reason the caller must write.

The silence ledger's ``reason`` column is a *closed* vocabulary (ARCHITECTURE §5.7, D10)::

    below_tau | model_refusal | dedup_sibling | cap_exceeded
    truncated | abstained | bounded_negative | unreachable

Every provider failure that must become a row in ``mainline_meas.silence_ledger`` carries
its reason as a class attribute, so the orchestrator never has to guess and a new failure
mode cannot quietly map to "nothing happened".  ``ProviderError`` subclasses that carry
``silence_reason = None`` are programmer errors — a bug in *our* code, not a fact about
the corpus — and must crash the run rather than be recorded as silence.
"""

from __future__ import annotations

from typing import Any, Final

__all__ = [
    "CANONICAL_SILENCE_REASONS",
    "CanonicalisationError",
    "CassetteMiss",
    "CassetteRecordingNotPermitted",
    "CassetteTampered",
    "DeadLetter",
    "EmptyEmbeddingInput",
    "HeterogeneousCorpus",
    "ModelRefusal",
    "ModelTruncated",
    "ProfileResolutionFailed",
    "ProjectionError",
    "ProviderError",
    "ProviderUnavailable",
    "ResidencyViolation",
    "SystemBlockContract",
    "VectorShapeError",
]

#: The closed D10 vocabulary.  Nothing outside this set may reach ``silence_ledger.reason``.
CANONICAL_SILENCE_REASONS: Final[frozenset[str]] = frozenset(
    {
        "below_tau",
        "model_refusal",
        "dedup_sibling",
        "cap_exceeded",
        "truncated",
        "abstained",
        "bounded_negative",
        "unreachable",
    }
)


class ProviderError(Exception):
    """Base class for every failure raised by this package.

    ``silence_reason`` is ``None`` for defects (bad calls, corrupt fixtures, contract
    violations).  A subclass that sets it is asserting: *this is a fact about the world
    that the record must retain*.
    """

    silence_reason: str | None = None

    def __init__(self, message: str, /, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __str__(self) -> str:  # pragma: no cover - trivial
        if not self.context:
            return self.message
        rendered = ", ".join(f"{k}={v!r}" for k, v in sorted(self.context.items()))
        return f"{self.message} [{rendered}]"


# --------------------------------------------------------------------------------------
# Failures that ARE evidence — they become silence_ledger rows.
# --------------------------------------------------------------------------------------


class ModelRefusal(ProviderError):
    """``stop_reason == 'refusal'``.

    Our corpus is cyanide leaching, H2S, explosives and confined-space chemistry, so a
    refusal on a clean document is plausible (ARCHITECTURE §8.4).  The caller writes
    ``silence_ledger(reason='model_refusal')`` and falls back to channels A+B **client
    side**.  A precursor the model declined to summarise must still block the merge.
    """

    silence_reason = "model_refusal"


class ModelTruncated(ProviderError):
    """``stop_reason == 'max_tokens'`` — the answer was cut off, so it is not an answer."""

    silence_reason = "truncated"


class DeadLetter(ProviderError):
    """Schema validation failed twice (one call, one repair attempt).

    Carries enough context for the caller to write ``silence_ledger(reason='abstained')``
    without re-deriving anything: the request digest, both raw completions and both
    validator errors.
    """

    silence_reason = "abstained"

    def __init__(
        self,
        message: str,
        /,
        *,
        request_digest: str,
        attempts: list[dict[str, Any]],
        model: dict[str, Any],
        **context: Any,
    ) -> None:
        super().__init__(
            message,
            request_digest=request_digest,
            attempt_count=len(attempts),
            model=model,
            **context,
        )
        self.request_digest = request_digest
        self.attempts = attempts
        self.model = model


class ProviderUnavailable(ProviderError):
    """The provider cannot run here at all (no weights, no SDK, no credentials).

    Distinct from a refusal: nothing was asked and nothing was declined.  Recall degrades
    to A+B and records ``arms_degraded``; the candidate that was never scored is
    ``unreachable``, not ``abstained``.
    """

    silence_reason = "unreachable"


# --------------------------------------------------------------------------------------
# Defects — these are bugs or corrupt inputs.  They must never become silence.
# --------------------------------------------------------------------------------------


class CanonicalisationError(ProviderError):
    """A value cannot be canonicalised under RFC 8785 (NaN, Infinity, exotic type)."""


class VectorShapeError(ProviderError):
    """Wrong dimensionality, non-finite component, or a zero vector where none is legal."""


class EmptyEmbeddingInput(ProviderError):
    """A blank cue was handed to an embedder.

    Refused rather than mapped to a vector: a blank cue that silently becomes a point in
    the index is a retrievable object with no content behind it.
    """


class HeterogeneousCorpus(ProviderError):
    """Rows in one corpus carry more than one ``embed_model`` / ``index_gen``.

    Cosine between two different embedding spaces is a number with no meaning, and it is
    a number that would reach a supervisor.
    """


class ProjectionError(ProviderError):
    """The committed coarse-projection artefact is missing, malformed or unverified."""


class ResidencyViolation(ProviderError):
    """A non-``au.*`` inference profile was about to be used.

    ``global.*`` routes to all commercial Regions and ``apac.*`` can take Queensland
    fatality narratives offshore (ARCHITECTURE §10.1).  Both are residency arguments we
    lose in the room, so this is a hard refusal rather than a warning.
    """


class ProfileResolutionFailed(ProviderError):
    """``bedrock:ListInferenceProfiles`` returned nothing usable for the requested tier."""


class SystemBlockContract(ProviderError):
    """Volatile content was placed in the cached system prefix, or the prefix is empty.

    A system prefix whose bytes change per request is a cache that never hits and a
    prompt-injection surface, so the contract is enforced structurally.
    """


class CassetteMiss(ProviderError):
    """Replay mode, and no cassette exists for this request digest."""


class CassetteTampered(ProviderError):
    """A cassette's recorded digest does not match its recorded request."""


class CassetteRecordingNotPermitted(ProviderError):
    """Record mode was requested without the explicit opt-in environment variables."""
