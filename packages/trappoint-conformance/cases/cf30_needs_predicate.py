# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-30 — a ``mechanism_absent`` disposition with no bounded, machine-checkable predicate.

Manifest: ``23514`` on ``needs_predicate``, ``MI11``, invariants ``I10`` and ``I12``.

An unquantified ``mechanism_absent`` is not a representable state. *The mechanism cannot
occur here* is a claim about the physical world, and a claim about the physical world that
cannot be checked is an opinion with a signature on it.

The constructor is ``mechanism_absent`` and never ``not_applicable``, and the naming is the
argument: **a dismissal is disregard, and disregard is the statutory element.** A verdict
called *not applicable* invites the reading that nothing was considered; a verdict called
*mechanism absent* forces the signer to say which mechanism, and the predicate forces them
to say how anybody could tell.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import Disposition, World, refusal


@register("CF-30")
def cf_30_needs_predicate(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Assert absence without saying how absence would be observed."""
    world = World(harness, scope, schema)
    world.site_row()
    armed = world.armed_permit(tag="cf30", countersigner_org=None)
    return refusal(
        harness,
        "CF-30",
        (
            Disposition(
                check_id=armed["check_id"],
                receipt_id=armed["receipt_id"],
                signer_sub=armed["signer"],
                signer_credential_id=armed["signer_key"],
                kind="mechanism_absent",
            ).step(world, "declare the mechanism absent with nothing to check"),
        ),
        relation="disposition",
    )
