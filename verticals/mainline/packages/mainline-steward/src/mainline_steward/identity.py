# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``agent_identity`` for the Steward — resolved once, at start-up, and never re-derived.

Decision A13: ``agent_identity := sha256(agent_name ‖ sql_role ‖ iam_role_arn ‖
prompt_version ‖ model_id ‖ inference_profile_arn ‖ schema_version)``. A prompt edit is
therefore a *different agent*, which is the property that makes "a quiet prompt change
suppressed a class of precursor" an attributable event rather than a rumour.

**Whose implementation is authoritative.** The ``agent-provenance`` worker owns the
canonical resolver and the ``mainline_meas.agent_identity`` table. That package is not
present in this checkout, so this module does two things and states which one ran:

1. If a resolver is available it is used, and ``identity_source`` records where it came
   from. Two places are consulted, in order: the ``MAINLINE_STEWARD_IDENTITY_PROVIDER``
   environment variable (``"module:attribute"``), and then ``mainline_provenance``'s
   ``resolve_agent_identity``. One named hook and one named import — not a search.
2. Otherwise :func:`local_agent_identity` computes the digest here, and
   ``identity_source`` is ``"local_fallback"``.

The fallback is honest rather than convenient, and the difference is visible in the
evidence: an attestation that says ``local_fallback`` is telling a reader that the digest
was computed by the Steward's own copy of the rule, which is exactly what they need to
know before comparing it with a row in ``agent_identity``.

**The framing rule.** ``‖`` in the specification is concatenation, and concatenation of
variable-length fields is ambiguous — ``"ab" ‖ "c"`` and ``"a" ‖ "bc"`` are the same
bytes. This module frames each field with its byte length, so no pair of different field
sets can produce the same preimage. If the provenance worker frames differently the two
digests differ, which is why ``identity_source`` exists and why the seven inputs are
carried in the attestation in clear beside the digest: a reader can always recompute.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Final, Protocol, runtime_checkable

from .errors import ConfigurationRefused

__all__ = [
    "AGENT_NAME",
    "IDENTITY_FIELD_ORDER",
    "AgentIdentity",
    "IdentityResolver",
    "local_agent_identity",
    "resolve_identity",
]

AGENT_NAME: Final = "steward"
"""Agent 8 in ``ARCHITECTURE.md`` §8.4. The name is part of the identity preimage."""

IDENTITY_FIELD_ORDER: Final = (
    "agent_name",
    "sql_role",
    "iam_role_arn",
    "prompt_version",
    "model_id",
    "inference_profile_arn",
    "schema_version",
)
"""The seven inputs, in the order decision A13 writes them. Order is part of the digest."""

_PROVIDER_ENV: Final = "MAINLINE_STEWARD_IDENTITY_PROVIDER"
_PROVENANCE_MODULE: Final = "mainline_provenance"
_PROVENANCE_ATTRIBUTE: Final = "resolve_agent_identity"
_LENGTH_BYTES: Final = 4
_SHA256_HEX_CHARS: Final = 64


@runtime_checkable
class IdentityResolver(Protocol):
    """What the Steward needs from the provenance worker: seven fields in, a digest out.

    Deliberately the narrowest possible shape. The provenance package also registers
    prompt assets and writes ``agent_action_provenance`` rows; none of that is reachable
    from here, and a wider Protocol would have made it reachable by accident.
    """

    def __call__(self, fields: Mapping[str, str]) -> str:
        """Return the lowercase hex ``agent_identity`` for these seven fields."""
        ...


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """The resolved identity, its seven inputs in clear, and where the digest came from."""

    agent_identity: str
    identity_source: str
    agent_name: str
    sql_role: str
    iam_role_arn: str
    prompt_version: str
    model_id: str
    inference_profile_arn: str
    schema_version: str

    def fields(self) -> dict[str, str]:
        """Return the seven preimage inputs, in A13 order."""
        return {name: getattr(self, name) for name in IDENTITY_FIELD_ORDER}

    def to_payload(self) -> dict[str, Any]:
        """Return the attestation fragment: digest, source, and every input in clear.

        The inputs are carried in clear on purpose. A digest a reader cannot recompute is
        a number, not evidence, and the seven fields here are configuration rather than
        secrets — the IAM role ARN and the profile ARN name capabilities, they do not
        confer them.
        """
        return {"agent_identity": self.agent_identity, "identity_source": self.identity_source} | (
            self.fields()
        )


