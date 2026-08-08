-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: C-SPANN keeps a separate K-means tree per distinct prefix value, so `(site_id, scope_id, facet)` does not filter the answer — it chooses which tree is searched — and an inserter that supplies those three columns chooses reachability; this function overwrites all three from the parent cue on every insert.
--
-- migration:  0114_fn_cue_prefix_project
-- band:       0110-0114z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- proposes:   MI31 — "the vector-index prefix columns are projections of the parent cue, never
--             inputs; a vector with no parent cue is refused"
-- source:     docs/leads/recall.md D1 · ARCHITECTURE.md §5.4, §5.11, §6.3
-- requires:   0040 mainline.event_cue
-- provides:   mainline.fn_cue_prefix_project() — welded to mainline.event_cue_embedding by 0138
-- companion:  0114a_fn_cue_coarse_project.sql — the coarse sidecar's projector. See
--             PLATFORM NOTE 2 for why the mechanism is two functions and not one, and
--             THE SPLIT below for why it is now two files.
-- sqlstate:   P0001
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
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
-- whatever the inserter supplied, on every insert, and RAISEs when the parent is absent —
-- because a vector with no cue cannot be placed at all, and silently defaulting it somewhere is
-- the same defect with better manners.
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
-- ── PLATFORM NOTE 1 · `(NEW).col` FOR READS ──────────────────────────────────────────────────
-- CockroachDB's PL/pgSQL requires `OLD` and `NEW` to be **wrapped in parentheses when accessing
-- column names** — a documented known limitation on the v26.2 Triggers page, whose own examples
-- read `(NEW).wage` and assign `NEW.wage := (NEW).wage + 5`. ARCHITECTURE §5.11's trigger bodies
-- are written in the unparenthesised PostgreSQL style throughout; every read below is therefore
-- parenthesised and every assignment target is not. Assignment targets are deliberately left
-- bare because that is the form the platform's own example uses. This is a transcription
-- correction, not a design change, and it applies to every trigger in the deployment.
--
-- ── PLATFORM NOTE 2 · WHY TWO FUNCTIONS AND NOT ONE ──────────────────────────────────────────
-- The obvious shape is one function welded to both sidecars, dispatching on `TG_TABLE_NAME`.
-- `TG_TABLE_NAME` IS supported and a trigger function MAY be reused across tables (both
-- documented). The problem is the branch bodies: such a function must contain
-- `NEW.severity_gate := …`, and `event_cue_embedding` HAS NO `severity_gate` COLUMN. CockroachDB
-- compiles PL/pgSQL through the optimizer rather than interpreting it statement-by-statement at
-- runtime, and `NEW` is bound to the trigger table's row type — so a reference in a branch that
-- can never execute is still plausibly resolved when the trigger is created, and the migration
-- that is this domain's headline would fail to apply.
--
-- **This is UNVERIFIED on the target platform** — the docs do not state when a trigger function
-- body is type-checked, and no cluster was reachable from the machine this was written on to
-- settle it. So it is not bet on. Two functions, each referencing only columns that exist on its
-- own table, are correct under BOTH answers; one function is correct only under the friendlier
-- one. PL-3: no unproven capability on a dated path. The mechanism, the trigger names, the
-- SQLSTATE and the diagnosis are unchanged — `fn_cue_prefix_project` keeps the name D1 gives it
-- and keeps the prefixed sidecar, which is the half the name is about.
--
-- ── THE SPLIT (migration reconciliation, 2026-08-08) ─────────────────────────────────────────
-- PLATFORM NOTE 2 decided there would be two FUNCTIONS. It did not decide there would be one
-- FILE, and for a while there was: this file carried both `CREATE FUNCTION`s, which made it a
-- two-statement migration. The runner does not wrap a file body in a transaction, because
-- CockroachDB DDL is not transactional across statements — so a two-statement file that fails on
-- its second leaves the schema half-applied with the version unrecorded, and the `dirty` marker
-- names a FILE rather than a STATEMENT. Here that is not academic: the half-applied state is
-- exactly "the prefixed sidecar's projector exists and the coarse sidecar's does not", which
-- 0138a's header shows is the state in which a severity-5 sweep hit stops blocking.
-- `fn_cue_coarse_project` now lives in `0114a_fn_cue_coarse_project.sql` — a band-overflow
-- suffix inside recall's own `0110`-`0114z` grant (MR-5), not a borrowed neighbour's number.

CREATE FUNCTION mainline.fn_cue_prefix_project() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  cue_site  UUID;
  cue_scope UUID;
  cue_facet STRING;
BEGIN
  SELECT c.site_id, c.scope_id, c.facet
    INTO cue_site, cue_scope, cue_facet
    FROM mainline.event_cue c
   WHERE c.cue_id = (NEW).cue_id;

  IF cue_site IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no parent cue — cannot place a vector in a prefix tree';
  END IF;

  NEW.site_id  := cue_site;
  NEW.scope_id := cue_scope;
  NEW.facet    := cue_facet;
  RETURN NEW;
END $$;
