# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-37 — a verbatim citation with no object key and no span digest.

Manifest: ``23514`` on ``verbatim_needs_anchor``, invariant ``I11``.

A clearance must cite a **re-verifiable anchor**, not a resemblance. ``object_key`` says
which stored object the text came from and ``span_sha256`` says which bytes of it; together
they are a claim anyone can check years later against an immutable copy, without trusting
the citation, the model that produced it, or the person who accepted it.

A verbatim citation missing either is a quotation with no source, which in an assurance
pack is worse than a gist — it *looks* like an anchor.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-37")
def cf_37_verbatim_needs_anchor(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Quote the document without saying which document, or which bytes."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf37", countersigner_org=None)
    disposition_id = world.sign(
        Disposition(
            check_id=armed["check_id"],
            receipt_id=armed["receipt_id"],
            signer_sub=armed["signer"],
            signer_credential_id=armed["signer_key"],
            kind="applied",
        ),
        label="a legal verdict, so the citation is the only illegal thing here",
    )
    return refusal(
        harness,
        "CF-37",
        (
            Step(
                label="cite verbatim with no anchor",
                sql=world.sql(
                    "INSERT INTO {s}.disposition_citation "
                    "(disposition_id, citation_ord, kind, object_key, span_sha256) "
                    "VALUES (%s, 1, 'verbatim', NULL, NULL)"
                ),
                params=(disposition_id,),
            ),
        ),
        relation="disposition_citation",
    )
