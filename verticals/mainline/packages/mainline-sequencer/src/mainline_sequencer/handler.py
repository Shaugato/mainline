# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One Lambda per site, invoked by EventBridge every 15 seconds.

The loop is four steps and each one can decline without failing the invocation:

1. **Take the lease**, or find somebody else holding it and stop. A lost election is an
   ordinary outcome, costs one 15-second cycle, and is *not* retried — a loser that
   retried would be the second writer the lease exists to prevent.
2. **Select the batch by anti-join.** No rows is the normal steady state.
3. **Append**: one ``SERIALIZABLE`` transaction, ``seq`` derived in-transaction, the tree
   extended incrementally, the checkpoint signed and recorded.
4. **Release the lease** so the next tick does not wait out the TTL. Releasing is an
   optimisation; failing to release is not an error.

**Everything external is injected and nothing is fabricated.** AWS credentials are not
valid on the build machine, so :func:`lambda_handler` resolves its signer and its beacon
from the environment and the invocation event and raises :class:`RuntimeNotConfigured`
naming exactly what is missing. There is no default key, no synthesised beacon and no
"development mode" that signs with something else — a checkpoint signed by a key nobody
anchored is a weaker exhibit that *looks identical* to a strong one, which is the failure
this domain exists to refuse.

**The two beacon values arrive in the event, not from a network call here.** The anchor
fanout (``verticals/mainline/packages/mainline-anchor``) owns the drand and NIST clients;
the sequencer consumes their already-fetched values so that a beacon outage cannot become
a reason not to record a checkpoint, and so that this Lambda needs no egress.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg

from trappoint_jcs import CANON_VERSION, canon_src_sha256

from . import batch as batch_mod
from . import lease as lease_mod
from .append import (
    AppendResult,
    CheckpointInputs,
    LedgerAlgebra,
    Signer,
    append_batch,
    default_algebra,
    optional_symbol,
)

__all__ = [
    "APPLICATION_NAME",
    "DEFAULT_REGION",
    "RunReport",
    "RuntimeNotConfigured",
    "SequencerConfig",
    "checkpoint_inputs_from_event",
    "connect",
    "kms_signer_from_env",
    "lambda_handler",
    "run_once",
]

APPLICATION_NAME = "mainline-sequencer"

#: Bedrock and the evidence stack are in Sydney; the database is in Singapore
#: (``docs/adr/0002`` F5). The default names the KMS region only, and no claim of
#: end-to-end Australian residency follows from it.
DEFAULT_REGION = "ap-southeast-2"


class RuntimeNotConfigured(RuntimeError):
    """A required piece of deployment configuration is absent.

    Raised instead of substituting a default, because every default this function could
    invent — a software signing key, a synthesised beacon, a guessed origin — produces a
    checkpoint that is indistinguishable from a real one at a glance and worthless under
    examination.
    """


@dataclass(frozen=True, slots=True)
class SequencerConfig:
    """What one invocation needs to know about itself."""

    site_code: str
    origin: str
    holder: str
    batch_size: int = batch_mod.DEFAULT_BATCH_SIZE
    lease_ttl_seconds: int = lease_mod.DEFAULT_TTL_SECONDS


@dataclass(frozen=True, slots=True)
class RunReport:
    """What one invocation did, in a shape CloudWatch can read."""

    site_code: str
    holder: str
    leader: bool
    epoch: int | None
    selected: int
    appended: int
    already_sequenced: int
    tree_size: int | None
    root_hash: str | None
    checkpoint_written: bool
    attempts: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        """Flatten for the Lambda return value and the structured log line."""
        return {
            "site_code": self.site_code,
            "holder": self.holder,
            "leader": self.leader,
            "epoch": self.epoch,
            "selected": self.selected,
            "appended": self.appended,
            "already_sequenced": self.already_sequenced,
            "tree_size": self.tree_size,
            "root_hash": self.root_hash,
            "checkpoint_written": self.checkpoint_written,
            "attempts": self.attempts,
            "reason": self.reason,
        }


