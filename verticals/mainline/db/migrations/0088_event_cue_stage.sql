-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- migration:  0088_event_cue_stage
-- domain:     recall
-- statements: 1
-- invariants: MI25 (the projection principle: the bulk path may not bypass the prefix weld),
--             MI31 (proposed, see 0041)
-- source:     BUILD_PLAN K4 ("both ingestion paths built and measured") · CockroachDB v26.2
--             vector-index limitation: IMPORT INTO is unsupported on vector-indexed tables
-- requires:   0001 CREATE SCHEMA mainline
-- sqlstate:   —
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
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
-- the trigger. It remains available as a measured fallback (`dm-recall-tables` owns the
-- `.fallback.sql` siblings) and if it is ever used, the load is a privileged, attested
-- operation, not a routine one.

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
