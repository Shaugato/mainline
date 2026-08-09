# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One anchoring pass: beacon, sign, lock, timestamp, publish, push — in that order.

ARCHITECTURE.md §7.3 lists five steps. This module runs six, because the beacon that
bounds the checkpoint from *below* has to be inside the body before the body is signed,
and a step that is invisible in the code is a step nobody can assert the position of.

**The order is the product.** Each adjacent pair is an argument someone will attack:

============================  ==========================================================
adjacency                     what running them the other way round would cost
============================  ==========================================================
beacon → sign                 A body signed before its beacon lines are chosen is a
                              different body; there is no lower bound on a signature
                              over bytes that no longer exist.
sign → object lock            Archiving an unsigned root archives nothing anyone can
                              attribute to us. §7.3 step 3 locks the *note*.
object lock → timestamp       A timestamp over bytes we have not yet committed to keep
                              proves the bytes existed, not that we kept them. Lock
                              first and the TSA is timestamping something indelible.
timestamp → publish tiles     Serving proofs against a root with no upper time bound
                              invites a reader to rely on an unbounded claim.
publish tiles → push witness  A witness asked to cosign a root whose tiles are not yet
                              fetchable cannot check the consistency proof it is
                              supposed to check before cosigning.
============================  ==========================================================

**Failure is split, and the split is deliberate.** The first three steps are fatal: until
Object Lock accepts the note there is no commitment outside our control, so aborting
costs nothing but a retry. The last three are not: by then the object is indelible, and
raising would be pretending an event that physically happened did not. Their failures
become :class:`~mainline_anchor.ports.AnchorDebt` rows — the same shape as §7.3 step 5's
unwitnessed debt, where *permits still merge and the debt is what makes the next
checkpoint inadmissible*. Nothing here retries and nothing logs-and-continues.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

from trappoint_ledger.checkpoint import (
    CANON_EXTENSION,
    CanonExtension,
    build_body,
    build_checkpoint_note,
)
from trappoint_ledger.signer import sign_note_text

from mainline_anchor.ports import (
    FATAL_STEPS,
    MIN_TSA_AUTHORITIES,
    RETENTION_SLACK,
    RETENTION_YEARS,
    STEP_ORDER,
    AnchorAborted,
    AnchorDebt,
    AnchorMisconfigured,
    AnchorStep,
    ArchivedObject,
    BeaconPort,
    BeaconSnapshot,
    Cosignature,
    KmsSignPort,
    ObjectLockPort,
    PublishedTile,
    Tile,
    TilePublishPort,
    TimestampToken,
    TsaPort,
    WitnessPushPort,
    as_metadata,
)

__all__ = [
    "AnchorFanout",
    "AnchorRequest",
    "AnchorResult",
    "checkpoint_object_key",
    "retention_floor",
]

#: How many hex characters of the root hash go into the object key. Eight bytes is far
#: more than enough to separate two roots at one tree size and short enough that the key
#: stays readable in a CloudTrail record.
_KEY_ROOT_PREFIX_HEX: Final = 16

#: Tree size is zero-padded in the object key so that a plain lexicographic listing of
#: the bucket is in checkpoint order. Twenty digits covers any tree a real log will ever
#: have and costs nothing.
_KEY_TREE_SIZE_WIDTH: Final = 20


def checkpoint_object_key(origin: str, tree_size: int, root_hash: bytes) -> str:
    """Return the S3 key for one checkpoint note.

    The root hash is part of the key on purpose. Two notes at the same tree size over
    **different roots** is a fork, and a key that collided would put the second one at a
    version of the first — recoverable, since versioning is on, but only by someone who
    already suspected. Distinct keys make a fork two visible objects.

    Two notes at the same tree size over the *same* root are not a fork: ECDSA is
    randomised, so re-anchoring produces different signature bytes over an identical
    body. Those land at the same key as a second version, which is correct — both are
    retained and both verify.

    Args:
        origin: The log origin, ``mainline.<domain>/site/<site_code>``.
        tree_size: The number of leaves.
        root_hash: The 32-byte RFC 6962 root.

    Returns:
        ``checkpoint/<origin>/<0-padded size>-<root prefix>.note``.
    """
    return (
        f"checkpoint/{origin}/"
        f"{tree_size:0{_KEY_TREE_SIZE_WIDTH}d}-"
        f"{root_hash.hex()[:_KEY_ROOT_PREFIX_HEX]}.note"
    )


