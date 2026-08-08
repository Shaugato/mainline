# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Process start-up: resolve the profile, assert residency, pin the record, then serve.

ARCHITECTURE.md §10.1 states the residency control in three layers, and the **first**
one is *"an ``au.*``-prefix assertion at process start-up"*. The other two are a
VPC-endpoint policy on ``bedrock-runtime`` and an unset ``crossRegionConfig`` on every
Guardrail; both are infrastructure, and neither is in this repository's Python. This
module is layer one, and it exists because an assertion that lives inside the transport
runs per call, on the live path only, and can be skipped by a caller who passes
``model_id=`` by hand. *A control a caller can decline is not a control.*

**What boot does, in order, refusing at the first failure.**

1. Reads the call-profile register and derives the one model generation the fleet uses.
   Two generations in one register is a refusal (decision A4): a run record pins exactly
   one inference-profile ARN, so a fleet spanning two generations cannot be described by
   one true record.
2. Resolves that generation to an inference-profile ARN — on the live provider from
   ``bedrock:ListInferenceProfiles``, never from a literal in our source (AR-2 makes a
   generation change a *data* change). ``tests/test_runtime.py`` asserts that no ARN
   appears in this file at all.
3. Asserts the resolved identifier is an Australian inference profile. A ``global.*``
   profile routes to every commercial Region and a bare foundation-model id bypasses the
   very ARNs the endpoint policy enumerates. Either one is refused, and the refusal is
   terminal.
4. Pins everything a later claim will need — the ARN, the region, the provider, the
   package version and, per profile, the ``prompt_version``, ``prompt_sha256`` and
   ``schema_version`` — into an immutable :class:`RunRecord`.

**Offline runs are pinned too.** The cassette provider is the CI default, and a replay
must still name the profile it is replaying: ``MAINLINE_INFERENCE_PROFILE_ARN`` or the
``inference_profile_arn=`` argument. That declaration is then **cross-checked against
the model id recorded in the cassettes**, so a replay cannot claim provenance from a
profile the recordings were never made against. It is the model-id analogue of the
prefix-drift refusal, and it costs one pass over a directory of small JSON files.

**A start-up refusal latches.** :func:`boot_runtime` records the refusal
process-wide; :func:`current_runtime` and every later boot then raise
:class:`~mainline_agentkit.errors.RuntimeRefusing` carrying the original reason until
:func:`shutdown_runtime` is called with ``force=True``. A retry loop around a residency
refusal is how a residency refusal becomes a warning.

**This module holds no new capability.** It has no ``tools`` parameter, constructs no
request body of its own, opens no database connection and holds no credential. It binds
the pieces :mod:`mainline_agentkit.call` already refuses to let anyone misuse, and it
makes the binding attributable.

