# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The line between "the model could not answer" and "we are misconfigured".

Everything Path B can do wrong falls into exactly one of two buckets, and putting
a failure in the wrong bucket is the most damaging bug this package can have.

**Bucket 1 — the model could not answer.**  A refusal on a cyanide-leaching
procedure, a Guardrail intervention, a truncated response, JSON that does not fit
the schema twice running, a throttle, a timeout.  Every one of these becomes
``OracleVerdict(abstained=True)``, which the abstention ratchet resolves to
``weaken``, which blocks the merge.  Fail closed, loudly, with the arithmetic in
the silence ledger.

**Bucket 2 — we are misconfigured.**  A cassette that was never recorded, a
prompt version that does not match the profile, a model id that is not an
``au.*`` inference profile, a cassette recorded against a different model
generation.  These **raise**.

The temptation is to fold bucket 2 into bucket 1, because abstention is the safe
direction and folding would mean nothing ever crashes.  It is refused here for
one reason: an abstention is a *statement about the model*, written into an
evidentiary ledger, and a deployment whose transport is broken would then be
producing a stream of rows saying a model declined to answer questions that were
never put to it.  A false record is worse than a crash, and a crash on a path
that never touches the gate costs nothing.

Nothing in this module ever converts an exception it does not recognise.
:func:`abstention_code_for` returns ``None`` for an unrecognised exception and
the caller re-raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit import (
    DeadLettered,
    ModelRefused,
    SchemaViolation,
    TruncatedResponse,
    UnknownStopReason,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "THROTTLE_ERROR_CODES",
    "TIMEOUT_EXCEPTION_NAMES",
    "CassetteModelDrift",
    "CassetteRootUnknown",
    "DeltaOracleError",
    "OracleConfigurationRefused",
    "PromptVersionMismatch",
    "abstention_code_for",
]


class DeltaOracleError(Exception):
    """Base class for this package's own refusals."""


class OracleConfigurationRefused(DeltaOracleError):
    """The deployment is wrong.  Never converted to an abstention."""


class PromptVersionMismatch(OracleConfigurationRefused):
    """The request was built for a different prompt version than the profile ships.

    Decision A13 makes a prompt edit a commit, and a cassette replayed under a
    prompt that has since been edited is a green test asserting something that no
    longer exists.  The version travels on the request so the mismatch is caught
    at the boundary rather than discovered in a cassette digest.
    """


class CassetteModelDrift(OracleConfigurationRefused):
    """A committed cassette was recorded against a different model generation."""


class CassetteRootUnknown(OracleConfigurationRefused):
    """No cassette store could be located and none was supplied.

    Replay never falls through to a live call, so the honest response to "I do not
    know where the recordings are" is to stop.
    """


#: Bedrock/botocore error codes that mean *try again later*, not *no*.
#:
#: Matched by string rather than by ``except botocore.exceptions.ClientError``
#: because ``boto3`` is an optional extra: the offline lane installs no AWS SDK
#: at all, and a package that imported ``botocore`` to name an exception class
#: would break the property that the whole test suite runs with no SDK present.
THROTTLE_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "ThrottlingException",
        "Throttling",
        "TooManyRequestsException",
        "RequestLimitExceeded",
        "ServiceQuotaExceededException",
        "ModelNotReadyException",
        "ServiceUnavailableException",
        "InternalServerException",
    }
)

#: Exception *class names* that mean the call never completed.
TIMEOUT_EXCEPTION_NAMES: Final[frozenset[str]] = frozenset(
    {
        "ReadTimeoutError",
        "ConnectTimeoutError",
        "ConnectionError",
        "ConnectionClosedError",
        "EndpointConnectionError",
        "TimeoutError",
        "socket.timeout",
    }
)


def _error_code(exc: BaseException) -> str:
    """Pull the AWS error code out of a ``ClientError``-shaped exception, if any."""
    response: Any = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return ""
    error: Mapping[str, Any] | Any = response.get("Error")
    if not isinstance(error, dict):
        return ""
    code = error.get("Code")
    return str(code) if code else ""


#: Agentkit exception classes that mean "the model answered, and the answer is
#: unusable", in the order they are tested.  A table rather than a chain of
#: ``if isinstance`` returns so that adding a mode is a data edit and so that the
#: whole mapping is visible in one place.
_BEHAVIOUR_CODES: Final[tuple[tuple[type[BaseException], str], ...]] = (
    (TruncatedResponse, "truncated"),
    (UnknownStopReason, "unknown_stop_reason"),
    (DeadLettered, "schema_violation"),
    (SchemaViolation, "schema_violation"),
)


def _transport_code(exc: BaseException) -> str | None:
    """Classify a call that never completed, by exception class name or AWS code."""
    name = type(exc).__name__
    if name in TIMEOUT_EXCEPTION_NAMES:
        return "timeout"
    if name in THROTTLE_ERROR_CODES or _error_code(exc) in THROTTLE_ERROR_CODES:
        return "throttled"
    return None


def abstention_code_for(exc: BaseException) -> str | None:
    """Classify one exception into an abstention code, or ``None`` to re-raise.

    The returned strings are exactly the vocabulary declared in
    ``mainline_domain.resolution.silence.ABSTENTION_CODES`` — the domain owns the
    word list, because the domain is what writes it into the ledger and this
    package may never be the thing a database CHECK depends on.

    Returns:
        An abstention code for a model-behaviour failure; ``None`` for anything
        else, including every configuration refusal.
    """
    if isinstance(exc, ModelRefused):
        guardrail = exc.category == "guardrail_intervention"
        return "guardrail_intervention" if guardrail else "model_refusal"
    for kind, code in _BEHAVIOUR_CODES:
        if isinstance(exc, kind):
            return code
    if isinstance(exc, OracleConfigurationRefused):
        # Bucket 2. Never converted: a broken deployment must crash rather than
        # write a row saying a model declined a question nobody put to it.
        return None
    return _transport_code(exc)
