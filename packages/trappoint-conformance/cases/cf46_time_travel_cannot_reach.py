# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-46 — reconstruct past state from the chain, and prove ``AS OF SYSTEM TIME`` cannot.

Manifest: class ``admit`` (``00000``), exhibit ``mainline.permit_event.chain_digest``,
``MI24``, anomaly ``A13``; ``asserts_stored_row``
``gc.ttlseconds < requested_horizon_seconds``.

Long-horizon history is the application-level commit DAG plus the event chain, **full
stop**. The temptation is to sell ``AS OF SYSTEM TIME`` as *"prove the state at time T"*,
and it does not work: garbage collection reclaims MVCC versions after ``gc.ttlseconds``, so
a query reaching past that window is refused rather than silently wrong. Measured on this
platform: ``4500`` seconds on Cloud Basic — seventy-five minutes, not the four hours the
architecture assumed — and the local container is configured to the same stricter value on
purpose.

Two assertions, and the second is the one that keeps the claim honest as the cluster
changes. The **history** reconstructs the subject's state at a past instant from the chain
and must complete. The **stored evidence** records the zone's configured retention against
the horizon a customer would ask for, so a future default change cannot make the sentence
in the README quietly false — the case goes red first.

The refusal that ``AS OF SYSTEM TIME`` produces is deliberately *not* the assertion. It is
outside the modelled taxonomy — it is not a gate refusal, because no gate was involved —
and recording it as evidence rather than as an expectation is the difference between
documenting a platform limit and modelling it as a product behaviour.
"""

from __future__ import annotations

import re

from trappoint_conformance.harness import Harness, HistoryOutcome, Step
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, fail_stored, refusal

REQUESTED_HORIZON_SECONDS = 90 * 24 * 3600  # a quarter, which is what an auditor asks for


@register("CF-46")
def cf_46_time_travel_cannot_reach(
    harness: Harness, scope: SiteScope, schema: str
) -> HistoryOutcome:
    """Read the chain; then try to read the past, and record that you cannot."""
    import psycopg

    world = World(harness, scope, schema)
    world.site_row()
    permit_id = world.permit("cf46")
    world.append_event(
        "genesis",
        permit_id,
        seq=1,
        prev_seq=0,
        from_state="draft",
        to_state="checks_materialised",
    )
    head = world.chain_digest(permit_id, 1)
    world.append_event(
        "second",
        permit_id,
        seq=2,
        prev_seq=1,
        from_state="checks_materialised",
        to_state="dispositioned",
        prev_digest=head,
    )

    outcome = refusal(
        harness,
        "CF-46",
        (
            Step(
                label="reconstruct the subject's state from the chain",
                sql=world.sql(
                    "SELECT to_state, chain_digest FROM {s}.permit_event "
                    "WHERE permit_id = %s ORDER BY seq"
                ),
                params=(permit_id,),
            ),
        ),
        relation="permit_event",
    )

    # `SHOW ZONE CONFIGURATION` returns (target, raw_config_sql); the retention is in the
    # SECOND column, and reading only the first would silently measure the string
    # "RANGE default" for gc.ttlseconds. Every column is scanned rather than the second
    # indexed, so a future column order cannot make this quietly unmeasurable.
    zone = " ".join(
        str(value)
        for row in world.read("SHOW ZONE CONFIGURATION FROM RANGE default")
        for value in row
    )
    match = re.search(r"gc\.ttlseconds\s*=\s*(\d+)", zone)
    ttl = int(match.group(1)) if match else -1
    outcome.stored["gc_ttlseconds"] = ttl
    outcome.stored["requested_horizon_seconds"] = REQUESTED_HORIZON_SECONDS

    probe = world.sibling_connection()
    try:
        with probe.cursor() as cur:
            cur.execute(
                world.sql(
                    "SELECT count(*) FROM {s}.permit AS OF SYSTEM TIME '-2160h' "
                    "WHERE permit_id = %s"
                ),
                (permit_id,),
            )
            outcome.stored["as_of_system_time"] = "COMPLETED"
    except psycopg.Error as exc:
        outcome.stored["as_of_system_time"] = (
            exc.diag.sqlstate if exc.diag is not None else "unknown"
        )
    finally:
        probe.close()

    if ttl < 0:
        return fail_stored(
            outcome,
            "gc.ttlseconds could not be read from the default range's zone configuration, "
            "so the claim that long-horizon history is the commit DAG rather than MVCC "
            "cannot be checked against the cluster it is being claimed about.",
        )
    if ttl >= REQUESTED_HORIZON_SECONDS:
        return fail_stored(
            outcome,
            f"gc.ttlseconds is {ttl}, which reaches the {REQUESTED_HORIZON_SECONDS}-second "
            f"horizon this case asks about. That is not a failure of the database; it means "
            f"the documented reason for the application-level commit DAG no longer holds on "
            f"this cluster and the prose has to be re-read before the test is re-tuned.",
        )
    if outcome.stored["as_of_system_time"] == "COMPLETED":
        return fail_stored(
            outcome,
            "a query ninety days in the past COMPLETED. Either the retention window is not "
            "what the zone configuration says, or the query did not do what it appears to "
            "do; either way A13's claim is not proved by this run.",
        )
    return outcome
