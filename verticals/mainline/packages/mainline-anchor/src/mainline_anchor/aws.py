# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The S3 and KMS adapters — the only place a boto3-shaped object is spoken to.

**`boto3` is not imported here, on any path.** The client is injected. That is the same
choice ``trappoint_ledger.signer.KmsSigner`` makes and for the same reason: AWS
credentials are not valid on the machine this package was written on, so *"we send
``ObjectLockMode='COMPLIANCE'``"* would otherwise be an unverified claim about the one
call the entire custody argument rests on. With the client injected, ``tests/fakes.py``
asserts the literal keyword arguments and the first live invocation fails loudly on a
mismatch instead of quietly writing an object nobody can rely on.

Three properties of the S3 write are worth stating because each is a way the naive
version is wrong:

1. **``PutObject`` succeeds against a bucket with no Object Lock configuration.** The
   lock parameters are accepted and ignored; you get an ordinary, deletable object and a
   200. Asking is therefore not evidence, so :meth:`S3ObjectLockArchive.put_checkpoint`
   reads the object's lock metadata back with ``HeadObject`` and
   :meth:`~mainline_anchor.ports.ArchivedObject.assert_indelible` refuses on disagreement.
2. **Retention and legal hold are different controls.** Retention answers *for how long*;
   a legal hold answers *and not even then*, has no expiry, and survives the retention
   period elapsing. Both are set — ARCHITECTURE.md §7.3 step 3 says "7-year default
   retention plus Legal Hold".
3. **A COMPLIANCE retention can never be shortened, by anyone, including the account
   root.** So every rounding decision in this module rounds the retention *up*. Being
   wrong long costs storage; being wrong short costs the evidence.

REGION PIN (ARCHITECTURE.md §10.1) is enforced here rather than assumed:
:func:`assert_region` refuses a client whose resolved region is not the one the caller
declared, because a gate that crosses a region is how an operator fixing latency
eventually routes around an invariant.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Final

from mainline_anchor.ports import (
    KMS_KEY_SPEC,
    KMS_MESSAGE_TYPE,
    KMS_SIGNING_ALGORITHM,
    OBJECT_LOCK_LEGAL_HOLD_ON,
    OBJECT_LOCK_MODE,
    RETENTION_YEARS,
    AnchorError,
    AnchorMisconfigured,
    ArchivedObject,
    KmsSignPort,
    PublishedTile,
    Tile,
)

__all__ = [
    "CHECKPOINT_CONTENT_TYPE",
    "TILE_CACHE_CONTROL",
    "TILE_CONTENT_TYPE",
    "S3ObjectLockArchive",
    "S3TilePublisher",
    "assert_region",
    "kms_sign_port",
    "plus_years",
]

#: A checkpoint note is UTF-8 text with LF line endings and a trailing newline. Serving it
#: as ``application/octet-stream`` would make a browser download it; a stranger who has
#: been sent a bundle should be able to click the archive URL and read the note.
CHECKPOINT_CONTENT_TYPE: Final = "text/plain; charset=utf-8"

#: Tiles are content-addressed by construction, so they are immutable for a year.
TILE_CACHE_CONTROL: Final = "public, max-age=31536000, immutable"
TILE_CONTENT_TYPE: Final = "application/octet-stream"

#: Ask S3 to compute and store a SHA-256 of the body. It is checked by S3 on the way in,
#: so a truncated upload is refused rather than stored, and it gives verifier check 8 a
#: second, service-attested digest of the same bytes.
_CHECKSUM_ALGORITHM: Final = "SHA256"


def assert_region(client: Any, expected_region: str | None) -> None:
    """Refuse a client that is not pointed at the region the caller declared.

    Args:
        client: A boto3-shaped client. Its ``meta.region_name`` is read if present.
        expected_region: The region the caller requires, or ``None`` to skip the check.

    Raises:
        AnchorMisconfigured: If the client's region disagrees.
    """
    if expected_region is None:
        return
    meta = getattr(client, "meta", None)
    actual = getattr(meta, "region_name", None)
    if actual is None:
        # Not fatal, and not silent either: a fake or a stub has no meta. The caller asked
        # for a region check and did not get one, so say so rather than pass.
        raise AnchorMisconfigured(
            f"expected_region={expected_region!r} was requested but the client exposes no "
            "meta.region_name, so REGION PIN could not be checked; pass "
            "expected_region=None to state that you know it is unchecked"
        )
    if actual != expected_region:
        raise AnchorMisconfigured(
            f"REGION PIN violated: the client resolves to {actual!r}, the caller requires "
            f"{expected_region!r} (ARCHITECTURE.md §10.1)"
        )


