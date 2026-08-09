-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0156_v_open_gate_summary.sql
-- CREATE VIEW mainline_audit.v_open_gate_summary — what is currently blocked, and who has
-- been overriding
--
-- MI: MI02, MI29
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The five counters this view sums are the five plain-column CHECKs that refuse a
--            merge, so summing them is the only aggregate in the system that answers "what
--            would the database refuse right now" without re-deriving anything. S8 adds
--            overrides_30d beside them because an override ladder is only a control if
--            somebody can see the rungs being climbed, and the person climbing them is the
--            last person who will report it.
--
-- migration:  0156_v_open_gate_summary
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1). ARCHITECTURE
--             §18 wrote this band as 0140-0154 and docs/leads/datamodel.md §3 wrote it as
--             0200-0279; BOTH are revoked by MR-7 and the allocation file is the authority.
-- statements: 1
-- invariants: MI02 — a merged permit has zero open blocking checks. This view is the
--                    contrapositive, aggregated: everything the gate is still holding.
--             MI29 — emergency overrides escalate against the person across permits, with no
--                    ceiling. `overrides_30d` is the site-level shadow of that ladder.
--             I02  — every cross-row gate condition is a trigger-maintained scalar. This
--                    view sums those scalars and computes nothing of its own.
-- source:     ARCHITECTURE.md §17 (view definition, verbatim shape) · §9.1 (Managed MCP:
--             one statement, ≤16 384 chars, 20 s, 10 KiB, SELECT capped at 25 rows) ·
--             §4.1 law 12 · correction S8
-- requires:   0050 mainline.permit · 0068 mainline.override_ledger
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- THE SIZE LIMIT IS A FUNCTIONAL REQUIREMENT, NOT A STYLE
-- ─────────────────────────────────────────────────────────────────────────────
-- The Managed MCP caps a response at 10 KiB and a SELECT at 25 rows. A view that
-- exceeds either does not error: it is TRUNCATED, and the auditor reads a
-- partial answer as a complete one. In this product that is a safety defect,
-- because the partial answer is about how much is currently blocked.
--
-- So every view in this band ends `LIMIT 25` and carries two columns nobody
-- asked for:
--
--   group_count    how many groups the aggregate actually produced
--   rows_complete  false when that number exceeded 25
--
-- `rows_complete = false` is the truncation flag §17 requires. A truncated
-- aggregate must never be indistinguishable from a complete one, and the only
-- way to make that true over a transport that silently truncates is to put the
-- fact INSIDE the rows that survive.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THE CTE, AND WHY THE CORRELATED SUBQUERY STAYS
-- ─────────────────────────────────────────────────────────────────────────────
-- `group_count` cannot be computed by the same GROUP BY it counts, so the
-- grouping is a CTE and the count is a second CTE cross-joined onto it. CTEs in
-- views are supported on v26.2 (and CTEs in routines since v25.1 — F1), and this
-- is a view, not a trigger, so no part of §4.1 law 4 applies.
--
-- The `overrides_30d` correlated scalar subquery is kept exactly as §17 wrote
-- it. §4.1 law 10's subquery ban is about RLS POLICY EXPRESSIONS and law 1's is
-- about CHECK constraints. A view is neither, and rewriting it as a join would
-- change the semantics: a LEFT JOIN aggregate over override_ledger would
-- multiply the permit rows before the counters were summed, and the five numbers
-- this view exists to report would silently inflate.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. IT IS NOT SITE-SCOPED FOR THE MCP IDENTITY. §9.1 assumes pessimistically
--    that the Managed-MCP SQL identity may be admin-equivalent and that RLS may
--    not apply to it. This view is therefore designed to be SAFE IF READ IN
--    FULL: it carries counts, states and site ids, and no clause text, no
--    narrative, and no person. We never market MCP as site-scoped.
-- 2. IT IS NOT A MERGE PREDICTION. `open_blocking = 0` here means the counters
--    say zero at read time. The merge gate re-derives inside the transaction and
--    pins the epoch; a precursor arriving at T+ε is a perfectly serializable
--    history and this view has no opinion about it.

CREATE VIEW mainline_audit.v_open_gate_summary AS
  WITH g AS (
    SELECT p.site_id                        AS site_id,
           p.state                          AS state,
           count(*)                         AS permits,
           sum(p.open_blocking)             AS open_blocking,
           sum(p.open_residue)              AS open_residue,
           sum(p.open_conflicts)            AS open_conflicts,
           sum(p.open_warrants)             AS open_warrants,
           sum(p.unmodelled_asset_count)    AS unmodelled_assets,
           sum(p.unmet_floor_count)         AS unmet_floor,
           sum(p.countersigned_count)       AS countersigned,
           count(*) FILTER (WHERE p.under_hold) AS under_hold
      FROM mainline.permit p
     WHERE p.state <> 'closed'
     GROUP BY p.site_id, p.state
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_id            AS site_id,
         g.state              AS state,
         g.permits            AS permits,
         g.open_blocking      AS open_blocking,
         g.open_residue       AS open_residue,
         g.open_conflicts     AS open_conflicts,
         g.open_warrants      AS open_warrants,
         g.unmodelled_assets  AS unmodelled_assets,
         g.unmet_floor        AS unmet_floor,
         g.countersigned      AS countersigned,
         g.under_hold         AS under_hold,
         -- S8. Site- and signer-scoped, monotone across permits, no ceiling. Thirty days
         -- because that is the window in which a pattern is still actionable rather than
         -- historical, and because a quarter's worth of overrides on one site reads as
         -- normal by the time anyone looks at a quarter.
         (SELECT count(*)
            FROM mainline.override_ledger o
           WHERE o.site_id = g.site_id
             AND o.at > now() - INTERVAL '30 days')  AS overrides_30d,
         t.group_count        AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.site_id, g.state
   LIMIT 25;
