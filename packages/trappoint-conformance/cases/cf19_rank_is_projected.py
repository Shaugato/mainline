# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-19 — sign with a client-supplied ``signer_rank`` of 6 on a person whose live rank is 2.

Manifest: ``23514`` on ``rank_floor``, ``MI27``, anomaly ``A14``; ``asserts_stored_row``
``disposition.signer_rank = 2``.

**Asserting only the 23514 would pass against an implementation that trusted the client**
and happened to have a low floor, which is why the manifest asks for two things and this
case runs two histories.

*The legal twin* signs the same lie — ``signer_rank = 6`` supplied by the client — at a
virulence whose floor a rank-2 signer clears. The row lands, and it reads ``2``. The
projection overwrote the client's claim before any constraint looked at it.

*The illegal history* signs the same lie where the floor is 4. The projection overwrites
first, ``rank_floor`` compares second, and the refusal names itself.

Order is the whole content of the case: overwrite, then compare. Reversed, the constraint
would be comparing the client's own claim against a floor, which is a signature checking
itself.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, fail_stored, refusal

# The rank the person actually holds, and the rank the client claims. Named because
# the whole case is the distance between the two.
LIVE_RANK = 2
CLAIMED_RANK = 6


@register("CF-19")
def cf_19_rank_is_projected(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Claim rank six twice: once where it does not matter, once where it does."""
    world = World(harness, scope, schema)
    world.site_row()

    # ── the legal twin: routine / applied, floor 1 ──
    twin = world.armed_permit(tag="cf19-twin", max_severity=1, virulence="routine", signer_rank=2)
    twin_id = world.sign(
        Disposition(
            check_id=twin["check_id"],
            receipt_id=twin["receipt_id"],
            signer_sub=twin["signer"],
            signer_credential_id=twin["signer_key"],
            kind="applied",
            claim_signer_rank=CLAIMED_RANK,
        ),
        label="the same claim where the floor does not bite",
    )
    landed = world.scalar(
        "SELECT signer_rank FROM {s}.disposition WHERE disposition_id = %s", (twin_id,)
    )

    # ── the illegal history: blood_fatal / applied, floor 4 ──
    armed = world.armed_permit(tag="cf19", max_severity=5, virulence="blood_fatal", signer_rank=2)
    outcome = refusal(
        harness,
        "CF-19",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="applied",
                claim_signer_rank=CLAIMED_RANK,
            ).step(world, "sign a fatality-written control claiming a rank not held"),
        ),
        relation="disposition",
    )
    outcome.stored["signer_rank"] = landed
    if landed != LIVE_RANK:
        return fail_stored(
            outcome,
            f"the client supplied signer_rank = 6 on a person whose live rank is 2, and "
            f"the stored row reads {landed!r}. The projection did not overwrite, so the "
            f"23514 this case also observed proves nothing: a floor compared against the "
            f"signer's own claim is a signature checking itself.",
        )
    return outcome
