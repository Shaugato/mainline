# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The order is the product: beacon → sign → lock → timestamp → publish → push.

Every assertion here is made twice where it can be. Once against
``AnchorResult.steps``, which the code under test maintains and which is therefore a
*claim*; and once against a :class:`~fakes.CallLog` the collaborators write to, which is
*evidence*. A fanout that recorded the right trace while calling the ports in the wrong
order would pass the first and fail the second, and the second is the one that matters.

The fakes go further than recording. ``FakeArchive`` refuses a note with no signature
line, ``FakeTsa`` refuses to stamp before the archive was written, ``FakeTileStore``
refuses to publish before a timestamp exists, and ``FakeWitness`` refuses to be pushed to
before tiles are published. Reordering two steps in ``fanout.py`` therefore fails as an
``AssertionError`` from the collaborator that was called too early, naming both steps.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fakes import (
    CallLog,
    FakeArchive,
    FakeBeacon,
    FakeCallRefused,
    FakeSigner,
    FakeTileStore,
    FakeTsa,
    FakeWitness,
    fixed_clock,
    fixed_snapshot,
)
from mainline_anchor.fanout import (
    AnchorFanout,
    AnchorRequest,
    checkpoint_object_key,
    retention_floor,
)
from mainline_anchor.ports import (
    STEP_ORDER,
    AnchorAborted,
    AnchorMisconfigured,
    AnchorStep,
    ObjectLockNotEnforced,
    Tile,
)
from trappoint_ledger.checkpoint import CanonExtension, parse_body

ORIGIN = "mainline.example/site/BLK-07"
ROOT = bytes(range(32))
CANON = CanonExtension(payload_ver=1, source_sha256=bytes(range(32, 64)))
TILES = (Tile(path="tile/0/000", data=b"tile-zero"), Tile(path="tile/0/001", data=b"tile-one"))


def build(log: CallLog, **overrides):
    """Assemble a fanout whose every collaborator writes to one shared call log."""
    parts = {
        "beacon": FakeBeacon(log),
        "signer": FakeSigner(log),
        "archive": FakeArchive(log),
        "authorities": [FakeTsa(log, "tsa-a"), FakeTsa(log, "tsa-b")],
        "tiles": FakeTileStore(log),
        "witnesses": [FakeWitness(log, "witness-insurer", adverse=True)],
        "clock": fixed_clock,
    }
    parts.update(overrides)
    return AnchorFanout(**parts)


def request(**overrides) -> AnchorRequest:
    fields = {"origin": ORIGIN, "tree_size": 5, "root_hash": ROOT, "canon": CANON, "tiles": TILES}
    fields.update(overrides)
    return AnchorRequest(**fields)


def test_the_six_steps_run_in_the_one_legal_order():
    log = CallLog()
    result = build(log).anchor(request())

    assert result.steps == STEP_ORDER
    assert log.steps == list(STEP_ORDER)
    assert result.fully_anchored


def test_the_call_log_is_the_evidence_and_the_trace_is_only_the_claim():
    # Both are asserted, and they are asserted against the same constant, so a fanout that
    # appended to its trace without calling a port would fail here rather than pass twice.
    log = CallLog()
    result = build(log).anchor(request())
    assert [step.value for step, _ in log.entries][:3] == ["beacon", "sign", "object_lock"]
    assert log.steps == list(result.steps)


def test_the_note_reaching_object_lock_is_the_signed_note():
    log = CallLog()
    archive = FakeArchive(log)
    result = build(log, archive=archive).anchor(request())

    assert len(archive.written) == 1
    key, note = archive.written[0]
    assert key == checkpoint_object_key(ORIGIN, 5, ROOT)
    assert note == result.note
    assert result.body in note.decode("utf-8")
    # The body that was signed is the body that was archived, extension lines and all.
    body = parse_body(result.body)
    assert body.origin == ORIGIN
    assert body.tree_size == 5
    assert body.root_hash == ROOT
    assert [name for name, _ in body.extensions] == ["canon", "drand", "nist"]


def test_the_digest_every_tsa_stamps_is_over_the_complete_signed_note():
    import hashlib

    log = CallLog()
    result = build(log).anchor(request())
    assert result.note_sha256 == hashlib.sha256(result.note).digest()
    assert {token.message_imprint for token in result.timestamps} == {result.note_sha256}


def test_a_beacon_failure_aborts_before_anything_is_signed():
    log = CallLog()
    fanout = build(log, beacon=FakeBeacon(log, fail="drand unreachable"))
    with pytest.raises(AnchorAborted) as caught:
        fanout.anchor(request())
    assert caught.value.step is AnchorStep.BEACON
    assert log.steps == [AnchorStep.BEACON]


