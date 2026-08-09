# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The two beacons: parsing, round-to-time arithmetic, and the two offline bindings.

Ruling **CU-4**: a checkpoint quotes *two* public randomness beacons, and only one of
them is load-bearing offline.

``drand`` **quicknet**
    Scheme ``bls-unchained-g1-rfc9380``, 3-second cadence. A round's value cannot be
    known before it is issued, so a checkpoint quoting round *r* cannot have been
    constructed before ``genesis + (r - 1) * period``. That arithmetic is
    :func:`drand_round_time` and it needs nothing but integers. The **BLS12-381 G1
    signature is not verifiable under the verifier's dependency floor** — ``cryptography``
    has no BLS12-381 — so the verifier reports it ``SKIP(optional-extra)``. This module
    therefore ships no BLS verification and claims none.

NIST Interoperable Randomness Beacon 2.0
    RSA PKCS#1 v1.5 over SHA-512 with an X.509 certificate, all of which ``cryptography``
    verifies. This is the lower bound that survives the floor, and verifying it is the
    verifier's check 6a — not this module's.

**This module parses and does arithmetic. It does not verify signatures.** The division
is deliberate: ``trappoint-ledger`` is what the *log* runs, and a log that could verify
its own beacons would be tempted to treat its own verdict as evidence. The two bindings
below are the exception, and they are not signature verification:

* :meth:`DrandRound.randomness_binds_signature` — drand defines ``randomness =
  SHA-256(signature)`` for every scheme, so a round whose randomness does not hash from
  its own signature is internally inconsistent and can be rejected with ``hashlib``
  alone. It says nothing about whether the signature is genuine.
* :meth:`NistPulse.output_binds_signature` — NIST 2.0 defines ``outputValue =
  SHA-512(signatureValue)``. **Marked UNVERIFIED against a live pulse**: published
  descriptions differ over whether the SHA-512 preimage is the signature bytes alone or
  the signing input concatenated with them, and nothing in MAINLINE has yet been run
  against beacon.nist.gov to settle it. Nothing in this repository gates on the result,
  and the authoritative check is the verifier's check 6a.

Dependency floor: ``hashlib``, ``re``, ``datetime``, ``dataclasses``, ``typing``,
``collections.abc``. No network client lives here either — ``mainline_anchor`` fetches,
this parses, and a parser that could also fetch is a parser that can be pointed at a URL
by whatever it just parsed.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

__all__ = [
    "DRAND_CHAIN_HASH_QUICKNET",
    "DRAND_GENESIS_TIME_QUICKNET",
    "DRAND_PERIOD_SECONDS_QUICKNET",
    "DRAND_SCHEME_QUICKNET",
    "NIST_BEACON_VERSION",
    "NIST_PERIOD_SECONDS",
    "BeaconParseError",
    "DrandRound",
    "NistPulse",
    "beacon_column",
    "drand_round_at_time",
    "drand_round_time",
    "parse_beacon_column",
    "parse_drand_extension",
    "parse_nist_extension",
]

#: The League of Entropy ``quicknet`` chain hash. A checkpoint quoting any other chain is
#: quoting a beacon nobody agreed to, which is verifier check 6b's first comparison.
DRAND_CHAIN_HASH_QUICKNET: Final = (
    "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
)

#: quicknet is *unchained*: a round does not depend on its predecessor, so a round can be
#: verified statelessly. That is why a checkpoint can quote one round and nothing else.
DRAND_SCHEME_QUICKNET: Final = "bls-unchained-g1-rfc9380"

#: Unix seconds. ``round_time = genesis + (round - 1) * period``.
DRAND_GENESIS_TIME_QUICKNET: Final = 1692803367

DRAND_PERIOD_SECONDS_QUICKNET: Final = 3

#: The only NIST beacon version this profile carries.
NIST_BEACON_VERSION: Final = "2.0"

#: NIST emits one pulse a minute. Recorded for the operator arithmetic that decides how
#: stale a quoted pulse may be; no check in this module reads it.
NIST_PERIOD_SECONDS: Final = 60

