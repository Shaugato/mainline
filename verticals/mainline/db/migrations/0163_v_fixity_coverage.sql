-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0163_v_fixity_coverage.sql
-- CREATE VIEW mainline_audit.v_fixity_coverage — how much of the plant nobody actually looked at
--
-- MI: MI21, MI22
-- I: I06
-- COUNSEL-GATED: no
-- RATIONALE: `not_checked_ratio` is the only number on this surface that reports what the
--            system DID NOT DO, expressed as a fraction of what it said it would do. A patrol
--            that ran, found nothing, and covered eleven per cent of its declared scope is
--            reported by every other kind of dashboard as a clean patrol. Here it is reported
--            as 0.89, which is what it is.
--
-- migration:  0163_v_fixity_coverage
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI21 — an UNDETERMINED fixity result never blocks. The corollary this view
--                    carries is that an unchecked asset is not a passed asset, and the ratio
--                    is where the difference is visible.
--             MI22 — the gate fails closed on a stale or absent projection: `last_completed`
--                    is how "stale" becomes readable, and a NULL `finished_at` means a patrol
--                    that started and never finished.
--             I06  — a dependency a gate consumes is COMPUTED, never declared.
-- source:     ARCHITECTURE.md §17 (view definition) · §5.8 (patrol_run, drift_finding) ·
--             §9.1 · correction S11
-- requires:   0090 mainline.patrol_run
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THE nullif(), AND WHAT A NULL RATIO MEANS
-- ─────────────────────────────────────────────────────────────────────────────
-- `sum(n_not_checked) / nullif(sum(n_in_scope), 0)` returns NULL rather than
-- raising when a patrol class declared an empty scope. NULL here means "the
-- question does not apply — nothing was in scope", and it is a DIFFERENT state
-- from 0.0, which means "everything in scope was checked". Coalescing the two
-- to zero would report an empty scope as perfect coverage, and an empty scope is
-- usually a scope predicate that stopped matching.
--
-- `scopeless_runs` is carried beside the ratio so that the NULL is not the only
-- signal: a class whose ratio is NULL and whose `scopeless_runs` equals its
-- `runs` is a patrol that has been declaring nothing in scope for ninety days.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- A MEASURED CORRECTION TO §17'S CAST — NUMERIC, NOT FLOAT8
-- ─────────────────────────────────────────────────────────────────────────────
-- §17 writes the ratio as
--
--     sum(pr.n_not_checked)::FLOAT8 / nullif(sum(pr.n_in_scope), 0)
--
-- which does not compile. Measured against CockroachDB CCL v26.2.5 on
-- 2026-08-10: `sum()` over an INT8 column returns DECIMAL, not INT8, and there
-- is no `<float> / <decimal>` binary operator. The statement fails with
--
--     round(): unsupported binary operator: <float> / <decimal>
--
-- The fix is to widen both sides to the SAME type, and NUMERIC is the right one
-- rather than FLOAT8: both operands are exact counts, the quotient is reported
-- to four places, and a binary float would introduce representation error into a
-- number that is quoted in an assurance report. `round(DECIMAL, INT)` is
-- well-defined; `round(FLOAT8, INT)` is not universally so.
--
-- The counts are INT8, so the division must be widened or it truncates toward
-- zero. Rounding to 4 places is a size decision, not a precision one: the 10 KiB
-- response cap is a functional requirement of this whole band (§9.1), and a
-- full-precision quotient costs ~20 bytes per row for digits nobody reads past
-- the third decimal.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. IT IS NOT A DRIFT REPORT. Drift findings are rows in `drift_finding`, each
--    typed by `fixity_class` and each carrying a `gate_class` that is DERIVED
--    (`gate_derived CHECK (gate_class <> 'blocking' OR severity_inherited >= 4)`).
--    This view says how much was looked at, not what was found.
-- 2. IT IS NOT LIVE OT DATA. §11.7 forbids claiming live OT connectivity. Patrol
--    scans read at `follower_read_timestamp()` against our own record of
--    observed assertions, and the observations arrive by export.

CREATE VIEW mainline_audit.v_fixity_coverage AS
  WITH g AS (
    SELECT pr.site_id                                        AS site_id,
           pr.patrol_class                                   AS patrol_class,
           count(*)                                          AS runs,
           count(*) FILTER (WHERE pr.finished_at IS NULL)     AS unfinished_runs,
           count(*) FILTER (WHERE pr.n_in_scope = 0)          AS scopeless_runs,
           max(pr.finished_at)                               AS last_completed,
           sum(pr.n_in_scope)                                AS in_scope,
           sum(pr.n_checked)                                 AS checked,
           sum(pr.n_not_checked)                             AS not_checked,
           round(sum(pr.n_not_checked)::NUMERIC
                 / nullif(sum(pr.n_in_scope), 0)::NUMERIC, 4) AS not_checked_ratio
      FROM mainline.patrol_run pr
     WHERE pr.started_at > now() - INTERVAL '90 days'
     GROUP BY pr.site_id, pr.patrol_class
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_id           AS site_id,
         g.patrol_class      AS patrol_class,
         g.runs              AS runs,
         g.unfinished_runs   AS unfinished_runs,
         g.scopeless_runs    AS scopeless_runs,
         g.last_completed    AS last_completed,
         g.in_scope          AS in_scope,
         g.checked           AS checked,
         g.not_checked       AS not_checked,
         g.not_checked_ratio AS not_checked_ratio,
         -- The truncation flag in this channel's own terms: a patrol that finished and
         -- checked everything it declared. Fail-closed — an unfinished run, an unchecked
         -- asset, or an empty scope all report false.
         (g.unfinished_runs = 0
          AND g.not_checked = 0
          AND g.in_scope > 0) AS coverage_complete,
         t.group_count       AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.site_id, g.patrol_class
   LIMIT 25;