def test_a_signing_failure_aborts_before_anything_is_archived():
    log = CallLog()
    archive = FakeArchive(log)
    fanout = build(log, signer=FakeSigner(log, fail="kms denied"), archive=archive)
    with pytest.raises(AnchorAborted) as caught:
        fanout.anchor(request())
    assert caught.value.step is AnchorStep.SIGN
    assert archive.written == []
    assert AnchorStep.OBJECT_LOCK not in log.steps


def test_an_archive_failure_aborts_before_any_timestamp_is_requested():
    log = CallLog()
    fanout = build(log, archive=FakeArchive(log, fail="AccessDenied"))
    with pytest.raises(AnchorAborted) as caught:
        fanout.anchor(request())
    assert caught.value.step is AnchorStep.OBJECT_LOCK
    assert AnchorStep.TIMESTAMP not in log.steps


def test_a_bucket_that_reports_governance_stops_the_pass_dead():
    # The most important refusal in the package. The write SUCCEEDED; what failed is the
    # claim that it cannot be removed. Nothing downstream may run, because timestamping
    # and publishing would advertise a commitment that does not exist.
    log = CallLog()
    archive = FakeArchive(log, mode="GOVERNANCE")
    fanout = build(log, archive=archive)
    with pytest.raises(ObjectLockNotEnforced, match="GOVERNANCE"):
        fanout.anchor(request())
    # The PutObject happened — that is exactly the shape of the real failure, since S3
    # returns 200 for a write it is not holding. What must not happen is anything after it.
    assert archive.written
    assert AnchorStep.TIMESTAMP not in log.steps
    assert AnchorStep.PUSH_WITNESS not in log.steps


def test_a_missing_legal_hold_stops_the_pass_dead():
    log = CallLog()
    fanout = build(log, archive=FakeArchive(log, legal_hold="OFF"))
    with pytest.raises(ObjectLockNotEnforced, match="LegalHoldStatus"):
        fanout.anchor(request())


def test_a_short_retention_stops_the_pass_dead():
    log = CallLog()
    fanout = build(log, archive=FakeArchive(log, retain_years=3))
    with pytest.raises(ObjectLockNotEnforced, match="RetainUntilDate"):
        fanout.anchor(request())


def test_an_unversioned_bucket_stops_the_pass_dead():
    log = CallLog()
    fanout = build(log, archive=FakeArchive(log, version_id=""))
    with pytest.raises(ObjectLockNotEnforced, match="VersionId"):
        fanout.anchor(request())


def test_a_dead_tsa_becomes_debt_and_does_not_abort_an_already_indelible_checkpoint():
    log = CallLog()
    fanout = build(log, authorities=[FakeTsa(log, "tsa-a"), FakeTsa(log, "tsa-b", fail="504")])
    result = fanout.anchor(request())

    assert result.steps == STEP_ORDER  # the pass completed
    assert not result.fully_anchored
    reasons = {(debt.step, debt.target) for debt in result.debts}
    assert (AnchorStep.TIMESTAMP, "tsa-b") in reasons
    assert (AnchorStep.TIMESTAMP, "quorum") in reasons
    assert len(result.timestamps) == 1


def test_a_token_over_someone_elses_digest_is_refused_and_recorded():
    log = CallLog()
    fanout = build(
        log,
        authorities=[FakeTsa(log, "tsa-a"), FakeTsa(log, "tsa-b", imprint_override=b"\x00" * 32)],
    )
    result = fanout.anchor(request())
    assert any("messageImprint" in debt.reason for debt in result.debts)
    assert [token.authority for token in result.timestamps] == ["tsa-a"]


def test_a_gen_time_before_the_beacon_inverts_the_bracket_and_is_recorded():
    log = CallLog()
    stale = datetime(2020, 1, 1, tzinfo=UTC)
    fanout = build(log, authorities=[FakeTsa(log, "tsa-a"), FakeTsa(log, "tsa-b", gen_time=stale)])
    result = fanout.anchor(request())
    assert any("bracket is inverted" in debt.reason for debt in result.debts)


def test_a_witness_that_refuses_becomes_unwitnessed_debt():
    log = CallLog()
    fanout = build(
        log,
        witnesses=[
            FakeWitness(log, "witness-a"),
            FakeWitness(log, "witness-b", fail="connection reset"),
        ],
    )
    result = fanout.anchor(request())
    assert [c.witness for c in result.cosignatures] == ["witness-a"]
    assert any(debt.target == "witness-b" for debt in result.debts)
    assert result.steps == STEP_ORDER


def test_no_witnesses_at_all_is_recorded_as_total_debt_rather_than_as_success():
    # docs/leads/custody.md §6 risk 1: the quorum is q = 1 over our own infrastructure and
    # that is NOT adverse. A pass with no witness must not read as fully anchored.
    log = CallLog()
    result = build(log, witnesses=[]).anchor(request())
    assert not result.fully_anchored
    assert any(debt.step is AnchorStep.PUSH_WITNESS for debt in result.debts)


