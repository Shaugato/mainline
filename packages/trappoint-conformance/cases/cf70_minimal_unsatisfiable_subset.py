# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-70 — a refusal with three obligations, two of them cleared, names exactly the third.

Manifest: ``23514`` on ``gate_closed_when_issued``, invariants ``I14`` and ``I02``,
``payload_schema = spec/wire/refusal.schema.json``, and
``asserts_payload``: ``len(mus) == 1 AND mus[0].kind == 'obligation' AND
naa.kind == 'dispose_obligations' AND naa.cardinality == 1``.

**Minimality is the assertion, not the presence of a payload.** A non-minimal set labelled
as a minimal unsatisfiable subset is *worse* than no MUS at all, because it is a diagnosis
that disagrees with the refusal: it names two obligations when clearing one of them would
have let the merge through, and the reader who acts on it does twice the work and learns
the wrong lesson about which obligation was binding.

A gate that only says no gets routed around. That is not a soft observation about user
experience — it is the mechanism by which safety systems are disabled, one exasperated
workaround at a time. ``I14`` is the invariant that says the refusal must be *actionable*,
and this case is where "actionable" is given a checkable meaning: the minimal reason set,
and the nearest admissible alternative with its cardinality.

The diagnosis is computed by the **database itself as the MUS oracle** — the same mechanism
that produced the refusal produces the explanation, so the two cannot disagree. For a
single-counter refusal the decomposition is declarative and costs no probe, which is why
this case also asserts ``diagnosis == 'declarative'``: a probe budget spent on the simplest
possible refusal would mean the decomposition is not doing its job.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, fail_stored, refusal


@register("CF-70")
def cf_70_minimal_unsatisfiable_subset(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Leave exactly one of three obligations open, and ask the database why it refused."""
    world = World(harness, scope, schema)
    world.site_row()
    clause_uuid, commit_id = world.clause_version("cf70")
    world.closure(clause_uuid, commit_id, max_severity=1, virulence="routine")
    permit_id = world.permit("cf70")
    signer = world.person(world.actor("signer"), rank=4)
    credential = world.credential(signer)

    checks = []
    for index in range(3):
        # Three distinct obligations: `dedupe_key` is a digest over the identity columns,
        # so three origins is the honest way to get three rows rather than three copies.
        origin = ("blame_ancestry", "weaken_over_blood", "severity_downgrade")[index]
        checks.append(
            world.check(
                clause_uuid=clause_uuid,
                commit_id=commit_id,
                permit_id=permit_id,
                origin=origin,
                tag=f"cf70-{index}",
            )
        )
    for index, check_id in enumerate(checks[:2]):
        receipt_id = world.receipt(actor_sub=signer, permit_id=permit_id, tag=f"cf70-r{index}")
        world.line(receipt_id, check_id)
        world.sign(
            Disposition(
                check_id=check_id,
                receipt_id=receipt_id,
                signer_sub=signer,
                signer_credential_id=credential,
                kind="applied",
            ),
            label=f"clear obligation {index}",
        )

    outcome = refusal(harness, "CF-70", (world.merge_step(permit_id),), relation="permit")
    payload = world.scalar(
        "SELECT trappoint.explain_refusal(%s, %s, %s, NULL)",
        ("permit", permit_id, "gate_closed_when_issued"),
    )
    outcome.stored["payload"] = payload
    outcome.stored["open_check_id"] = str(checks[2])
    if not outcome.completed and outcome.sqlstate == "23514":
        problem = _payload_problem(payload, str(checks[2]))
        if problem:
            return fail_stored(outcome, problem)
    return outcome


def _payload_problem(payload: object, expected_obligation: str) -> str:  # noqa: PLR0911
    """Return a sentence naming what is wrong with the payload, or the empty string."""
    if not isinstance(payload, dict):
        return f"explain_refusal returned {type(payload).__name__}, not a JSON object"
    mus = payload.get("mus")
    if not isinstance(mus, list):
        return "the payload carries no reason set; a refusal with no reason set is not evidence"
    if len(mus) != 1:
        return (
            f"the reason set holds {len(mus)} atoms and exactly one obligation is open. A "
            f"non-minimal set labelled as a MUS is a diagnosis that disagrees with the "
            f"refusal, which is worse than no diagnosis: {mus!r}"
        )
    atom = mus[0]
    if not isinstance(atom, dict) or atom.get("kind") != "obligation":
        return f"the single reason atom is not an obligation: {atom!r}"
    named = str(atom.get("obligation_id", ""))
    if named and named != expected_obligation:
        return (
            f"the reason set names obligation {named}, but the obligation left open is "
            f"{expected_obligation}. Naming the wrong one is how a reader clears the wrong "
            f"obligation and learns that the gate is arbitrary."
        )
    naa = payload.get("naa")
    if not isinstance(naa, dict):
        return (
            "there is no nearest admissible alternative and no stated reason for its "
            "absence. `naa: null` is legitimate only with a reason; silence is not."
        )
    if naa.get("kind") != "dispose_obligations":
        return f"the alternative is {naa.get('kind')!r}, not 'dispose_obligations'"
    if naa.get("cardinality") != 1:
        return (
            f"the alternative asks for {naa.get('cardinality')!r} dispositions where one "
            f"would open the gate"
        )
    if payload.get("diagnosis") != "declarative":
        return (
            f"a single-counter refusal was diagnosed by {payload.get('diagnosis')!r}. The "
            f"declarative decomposition covers every single-counter refusal without a "
            f"probe; spending a probe transaction here means it is not doing its job."
        )
    return ""
