-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI15, MI26
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: The blame closure's only cycle guard is an explicit `depth < 64` end condition — CockroachDB has no CYCLE clause — so a one-hop cycle in this table would not error, it would silently consume the entire depth budget and return a TRUNCATED ancestry that looks exactly like a complete one, which is the single worst failure mode the closure has.
--
-- migration:  0034_event_edge
-- band:       0032-0039 · dm-blame · AUTHORED (activity taxonomy, events, the severity record),
--             allocated by verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.4 (verbatim shape; constraints named per DM-10, index inline per DM-6)
-- requires:   0033 mainline.event
-- consumed:   the recursive CTE in queries/closure_write.sql (0038's writer) walks THIS table
-- sqlstate:   23514 on relation_closed / no_self_edge; 23503 on fk_child_event / fk_parent_event;
--             23505 on event_edge_pk
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- THE EVENT DAG. `blame_edge` (0037) says which clause an event wrote; THIS table says which
-- earlier events an event descends from, and the closure's recursive walk is over both. It is
-- what makes the product's claim transitive: a permit that weakens a clause written by a 2019
-- near-miss is refused because that near-miss is `recurrence_of` a 2004 fatality, and the
-- fatality's virulence is inherited through this edge rather than re-argued.
--
-- THREE RELATIONS, THREE DIFFERENT CLAIMS ABOUT THE PAST:
--
--   recurrence_of  the same thing happened again. The strongest form: it means the control that
--                  was written last time did not hold, which is the fact a regulator opens with.
--   precursor_of   this earlier event was a warning that preceded the later one. Directional and
--                  contestable, which is why it is a typed edge and not prose in a narrative.
--   supersedes     a later investigation replaced an earlier finding about the same occurrence.
--
-- `supersedes` does NOT delete anything, here or anywhere. The superseded event stays, its blame
-- edges stay, and the closure records which generation it was believed in. An edge that erases
-- its predecessor manufactures the plaintiff's best exhibit — a record that changed and cannot
-- say what it used to say.
--
-- `no_self_edge` IS STRICTLY STRONGER THAN §5.4 AND IT IS LOAD-BEARING, NOT TIDY.
-- The closure writer is:
--
--     WITH RECURSIVE anc(event_id, depth) AS (
--         SELECT b.event_id, 0 FROM mainline.blame_edge b WHERE …
--       UNION
--         SELECT e.parent_event_id, a.depth + 1
--           FROM anc a JOIN mainline.event_edge e ON e.child_event_id = a.event_id
--          WHERE a.depth < 64)
--
-- `UNION` (not `UNION ALL`) collapses diamond ancestry, so a self-edge does not loop forever —
-- it terminates immediately, having produced the same row at depth 1. The damage is subtler and
-- worse than a hang: for a genuine cycle of length two or three the walk burns depth budget on
-- repeats and, on a deep ancestry, trips the 512-ancestor truncation for a reason that has
-- nothing to do with the ancestry actually being large. `truncated = true` then means something
-- other than what every downstream `ancestry_complete` flag says it means. A one-column CHECK
-- removes the cheapest way to produce that state. Longer cycles are the ingest validator's
-- problem and the closure's `depth` cap is the backstop; this refuses the trivial case at the
-- only place it can be refused for every writer.
--
-- The `up` index is the walk's access path: the recursion joins on `child_event_id` (the primary
-- key prefix, already covered) and the descendant direction — "what did this event go on to
-- cause" — reads `parent_event_id` first. Both directions of the DAG are indexed because the
-- console renders both and neither may fall back to a scan on the gate path.

CREATE TABLE mainline.event_edge (
  child_event_id  UUID   NOT NULL,
  parent_event_id UUID   NOT NULL,
  relation        STRING NOT NULL,
  CONSTRAINT event_edge_pk PRIMARY KEY (child_event_id, parent_event_id, relation),
  CONSTRAINT fk_child_event FOREIGN KEY (child_event_id)
    REFERENCES mainline.event (event_id),
  CONSTRAINT fk_parent_event FOREIGN KEY (parent_event_id)
    REFERENCES mainline.event (event_id),
  CONSTRAINT relation_closed CHECK (relation IN
    ('recurrence_of', 'precursor_of', 'supersedes')),
  CONSTRAINT no_self_edge CHECK (child_event_id <> parent_event_id),
  INDEX up (parent_event_id, child_event_id)
);
