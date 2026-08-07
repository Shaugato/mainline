-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- STAND-IN for the repository-spine DDL that migration 0207 reads.
--
-- THIS IS NOT A MIGRATION AND MUST NEVER BECOME ONE.  It lives under a test
-- directory owned by worker W2 and is applied only by that worker's integration
-- suite.  `mainline.commit_obj`, `commit_edge`, `doc`, `clause` and
-- `clause_version` belong to the schema/kernel lead in migration band
-- 0001-0171; at the time this file was written those migrations had not landed,
-- and 0207 is a VIEW over four of those tables, so there was nothing to apply it
-- against.
--
-- The columns below are transcribed from ARCHITECTURE.md §5.2 and §5.3, limited
-- to what 0207 and `mainline_domain.registry.sql` actually read, plus the
-- primary and foreign keys needed for the rows to be legal.  Deliberately
-- omitted: FAMILY clauses, the inverted and trigram indexes, the vector sidecar,
-- and every projection trigger — none of which the view touches, and all of
-- which are somebody else's file.
--
-- The suite reports `spine_is_standin = True` in its header when it applies
-- this, and `_directrix_support.spine_migrations()` looks for the real
-- migrations first.  A green run against a stand-in is a weaker claim than a
-- green run against the deployed schema, and the report says which one happened
-- rather than leaving a reader to assume the stronger one.

CREATE SCHEMA IF NOT EXISTS mainline;

CREATE TYPE mainline.control_delta AS ENUM
  ('introduce', 'strengthen', 'restate', 'weaken', 'remove');

CREATE TABLE mainline.commit_obj (
  commit_id      BYTES  NOT NULL,
  site_id        UUID   NOT NULL,
  gen            INT8   NOT NULL,
  ref_name       STRING NOT NULL,
  committed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  author_sub     STRING NOT NULL,
  message        STRING NOT NULL,
  envelope       JSONB  NOT NULL,
  envelope_bytes BYTES  NOT NULL,
  sig            BYTES  NULL,
  PRIMARY KEY (commit_id),
  CONSTRAINT id_is_sha256 CHECK (length(commit_id) = 32),
  CONSTRAINT gen_positive CHECK (gen >= 0),
  INDEX by_branch_gen (site_id, ref_name, gen) STORING (committed_at, author_sub)
);

CREATE TABLE mainline.commit_edge (
  child_id   BYTES NOT NULL,
  parent_ord INT2  NOT NULL,
  parent_id  BYTES NOT NULL,
  parent_gen INT8  NOT NULL,
  PRIMARY KEY (child_id, parent_ord),
  INDEX desc_walk (parent_id, child_id),
  CONSTRAINT fk_child  FOREIGN KEY (child_id)  REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_parent FOREIGN KEY (parent_id) REFERENCES mainline.commit_obj (commit_id)
);

CREATE TABLE mainline.doc (
  doc_id           UUID   NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id          UUID   NOT NULL,
  doc_code         STRING NOT NULL,
  title            STRING NOT NULL,
  state            STRING NOT NULL DEFAULT 'live'
                     CHECK (state IN ('live','superseded','withdrawn')),
  open_token_count INT4   NOT NULL DEFAULT 0,
  superseded_by    UUID[] NULL,
  UNIQUE (site_id, doc_code),
  CONSTRAINT tokens_nonneg CHECK (open_token_count >= 0),
  CONSTRAINT no_orphan_controls CHECK (state <> 'superseded' OR open_token_count = 0)
);

CREATE TABLE mainline.clause (
  clause_uuid    UUID   NOT NULL PRIMARY KEY,
  site_id        UUID   NOT NULL,
  birth_commit   BYTES  NOT NULL REFERENCES mainline.commit_obj (commit_id),
  activity_root  STRING NOT NULL,
  head_commit    BYTES  NULL,
  retired_commit BYTES  NULL,
  INDEX by_site_activity (site_id, activity_root)
);

CREATE TABLE mainline.clause_version (
  clause_uuid    UUID   NOT NULL,
  gen            INT8   NOT NULL,
  commit_id      BYTES  NOT NULL,
  site_id        UUID   NOT NULL,
  doc_id         UUID   NOT NULL REFERENCES mainline.doc (doc_id),
  activity_root  STRING NOT NULL,
  parent_version BYTES  NULL,
  ordinal        INT8   NOT NULL,
  printed_label  STRING NULL,
  raw_text       STRING NOT NULL,
  canon_text     STRING NOT NULL,
  canon_version  INT2   NOT NULL,
  canon_sha256   BYTES  NOT NULL,
  anchor_set     STRING[] NOT NULL,
  cat_key        STRING NULL,
  cat_json       JSONB  NULL,
  cat_confidence STRING NOT NULL DEFAULT 'ok'
                   CHECK (cat_confidence IN ('ok','low','opaque')),
  control_delta  mainline.control_delta NOT NULL,
  delta_basis    STRING NOT NULL
                   CHECK (delta_basis IN ('lattice','lattice+model','abstain_to_weaken','human')),
  delta_model    STRING NULL,
  delta_prompt_version STRING NULL,
  blood_root     BYTES   NOT NULL,
  blood_peaks    BYTES[] NOT NULL,
  blood_size     INT8    NOT NULL,
  sev_max        INT2    NOT NULL DEFAULT 0,
  PRIMARY KEY (clause_uuid, gen, commit_id),
  UNIQUE (clause_uuid, commit_id),
  CONSTRAINT fk_clause FOREIGN KEY (clause_uuid) REFERENCES mainline.clause (clause_uuid),
  CONSTRAINT fk_commit FOREIGN KEY (commit_id)  REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT sev_range CHECK (sev_max BETWEEN 0 AND 5),
  INDEX by_commit (site_id, commit_id) STORING (clause_uuid, canon_sha256, control_delta, sev_max),
  INDEX by_digest (site_id, canon_sha256),
  INDEX by_doc    (doc_id, gen)
);
