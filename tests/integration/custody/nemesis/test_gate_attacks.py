# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Attacks on the mechanisms the gate depends on — A10, A11, A13.

These three are the ones that matter operationally, because none of them touches the ledger
at all. They attack the things the merge gate *reads*: the blame closure under every
ancestry gate (S2), the state-machine chain whose input was trusted (S9), and the trigger
itself.

**A13 is the demo beat, and it is honest in the direction that costs us something.** The
gate refuses. The raw-SQL bypass refuses. ``ALTER TABLE … DISABLE TRIGGER`` **succeeds** —
measured on CockroachDB v26.2.5 — and the merge then lands. Showing the successful bypass
is the point: a product that claims nothing can be disabled is lying, and one that detects
the disabling is telling the truth.

This module is also what makes ``test_k2_exit.py::test_gate_depends_on_ledger`` a real
statement rather than a skip: the merge is refused while an obligation carries no live
disposition, which is a database refusal and nothing in process can stand in for it.
"""

from __future__ import annotations

import attacks
import pytest
from nemesis_harness import NemesisContext, OutcomeRecorder

#: Standing up a fresh database, applying the reduced schema and seeding 72 leaves
#: costs a few seconds per attack, and the repository's default 120 s per-test budget
#: is written for unit tests. Raised here rather than globally: a slow lane is a cost,
#: a hanging lane is a test that has stopped asserting.
pytestmark = pytest.mark.timeout(300)


def _record(recorder: OutcomeRecorder, ctx: NemesisContext, outcome: attacks.AttackOutcome) -> None:
    recorder.environment.setdefault("cluster", ctx.provenance)
    recorder.record(outcome)


def _assert_detected(outcome: attacks.AttackOutcome) -> None:
    assert outcome.detected_by, (
        f"{outcome.id} ({outcome.name}) ran and was detected by ZERO checks. Verifier: "
        f"{outcome.verifier}. Skipped checks: {outcome.skipped_checks}"
    )


@pytest.mark.slow
def test_a10_closure_mass_rewrite(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """S2 — one ``UPDATE`` evaporates every weakening gate. K2 exit criterion 2.

    The blame closure sits under *every* ancestry gate. In the reviewed design it was
    mutable, un-granted, un-ledgered and unguarded, so one statement from the
    least-protected identity in the architecture — a Lambda execution role — would have
    zeroed ``max_severity`` while every coverage view reported full coverage. It does not
    even take a rogue DBA; one bug in an async, batched, at-least-once projector does it.

    Check 14 is what makes that visible to somebody who has never touched the cluster.
    """
    outcome = attacks.run_attack(nemesis, "A10", attacks.a10_closure_mass_rewrite)
    _record(recorder, nemesis, outcome)
    assert outcome.database_refusals, (
        "the append-only trigger on mainline.clause_blame_closure did not refuse the "
        "UPDATE. That refusal is the first of the two defences and it is the one that "
        "holds against everything below a rogue DBA."
    )
    _assert_detected(outcome)
    assert 14 in outcome.detected_by, (
        "K2.2: A10 was not detected by check 14. Generations dense from 1 with "
        "non-decreasing max_severity is the property that survives the trigger being "
        f"disabled. Detected by: {outcome.detected_by}"
    )


@pytest.mark.slow
def test_a11_prev_digest_forgery(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """S9 — ``chain_digest`` was computed server-side; its INPUT was whatever we were told.

    The primary defence here is a database refusal (``P0001`` from
    ``fn_permit_event_chain``), not a verifier finding. Check 11 catches the case where the
    trigger was removed first, which is the only case that gets past the refusal.
    """
    outcome = attacks.run_attack(nemesis, "A11", attacks.a11_prev_digest_forgery)
    _record(recorder, nemesis, outcome)
    assert outcome.database_refusals, (
        "fn_permit_event_chain did not refuse a fabricated prev_digest. Without that "
        "refusal the state-machine chain is whatever the inserter says it is, which is "
        "exactly finding S9."
    )
    assert any("P0001" in refusal for refusal in outcome.database_refusals), (
        f"the refusal was not P0001: {outcome.database_refusals}"
    )
    _assert_detected(outcome)
    assert 11 in outcome.detected_by, (
        "A11 must be caught by check 11 once the trigger has been disabled: the mechanism "
        "attested at migration time is no longer the mechanism that is running."
    )


@pytest.mark.slow
def test_a13_trigger_disable(nemesis: NemesisContext, recorder: OutcomeRecorder) -> None:
    """Disable the merge gate, then merge a permit carrying an undischarged obligation."""
    outcome = attacks.run_attack(nemesis, "A13", attacks.a13_trigger_disable)
    _record(recorder, nemesis, outcome)
    assert outcome.database_refusals, (
        "the merge gate did not refuse a permit with an undischarged obligation. That "
        "refusal IS the product: recall is a precondition of the state transition, not a "
        "report about it."
    )
    assert any("fn_permit_merge_gate" in refusal for refusal in outcome.database_refusals), (
        f"the refusal did not name the gate: {outcome.database_refusals}"
    )
    _assert_detected(outcome)
    assert 11 in outcome.detected_by, (
        "A13 must be caught by check 11. The gate is self-attesting: its CREATE TRIGGER "
        "text was sequenced into the ledger before anything it later refused, so an exhibit "
        "can show the exact source of the mechanism — and its absence."
    )


@pytest.mark.slow
def test_gate_refuses_before_anybody_disables_anything(nemesis: NemesisContext) -> None:
    """Evidence Act s.69 — the ledger is what lets work start, not a record of it.

    Stated as its own test because it is the load-bearing sentence of the whole
    admissibility argument and it must not be a side effect of an attack passing. A merge
    is REFUSED while an obligation carries no live disposition; the record therefore exists
    because the business could not proceed without it, which is what makes it a business
    record rather than something prepared in contemplation of a proceeding.
    """
    permit_id = nemesis.sql("SELECT permit_id FROM mainline.permit LIMIT 1")[0][0]
    refusal = attacks.expect_refusal(
        nemesis,
        "UPDATE mainline.permit SET state = 'merged' WHERE permit_id = %s",
        (permit_id,),
    )
    assert refusal is not None, "the merge was permitted with an open obligation"
    assert "P0001" in refusal, refusal
    assert "fn_permit_merge_gate" in refusal, refusal
    state = nemesis.sql(
        "SELECT state::STRING FROM mainline.permit WHERE permit_id = %s", (permit_id,)
    )[0][0]
    assert state != "merged"
