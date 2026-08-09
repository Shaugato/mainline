-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · queries/closure_read.sql
-- "WHICH CLAUSES INHERIT INCIDENT E?" — the containment lookup, through the view and only the view.
--
-- MI: MI26, MI25
-- I: I05, I02
-- Owner:      datamodel/dm-blame (band 0032-0039)
-- Source:     ARCHITECTURE.md §5.4 · docs/leads/datamodel.md DM-9
-- Reads:      mainline.clause_blame_current — and nothing else, ever
-- Plan:       stated, with its honest cost, in verticals/mainline/db/queries/EXPLAIN-ASSERTIONS.md
--
-- ── PARAMETERS ────────────────────────────────────────────────────────────────────────────────
--
--   $1  site_id   UUID   the tenancy scope; the leading column of `cbc_anc`
--   $2  event_id  UUID   the incident whose descendants are being asked for
--
-- ── WHAT THIS QUERY ANSWERS, AND WHY IT IS THE PRODUCT'S OWN QUESTION ─────────────────────────
--
-- It is the reverse of a blame pointer. A blame pointer says "this clause was written by that
-- incident"; this says "given the incident, show me every clause version now answerable to it".
-- It is what the propagation console renders, what the fleet-wide "who else has this control"
-- sweep runs, and what a severity revision must enumerate before it can extinguish anything.
--
-- ── WHY IT NAMES THE VIEW AND NOT THE TABLE (DM-9) ────────────────────────────────────────────
--
-- `mainline.clause_blame_closure` is append-only and generation-versioned. Reading it directly
-- and forgetting `max(closure_gen)` returns a real row from a superseded generation — a
-- generation computed with LESS ancestry, so a LOWER `max_severity`. There is no error and no
-- warning. `mainline.clause_blame_current` carries the discipline once, and
-- `scripts/grep_closure_readpath.py` fails CI on any file that goes around it.
--
-- The containment predicate is applied to the CURRENT generation's array, which is the only
-- correct reading of the question: a clause whose generation 2 held incident E and whose
-- generation 3 does not (because the edge was refuted) is NOT a descendant of E today, and this
-- query is right to omit it.
--
-- ── THE COST, STATED HERE AND NOT ONLY IN THE PLAN FILE ───────────────────────────────────────
--
-- §5.4 calls this "one index lookup". Through the view it is not, and the reason is a correctness
-- property rather than an optimizer weakness: `ancestor_events @> …` filters on a column that is
-- neither in the `DISTINCT ON` list nor determined by it, so the predicate CANNOT be pushed below
-- the de-duplication — pushing it there would surface a superseded generation that satisfies the
-- predicate when the current one does not. The inverted index `cbc_anc` is therefore not
-- traversed on this path at present. EXPLAIN-ASSERTIONS.md states exactly what CI asserts
-- instead, and writes out the accelerated two-stage form — a prefilter on the table's inverted
-- index, re-decided by this view — together with what adopting it would cost DM-9. It is
-- deliberately NOT adopted here: at the scale this system runs at, one relation as the read path
-- is worth more than one index traversal, and the moment that stops being true it is a change
-- with an owner and a review rather than a query somebody quietly rewrote.

SELECT c.clause_uuid,
       c.as_of_commit,
       c.closure_gen,
       c.max_severity,
       c.virulence,
       c.ancestor_count,
       c.truncated
  FROM mainline.clause_blame_current AS c
 WHERE c.site_id = $1
   AND c.ancestor_events @> ARRAY[$2::UUID];
