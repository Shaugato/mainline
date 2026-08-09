# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A recall that arrives after the merge. It must be refused, and loudly.

The anomaly, stated precisely: ``SERIALIZABLE`` orders writes, it does not prevent late
arrival. A precursor inserted at ``T+ε`` after a merge at ``T`` is a **perfectly serializable
history** — there is no isolation level that makes it go away, so the answer has to be
structural. It is the epoch pin: ``merge_record`` takes a composite foreign key onto
``(subject_id, gate_epoch)`` with ``ON UPDATE RESTRICT``, and every new obligation bumps the
epoch. Once a merge exists, the database refuses any ``UPDATE`` that moves that epoch, which
makes attaching a new precursor to an issued permit *physically impossible* rather than
merely forbidden.

Two lanes, and the split is deliberate.

**Database lane** (needs a cluster; skips with a reason otherwise). The refusal itself:
``P0001`` from the deterministic ``RAISE``, and — with that ``RAISE`` unwelded — ``23503`` or
``23514`` from the structure underneath it. ARCHITECTURE 5.11 claims refusal depth ≥ 2 here,
and a claim of structural redundancy that has never been executed is a sentence, not a
property.

**Agent lane** (always runs). The client contract on top of that refusal: the recall agent
must convert it into a *stopped run* with nothing committed and nothing POSTed, must never
retry it, and must never let a late recall look like a run that simply found nothing. The
distinction matters because those two states are indistinguishable from the outside — a
permit with no new obligations — and only one of them is a system working correctly.

