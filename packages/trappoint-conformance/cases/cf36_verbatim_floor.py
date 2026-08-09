# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-36 — a ``mechanism_absent`` disposition citing only gist evidence.

Manifest: ``23514`` on ``verbatim_floor``, invariant ``I11``.

**Gist may accuse; only verbatim may acquit.** A paraphrase is enough to raise an
obligation — it costs nothing but attention, and a false positive is a conversation — but
it is not enough to dismiss one, because a dismissal ends the conversation and the
paraphrase is the artefact most likely to have lost the qualifier that mattered.

``verbatim_anchor_count`` is projected from ``disposition_citation``, counting only
citations of kind ``verbatim``. Citations are written *after* the disposition — they carry a
foreign key to it — so at insert time the count is zero, and a verdict declaring
``required_anchors`` above zero is refused until the anchors exist. The floor is therefore
enforced at the moment of signature rather than at some later reconciliation nobody runs.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-36")
def cf_36_verbatim_floor(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Acquit on a paraphrase."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf36", countersigner_org=None)
    return refusal(
        harness,
        "CF-36",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="mechanism_absent",
                predicate_id=world.uid("cf36:predicate"),
                required_anchors=1,
            ).step(world, "dismiss a mechanism with no verbatim anchor"),
        ),
        relation="disposition",
    )