@contextmanager
def connect(dsn: str) -> Iterator[psycopg.Connection[Any]]:
    """Open a connection with the sequencer's discipline applied.

    Isolation is set explicitly rather than inherited from a server or pool default
    (``spec/errors.md`` §2.1): CockroachDB's default *is* ``SERIALIZABLE``, and this line
    exists precisely so the claim does not rest on that default. ``autocommit=True`` with
    explicit ``conn.transaction()`` blocks means every transaction boundary in this
    package is visible in the source rather than implied by the driver.
    """
    conn = psycopg.connect(dsn, autocommit=True, application_name=APPLICATION_NAME)
    try:
        conn.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
        yield conn
    finally:
        conn.close()


def run_once(
    conn: psycopg.Connection[Any],
    *,
    config: SequencerConfig,
    signer: Signer,
    checkpoint: CheckpointInputs,
    algebra: LedgerAlgebra | None = None,
) -> RunReport:
    """Contest the lease, select a batch, append it, and release.

    Returns:
        A report. A non-leader run and an empty batch are both reported rather than
        raised: neither is a failure, and an alarm that fires on the steady state is an
        alarm somebody switches off.
    """
    held = lease_mod.contend(
        conn,
        site_code=config.site_code,
        holder=config.holder,
        ttl_seconds=config.lease_ttl_seconds,
    )
    if held is None:
        return RunReport(
            site_code=config.site_code,
            holder=config.holder,
            leader=False,
            epoch=None,
            selected=0,
            appended=0,
            already_sequenced=0,
            tree_size=None,
            root_hash=None,
            checkpoint_written=False,
            attempts=0,
            reason="another holder has an unexpired lease; this invocation stands down",
        )

    try:
        rows = batch_mod.unsequenced(conn, site_code=config.site_code, limit=config.batch_size)
        if not rows:
            return RunReport(
                site_code=config.site_code,
                holder=config.holder,
                leader=True,
                epoch=held.epoch,
                selected=0,
                appended=0,
                already_sequenced=0,
                tree_size=None,
                root_hash=None,
                checkpoint_written=False,
                attempts=0,
                reason="no unsequenced intake rows",
            )
        result: AppendResult = append_batch(
            conn,
            site_code=config.site_code,
            rows=rows,
            signer=signer,
            checkpoint=checkpoint,
            algebra=algebra if algebra is not None else default_algebra(),
        )
    finally:
        lease_mod.release(conn, held)

    return RunReport(
        site_code=config.site_code,
        holder=config.holder,
        leader=True,
        epoch=held.epoch,
        selected=len(rows),
        appended=result.appended,
        already_sequenced=result.already_sequenced,
        tree_size=result.tree_size,
        root_hash=result.root_hash.hex() if result.root_hash is not None else None,
        checkpoint_written=result.checkpoint_written,
        attempts=result.attempts,
        reason="appended" if result.appended else "every selected row was already sequenced",
    )


# ── Deployment wiring. Nothing here invents a value it cannot find. ────────────────────