**The one thing neither lane may permit is a silent no-op.** A late recall that quietly did
nothing is the exact anomaly the pin exists to make impossible, and it is also the shape a
plaintiff would find first: the system knew, after the fact, and no row anywhere says so.
"""

from __future__ import annotations

import uuid

import pytest
from _late_recall_ddl import REWELD_RESTORE_RAISE, UNWELD_REMOVE_RAISE
from _late_recall_support import (
    FakeSqlError,
    RecordingWriter,
    RefusingSession,
    minimal_candidate_set,
    minimal_record,
)
from mainline_recall_agent.run.errors import (
    GATE_REFUSAL_SQLSTATES,
    RETRYABLE_SQLSTATES,
    KernelRefused,
    LateRecall,
    RunRefused,
    UnmodelledSqlstate,
)
from mainline_recall_agent.run.kernel import MaterialiseClient
from mainline_recall_agent.run.orchestrator import MAX_WRITE_ATTEMPTS, RecallOrchestrator
from mainline_recall_agent.run.session import classify_sqlstate

psycopg = pytest.importorskip("psycopg")

#: The two SQLSTATEs a late recall is permitted to fail with. Anything else — including
#: success — is a defect.
LATE_RECALL_SQLSTATES = frozenset({"P0001", "23503", "23514"})


# ────────────────────────────────────────────────────────────────────────────────────────
# Database lane
# ────────────────────────────────────────────────────────────────────────────────────────


def _merged_permit(conn) -> uuid.UUID:
    """A permit that has been through the gate: one obligation, dispositioned, merged, pinned."""
    permit_id = uuid.uuid4()
    site_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, external_ref) VALUES (%s, %s, %s)",
        (permit_id, site_id, f"WO-{permit_id.hex[:6]}"),
    )
    conn.execute(
        "INSERT INTO mainline.blocking_check "
        "(check_id, permit_id, site_id, severity, origin, evidence_summary) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (uuid.uuid4(), permit_id, site_id, 5, "blame_ancestry", "a fatality wrote this control"),
    )
    # The disposition path, reduced: the obligation is cleared and the gate closes.
    conn.execute(
        "UPDATE mainline.permit SET open_blocking = 0, state = 'dispositioned' "
        "WHERE permit_id = %s",
        (permit_id,),
    )
    conn.execute(
        "UPDATE mainline.permit SET state = 'merged', merged_commit = %s WHERE permit_id = %s",
        (b"\x01" * 32, permit_id),
    )
    epoch = conn.execute(
        "SELECT gate_epoch FROM mainline.permit WHERE permit_id = %s", (permit_id,)
    ).fetchone()[0]
    assert epoch == 1, "materialising one obligation must have bumped the gate epoch"
    conn.execute(
        "INSERT INTO mainline.merge_record (subject_kind, subject_id, gate_epoch, merged_by) "
        "VALUES ('permit', %s, %s, 'gate-fixture')",
        (permit_id, epoch),
    )
    return permit_id


@pytest.mark.requires_cluster
def test_a_late_precursor_is_refused_with_p0001(conn) -> None:
    """The deterministic refusal, which is also the one that reads to a jury."""
    permit_id = _merged_permit(conn)
    before = conn.execute(
        "SELECT count(*) FROM mainline.blocking_check WHERE permit_id = %s", (permit_id,)
    ).fetchone()[0]

    with pytest.raises(psycopg.Error) as raised:
        conn.execute(
            "INSERT INTO mainline.blocking_check "
            "(check_id, permit_id, site_id, severity, origin, evidence_summary) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                uuid.uuid4(),
                permit_id,
                uuid.uuid4(),
                5,
                "recall_probabilistic",
                "a precursor that arrived after the merge",
            ),
        )
    assert raised.value.sqlstate == "P0001", raised.value
    assert "after issue" in str(raised.value)

    after = conn.execute(
        "SELECT count(*) FROM mainline.blocking_check WHERE permit_id = %s", (permit_id,)
    ).fetchone()[0]
    assert after == before, "the refusal must not be a partial write"


@pytest.mark.requires_cluster
def test_the_refusal_is_never_a_silent_no_op(conn) -> None:
    """The failure mode that would be worst: nothing raised, and nothing recorded."""
    permit_id = _merged_permit(conn)
    state_before = conn.execute(
        "SELECT state, gate_epoch, open_blocking FROM mainline.permit WHERE permit_id = %s",
        (permit_id,),
    ).fetchone()

    with pytest.raises(psycopg.Error) as raised:
        conn.execute(
            "INSERT INTO mainline.blocking_check "
            "(check_id, permit_id, site_id, severity, origin, evidence_summary) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (uuid.uuid4(), permit_id, uuid.uuid4(), 4, "blame_ancestry", "late arrival"),
        )
    assert raised.value.sqlstate in LATE_RECALL_SQLSTATES

    state_after = conn.execute(
        "SELECT state, gate_epoch, open_blocking FROM mainline.permit WHERE permit_id = %s",
        (permit_id,),
    ).fetchone()
    assert state_after == state_before, (
        "a late recall that quietly changed nothing and raised nothing is exactly the anomaly "
        "the epoch pin exists to make impossible"
    )


@pytest.mark.requires_cluster
def test_the_epoch_of_a_merged_permit_cannot_be_moved(conn) -> None:
    """``ON UPDATE RESTRICT`` directly: the pinned epoch is not editable, by anyone."""
    permit_id = _merged_permit(conn)
    with pytest.raises(psycopg.Error) as raised:
        conn.execute(
            "UPDATE mainline.permit SET gate_epoch = gate_epoch + 1 WHERE permit_id = %s",
            (permit_id,),
        )
    assert raised.value.sqlstate == "23503", raised.value
    assert (
        conn.execute(
            "SELECT gate_epoch FROM mainline.permit WHERE permit_id = %s", (permit_id,)
        ).fetchone()[0]
        == 1
    )


@pytest.mark.requires_cluster
def test_the_merge_record_cannot_be_deleted_to_free_the_epoch(conn) -> None:
    """``ON DELETE RESTRICT``. A cascade here would let a writer rewrite history."""
    permit_id = _merged_permit(conn)
    conn.execute(
        "DELETE FROM mainline.merge_record WHERE subject_kind = 'permit' AND subject_id = %s",
        (permit_id,),
    )
    # Deleting the merge_record is legal (it is the referencing side); what must not be legal
    # is deleting the PERMIT out from under a live merge record.
    conn.execute(
        "INSERT INTO mainline.merge_record (subject_kind, subject_id, gate_epoch, merged_by) "
        "VALUES ('permit', %s, 1, 'gate-fixture')",
        (permit_id,),
    )
    with pytest.raises(psycopg.Error) as raised:
        conn.execute("DELETE FROM mainline.permit WHERE permit_id = %s", (permit_id,))
    assert raised.value.sqlstate == "23503", raised.value


@pytest.mark.requires_cluster
def test_refusal_depth_is_at_least_two(conn) -> None:
    """Unweld the deterministic ``RAISE``; the structure underneath must still refuse.

    ARCHITECTURE 5.11 (finding S4): with the ``RAISE`` deleted the write still fails twice
    over — the ``UPDATE`` drives ``open_blocking > 0`` on a merged row (``23514``) *and*
    mutates a pinned ``gate_epoch`` (``23503``). Which of the two is observed is a race
    between ``CHECK`` and FK evaluation, which is exactly why the ``RAISE`` is kept first at
    runtime and why this assertion accepts either.
    """
    permit_id = _merged_permit(conn)
    conn.execute(UNWELD_REMOVE_RAISE)
    try:
        with pytest.raises(psycopg.Error) as raised:
            conn.execute(
                "INSERT INTO mainline.blocking_check "
                "(check_id, permit_id, site_id, severity, origin, evidence_summary) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (uuid.uuid4(), permit_id, uuid.uuid4(), 5, "blame_ancestry", "unwelded"),
            )
        assert raised.value.sqlstate in {"23503", "23514"}, (
            "with the RAISE removed the write must still be refused by the epoch pin or by "
            f"gate_closed_when_issued; got {raised.value.sqlstate}"
        )
    finally:
        conn.execute(REWELD_RESTORE_RAISE)


@pytest.mark.requires_cluster
def test_an_unmerged_permit_still_accepts_precursors(conn) -> None:
    """The green half. Without it, the refusals above could be a table that rejects everything."""
    permit_id = uuid.uuid4()
    site_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, external_ref) VALUES (%s, %s, %s)",
        (permit_id, site_id, f"WO-{permit_id.hex[:6]}"),
    )
    for index in range(3):
        conn.execute(
            "INSERT INTO mainline.blocking_check "
            "(check_id, permit_id, site_id, severity, origin, evidence_summary) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (uuid.uuid4(), permit_id, site_id, 3, "recall_probabilistic", f"precursor {index}"),
        )
    epoch, open_blocking = conn.execute(
        "SELECT gate_epoch, open_blocking FROM mainline.permit WHERE permit_id = %s",
        (permit_id,),
    ).fetchone()
    assert epoch == 3, "every new obligation bumps the epoch"
    assert open_blocking == 3


def _dispositioned_permit(conn) -> uuid.UUID:
    """A permit whose one obligation has been cleared: gate closed, epoch already at 1."""
    permit_id = uuid.uuid4()
    site_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, external_ref) VALUES (%s, %s, %s)",
        (permit_id, site_id, f"WO-{permit_id.hex[:6]}"),
    )
    conn.execute(
        "INSERT INTO mainline.blocking_check "
        "(check_id, permit_id, site_id, severity, origin, evidence_summary) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (uuid.uuid4(), permit_id, site_id, 4, "blame_ancestry", "cleared before the race"),
    )
    conn.execute(
        "UPDATE mainline.permit SET open_blocking = 0, state = 'dispositioned' "
        "WHERE permit_id = %s",
        (permit_id,),
    )
    return permit_id


@pytest.mark.requires_cluster
def test_no_interleaving_leaves_a_merged_permit_with_an_open_obligation(epoch_pin) -> None:
    """The race itself: a recall landing while the merge is in flight.

    ``SERIALIZABLE`` orders these two writers because they contend for one ``permit`` row, so
    one of them must lose — with ``40001`` if the conflict is detected as contention, with
    ``23514`` if the merge is retried after the obligation lands, or with ``57014`` if the
    contending statement was still waiting when its timeout expired. Which one is a property
    of the cluster's contention handling and is not asserted.

    What **is** asserted is the invariant underneath all three: there is no interleaving that
    ends with a merged permit carrying an open obligation. That is L1 — the gate conservation
    law — under concurrency, and it is the state a plaintiff would look for first.
    """
    with epoch_pin.connect() as setup:
        permit_id = _dispositioned_permit(setup)

    late = epoch_pin.connect(autocommit=False)
    merge = epoch_pin.connect(autocommit=False)
    refused: list[str] = []
    try:
        # The recall arrives first and is still uncommitted: the trigger has already bumped
        # the epoch and raised open_blocking inside this transaction.
        late.execute(
            "INSERT INTO mainline.blocking_check "
            "(check_id, permit_id, site_id, severity, origin, evidence_summary) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (uuid.uuid4(), permit_id, uuid.uuid4(), 5, "blame_ancestry", "arrived mid-merge"),
        )
        try:
            merge.execute(
                "UPDATE mainline.permit SET state = 'merged', merged_commit = %s "
                "WHERE permit_id = %s",
                (b"\x02" * 32, permit_id),
            )
            merge.commit()
        except psycopg.Error as exc:
            refused.append(exc.sqlstate or "unknown")
            merge.rollback()

        try:
            late.commit()
        except psycopg.Error as exc:
            refused.append(exc.sqlstate or "unknown")
            late.rollback()
    finally:
        late.close()
        merge.close()

    assert refused, "both transactions committed; one of them had to lose"

    with epoch_pin.connect() as check:
        state, gate_epoch, open_blocking = check.execute(
            "SELECT state, gate_epoch, open_blocking FROM mainline.permit WHERE permit_id = %s",
            (permit_id,),
        ).fetchone()
    assert not (state == "merged" and open_blocking > 0), (
        f"L1 violated: permit {permit_id} is {state} with open_blocking={open_blocking} at "
        f"gate_epoch={gate_epoch}. A merged subject with an open obligation is the state the "
        "whole gate exists to make unreachable."
    )


# ────────────────────────────────────────────────────────────────────────────────────────
# Agent lane — no cluster required
# ────────────────────────────────────────────────────────────────────────────────────────


class _StatusTransport:
    def __init__(self, status: int, body: bytes = b"{}") -> None:
        self.status = status
        self.body = body
        self.posts: list[str] = []

    def post(self, url, body, headers, timeout):  # noqa: ARG002 - KernelTransport shape
        self.posts.append(url)
        return self.status, self.body


def _writer(**kwargs) -> RecordingWriter:
    return RecordingWriter(**kwargs)


def _orchestrator(writer: RecordingWriter) -> RecallOrchestrator:
    """An orchestrator wired for the write path alone; any read is an assertion failure."""
    return RecallOrchestrator(session=RefusingSession(), writer=writer)


@pytest.mark.parametrize("status", [409, 412])
def test_the_kernel_late_recall_answer_becomes_a_stopped_run(status) -> None:
    """``409``/``412`` is the kernel saying the subject's epoch is pinned. Never a retry."""
    transport = _StatusTransport(status, b'{"error": "gate epoch is pinned by merge_record"}')
    client = MaterialiseClient(base_url="https://kernel.invalid", transport=transport)

    with pytest.raises(LateRecall) as raised:
        client.materialise(minimal_candidate_set())
    assert "MI07" in str(raised.value)
    assert "do not retry" in str(raised.value)
    assert "suspend" in str(raised.value).lower(), (
        "the refusal must name the declared path — suspend the issued permit and fork a child "
        "whose gate is cleared afresh — or the operator is told only that it failed"
    )
    assert len(transport.posts) == 1, "a late recall is attempted exactly once, ever"


