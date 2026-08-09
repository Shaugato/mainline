# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``40001`` is retried with capped backoff. The four refusal codes are attempted once, ever.

``spec/errors.md`` §4 states the property; ``trappoint_core.retry`` implements it; this
file **watches it happen** and asserts the observation rather than the implementation.
The distinction matters. A test that read the source and agreed with it would pass against
a loop that had been rewritten to catch ``Exception``; a spy that counts attempts cannot.

The reason the property exists is evidentiary, not performance-related. The refusal ledger
records *decisions the gate made*. A client that retries a ``23514`` writes five identical
refusals for one attempted history, the count of refusals stops being a count of anything,
and an opposing expert reads a system that repeatedly attempted a write the database had
already refused.

Two halves, and the second is what makes this a concurrency test rather than a unit test:

1. **The taxonomy half** drives ``trappoint_core.retry.run_gate`` with an injected
   operation for each of the five modelled codes and asserts the spy's tally. No cluster
   needed; it always runs.
2. **The live half** drives the REAL gate through the REAL retry loop against a cluster,
   with a refusal the database actually produces, and asserts the loop attempted it once.
   A refusal manufactured in Python proves the loop's branches; a refusal produced by a
   CHECK proves the loop is wired to the thing that refuses.

``trappoint-core`` is imported HERE and not in ``trappoint-model``. The model must stay
independent of the client it judges; this file is not the model — it is the client's own
conformance, and importing the client is the point.
"""

from __future__ import annotations

import random
import uuid
from typing import Any

import psycopg
import pytest

# See the note in `test_single_merge.py`: a conftest-level skip would take the custody
# and recall lanes with it, so both optional imports are gated here.
pytest.importorskip(
    "trappoint_model",
    reason="`uv sync --package trappoint-model` installs it. A SKIP IS NOT EVIDENCE.",
)
pytest.importorskip(
    "trappoint_core",
    reason=(
        "the spy watches the REAL client's retry loop; `uv sync --package "
        "trappoint-core` installs it. A SKIP IS NOT EVIDENCE."
    ),
)

from trappoint_model.adapter import Adapter
from trappoint_model.model import Accept
from trappoint_model.programs import merge_program
from trappoint_model.refschema import SCHEMA, Fixture

from trappoint_core.errors import (
    REFUSAL_SQLSTATES,
    RETRYABLE_SQLSTATE,
    GateRefused,
    RetryBudgetExhausted,
)
from trappoint_core.retry import RecordingObserver, RetryPolicy, run_gate

FAST = RetryPolicy(max_attempts=5, base_delay_s=0.0, cap_delay_s=0.0)


class _Refusal(psycopg.Error):
    """A driver-shaped exception carrying a chosen SQLSTATE and the substrate's message form.

    A real ``psycopg.Error`` subclass rather than a duck type, because
    ``trappoint_core.retry`` catches ``psycopg.Error`` and never ``Exception`` — a
    deliberate narrowness that a stand-in with the right attributes would slip past.

    ``_sqlstate`` is assigned BEFORE ``super().__init__``: psycopg's own constructor reads
    ``self.sqlstate`` while it runs, so the property must already have something to
    return.
    """

    def __init__(self, sqlstate: str, constraint: str) -> None:
        """Build a refusal carrying *sqlstate* and the ``refused by`` clause for *constraint*."""
        self._sqlstate = sqlstate
        super().__init__(f"TRAPPOINT_REF: merge refused by {SCHEMA}.{constraint}")

    @property
    def sqlstate(self) -> str:  # type: ignore[override]
        """The code the loop discriminates on."""
        return self._sqlstate


@pytest.mark.parametrize("sqlstate", sorted(REFUSAL_SQLSTATES))
def test_a_refusal_is_attempted_exactly_once_ever(sqlstate: str) -> None:
    """Each of the four refusal codes: one attempt, one refusal, zero retries."""
    spy = RecordingObserver()
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise _Refusal(sqlstate, "fn_permit_merge_gate")

    with pytest.raises(GateRefused) as raised:
        run_gate(operation, policy=FAST, observer=spy, rng=random.Random(0), sleep=lambda _: None)

    assert calls == 1, f"{sqlstate} was attempted {calls} times; the contract is once, ever"
    assert spy.attempts_for(sqlstate) == 1
    assert spy.retries == [], f"{sqlstate} was retried: {spy.retries}"
    assert len(spy.refusals) == 1
    assert raised.value.constraint == f"{SCHEMA}.fn_permit_merge_gate", (
        "the refusal reached the caller without its exhibit"
    )


def test_the_retryable_code_is_retried_with_a_capped_ladder() -> None:
    """``40001`` and only ``40001``, with delays that never exceed the cap."""
    spy = RecordingObserver()
    delays: list[float] = []
    policy = RetryPolicy(max_attempts=5, base_delay_s=0.02, cap_delay_s=0.1)

    def operation() -> None:
        raise _Refusal(RETRYABLE_SQLSTATE, "merge_permit")

    with pytest.raises(RetryBudgetExhausted) as raised:
        run_gate(
            operation,
            policy=policy,
            observer=spy,
            rng=random.Random(7),
            sleep=delays.append,
        )

    assert raised.value.attempts == policy.max_attempts
    assert spy.attempts_for(RETRYABLE_SQLSTATE) == policy.max_attempts
    assert not spy.refusals, (
        "an exhausted budget was recorded as a refusal. The gate never decided; a "
        "transaction that is undecided is not one that was refused (spec/errors.md §5)."
    )
    assert all(0.0 <= d <= policy.cap_delay_s for d in delays), f"a delay escaped the cap: {delays}"
    assert len(delays) == policy.max_attempts - 1, (
        f"{len(delays)} sleeps for {policy.max_attempts} attempts; the loop must not sleep "
        "after the attempt that exhausts the budget"
    )


def test_a_success_after_a_conflict_is_not_recorded_as_a_refusal() -> None:
    """The ordinary happy path under contention: retry, succeed, no refusal recorded."""
    spy = RecordingObserver()
    attempts = 0

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _Refusal(RETRYABLE_SQLSTATE, "merge_permit")
        return "merged"

    assert (
        run_gate(operation, policy=FAST, observer=spy, rng=random.Random(1), sleep=lambda _: None)
        == "merged"
    )
    assert spy.successes == [2]
    assert not spy.refusals
    assert spy.attempts_for(RETRYABLE_SQLSTATE) == 2


@pytest.mark.requires_cluster
@pytest.mark.timeout(300)
def test_a_real_refusal_from_the_real_gate_is_attempted_once(
    kernel_conn: Any, kernel_fixture: Fixture
) -> None:
    """The live half: a refusal a CHECK produced, through the loop the service uses.

    The history is conformance case CF-01 in miniature — an obligation arrives after the
    subject was cleared, so ``open_blocking`` reads one while the subject sits in
    ``dispositioned`` — and the gate refuses with ``23514`` on
    ``gate_closed_when_issued``. The assertion is that the loop attempted it **once**.
    """
    adapter = Adapter(kernel_conn, kernel_fixture)
    sid, cid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert isinstance(adapter.create_subject(sid), Accept)
    assert isinstance(adapter.materialise_check(sid, cid), Accept)
    assert isinstance(adapter.sign_disposition(cid, did), Accept)
    # The obligation that arrives after clearance. The subject stays `dispositioned`, so
    # the projected counter is the only thing between it and a merge.
    assert isinstance(adapter.materialise_check(sid, uuid.uuid4()), Accept)

    statement = merge_program(sid, kernel_fixture)[0]
    spy = RecordingObserver()
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        kernel_conn.execute(statement.sql, statement.params)

    with pytest.raises(GateRefused) as raised:
        run_gate(
            operation,
            subject_kind="permit",
            subject_id=str(sid),
            policy=FAST,
            observer=spy,
            rng=random.Random(0),
            sleep=lambda _: None,
        )

    assert raised.value.sqlstate == "23514"
    assert raised.value.constraint == "gate_closed_when_issued", (
        f"the gate refused with {raised.value.constraint!r}; the exhibit for an open "
        "obligation at a completing transition is gate_closed_when_issued"
    )
    assert calls == 1, f"the real gate's refusal was attempted {calls} times, not once"
    assert spy.retries == [], f"a refusal was retried against a live cluster: {spy.retries}"
