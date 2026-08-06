-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0114_fn_cue_prefix_project
-- domain:     recall
-- statements: 1
-- invariants: MI25 (the projection principle, instantiated on the index partition)
-- proposes:   MI31 — "the vector-index prefix columns are projections of the parent cue, never
--             inputs; a vector with no parent cue is refused"
-- source:     docs/leads/recall.md D1 · ARCHITECTURE.md §5.4, §5.11, §6.3
-- requires:   0040 event_cue · 0041 event_cue_embedding · 0042 event_cue_coarse · 0033 event
-- sqlstate:   P0001
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═══ THE HEADLINE OF THIS DOMAIN ═══
--
-- C-SPANN maintains a SEPARATE K-means tree per distinct prefix value. That single verified
-- platform fact turns `(site_id, scope_id, facet)` from metadata into topology: those three
-- columns do not filter the answer, THEY CHOOSE WHICH TREE IS SEARCHED. An inserter that
-- supplies them chooses reachability.
--
-- Consider the failure that motivates this file. A cue for a fatality is written with a
-- scope_id belonging to a neighbouring activity — through a bug, a stale taxonomy version, a
-- retry that reused a variable, or deliberately. Every subsequent arm queries the trees for the
-- permit's own ancestry. The fatality's tree is not among them. The vector is never compared
-- against anything. No query fails. No constraint is violated. No row is wrong. The silence
-- ledger records nothing, because nothing was retrieved and rejected — the candidate never
-- existed. The system reports a clean recall and the permit merges.
--
-- That is why P2 — *the column a gate reads is written by a trigger from an authoritative
-- source, never by the inserter* — has to reach one hop upstream of the gate scalar and land on
-- the index partition itself. There is exactly one authoritative statement of which tree a cue
-- belongs to, and it is the parent row in `mainline.event_cue`. This function copies it over
-- whatever the inserter supplied, on every insert, on both sidecars, and RAISEs when the parent
-- is absent — because a vector with no cue cannot be placed at all, and silently defaulting it
-- somewhere is the same defect with better manners.
--
-- ON THE COARSE SIDECAR. `event_cue_coarse` has one deliberately constant prefix (`tenant_id`),
-- so its tree placement is not forgeable — but its `severity_gate` is, and that column decides
-- whether a sweep hit blocks (a sweep hit is never blocking unless severity_gate = 5). It is
-- therefore projected from `mainline.event` through `event_cue.event_id`. `tenant_id` is left
-- alone: DM-3 makes `mainline.site` its authoritative source, and forging a projection from a
-- table this domain does not own would be worse than naming the gap.
--
-- WHAT THIS FUNCTION DOES NOT DO, said here rather than discovered later: with the trigger
-- dropped, a forged prefix is accepted. The weld's refusal depth is 1. The available
-- strengthening is a composite FK `(cue_id, site_id, scope_id, facet)` onto a matching UNIQUE
-- on `event_cue` with ON UPDATE RESTRICT, which would make the forgery 23503 with no trigger at
-- all; it is not applied here because §5.4's shape is shared with `dm-recall-tables` and an
-- unrequested FK change is a cross-domain break. See
-- tests/integration/recall_schema/test_unweld.py::test_uw02_prefix_projection_depth_is_one,
-- which asserts the current depth honestly.
--
-- Style (§5.11): PL/pgSQL, row-level, no FOR..IN, no FOREACH, no EXECUTE, no PERFORM, no CASE;
-- IF/ELSIF plus exactly one SELECT..INTO. One function serves both sidecars — CockroachDB
-- supports sharing a trigger function across tables — and dispatches on TG_TABLE_NAME because
-- the two sidecars project different columns.

CREATE FUNCTION mainline.fn_cue_prefix_project() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  cue_site  UUID;
  cue_scope UUID;
  cue_facet STRING;
  cue_sev   INT2;
BEGIN
  SELECT c.site_id, c.scope_id, c.facet, e.severity_gate
    INTO cue_site, cue_scope, cue_facet, cue_sev
    FROM mainline.event_cue c
    JOIN mainline.event e ON e.event_id = c.event_id
   WHERE c.cue_id = NEW.cue_id;

  IF cue_site IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no parent cue — cannot place a vector in a prefix tree';
  END IF;

  IF TG_TABLE_NAME = 'event_cue_embedding' THEN
    NEW.site_id  := cue_site;
    NEW.scope_id := cue_scope;
    NEW.facet    := cue_facet;
  ELSIF TG_TABLE_NAME = 'event_cue_coarse' THEN
    NEW.severity_gate := cue_sev;
  ELSE
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: fn_cue_prefix_project welded to an unknown table';
  END IF;

  RETURN NEW;
END $$;