**Unverified, and stated rather than implied.** The live control-plane leg — that
``bedrock:ListInferenceProfiles`` returns an Australian profile for this generation in
this account — has **not** been executed: AWS credentials are not valid on the build
machine as of 2026-08-07 (PL-3), and ``GT-11`` is the day-1 check that settles it. Every
test here drives the resolver through an injected client or through a declared ARN, so
what is proven is *our* refusal behaviour, not the account's inventory. AR-2 is the
pre-committed answer if the inventory disappoints, and it is a data change by
construction.
"""

from __future__ import annotations

import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ._canon import canonical_json_bytes, sha256_hex
from .call import quarantined_call, warm_then_fanout
from .cassette import CassetteTransport
from .errors import (
    ConfigurationRefused,
    ProfileNotPinned,
    RuntimeAlreadyBooted,
    RuntimeNotBooted,
    RuntimeRefusing,
)
from .profiles import PROFILES
from .refusal import silence_row_for_refusal
from .transport import (
    AgentkitSettings,
    assert_australian_profile,
    resolve_inference_profile,
    select_transport,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from pydantic import BaseModel

    from .call import FanoutInput, UntrustedText, Validated
    from .cassette import CassetteStore
    from .errors import ModelRefused
    from .profiles import CallProfile
    from .refusal import SilenceRow
    from .transport import Transport

__all__ = [
    "IDENTITY_COMPONENT_ORDER",
    "INFERENCE_PROFILE_ARN_ENV",
    "RUN_RECORD_VERSION",
    "AgentkitRuntime",
    "ProfilePin",
    "RunRecord",
    "boot_runtime",
    "current_runtime",
    "is_serving",
    "shutdown_runtime",
]

#: Bumped when the run-record shape changes. A consumer that stored yesterday's records
#: can then tell which shape it is reading rather than inferring it from a missing key.
RUN_RECORD_VERSION = "1"

#: Where an offline run declares the profile it is replaying.
INFERENCE_PROFILE_ARN_ENV = "MAINLINE_INFERENCE_PROFILE_ARN"

#: The seven components of ``agent_identity`` (ARCHITECTURE.md §8.2), **in the order the
#: formula concatenates them**. This package supplies the components and deliberately
#: does not hash them: ``mainline-provenance`` owns the formula, and two implementations
#: of one digest is one implementation too many.
IDENTITY_COMPONENT_ORDER: tuple[str, ...] = (
    "agent_name",
    "sql_role",
    "iam_role_arn",
    "prompt_version",
    "model_id",
    "inference_profile_arn",
    "schema_version",
)

#: Stated wherever residency is mentioned, because F5 measured the split: inference is
#: in Australia, the demo cluster is not. This package pins the first and knows nothing
#: about the second, and says exactly that rather than implying more.
RESIDENCY_NOTE = (
    "Inference is pinned to au.* inference profiles in the configured Bedrock region. "
    "This package pins inference only and makes no claim about database residency; on "
    "the free demo tier the cluster is not in Australia, so end-to-end Australian data "
    "residency is FALSE for that deployment and is never claimed."
)

_RUN_ID_BYTES = 16


@dataclass(frozen=True, slots=True)
class ProfilePin:
    """What the run record fixes about one call profile.

    These are the fields a later claim about a model action depends on: which prompt
    bytes were loaded (``prompt_version`` plus its content address), which schema the
    output was constrained by, and what the budget was. A profile whose bytes move
    without the record moving is the quiet prompt edit decision A13 forbids.
    """

    profile_id: str
    agent: str
    tier: str
    effort: str
    prompt_version: str
    prompt_sha256: str
    schema_version: str
    max_tokens: int
    may_write_gate_field: bool

    @classmethod
    def of(cls, profile: CallProfile[Any]) -> ProfilePin:
        """Pin a profile as it stands at boot."""
        return cls(
            profile_id=profile.profile_id,
            agent=profile.agent,
            tier=str(profile.tier),
            effort=str(profile.effort),
            prompt_version=profile.prompt_version,
            prompt_sha256=profile.prompt_sha256(),
            schema_version=profile.schema_version,
            max_tokens=profile.max_tokens,
            may_write_gate_field=profile.may_write_gate_field,
        )

    def to_mapping(self) -> dict[str, Any]:
        """Ledger-shaped form."""
        return {
            "profile_id": self.profile_id,
            "agent": self.agent,
            "tier": self.tier,
            "effort": self.effort,
            "prompt_version": self.prompt_version,
            "prompt_sha256": self.prompt_sha256,
            "schema_version": self.schema_version,
            "max_tokens": self.max_tokens,
            "may_write_gate_field": self.may_write_gate_field,
        }


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Everything this process pinned at start-up, and nothing it learned later.

    The record is what makes a model action attributable *without trusting the caller*:
    every served call reports the same ARN, the same region and the same prompt digests,
    because they were fixed before the first call was built.

    Attributes:
        run_id: unique to this process. Two runs of identical code differ here and
            nowhere else, which is why :meth:`configuration_sha256` excludes it.
        resolution: how the ARN was obtained — the control-plane call, or a declaration
            for an offline replay. A reader must be able to tell those apart.
        cassette_model_ids_checked: how many distinct model ids the cassette store held
            when the declared ARN was cross-checked. ``0`` means the check found nothing
            to check, which is recorded rather than reported as a pass.
    """

    record_version: str
    run_id: str
    started_at: str
    agentkit_version: str
    provider: str
    transport: str
    region: str
    cassette_mode: str
    model_key: str
    inference_profile_id: str
    inference_profile_arn: str
    resolution: str
    residency_note: str
    cassette_model_ids_checked: int
    profiles: tuple[ProfilePin, ...]

    def to_mapping(self) -> dict[str, Any]:
        """Render the full record, ledger-shaped and JCS-canonicalisable."""
        return {
            "record_version": self.record_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "agentkit_version": self.agentkit_version,
            "provider": self.provider,
            "transport": self.transport,
            "region": self.region,
            "cassette_mode": self.cassette_mode,
            "model_key": self.model_key,
            "inference_profile_id": self.inference_profile_id,
            "inference_profile_arn": self.inference_profile_arn,
            "resolution": self.resolution,
            "residency_note": self.residency_note,
            "cassette_model_ids_checked": self.cassette_model_ids_checked,
            "profiles": [pin.to_mapping() for pin in self.profiles],
        }

    def configuration_sha256(self) -> str:
        """Content address of the *configuration*, with the run identity removed.

        Two processes running the same code, the same prompts and the same profile ARN
        produce the same digest; a prompt edit, a region change or a swapped ARN moves
        it. That is what makes "the fleet did not change between these two runs" a
        checkable statement rather than an assurance.
        """
        payload = self.to_mapping()
        del payload["run_id"]
        del payload["started_at"]
        return sha256_hex(canonical_json_bytes(payload))

    def pin(self, profile_id: str) -> ProfilePin:
        """Return the pin for ``profile_id``.

        Raises:
            ProfileNotPinned: when this record does not pin that profile.
        """
        for candidate in self.profiles:
            if candidate.profile_id == profile_id:
                return candidate
        raise ProfileNotPinned(
            profile_id,
            "the run record pins no profile of that id",
            tuple(pin.profile_id for pin in self.profiles),
        )

    def identity_components(
        self,
        *,
        agent_name: str,
        sql_role: str,
        iam_role_arn: str,
        profile_id: str,
    ) -> dict[str, str]:
        """Return the seven ``agent_identity`` components, in concatenation order.

        The three this package cannot know — the agent's name, its SQL role and its IAM
        role — are arguments; the four it pinned at boot are filled in. ``model_id``
        carries the model **generation** and ``inference_profile_arn`` the routing ARN:
        read any other way the formula would hash one fact twice.

        The digest itself is computed by ``mainline-provenance``. Returning components
        rather than a hash is deliberate — a second implementation of the formula is a
        second answer to "which identity signed this", and §8.2 admits only one.

        Raises:
            ProfileNotPinned: when this record does not pin ``profile_id``.
        """
        pinned = self.pin(profile_id)
        return {
            "agent_name": agent_name,
            "sql_role": sql_role,
            "iam_role_arn": iam_role_arn,
            "prompt_version": pinned.prompt_version,
            "model_id": self.model_key,
            "inference_profile_arn": self.inference_profile_arn,
            "schema_version": pinned.schema_version,
        }