def plus_years(when: datetime, years: int) -> datetime:
    """Add whole calendar years, rounding a 29 February start UP to 1 March.

    Args:
        when: A timezone-aware instant.
        years: Whole years to add.

    Returns:
        The later instant.

    Raises:
        AnchorMisconfigured: If ``when`` is naive.
    """
    if when.tzinfo is None:
        raise AnchorMisconfigured("a retention date cannot be computed from a naive datetime")
    try:
        return when.replace(year=when.year + years)
    except ValueError:
        return when.replace(year=when.year + years, month=3, day=1)


def kms_sign_port(client: Any, key_id: str, *, expected_region: str | None = None) -> KmsSignPort:
    """Return the KMS-backed log signer, after checking the client's region.

    The signer itself is ``trappoint_ledger.signer.KmsSigner``: the Apache substrate owns
    the C2SP type-``0x02`` signature and this package does not restate it. What is added
    here is the REGION PIN check, which belongs to the deployment and not to the wire
    format.

    Args:
        client: An injected ``boto3`` KMS client.
        key_id: The key ARN or alias. ``ECC_NIST_P256`` / ``SIGN_VERIFY``; ``KmsSigner``
            verifies both against ``GetPublicKey`` on first use and raises otherwise.
        expected_region: REGION PIN, or ``None`` to skip.

    Returns:
        A :class:`~mainline_anchor.ports.KmsSignPort`.

    Raises:
        AnchorMisconfigured: On a region mismatch.
    """
    assert_region(client, expected_region)
    from trappoint_ledger.signer import KmsSigner

    # Annotated rather than returned bare: `trappoint-ledger` ships no `py.typed`, so
    # `KmsSigner` is `Any` here and an unannotated return would widen this function's
    # contract to `Any` without anyone noticing.
    signer: KmsSignPort = KmsSigner(client, key_id)
    return signer


class S3ObjectLockArchive:
    """Write checkpoint notes to the COMPLIANCE bucket, then verify the lock took.

    Implements :class:`~mainline_anchor.ports.ObjectLockPort`.
    """

    __slots__ = ("_bucket", "_client", "_clock", "_retention_years", "_verify_after_write")

    def __init__(
        self,
        client: Any,
        bucket: str,
        *,
        retention_years: int = RETENTION_YEARS,
        expected_region: str | None = None,
        clock: Any = None,
        verify_after_write: bool = True,
    ) -> None:
        """Bind an injected S3 client to one bucket.

        Args:
            client: A boto3-shaped S3 client. Never constructed here.
            bucket: The COMPLIANCE bucket from ``infra/modules/evidence-store``.
            retention_years: Whole years of retention to request per object.
            expected_region: REGION PIN, or ``None`` to skip.
            clock: A zero-argument callable returning an aware ``datetime``.
            verify_after_write: Read the object's lock metadata back with ``HeadObject``.
                Defaults to on. Turning it off is supported for a store that genuinely
                has no ``HeadObject``, and it is the caller's declaration that
                indelibility is then unchecked rather than proven.

        Raises:
            AnchorMisconfigured: On a region mismatch or a retention below the floor.
        """
        assert_region(client, expected_region)
        if retention_years < RETENTION_YEARS:
            raise AnchorMisconfigured(
                f"retention_years={retention_years} is below the {RETENTION_YEARS}-year "
                "floor that infra/modules/evidence-store sets as the bucket default"
            )
        self._client = client
        self._bucket = bucket
        self._retention_years = retention_years
        self._clock = clock if clock is not None else _utc_now
        self._verify_after_write = verify_after_write

    @property
    def bucket(self) -> str:
        """Return the bucket these checkpoints are written to."""
        return self._bucket

    def put_checkpoint(
        self, *, key: str, note: bytes, metadata: Mapping[str, str]
    ) -> ArchivedObject:
        """Write one note under COMPLIANCE retention and a legal hold.

        Args:
            key: The object key.
            note: The signed checkpoint note bytes.
            metadata: S3 user metadata — origin, tree size, root hash.

        Returns:
            The archived object, with its lock fields read back from S3 when
            ``verify_after_write`` is on and echoed from the request when it is not.

        Raises:
            AnchorError: If the ``PutObject`` response is not a mapping, or if
                ``HeadObject`` fails.
        """
        now = self._now()
        retain_until = plus_years(now, self._retention_years)
        response = self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=note,
            ContentType=CHECKPOINT_CONTENT_TYPE,
            ChecksumAlgorithm=_CHECKSUM_ALGORITHM,
            Metadata=dict(metadata),
            ObjectLockMode=OBJECT_LOCK_MODE,
            ObjectLockRetainUntilDate=retain_until,
            ObjectLockLegalHoldStatus=OBJECT_LOCK_LEGAL_HOLD_ON,
        )
        if not isinstance(response, Mapping):
            raise AnchorError(
                f"PutObject returned {type(response).__name__}, not a mapping; the write "
                "may or may not have happened and this process must not decide which"
            )
        version_id = str(response.get("VersionId", ""))
        etag = str(response.get("ETag", ""))
        if not self._verify_after_write:
            return ArchivedObject(
                bucket=self._bucket,
                key=key,
                version_id=version_id,
                etag=etag,
                object_lock_mode=OBJECT_LOCK_MODE,
                retain_until=retain_until,
                legal_hold_status=OBJECT_LOCK_LEGAL_HOLD_ON,
            )
        return self._head(key, version_id, etag)

    def _head(self, key: str, version_id: str, etag: str) -> ArchivedObject:
        """Read the written object's lock metadata back from the service."""
        kwargs: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if version_id:
            kwargs["VersionId"] = version_id
        head = self._client.head_object(**kwargs)
        if not isinstance(head, Mapping):
            raise AnchorError(
                f"HeadObject returned {type(head).__name__}, not a mapping, so the "
                "object's retention could not be read back"
            )
        retain = head.get("ObjectLockRetainUntilDate")
        return ArchivedObject(
            bucket=self._bucket,
            key=key,
            version_id=str(head.get("VersionId", version_id)),
            etag=str(head.get("ETag", etag)),
            object_lock_mode=_optional_str(head.get("ObjectLockMode")),
            retain_until=_as_aware(retain),
            legal_hold_status=_optional_str(head.get("ObjectLockLegalHoldStatus")),
            last_modified=_as_aware(head.get("LastModified")),
        )

    def _now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise AnchorMisconfigured(
                "the injected clock must return a timezone-aware datetime; a naive "
                "RetainUntilDate is an argument about which timezone we meant"
            )
        return now.astimezone(UTC)


