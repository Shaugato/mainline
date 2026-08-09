-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
--
-- TEST FIXTURE. THIS IS NOT A MIGRATION AND MUST NEVER BE APPLIED TO ANYTHING REAL.
--
-- `verticals/mainline/db/migrations/0072..0079` are the authoritative DDL and they are the
-- datamodel lead's exclusive territory. This file is a REDUCTION of them to the objects the
-- sequencer touches, so that the concurrency lane can stand up a disposable single-node
-- CockroachDB in a second instead of applying 120+ migrations that pull in half the schema.
--
-- THE REDUCTION IS GUARDED, NOT PROMISED. `tests/test_append_unit.py::
-- test_fixture_names_the_same_constraints_as_the_migration` reads BOTH this file and
-- `0073_ledger_leaf.sql` and fails if the constraint names diverge. That guard exists because
-- CU-2's retry predicate matches on CONSTRAINT NAME: `ledger_leaf_pkey` and `ledger_linear` are
-- an INTERFACE, renaming one is a breaking change to `mainline_sequencer.append`, and a fixture
-- that drifted from the migration would let this package's tests pass against names the
-- database does not use.
--
-- WHAT IS DELIBERATELY REDUCED, and why each reduction is safe for what these tests assert:
--
--   * `mainline.site` keeps only the columns the foreign keys need. The sequencer never reads
--     the table; it needs the FK target to exist so that `fk_site`'s 23503 is a real refusal
--     rather than a missing object's 42P01.
--   * The append-only trigger family (`fn_refuse_mutation`, band 0130-0199) is ABSENT. It is not
--     the sequencer's mechanism: this package issues no UPDATE and no DELETE against any
--     `ledger_*` table at all, and `test_batch_antijoin.py::test_no_update_against_any_ledger_table`
--     proves that from the source. The nemesis harness is where the trigger is exercised, against
--     the real migration tree.
--   * `mainline.cosignature`, `unwitnessed_debt` and `custodian_attestation` are absent: the
--     sequencer neither reads nor writes them.
--
-- Statements are separated by `;`. No statement contains a semicolon inside a literal, so a
-- naive split is safe and the loader stays four lines long.

CREATE SCHEMA IF NOT EXISTS mainline;

CREATE SCHEMA IF NOT EXISTS mainline_ops;

CREATE TABLE mainline.site (
  site_id      UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_code    STRING      NOT NULL,
  site_role    NAME        NOT NULL,
  tenant_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
  taxonomy_ver INT4        NOT NULL DEFAULT 1,
  opened_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT site_pk PRIMARY KEY (site_id),
  CONSTRAINT site_code_unique UNIQUE (site_code),
  CONSTRAINT site_role_unique UNIQUE (site_role),
  CONSTRAINT site_code_stated CHECK (site_code <> ''),
  CONSTRAINT site_code_is_lower_case CHECK (site_code = lower(site_code)),
  CONSTRAINT taxonomy_ver_positive CHECK (taxonomy_ver >= 1)
);

CREATE TABLE mainline.ledger_intake (
  entry_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_code   STRING      NOT NULL,
  entry_kind  STRING      NOT NULL,
  subject_id  UUID        NOT NULL,
  actor       STRING      NOT NULL,
  actor_kind  STRING      NOT NULL,
  payload     JSONB       NOT NULL,
  canon_bytes BYTES       NOT NULL,
  payload_ver INT2        NOT NULL,
  leaf_hash   BYTES       NOT NULL,
  is_sandbox  BOOL        NOT NULL DEFAULT false,
  hlc         DECIMAL     NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_intake_pkey PRIMARY KEY (entry_id),
  CONSTRAINT intake_site_entry_unique UNIQUE (site_code, entry_id),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT actor_kind_known
    CHECK (actor_kind IN ('human', 'agent', 'service', 'external')),
  CONSTRAINT entry_kind_stated CHECK (entry_kind <> ''),
  CONSTRAINT actor_stated CHECK (actor <> ''),
  CONSTRAINT payload_ver_positive CHECK (payload_ver >= 1),
  CONSTRAINT canon_bytes_present CHECK (length(canon_bytes) > 0),
  CONSTRAINT leaf_hash_is_sha256 CHECK (length(leaf_hash) = 32),
  INDEX by_site_hlc (site_code, hlc ASC)
);

CREATE TABLE mainline.ledger_leaf (
  site_code      STRING NOT NULL,
  seq            INT8   NOT NULL,
  entry_id       UUID   NOT NULL,
  leaf_hash      BYTES  NOT NULL,
  prev_link_hash BYTES  NOT NULL,
  link_hash      BYTES  NOT NULL,
  batch_id       UUID   NOT NULL,
  CONSTRAINT ledger_leaf_pkey PRIMARY KEY (site_code, seq),
  CONSTRAINT ledger_linear UNIQUE (site_code, prev_link_hash),
  CONSTRAINT ledger_leaf_entry_unique UNIQUE (site_code, entry_id),
  CONSTRAINT fk_intake FOREIGN KEY (site_code, entry_id)
    REFERENCES mainline.ledger_intake (site_code, entry_id),
  CONSTRAINT seq_zero_based CHECK (seq >= 0),
  CONSTRAINT leaf_hash_is_sha256 CHECK (length(leaf_hash) = 32),
  CONSTRAINT prev_link_hash_is_sha256 CHECK (length(prev_link_hash) = 32),
  CONSTRAINT link_hash_is_sha256 CHECK (length(link_hash) = 32)
);

CREATE TABLE mainline.ledger_node (
  site_code STRING NOT NULL,
  level     INT2   NOT NULL,
  idx       INT8   NOT NULL,
  hash      BYTES  NOT NULL,
  CONSTRAINT ledger_node_pkey PRIMARY KEY (site_code, level, idx),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT level_non_negative CHECK (level >= 0),
  CONSTRAINT idx_non_negative CHECK (idx >= 0),
  CONSTRAINT hash_is_sha256 CHECK (length(hash) = 32)
);

CREATE TABLE mainline.ledger_checkpoint (
  site_code        STRING      NOT NULL,
  tree_size        INT8        NOT NULL,
  root_hash        BYTES       NOT NULL,
  body             STRING      NOT NULL,
  beacon           JSONB       NOT NULL,
  log_sig          BYTES       NOT NULL,
  tsa_token        BYTES       NULL,
  s3_version       STRING      NULL,
  canon_src_sha256 BYTES       NOT NULL,
  admissible       BOOL        NOT NULL DEFAULT false,
  issued_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ledger_checkpoint_pkey PRIMARY KEY (site_code, tree_size),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT tree_size_non_negative CHECK (tree_size >= 0),
  CONSTRAINT root_hash_is_sha256 CHECK (length(root_hash) = 32),
  CONSTRAINT canon_src_is_sha256 CHECK (length(canon_src_sha256) = 32),
  CONSTRAINT body_stated CHECK (body <> ''),
  CONSTRAINT log_sig_present CHECK (length(log_sig) > 0),
  CONSTRAINT tsa_token_present_if_stated CHECK (tsa_token IS NULL OR length(tsa_token) > 0),
  CONSTRAINT s3_version_stated_if_present CHECK (s3_version IS NULL OR s3_version <> '')
);

CREATE TABLE mainline_ops.sequencer_lease (
  site_code  STRING      NOT NULL,
  holder     STRING      NOT NULL,
  epoch      INT8        NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT sequencer_lease_pkey PRIMARY KEY (site_code),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT epoch_non_negative CHECK (epoch >= 0),
  CONSTRAINT holder_stated CHECK (holder <> '')
);
