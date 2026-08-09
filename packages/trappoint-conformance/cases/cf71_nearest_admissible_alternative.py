# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-71 — a clearance-lattice refusal names exactly the verdict kinds that DO exist.

Manifest: ``23503`` on ``fk_clearance``, invariants ``I14`` and ``I10``, ``MI11``,
``payload_schema = spec/wire/refusal.schema.json``, and ``asserts_payload``:
``naa.kind == 'substitute_kind' AND set(naa.legal_kinds) ==
kinds_present_in_clearance_legal(virulence)``.

``CF-07`` proves the lattice refuses. This case proves the refusal is **navigable**. At
``blood_fatal`` with ``mechanism_absent`` the alternative lists the kinds that do exist at
that virulence — and it lists them by reading ``clearance_legal``, which is the same table
the foreign key consulted, so the advice cannot drift from the rule.

That is the difference between a gate and an obstacle. *"You may not dismiss this"* is an
obstacle. *"You may not dismiss this; at this severity the available verdicts are applied,
mitigated, escalated and emergency_override"* is a gate with a door in it, and the person
reading it does the safe thing instead of the thing that gets the job done.

**Where the verdict set is empty by design, ``naa`` is null with reason
``no_legal_verdict_exists``** — which is the product working, not a diagnoser failing, and
the payload says which of the two happened. A diagnoser that emitted a helpful-looking
empty list in that case would be inviting the reader to keep looking for the door.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, fail_stored, refusal


@register("CF-71")
def cf_71_nearest_admissible_alternative(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Be refused by the lattice, and ask it what would have been legal."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf71", max_severity=5, virulence="blood_fatal", signer_rank=9)
    outcome = refusal(
        harness,
        "CF-71",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="mechanism_absent",
                countersigner_sub=armed["countersigner"],
                countersigner_credential_id=armed["counter_key"],
                compensating_clause_uuid=world.clause_row(),
                predicate_id=world.uid("cf71:predicate"),
                reassert_by=World.soon(86400),
            ).step(world, "dismiss a fatality-written control"),
        ),
        relation="disposition",
    )
    legal_kinds = {
        row[0]
        for row in world.read(
            "SELECT kind::STRING FROM {s}.clearance_legal WHERE virulence = 'blood_fatal'"
        )
    }
    payload = world.scalar(
        "SELECT trappoint.explain_refusal(%s, %s, %s, %s::JSONB)",
        (
            "permit",
            armed["permit_id"],
            "fk_clearance",
            f'{{"kind": "mechanism_absent", "check_id": "{armed["check_id"]}"}}',
        ),
    )
    outcome.stored["payload"] = payload
    outcome.stored["legal_kinds"] = sorted(legal_kinds)
    if not outcome.completed and outcome.sqlstate == "23503":
        problem = _alternative_problem(payload, legal_kinds)
        if problem:
            return fail_stored(outcome, problem)
    return outcome


def _alternative_problem(payload: object, legal_kinds: set[str]) -> str:  # noqa: PLR0911
    """Return a sentence naming what is wrong with the alternative, or the empty string."""
    if not isinstance(payload, dict):
        return f"explain_refusal returned {type(payload).__name__}, not a JSON object"
    naa = payload.get("naa")
    if naa is None:
        reason = payload.get("naa_reason")
        if reason == "no_legal_verdict_exists" and not legal_kinds:
            return ""
        return (
            f"there is no alternative and the stated reason is {reason!r}, but "
            f"{len(legal_kinds)} verdict kind(s) do exist at this virulence: "
            f"{sorted(legal_kinds)!r}. A gate with a door in it that does not mention the "
            f"door is an obstacle."
        )
    if not isinstance(naa, dict):
        return f"the alternative is not an object: {naa!r}"
    if naa.get("kind") != "substitute_kind":
        return (
            f"the alternative is {naa.get('kind')!r}; a lattice refusal is answered by "
            f"substituting a verdict kind, not by anything else"
        )
    offered = naa.get("legal_kinds")
    if not isinstance(offered, list):
        return f"the alternative names no legal kinds: {naa!r}"
    if set(offered) != legal_kinds:
        return (
            f"the alternative offers {sorted(offered)!r} and clearance_legal holds "
            f"{sorted(legal_kinds)!r} at this virulence. Advice that has drifted from the "
            f"rule it is advice about is worse than no advice: it sends the reader to a "
            f"door that is not there."
        )
    return ""
