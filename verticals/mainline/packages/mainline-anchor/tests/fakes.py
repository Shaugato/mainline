# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""In-process fakes that REFUSE a wrong call, rather than recording one.

This file is the mitigation for risk 3 in ``docs/leads/custody.md`` §6: AWS credentials
are not valid on the machine this package was written on, and *an unexercised path is a
broken path*. A fake that accepted ``**kwargs`` and stored them would make the suite green
against a call shape that writes a checkpoint object with no retention at all — and S3
Object Lock cannot be retrofitted onto an object any more than onto a bucket (GT-18).

So every fake here asserts, at the moment of the call:

* ``FakeKmsClient`` — ``SigningAlgorithm='ECDSA_SHA_256'``, ``MessageType='RAW'``, and a
  ``KeySpec`` of ``ECC_NIST_P256`` from ``GetPublicKey``.
* ``FakeS3Client`` — ``ObjectLockMode='COMPLIANCE'``, ``ObjectLockLegalHoldStatus='ON'``,
  an aware ``ObjectLockRetainUntilDate`` at least seven years out, and a bucket that was
  created with Object Lock enabled. A bucket constructed with
  ``object_lock_enabled=False`` behaves the way S3 actually behaves — it **accepts the
  write and silently ignores the lock parameters** — which is what makes
  ``test_call_shapes.py::test_a_bucket_without_object_lock_is_refused`` a real test.
* the port fakes — each one refuses to run before its predecessor in
  :data:`mainline_anchor.ports.STEP_ORDER` has run, using a shared :class:`CallLog`. The
  ordering assertion in ``test_fanout_order.py`` is therefore made by the collaborators
  and not only by the code under test, which is the difference between evidence and a
  claim.

**Deliberately NOT moto** (ruling CU-10). moto's Object Lock support does not enforce the
control, and a green test against a mock that does not enforce the thing is worse than no
test: it converts an unproven property into a believed one. What is proven instead is the
call shape here, and the OpenTofu plan JSON in ``scripts/custody/check_evidence_plan.py``.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# The suite must run on a checkout where `uv sync` has not installed this distribution —
# a stranger's `git clone && pytest` is Tier 2 in ARCHITECTURE.md §7.5 and it needs
# nothing from us. Importing this module first is what puts `src` on the path; every test
# module in this package imports `fakes` before it imports `mainline_anchor`.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mainline_anchor.ports import (  # noqa: E402 - after the sys.path bootstrap above
    AnchorStep,
    ArchivedObject,
    BeaconSnapshot,
    Cosignature,
    HttpResponse,
    PublishedTile,
    Tile,
    TimestampToken,
)
from trappoint_ledger.beacon import DrandRound, NistPulse  # noqa: E402 - same

# ── Literals. Spelled out here on purpose ─────────────────────────────────────────────
#
# These are NOT imported from `mainline_anchor.ports`. A test that asserted
# `kwargs["ObjectLockMode"] == ports.OBJECT_LOCK_MODE` would pass after somebody changed
# `OBJECT_LOCK_MODE` to "GOVERNANCE", which is precisely the change that must fail.

EXPECTED_OBJECT_LOCK_MODE = "COMPLIANCE"
EXPECTED_LEGAL_HOLD = "ON"
EXPECTED_SIGNING_ALGORITHM = "ECDSA_SHA_256"
EXPECTED_MESSAGE_TYPE = "RAW"
EXPECTED_KEY_SPEC = "ECC_NIST_P256"
EXPECTED_KEY_USAGE = "SIGN_VERIFY"
MINIMUM_RETENTION_DAYS = 365 * 7 - 3  # seven years, less enough slack for leap years


class FakeCallRefused(AssertionError):
    """A fake was called in a shape or an order that would be wrong against the real thing."""


