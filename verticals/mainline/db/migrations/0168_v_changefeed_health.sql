-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0168_v_changefeed_health.sql
-- CREATE VIEW mainline_audit.v_changefeed_health — the ops family, arm 4 of 4
--
-- MI: MI22, MI26
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: The blame closure is written by a top-level statement driven by the outbox
--            changefeed, never by a trigger. So a stopped changefeed is not a degraded
--            notification path — it is the projector never running, which is the closure
--            going stale, which is MI22 firing on every gate that reads it. A dead feed is
--            the quietest way this system can break, and this view is the only place the
--            silence is audible.
--
-- migration:  0168_v_changefeed_health
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI22 — the gate fails closed on a stale or absent projection. `behind_seconds`
--                    and `feed_absent` are how "stale" and "absent" are told apart.
--             MI26 — the closure is append-only and generation-dense; the feed is what
--                    triggers each generation, so its health is the closure's liveness.
--             I06  — a dependency a gate consumes is COMPUTED, never declared.
-- source:     ARCHITECTURE.md §17 (the ops family) · §8.5 (the changefeed event spine,
--             cf_outbox) · §5.4 (the closure writer is driven by the outbox feed) ·
--             §18 ("changefeeds are not migrations") · §4.1 laws 11 and 12
-- requires:   0155a mainline_ops.changefeed_health_snapshot
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY A CHANGEFEED CANNOT REPORT ON ITSELF, AND WHY THAT IS THE WHOLE PROBLEM
-- ─────────────────────────────────────────────────────────────────────────────
-- §18: changefeeds are cluster JOBS, not migrations. They are re-created on
-- restore and owned by the provisioning agent, because putting CREATE CHANGEFEED
-- in a migration makes migrations non-idempotent across environments and couples
-- DDL to S3 credentials. That is the right call and it has a consequence: after
-- a restore the schema is complete, the tables are populated, every constraint
-- is armed — and no feed is running. Nothing in the database knows.
--
-- The one status a feed cannot emit is "I am not running". So the status has to
-- be collected from outside — `SHOW CHANGEFEED JOBS` on pgwire, under a
-- privileged collector — and compared against the provisioning plan's list of
-- expected feeds. `job_status = 'absent'` is the row that carries the finding,
-- and migration 0155a makes it a representable state with a CHECK rather than
-- letting absence be a missing row. A missing row is indistinguishable from a
-- collector that did not run, which is exactly the ambiguity this view exists to
-- remove.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THERE IS EXACTLY ONE CDC-QUERY SOURCE, AND WHY IT HAS NO RLS
-- ─────────────────────────────────────────────────────────────────────────────
-- §4.1 law 11, verified against the v26.2 row-level-security page: CDC queries
-- are NOT SUPPORTED on tables using RLS and will FAIL; and CDC bypasses RLS
-- entirely for the messages it does emit. `mainline_ops.outbox` is therefore the
-- one changefeed-query source in the deployment, single-family, RLS-free by
-- construction, carrying POINTERS AND DIGESTS ONLY and never clause or narrative
-- text. `RLS-MATRIX.yaml` records it under `rls_forbidden` with a test, because
-- "somebody enables RLS on the outbox" is a one-line change that breaks the
-- fleet at the next feed restart and passes every schema review.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- IT IS NOT A DELIVERY GUARANTEE. `emitted_messages` counts what the feed emitted,
-- not what the relay accepted, deduped or forwarded to EventBridge. End-to-end
-- delivery is asserted by the relay's own idempotency ledger, not here, and
-- reading a healthy highwater as "the fleet got the message" would skip three
-- hops that can each drop one.

CREATE VIEW mainline_audit.v_changefeed_health AS
  WITH latest AS (
    SELECT c.feed_name        AS feed_name,
           c.job_status       AS job_status,
           c.highwater        AS highwater,
           c.behind_seconds   AS behind_seconds,
           c.emitted_messages AS emitted_messages,
           c.error_text       AS error_text,
           c.sink_kind        AS sink_kind,
           c.sink_uri_sha256  AS sink_uri_sha256,
           c.collected_at     AS collected_at,
           c.collector        AS collector
      FROM mainline_ops.changefeed_health_snapshot c
     WHERE c.collected_at = (
             SELECT max(c2.collected_at)
               FROM mainline_ops.changefeed_health_snapshot c2
              WHERE c2.feed_name = c.feed_name)
  ),
  t AS (SELECT count(*) AS group_count FROM latest)
  SELECT latest.feed_name        AS feed_name,
         latest.job_status       AS job_status,
         (latest.job_status = 'absent')  AS feed_absent,
         (latest.job_status = 'running') AS feed_running,
         latest.highwater        AS highwater,
         latest.behind_seconds   AS behind_seconds,
         latest.emitted_messages AS emitted_messages,
         -- The error string is truncated by the collector and truncated again here. A
         -- 10 KiB response cap across 25 rows leaves ~410 bytes per row for everything,
         -- and an untruncated stack trace in one row would silently drop the other 24.
         left(coalesce(latest.error_text, ''), 160) AS error_head,
         latest.sink_kind        AS sink_kind,
         -- The digest, never the URI: a sink URI carries its credentials inline. See 0155a.
         encode(latest.sink_uri_sha256, 'hex')      AS sink_uri_sha256_hex,
         latest.collected_at     AS collected_at,
         latest.collector        AS collector,
         (now() - latest.collected_at)              AS snapshot_age,
         (latest.collected_at > now() - INTERVAL '15 minutes') AS snapshot_fresh,
         -- Fail-closed liveness. Running, with a highwater, and no more than five minutes
         -- behind. Anything else — paused, failed, absent, or running with no resolved
         -- span at all — reports false, because a feed that has emitted no resolved
         -- timestamp has committed to nothing.
         (latest.job_status = 'running'
          AND latest.highwater IS NOT NULL
          AND coalesce(latest.behind_seconds, 1e9) <= 300) AS spine_live,
         t.group_count           AS group_count,
         (t.group_count <= 25)   AS rows_complete
    FROM latest CROSS JOIN t
   ORDER BY (latest.job_status = 'running'), latest.feed_name
   LIMIT 25;
