# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Every external system the anchor fanout touches, as a Protocol.

ARCHITECTURE.md §7.3 names five anchoring steps and a beacon that must already be inside
the body before the first of them runs. Each of those systems is somebody else's: AWS
KMS, AWS S3, two RFC 3161 authorities, drand and NIST, a tile store, and a set of
witnesses chosen for *adverse* legal interest. **AWS credentials are not valid on the
machine this package was written on**, so every one of them is a `typing.Protocol` with
an in-process fake in ``tests/fakes.py``, and the fakes assert the exact call shape.

That is not a testing convenience, it is the mitigation for risk 3 in
``docs/leads/custody.md`` §6: *an unexercised path is a broken path*. A fake that accepts
any keyword argument would let the first live invocation write a checkpoint object with
GOVERNANCE retention, or none, and S3 Object Lock cannot be retrofitted onto an object
any more than onto a bucket (GT-18). The fakes therefore refuse anything that is not
literally ``ObjectLockMode='COMPLIANCE'``, ``ObjectLockLegalHoldStatus='ON'`` and
``SigningAlgorithm='ECDSA_SHA_256'``, so the failure happens here rather than in a
deposition.

**Nothing in this module imports boto3, urllib or cryptography.** The protocols are the
seam; the adapters in :mod:`mainline_anchor.aws`, :mod:`mainline_anchor.tsa_client` and
:mod:`mainline_anchor.beacon_client` are where a real SDK object is finally spoken to,
and even there the client is injected rather than constructed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final, Protocol, runtime_checkable

from trappoint_ledger.beacon import DrandRound, NistPulse

__all__ = [
    "FATAL_STEPS",
    "KMS_KEY_SPEC",
    "KMS_MESSAGE_TYPE",
    "KMS_SIGNING_ALGORITHM",
    "MIN_TSA_AUTHORITIES",
    "OBJECT_LOCK_LEGAL_HOLD_ON",
    "OBJECT_LOCK_MODE",
    "RETENTION_YEARS",
    "STEP_ORDER",
    "AnchorAborted",
    "AnchorDebt",
    "AnchorError",
    "AnchorMisconfigured",
    "AnchorStep",
    "ArchivedObject",
    "BeaconPort",
    "BeaconSnapshot",
    "Cosignature",
    "HttpResponse",
    "HttpTransport",
    "KmsSignPort",
    "ObjectLockNotEnforced",
    "ObjectLockPort",
    "PublishedTile",
    "Tile",
    "TilePublishPort",
    "TimestampToken",
    "TsaPort",
    "WitnessPushPort",
]

# ── The four literals the whole indelibility argument rests on ────────────────────────
#
# They are `Final` module constants and not parameters, for the same reason
# `trappoint_ledger.signer.KMS_MESSAGE_TYPE` is: a value that can be passed in is a value
# that can be passed in wrong, and the wrong value here is unrecoverable rather than
# merely broken.

#: S3 Object Lock retention mode. GOVERNANCE can be bypassed by a principal holding
#: ``s3:BypassGovernanceRetention``; COMPLIANCE cannot be bypassed by anyone, including
#: the account root. The custody bucket is COMPLIANCE and the bulk and audit buckets
#: deliberately are not — see ARCHITECTURE.md §10.2 and ``infra/modules/evidence-store``.
OBJECT_LOCK_MODE: Final = "COMPLIANCE"

#: A legal hold has no expiry and is independent of the retention period. Retention
#: answers "for how long"; the hold answers "and not even then". Both are set.
OBJECT_LOCK_LEGAL_HOLD_ON: Final = "ON"

#: Seven years, the retention floor in ``infra/modules/evidence-store``. Set once at
#: provisioning as the bucket default and again per object here, because a bucket default
#: that is later relaxed changes nothing about objects already written but changes
#: everything about the next one.
RETENTION_YEARS: Final = 7

#: KMS ``Sign`` parameters. ``RAW`` means KMS hashes the note text itself; ``DIGEST``
#: would have KMS treat several hundred bytes of note text as if it were a SHA-256 digest
#: and emit a signature no verifier on earth accepts.
KMS_SIGNING_ALGORITHM: Final = "ECDSA_SHA_256"
KMS_MESSAGE_TYPE: Final = "RAW"
KMS_KEY_SPEC: Final = "ECC_NIST_P256"

#: ARCHITECTURE.md §7.3 step 1: "from >= 2 independent TSAs". Two authorities under
#: different jurisdictions and different roots is what makes the upper bound survive one
#: of them being wrong, compromised or simply gone by the time anyone reads the bundle.
MIN_TSA_AUTHORITIES: Final = 2

