-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · queries/closure_write.sql
-- THE BLAME CLOSURE WRITER — one top-level statement, executed by the projector, never a trigger.
--
-- MI: MI26, MI13, MI22
-- I: I05, I11
-- Owner:      datamodel/dm-blame (band 0032-0039)
-- Source:     ARCHITECTURE.md §5.4 (the recursive CTE, verbatim in shape) · §8 the
--             `closure-projector` agent · docs/leads/datamodel.md DM-9
-- Reads:      mainline.blame_edge · mainline.event_edge · mainline.event ·
--             mainline.clause_version · mainline.clause_blame_current
-- Writes:     mainline.clause_blame_closure — one row, INSERT only, as `agent_projector`
-- Plan:       asserted in verticals/mainline/db/queries/EXPLAIN-ASSERTIONS.md
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS IS A TOP-LEVEL APPLICATION STATEMENT. IT IS NOT A TRIGGER AND MUST NEVER BECOME ONE.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- The closure is projected ASYNCHRONOUSLY, off the `blame_dirty` outbox changefeed, by the
-- `closure-projector` Lambda running as `agent_projector` — a role that holds `INSERT` on
-- `mainline.clause_blame_closure` and on nothing else in the entire schema (finding S2). Three
-- reasons, and the third is the one people try to argue with:
--
--   1. A recursive walk of unbounded cost inside a hot trigger is not `EXPLAIN`-assertable and
--      its runtime is a function of a customer's incident history. The gate transaction's p99 is
--      a product requirement, not an aspiration.
--   2. A `CHECK` can consume a projected scalar and nothing else (§4.1 law 1).
--   3. Asynchrony is SAFE HERE PRECISELY BECAUSE THE GATE FAILS CLOSED (MI22). A permit whose
--      clause has no closure row, or whose closure is stale, does not merge — it is refused. So
--      the worst case of projector lag is a refusal that should not have been needed, which is
--      the correct direction. Making this a trigger to "keep it fresh" would trade an honest
--      refusal for a hot unbounded walk on the money path.
--
-- ── PARAMETERS ────────────────────────────────────────────────────────────────────────────────
--
--   $1  clause_uuid     UUID   the clause whose ancestry is being projected
--   $2  as_of_commit    BYTES  the commit that produced the clause VERSION (32-byte sha256)
--   $3  computed_by     STRING the projector's agent identity, e.g. 'agent_projector'
--   $4  projector_ver   STRING the code version that produced this generation
--
-- `closure_gen` and `site_id` are NOT parameters, deliberately. Both are DERIVED inside the
-- statement, from authoritative relations, because a caller-supplied value for either is a
-- projection that is trusted rather than enforced (P2) and both feed things a gate reads:
--
--   closure_gen  ← `mainline.clause_blame_current` (DM-9: the ONLY read path), + 1, or 0 when no
--                  generation exists. A caller that computes this itself gets it wrong exactly
--                  once — under a redelivered changefeed message — and `fn_closure_guard` (0108)
--                  then raises P0001 on a non-dense generation, which is a refusal for a defect
--                  the statement can simply not have.
--   site_id      ← `mainline.clause_version`. The closure's `site_id` is the RLS scope token and
--                  the leading column of BOTH indexes; a caller that supplied it could file a
--                  clause's ancestry under another site's tenancy.
--
-- ── THE ZERO-ROW CONTRACT, WHICH THE CALLER MUST HONOUR ───────────────────────────────────────
--
-- Because `site_id` is derived by joining `mainline.clause_version`, a `(clause_uuid,
-- as_of_commit)` pair that names no committed clause version produces ZERO rows from the SELECT
-- and therefore inserts NOTHING, silently and with no error. That is the one failure mode of this
-- statement, so it is stated here and made detectable rather than hidden:
--
--     **A caller that receives an empty `RETURNING` result MUST treat it as a refusal**, log it
--     against the outbox message, and NOT acknowledge the changefeed row. An empty result means
--     "there is no such clause version", never "the closure is empty" — an empty closure is a
--     REAL ROW with `ancestor_count = 0`, and distinguishing the two is exactly what MI22 needs.
--
-- ── WHY `UNION` AND NOT `UNION ALL` ───────────────────────────────────────────────────────────
--
-- Diamond ancestry is the normal case, not the exotic one: a 2019 near-miss is `recurrence_of` a
-- 2011 incident AND `precursor_of` a 2021 one, and both paths reach the same 2004 fatality.
-- `UNION ALL` would enumerate every path and the row count would grow combinatorially in a graph
-- whose node count is small. `UNION` de-duplicates `(event_id, depth)` at every step, which
-- collapses the diamond and — as 0034's `no_self_edge` comment records — makes a one-hop cycle
-- terminate immediately instead of looping.
--
-- ── WHY `depth < 64` IS WRITTEN OUT AND IS NOT A STYLE CHOICE ─────────────────────────────────
--
-- CockroachDB has no `CYCLE` clause. This predicate is the ONLY cycle guard the walk has. A row
-- at depth 64 exists if and only if the recursion stopped at the bound, which is what makes
-- `truncated` exact in the depth direction and what `0038`'s `depth_truncation` half of
-- `truncation_is_declared` relies on.
--
-- ── THE 512-ANCESTOR RULE, AND WHAT TRUNCATION KEEPS ──────────────────────────────────────────
--
-- Realistic ancestry is 1-20 events. Above 512 the array is capped. Which 512 survive is not
-- arbitrary and is not "the first ones the optimizer produced": they are ordered by
-- `severity_gate DESC, occurred_at DESC, event_id`, so **truncation keeps the worst and the most
-- recent**, and `max_severity` is computed over the WHOLE walk rather than over the surviving
-- 512, so capping the array can never lower the scalar the gate reads.
--
-- `truncated` is declared at `total >= 512`, not `> 512`. A complete closure of exactly 512 and a
-- truncated one holding its first 512 are the same row and no CHECK can separate them, so the
-- writer resolves the ambiguity toward "incomplete". Over-declaring incompleteness costs an
-- `ancestry_complete = false` on an MCP aggregate. Under-declaring it is the failure that column
-- exists to prevent.
--
-- NOT DONE HERE, AND SAID PLAINLY: §5.4 also requires that an overflow SPILL to a side table and
-- write a silence-ledger row. Neither the spill table nor the silence write is in band 0032-0039
-- and neither is in this statement. What this statement guarantees is that the overflow is
-- DECLARED — `truncated = true` — so no downstream reader can mistake a capped ancestry for a
-- complete one while the spill is being built.
--
-- ── WHY AN INFERRED EDGE CANNOT REACH THIS STATEMENT'S OUTPUT ─────────────────────────────────
--
-- The base case filters `b.state = 'active'`, and 0037's `inference_never_blocks` makes
-- `basis = 'inferred_semantic' AND state = 'active'` an unrepresentable row (23514). So an
-- inferred edge can never enter the walk, can never contribute an event to `ancestor_events`, and
-- can never raise `max_severity`. That chain — CHECK, then filter, then scalar — is MI13's whole
-- mechanism, and `tests/integration/schema/test_mi_blame.py` asserts it end to end rather than
-- asserting the CHECK alone.
--
-- Symmetrically, MI14's `model_cannot_arm` on `mainline.event` is what stops a model-rated
-- severity from arming through `max(ev.severity_gate)` below: a `model_rated` event cannot carry
-- `severity_gate >= 4`, so it cannot band this closure to `blood_major` or `blood_fatal`.
--
-- ── CONCURRENCY ───────────────────────────────────────────────────────────────────────────────
--
-- Two projectors racing on the same clause version both read generation N and both attempt N+1.
-- One wins; the other gets `23505` on `clause_blame_closure_pk`, or `40001` under SERIALIZABLE.
-- That is the intended resolution and it needs no lock — CockroachDB has no advisory locks and
-- this statement takes none. `40001` is retryable; `23505` means "someone else already projected
-- this generation" and the caller should re-read rather than retry blindly.
--
-- ── VERIFIED, AND THE FALLBACK IF THAT EVER CHANGES ───────────────────────────────────────────
--
-- The construct that is more than routine is `WITH RECURSIVE … INSERT INTO … SELECT` — a
-- recursive CTE feeding a top-level INSERT. It was EXECUTED, as written, against a live
-- CockroachDB CCL v26.2.5 on 2026-08-10 by
-- `tests/integration/schema/test_mi_blame.py::test_the_writer_projects_a_real_blame_dag`, over a
-- three-generation event DAG, and it produced the correct closure: three ancestors,
-- `max_severity = 5` from a fatality two hops away, `virulence = blood_fatal`, `depth = 2`,
-- `truncated = false`. A second execution appended generation 1 rather than overwriting
-- generation 0.
--
-- The measured plan is in `queries/EXPLAIN-ASSERTIONS.md`. The base case is a single constrained
-- scan of `blame_edge@by_clause_commit`; `uniq` is a lookup join on `event@event_pk`; `nextgen`
-- is a reverse scan of `clause_blame_closure@clause_blame_closure_pk` with `limit: 1`; and
-- `fk_version` shows up as an anti-lookup-join constraint check, which is the composite FK doing
-- its job.
--
-- If a later version refuses the combination, the fallback costs the projector one extra round
-- trip and nothing else: run everything down to and including the final `SELECT` as a read, then
-- issue the `INSERT … VALUES` with bound parameters inside the same transaction. The
-- derivations, the ordering, the caps and the banding are unchanged; only the transport moves.
--
-- NOTE FOR THE CALLER'S DRIVER. `$1` and `$2` each appear FOUR times, because deriving `site_id`
-- and `closure_gen` inside the statement is what stops a caller supplying either (P2). A driver
-- that speaks the PostgreSQL numbered form (asyncpg, a server-side PREPARE) binds four values.
-- A driver that speaks positional `%s` (psycopg) needs one value per OCCURRENCE — ten of them.

