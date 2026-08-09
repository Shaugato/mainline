# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The differential at SERIALIZABLE. Every generated operation, twice, compared exactly.

This is the test the whole package exists for. It is one line long because everything
that makes it work is in :mod:`~trappoint_model.machine`, and that is the right shape: a
reviewer reads the machine, not the test.

**Budget.** ``ci`` runs 50 examples x 25 steps, about 1,250 generated operations per class,
each of which is one round trip to a real cluster. ``nightly`` runs 2,000 x 120, about 240,000
per class, and the ≥ 10⁶ figure in the exit criteria is reached across the nightly matrix
(both isolation levels, both machine classes, repeated runs), not by one invocation —
stating which is the difference between a budget and a boast.
"""

from __future__ import annotations

import pytest
from hypothesis import settings
from hypothesis.stateful import run_state_machine_as_test
from trappoint_model.machine import make_machine
from trappoint_model.refschema import Fixture

pytestmark = [pytest.mark.requires_cluster, pytest.mark.slow]


@pytest.mark.timeout(1800)
def test_gate_agrees_with_the_oracle_at_serializable(conn: object, fixture: Fixture) -> None:
    """Model and cluster agree on outcome AND SQLSTATE class, step for step.

    A failure here is a FINDING, not a flake. Record the counterexample Hypothesis prints
    — it is already in ``.hypothesis-corpus/`` by the time you read it — and establish
    which side is wrong before editing either. Editing the model to match the cluster is
    how a differential stops being one.
    """
    run_state_machine_as_test(
        make_machine(conn, fixture),  # type: ignore[arg-type]
        settings=settings(settings.default, print_blob=True),
    )