def retention_floor(now: datetime, *, years: int = RETENTION_YEARS) -> datetime:
    """Return the earliest ``RetainUntilDate`` the fanout will accept for a checkpoint.

    Args:
        now: The current time, timezone-aware.
        years: The retention period in whole years.

    Returns:
        ``now + years`` less one day of slack for clock skew between this process and S3.
    """
    return _plus_years(now, years) - RETENTION_SLACK


def _plus_years(when: datetime, years: int) -> datetime:
    """Add whole calendar years, rounding a 29 February start UP to 1 March.

    A COMPLIANCE retention can never be shortened, so the only direction it is safe to be
    wrong in is longer. Rounding down would silently produce a six-year-and-364-day
    retention on one day in four.
    """
    try:
        return when.replace(year=when.year + years)
    except ValueError:
        return when.replace(year=when.year + years, month=3, day=1)


@dataclass(frozen=True, slots=True)
class AnchorRequest:
    """Everything the fanout needs that is not a collaborator.

    The tree itself is not here. The RFC 6962 root and the tiles are computed by
    ``trappoint_ledger.merkle`` in the sequencer and handed over; this package does no
    hashing of leaves and owns no tree.
    """

    origin: str
    """Line 1 of the note, and the C2SP key name the signature line is keyed by."""

    tree_size: int
    """Line 2. The number of leaves. Zero is legal and anchors an empty log."""

    root_hash: bytes
    """Line 3, as 32 raw bytes."""

    canon: CanonExtension
    """The ``canon:`` extension — which canonicaliser produced this tree's leaves, and
    the SHA-256 of its source. Verifier check 10 compares it against the canonicaliser it
    is itself running, which is what puts the scheme's own code inside the scheme."""

    tiles: tuple[Tile, ...] = ()
    """Tiles to publish for this checkpoint. May be empty; the bundle carries proofs
    regardless, and tiles are a fetchability convenience for third parties."""


@dataclass(frozen=True, slots=True)
class AnchorResult:
    """What one anchoring pass produced, including what it failed to produce."""

    body: str
    """The checkpoint note text. These are the bytes the signature covers."""

    note: bytes
    """The complete signed note: body, blank line, signature line."""

    note_sha256: bytes
    """SHA-256 over :attr:`note` — the digest submitted to every TSA."""

    beacon: BeaconSnapshot
    archived: ArchivedObject
    timestamps: tuple[TimestampToken, ...] = ()
    tiles: tuple[PublishedTile, ...] = ()
    cosignatures: tuple[Cosignature, ...] = ()
    debts: tuple[AnchorDebt, ...] = ()
    steps: tuple[AnchorStep, ...] = ()
    """The steps that completed, in the order they completed."""

    @property
    def fully_anchored(self) -> bool:
        """Return whether every step completed with no debt."""
        return not self.debts and self.steps == STEP_ORDER

    @property
    def bracket(self) -> tuple[datetime, datetime] | None:
        """Return ``(lower, upper)``: the beacon floor and the earliest TSA ``genTime``.

        Returns:
            ``None`` when no timestamp was obtained, because a bracket with one side
            missing is not a bracket and must not be rendered as one.
        """
        if not self.timestamps:
            return None
        return (self.beacon.lower_bound(), min(t.gen_time for t in self.timestamps))


@dataclass
class _Trace:
    """Mutable bookkeeping for one pass. Never escapes this module."""

    steps: list[AnchorStep] = field(default_factory=list)
    debts: list[AnchorDebt] = field(default_factory=list)


