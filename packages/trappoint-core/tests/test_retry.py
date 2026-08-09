# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The once-only property, asserted directly. No database.

``spec/errors.md`` §4: a refusal is attempted exactly once, ever. Every test below is a
statement of that property or of the one exception to it (``40001``).
"""

from __future__ import annotations

import random

import pytest

from trappoint_core.errors import (
    AuthorisationDenied,
    GateRefused,
    RetryBudgetExhausted,
    UnmodelledRefusal,
)
from trappoint_core.retry import (
    RecordingObserver,
    RetryPolicy,
    full_jitter,
    run_gate,
)

SERIALIZATION_FAILURE = "40001"


class Clock:
    """A sleep that records instead of sleeping, and a monotonic clock that advances."""

    def __init__(self) -> None:
        self.slept: list[float] = []
        self.t = 0.0

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds

    def now(self) -> float:
        return self.t


def failing(*errors: BaseException):
    """Return an operation that raises *errors* in order, then returns ``'merged'``."""
    queue = list(errors)

    def operation() -> str:
        if queue:
            raise queue.pop(0)
        return "merged"

    return operation


@pytest.mark.parametrize(
    ("sqlstate", "constraint"),
    [
        ("23514", "gate_closed_when_issued"),
        ("23503", "epoch_pin_permit"),
        ("23505", "merge_record_pkey"),
        ("P0001", "mainline.fn_permit_merge_gate"),
    ],
)
def test_every_refusal_code_is_attempted_exactly_once_ever(sqlstate, constraint, make_error):
    clock = Clock()
    spy = RecordingObserver()
    message = (
        f"MAINLINE: merge refused by {constraint} — refused" if sqlstate == "P0001" else "refused"
    )
    error = make_error(sqlstate, None if sqlstate == "P0001" else constraint, message)

    with pytest.raises(GateRefused) as caught:
        run_gate(
            failing(error, error, error),
            subject_kind="permit",
            subject_id="00000000-0000-0000-0000-00000000000a",
            policy=RetryPolicy(max_attempts=5),
            observer=spy,
            sleep=clock.sleep,
            rng=random.Random(7),
            now=clock.now,
        )

    assert caught.value.sqlstate == sqlstate
    assert caught.value.constraint == constraint
    assert spy.attempts == [0], "a refusal must be attempted once, not once per budget"
    assert spy.retries == []
    assert spy.attempts_for(sqlstate) == 1
    assert clock.slept == [], "no backoff is spent on a decision the gate already made"


def test_40001_is_retried_with_capped_backoff_and_then_succeeds(make_error):
    clock = Clock()
    spy = RecordingObserver()
    transient = make_error(SERIALIZATION_FAILURE, None, "restart transaction: TransactionRetry")

    result = run_gate(
        failing(transient, transient),
        policy=RetryPolicy(max_attempts=5, base_delay_s=0.02, cap_delay_s=0.5),
        observer=spy,
        sleep=clock.sleep,
        rng=random.Random(11),
        now=clock.now,
    )

    assert result == "merged"
    assert spy.attempts == [0, 1, 2]
    assert [state for _, state, _ in spy.retries] == [SERIALIZATION_FAILURE] * 2
    assert spy.refusals == []
    assert spy.successes == [2]
    assert len(clock.slept) == 2
    assert all(0.0 <= delay <= 0.5 for delay in clock.slept)


def test_the_budget_is_bounded_and_exhaustion_is_not_a_refusal(make_error):
    clock = Clock()
    spy = RecordingObserver()
    transient = make_error(SERIALIZATION_FAILURE, None, "restart transaction")

    with pytest.raises(RetryBudgetExhausted) as caught:
        run_gate(
            failing(*[transient] * 20),
            policy=RetryPolicy(max_attempts=4),
            observer=spy,
            sleep=clock.sleep,
            rng=random.Random(3),
            now=clock.now,
        )

    # NOT a GateRefused, and that distinction is the product: the gate never decided.
    assert not isinstance(caught.value, GateRefused)
    assert caught.value.attempts == 4
    assert spy.attempts == [0, 1, 2, 3]
    # Three sleeps for four attempts: nothing is slept after the last one, because there
    # is nothing left to wait for.
    assert len(clock.slept) == 3


def test_42501_never_reaches_the_gate_and_is_never_retried(make_error):
    clock = Clock()
    spy = RecordingObserver()
    with pytest.raises(AuthorisationDenied):
        run_gate(
            failing(make_error("42501", None, "user agent_gate does not have INSERT privilege")),
            observer=spy,
            sleep=clock.sleep,
            rng=random.Random(1),
            now=clock.now,
        )
    assert spy.attempts == [0]
    assert spy.refusals == [], "a denial is a fact about the writer, not a gate refusal"
    assert clock.slept == []


def test_an_unmodelled_sqlstate_is_raised_as_unmodelled_and_not_retried(make_error):
    clock = Clock()
    with pytest.raises(UnmodelledRefusal) as caught:
        run_gate(
            failing(make_error("23502", None, "null value in column violates not-null")),
            sleep=clock.sleep,
            rng=random.Random(1),
            now=clock.now,
        )
    assert caught.value.sqlstate == "23502"
    assert clock.slept == []


def test_a_bug_in_the_operation_is_not_classified_as_a_database_verdict():
    # `except psycopg.Error`, never `except Exception`. A KeyError in the caller's
    # payload builder must surface as a KeyError.
    def broken() -> str:
        raise KeyError("payload")

    with pytest.raises(KeyError):
        run_gate(broken, sleep=lambda _: None, rng=random.Random(1))


def test_full_jitter_is_bounded_by_the_cap_and_reaches_toward_zero():
    policy = RetryPolicy(max_attempts=8, base_delay_s=0.02, cap_delay_s=0.5)
    rng = random.Random(2026)
    draws = [full_jitter(attempt, policy, rng) for attempt in range(8) for _ in range(64)]
    assert min(draws) < 0.01, "full jitter must be able to retry almost immediately"
    assert max(draws) <= policy.cap_delay_s
    # The ceiling doubles until it caps, so attempt 0 can never draw the cap.
    assert max(full_jitter(0, policy, rng) for _ in range(256)) <= policy.base_delay_s


def test_a_policy_that_could_not_hold_the_property_is_refused():
    with pytest.raises(ValueError, match="at least 1"):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="base_delay_s <= cap_delay_s"):
        RetryPolicy(base_delay_s=1.0, cap_delay_s=0.1)


def test_no_blanket_retry_helper_is_importable_from_this_package():
    # The import-linter contract is the enforcement; this is the local statement of it,
    # so a developer who adds `import tenacity` to this package learns it here rather
    # than in CI twenty minutes later.
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "trappoint_core"
    banned = ("tenacity", "backoff", "retrying", "stamina", "aiohttp_retry")
    for module in sorted(root.glob("*.py")):
        text = module.read_text(encoding="utf-8")
        for name in banned:
            assert f"import {name}" not in text, f"{module.name} imports {name}"
