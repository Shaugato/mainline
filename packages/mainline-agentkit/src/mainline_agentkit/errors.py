# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal vocabulary.

Every failure this package can produce has a *name*, and the name is the product
surface: it is what appears in an operator message, in a `silence_ledger` row, and
in the ADR that explains why a merge did not happen. A generic ``ValueError`` here
would be a refusal nobody can act on.

Two rules hold across the whole hierarchy.

* **Nothing is absorbed.** There is no exception in this module that any code path
  in this package catches and converts into a default value. In a product whose
  deliverable is a refusal, swallowing an exception is the defect class.
* **Unknown means refused.** :class:`UnknownStopReason` exists because a stop reason
  this package has never seen must fail closed. A future model generation that adds
  a stop reason we treat as success is exactly how a silent extraction failure
  becomes a silent memory gap.

Naming note: these classes deliberately do not end in ``Error``. ``ModelRefused``,
``ResidencyRefused`` and ``ColdFanout`` are the words this system uses in prose, and
``ruff``'s ``N818`` is disabled repository-wide for that reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "AgentkitError",
    "CachePrefixTooSmall",
    "CassetteMiss",
    "CassettePrefixDrift",
    "ColdFanout",
    "ConfigurationRefused",
    "DeadLettered",
    "ForbiddenRequestField",
    "ModelRefused",
    "ProfileNotPinned",
    "ProfileUnknown",
    "ResidencyRefused",
    "RuntimeAlreadyBooted",
    "RuntimeNotBooted",
    "RuntimeRefusing",
    "SchemaViolation",
    "ToolFormDisabled",
    "ToolSurfaceConstructed",
    "TransportUnavailable",
    "TruncatedResponse",
    "UnknownStopReason",
    "UnsupportedSchema",
    "UntrustedTextInSystemPrompt",
    "WarmTimeout",
]


class AgentkitError(Exception):
    """Base class for every refusal this package can raise."""


class ConfigurationRefused(AgentkitError):
    """The process is configured in a way that must not be allowed to serve traffic."""


class ResidencyRefused(ConfigurationRefused):
    """A model identifier that is not an Australian inference profile was resolved.

    §10.1 pins the residency control to a VPC-endpoint policy enumerating ``au.*``
    inference-profile ARNs. A ``global.*`` profile routes to every commercial Region
    and an ``apac.*`` profile can take a Queensland fatality narrative offshore. Both
    are arguments we lose in the room, so the process refuses to serve rather than
    resolving one.
    """

    def __init__(self, identifier: str, reason: str) -> None:
        """Record the offending identifier and why it was refused."""
        super().__init__(
            f"refusing to serve: {identifier!r} is not an Australian inference profile "
            f"({reason}). ARCHITECTURE.md §10.1 permits au.* profile identifiers only."
        )
        self.identifier = identifier
        self.reason = reason


class ProfileUnknown(ConfigurationRefused):
    """A call profile id was requested that the register does not contain."""

    def __init__(self, profile_id: str, known: Sequence[str]) -> None:
        """Name the missing profile and list the ones that exist."""
        super().__init__(f"unknown call profile {profile_id!r}; registered: {sorted(known)}")
        self.profile_id = profile_id


class ProfileNotPinned(ConfigurationRefused):
    """A call was attempted through a profile the booted run record does not pin.

    Two shapes reach here and both are the same defect. An id the register never held,
    and — the sharper one — an id the register *does* hold whose bytes have since been
    edited at the call site. The run record attests a ``prompt_version`` and a
    ``prompt_sha256`` per profile; serving a call under different bytes would produce
    provenance naming a prompt that was never pinned, which is exactly the quiet prompt
    edit decision A13 exists to make impossible.
    """

    def __init__(self, profile_id: str, reason: str, pinned: Sequence[str]) -> None:
        """Name the profile, why it is not the pinned one, and what is pinned."""
        super().__init__(
            f"profile {profile_id!r} is not pinned by this run record ({reason}); "
            f"pinned: {sorted(pinned)}. A prompt edit is a commit, not a call-site "
            f"argument (ARCHITECTURE.md §8.2, decision A13)."
        )
        self.profile_id = profile_id
        self.reason = reason


class RuntimeNotBooted(ConfigurationRefused):
    """The process runtime was asked to serve before it was booted.

    §10.1 layer 1 is an ``au.*``-prefix assertion **at process start-up**. Returning
    ``None`` here would let a caller reach the model without that assertion ever having
    run, so the absence of a runtime is a refusal rather than a missing value.
    """


class RuntimeAlreadyBooted(ConfigurationRefused):
    """A second boot was attempted while a runtime was already serving.

    A second boot would swap the pinned inference-profile ARN underneath calls already
    in flight, and the run record they were attributed to would no longer describe the
    process that served them.
    """


