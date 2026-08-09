-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0157_v_weakenings_without_disposition.sql
-- CREATE VIEW mainline_audit.v_weakenings_without_disposition — the plaintiff's first query
--
-- MI: MI02, MI26
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: This is the question a solicitor asks three years from now: which controls were
--            weakened over blood-written ancestry and never answered for. If MAINLINE cannot
--            answer it about itself, the first person to ask it will be answering it for us.
--            The view is deliberately an ACCUSATION SURFACE — it lists our own unanswered
--            weakenings — because a system that only reports its clean state is a system
--            whose reports are worth nothing in a courtroom.
--
-- migration:  0157_v_weakenings_without_disposition
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI02 — a merged permit has zero open blocking checks. This view finds the
--                    weakenings for which no obligation was ever DISPOSITIONED, which is the
--                    set MI02 would have caught had a permit cited them.
--             MI26 — the blame closure is append-only, generation-dense and severity-monotone.
--                    `ancestry_complete` is that invariant's read-side confession.
--             I02  — the severity this view filters on (`sev_max`) is a projected scalar, not
--                    a model output.
-- source:     ARCHITECTURE.md §17 (view definition) · §5.4 (the closure and its truncation
--             cap of 512 ancestors) · §9.1 · correction S2
-- requires:   0029 mainline.clause_version · 0024 mainline.commit_obj ·
--             0039 mainline.clause_blame_current (VIEW over 0038 clause_blame_closure) ·
--             0058 mainline.blocking_check · 0066 mainline.disposition
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- ONE DELIBERATE CORRECTION TO §17'S DRAFT, AND IT IS THE WHOLE POINT OF THE VIEW
-- ─────────────────────────────────────────────────────────────────────────────
-- §17 writes the truncation flag as:
--
--     bool_and(NOT cbc.truncated) AS ancestry_complete
--
-- Under the LEFT JOIN that precedes it, a clause version with NO closure row at
-- all produces `cbc.truncated IS NULL`, so `NOT cbc.truncated` is NULL, and
-- `bool_and` IGNORES NULLs. A group in which every clause is missing its closure
-- therefore reports `ancestry_complete = NULL`, and a group in which one clause
-- is missing and the rest are complete reports TRUE.
--
-- That fails OPEN, in the one column whose entire job is to fail closed. A
-- missing closure is strictly worse than a truncated one — truncation means we
-- walked and stopped; absence means we never walked — and §5.4 is explicit that
-- a truncated closure must never be indistinguishable from a complete one.
--
-- The shipped form is therefore:
--
--     bool_and(cbc.clause_uuid IS NOT NULL AND NOT cbc.truncated)
--
-- which reports FALSE for absence, FALSE for truncation, and TRUE only when
-- every clause in the group was walked to the end. This is a correction to the
-- draft, not a deviation from the design: §5.4's rule is the authority and §17's
-- expression did not implement it.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY `sev_max >= 4` AND NOT A MODEL SCORE
-- ─────────────────────────────────────────────────────────────────────────────
-- `clause_version.sev_max` is the BLOODLINE accumulator, monotone by MI15 and
-- derived only from ACTIVE blame edges — and MI13 keeps inferred edges out of
-- `active`, so no model output can raise this number. That is what makes this
-- view's population defensible under cross-examination: every row in it is here
-- because of a graph fact, and the graph's edges each cite a document.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. IT IS NOT A LIST OF UNSAFE CLAUSES. A weakening with no disposition may
--    simply be a weakening no permit has cited yet; the obligation materialises
--    when a subject cites the clause. Reading this as a defect list overstates
--    it, and overstating it is how an internally-generated exhibit becomes the
--    plaintiff's best one.
-- 2. IT IS NOT SCOPED TO MERGED SUBJECTS. It reports the repository's own
--    weakenings whether or not anything downstream has consumed them, because
--    the MOC Ancestry Audit's question is about the repository.

CREATE VIEW mainline_audit.v_weakenings_without_disposition AS
  WITH g AS (
    SELECT cv.site_id                    AS site_id,
           cv.activity_root              AS activity_root,
           cv.sev_max                    AS sev_max,
           count(*)                      AS n,
           max(co.committed_at)          AS most_recent,
           count(*) FILTER (WHERE cv.control_delta = 'remove') AS n_removed,
           -- Fail-closed truncation flag; see the block above. Absence and truncation are
           -- both `false`, and only a fully-walked group reports `true`.
           bool_and(cbc.clause_uuid IS NOT NULL AND NOT cbc.truncated) AS ancestry_complete,
           count(*) FILTER (WHERE cbc.clause_uuid IS NULL)     AS closures_absent,
           count(*) FILTER (WHERE cbc.truncated)               AS closures_truncated
      FROM mainline.clause_version cv
      JOIN mainline.commit_obj co
        ON co.commit_id = cv.commit_id
      LEFT JOIN mainline.clause_blame_current cbc
        ON cbc.clause_uuid  = cv.clause_uuid
       AND cbc.as_of_commit = cv.commit_id
     WHERE cv.control_delta IN ('weaken', 'remove')
       AND cv.sev_max >= 4
       AND NOT EXISTS (
             SELECT 1
               FROM mainline.blocking_check bc
               JOIN mainline.disposition d
                 ON d.check_id = bc.check_id
                AND d.retracted_by IS NULL
              WHERE bc.clause_uuid = cv.clause_uuid
                AND bc.commit_id   = cv.commit_id)
     GROUP BY cv.site_id, cv.activity_root, cv.sev_max
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_id            AS site_id,
         g.activity_root      AS activity_root,
         g.sev_max            AS sev_max,
         g.n                  AS n,
         g.n_removed          AS n_removed,
         g.most_recent        AS most_recent,
         g.ancestry_complete  AS ancestry_complete,
         g.closures_absent    AS closures_absent,
         g.closures_truncated AS closures_truncated,
         t.group_count        AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.sev_max DESC, g.n DESC, g.site_id, g.activity_root
   LIMIT 25;