#: How far a returned ``RetainUntilDate`` may fall short of the computed seven years
#: before the fanout treats the bucket as misconfigured. One day absorbs clock skew
#: between this process and S3 and nothing else.
RETENTION_SLACK: Final = timedelta(days=1)


class AnchorStep(StrEnum):
    """The ordered steps of one anchoring pass.

    The order is the argument, not an implementation detail. Signing a root that is not
    yet bounded from below by a beacon signs an unbounded claim; timestamping bytes that
    are not yet in Object Lock timestamps bytes we could still choose not to keep;
    publishing tiles or pushing to a witness before either is advertising a commitment
    that does not exist yet.
    """

    BEACON = "beacon"
    SIGN = "sign"
    OBJECT_LOCK = "object_lock"
    TIMESTAMP = "timestamp"
    PUBLISH_TILES = "publish_tiles"
    PUSH_WITNESS = "push_witness"


#: The only legal order. ``tests/test_fanout_order.py`` asserts it twice: once over the
#: fanout's own trace, and once over a call log the fakes write to, because a trace the
#: code under test maintains is a claim and a call log the collaborators write is
#: evidence.
STEP_ORDER: Final = (
    AnchorStep.BEACON,
    AnchorStep.SIGN,
    AnchorStep.OBJECT_LOCK,
    AnchorStep.TIMESTAMP,
    AnchorStep.PUBLISH_TILES,
    AnchorStep.PUSH_WITNESS,
)

#: Steps whose failure aborts the pass. The split is not arbitrary.
#:
#: BEACON, SIGN and OBJECT_LOCK are fatal because until the third of them completes there
#: is no commitment outside our control, and a partially-anchored checkpoint is a
#: checkpoint we can still quietly abandon — the exact property the design exists to
#: remove.
#:
#: TIMESTAMP, PUBLISH_TILES and PUSH_WITNESS are NOT fatal, because by the time they run
#: the object is already indelible: raising there would abort a transaction that has
#: physically already happened, and the honest record of a TSA being down is a debt row,
#: not a rollback. This is the same shape as the unwitnessed-debt rule in §7.3 step 5 —
#: *going dark stays possible and self-reports*.
FATAL_STEPS: Final = frozenset({AnchorStep.BEACON, AnchorStep.SIGN, AnchorStep.OBJECT_LOCK})


class AnchorError(RuntimeError):
    """Base class for every refusal this package raises."""


class AnchorMisconfigured(AnchorError):
    """The fanout was assembled in a shape that cannot produce admissible evidence.

    Raised from ``__init__``, never from ``anchor()``. A fanout with one TSA, or with
    tiles to publish and nowhere to publish them, is a defect in wiring and the right
    time to find it is process start-up rather than the first checkpoint.
    """


class AnchorAborted(AnchorError):
    """A fatal step failed; nothing after it ran.

    Attributes:
        step: The step that failed.
    """

    def __init__(self, step: AnchorStep, message: str) -> None:
        super().__init__(f"anchor aborted at step {step.value}: {message}")
        self.step = step


class ObjectLockNotEnforced(AnchorError):
    """S3 accepted the write but did not report the retention we asked for.

    This is the single most important refusal in the package. ``PutObject`` succeeds
    against a bucket with no Object Lock configuration, silently, returning an ordinary
    object; the request parameters are then simply ignored. Asking is therefore not
    evidence of anything, and the fanout reads the object's own metadata back and refuses
    when it disagrees.
    """


@dataclass(frozen=True, slots=True)
class BeaconSnapshot:
    """The two public randomness values quoted by one checkpoint body (CU-4)."""

    drand: DrandRound
    """A drand quicknet round. Verifiable arithmetically offline; its BLS signature is
    not verifiable under the ``cryptography``-only dependency floor."""

    nist: NistPulse
    """A NIST Interoperable Randomness Beacon 2.0 pulse. RSA/SHA-512 with an X.509
    certificate, so it IS verifiable under the floor. This is the load-bearing one."""

    def extensions(self) -> tuple[tuple[str, str], ...]:
        """Return the ``drand:`` and ``nist:`` extension pairs, in §4's fixed order."""
        return (
            ("drand", self.drand.extension_value()),
            ("nist", self.nist.extension_value()),
        )

    def lower_bound(self) -> datetime:
        """Return the later of the two beacons' issue times.

        Returns:
            The instant before which this checkpoint cannot have been constructed. The
            drand round time is arithmetic from quicknet's genesis and period; the NIST
            pulse contributes a time only when it was fetched rather than parsed off a
            note, so it is used when present and ignored when not.
        """
        # The explicit annotations are load-bearing for mypy, not decoration:
        # `packages/trappoint-ledger` ships no `py.typed` marker today, so every symbol
        # imported from it is `Any` and a bare `return` here would silently widen this
        # method's contract to `Any`. Noted for that package's owner in the worker output.
        drand_time: datetime = self.drand.round_time()
        nist_time: datetime | None = self.nist.timestamp
        if nist_time is None:
            return drand_time
        return max(drand_time, nist_time)