WITH RECURSIVE anc (event_id, depth) AS (
    -- BASE CASE: the clause version's own blame edges. ACTIVE only — this is where MI13 bites.
    SELECT b.event_id, 0
      FROM mainline.blame_edge AS b
     WHERE b.clause_uuid = $1
       AND b.commit_id   = $2
       AND b.state       = 'active'
  UNION                       -- UNION, not UNION ALL: collapses diamond ancestry
    -- RECURSION: walk the event DAG upward, child → parent.
    SELECT e.parent_event_id, a.depth + 1
      FROM anc AS a
      JOIN mainline.event_edge AS e ON e.child_event_id = a.event_id
     WHERE a.depth < 64      -- explicit end condition; CockroachDB has no CYCLE clause
),
walk AS (
    -- max(depth) over EVERY row of the walk, not over the de-duplicated events: a row at
    -- depth 64 is the signal that the recursion stopped at its bound.
    SELECT coalesce(max(a.depth), 0)::INT4 AS max_depth FROM anc AS a
),
uniq AS (
    -- De-duplicate to one row per ancestral event and pick up the severity the gate reads.
    -- `IN` against the walk rather than a JOIN, so the event table is keyed once per event.
    SELECT ev.event_id, ev.severity_gate, ev.occurred_at
      FROM mainline.event AS ev
     WHERE ev.event_id IN (SELECT a.event_id FROM anc AS a)
),
tally AS (
    -- max_severity is computed over the WHOLE ancestry, before any cap is applied.
    SELECT count(*)::INT8 AS total,
           coalesce(max(u.severity_gate), 0)::INT2 AS max_sev
      FROM uniq AS u
),
ranked AS (
    -- Truncation keeps the WORST and the MOST RECENT, never an arbitrary prefix.
    SELECT u.event_id,
           row_number() OVER (
             ORDER BY u.severity_gate DESC, u.occurred_at DESC, u.event_id
           ) AS rn
      FROM uniq AS u
),
kept AS (
    SELECT r.event_id FROM ranked AS r WHERE r.rn <= 512
),
ver AS (
    -- site_id has a SOURCE. An absent row here inserts nothing — see the zero-row contract.
    SELECT cv.site_id
      FROM mainline.clause_version AS cv
     WHERE cv.clause_uuid = $1
       AND cv.commit_id   = $2
),
nextgen AS (
    -- Through the view, never the table (DM-9). NULL ⇒ this is generation zero.
    SELECT coalesce(max(c.closure_gen) + 1, 0)::INT8 AS closure_gen
      FROM mainline.clause_blame_current AS c
     WHERE c.clause_uuid  = $1
       AND c.as_of_commit = $2
)
INSERT INTO mainline.clause_blame_closure
            (clause_uuid, as_of_commit, closure_gen, site_id,
             ancestor_events, ancestor_count, max_severity, virulence,
             depth, truncated, computed_by, projector_ver)
SELECT $1,
       $2,
       g.closure_gen,
       v.site_id,
       coalesce((SELECT array_agg(k.event_id ORDER BY k.event_id) FROM kept AS k),
                ARRAY[]::UUID[]),
       (SELECT count(*)::INT4 FROM kept AS k2),
       t.max_sev,
       (CASE WHEN t.max_sev >= 5 THEN 'blood_fatal'
             WHEN t.max_sev >= 4 THEN 'blood_major'
             WHEN t.max_sev >= 3 THEN 'serious'
             ELSE                      'routine'
        END)::mainline.virulence_class,
       w.max_depth,
       (t.total >= 512 OR w.max_depth >= 64),
       $3,
       $4
  FROM tally AS t, walk AS w, ver AS v, nextgen AS g
RETURNING clause_uuid, as_of_commit, closure_gen, site_id,
          ancestor_count, max_severity, virulence, depth, truncated;
