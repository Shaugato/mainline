# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-40 — retract a disposition after the permit has merged.

Manifest: ``23503`` on ``epoch_pin_permit``, ``MI07``, anomaly ``A3``, depth >= 2.

**Refusal by referential integrity, not by policy.** Retraction re-opens the gate *and*
bumps ``gate_epoch``; ``merge_record`` holds a composite foreign key onto
``(permit_id, gate_epoch)`` under ``ON UPDATE RESTRICT``; therefore a retraction after issue
is an attempt to mutate a pinned value, and the database refuses it the way it refuses any
other attempt to move a row a foreign key is standing on.

That is the ``PIN`` half of the kernel idiom, and it is why the composite ``UNIQUE`` on
``(permit_id, gate_epoch)`` exists at all: without a foreign-key target there is no pin,
and without the pin a precursor arriving after the merge is a perfectly serializable
history that quietly reopens an issued permit.

The declared remedy for a post-issue fact is a **fork** — suspend the issued permit, open a
child, clear its gate afresh — and the refusal here is what makes that the only available
move rather than the recommended one.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, digest32, refusal


@register("CF-40")
def cf_40_retract_after_merge(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Withdraw a signature the merge was built on."""
    world = World(harness, scope, schema)
    world.site_row()
    built = world.cleared_permit(tag="cf40")
    permit_id = built["permit_id"]

    # A second obligation and a second verdict, so the retraction has something to name:
    # `retraction_not_reflexive` refuses a disposition that retracts itself, and
    # `one_live_disposition` refuses a second live verdict on the same check.
    second_clause, second_commit = world.clause_version("cf40b")
    world.closure(second_clause, second_commit, max_severity=1, virulence="routine")
    second_check = world.check(
        clause_uuid=second_clause,
        commit_id=second_commit,
        permit_id=permit_id,
        tag="cf40b",
    )
    second_receipt = world.receipt(actor_sub=built["signer"], permit_id=permit_id, tag="cf40b")
    world.line(second_receipt, second_check)
    replacement = world.sign(
        Disposition(
            check_id=second_check,
            receipt_id=second_receipt,
            signer_sub=built["signer"],
            signer_credential_id=built["credential"],
            kind="applied",
        ),
        label="the verdict that will do the retracting",
    )
    world.run(
        "merge the permit",
        "CALL {s}.merge_permit(%s, %s, %s, 'service', '{{}}'::JSONB, %s, 1::INT2, %s)",
        (permit_id, digest32("merged"), "conformance", b"\x00", digest32("leaf")),
    )
    # THE PERMIT IS THEN SUSPENDED, and the reason is measured rather than stylistic.
    #
    # With the subject left in `merged`, the retraction trips TWO mechanisms at once:
    # `open_blocking` rises above zero on a merged row (`gate_closed_when_issued`,
    # 23514) and the epoch bump mutates a pinned value (`epoch_pin_permit`, 23503).
    # CockroachDB evaluates the table's own CHECK before the inbound foreign key and
    # reports the 23514, so the history would be refused — correctly — by a mechanism
    # that is not the one this case is about, and the exhibit would be wrong.
    #
    # `merged -> suspended` is a legal edge and it is the DECLARED REMEDY for a
    # post-issue fact: suspend the issued permit, open a child, clear its gate afresh.
    # A suspended permit satisfies `gate_closed_when_issued` (state <> 'merged') while
    # `merge_record` still pins (permit_id, gate_epoch) — so the epoch pin is isolated
    # and the refusal names it. That the OTHER mechanism also holds is not lost: it is
    # measured in `unweld/`, and it is why the manifest gives this history depth 2.
    world.append_event(
        "suspend the issued permit",
        permit_id,
        seq=4,
        prev_seq=3,
        from_state="merged",
        to_state="suspended",
        prev_digest=world.chain_digest(permit_id, 3),
    )
    world.run(
        "record the suspension on the subject",
        "UPDATE {s}.permit SET state = 'suspended', head_seq = 4 WHERE permit_id = %s",
        (permit_id,),
    )
    outcome = refusal(
        harness,
        "CF-40",
        (
            Step(
                label="retract a signature the completed merge depended on",
                sql=world.sql(
                    "UPDATE {s}.disposition SET retracted_by = %s WHERE disposition_id = %s"
                ),
                params=(replacement, built["disposition_id"]),
            ),
        ),
        relation="disposition",
    )
    outcome.stored["pinned_epoch"] = world.scalar(
        "SELECT gate_epoch FROM {s}.merge_record WHERE subject_id = %s", (permit_id,)
    )
    outcome.stored["subject_epoch"] = world.scalar(
        "SELECT gate_epoch FROM {s}.permit WHERE permit_id = %s", (permit_id,)
    )
    return outcome
