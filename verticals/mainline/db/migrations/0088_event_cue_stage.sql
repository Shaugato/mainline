-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: Rows leave this table by INSERT into `event_cue_embedding`, so the bulk path fires the same projection trigger the live path does; the alternative shape — IMPORT INTO the indexed table, then build the index — is rejected precisely because it is the path that bypasses the weld.
--
-- migration:  0088_event_cue_stage
-- band:       0080-0089z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- domain:     recall
-- statements: 1
-- invariants: MI25 (the projection principle: the bulk path may not bypass the prefix weld),
--             MI31 (proposed, see 0041)
-- source:     BUILD_PLAN K4 ("both ingestion paths built and measured") · CockroachDB v26.2
--             vector-index limitation: IMPORT INTO is unsupported on vector-indexed tables
-- requires:   0001a CREATE SCHEMA mainline (RENDERED; template 0001_schemas.sql.j2)
-- sqlstate:   —
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction.
--
-- AN INDEX-FREE MIRROR OF `event_cue_embedding`, FOR THE BULK PATH ONLY. CockroachDB v26.2
-- cannot `IMPORT INTO` a table that carries a vector index, and the documented remedy is
-- import-then-index. This table is the "import" half: it has no vector index and no foreign
-- keys, so a corpus load is a bulk import rather than a million single-row round trips.
--
-- THE PROMOTION STATEMENT IS THE POINT — and it is why staging does not open a hole in the
-- weld. Rows leave this table by:
--
--   INSERT INTO mainline.event_cue_embedding
--        (cue_id, site_id, scope_id, facet, embed_model, index_gen, emb)
--   SELECT s.cue_id, s.site_id, s.scope_id, s.facet, s.embed_model, s.index_gen, s.emb
--     FROM mainline.event_cue_stage s
--    WHERE s.cue_id > $cursor
--    ORDER BY s.cue_id
--    LIMIT $batch;
--
-- which is an INSERT, so `cue_prefix_project_embedding` (0138) fires on every staged row and
-- rewrites `site_id`, `scope_id` and `facet` from the parent cue exactly as it does on the live
-- path — and RAISEs P0001 on any staged row whose cue was never written. A bulk loader
-- therefore cannot place a vector in a tree of its own choosing either. There is no path into
-- the prefixed sidecar that does not pass through the projection.
--
-- The alternative shape — `IMPORT INTO event_cue_embedding` then `CREATE VECTOR INDEX` — is
-- rejected for the production corpus for the same reason: it is exactly the path that bypasses
-- the trigger. It remains available as a measured fallback, and if it is ever used the load is a
-- privileged, attested operation, not a routine one. The fallback DDL no longer sits beside the
-- primary in the apply path: MR-5 forbids a second dot in a migration filename (a
-- `.fallback.sql` stem makes the WHOLE directory undiscoverable) and a variant next to the
-- primary is one glob away from being applied. Capability variants live in
-- verticals/mainline/db/ext/<topic>/ behind a render-time switch (kernel D5).

CREATE TABLE mainline.event_cue_stage (
  cue_id      UUID   NOT NULL,
  site_id     UUID   NOT NULL,                  -- staged value; REWRITTEN on promotion
  scope_id    UUID   NOT NULL,                  -- staged value; REWRITTEN on promotion
  facet       STRING NOT NULL,                  -- staged value; REWRITTEN on promotion
  embed_model STRING NOT NULL,
  index_gen   STRING NOT NULL,
  emb         VECTOR(1024) NOT NULL,
  staged_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT event_cue_stage_pk PRIMARY KEY (cue_id)
);