@dataclass(frozen=True, slots=True)
class AgentkitRuntime:
    """A booted process: one pinned ARN, one register, one transport.

    Every method that reaches a model goes through :func:`quarantined_call` or
    :func:`warm_then_fanout` with the pinned ARN injected, so a caller cannot serve a
    call under a model identifier the run record does not name. There is no ``tools``
    parameter here either — the quarantine is the call shape, and this class does not
    widen it.
    """

    run_record: RunRecord
    transport: Transport
    settings: AgentkitSettings
    register: Mapping[str, CallProfile[Any]] = field(repr=False)

    # ── start-up ────────────────────────────────────────────────────────────────

    @classmethod
    def boot(
        cls,
        *,
        settings: AgentkitSettings | None = None,
        transport: Transport | None = None,
        control_plane: Any = None,
        inference_profile_arn: str | None = None,
        profiles: Mapping[str, CallProfile[Any]] | None = None,
        cassette_root: Path | None = None,
        run_id: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> AgentkitRuntime:
        """Resolve, assert, pin, and return a runtime that may serve.

        Args:
            settings: process settings; read from the environment when omitted.
            transport: the provider. Built from ``settings`` when omitted, which on the
                default configuration is the offline cassette provider.
            control_plane: a ``bedrock`` control-plane client, injected by tests. Built
                from ``boto3`` when omitted **and** the live provider is selected.
            inference_profile_arn: the declared ARN. Required for an offline replay;
                on the live provider it is optional and, if given, must equal what the
                control plane resolves.
            profiles: the call-profile register. Defaults to the shipped one.
            cassette_root: overrides the cassette directory when building the transport.
            run_id: injected only by callers that mint run ids elsewhere.
            env: environment mapping; defaults to the process environment.

        Raises:
            ResidencyRefused: the resolved identifier is not an Australian inference
                profile, or no such profile exists for this generation (AR-2).
            ConfigurationRefused: the register spans two model generations, no ARN was
                declared for an offline run, the declared ARN names a different
                generation or disagrees with the control plane, or it names a profile
                the cassettes were never recorded against.
        """
        resolved_settings = settings or AgentkitSettings.from_env()
        register = dict(PROFILES if profiles is None else profiles)
        if not register:
            raise ConfigurationRefused(
                "the call-profile register is empty: a run record that pins no profile "
                "cannot attribute anything, so this process refuses to serve"
            )
        model_key = _single_generation(register)
        wire = (
            transport
            if transport is not None
            else select_transport(resolved_settings, cassette_root=cassette_root)
        )
        declared = inference_profile_arn or (os.environ if env is None else env).get(
            INFERENCE_PROFILE_ARN_ENV
        )

        if resolved_settings.provider == "bedrock":
            resolved = resolve_inference_profile(
                model_key, client=control_plane, region=resolved_settings.region
            )
            arn = resolved.profile_arn
            resolution = "bedrock:ListInferenceProfiles"
            if declared and declared != arn:
                raise ConfigurationRefused(
                    f"the declared inference profile {declared!r} is not the one the "
                    f"control plane resolved ({arn!r}). A deploy-time pin that "
                    f"disagrees with the account is a pin nobody can trust, so this "
                    f"process refuses to serve rather than choosing one of them."
                )
        else:
            if not declared:
                raise ConfigurationRefused(
                    f"provider {resolved_settings.provider!r} does not reach the "
                    f"control plane, so the inference profile must be declared: set "
                    f"{INFERENCE_PROFILE_ARN_ENV} or pass inference_profile_arn=. A "
                    f"replay that cannot name the profile it replays cannot carry its "
                    f"provenance either."
                )
            arn = declared
            resolution = f"declared ({resolved_settings.provider} replay)"

        # §10.1 layer 1, and the only place in this package it runs unconditionally.
        profile_identifier = assert_australian_profile(arn)
        if model_key not in profile_identifier:
            raise ConfigurationRefused(
                f"inference profile {profile_identifier!r} does not name the model "
                f"generation {model_key!r} the profile register uses. The run record "
                f"would claim a generation the endpoint would not serve."
            )
        checked = _cross_check_cassettes(wire, arn)

        # Imported here, not at module scope: the package `__init__` re-exports this
        # module, so a module-level `from . import __version__` would run while the
        # package is still half-initialised. PLC0415 is disabled repo-wide for exactly
        # this shape and it is documented at every site.
        from . import __version__

        record = RunRecord(
            record_version=RUN_RECORD_VERSION,
            run_id=run_id or secrets.token_hex(_RUN_ID_BYTES),
            started_at=datetime.now(tz=UTC).isoformat(),
            agentkit_version=__version__,
            provider=resolved_settings.provider,
            transport=type(wire).__name__,
            region=resolved_settings.region,
            cassette_mode=resolved_settings.cassette_mode,
            model_key=model_key,
            inference_profile_id=profile_identifier,
            inference_profile_arn=arn,
            resolution=resolution,
            residency_note=RESIDENCY_NOTE,
            cassette_model_ids_checked=checked,
            profiles=tuple(ProfilePin.of(register[key]) for key in sorted(register)),
        )
        return cls(
            run_record=record,
            transport=wire,
            settings=resolved_settings,
            register=register,
        )

    # ── serving ─────────────────────────────────────────────────────────────────

    @property
    def model_id(self) -> str:
        """The pinned inference-profile ARN every served call is issued against."""
        return self.run_record.inference_profile_arn

    def profile(self, profile_id: str) -> CallProfile[Any]:
        """Look up a pinned profile by id.

        Raises:
            ProfileNotPinned: when the register this process booted with has no such
                profile.
        """
        try:
            return self.register[profile_id]
        except KeyError as exc:
            raise ProfileNotPinned(
                profile_id, "no profile of that id is registered", tuple(self.register)
            ) from exc

    def call[T: BaseModel](
        self,
        profile: CallProfile[T],
        untrusted: UntrustedText,
        trusted_context: Mapping[str, Any],
        *,
        sentinel: str | None = None,
    ) -> Validated[T]:
        """Issue one zero-tool, schema-constrained call against the pinned ARN.

        Raises:
            ProfileNotPinned: the profile is not the one this run record pinned.
            ModelRefused: the model declined. Turn it into a row with
                :meth:`silence_row`; it is never an empty result.
            TruncatedResponse: ``max_tokens`` was hit. Fatal by decision A5.
            DeadLettered: the schema violation survived its one retry.
        """
        self._require_pinned(profile)
        return quarantined_call(
            profile,
            untrusted,
            trusted_context,
            transport=self.transport,
            model_id=self.model_id,
            settings=self.settings,
            sentinel=sentinel,
        )

    def fanout[T: BaseModel](
        self,
        profile: CallProfile[T],
        inputs: Sequence[FanoutInput],
        *,
        max_workers: int = 4,
    ) -> list[Validated[T]]:
        """Warm the shared prefix on one call, then fan the rest out (decision A9).

        Raises:
            ProfileNotPinned: the profile is not the one this run record pinned.
            WarmTimeout: the warming call produced no first token inside the budget.
        """
        self._require_pinned(profile)
        return warm_then_fanout(
            profile,
            inputs,
            transport=self.transport,
            model_id=self.model_id,
            settings=self.settings,
            max_workers=max_workers,
        )

    def provenance(self, validated: Validated[Any]) -> dict[str, Any]:
        """Merge the call's replayability record with what this process pinned.

        The result is what a caller writes into ``agent_action_provenance`` and
        ``recall_run``: the run identity and the pinned ARN on the same row as the input
        and output digests, so a claim about one call can be checked against the process
        that served it without a join through a config file.
        """
        return {
            "run_id": self.run_record.run_id,
            "configuration_sha256": self.run_record.configuration_sha256(),
            "provider": self.run_record.provider,
            "transport": self.run_record.transport,
            "region": self.run_record.region,
            "agentkit_version": self.run_record.agentkit_version,
            "model_key": self.run_record.model_key,
            "inference_profile_id": self.run_record.inference_profile_id,
            "inference_profile_arn": self.run_record.inference_profile_arn,
            **validated.provenance(),
        }

    def silence_row(
        self,
        refusal: ModelRefused,
        *,
        profile_id: str,
        site_id: str,
        source: str,
        subject_kind: str,
        subject_id: str,
        severity: int,
        input_sha256: str,
        policy_version: str | None = None,
    ) -> SilenceRow:
        """Build the ``silence_ledger`` row for a refusal, with the pin filled in.

        Decision A8: *a precursor the model declined to summarise must still block the
        merge.* This package holds no driver and no credential — the row is returned for
        the caller to write through its own SQL role.

        Raises:
            ProfileNotPinned: when this record does not pin ``profile_id``.
        """
        pinned = self.run_record.pin(profile_id)
        return silence_row_for_refusal(
            refusal,
            site_id=site_id,
            source=source,
            subject_kind=subject_kind,
            subject_id=subject_id,
            severity=severity,
            profile_id=pinned.profile_id,
            prompt_version=pinned.prompt_version,
            model_id=self.run_record.model_key,
            inference_profile_arn=self.model_id,
            input_sha256=input_sha256,
            policy_version=policy_version,
        )

    # ── internals ───────────────────────────────────────────────────────────────

    def _require_pinned(self, profile: CallProfile[Any]) -> None:
        """Refuse a call through anything the run record did not pin.

        A byte-identical copy of a pinned profile is accepted — it *is* the pinned call.
        A profile carrying the same id under different prompt bytes, a different schema
        version or a different budget is refused, because serving it would attribute the
        result to a prompt this process never pinned.
        """
        registered = self.register.get(profile.profile_id)
        if registered is None:
            raise ProfileNotPinned(
                profile.profile_id,
                "no profile of that id is registered",
                tuple(self.register),
            )
        if registered is profile:
            return
        pinned = self.run_record.pin(profile.profile_id)
        drifted = [
            f"{name}: pinned {expected!r}, call carries {actual!r}"
            for name, expected, actual in (
                ("prompt_version", pinned.prompt_version, profile.prompt_version),
                ("prompt_sha256", pinned.prompt_sha256, profile.prompt_sha256()),
                ("schema_version", pinned.schema_version, profile.schema_version),
                ("max_tokens", str(pinned.max_tokens), str(profile.max_tokens)),
            )
            if expected != actual
        ]
        if drifted:
            raise ProfileNotPinned(profile.profile_id, "; ".join(drifted), tuple(self.register))


def _single_generation(register: Mapping[str, CallProfile[Any]]) -> str:
    """Return the one model generation the register uses.

    Raises:
        ConfigurationRefused: when the register names more than one. Decision A4 ships
            one generation across the whole fleet, differentiated by ``effort``; a run
            record pins one ARN, so two generations cannot both be true of it.
    """
    generations = sorted({profile.model_key for profile in register.values()})
    if len(generations) != 1:
        raise ConfigurationRefused(
            f"the call-profile register spans model generations {generations}: decision "
            f"A4 ships one generation across the whole fleet, differentiated by "
            f"output_config.effort, and a run record pins exactly one inference-profile "
            f"ARN. Two generations cannot both be pinned by one record."
        )
    return generations[0]


def _cross_check_cassettes(wire: Transport, arn: str) -> int:
    """Refuse a replay that claims an ARN the recordings were never made against.

    Returns:
        The number of distinct model ids found in the store. ``0`` means there was
        nothing to check, which the run record states rather than treating as a pass.

    Raises:
        ConfigurationRefused: when the store holds recordings and none of them was made
            against ``arn``.
    """
    if not isinstance(wire, CassetteTransport):
        return 0
    recorded = _recorded_model_ids(wire.store)
    if not recorded:
        return 0
    if arn not in recorded:
        raise ConfigurationRefused(
            f"the declared inference profile {arn!r} is not one the cassettes were "
            f"recorded against ({recorded}). A replay that claims a profile it never "
            f"ran on would put a false ARN into every provenance row this process "
            f"writes; re-record with tests/make_cassettes.py or declare the recorded "
            f"profile."
        )
    return len(recorded)


def _recorded_model_ids(store: CassetteStore) -> list[str]:
    """Every distinct ``model_id`` in a cassette store, sorted."""
    keys = store.keys()
    return sorted({store.get(key).model_id for key in keys})


# ── the process-wide runtime ────────────────────────────────────────────────────


class _ProcessRuntime:
    """The one booted runtime per process, and the latch that outlives a refusal."""

    def __init__(self) -> None:
        """Start unbooted and unlatched."""
        self._lock = threading.Lock()
        self._runtime: AgentkitRuntime | None = None
        self._refusal: str | None = None

    def boot(self, **kwargs: Any) -> AgentkitRuntime:
        with self._lock:
            if self._refusal is not None:
                raise RuntimeRefusing(self._refusal)
            if self._runtime is not None:
                raise RuntimeAlreadyBooted(
                    "a runtime is already serving in this process; a second boot would "
                    "swap the pinned inference-profile ARN underneath calls already in "
                    "flight. Call shutdown_runtime() first if that is genuinely meant."
                )
            try:
                booted = AgentkitRuntime.boot(**kwargs)
            except ConfigurationRefused as refusal:
                # Only a *configuration* refusal latches. A residency refusal must not
                # be retried; an ordinary bug is not a statement about this process's
                # right to serve.
                self._refusal = str(refusal)
                raise
            self._runtime = booted
            return booted

    def current(self) -> AgentkitRuntime:
        with self._lock:
            if self._refusal is not None:
                raise RuntimeRefusing(self._refusal)
            if self._runtime is None:
                raise RuntimeNotBooted(
                    "no agentkit runtime has been booted in this process. The au.* "
                    "assertion happens at start-up (ARCHITECTURE.md §10.1), so there is "
                    "no path that serves a call without it: call boot_runtime() first."
                )
            return self._runtime

    def shutdown(self, *, force: bool) -> None:
        with self._lock:
            if self._refusal is not None and not force:
                raise RuntimeRefusing(self._refusal)
            self._runtime = None
            self._refusal = None

    def serving(self) -> bool:
        with self._lock:
            return self._runtime is not None and self._refusal is None


_PROCESS = _ProcessRuntime()


def boot_runtime(
    *,
    settings: AgentkitSettings | None = None,
    transport: Transport | None = None,
    control_plane: Any = None,
    inference_profile_arn: str | None = None,
    profiles: Mapping[str, CallProfile[Any]] | None = None,
    cassette_root: Path | None = None,
    run_id: str | None = None,
    env: Mapping[str, str] | None = None,
) -> AgentkitRuntime:
    """Boot the one runtime this process serves from.

    Same arguments and same refusals as :meth:`AgentkitRuntime.boot`, plus two
    process-level ones.

    Raises:
        RuntimeAlreadyBooted: a runtime is already serving.
        RuntimeRefusing: a previous boot refused and the latch has not been cleared.
    """
    return _PROCESS.boot(
        settings=settings,
        transport=transport,
        control_plane=control_plane,
        inference_profile_arn=inference_profile_arn,
        profiles=profiles,
        cassette_root=cassette_root,
        run_id=run_id,
        env=env,
    )


def current_runtime() -> AgentkitRuntime:
    """Return the booted runtime.

    Raises:
        RuntimeNotBooted: nothing has booted in this process.
        RuntimeRefusing: start-up refused and the latch has not been cleared.
    """
    return _PROCESS.current()


def shutdown_runtime(*, force: bool = False) -> None:
    """Forget the booted runtime.

    Args:
        force: also clear a start-up refusal. Required, and deliberately awkward: a
            latch that anything could clear would not be a latch.

    Raises:
        RuntimeRefusing: the process is latched and ``force`` was not set.
    """
    _PROCESS.shutdown(force=force)


def is_serving() -> bool:
    """Whether this process has a booted, unlatched runtime."""
    return _PROCESS.serving()