@dataclass
class CallLog:
    """The single ordered record of every port call in one pass.

    Shared by every fake. ``test_fanout_order.py`` asserts against this rather than
    against ``AnchorResult.steps``, because the result's trace is maintained by the code
    under test and this is maintained by its collaborators.
    """

    entries: list[tuple[AnchorStep, str]] = field(default_factory=list)

    def record(self, step: AnchorStep, detail: str = "") -> None:
        """Append one call."""
        self.entries.append((step, detail))

    @property
    def steps(self) -> list[AnchorStep]:
        """Return the distinct steps in first-call order."""
        seen: list[AnchorStep] = []
        for step, _ in self.entries:
            if step not in seen:
                seen.append(step)
        return seen

    def require_before(self, later: AnchorStep, earlier: AnchorStep) -> None:
        """Refuse unless ``earlier`` has already been called.

        This is what makes the fakes enforce the order instead of observing it.
        """
        if earlier not in self.steps:
            raise FakeCallRefused(
                f"{later.value} was called before {earlier.value}; "
                f"the calls so far are {[s.value for s in self.steps]}"
            )


# ── SDK-shaped fakes: these assert the literal keyword arguments ──────────────────────


class FakeKmsClient:
    """A boto3-shaped KMS client that refuses anything but the pinned call shape."""

    def __init__(
        self, *, key_id: str = "arn:aws:kms:ap-southeast-2:111:key/log", region: str | None = None
    ) -> None:
        self.key_id = key_id
        self.sign_calls: list[dict[str, Any]] = []
        self.get_public_key_calls: list[dict[str, Any]] = []
        # A 91-byte DER SubjectPublicKeyInfo for a P-256 key. The point is not on the
        # curve and does not need to be: nothing in this package verifies a signature, and
        # a fixture that pretended to be a real key would invite somebody to believe it.
        self.spki = bytes(range(91))
        self.meta = _Meta(region)

    def get_public_key(self, **kwargs: Any) -> dict[str, Any]:
        self.get_public_key_calls.append(dict(kwargs))
        if kwargs.get("KeyId") != self.key_id:
            raise FakeCallRefused(
                f"GetPublicKey KeyId={kwargs.get('KeyId')!r}, expected {self.key_id!r}"
            )
        return {
            "KeyId": self.key_id,
            "PublicKey": self.spki,
            "KeySpec": EXPECTED_KEY_SPEC,
            "KeyUsage": EXPECTED_KEY_USAGE,
            "SigningAlgorithms": [EXPECTED_SIGNING_ALGORITHM],
        }

    def sign(self, **kwargs: Any) -> dict[str, Any]:
        self.sign_calls.append(dict(kwargs))
        if kwargs.get("SigningAlgorithm") != EXPECTED_SIGNING_ALGORITHM:
            raise FakeCallRefused(
                f"kms:Sign SigningAlgorithm={kwargs.get('SigningAlgorithm')!r}, expected "
                f"{EXPECTED_SIGNING_ALGORITHM!r} (ruling CU-3)"
            )
        if kwargs.get("MessageType") != EXPECTED_MESSAGE_TYPE:
            raise FakeCallRefused(
                f"kms:Sign MessageType={kwargs.get('MessageType')!r}, expected "
                f"{EXPECTED_MESSAGE_TYPE!r}; under DIGEST, KMS would treat the note text "
                "as if it were a SHA-256 digest"
            )
        message = kwargs.get("Message")
        if not isinstance(message, bytes) or not message:
            raise FakeCallRefused("kms:Sign Message must be non-empty bytes")
        return {
            "KeyId": self.key_id,
            "SigningAlgorithm": EXPECTED_SIGNING_ALGORITHM,
            # Deterministic and DER-shaped enough to travel; not a real ECDSA signature.
            "Signature": b"\x30\x06\x02\x01\x01\x02\x01" + hashlib.sha256(message).digest()[:1],
        }


