# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Attacks on the commitments themselves — A7, A8, A9, A15.

This is where the design stops relying on the database. A T4 adversary — the cloud-org
admin colluding with the signer — can mint a valid signature over anything they like. What
they cannot do is mint an RFC 3161 token dated in the past, make a witness un-see a size it
already cosigned, or quote a beacon round that had not been issued yet.

The honest limit is stated in ``spec/wire/checkpoint.md`` §4.4 and is repeated here because
it is the kind of sentence that goes missing: extension lines are covered by the ``0x02``
log signature but **not** by ``0x04``/``0x06`` witness cosignatures, so against T4 the
beacon bound is exactly as strong as the log signature and no stronger.
"""

from __future__ import annotations

import os

import attacks
import pytest
from conftest import NemesisContext, OutcomeRecorder

#: Standing up a fresh database, applying the reduced schema and seeding 72 leaves
#: costs a few seconds per attack, and the repository's default 120 s per-test budget
#: is written for unit tests. Raised here rather than globally: a slow lane is a cost,
#: a hanging lane is a test that has stopped asserting.
pytestmark = pytest.mark.timeout(300)


def _record(
    recorder: OutcomeRecorder,
    ctx: NemesisContext | None,
    outcome: attacks.AttackOutcome,
) -> None:
    if ctx is not None:
        recorder.environment.setdefault("cluster", ctx.provenance)
    recorder.record(outcome)


def _assert_detected(outcome: attacks.AttackOutcome) -> None:
    assert outcome.detected_by, (
        f"{outcome.id} ({outcome.name}) ran and was detected by ZERO checks. Verifier: "
        f"{outcome.verifier}. Skipped checks: {outcome.skipped_checks}"
    )


@pytest.mark.slow
def test_a7_checkpoint_swap(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Replace a checkpoint body with a self-consistent one over a different tree.

    The signature is not the obstacle — a T4 adversary holds the key. The obstacle is that
    the timestamp token in hand was computed over ``SHA-256(note text)`` of the note that
    used to be there, and the authority that issued it has no relationship with us.
    """
    outcome = attacks.run_attack(nemesis, "A7", attacks.a7_checkpoint_swap)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome)
    assert 5 in outcome.detected_by or 3 in outcome.detected_by, (
        "A7 must be caught by the RFC 3161 imprint (check 5) or by a consistency proof "
        "against its neighbours (check 3). If neither fires, the checkpoint chain is "
        "trusting a body the operator can rewrite."
    )


@pytest.mark.slow
def test_a8_backdate_forward(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Mint history and claim the authority saw it earlier than it did.

    Detected by exactly one check today, which is why the design calls for at least two
    independent timestamp authorities. The matrix FLAGS that; it does not fail it, because
    a single detector is a single point of failure in the argument rather than in the code.
    """
    outcome = attacks.run_attack(nemesis, "A8", attacks.a8_backdate_forward)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome)
    assert 5 in outcome.detected_by, "A8 must be caught by check 5, the RFC 3161 upper bound"


@pytest.mark.slow
def test_a9_backdate_backward(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Claim a checkpoint existed BEFORE the beacon round it quotes.

    ``round_time = 1692803367 + (round - 1) * 3``. That expression is the whole check, it
    needs no key, no network and no dependency, and it is why the drand line is in the note
    at all.
    """
    outcome = attacks.run_attack(nemesis, "A9", attacks.a9_backdate_backward)
    _record(recorder, nemesis, outcome)
    _assert_detected(outcome)
    assert 6 in outcome.detected_by, (
        "A9 must be caught by check 6. The round→time arithmetic is the lower half of the "
        "two-sided bracket and it is the half a stranger can check with nothing installed."
    )


def test_a15_object_lock_downgrade(recorder: OutcomeRecorder) -> None:
    """``PutObjectRetention`` against a COMPLIANCE-locked checkpoint object.

    **This attack does not run today and says so.** AWS credentials are not valid on the
    build machine, and CU-10 rules that Object Lock semantics are proven by policy-as-code
    over the OpenTofu plan JSON rather than by ``moto``, whose Object Lock enforcement is
    incomplete — a green test against a mock that does not enforce the thing is worse than
    no test.

    The requirement this test exists to meet is that A15 appears in the matrix as
    ``SKIP(no-credentials)`` and is **never silently absent**. An attack quietly missing
    from the matrix is indistinguishable from an attack that was never thought of.
    """
    live = os.environ.get("MAINLINE_AWS_LIVE") == "1"
    reason = "live-run-requested-but-unimplemented" if live else "no-credentials"
    outcome = attacks.skipped_attack(
        "A15",
        reason,
        note=(
            "The static defence is proven instead by policy-as-code over the OpenTofu plan "
            "JSON (`infra/policy/custody/object_lock.rego`, `scripts/custody/"
            "check_evidence_plan.py`): the bucket must declare `object_lock_enabled` AT "
            "CREATION and versioning, and no principal in the write account may hold "
            "`s3:DeleteObject*`, `s3:PutObjectRetention`, `s3:PutObjectLegalHold` or "
            "`s3:BypassGovernanceRetention`. GT-18 is a one-shot: Object Lock cannot be "
            "retrofitted, so it must be right the first time."
        ),
    )
    _record(recorder, None, outcome)
    assert outcome.skipped_reason == reason
    assert not outcome.ran
