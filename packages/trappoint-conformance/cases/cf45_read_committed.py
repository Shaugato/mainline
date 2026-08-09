# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CF-45 — run the entire gate history at ``READ COMMITTED``.

Manifest: ``23514`` on ``gate_closed_when_issued``, ``MI02``, anomaly ``A12``, depth >= 2.

The gate stays welded because the conflict is **materialised in data** rather than inferred
by the isolation level. ``open_blocking`` is a real column on the subject row, written by a
trigger; the ``CHECK`` reads it in the same statement that completes the transition. None of
that requires the transaction to be serializable — it requires the row to be current, which
``READ COMMITTED`` guarantees at statement boundaries.

**This does not claim READ COMMITTED is equivalent to SERIALIZABLE, and the corpus must
never be read as claiming it.** What weakens at ``READ COMMITTED`` is *drift detection*: the
re-derivation inside ``fn_permit_merge_gate`` takes a snapshot per statement, so a
concurrent materialisation can land between the re-derivation and the counter read, and the
disagreement ``CF-03`` relies on can go unnoticed. The core refusal survives; the anomaly
detector is the part that degrades, and ``A12``'s residual says exactly that.

The isolation level is set on a dedicated connection and asserted from
``SHOW transaction_isolation`` before the history runs, because a case that *meant* to run
at ``READ COMMITTED`` and silently ran at ``SERIALIZABLE`` would be the most reassuring
possible way to prove nothing.
"""

from __future__ import annotations

from trappoint_conformance.harness import Harness, HistoryOutcome
from trappoint_conformance.runner import register
from trappoint_conformance.site import SiteScope

from ._world import World, fail_stored, refusal


@register("CF-45")
def cf_45_read_committed(harness: Harness, scope: SiteScope, schema: str) -> HistoryOutcome:
    """Run the whole history, one isolation level down."""
    import psycopg

    # THE CORPUS IS BUILT AT SERIALIZABLE, AND THAT IS A MEASUREMENT, NOT A CONVENIENCE.
    #
    # `fn_closure_guard` writes the blame closure into the custody ledger's intake in the
    # same transaction, stamping it with `cluster_logical_timestamp()` — and that function
    # is REFUSED at READ COMMITTED on v26.2.5 ("unsupported in READ COMMITTED isolation").
    # So the projection pipeline genuinely cannot run at this isolation level on this
    # platform, and a case that pretended otherwise would fail in setup and be read as a
    # gate failure.
    #
    # The split is also the right reading of the claim. A12 is about THE GATE staying
    # welded when the isolation level is downgraded — the subject, its obligation and its
    # merge — not about the ancestry projector, which is a batch writer with its own
    # transaction discipline.
    seed = World(harness, scope, schema)
    seed.site_row()
    clause_uuid, commit_id = seed.clause_version("cf45")
    seed.closure(clause_uuid, commit_id, max_severity=5, virulence="blood_fatal")

    downgraded = None
    try:
        conn = psycopg.connect(
            harness.conn.info.dsn,
            autocommit=True,
            application_name="trappoint-conform:read-committed",
        )
        # Harness pins SERIALIZABLE in its constructor — deliberately, because an
        # isolation level inherited from a pool default is an isolation level nobody
        # chose. This case is the one place that overrides it, immediately after and in
        # two visible lines, rather than by configuring the pool.
        #
        # BOTH lines are required and they do different jobs. The driver attribute is
        # what psycopg emits with `BEGIN` for the explicit transaction the history runs
        # in; the session variable is what an autocommit statement — every setup
        # statement in this case — actually runs under, and it is also what
        # `SHOW transaction_isolation` reports. Setting only the attribute leaves the
        # world built at SERIALIZABLE and the assertion below is what catches that.
        downgraded = Harness(conn)
        downgraded.conn.isolation_level = psycopg.IsolationLevel.READ_COMMITTED
        conn.execute("SET default_transaction_isolation = 'read committed'")
        world = World(downgraded, scope, schema)
        observed_level = world.scalar("SHOW transaction_isolation")
        # Everything from here down — opening the subject, materialising the obligation,
        # attempting the merge — is THE GATE HISTORY, and all of it runs downgraded.
        permit_id = world.permit("cf45")
        world.check(clause_uuid=clause_uuid, commit_id=commit_id, permit_id=permit_id, tag="cf45")
        outcome = refusal(downgraded, "CF-45", (world.merge_step(permit_id),), relation="permit")
        outcome.stored["transaction_isolation"] = observed_level
        if str(observed_level).replace(" ", "_").lower() != "read_committed":
            return fail_stored(
                outcome,
                f"this case must run at READ COMMITTED and the session reports "
                f"{observed_level!r}. A downgrade that silently did not happen is the most "
                f"reassuring possible way to prove nothing.",
            )
        return outcome
    finally:
        if downgraded is not None:
            downgraded.conn.close()