def test_any_other_refusal_is_distinguished_from_a_late_recall() -> None:
    """A ``422`` is a malformed set, not a pinned epoch. Conflating them hides both."""
    transport = _StatusTransport(422, b'{"error": "candidate set failed validation"}')
    client = MaterialiseClient(base_url="https://kernel.invalid", transport=transport)
    with pytest.raises(KernelRefused) as raised:
        client.materialise(minimal_candidate_set())
    assert not isinstance(raised.value, LateRecall)


def test_a_successful_materialise_is_not_confused_with_a_refusal() -> None:
    """Green half: a 2xx returns a result, so the refusals above are about the status."""
    transport = _StatusTransport(200, b'{"receipt_id": "r-1", "open_blocking": 1}')
    client = MaterialiseClient(base_url="https://kernel.invalid", transport=transport)
    result = client.materialise(minimal_candidate_set())
    assert result.status == 200
    assert result.open_blocking == 1


def test_the_epoch_pin_sqlstates_are_classified_as_refusals() -> None:
    """``40001`` is the only retryable code. A pin refusal is attempted exactly once."""
    for sqlstate in ("P0001", "23503", "23514", "23505"):
        assert classify_sqlstate(sqlstate) == "refusal"
        assert sqlstate in GATE_REFUSAL_SQLSTATES
    assert classify_sqlstate("40001") == "retryable"
    assert frozenset({"40001"}) == RETRYABLE_SQLSTATES
    # An unknown code is deliberately NOT retryable: retrying a refusal nobody modelled is how
    # a gate quietly stops being a gate.
    assert classify_sqlstate("XX000") == "unmodelled"
    assert classify_sqlstate(None) == "unmodelled"