class FakeS3Client:
    """A boto3-shaped S3 client that behaves like S3, including the dangerous part.

    ``object_lock_enabled=False`` does what the real service does: it accepts the write,
    ignores every lock parameter, and returns 200. That is the failure this package's
    read-back exists to catch.
    """

    def __init__(
        self,
        *,
        bucket: str = "mainline-custody-blk07",
        object_lock_enabled: bool = True,
        versioned: bool = True,
        region: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.object_lock_enabled = object_lock_enabled
        self.versioned = versioned
        self.put_calls: list[dict[str, Any]] = []
        self.head_calls: list[dict[str, Any]] = []
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}
        self.meta = _Meta(region)
        self._version_counter = 0

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(dict(kwargs))
        if kwargs.get("Bucket") != self.bucket:
            raise FakeCallRefused(
                f"PutObject Bucket={kwargs.get('Bucket')!r}, expected {self.bucket!r}"
            )
        body = kwargs.get("Body")
        if not isinstance(body, bytes):
            raise FakeCallRefused(
                "PutObject Body must be bytes; a str would be encoded by the SDK "
                "under a charset nobody chose"
            )
        is_checkpoint = "ObjectLockMode" in kwargs or kwargs.get("Key", "").startswith(
            "checkpoint/"
        )
        if is_checkpoint:
            self._assert_checkpoint_lock_shape(kwargs)
        self._version_counter += 1
        version_id = f"v{self._version_counter:04d}" if self.versioned else ""
        stored: dict[str, Any] = {
            "Body": body,
            "ETag": f'"{hashlib.md5(body, usedforsecurity=False).hexdigest()}"',
            "VersionId": version_id,
            "LastModified": datetime(2026, 8, 10, 4, 30, tzinfo=UTC),
            "Metadata": dict(kwargs.get("Metadata", {})),
        }
        if self.object_lock_enabled and is_checkpoint:
            stored["ObjectLockMode"] = kwargs["ObjectLockMode"]
            stored["ObjectLockRetainUntilDate"] = kwargs["ObjectLockRetainUntilDate"]
            stored["ObjectLockLegalHoldStatus"] = kwargs["ObjectLockLegalHoldStatus"]
        self.objects[(kwargs["Key"], version_id)] = stored
        return {"ETag": stored["ETag"], "VersionId": version_id}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self.head_calls.append(dict(kwargs))
        key = kwargs["Key"]
        version_id = kwargs.get("VersionId", "")
        stored = self.objects.get((key, version_id))
        if stored is None:
            raise FakeCallRefused(
                f"HeadObject on an object that was never written: {key!r}@{version_id!r}"
            )
        head = {k: v for k, v in stored.items() if k != "Body"}
        head["ContentLength"] = len(stored["Body"])
        return head

    def _assert_checkpoint_lock_shape(self, kwargs: dict[str, Any]) -> None:
        mode = kwargs.get("ObjectLockMode")
        if mode != EXPECTED_OBJECT_LOCK_MODE:
            raise FakeCallRefused(
                f"PutObject ObjectLockMode={mode!r}, expected {EXPECTED_OBJECT_LOCK_MODE!r}. "
                "GOVERNANCE is removable by a principal holding s3:BypassGovernanceRetention"
            )
        hold = kwargs.get("ObjectLockLegalHoldStatus")
        if hold != EXPECTED_LEGAL_HOLD:
            raise FakeCallRefused(
                f"PutObject ObjectLockLegalHoldStatus={hold!r}, expected {EXPECTED_LEGAL_HOLD!r}"
            )
        retain = kwargs.get("ObjectLockRetainUntilDate")
        if not isinstance(retain, datetime) or retain.tzinfo is None:
            raise FakeCallRefused(
                f"PutObject ObjectLockRetainUntilDate={retain!r} must be a timezone-aware datetime"
            )
        horizon = retain - datetime.now(UTC)
        if horizon < timedelta(days=MINIMUM_RETENTION_DAYS):
            raise FakeCallRefused(
                f"PutObject ObjectLockRetainUntilDate is only {horizon.days} days out; the "
                f"floor is {MINIMUM_RETENTION_DAYS} days (seven years)"
            )


@dataclass
class _Meta:
    region_name: str | None = None


# ── Port fakes: these enforce the ORDER ───────────────────────────────────────────────

FIXED_DRAND = DrandRound(
    round_number=31088494,
    # SHA-256 of the signature below, so `randomness_binds_signature()` holds. Computed at
    # import time rather than pasted, because a pasted digest that drifts from its
    # preimage is a fixture that quietly stops testing the binding.
    randomness=hashlib.sha256(bytes.fromhex("ab" * 48)).hexdigest(),
    signature="ab" * 48,
)
FIXED_NIST = NistPulse(
    chain_index=2,
    pulse_index=29255654,
    output_value="d7" * 64,
    timestamp=datetime(2026, 8, 10, 4, 0, tzinfo=UTC),
)