class RuntimeRefusing(ConfigurationRefused):
    """This process refused to serve at start-up and has not been reset.

    The refusal **latches**. A retry loop around a residency refusal is how a residency
    refusal becomes a warning, so every later call — including another boot — is refused
    with the original reason attached until the latch is cleared explicitly.
    """

    def __init__(self, reason: str) -> None:
        """Carry the original start-up refusal forward, verbatim."""
        super().__init__(
            f"this process refused to serve at start-up and the refusal has not been "
            f"cleared. Original refusal: {reason}"
        )
        self.reason = reason


class TransportUnavailable(ConfigurationRefused):
    """The selected transport cannot be constructed in this process.

    Raised when ``MAINLINE_AGENT_PROVIDER=bedrock`` but ``boto3`` is absent, and when
    the live provider is selected without ``MAINLINE_AGENT_ALLOW_LIVE=1``. A live call
    that happens by accident costs money and non-determinism, and CI must fail loudly
    rather than pay for it.
    """


class UnsupportedSchema(ConfigurationRefused):
    """A Pydantic model cannot be expressed as a Bedrock-legal JSON Schema.

    The only case this package refuses outright is **recursion**: a ``$ref`` cycle
    cannot be inlined, and silently truncating it would hand the model a schema that
    does not describe the type we then validate against.
    """


class ForbiddenRequestField(AgentkitError):
    """A request body carried a field that is banned everywhere in this repository.

    Decision A6: ``temperature``, ``top_p`` and ``top_k`` return 400 on this model
    generation, and the honest claim was never reproducibility. A parameter that
    cannot exist cannot be blamed for drift.
    """

    def __init__(self, field: str, path: str) -> None:
        """Name the banned field and the JSON path it appeared at."""
        super().__init__(
            f"banned request field {field!r} at {path}: no sampling parameter may appear "
            f"in any MAINLINE request body (decision A6)."
        )
        self.field = field
        self.path = path


class ToolSurfaceConstructed(AgentkitError):
    """A request body carried ``tools``, ``tool_choice`` or ``toolConfig``.

    This is the runtime half of the CaMeL structural quarantine. The compile-time half
    is that :func:`mainline_agentkit.call.quarantined_call` has no ``tools`` parameter
    and the AST scan in ``scripts/agents/assert_no_tool_construction.py`` refuses a
    tree that constructs one.
    """

    def __init__(self, field: str, path: str) -> None:
        """Name the tool-surface key and where it appeared."""
        super().__init__(
            f"tool surface {field!r} constructed at {path}: the quarantined call shape "
            f"holds no tools. See ARCHITECTURE.md §8.4 layer 1."
        )
        self.field = field
        self.path = path


class UntrustedTextInSystemPrompt(AgentkitError):
    """Untrusted document text was found inside a system block.

    Layer 1 of the six-layer posture is that document text never enters a system
    prompt. This is checked on the built body rather than trusted to a convention,
    because a convention is not a control.
    """


class ModelRefused(AgentkitError):
    """The model declined, and the decline is a row in the silence ledger.

    Decision A8. Our corpus is cyanide leaching, H2S and confined-space chemistry, so
    a refusal on a clean document is expected rather than exceptional. **A precursor
    the model declined to summarise must still block the merge**, which is why this is
    an exception the caller converts into a `silence_ledger` row and a deterministic
    fallback, never a `None` that quietly shrinks a candidate set.
    """

    def __init__(self, category: str, stop_reason: str | None, detail: str = "") -> None:
        """Record the refusal category and the stop reason that produced it."""
        suffix = f": {detail}" if detail else ""
        super().__init__(
            f"model refused (category={category}, stop_reason={stop_reason!r}){suffix}"
        )
        self.category = category
        self.stop_reason = stop_reason
        self.detail = detail


class TruncatedResponse(AgentkitError):
    """``stop_reason`` was ``max_tokens`` (or the context window was exceeded).

    Decision A5: ``max_tokens`` caps thinking **plus** text, so a truncated response is
    a response whose JSON is either invalid or — far worse — valid and short. Never
    absorbed, never retried with a bigger budget by this package: the profile's token
    floor is a committed number and a breach of it is a change to the profile.
    """

    def __init__(self, stop_reason: str, max_tokens: int, output_tokens: int) -> None:
        """Record the budget and what was actually produced."""
        super().__init__(
            f"response truncated (stop_reason={stop_reason!r}, max_tokens={max_tokens}, "
            f"output_tokens={output_tokens}): a truncated structured output is a silent "
            f"memory gap, so this is fatal (decision A5)."
        )
        self.stop_reason = stop_reason
        self.max_tokens = max_tokens
        self.output_tokens = output_tokens


class UnknownStopReason(AgentkitError):
    """A stop reason this package has never seen. Fail closed."""

    def __init__(self, stop_reason: str | None, known: Sequence[str]) -> None:
        """Record the unrecognised stop reason and the set we do recognise."""
        super().__init__(
            f"unrecognised stop_reason {stop_reason!r}; known: {sorted(known)}. "
            f"A stop reason we cannot classify is refused, never treated as success."
        )
        self.stop_reason = stop_reason