def _required_env(name: str, why: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeNotConfigured(f"{name} is unset. {why}")
    return value


def kms_signer_from_env() -> Signer:
    """Build the KMS signer named by ``MAINLINE_LOG_KMS_KEY_ID``.

    ``boto3`` and ``trappoint_ledger`` are imported inside the function so that neither
    is on the import path of a test that only exercises the sequencing logic. The signer
    itself lives in ``packages/trappoint-ledger``: the point of KMS is that a T1
    adversary with arbitrary SQL has no path to ``kms:Sign``, and a software key living
    in this Lambda's memory would destroy exactly that argument.

    Raises:
        RuntimeNotConfigured: if the key id is unset, or if ``boto3`` or
            ``trappoint_ledger.signer.KmsSigner`` is unavailable.
    """
    key_id = _required_env(
        "MAINLINE_LOG_KMS_KEY_ID",
        "the checkpoint signature is the only object in this design that leaves our "
        "trust boundary; there is no fallback key and there must not be one.",
    )
    region = os.environ.get("AWS_REGION", DEFAULT_REGION)
    kms_signer = optional_symbol("trappoint_ledger.signer", "KmsSigner")
    if kms_signer is None:
        raise RuntimeNotConfigured(
            "trappoint_ledger.signer.KmsSigner is not importable. The signer lives in the "
            "substrate package on purpose: the point of KMS is that a T1 adversary holding "
            "arbitrary SQL has no path to kms:Sign, and a software key in this Lambda's "
            "memory would destroy exactly that argument — so there is no local fallback."
        )
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeNotConfigured(
            f"the KMS signer needs boto3, which is not installed: {exc}"
        ) from exc
    signer: Signer = kms_signer(client=boto3.client("kms", region_name=region), key_id=key_id)
    return signer


def checkpoint_inputs_from_event(event: Mapping[str, Any], *, origin: str) -> CheckpointInputs:
    """Read the two beacon extension values out of the invocation event.

    Expected shape, produced by ``mainline-anchor``'s beacon clients::

        {
            "beacon": {
                "drand": "<chain hash> <round> <randomness>",
                "nist": "2.0 <chainIndex>.<pulseIndex> <outputValue>",
            }
        }

    Both are REQUIRED. A checkpoint without a beacon has no lower time bound, and
    ``ledger_checkpoint.beacon`` is ``NOT NULL`` besides. The values are validated by
    :class:`~mainline_sequencer.append.CheckpointInputs`, so a malformed line is refused
    here rather than by the stranger running the verifier.

    Raises:
        RuntimeNotConfigured: if either value is absent.
    """
    beacon = event.get("beacon")
    if not isinstance(beacon, Mapping):
        raise RuntimeNotConfigured(
            "the invocation event carries no 'beacon' object. The sequencer does not "
            "fetch beacons itself — mainline-anchor owns the drand and NIST clients, so "
            "this Lambda needs no egress — and it will not sign a checkpoint with no "
            "lower time bound."
        )
    drand = beacon.get("drand")
    nist = beacon.get("nist")
    if not isinstance(drand, str) or not isinstance(nist, str):
        raise RuntimeNotConfigured(
            "event['beacon'] must carry BOTH 'drand' and 'nist' as strings. Two beacons, "
            "two independent issuers, and only one of them verifiable under the "
            "verifier's dependency floor (CU-4) — dropping either is dropping a bound "
            "the report would still print."
        )
    return CheckpointInputs(
        origin=origin,
        payload_ver=CANON_VERSION,
        canon_src_sha256=canon_src_sha256(),
        drand=drand,
        nist=nist,
    )


def lambda_handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """EventBridge entry point.

    Configuration, all of it explicit:

    ==============================  ==========================================
    ``MAINLINE_SEQUENCER_DSN``      required
    ``MAINLINE_LOG_DOMAIN``         required — origin is ``mainline.<domain>/site/<site>``
    ``MAINLINE_SITE_CODE``          required unless ``event['site_code']`` is given
    ``MAINLINE_LOG_KMS_KEY_ID``     required
    ``MAINLINE_SEQUENCER_BATCH``    optional, default 512, ceiling 2048
    ``MAINLINE_LEASE_TTL_SECONDS``  optional, default 60
    ``AWS_REGION``                  optional, default ap-southeast-2
    ==============================  ==========================================

    The holder id is the Lambda request id when there is one. It is opaque and is only
    ever compared — but taking it from the invocation rather than from the container
    means a warm container that is invoked twice concurrently presents two identities,
    and the lease's ``holder = $me`` disjunct then does not hand both of them the log.
    """
    dsn = _required_env("MAINLINE_SEQUENCER_DSN", "the sequencer has no database to sequence.")
    domain = _required_env(
        "MAINLINE_LOG_DOMAIN",
        "spec/wire/checkpoint.md §3 fixes the origin as 'mainline.<domain>/site/<site_code>' "
        "and a guessed origin is a log identity a witness will refuse.",
    )
    site_code = str(event.get("site_code") or "") or _required_env(
        "MAINLINE_SITE_CODE", "one Lambda sequences one site; there is no all-sites mode."
    )
    origin = f"mainline.{domain}/site/{site_code}"

    config = SequencerConfig(
        site_code=site_code,
        origin=origin,
        holder=str(getattr(context, "aws_request_id", "") or uuid.uuid4()),
        batch_size=int(os.environ.get("MAINLINE_SEQUENCER_BATCH", batch_mod.DEFAULT_BATCH_SIZE)),
        lease_ttl_seconds=int(
            os.environ.get("MAINLINE_LEASE_TTL_SECONDS", lease_mod.DEFAULT_TTL_SECONDS)
        ),
    )
    checkpoint = checkpoint_inputs_from_event(event, origin=origin)
    signer = kms_signer_from_env()

    with connect(dsn) as conn:
        report = run_once(conn, config=config, signer=signer, checkpoint=checkpoint)
    return report.as_dict()