def fixed_snapshot() -> BeaconSnapshot:
    """Return the deterministic beacon snapshot every test in this package uses."""
    return BeaconSnapshot(drand=FIXED_DRAND, nist=FIXED_NIST)


def fixed_clock() -> datetime:
    """Return an instant comfortably after both fixed beacons.

    The drand round above maps to roughly 2026-07-31 under quicknet's genesis and period,
    and the NIST pulse is stamped 2026-08-10T04:00Z, so this satisfies the fanout's
    "the lower bound is not in the future" refusal without depending on the wall clock.
    """
    return datetime(2026, 8, 10, 4, 30, tzinfo=UTC)


class FakeBeacon:
    """A :class:`~mainline_anchor.ports.BeaconPort` that records its call."""

    def __init__(
        self, log: CallLog, *, snapshot: BeaconSnapshot | None = None, fail: str | None = None
    ) -> None:
        self._log = log
        self._snapshot = snapshot if snapshot is not None else fixed_snapshot()
        self._fail = fail

    def snapshot(self) -> BeaconSnapshot:
        self._log.record(AnchorStep.BEACON)
        if self._fail is not None:
            raise RuntimeError(self._fail)
        return self._snapshot


class FakeSigner:
    """A :class:`~mainline_anchor.ports.KmsSignPort` that needs no `cryptography`.

    The whole fanout suite runs on an install without `cryptography`, which is the point:
    the signature is a port, so ordering and call shape are testable on a floor install.
    Signature *verification* is `trappoint-verify`'s, and it is tested there.
    """

    def __init__(self, log: CallLog, *, fail: str | None = None) -> None:
        self._log = log
        self._fail = fail
        self.signed: list[bytes] = []
        self.spki = bytes(range(91))

    def sign(self, body: bytes) -> bytes:
        self._log.record(AnchorStep.SIGN, f"{len(body)} bytes")
        if self._fail is not None:
            raise RuntimeError(self._fail)
        self.signed.append(body)
        return b"\x30\x06\x02\x01\x01\x02\x01" + hashlib.sha256(body).digest()[:1]

    def public_key_spki_der(self) -> bytes:
        return self.spki


class FakeArchive:
    """An :class:`~mainline_anchor.ports.ObjectLockPort` that refuses an unsigned note.

    Refusing here is what proves the ordering claim `sign → object lock`: a note with no
    signature line reaching the archive means the fanout locked bytes nobody attributed
    to us, and the fake will not pretend that succeeded.
    """

    def __init__(
        self,
        log: CallLog,
        *,
        bucket: str = "mainline-custody-blk07",
        mode: str = EXPECTED_OBJECT_LOCK_MODE,
        legal_hold: str = EXPECTED_LEGAL_HOLD,
        retain_years: int = 7,
        version_id: str = "v0001",
        fail: str | None = None,
        clock: Any = fixed_clock,
    ) -> None:
        self._log = log
        self._bucket = bucket
        self._mode = mode
        self._legal_hold = legal_hold
        self._retain_years = retain_years
        self._version_id = version_id
        self._fail = fail
        self._clock = clock
        self.written: list[tuple[str, bytes]] = []

    def put_checkpoint(self, *, key: str, note: bytes, metadata: Any) -> ArchivedObject:
        self._log.require_before(AnchorStep.OBJECT_LOCK, AnchorStep.SIGN)
        self._log.record(AnchorStep.OBJECT_LOCK, key)
        if self._fail is not None:
            raise RuntimeError(self._fail)
        if "\n\n— " not in note.decode("utf-8"):
            raise FakeCallRefused(
                "the note handed to Object Lock carries no C2SP signature line, so the "
                "fanout locked an unsigned root"
            )
        if "origin" not in dict(metadata):
            raise FakeCallRefused("the checkpoint object carries no 'origin' metadata")
        self.written.append((key, note))
        now = self._clock()
        return ArchivedObject(
            bucket=self._bucket,
            key=key,
            version_id=self._version_id,
            etag='"fake"',
            object_lock_mode=self._mode,
            retain_until=now.replace(year=now.year + self._retain_years),
            legal_hold_status=self._legal_hold,
            last_modified=now,
        )


