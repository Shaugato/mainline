# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 2, second half: the guardrail document, and what a guardrail response means.

``config/guardrail.json`` is a **committed** ``CreateGuardrail`` request body, not a
console screenshot and not a Terraform resource whose rendered form nobody reads. Three
properties of it are load-bearing, and :func:`validate_guardrail_document` refuses the
document if any of them is untrue:

1. ``PROMPT_ATTACK`` is present, enabled on the input side, at ``inputStrength: HIGH``
   with ``inputAction: BLOCK``. Any weaker pair is a filter that observes and permits.
2. ``crossRegionConfig`` is **absent**, at every depth. A guardrail profile routes
   guardrail inference to a set of destination Regions chosen by AWS; attaching one
   moves the evaluation of Australian incident text offshore with no error and no
   change in the response shape.
3. Both blocked-messaging strings are present, because they are what an operator sees
   when a document is refused and a refusal nobody can read is a refusal nobody acts on.

**Reading a response.** ``ApplyGuardrail`` returns ``action`` in
``{NONE, GUARDRAIL_INTERVENED}``; ``InvokeModel`` reports the same event out of band as
``amazon-bedrock-guardrailAction: INTERVENED`` (which is what
``mainline_agentkit.refusal`` already checks). Both are handled, and an ``action`` value
this module has never seen **refuses**: an unrecognised guardrail verdict treated as
``NONE`` is a guardrail that fails open, and layer 2's whole purpose is that it does not.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from .errors import GuardrailConfigInvalid, GuardrailResidencyRefused, GuardrailUnavailable

if TYPE_CHECKING:
    from .screen import ScreenResult

__all__ = [
    "APPLY_GUARDRAIL_INTERVENED",
    "APPLY_GUARDRAIL_NONE",
    "CROSS_REGION_KEY",
    "INVOKE_GUARDRAIL_ACTION_KEY",
    "PROMPT_ATTACK",
    "BedrockGuardrailScreen",
    "GuardrailDocument",
    "default_guardrail_path",
    "guardrail_intervened",
    "load_guardrail_document",
    "validate_guardrail_document",
]

PROMPT_ATTACK: Final[str] = "PROMPT_ATTACK"
CROSS_REGION_KEY: Final[str] = "crossRegionConfig"
APPLY_GUARDRAIL_NONE: Final[str] = "NONE"
APPLY_GUARDRAIL_INTERVENED: Final[str] = "GUARDRAIL_INTERVENED"

#: The out-of-band key ``InvokeModel`` uses. Kept equal to
#: ``mainline_agentkit.refusal.GUARDRAIL_ACTION_KEY`` by a test rather than by an import.
INVOKE_GUARDRAIL_ACTION_KEY: Final[str] = "amazon-bedrock-guardrailAction"

_REQUIRED_STRINGS: Final[tuple[str, ...]] = (
    "name",
    "blockedInputMessaging",
    "blockedOutputsMessaging",
)


@dataclass(frozen=True, slots=True)
class GuardrailDocument:
    """A validated ``CreateGuardrail`` body, with the digest of the bytes it came from."""

    path: Path
    document: Mapping[str, Any]
    sha256: str

    @property
    def name(self) -> str:
        """The guardrail name AWS will create."""
        return str(self.document["name"])

    def prompt_attack_filter(self) -> Mapping[str, Any]:
        """Return the ``PROMPT_ATTACK`` entry of ``contentPolicyConfig.filtersConfig``."""
        return _prompt_attack_filter(self.document)


def default_guardrail_path() -> Path:
    """Path to the committed guardrail document that ships with this package."""
    return Path(__file__).resolve().parent.parent.parent / "config" / "guardrail.json"