@dataclass(frozen=True, slots=True)
class ArchivedObject:
    """What S3 reported back about a checkpoint object, after it was written.

    Every field here is read from the service, not remembered from the request. That
    distinction is the whole point: :meth:`assert_indelible` is a check on the bucket's
    behaviour, and a check performed against our own memory of what we asked for would
    pass on a bucket with Object Lock switched off.
    """

    bucket: str
    key: str
    version_id: str
    etag: str
    object_lock_mode: str | None
    retain_until: datetime | None
    legal_hold_status: str | None
    last_modified: datetime | None = None

    def assert_indelible(self, *, floor: datetime) -> None:
        """Refuse unless S3 reports COMPLIANCE, a legal hold, and retention past ``floor``.

        Args:
            floor: The earliest acceptable ``RetainUntilDate``, normally seven years from
                now less :data:`RETENTION_SLACK`.

        Raises:
            ObjectLockNotEnforced: On any disagreement, naming the field.
        """
        if not self.version_id:
            raise ObjectLockNotEnforced(
                f"s3://{self.bucket}/{self.key} came back with no VersionId, so the "
                "bucket is not versioned; Object Lock requires versioning and neither "
                "can be enabled after the fact (GT-18)"
            )
        if self.object_lock_mode != OBJECT_LOCK_MODE:
            raise ObjectLockNotEnforced(
                f"s3://{self.bucket}/{self.key} reports ObjectLockMode="
                f"{self.object_lock_mode!r}, not {OBJECT_LOCK_MODE!r}; a GOVERNANCE or "
                "absent retention can be removed by a principal holding "
                "s3:BypassGovernanceRetention, which makes this object a copy rather "
                "than a commitment"
            )
        if self.legal_hold_status != OBJECT_LOCK_LEGAL_HOLD_ON:
            raise ObjectLockNotEnforced(
                f"s3://{self.bucket}/{self.key} reports ObjectLockLegalHoldStatus="
                f"{self.legal_hold_status!r}, not {OBJECT_LOCK_LEGAL_HOLD_ON!r}"
            )
        if self.retain_until is None or self.retain_until < floor:
            raise ObjectLockNotEnforced(
                f"s3://{self.bucket}/{self.key} reports RetainUntilDate="
                f"{self.retain_until!r}, which is earlier than the required floor "
                f"{floor.isoformat()}"
            )


@dataclass(frozen=True, slots=True)
class TimestampToken:
    """One RFC 3161 token, with the fields the fanout itself checks.

    Full verification — the CMS ``SignedData`` signature, the chain to a trusted root —
    is verifier check 5 and lives in ``trappoint-verify`` under ruling CU-8. What this
    package checks is narrower and still worth checking at the boundary: that the token
    the authority returned is a timestamp over **our** digest.
    """

    authority: str
    """A stable name for the authority, used to prove the two tokens are independent."""

    token_der: bytes
    """The ``TimeStampToken`` ContentInfo, DER, exactly as returned."""

    gen_time: datetime
    """``TSTInfo.genTime`` — the upper time bound this token contributes."""

    message_imprint: bytes
    """``TSTInfo.messageImprint.hashedMessage``. Compared against the note digest."""


@dataclass(frozen=True, slots=True)
class Tile:
    """One RFC 6962 tile to publish. Path and bytes are the caller's to compute."""

    path: str
    data: bytes


@dataclass(frozen=True, slots=True)
class PublishedTile:
    """A tile that reached the tile store."""

    path: str
    etag: str


@dataclass(frozen=True, slots=True)
class Cosignature:
    """A witness's cosignature over ``(origin, size, root)``.

    ``adverse`` is a claim about legal interest and not a cryptographic property. It is
    carried here because verifier check 7 needs it and refuses to infer it, and because
    ``docs/leads/custody.md`` §6 risk 1 requires that a quorum of one non-adverse witness
    is reported as exactly that. **Split-view resistance is not claimed.**
    """

    witness: str
    trust_domain: str
    adverse: bool
    signature_line: str


