# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The per-checkpoint anchor fanout: beacon, sign, lock, timestamp, publish, push.

One import surface for the whole package. Everything reachable from here is either a
Protocol (the seam), a dataclass (the wire), or an adapter that speaks to exactly one
injected client.
"""

from __future__ import annotations

from mainline_anchor.aws import (
    S3ObjectLockArchive,
    S3TilePublisher,
    assert_region,
    kms_sign_port,
)
from mainline_anchor.beacon_client import (
    BeaconUnavailable,
    HttpBeaconSource,
    StaticBeaconSource,
)
from mainline_anchor.fanout import (
    AnchorFanout,
    AnchorRequest,
    AnchorResult,
    checkpoint_object_key,
    retention_floor,
)
from mainline_anchor.ports import (
    FATAL_STEPS,
    KMS_SIGNING_ALGORITHM,
    MIN_TSA_AUTHORITIES,
    OBJECT_LOCK_LEGAL_HOLD_ON,
    OBJECT_LOCK_MODE,
    RETENTION_YEARS,
    STEP_ORDER,
    AnchorAborted,
    AnchorDebt,
    AnchorError,
    AnchorMisconfigured,
    AnchorStep,
    ArchivedObject,
    BeaconPort,
    BeaconSnapshot,
    Cosignature,
    HttpResponse,
    HttpTransport,
    KmsSignPort,
    ObjectLockNotEnforced,
    ObjectLockPort,
    PublishedTile,
    Tile,
    TilePublishPort,
    TimestampToken,
    TsaPort,
    WitnessPushPort,
)
from mainline_anchor.tsa_client import (
    HttpTsaAuthority,
    TsaRejected,
    TsaResponseInvalid,
    UrllibTransport,
    build_timestamp_request,
    parse_timestamp_response,
)

__version__ = "0.1.0"

__all__ = [
    "FATAL_STEPS",
    "KMS_SIGNING_ALGORITHM",
    "MIN_TSA_AUTHORITIES",
    "OBJECT_LOCK_LEGAL_HOLD_ON",
    "OBJECT_LOCK_MODE",
    "RETENTION_YEARS",
    "STEP_ORDER",
    "AnchorAborted",
    "AnchorDebt",
    "AnchorError",
    "AnchorFanout",
    "AnchorMisconfigured",
    "AnchorRequest",
    "AnchorResult",
    "AnchorStep",
    "ArchivedObject",
    "BeaconPort",
    "BeaconSnapshot",
    "BeaconUnavailable",
    "Cosignature",
    "HttpBeaconSource",
    "HttpResponse",
    "HttpTransport",
    "HttpTsaAuthority",
    "KmsSignPort",
    "ObjectLockNotEnforced",
    "ObjectLockPort",
    "PublishedTile",
    "S3ObjectLockArchive",
    "S3TilePublisher",
    "StaticBeaconSource",
    "Tile",
    "TilePublishPort",
    "TimestampToken",
    "TsaPort",
    "TsaRejected",
    "TsaResponseInvalid",
    "UrllibTransport",
    "WitnessPushPort",
    "__version__",
    "assert_region",
    "build_timestamp_request",
    "checkpoint_object_key",
    "kms_sign_port",
    "parse_timestamp_response",
    "retention_floor",
]
