-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0158_v_blame_coverage.sql
-- CREATE VIEW mainline_audit.v_blame_coverage — the mass-rewrite tripwire (S2)
--
-- MI: MI26, MI25
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: The blame closure is the scalar every gate reads, so the interesting attack on
--            it is not "edit one row" — the append-only trigger and the monotone guard refuse
--            that — but "append a new generation for everything at once and let the readers
--            take max(closure_gen)". That attack is legal at every row and visible only in
--            aggregate, which is why S2 puts BOTH max(closure_gen) and sum(closure_gen) on
--            the MCP surface: the max moves by one on a legitimate reprojection of one
--            clause, and the sum moves by thousands on a sweep.
--
-- migration:  0158_v_blame_coverage
-- domain:     datamodel / dm-views-rls
-- band:       0155-0169z · datamodel/dm-views-rls · AUTHORED (migrations.allocation.toml, MR-6 lock 1)
-- statements: 1
-- invariants: MI26 — the closure is append-only, generation-dense and severity-monotone.
--                    This view is how a human sees the generation counter move.
--             MI25 — severity and virulence are projections of the closure, never inputs. The
--                    virulence banding this view groups on is the one performed HERE, once.
--             I05  — ancestry monotone: inherited severity must not decrease.
-- source:     ARCHITECTURE.md §17 (view definition) · §5.4 (closure DDL, the 512-ancestor
--             truncation cap) · correction S2 · §9.1
-- requires:   0039 mainline.clause_blame_current (VIEW over 0038 clause_blame_closure)
-- sqlstate:   none — this object refuses nothing.
-- forward-only; no .down.sql exists at or below the protected floor.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY TWO GENERATION COLUMNS AND NOT ONE
-- ─────────────────────────────────────────────────────────────────────────────
-- `max_closure_gen` answers "has anything been reprojected". `total_generations`
-- answers "how much". They differ in exactly the case that matters:
--
--   one clause legitimately reprojected  →  max +1,  sum +1
--   a sweep across ten thousand clauses  →  max +1,  sum +10000
--
-- A monitor watching only the max cannot tell those apart, and the sweep is the
-- shape of the attack: every individual append is legal, monotone and signed by
-- the one role that holds INSERT (`agent_projector`, S2 — the narrowest role in
-- the system). The refusal is not available; the VISIBILITY is, and this is it.
--
-- `clause_versions` beside them makes the ratio readable: sum/count is the mean
-- generation depth per clause version, and on a healthy corpus it sits just
-- above 1.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHY THIS READS clause_blame_current AND NEVER clause_blame_closure
-- ─────────────────────────────────────────────────────────────────────────────
-- DM-9: `clause_blame_current` is the ONLY read path to the closure, and a CI
-- grep fails any migration, query or view that names `clause_blame_closure`
-- outside 0038, 0039 and queries/closure_write.sql. The view carries the
-- `DISTINCT ON … ORDER BY closure_gen DESC` discipline so that no call site has
-- to remember it. One forgotten call site silently reads a superseded
-- generation, which in this table means reading a severity that has since been
-- raised — the exact direction of error the product exists to refuse.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- WHAT THIS VIEW IS NOT
-- ─────────────────────────────────────────────────────────────────────────────
-- IT IS NOT TAMPER-EVIDENCE. It is a tripwire on a surface a rogue operator can
-- read and reason about. The tamper-evidence control is the custody ledger: each
-- closure write emits a `ledger_intake` row in the same transaction (S2), so the
-- arithmetic here is corroborated by a Merkle log anchored outside the cluster.
-- Presenting this view as the control would be presenting a dashboard as a
-- defence, which §11.7's must-not-claim list names in its first line.

CREATE VIEW mainline_audit.v_blame_coverage AS
  WITH g AS (
    SELECT cbc.site_id            AS site_id,
           cbc.virulence          AS virulence,
           count(*)               AS clause_versions,
           count(*) FILTER (WHERE cbc.truncated) AS truncated_closures,
           max(cbc.depth)         AS max_depth,
           max(cbc.ancestor_count) AS max_ancestors,
           max(cbc.max_severity)  AS max_severity,
           -- S2, both halves. The max moves on any reprojection; the sum is the only column
           -- on this surface that separates one reprojection from ten thousand.
           max(cbc.closure_gen)   AS max_closure_gen,
           sum(cbc.closure_gen)   AS total_generations,
           max(cbc.computed_at)   AS last_computed_at
      FROM mainline.clause_blame_current cbc
     GROUP BY cbc.site_id, cbc.virulence
  ),
  t AS (SELECT count(*) AS group_count FROM g)
  SELECT g.site_id            AS site_id,
         g.virulence          AS virulence,
         g.clause_versions    AS clause_versions,
         g.truncated_closures AS truncated_closures,
         g.max_depth          AS max_depth,
         g.max_ancestors      AS max_ancestors,
         g.max_severity       AS max_severity,
         g.max_closure_gen    AS max_closure_gen,
         g.total_generations  AS total_generations,
         g.last_computed_at   AS last_computed_at,
         -- The truncation flag §17 requires, stated positively at the grain the reader
         -- cares about: this virulence band, at this site, was walked to the end.
         (g.truncated_closures = 0) AS ancestry_complete,
         t.group_count        AS group_count,
         (t.group_count <= 25) AS rows_complete
    FROM g CROSS JOIN t
   ORDER BY g.virulence DESC, g.site_id
   LIMIT 25;
