-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The prefix columns of a C-SPANN index are not metadata, they select the tree that is searched, so MI25's projection principle has to reach one hop upstream of the gate scalar and land on the index partition itself.
--
-- migration:  0041_event_cue_embedding
-- band:       0040-0046z · recall/recall-ddl-triggers · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- invariants: MI25 is instantiated here on the INDEX PARTITION rather than on a gate scalar.
-- proposes:   MI31 — "the vector-index prefix columns are projections of the parent cue, never
--             inputs"; catalogue entry owed to `dm-runner` (mi_catalogue.yaml).
-- source:     ARCHITECTURE.md §5.4 · docs/leads/recall.md D1 · §6.3
-- requires:   0040 mainline.event_cue
-- sqlstate:   P0001 via 0114/0138 when the parent cue is absent
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- THE TABLE IS CREATED EMPTY AND THE VECTOR INDEX IS DECLARED INLINE. Both halves of that
-- sentence are load-bearing on CockroachDB v26.2: `CREATE VECTOR INDEX` on a table that already
-- holds rows blocks mutations until the backfill completes and requires `sql_safe_updates` off,
-- and `IMPORT INTO` is unsupported on a vector-indexed table entirely (see 0088 for the bulk
-- path). Creating the index at t=0 on an empty table sidesteps both.
--
-- WHY THE PREFIX COLUMNS ARE PROJECTIONS (recall D1 — the headline of this domain).
-- C-SPANN maintains a SEPARATE K-means tree per distinct prefix value. `(site_id, scope_id,
-- facet)` therefore does not filter a result set — it SELECTS THE TREE THAT IS SEARCHED. An
-- inserter that chooses these three values chooses reachability. A fatality cue written into
-- the wrong tree is not "ranked lower": it is unreachable forever, by every arm, with no
-- refusal anywhere in the system and no row anywhere that is wrong. TRAPPOINT's P2 —
-- a column a gate reads is written by a trigger from an authoritative source, never by the
-- inserter — therefore has to reach one hop further than the gate scalar: it has to reach the
-- index partition. `mainline.fn_cue_prefix_project` (0114) overwrites all three from
-- `mainline.event_cue` on every insert and RAISEs P0001 when there is no parent cue.
--
-- HONEST LIMIT, stated where it lives rather than in a slide: with the trigger dropped, a
-- forged prefix is accepted — this weld's refusal depth is 1, not 2. See
-- tests/integration/recall_schema/test_unweld.py::test_uw02_prefix_projection_depth_is_one,
-- which asserts that fact rather than hiding it, and the composite-FK strengthening it names.

CREATE TABLE mainline.event_cue_embedding (
  cue_id      UUID   NOT NULL REFERENCES mainline.event_cue (cue_id),
  site_id     UUID   NOT NULL,                  -- prefix 1  ← PROJECTED (0114)
  scope_id    UUID   NOT NULL,                  -- prefix 2  ← PROJECTED (0114)
  facet       STRING NOT NULL,                  -- prefix 3  ← PROJECTED (0114)
  embed_model STRING NOT NULL,
  index_gen   STRING NOT NULL,
  emb         VECTOR(1024) NOT NULL,
  CONSTRAINT event_cue_embedding_pk PRIMARY KEY (cue_id),
  VECTOR INDEX cue_scoped_idx (site_id, scope_id, facet, emb vector_cosine_ops)
);
