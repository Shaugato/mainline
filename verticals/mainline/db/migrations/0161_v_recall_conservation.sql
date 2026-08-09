-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0161_v_recall_conservation.sql
-- CREATE VIEW mainline_audit.v_recall_conservation — conservation law L3, on the audit surface
--
-- MI: MI17, MI16, MI18
-- I: I13
-- COUNSEL-GATED: no
-- RATIONALE: `candidates = blocking + advisory + silenced + deduped` is a database CHECK on
--            every recall run, so a violation cannot reach this view. What the view adds is
--            the fleet-level question the CHECK cannot ask: is the partition DRIFTING — is the
--            silenced share climbing, are arms degrading, is the bonded-fatality count moving
--            — which is how a retrieval system fails in practice. It fails by getting quieter,
--            not by getting wrong.
--
-- migration:  0161_v_recall_conservation
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI17 — recall candidates are exactly partitioned (`candidates_conserved`).
--             MI16 — every severity-5 event bonded to the permit's activity node or an
--                    ancestor is blocking (`bonded_fatalities_all_blocking`). Summed here so
--                    that "a fatality in your fonds is always recalled" is a number a
--                    regulator can read, not a sentence in a deck.
--             MI18 — a recall runs only under an anchored, cosigned policy version.
--             I13  — silence is logged with its arithmetic.
-- source:     ARCHITECTURE.md §17 (view definition) · §5.7 (recall_run DDL) · §16 L3 ·
--             corrections S10, S24 · §9.1
-- requires:   0081 mainline_meas.recall_run
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY A CONSERVATION COLUMN ON A SURFACE WHERE CONSERVATION IS ALREADY A CHECK
-- ─────────────────────────────────────────────────────────────────────────────
-- `conserved` below re-computes, in SQL, the same equality the table's
-- `candidates_conserved` CHECK enforces. It should be `true` on every row of
-- every corpus, forever. That is the point.
--
-- A column that is always true is worthless as a metric and valuable as a
-- TRIPWIRE, because it is false in exactly two situations, both of which matter
-- more than any number beside it: somebody dropped the constraint (which is
-- legal for an admin — case S23 — and is what the custodian patrol exists to
-- surface), or the constraint was never applied on this cluster because a
-- migration was skipped. In both cases the fleet keeps running and every other
-- column on this view keeps looking reasonable. This is the one that stops.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY 25 DAYS AND NOT 30
-- ─────────────────────────────────────────────────────────────────────────────
-- The grain is one row per (site, day), and the transport caps a SELECT at 25
-- rows. A 30-day window over a single site produces 30 groups, of which the
-- reader sees 25 and — without `rows_complete` — has no way to know five are
-- missing. §17 chose 25 days deliberately so that a single-site deployment fits
-- exactly, and the flag covers the multi-site case where it cannot. Both, not
-- either: the window makes truncation rare and the flag makes it visible.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- `any_degraded` is an OR across the day: one degraded arm in one run flips the
-- day. That is deliberate and it is not a quality score. Degradation on the
-- recall path is a fail-closed event — the ladder in §14 turns a degraded arm
-- into a wider candidate set and more blocking checks, never fewer — so a day
-- flagged degraded is a day the gate was NOISIER, not a day it was weaker.
-- Reading this column as an availability metric inverts its sign.

CREATE VIEW mainline_audit.v_recall_conservation AS
  WITH g AS (
    SELECT r.site_id                          AS site_id,
           date_trunc('day', r.started_at)    AS d,
           count(*)                           AS runs,
           sum(r.n_candidates)                AS candidates,
           sum(r.n_blocking)                  AS blocking,
           sum(r.n_advisory)                  AS advisory,
           sum(r.n_silenced)                  AS silenced,
           sum(r.n_deduped)                   AS deduped,
           sum(r.n_bonded_sev5)               AS bonded_sev5,
           sum(r.n_bonded_sev5_blocking)      AS bonded_sev5_blocking,
           bool_or(r.arms_degraded)           AS any_degraded,
           count(DISTINCT r.policy_version)   AS policy_versions,
           count(DISTINCT r.index_generation) AS index_generations
      FROM mainline_meas.recall_run r
     WHERE r.started_at > now() - INTERVAL '25 days'
     GROUP BY r.site_id, date_trunc('day', r.started_at)
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_id              AS site_id,
         g.d                    AS d,
         g.runs                 AS runs,
         g.candidates           AS candidates,
         g.blocking             AS blocking,
         g.advisory             AS advisory,
         g.silenced             AS silenced,
         g.deduped              AS deduped,
         g.bonded_sev5          AS bonded_sev5,
         g.bonded_sev5_blocking AS bonded_sev5_blocking,
         g.any_degraded         AS any_degraded,
         g.policy_versions      AS policy_versions,
         g.index_generations    AS index_generations,
         -- L3, re-derived. Always true; false only if the CHECK is gone. See above.
         (g.candidates = g.blocking + g.advisory + g.silenced + g.deduped) AS conserved,
         -- MI16, re-derived at the same grain, for the same reason.
         (g.bonded_sev5 = g.bonded_sev5_blocking) AS fatalities_all_blocking,
         -- The truncation flag this table can honestly support: a degraded arm is a
         -- retrieval that did not cover what it intended to cover, which is the recall
         -- channel's form of an incomplete walk.
         (NOT g.any_degraded)   AS retrieval_complete,
         t.group_count          AS group_count,
         (t.group_count <= 25)  AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.d DESC, g.site_id
   LIMIT 25;