_SHA256_HEX: Final = re.compile(r"\A[0-9a-f]{64}\Z")
_SHA512_HEX: Final = re.compile(r"\A[0-9a-f]{128}\Z")
_HEX: Final = re.compile(r"\A[0-9a-f]*\Z")
_DRAND_EXTENSION: Final = re.compile(r"\A([0-9a-f]{64}) ([1-9][0-9]*) ([0-9a-f]{64})\Z")
_NIST_EXTENSION: Final = re.compile(r"\A2\.0 ([0-9]+)\.([0-9]+) ([0-9a-f]{128})\Z")
_RFC3339: Final = re.compile(
    r"\A(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6})\d*)?"
    r"(Z|[+-]\d{2}:\d{2})\Z"
)


class BeaconParseError(ValueError):
    """A beacon value does not have the shape ``spec/wire/checkpoint.md`` §4 fixes."""


def drand_round_time(round_number: int, *, genesis: int | None = None, period: int = 0) -> datetime:
    """Return the earliest instant at which a drand round could have existed.

    ``genesis + (round - 1) * period``, per ``spec/wire/checkpoint.md`` §4.2. This is the
    whole of the lower bound a stranger can compute with no dependency and no network:
    a checkpoint quoting round *r* cannot have been constructed before this instant, so a
    backdated checkpoint that quotes a real round contradicts itself.

    Args:
        round_number: The drand round, 1-based.
        genesis: Chain genesis in Unix seconds; defaults to quicknet's.
        period: Round period in seconds; defaults to quicknet's when ``0``.

    Returns:
        A timezone-aware UTC datetime.

    Raises:
        ValueError: If the round is not positive or the period is not positive.
    """
    if round_number < 1:
        raise ValueError(f"drand rounds are 1-based; got {round_number}")
    genesis_time = DRAND_GENESIS_TIME_QUICKNET if genesis is None else genesis
    period_seconds = DRAND_PERIOD_SECONDS_QUICKNET if period == 0 else period
    if period_seconds <= 0:
        raise ValueError(f"a drand period is positive; got {period_seconds}")
    return datetime.fromtimestamp(genesis_time + (round_number - 1) * period_seconds, tz=UTC)


def drand_round_at_time(when: datetime, *, genesis: int | None = None, period: int = 0) -> int:
    """Return the latest drand round whose issue time is at or before ``when``.

    The inverse of :func:`drand_round_time`, and the arithmetic an anchor process uses to
    decide which round a checkpoint may legitimately quote.

    Args:
        when: A timezone-aware instant.
        genesis: Chain genesis in Unix seconds; defaults to quicknet's.
        period: Round period in seconds; defaults to quicknet's when ``0``.

    Returns:
        The round number, at least 1.

    Raises:
        ValueError: If ``when`` is naive — a naive datetime in an evidentiary
            computation is an unanswerable question in cross-examination — or precedes
            the chain genesis.
    """
    if when.tzinfo is None:
        raise ValueError("drand_round_at_time needs a timezone-aware instant")
    genesis_time = DRAND_GENESIS_TIME_QUICKNET if genesis is None else genesis
    period_seconds = DRAND_PERIOD_SECONDS_QUICKNET if period == 0 else period
    if period_seconds <= 0:
        raise ValueError(f"a drand period is positive; got {period_seconds}")
    elapsed = int(when.timestamp()) - genesis_time
    if elapsed < 0:
        raise ValueError(
            f"{when.isoformat()} precedes the chain genesis at {genesis_time}; no round existed yet"
        )
    return elapsed // period_seconds + 1