@dataclass(frozen=True, slots=True)
class AnchorDebt:
    """A non-fatal step that did not complete, recorded rather than swallowed.

    Nothing in this package retries and nothing logs-and-continues. A debt is a value on
    the result that the caller writes to ``mainline.unwitnessed_debt``; a checkpoint with
    open debt is not admissible, which is how "going dark stays possible and
    self-reports" is implemented rather than promised.
    """

    step: AnchorStep
    target: str
    reason: str


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A minimal HTTP response. Enough for a TSA POST and a beacon GET, and no more."""

    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class HttpTransport(Protocol):
    """The one network primitive this package uses.

    A Protocol rather than ``requests``: the anchor runs in a Lambda whose egress is an
    enumerated allowlist (ARCHITECTURE.md §10.3, "Custody: ... NAT to the RFC 3161 TSAs,
    the beacon and the external witnesses"), and a transport that can be swapped is a
    transport whose destinations can be asserted in a test.
    """

    def request(
        self,
        method: str,
        url: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        """Perform one request and return the response, without raising on 4xx/5xx."""
        ...


@runtime_checkable
class KmsSignPort(Protocol):
    """The log signing key.

    Structurally identical to :class:`trappoint_ledger.signer.Signer`, deliberately: the
    real implementation IS ``trappoint_ledger.signer.KmsSigner``, and restating the shape
    here is what lets this package depend on the *capability* rather than on that class.
    """

    def sign(self, body: bytes) -> bytes:
        """Return the ASN.1 DER ECDSA signature over ``body`` (the message, not a digest)."""
        ...

    def public_key_spki_der(self) -> bytes:
        """Return the DER ``SubjectPublicKeyInfo`` of the public key."""
        ...


@runtime_checkable
class ObjectLockPort(Protocol):
    """The COMPLIANCE-locked, versioned, separate-account checkpoint archive."""

    def put_checkpoint(
        self, *, key: str, note: bytes, metadata: Mapping[str, str]
    ) -> ArchivedObject:
        """Write one checkpoint note under Object Lock and report what the store says.

        Implementations MUST read the resulting object's lock metadata back from the
        service rather than echoing the request, because :meth:`ArchivedObject.
        assert_indelible` is only a check if the values it reads came from S3.
        """
        ...


@runtime_checkable
class TsaPort(Protocol):
    """One RFC 3161 timestamp authority."""

    @property
    def name(self) -> str:
        """A stable identifier, used to prove two tokens came from two authorities."""
        ...

    def timestamp(self, digest: bytes) -> TimestampToken:
        """Return a token over ``digest``, refusing a token whose imprint disagrees."""
        ...


@runtime_checkable
class BeaconPort(Protocol):
    """The two public randomness beacons quoted in the checkpoint body."""

    def snapshot(self) -> BeaconSnapshot:
        """Return the current drand round and NIST pulse."""
        ...


@runtime_checkable
class TilePublishPort(Protocol):
    """Where RFC 6962 tiles are served from, so a stranger can fetch proofs."""

    def publish(self, tiles: Sequence[Tile]) -> tuple[PublishedTile, ...]:
        """Publish every tile, or raise."""
        ...


@runtime_checkable
class WitnessPushPort(Protocol):
    """One C2SP ``tlog-witness``. The ledger pushes to its adversaries; it does not wait."""

    @property
    def name(self) -> str:
        """A stable identifier for the witness."""
        ...

    def push(self, note: bytes) -> Cosignature:
        """Send the signed note and return the cosignature, or raise."""
        ...


def as_metadata(origin: str, tree_size: int, root_hash: bytes) -> dict[str, str]:
    """Return the S3 user metadata carried alongside a checkpoint object.

    S3 lowercases user-metadata keys and the SDK does not, so the keys are lowercase and
    hyphenated here to make the stored form and the requested form the same string.

    Args:
        origin: The log origin — line 1 of the note.
        tree_size: Line 2.
        root_hash: Line 3, as raw bytes.

    Returns:
        A mapping suitable for ``PutObject(Metadata=...)``.
    """
    return {
        "origin": origin,
        "tree-size": str(tree_size),
        "root-sha256": root_hash.hex(),
    }


def coerce_any_mapping(value: Any) -> Mapping[str, Any]:
    """Return ``value`` as a mapping, or raise a typed error naming what arrived.

    Used at every SDK and HTTP boundary in this package. ``boto3`` returns plain dicts
    and a JSON body decodes to whatever the server sent, so "it is a mapping" is an
    assumption, and an assumption at an evidence boundary is checked here rather than
    discovered as an ``AttributeError`` three frames later.

    Args:
        value: Anything.

    Returns:
        The value, typed as a mapping.

    Raises:
        AnchorError: If it is not one.
    """
    if not isinstance(value, Mapping):
        raise AnchorError(f"expected a JSON object, got {type(value).__name__}")
    return value