def test_a_clean_write_commits_once() -> None:
    """Green half of the write-path pair: one transaction, no rollback, no retry."""
    writer = _writer()
    _orchestrator(writer)._write(minimal_record())
    assert len(writer.committed) == 1
    assert writer.rolled_back == []


@pytest.mark.parametrize("sqlstate", ["23503", "P0001", "23514", "23505"])
def test_a_gate_refusal_is_attempted_once_and_never_retried(sqlstate) -> None:
    """The write path must not launder a pin refusal into an apparent success by retrying."""
    writer = _writer(failure=FakeSqlError(sqlstate, "epoch_pin_permit"), fail_first_n=10_000)

    with pytest.raises(FakeSqlError) as raised:
        _orchestrator(writer)._write(minimal_record())
    assert raised.value.sqlstate == sqlstate
    assert writer.attempts == 1, (
        "a gate refusal is attempted exactly once; a retry loop that could absorb a 23503 "
        "would launder a refusal into an apparent success"
    )
    assert writer.committed == []


def test_a_serialization_failure_is_retried_and_the_write_survives() -> None:
    """The other half of the same rule: ``40001`` is retryable, boundedly, and only it."""
    writer = _writer(failure=FakeSqlError("40001", "restart transaction"), fail_first_n=1)
    _orchestrator(writer)._write(minimal_record())

    assert len(writer.committed) == 1, "the retry rebuilt the transaction and committed"
    assert len(writer.rolled_back) == 1, "the first attempt rolled back, not partially kept"


def test_an_unmodelled_sqlstate_is_fatal_rather_than_retried() -> None:
    """A code outside the two sets means the schema moved or an assumption is wrong."""
    writer = _writer(failure=FakeSqlError("42P01", "relation does not exist"))
    with pytest.raises(UnmodelledSqlstate, match="42P01"):
        _orchestrator(writer)._write(minimal_record())
    assert writer.committed == []


def test_the_retry_allowance_is_bounded() -> None:
    """A bounded allowance, scoped to one SQLSTATE. There is no blanket-retry helper."""
    assert MAX_WRITE_ATTEMPTS == 3
    writer = _writer(failure=FakeSqlError("40001", "restart transaction"), fail_first_n=10_000)
    with pytest.raises(RunRefused, match="40001"):
        _orchestrator(writer)._write(minimal_record())
    assert len(writer.rolled_back) == MAX_WRITE_ATTEMPTS
    assert writer.committed == []