class SchemaViolation(AgentkitError):
    """The parsed payload did not validate against the profile's output model."""

    def __init__(self, profile_id: str, detail: str, payload_sha256: str) -> None:
        """Record which profile, which validator complaint, and which payload."""
        super().__init__(f"schema violation on profile {profile_id!r}: {detail}")
        self.profile_id = profile_id
        self.detail = detail
        self.payload_sha256 = payload_sha256


class DeadLettered(AgentkitError):
    """One retry was spent on the validator error and the second attempt also failed.

    §8.4: *a schema violation gets one retry with the validator error appended, then
    dead-letters — never a free-text retry loop, because a retry loop against an
    ill-posed prompt is how a silent extraction failure becomes a silent memory gap.*
    """

    def __init__(self, profile_id: str, attempts: int, record: Mapping[str, object]) -> None:
        """Record the profile, the attempt count and the full dead-letter record."""
        super().__init__(
            f"dead-lettered profile {profile_id!r} after {attempts} attempts; "
            f"no further retry is permitted (ARCHITECTURE.md §8.4)."
        )
        self.profile_id = profile_id
        self.attempts = attempts
        self.record = dict(record)


class CassetteMiss(AgentkitError):
    """No recorded interaction exists for this key, and replay never falls through.

    A cassette provider that quietly reached the network on a miss would make every
    green CI run a claim about a call that may never have been recorded.
    """

    def __init__(self, key: str, root: str) -> None:
        """Record the missing key and the store it was looked for in."""
        super().__init__(
            f"cassette miss for key {key} under {root}: replay mode never falls through "
            f"to a live call. Re-record with tests/make_cassettes.py."
        )
        self.key = key
        self.root = root


class CassettePrefixDrift(AgentkitError):
    """A cassette was recorded against a different frozen system prefix.

    AR-7 says cassette drift is accepted and named. This is the part that is *not*
    accepted: replaying a recording made against a different rubric would let a prompt
    edit pass CI unnoticed, which decision A13 exists to prevent.
    """

    def __init__(self, key: str, recorded: str, observed: str) -> None:
        """Record the key and both prefix digests."""
        super().__init__(
            f"cassette {key} was recorded against prefix {recorded} but this process "
            f"built prefix {observed}: the frozen system prefix changed."
        )
        self.key = key
        self.recorded = recorded
        self.observed = observed


class CachePrefixTooSmall(AgentkitError):
    """The frozen system prefix is below the model generation's cacheable minimum.

    Decision A4/A9. Below the minimum the ``cache_control`` breakpoint is accepted and
    silently does nothing, so every fan-out call pays full price and the assertion
    ``cache_read_input_tokens > 0`` can never become true. An un-asserted cache is
    usually a broken cache, so this is loud.
    """

    def __init__(self, profile_id: str, estimated: int, minimum: int) -> None:
        """Record the estimate, the minimum and the profile it applies to."""
        super().__init__(
            f"profile {profile_id!r} has an estimated {estimated}-token cacheable prefix, "
            f"below the {minimum}-token minimum for its model generation: the "
            f"cache_control breakpoint would be accepted and do nothing."
        )
        self.profile_id = profile_id
        self.estimated = estimated
        self.minimum = minimum


class ColdFanout(AgentkitError):
    """A fan-out call was attempted before the shared prefix was warmed.

    Decision A9: a cache entry is readable only once the first response *begins
    streaming*. N parallel calls sharing a prefix that has never been warmed all pay
    full price, which looks exactly like a working cache until the bill arrives.
    """

    def __init__(self, prefix_digest: str) -> None:
        """Record the prefix digest that was never warmed."""
        super().__init__(
            f"cold fan-out refused: prefix {prefix_digest} has not been warmed in this "
            f"process. Use warm_then_fanout() (decision A9)."
        )
        self.prefix_digest = prefix_digest


class WarmTimeout(AgentkitError):
    """The warming call did not reach its first streamed token within the budget."""

    def __init__(self, prefix_digest: str, timeout_s: float) -> None:
        """Record the prefix and the budget that elapsed."""
        super().__init__(
            f"warming call for prefix {prefix_digest} produced no first token within "
            f"{timeout_s}s; refusing to fan out cold."
        )
        self.prefix_digest = prefix_digest
        self.timeout_s = timeout_s


class ToolFormDisabled(ConfigurationRefused):
    """The AR-1 tool-form fallback was invoked while it is switched off.

    ``fallback_toolform`` is written and unused. It is reachable only by setting
    ``MAINLINE_AR1_FALLBACK=1`` **and** passing the switch explicitly, so it cannot be
    entered by an import or a default.
    """