def load_guardrail_document(path: Path | None = None) -> GuardrailDocument:
    """Load and validate ``config/guardrail.json``.

    Raises:
        GuardrailConfigInvalid: the file is missing, is not JSON, or does not express
            the posture. There is no lenient mode.
        GuardrailResidencyRefused: ``crossRegionConfig`` appears anywhere in it.
    """
    resolved = path or default_guardrail_path()
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise GuardrailConfigInvalid(f"cannot read {resolved}: {exc}") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardrailConfigInvalid(f"{resolved} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise GuardrailConfigInvalid(f"{resolved} must contain a JSON object")
    validate_guardrail_document(document)
    return GuardrailDocument(
        path=resolved,
        document=document,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def validate_guardrail_document(document: Mapping[str, Any]) -> None:
    """Refuse a guardrail body that does not express ARCHITECTURE.md 8.4 layer 2.

    Raises:
        GuardrailResidencyRefused: ``crossRegionConfig`` present at any depth.
        GuardrailConfigInvalid: any other clause of the posture unmet.
    """
    _refuse_cross_region(document, "$")

    for key in _REQUIRED_STRINGS:
        value = document.get(key)
        if not isinstance(value, str) or not value.strip():
            raise GuardrailConfigInvalid(f"{key} must be a non-empty string")

    guard_filter = _prompt_attack_filter(document)
    strength = guard_filter.get("inputStrength")
    action = guard_filter.get("inputAction")
    enabled = guard_filter.get("inputEnabled")
    if strength != "HIGH":
        raise GuardrailConfigInvalid(
            f"{PROMPT_ATTACK}.inputStrength is {strength!r}; the posture requires 'HIGH'"
        )
    if action != "BLOCK":
        raise GuardrailConfigInvalid(
            f"{PROMPT_ATTACK}.inputAction is {action!r}; the posture requires 'BLOCK'. "
            f"'NONE' detects and permits, which is a filter that writes a metric rather "
            f"than a control that refuses."
        )
    if enabled is not True:
        raise GuardrailConfigInvalid(
            f"{PROMPT_ATTACK}.inputEnabled is {enabled!r}; the filter must be enabled on "
            f"the input side, which is the only side untrusted document text arrives on"
        )


def _prompt_attack_filter(document: Mapping[str, Any]) -> Mapping[str, Any]:
    policy = document.get("contentPolicyConfig")
    if not isinstance(policy, Mapping):
        raise GuardrailConfigInvalid("contentPolicyConfig is missing")
    filters = policy.get("filtersConfig")
    if not isinstance(filters, Sequence) or isinstance(filters, (str, bytes)):
        raise GuardrailConfigInvalid("contentPolicyConfig.filtersConfig must be an array")
    for entry in filters:
        if isinstance(entry, Mapping) and entry.get("type") == PROMPT_ATTACK:
            return entry
    raise GuardrailConfigInvalid(
        f"no {PROMPT_ATTACK} filter in contentPolicyConfig.filtersConfig; without it the "
        f"guardrail does not screen prompt attacks at all"
    )


def _refuse_cross_region(node: Any, pointer: str) -> None:
    """Walk the whole document. ``crossRegionConfig`` is refused wherever it appears."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == CROSS_REGION_KEY:
                raise GuardrailResidencyRefused(value)
            _refuse_cross_region(value, f"{pointer}.{key}")
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for index, item in enumerate(node):
            _refuse_cross_region(item, f"{pointer}[{index}]")


def guardrail_intervened(payload: Mapping[str, Any]) -> bool:
    """Whether a guardrail blocked this call, from either API's report of it.

    Raises:
        GuardrailConfigInvalid: an ``action`` value this module does not recognise. A
            verdict we cannot classify is refused, never read as ``NONE``.
    """
    action = payload.get("action")
    if isinstance(action, str):
        if action == APPLY_GUARDRAIL_INTERVENED:
            return True
        if action != APPLY_GUARDRAIL_NONE:
            raise GuardrailConfigInvalid(
                f"unrecognised ApplyGuardrail action {action!r}; known: "
                f"{[APPLY_GUARDRAIL_NONE, APPLY_GUARDRAIL_INTERVENED]}. An unclassifiable "
                f"guardrail verdict fails closed."
            )
    invoke_action = payload.get(INVOKE_GUARDRAIL_ACTION_KEY)
    if isinstance(invoke_action, str) and invoke_action.upper() == "INTERVENED":
        return True
    return action == APPLY_GUARDRAIL_INTERVENED


@dataclass(frozen=True, slots=True)
class BedrockGuardrailScreen:
    """The live ``ApplyGuardrail`` screen. Off by default, never exercised in CI.

    Satisfies the same ``PromptAttackScreen`` protocol as
    :class:`mainline_quarantine.screen.LocalPromptAttackScreen`, so a caller swaps one
    for the other without a branch. It is constructed only through
    :meth:`from_settings`, which refuses unless the operator opted in explicitly — a
    live call that happens by accident costs money and, worse, makes a CI result depend
    on a network.

    The content block carries ``qualifiers: ["guard_content"]``, which is the
    ``ApplyGuardrail`` spelling of the same "only tagged spans are guarded" rule the
    ``InvokeModel`` path expresses with ``guardContent`` tags.

    *Unverified against a live account.* Written from the API reference; AWS credentials
    are not valid on the build machine (PL-3).
    """

    guardrail_id: str
    guardrail_version: str
    region: str
    client: Any

    @classmethod
    def from_settings(
        cls,
        *,
        guardrail_id: str | None,
        guardrail_version: str = "DRAFT",
        region: str = "ap-southeast-2",
        allow_live: bool = False,
        client: Any = None,
    ) -> BedrockGuardrailScreen:
        """Construct the live screen, or refuse and say which precondition failed.

        Raises:
            GuardrailUnavailable: no identifier, no opt-in, or no ``boto3``.
        """
        if not guardrail_id:
            raise GuardrailUnavailable(
                "no guardrail identifier configured; the live screen has nothing to apply"
            )
        if not allow_live:
            raise GuardrailUnavailable(
                "the live Bedrock Guardrails screen requires an explicit opt-in "
                "(allow_live=True). CI runs the local screen, which does not claim to be "
                "Guardrails; silently substituting one for the other is the defect."
            )
        resolved = client
        if resolved is None:
            try:
                # Imported here so that the package's stdlib-only import graph survives:
                # nothing that reads hostile text pulls in an AWS SDK on import.
                import boto3
            except ImportError as exc:  # pragma: no cover - exercised only with the extra
                raise GuardrailUnavailable(
                    "boto3 is not installed; install mainline-quarantine[bedrock]"
                ) from exc
            resolved = boto3.client("bedrock-runtime", region_name=region)
        return cls(
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
            region=region,
            client=resolved,
        )

    def request(self, text: str) -> dict[str, Any]:
        """Build the exact ``ApplyGuardrail`` request this screen sends, as a dict.

        Exposed so a test can assert the shape without a network, and so a reviewer can
        read the request rather than infer it from a call site.
        """
        return {
            "guardrailIdentifier": self.guardrail_id,
            "guardrailVersion": self.guardrail_version,
            "source": "INPUT",
            "outputScope": "FULL",
            "content": [{"text": {"text": text, "qualifiers": ["guard_content"]}}],
        }

    def screen(self, text: str) -> ScreenResult:
        """Apply the live guardrail to one untrusted span."""
        from .classes import Layer, Outcome
        from .normalise import span_sha256
        from .screen import ScreenResult

        response = self.client.apply_guardrail(**self.request(text))
        if not guardrail_intervened(response):
            return ScreenResult(
                outcome=Outcome.CLEAN,
                layer=Layer.L2_DELIMIT_AND_DATAMARK,
                detector="",
                attack_class=None,
                span=(0, 0),
                span_sha256="",
                evidence="",
                screen="bedrock-guardrails",
            )
        reason = str(response.get("actionReason", "")) or "guardrail intervened"
        return ScreenResult(
            outcome=Outcome.BLOCKED_PROMPT_ATTACK,
            layer=Layer.L2_DELIMIT_AND_DATAMARK,
            detector="bedrock:PROMPT_ATTACK",
            # Bedrock reports that it intervened, not WHICH shape of attack it saw.
            # Naming a class here would be inventing evidence.
            attack_class=None,
            span=(0, len(text)),
            span_sha256=span_sha256(text),
            evidence=reason,
            screen="bedrock-guardrails",
        )