class FakeTsa:
    """A :class:`~mainline_anchor.ports.TsaPort` that refuses to stamp an unlocked note."""

    def __init__(
        self,
        log: CallLog,
        name: str,
        *,
        gen_time: datetime | None = None,
        fail: str | None = None,
        imprint_override: bytes | None = None,
    ) -> None:
        self._log = log
        self._name = name
        self._gen_time = (
            gen_time if gen_time is not None else datetime(2026, 8, 10, 4, 30, 5, tzinfo=UTC)
        )
        self._fail = fail
        self._imprint_override = imprint_override

    @property
    def name(self) -> str:
        return self._name

    def timestamp(self, digest: bytes) -> TimestampToken:
        self._log.require_before(AnchorStep.TIMESTAMP, AnchorStep.OBJECT_LOCK)
        self._log.record(AnchorStep.TIMESTAMP, self._name)
        if self._fail is not None:
            raise RuntimeError(self._fail)
        return TimestampToken(
            authority=self._name,
            token_der=b"\x30\x03\x02\x01\x00",
            gen_time=self._gen_time,
            message_imprint=self._imprint_override
            if self._imprint_override is not None
            else digest,
        )


class FakeTileStore:
    """A :class:`~mainline_anchor.ports.TilePublishPort`."""

    def __init__(
        self, log: CallLog, *, fail: str | None = None, drop: set[str] | None = None
    ) -> None:
        self._log = log
        self._fail = fail
        self._drop = drop or set()
        self.published: list[Tile] = []

    def publish(self, tiles: Any) -> tuple[PublishedTile, ...]:
        self._log.require_before(AnchorStep.PUBLISH_TILES, AnchorStep.TIMESTAMP)
        self._log.record(AnchorStep.PUBLISH_TILES, f"{len(tiles)} tiles")
        if self._fail is not None:
            raise RuntimeError(self._fail)
        out: list[PublishedTile] = []
        for tile in tiles:
            if tile.path in self._drop:
                continue
            self.published.append(tile)
            out.append(
                PublishedTile(path=tile.path, etag=f'"{hashlib.sha256(tile.data).hexdigest()[:8]}"')
            )
        return tuple(out)


class FakeWitness:
    """A :class:`~mainline_anchor.ports.WitnessPushPort` that refuses an unpublished tree."""

    def __init__(
        self,
        log: CallLog,
        name: str,
        *,
        trust_domain: str = "example.test",
        adverse: bool = False,
        fail: str | None = None,
    ) -> None:
        self._log = log
        self._name = name
        self._trust_domain = trust_domain
        self._adverse = adverse
        self._fail = fail
        self.pushed: list[bytes] = []

    @property
    def name(self) -> str:
        return self._name

    def push(self, note: bytes) -> Cosignature:
        self._log.require_before(AnchorStep.PUSH_WITNESS, AnchorStep.PUBLISH_TILES)
        self._log.record(AnchorStep.PUSH_WITNESS, self._name)
        if self._fail is not None:
            raise RuntimeError(self._fail)
        self.pushed.append(note)
        return Cosignature(
            witness=self._name,
            trust_domain=self._trust_domain,
            adverse=self._adverse,
            signature_line=f"— {self._name} AAAAAAAA",
        )


# ── HTTP fake, for the TSA and beacon clients ─────────────────────────────────────────


class FakeTransport:
    """An :class:`~mainline_anchor.ports.HttpTransport` over a canned routing table."""

    def __init__(self, routes: dict[str, HttpResponse] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[tuple[str, str, bytes | None]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: Any = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        self.calls.append((method, url, body))
        self.last_headers = dict(headers or {})
        self.last_timeout = timeout
        if url not in self.routes:
            raise FakeCallRefused(f"no canned route for {method} {url}")
        return self.routes[url]