class S3TilePublisher:
    """Publish RFC 6962 tiles to a plain (non-locked) bucket.

    Implements :class:`~mainline_anchor.ports.TilePublishPort`.

    Tiles are deliberately **not** under Object Lock. They are entirely derivable from the
    leaves, so locking them buys nothing and costs the ability to re-publish a corrupted
    tile — and ARCHITECTURE.md §10.2's three-way bucket split exists precisely because
    COMPLIANCE on the wrong content turns a mistake into a permanent liability.
    """

    __slots__ = ("_bucket", "_client", "_prefix")

    def __init__(
        self,
        client: Any,
        bucket: str,
        *,
        prefix: str = "tile/",
        expected_region: str | None = None,
    ) -> None:
        """Bind an injected S3 client to the tile bucket.

        Args:
            client: A boto3-shaped S3 client.
            bucket: The tile bucket.
            prefix: Key prefix for every tile.
            expected_region: REGION PIN, or ``None`` to skip.
        """
        assert_region(client, expected_region)
        self._client = client
        self._bucket = bucket
        self._prefix = prefix

    def publish(self, tiles: Any) -> tuple[PublishedTile, ...]:
        """Publish every tile, raising on the first failure.

        Args:
            tiles: A sequence of :class:`~mainline_anchor.ports.Tile`.

        Returns:
            The published tiles, in input order.

        Raises:
            AnchorError: If a ``PutObject`` response is not a mapping.
        """
        published: list[PublishedTile] = []
        for tile in tiles:
            if not isinstance(tile, Tile):
                raise AnchorError(f"expected a Tile, got {type(tile).__name__}")
            response = self._client.put_object(
                Bucket=self._bucket,
                Key=f"{self._prefix}{tile.path}",
                Body=tile.data,
                ContentType=TILE_CONTENT_TYPE,
                CacheControl=TILE_CACHE_CONTROL,
                ChecksumAlgorithm=_CHECKSUM_ALGORITHM,
            )
            if not isinstance(response, Mapping):
                raise AnchorError(
                    f"PutObject for tile {tile.path!r} returned "
                    f"{type(response).__name__}, not a mapping"
                )
            published.append(PublishedTile(path=tile.path, etag=str(response.get("ETag", ""))))
        return tuple(published)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _as_aware(value: Any) -> datetime | None:
    """Return a timezone-aware datetime, or ``None``.

    ``botocore`` returns aware datetimes for S3 date fields; a fake or a JSON round-trip
    may not. A naive value is coerced to UTC rather than accepted as-is, because the only
    alternative is comparing a naive instant with an aware one and raising ``TypeError``
    somewhere less informative.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    raise AnchorError(f"cannot read {value!r} as a datetime")


def _utc_now() -> datetime:
    return datetime.now(UTC)


#: Re-exported so a caller assembling the fanout can assert the KMS contract without
#: importing two modules. These are the values ``trappoint_ledger.signer.KmsSigner``
#: sends; ``tests/test_call_shapes.py`` asserts them as literals against a fake client,
#: which is what makes the re-export a claim with a test behind it.
KMS_CONTRACT: Final = {
    "SigningAlgorithm": KMS_SIGNING_ALGORITHM,
    "MessageType": KMS_MESSAGE_TYPE,
    "KeySpec": KMS_KEY_SPEC,
}