def _require_hex(value: str, pattern: re.Pattern[str], what: str) -> str:
    if pattern.match(value) is None:
        raise BeaconParseError(f"{what} is not the expected lowercase hex string: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class DrandRound:
    """A drand quicknet round, as quoted by a checkpoint or fetched from the API."""

    round_number: int
    """1-based round index."""

    randomness: str
    """64 lowercase hex characters. drand defines it as ``SHA-256(signature)``."""

    chain_hash: str = DRAND_CHAIN_HASH_QUICKNET
    """64 lowercase hex characters identifying the chain."""

    signature: str | None = None
    """The BLS12-381 G1 signature as lowercase hex, when the round was fetched rather
    than read off a checkpoint. The checkpoint's ``drand:`` line does **not** carry it:
    it is 96 hex characters that no offline verifier under the dependency floor can
    check, and a field nobody verifies is a field that invites being believed."""

    def __post_init__(self) -> None:
        """Validate the field shapes."""
        if self.round_number < 1:
            raise BeaconParseError(f"drand rounds are 1-based; got {self.round_number}")
        _require_hex(self.randomness, _SHA256_HEX, "drand randomness")
        _require_hex(self.chain_hash, _SHA256_HEX, "drand chain hash")
        if self.signature is not None and _HEX.match(self.signature) is None:
            raise BeaconParseError(f"drand signature is not lowercase hex: {self.signature!r}")

    @property
    def is_quicknet(self) -> bool:
        """Return whether this round is on the chain ruling CU-4 names."""
        return self.chain_hash == DRAND_CHAIN_HASH_QUICKNET

    def round_time(self) -> datetime:
        """Return the round's issue time — the lower time bound it contributes."""
        if not self.is_quicknet:
            raise BeaconParseError(
                f"round time for chain {self.chain_hash} cannot be computed from "
                "quicknet's genesis and period; pass them explicitly to drand_round_time"
            )
        return drand_round_time(self.round_number)

    def randomness_binds_signature(self) -> bool:
        """Return whether ``randomness == SHA-256(signature)``.

        drand defines the randomness of every scheme as the SHA-256 of the round's
        signature, so this is checkable with ``hashlib`` and no BLS library at all.

        **It is an internal-consistency check, not verification.** It proves the two
        fields belong together; it proves nothing about whether the League of Entropy
        produced either. Anyone can mint a self-consistent pair. The BLS verification
        that would make this a real bound is verifier check 6b, and it reports
        ``SKIP(optional-extra)`` under the dependency floor.

        Returns:
            ``False`` when no signature is present, since nothing has been shown.
        """
        if self.signature is None:
            return False
        return hashlib.sha256(bytes.fromhex(self.signature)).hexdigest() == self.randomness

    def extension_value(self) -> str:
        """Return the ``drand:`` extension line's value field."""
        return f"{self.chain_hash} {self.round_number} {self.randomness}"

    def to_column(self) -> dict[str, Any]:
        """Return the ``ledger_checkpoint.beacon -> 'drand'`` JSON object."""
        return {
            "chain_hash": self.chain_hash,
            "round": self.round_number,
            "randomness": self.randomness,
        }

    @classmethod
    def from_api(cls, payload: Mapping[str, Any], *, chain_hash: str | None = None) -> DrandRound:
        """Parse a drand HTTP API round object.

        Args:
            payload: ``{"round": int, "randomness": hex, "signature": hex}``. quicknet is
                unchained, so ``previous_signature`` is absent and is not read here even
                when present.
            chain_hash: The chain the round was fetched from; defaults to quicknet's.

        Returns:
            The parsed round.

        Raises:
            BeaconParseError: If a required field is missing or malformed.
        """
        try:
            round_number = int(payload["round"])
            randomness = str(payload["randomness"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BeaconParseError(
                f"drand round object is missing round/randomness: {exc}"
            ) from exc
        signature = payload.get("signature")
        return cls(
            round_number=round_number,
            randomness=randomness,
            chain_hash=DRAND_CHAIN_HASH_QUICKNET if chain_hash is None else chain_hash,
            signature=None if signature is None else str(signature),
        )


def parse_drand_extension(value: str) -> DrandRound:
    """Parse a checkpoint's ``drand:`` extension value.

    Args:
        value: ``<64 hex chain hash> <round decimal> <64 hex randomness>``.

    Returns:
        The round, with :attr:`DrandRound.signature` unset — the line does not carry one.

    Raises:
        BeaconParseError: If the value does not match §4.2's shape.
    """
    match = _DRAND_EXTENSION.match(value)
    if match is None:
        raise BeaconParseError(
            f"drand: value {value!r} is not '<64 hex chain hash> <round> <64 hex "
            "randomness>' (spec/wire/checkpoint.md §4.2)"
        )
    return DrandRound(
        round_number=int(match.group(2)),
        randomness=match.group(3),
        chain_hash=match.group(1),
    )


def _parse_rfc3339(text: str) -> datetime:
    match = _RFC3339.match(text)
    if match is None:
        raise BeaconParseError(f"{text!r} is not an RFC 3339 timestamp")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:  # pragma: no cover - the regex requires an offset
        raise BeaconParseError(f"{text!r} carries no UTC offset")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class NistPulse:
    """A NIST Interoperable Randomness Beacon 2.0 pulse, parsed.

    Only the members MAINLINE carries or reasons about are modelled. The full pulse has
    around twenty fields; :attr:`raw` keeps whatever it was parsed from, so the verifier
    — which needs every field to reconstruct the signing input — reads them from there
    rather than from a subset this module chose.
    """

    chain_index: int
    """``chainIndex``. Resets only when NIST restarts the beacon."""

    pulse_index: int
    """``pulseIndex``. One per minute within a chain."""

    output_value: str
    """``outputValue``: 128 lowercase hex characters — a SHA-512 digest."""

    version: str = NIST_BEACON_VERSION
    """``version``, normalised to ``"2.0"``."""

    timestamp: datetime | None = None
    """``timeStamp``, when the pulse was fetched rather than read off a checkpoint. The
    ``nist:`` extension line does not carry it, so a checkpoint alone gives an index and
    not an instant — fetching the pulse is what turns the index into a time bound."""

    signature_value: str | None = None
    """``signatureValue`` as lowercase hex, when known. 512 bytes for a 2048-bit RSA key."""

    certificate_id: str | None = None
    """``certificateId``: the SHA-512 of the signing certificate, 128 hex characters."""

    raw: Mapping[str, Any] | None = None
    """The pulse object as received, for the verifier's signing-input reconstruction."""

    def __post_init__(self) -> None:
        """Validate the field shapes."""
        if self.chain_index < 0 or self.pulse_index < 0:
            raise BeaconParseError(
                f"NIST indices are non-negative; got {self.chain_index}.{self.pulse_index}"
            )
        _require_hex(self.output_value, _SHA512_HEX, "NIST outputValue")
        if self.version != NIST_BEACON_VERSION:
            raise BeaconParseError(
                f"this profile carries NIST beacon version {NIST_BEACON_VERSION}, not "
                f"{self.version!r} (spec/wire/checkpoint.md §4.3)"
            )
        if self.certificate_id is not None:
            _require_hex(self.certificate_id, _SHA512_HEX, "NIST certificateId")
        if self.signature_value is not None and _HEX.match(self.signature_value) is None:
            raise BeaconParseError("NIST signatureValue is not lowercase hex")
        if self.timestamp is not None and self.timestamp.tzinfo is None:
            raise BeaconParseError("a NIST pulse timestamp must be timezone-aware")

    def output_binds_signature(self) -> bool:
        """Return whether ``outputValue == SHA-512(signatureValue)``.

        **UNVERIFIED against a live pulse.** NIST 2.0 defines ``outputValue`` as a
        SHA-512 digest derived from ``signatureValue``; published descriptions differ over
        whether the preimage is the signature bytes alone or the pulse's signing input
        concatenated with them, and no MAINLINE build has yet been run against
        beacon.nist.gov to settle which. This method implements the *signature bytes
        alone* reading, is gated by nothing, and is read by no check in this repository.
        The authoritative verification is verifier check 6a, which reconstructs the
        signing input and verifies the RSA signature — see
        ``packages/trappoint-verify/src/trappoint_verify/checks/beacon.py``.

        Returns:
            ``False`` when no signature value is present, since nothing has been shown.
        """
        if self.signature_value is None:
            return False
        return hashlib.sha512(bytes.fromhex(self.signature_value)).hexdigest() == self.output_value

    def extension_value(self) -> str:
        """Return the ``nist:`` extension line's value field."""
        return f"{self.version} {self.chain_index}.{self.pulse_index} {self.output_value}"

    def to_column(self) -> dict[str, Any]:
        """Return the ``ledger_checkpoint.beacon -> 'nist'`` JSON object."""
        return {
            "version": self.version,
            "chain_index": self.chain_index,
            "pulse_index": self.pulse_index,
            "output_value": self.output_value,
        }

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> NistPulse:
        """Parse a NIST beacon 2.0 REST response or a bare pulse object.

        Args:
            payload: Either ``{"pulse": {...}}`` as the REST API returns, or the pulse
                object itself.

        Returns:
            The parsed pulse, with :attr:`raw` set to the pulse object.

        Raises:
            BeaconParseError: If a required member is missing or malformed.
        """
        pulse = payload.get("pulse", payload)
        if not isinstance(pulse, Mapping):
            raise BeaconParseError("the 'pulse' member is not an object")
        try:
            chain_index = int(pulse["chainIndex"])
            pulse_index = int(pulse["pulseIndex"])
            output_value = str(pulse["outputValue"]).lower()
        except (KeyError, TypeError, ValueError) as exc:
            raise BeaconParseError(
                f"NIST pulse is missing chainIndex/pulseIndex/outputValue: {exc}"
            ) from exc
        version = str(pulse.get("version", NIST_BEACON_VERSION))
        # NIST spells it "Version 2.0" in the pulse and "2.0" nowhere; normalise once,
        # here, so that the extension line is a function of the pulse and not of which
        # transport it arrived over.
        normalised = version.removeprefix("Version").strip() or NIST_BEACON_VERSION
        timestamp = pulse.get("timeStamp")
        signature_value = pulse.get("signatureValue")
        certificate_id = pulse.get("certificateId")
        return cls(
            chain_index=chain_index,
            pulse_index=pulse_index,
            output_value=output_value,
            version=normalised,
            timestamp=None if timestamp is None else _parse_rfc3339(str(timestamp)),
            signature_value=None if signature_value is None else str(signature_value).lower(),
            certificate_id=None if certificate_id is None else str(certificate_id).lower(),
            raw=dict(pulse),
        )


def parse_nist_extension(value: str) -> NistPulse:
    """Parse a checkpoint's ``nist:`` extension value.

    Args:
        value: ``2.0 <chainIndex>.<pulseIndex> <128 hex outputValue>``.

    Returns:
        The pulse, with no timestamp and no signature — the line carries neither.

    Raises:
        BeaconParseError: If the value does not match §4.3's shape.
    """
    match = _NIST_EXTENSION.match(value)
    if match is None:
        raise BeaconParseError(
            f"nist: value {value!r} is not '2.0 <chainIndex>.<pulseIndex> <128 hex "
            "outputValue>' (spec/wire/checkpoint.md §4.3)"
        )
    return NistPulse(
        chain_index=int(match.group(1)),
        pulse_index=int(match.group(2)),
        output_value=match.group(3),
    )


def beacon_column(drand: DrandRound, nist: NistPulse) -> dict[str, Any]:
    """Return the ``ledger_checkpoint.beacon`` JSONB value for a checkpoint.

    The shape is the one ``mainline_sequencer.append.CheckpointInputs.beacon_json``
    writes, so the column and the signed note cannot disagree about which round was
    quoted.

    Args:
        drand: The quoted drand round.
        nist: The quoted NIST pulse.

    Returns:
        ``{"drand": {...}, "nist": {...}}``.
    """
    return {"drand": drand.to_column(), "nist": nist.to_column()}


def parse_beacon_column(column: Mapping[str, Any]) -> tuple[DrandRound, NistPulse]:
    """Parse a stored ``ledger_checkpoint.beacon`` value back into its two beacons.

    Args:
        column: The JSONB object.

    Returns:
        ``(drand round, NIST pulse)``.

    Raises:
        BeaconParseError: If either member is missing or malformed.
    """
    try:
        drand_obj = column["drand"]
        nist_obj = column["nist"]
    except (KeyError, TypeError) as exc:
        raise BeaconParseError(
            f"a beacon column carries both a 'drand' and a 'nist' member: {exc}"
        ) from exc
    try:
        drand = DrandRound(
            round_number=int(drand_obj["round"]),
            randomness=str(drand_obj["randomness"]),
            chain_hash=str(drand_obj["chain_hash"]),
        )
        nist = NistPulse(
            chain_index=int(nist_obj["chain_index"]),
            pulse_index=int(nist_obj["pulse_index"]),
            output_value=str(nist_obj["output_value"]),
            version=str(nist_obj.get("version", NIST_BEACON_VERSION)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BeaconParseError(f"beacon column member is missing or malformed: {exc}") from exc
    return drand, nist