def local_agent_identity(fields: Mapping[str, str]) -> str:
    """Compute ``agent_identity`` here, with the length-framed concatenation rule.

    Args:
        fields: every name in :data:`IDENTITY_FIELD_ORDER`, each a non-empty string.

    Returns:
        Lowercase hex SHA-256 of ``len(f) ‖ f`` for each field, in A13 order.

    Raises:
        ConfigurationRefused: a field is missing or empty. An identity computed over an
            empty ``sql_role`` would be a stable digest of a fact nobody established.
    """
    hasher = hashlib.sha256()
    for name in IDENTITY_FIELD_ORDER:
        value = fields.get(name, "")
        if not value:
            raise ConfigurationRefused(
                f"agent_identity input {name!r} is empty. The Steward's identity is the "
                "digest of what it is allowed to be; an empty input is an unestablished fact"
            )
        encoded = value.encode("utf-8")
        hasher.update(len(encoded).to_bytes(_LENGTH_BYTES, "big"))
        hasher.update(encoded)
    return hasher.hexdigest()


def _from_environment_provider() -> tuple[IdentityResolver, str] | None:
    """Load the resolver named by ``MAINLINE_STEWARD_IDENTITY_PROVIDER``, if it is set."""
    spec = os.environ.get(_PROVIDER_ENV, "").strip()
    if not spec:
        return None
    if ":" not in spec:
        raise ConfigurationRefused(
            f"{_PROVIDER_ENV}={spec!r} must be 'module:attribute'; a provider that cannot be "
            "resolved must fail loudly rather than fall back, because the fallback would "
            "silently produce a different digest"
        )
    module_name, _, attribute = spec.partition(":")
    try:
        module = import_module(module_name)
    except ImportError as exc:
        raise ConfigurationRefused(f"{_PROVIDER_ENV}={spec!r}: {exc}") from exc
    resolver = getattr(module, attribute, None)
    if not callable(resolver):
        raise ConfigurationRefused(f"{_PROVIDER_ENV}={spec!r}: {attribute!r} is not callable")
    typed: IdentityResolver = resolver
    return typed, spec


def _from_provenance_package() -> tuple[IdentityResolver, str] | None:
    """Use ``mainline_provenance.resolve_agent_identity`` when that package is installed."""
    try:
        module = import_module(_PROVENANCE_MODULE)
    except ImportError:
        return None
    resolver: Callable[..., Any] | None = getattr(module, _PROVENANCE_ATTRIBUTE, None)
    if not callable(resolver):
        return None
    typed: IdentityResolver = resolver
    return typed, f"{_PROVENANCE_MODULE}:{_PROVENANCE_ATTRIBUTE}"


def resolve_identity(
    *,
    sql_role: str,
    iam_role_arn: str,
    prompt_version: str,
    model_id: str,
    inference_profile_arn: str,
    schema_version: str,
    agent_name: str = AGENT_NAME,
    resolver: IdentityResolver | None = None,
) -> AgentIdentity:
    """Resolve the Steward's ``agent_identity`` once, at start-up.

    Args:
        sql_role: the SQL role the MCP identity runs as (``mainline_auditor``).
        iam_role_arn: the Fargate task role.
        prompt_version: the digest of the prompt tree this run will use.
        model_id: the model generation, e.g. ``au.anthropic.claude-opus-5``.
        inference_profile_arn: the resolved ``au.*`` profile ARN.
        schema_version: the migration-tree fingerprint the cluster is at.
        agent_name: overridable only so a test can prove the name is in the preimage.
        resolver: an explicit resolver, which wins over both discovery paths.

    Returns:
        The identity, with ``identity_source`` naming which implementation produced it.
    """
    fields = {
        "agent_name": agent_name,
        "sql_role": sql_role,
        "iam_role_arn": iam_role_arn,
        "prompt_version": prompt_version,
        "model_id": model_id,
        "inference_profile_arn": inference_profile_arn,
        "schema_version": schema_version,
    }
    chosen: tuple[IdentityResolver, str] | None
    if resolver is not None:
        chosen = (resolver, "explicit")
    else:
        chosen = _from_environment_provider() or _from_provenance_package()
    if chosen is None:
        digest = local_agent_identity(fields)
        source = "local_fallback"
    else:
        implementation, source = chosen
        # Validate the inputs with the local rule first, so a resolver that tolerates an
        # empty field cannot produce an identity this package would have refused.
        local_agent_identity(fields)
        digest = str(implementation(fields))
    hexadecimal = "0123456789abcdef"
    if len(digest) != _SHA256_HEX_CHARS or any(c not in hexadecimal for c in digest.lower()):
        raise ConfigurationRefused(
            f"identity resolver {source!r} returned {digest!r}, which is not a hex SHA-256"
        )
    return AgentIdentity(
        agent_identity=digest.lower(),
        identity_source=source,
        **fields,
    )