class AnchorFanout:
    """The per-checkpoint fanout, assembled from ports and nothing else.

    Every collaborator is injected. There is no default that reaches the network, no
    module-level client, and no ``boto3`` import anywhere in this package — so a test
    that forgot to inject something fails with a ``TypeError`` at construction rather
    than by quietly contacting AWS.
    """

    __slots__ = (
        "_archive",
        "_authorities",
        "_beacon",
        "_clock",
        "_min_authorities",
        "_retention_years",
        "_signer",
        "_tiles",
        "_witnesses",
    )

    def __init__(
        self,
        *,
        beacon: BeaconPort,
        signer: KmsSignPort,
        archive: ObjectLockPort,
        authorities: Sequence[TsaPort],
        tiles: TilePublishPort | None = None,
        witnesses: Sequence[WitnessPushPort] = (),
        min_authorities: int = MIN_TSA_AUTHORITIES,
        retention_years: int = RETENTION_YEARS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Assemble a fanout, refusing a shape that cannot produce admissible evidence.

        Args:
            beacon: The two-beacon source.
            signer: The log key.
            archive: The COMPLIANCE Object Lock bucket.
            authorities: RFC 3161 authorities. At least ``min_authorities`` of them, with
                distinct names.
            tiles: The tile store. Required only if a request carries tiles.
            witnesses: C2SP witnesses. May be empty; the debt is then total and visible.
            min_authorities: The configured floor, defaulting to ARCHITECTURE §7.3's two.
            retention_years: Whole years of COMPLIANCE retention to require.
            clock: Returns the current time. Injected so a test is not a race.

        Raises:
            AnchorMisconfigured: If fewer than ``min_authorities`` authorities were given,
                if two authorities share a name, or if ``min_authorities`` is below two.
        """
        if min_authorities < MIN_TSA_AUTHORITIES:
            raise AnchorMisconfigured(
                f"min_authorities={min_authorities} is below {MIN_TSA_AUTHORITIES}; "
                "ARCHITECTURE.md §7.3 step 1 requires an upper time bound from at least "
                "two INDEPENDENT authorities, because a single TSA that is compromised, "
                "wrong or simply gone by the time anyone reads the bundle takes the "
                "entire upper bound with it"
            )
        if len(authorities) < min_authorities:
            raise AnchorMisconfigured(
                f"{len(authorities)} timestamp authorities configured, {min_authorities} required"
            )
        names = [authority.name for authority in authorities]
        if len(set(names)) != len(names):
            raise AnchorMisconfigured(
                f"timestamp authority names are not distinct: {names}; two tokens from "
                "one authority are one attestation wearing two hats"
            )
        witness_names = [witness.name for witness in witnesses]
        if len(set(witness_names)) != len(witness_names):
            raise AnchorMisconfigured(f"witness names are not distinct: {witness_names}")
        if retention_years < RETENTION_YEARS:
            raise AnchorMisconfigured(
                f"retention_years={retention_years} is below the {RETENTION_YEARS}-year "
                "floor in infra/modules/evidence-store"
            )
        self._beacon = beacon
        self._signer = signer
        self._archive = archive
        self._authorities = tuple(authorities)
        self._tiles = tiles
        self._witnesses = tuple(witnesses)
        self._min_authorities = min_authorities
        self._retention_years = retention_years
        self._clock = clock if clock is not None else _utc_now

    def anchor(self, request: AnchorRequest) -> AnchorResult:
        """Run one anchoring pass.

        Args:
            request: The checkpoint to anchor.

        Returns:
            The result, carrying whatever debt the non-fatal steps accrued.

        Raises:
            AnchorAborted: If the beacon, signing or Object Lock step failed.
            AnchorMisconfigured: If the request carries tiles and no tile store was wired.
        """
        if request.tiles and self._tiles is None:
            raise AnchorMisconfigured(
                f"the request carries {len(request.tiles)} tiles and no TilePublishPort "
                "was wired; publishing nowhere is not a degraded mode, it is a typo"
            )
        trace = _Trace()

        beacon = self._step_beacon(trace)
        body, note, digest = self._step_sign(request, beacon, trace)
        archived = self._step_object_lock(request, note, trace)
        timestamps = self._step_timestamp(digest, beacon, trace)
        published = self._step_publish(request, trace)
        cosignatures = self._step_push(note, trace)

        return AnchorResult(
            body=body,
            note=note,
            note_sha256=digest,
            beacon=beacon,
            archived=archived,
            timestamps=timestamps,
            tiles=published,
            cosignatures=cosignatures,
            debts=tuple(trace.debts),
            steps=tuple(trace.steps),
        )

    # ── step 1 · beacon ───────────────────────────────────────────────────────────────

    def _step_beacon(self, trace: _Trace) -> BeaconSnapshot:
        step = AnchorStep.BEACON
        try:
            snapshot = self._beacon.snapshot()
        except Exception as exc:
            raise self._fatal(step, f"beacon source failed: {exc!r}") from exc
        if not snapshot.drand.is_quicknet:
            raise self._fatal(
                step,
                f"the drand round is on chain {snapshot.drand.chain_hash}, not quicknet; "
                "ruling CU-4 pins the chain because the round-to-time arithmetic a "
                "stranger runs offline is only valid for quicknet's genesis and period",
            )
        lower = snapshot.lower_bound()
        now = self._now()
        if lower > now:
            raise self._fatal(
                step,
                f"the beacon lower bound {lower.isoformat()} is in the future relative to "
                f"this process's clock {now.isoformat()}; one of the two is wrong and a "
                "checkpoint minted from either is a backdating claim we would lose",
            )
        trace.steps.append(step)
        return snapshot

    # ── step 2 · sign ─────────────────────────────────────────────────────────────────

    def _step_sign(
        self, request: AnchorRequest, beacon: BeaconSnapshot, trace: _Trace
    ) -> tuple[str, bytes, bytes]:
        step = AnchorStep.SIGN
        extensions = ((CANON_EXTENSION, request.canon.value), *beacon.extensions())
        try:
            body = build_body(request.origin, request.tree_size, request.root_hash, extensions)
        except Exception as exc:
            raise self._fatal(step, f"the note body is malformed: {exc}") from exc
        try:
            # The C2SP key name for a MAINLINE checkpoint IS the origin. Passing anything
            # else would produce a note whose signature line names a key the verifier does
            # not look for, which reads to a stranger as an unsigned checkpoint.
            line = sign_note_text(self._signer, request.origin, body)
            note = build_checkpoint_note(body, [line])
        except Exception as exc:
            raise self._fatal(step, f"signing failed: {exc!r}") from exc
        trace.steps.append(step)
        return body, note, hashlib.sha256(note).digest()

    # ── step 3 · object lock ──────────────────────────────────────────────────────────

    def _step_object_lock(
        self, request: AnchorRequest, note: bytes, trace: _Trace
    ) -> ArchivedObject:
        step = AnchorStep.OBJECT_LOCK
        key = checkpoint_object_key(request.origin, request.tree_size, request.root_hash)
        metadata = as_metadata(request.origin, request.tree_size, request.root_hash)
        try:
            archived = self._archive.put_checkpoint(key=key, note=note, metadata=metadata)
        except Exception as exc:
            raise self._fatal(step, f"the archive refused the write: {exc!r}") from exc
        floor = retention_floor(self._now(), years=self._retention_years)
        # Deliberately NOT wrapped in AnchorAborted. `ObjectLockNotEnforced` is already an
        # `AnchorError`, and it is the one refusal in this package whose exact type a
        # caller will branch on: "the bucket accepted the write and is not holding it" is
        # a Class E evidentiary-integrity incident (ARCHITECTURE.md §11.6), not a retry.
        # Nothing after this line runs, which is the point — timestamping and publishing
        # would advertise a commitment that does not exist.
        archived.assert_indelible(floor=floor)
        trace.steps.append(step)
        return archived

    # ── step 4 · timestamp ────────────────────────────────────────────────────────────

    def _step_timestamp(
        self, digest: bytes, beacon: BeaconSnapshot, trace: _Trace
    ) -> tuple[TimestampToken, ...]:
        step = AnchorStep.TIMESTAMP
        tokens: list[TimestampToken] = []
        lower = beacon.lower_bound()
        for authority in self._authorities:
            try:
                token = authority.timestamp(digest)
            # BLE001 is suppressed here and at the two sites below, and the reason is the
            # opposite of the one the rule guards against. A TSA client, a tile store and a
            # witness are third-party collaborators whose exception taxonomies must not
            # leak into the fanout — and nothing is swallowed: every one of these handlers
            # records an `AnchorDebt` naming the target and the repr of the failure, which
            # the caller writes to `mainline.unwitnessed_debt` and which makes the next
            # checkpoint inadmissible. Narrowing to a named class here would let an
            # unanticipated one escape and abort a pass whose object is already indelible.
            except Exception as exc:  # noqa: BLE001 - recorded as debt, never swallowed
                trace.debts.append(AnchorDebt(step, authority.name, f"{exc!r}"))
                continue
            if token.message_imprint != digest:
                trace.debts.append(
                    AnchorDebt(
                        step,
                        authority.name,
                        "the token's messageImprint is not the note digest: "
                        f"{token.message_imprint.hex()} != {digest.hex()}",
                    )
                )
                continue
            if token.gen_time < lower:
                # The two bounds cross. Recorded, never silently dropped: a genTime
                # earlier than a beacon round that was already published is either a TSA
                # with a wrong clock or a forged token, and both are findings.
                trace.debts.append(
                    AnchorDebt(
                        step,
                        authority.name,
                        f"genTime {token.gen_time.isoformat()} precedes the beacon lower "
                        f"bound {lower.isoformat()}; the bracket is inverted",
                    )
                )
                continue
            tokens.append(token)
        if len(tokens) < self._min_authorities:
            trace.debts.append(
                AnchorDebt(
                    step,
                    "quorum",
                    f"{len(tokens)} usable tokens, {self._min_authorities} required; the "
                    "checkpoint is archived but its upper time bound is under-attested",
                )
            )
        trace.steps.append(step)
        return tuple(tokens)

    # ── step 5 · publish tiles ────────────────────────────────────────────────────────

    def _step_publish(self, request: AnchorRequest, trace: _Trace) -> tuple[PublishedTile, ...]:
        step = AnchorStep.PUBLISH_TILES
        published: tuple[PublishedTile, ...] = ()
        if request.tiles and self._tiles is not None:
            try:
                published = self._tiles.publish(request.tiles)
            except Exception as exc:  # noqa: BLE001 - recorded as debt, never swallowed
                trace.debts.append(AnchorDebt(step, "tile-store", f"{exc!r}"))
            else:
                missing = {tile.path for tile in request.tiles} - {p.path for p in published}
                if missing:
                    trace.debts.append(
                        AnchorDebt(step, "tile-store", f"tiles not published: {sorted(missing)}")
                    )
        trace.steps.append(step)
        return published

    # ── step 6 · push to witnesses ────────────────────────────────────────────────────

    def _step_push(self, note: bytes, trace: _Trace) -> tuple[Cosignature, ...]:
        step = AnchorStep.PUSH_WITNESS
        cosignatures: list[Cosignature] = []
        for witness in self._witnesses:
            try:
                cosignatures.append(witness.push(note))
            except Exception as exc:  # noqa: BLE001 - recorded as debt, never swallowed
                trace.debts.append(AnchorDebt(step, witness.name, f"{exc!r}"))
        if not self._witnesses:
            trace.debts.append(
                AnchorDebt(
                    step,
                    "quorum",
                    "no witnesses are configured, so this checkpoint has no external "
                    "cosignature at all; split-view resistance is not claimed",
                )
            )
        trace.steps.append(step)
        return tuple(cosignatures)

    # ── shared ────────────────────────────────────────────────────────────────────────

    def _fatal(self, step: AnchorStep, message: str) -> AnchorAborted:
        if step not in FATAL_STEPS:  # pragma: no cover - a guard on this module's own wiring
            raise AnchorMisconfigured(
                f"step {step.value} is not in FATAL_STEPS and must not abort a pass"
            )
        return AnchorAborted(step, message)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise AnchorMisconfigured(
                "the injected clock returned a naive datetime; a naive timestamp in an "
                "evidentiary path is an unanswerable question in cross-examination"
            )
        return now.astimezone(UTC)


def _utc_now() -> datetime:
    return datetime.now(UTC)


#: Exported so callers can express "seven years from now" without importing timedelta and
#: getting it subtly wrong. Not used internally; :func:`retention_floor` is.
SEVEN_YEARS_APPROX: Final = timedelta(days=365 * RETENTION_YEARS + 2)
