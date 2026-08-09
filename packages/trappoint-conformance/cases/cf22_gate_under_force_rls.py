# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-22 — run the entire gate transaction with ``FORCE ROW LEVEL SECURITY`` active.

Manifest: class ``admit`` (``00000``) on ``gate_write``; secondary ``42501`` on
``gate_write``; ``requires = ["policy:mainline.permit"]``; profile ``mainline`` only.

With ``FORCE`` and no write policy the default is **DENY**, and the gate locks *itself*
out: the merge cannot happen at all, and a suite that never ran this history would
discover that in production.

**This case must never pass by absence.** While ``pg_policies`` holds nothing for the
profile's schema it is a skip *with a printed reason*; the moment a policy exists it is a
hard failure if the gate cannot complete a legal merge under it. The two states are
distinguished mechanically, here, rather than by whoever reads the report:

* the operator did not declare ``policy:mainline.permit`` — the runner skips it before
  this function is ever called, and the skip is printed and counted;
* the operator *did* declare it and the policies are not there — that is a false
  declaration and this function fails, naming the missing policy.

The policy-drop half is a schema mutation and therefore belongs to the unwelding suite,
which runs serially on a disposable container. It is registered there as the
``force-rls-without-write-policy`` mutation, and ``REFUSAL_DEPTH.md`` carries the result.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, digest32, fail_stored, refusal

POLICY = "gate_write"


@register("CF-22")
def cf_22_gate_under_force_rls(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Complete a legal merge with row-level security forced on."""
    world = World(harness, scope, schema)
    policies = world.read(
        "SELECT policyname FROM pg_policies WHERE schemaname = %s AND tablename = 'permit'",
        (schema,),
    )
    forced = world.scalar(
        "SELECT c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = 'permit'",
        (schema,),
    )
    world.site_row()
    built = world.cleared_permit(tag="cf22")
    outcome = refusal(
        harness,
        "CF-22",
        (world.call_merge_permit(built["permit_id"]),),
        relation="permit",
    )
    outcome.stored["policies"] = [row[0] for row in policies]
    outcome.stored["relforcerowsecurity"] = forced
    if not policies:
        return fail_stored(
            outcome,
            f"the capability token policy:{schema}.permit was declared satisfied, but "
            f"pg_policies holds no policy for {schema}.permit. This case exists to fail "
            f"here rather than pass by absence: a gate that is never run under FORCE ROW "
            f"LEVEL SECURITY has not been shown to survive it.",
        )
    if POLICY not in {row[0] for row in policies}:
        return fail_stored(
            outcome,
            f"{schema}.permit carries policies {[r[0] for r in policies]!r} but not "
            f"{POLICY!r}, which is the exhibit the manifest names for both halves of this "
            f"case.",
        )
    if not forced:
        return fail_stored(
            outcome,
            f"{schema}.permit has policies but relforcerowsecurity is false. Without "
            f"FORCE, the table owner bypasses every policy and this history proves "
            f"nothing about the configuration that actually ships. "
            f"Digest of the attempted merge: {digest32('merged').hex()[:16]}.",
        )
    return outcome
