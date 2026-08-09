-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0159_v_disposition_coverage.sql
-- CREATE VIEW mainline_audit.v_disposition_coverage — surfaced versus answered, by quarter
--
-- MI: MI08, MI12, MI25
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: An obligation the database materialised and nobody ever answered is the single
--            most damaging artefact this schema can hold, because it is our own record of our
--            own warning going unread. Reporting it quarterly, on the surface a regulator can
--            reach, is the difference between a discovery liability and evidence of an active
--            assurance programme. `generations_aligned` is the diachronic half: a verdict
--            signed against generation 3 of a closure that is now on generation 7 was a
--            verdict about a different ancestry.
--
-- migration:  0159_v_disposition_coverage
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI08 — at most one live disposition per check, by partial UNIQUE. That is what
--                    makes the LEFT JOIN below safe: it cannot multiply a check row.
--             MI12 — a disposition exists only for a precursor materialised to that actor.
--             MI25 — severity and virulence on the check are closure projections, so
--                    `worst_ancestor` is a graph fact, not an assessor's opinion.
--             I09  — exposure binding.
-- source:     ARCHITECTURE.md §17 (view definition) · §5.5 (blocking_check, disposition) ·
--             §16 MI08 · §9.1
-- requires:   0058 mainline.blocking_check · 0066 mainline.disposition ·
--             0039 mainline.clause_blame_current
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- TWO DELIBERATE CORRECTIONS TO §17'S DRAFT
-- ─────────────────────────────────────────────────────────────────────────────
-- §17 writes:
--
--     SELECT d.site_id, date_trunc('quarter', d.signed_at) AS q,
--            count(*) AS surfaced, count(*) AS dispositioned,
--            (SELECT count(*) FROM mainline.blocking_check bc
--              WHERE bc.site_id = d.site_id AND NOT EXISTS (…)) AS orphans,
--            …
--       FROM mainline.disposition d …
--
-- 1. `count(*) AS surfaced, count(*) AS dispositioned` are the SAME expression.
--    Over a scan of `disposition` they are necessarily equal, so the view's
--    headline ratio — how much of what we surfaced got answered — is 100 % by
--    construction, always, on every corpus. A coverage metric that cannot report
--    a shortfall is worse than no coverage metric, because it is quoted.
--
-- 2. The `orphans` subquery is not scoped to the quarter it sits beside. Every
--    row of a site's history repeats the site's whole-of-time orphan count, so
--    the number grows monotonically down the page and belongs to no period.
--
-- The shipped form drives the aggregate from `blocking_check` — the OBLIGATION,
-- which is what "surfaced" means — and LEFT JOINs the live disposition onto it.
-- `dispositioned` then counts the answered subset, `orphans` is the complement
-- WITHIN THE QUARTER, and the ratio can be less than one, which is the only way
-- it can ever be evidence.
--
-- The join cannot multiply rows: MI08's partial UNIQUE
-- (`one_live_disposition … WHERE retracted_by IS NULL`) admits at most one live
-- disposition per check, and the join predicate carries that filter.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THE QUARTER IS THE CHECK'S, NOT THE SIGNATURE'S
-- ─────────────────────────────────────────────────────────────────────────────
-- `materialised_at` is a server DEFAULT now() on a row the kernel wrote inside
-- the gate transaction; `signed_at` is when a human got round to it. Bucketing
-- by the signature would move an obligation from the quarter in which it went
-- unanswered into the quarter in which it was finally answered — which is
-- precisely the presentational move that makes a backlog disappear.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- IT IS NOT A JUDGEMENT ABOUT ANY DISPOSITION'S QUALITY. §11.7's must-not-claim
-- list forbids claiming that a disposition can be distinguished from a rubber
-- stamp, and this view carries no deliberation seconds, no reading floor and no
-- person. Those exist, in `mainline_qa`, behind a role no MCP account ever
-- receives (S14).

CREATE VIEW mainline_audit.v_disposition_coverage AS
  WITH g AS (
    SELECT bc.site_id                                  AS site_id,
           date_trunc('quarter', bc.materialised_at)   AS q,
           count(*)                                    AS surfaced,
           count(d.disposition_id)                     AS dispositioned,
           count(*) - count(d.disposition_id)          AS orphans,
           max(bc.virulence::STRING)                   AS worst_ancestor,
           max(bc.severity)                            AS worst_severity,
           -- The diachronic column. A live verdict taken against an older generation of the
           -- closure is not wrong, but it is a verdict about an ancestry that has since
           -- changed, and nobody can see that without being told.
           bool_and(d.disposition_id IS NULL OR d.closure_gen = bc.closure_gen)
                                                       AS generations_aligned,
           -- Fail-closed, in the same form as 0157: absence and truncation are both false.
           bool_and(cbc.clause_uuid IS NOT NULL AND NOT cbc.truncated)
                                                       AS ancestry_complete
      FROM mainline.blocking_check bc
      LEFT JOIN mainline.disposition d
        ON d.check_id     = bc.check_id
       AND d.retracted_by IS NULL
      LEFT JOIN mainline.clause_blame_current cbc
        ON cbc.clause_uuid  = bc.clause_uuid
       AND cbc.as_of_commit = bc.commit_id
     WHERE bc.materialised_at > now() - INTERVAL '400 days'
     GROUP BY bc.site_id, date_trunc('quarter', bc.materialised_at)
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_id             AS site_id,
         g.q                   AS q,
         g.surfaced            AS surfaced,
         g.dispositioned       AS dispositioned,
         g.orphans             AS orphans,
         g.worst_ancestor      AS worst_ancestor,
         g.worst_severity      AS worst_severity,
         g.generations_aligned AS generations_aligned,
         g.ancestry_complete   AS ancestry_complete,
         t.group_count         AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.q DESC, g.orphans DESC, g.site_id
   LIMIT 25;