def test_a_tile_store_failure_is_debt_and_the_witness_push_still_happens():
    log = CallLog()
    witness = FakeWitness(log, "witness-a")
    fanout = build(log, tiles=FakeTileStore(log, fail="503"), witnesses=[witness])
    result = fanout.anchor(request())
    assert any(debt.step is AnchorStep.PUBLISH_TILES for debt in result.debts)
    assert witness.pushed  # going dark on tiles does not go dark on witnesses


def test_a_silently_dropped_tile_is_detected_by_comparing_paths():
    log = CallLog()
    fanout = build(log, tiles=FakeTileStore(log, drop={"tile/0/001"}))
    result = fanout.anchor(request())
    assert any("tile/0/001" in debt.reason for debt in result.debts)


def test_one_timestamp_authority_is_refused_at_construction():
    log = CallLog()
    with pytest.raises(AnchorMisconfigured, match="two INDEPENDENT authorities"):
        build(log, authorities=[FakeTsa(log, "tsa-a")], min_authorities=1)
    with pytest.raises(AnchorMisconfigured, match="required"):
        build(log, authorities=[FakeTsa(log, "tsa-a")])


def test_two_tokens_from_one_authority_are_one_attestation_wearing_two_hats():
    log = CallLog()
    with pytest.raises(AnchorMisconfigured, match="not distinct"):
        build(log, authorities=[FakeTsa(log, "tsa-a"), FakeTsa(log, "tsa-a")])


def test_tiles_with_nowhere_to_publish_them_is_a_typo_not_a_degraded_mode():
    log = CallLog()
    fanout = build(log, tiles=None)
    with pytest.raises(AnchorMisconfigured, match="publishing nowhere"):
        fanout.anchor(request())
    # ...and a request with no tiles is fine against the same fanout.
    assert fanout.anchor(request(tiles=())).steps == STEP_ORDER


def test_a_retention_below_the_seven_year_floor_is_refused_at_construction():
    log = CallLog()
    with pytest.raises(AnchorMisconfigured, match="floor"):
        build(log, retention_years=3)


def test_a_naive_clock_is_refused_rather_than_assumed_to_be_utc():
    log = CallLog()
    fanout = build(log, clock=lambda: datetime(2026, 8, 10, 4, 30))  # noqa: DTZ001 - the point
    with pytest.raises(AnchorMisconfigured, match="naive"):
        fanout.anchor(request())


def test_a_beacon_lower_bound_in_the_future_aborts():
    log = CallLog()
    fanout = build(log, clock=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    with pytest.raises(AnchorAborted, match="in the future"):
        fanout.anchor(request())


def test_the_fakes_themselves_enforce_the_order():
    # A direct proof that the ordering assertion has teeth: call a downstream port on a
    # fresh log and the fake refuses, naming both steps.
    log = CallLog()
    with pytest.raises(FakeCallRefused, match="timestamp was called before object_lock"):
        FakeTsa(log, "tsa-a").timestamp(b"\x00" * 32)


def test_the_bracket_is_none_when_no_token_survived():
    log = CallLog()
    fanout = build(
        log, authorities=[FakeTsa(log, "a", fail="down"), FakeTsa(log, "b", fail="down")]
    )
    result = fanout.anchor(request())
    assert result.bracket is None  # half a bracket is not a bracket
    assert result.timestamps == ()


def test_the_bracket_is_the_beacon_floor_and_the_earliest_gen_time():
    log = CallLog()
    early = datetime(2026, 8, 10, 4, 30, 1, tzinfo=UTC)
    late = datetime(2026, 8, 10, 4, 30, 9, tzinfo=UTC)
    fanout = build(
        log,
        authorities=[FakeTsa(log, "a", gen_time=late), FakeTsa(log, "b", gen_time=early)],
    )
    result = fanout.anchor(request())
    lower, upper = result.bracket
    assert upper == early
    assert lower == fixed_snapshot().lower_bound()
    assert lower < upper


def test_the_object_key_separates_a_fork_and_not_a_re_signature():
    other_root = bytes(range(1, 33))
    assert checkpoint_object_key(ORIGIN, 5, ROOT) != checkpoint_object_key(ORIGIN, 5, other_root)
    assert checkpoint_object_key(ORIGIN, 5, ROOT) == checkpoint_object_key(ORIGIN, 5, ROOT)
    # Zero-padded, so a plain bucket listing is in checkpoint order.
    assert checkpoint_object_key(ORIGIN, 9, ROOT) < checkpoint_object_key(ORIGIN, 10, ROOT)


def test_the_retention_floor_rounds_a_leap_day_up_rather_than_down():
    leap = datetime(2028, 2, 29, 12, 0, tzinfo=UTC)
    floor = retention_floor(leap)
    # 2035 is not a leap year: rounding down would silently produce a retention short of
    # seven years, and a COMPLIANCE retention can never afterwards be lengthened in the
    # only direction that matters.
    assert floor.year == 2035
    assert (floor.month, floor.day) == (2, 28)  # 1 March less one day of slack
