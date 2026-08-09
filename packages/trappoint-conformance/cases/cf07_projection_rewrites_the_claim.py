# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-07 — the only test of the claim the company is built on.

Manifest: ``23503`` on ``fk_clearance``; ``asserts_stored_row``
``blocking_check.severity = 5 AND blocking_check.virulence = 'blood_fatal'``;
``MI25`` and ``MI11``. **The first case that must be green.**

Finding ``S1`` said the flagship claim was launderable one hop upstream: a model-driven
role that can write an obligation could choose its own virulence class, and the clearance
lattice would then faithfully enforce a claim the writer had made about itself. Two
assertions close it, and both are required.

**One — the row is rewritten.** The check is inserted claiming ``virulence='routine'`` and
``severity=1`` against a clause whose blame closure holds ``max_severity=5``. What lands
reads ``(5, 'blood_fatal')``. Not flagged, not warned about: *overwritten*, before the row
exists, from a relation the writing role may not write.

**Two — the disposition is then refused by name.** ``(blood_fatal, mechanism_absent)`` is
not a stricter row in the clearance lattice; it is **no row**, so the composite foreign key
refuses with ``23503`` and names itself. Not a policy engine, not an ``if``: referential
integrity, for every writer including a DBA at a prompt.

**Why the disposition is so heavily equipped.** Ruling ``D3``: a missing lattice row
projects the *strictest* requirements rather than raising, because a synthetic ``23503``
carries no constraint name and the constraint name is the exhibit. So every ``CHECK`` on
the table must be satisfied before the foreign key is ever consulted — rank nine, a
foreign-org countersigner on a different credential, a compensating clause, a bounded
predicate and a reassertion date. Removing any one of them would produce a ``23514``
somewhere else and this case would pass for the wrong reason.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, fail_stored, refusal


@register("CF-07")
def cf_07_projection_rewrites_the_claim(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Claim routine over a fatality, then try to dismiss what was really written."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf07")
    world.closure(clause_uuid, commit_id, max_severity=5, virulence="blood_fatal")
    permit_id = world.permit()

    signer = world.person(world.actor("signer"), rank=9, org="alpha-operations")
    countersigner = world.person(world.actor("counter"), rank=9, org="beta-assurance")
    signer_key = world.credential(signer, tag="signer")
    counter_key = world.credential(countersigner, tag="counter")

    # THE LAUNDERING ATTEMPT, as setup. It is not refused — a check may be proposed by a
    # role that is wrong about it — it is CORRECTED.
    check_id = world.check(
        clause_uuid=clause_uuid,
        commit_id=commit_id,
        permit_id=permit_id,
        origin="weaken_over_blood",
        claim_severity=1,
        claim_virulence="routine",
    )
    stored = world.read(
        "SELECT severity, virulence FROM {s}.blocking_check WHERE check_id = %s", (check_id,)
    )
    receipt_id = world.receipt(actor_sub=signer, permit_id=permit_id)
    world.line(receipt_id, check_id)

    outcome = refusal(
        harness,
        "CF-07",
        (
            Disposition(
                check_id=check_id,
                receipt_id=receipt_id,
                signer_sub=signer,
                signer_credential_id=signer_key,
                kind="mechanism_absent",
                countersigner_sub=countersigner,
                countersigner_credential_id=counter_key,
                compensating_clause_uuid=world.clause_row(),
                predicate_id=world.uid("cf07:predicate"),
                reassert_by=World.soon(86400),
            ).step(world, "file a mechanism_absent disposition against a fatality"),
        ),
        relation="disposition",
    )
    outcome.stored["blocking_check"] = stored
    outcome.stored["permit_open_blocking"] = world.scalar(
        "SELECT open_blocking FROM {s}.permit WHERE permit_id = %s", (permit_id,)
    )

    # ASSERTION ONE. Checked here rather than only in tests/, so the CLI path — the one a
    # third party runs to check a fork's claim — enforces it too.
    if stored != [(5, "blood_fatal")]:
        return fail_stored(
            outcome,
            f"the check was inserted claiming (1, 'routine') and must read (5, "
            f"'blood_fatal') after fn_check_project; it reads {stored!r}. The projection "
            f"did not overwrite, so severity is an input and the clearance lattice is "
            f"enforcing a claim the writer made about itself.",
        )
    return outcome
