-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- PREREQUISITE FIXTURE — NOT PART OF THE DEPLOYED SCHEMA, NOT A MIGRATION.
--
-- The taxonomy / LMB worker CONSUMES two tables it does not own: `mainline.activity_node`
-- and `mainline.event`, reserved as migrations 0032-0033 by the ancestry/ingest lead. At the
-- time this file was written those migrations are ABSENT from the repository (the migration
-- band jumps 0023 -> 0040), so there is nothing for a taxonomy integration test to write
-- against.
--
-- This file is what the brief means by "run against the fixture DDL you commit ... and mark
-- the integration lane skipped — never fake the table". It is:
--
--   * copied VERBATIM from ARCHITECTURE.md §5.4 for `activity_node` and `event`, so a fixture
--     that drifts from the real shape cannot pass a test the real shape would fail;
--   * `IF NOT EXISTS` on every statement, so once 0032/0033 land this file is a no-op and any
--     lane that applies it runs against the deployed shapes instead;
--   * carrying NO enforcement of its own. There are no triggers here, no extra constraints,
--     no defaults beyond the ones §5.4 declares. Nothing in a taxonomy test can therefore
--     pass because of something this fixture did.
--
-- `event_cue` and `event_bond` are included because the LMB and bond writers target them, and
-- they are copied from the committed migrations 0040 and 0046 (not from ARCHITECTURE, so that
-- a drift between the migration and this file is a test failure rather than a silent
-- divergence). `tests/unit/recall_taxonomy/test_fixture_ddl_contract.py` asserts the column
-- sets match, with no cluster required.
--
-- Applying this file DOES NOT make the integration lane valid. It makes the DDL applicable in
-- isolation for a developer with a local `cockroach` binary. The lane that would prove the
-- writers against a real cluster is skipped, with a reason, until 0032/0033 exist.

CREATE SCHEMA IF NOT EXISTS mainline;

-- ── ARCHITECTURE.md §5.4, verbatim ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mainline.activity_node (
  scope_id      UUID   NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id       UUID   NOT NULL,
  level         INT2   NOT NULL CHECK (level BETWEEN 1 AND 3),   -- 1 fonds, 2 series, 3 file
  parent_scope  UUID   NULL REFERENCES mainline.activity_node (scope_id),
  label         STRING NOT NULL,       -- a FUNCTION PERFORMED, never a thing or a place
  activity_root STRING NOT NULL,       -- level-1 code, denormalised: the clause vector prefix
  taxonomy_ver  INT4   NOT NULL,
  induced_by    STRING NOT NULL CHECK (induced_by IN ('icmm_mue','llm_induced','human')),
  frozen        BOOL   NOT NULL DEFAULT false,
  UNIQUE (site_id, taxonomy_ver, level, label),
  -- Level 1 is anchored to the buyer's ICMM Material Unwanted Event register and is FROZEN:
  -- prefix values are baked into the physical index, so re-inducting level 1 is a re-partition.
  CONSTRAINT l1_frozen CHECK (level <> 1 OR frozen = true)
);

CREATE TABLE IF NOT EXISTS mainline.event (
  event_id           UUID   NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id            UUID   NOT NULL,
  external_ref       STRING NULL,
  occurred_at        TIMESTAMPTZ NOT NULL,
  ingested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  kind               STRING NOT NULL CHECK (kind IN
    ('incident','near_miss','regulator_notice','oem_alert','audit_finding','capa')),
  title              STRING NOT NULL,
  narrative          STRING NOT NULL,
  source_doc_id      UUID   NULL,
  source_object_key  STRING NOT NULL,
  source_sha256      BYTES  NOT NULL,
  severity_actual    INT2   NOT NULL CHECK (severity_actual BETWEEN 0 AND 5),
  severity_potential INT2   NOT NULL CHECK (severity_potential BETWEEN 0 AND 5),
  severity_gate      INT2   NOT NULL CHECK (severity_gate BETWEEN 0 AND 5),
  severity_basis     STRING NOT NULL CHECK (severity_basis IN
    ('coded_field','regulator_class','human_rated','model_rated')),
  severity_span      INT8[] NULL,
  consequence_proxy  JSONB  NULL,
  cluster_id         UUID   NULL,
  canon_version      INT2   NOT NULL,
  UNIQUE (site_id, external_ref),
  CONSTRAINT model_cannot_arm CHECK (severity_gate < 4 OR severity_basis <> 'model_rated'),
  INDEX by_sev (site_id, severity_gate, occurred_at DESC)
);

-- ── migration 0040, the LMB writer's target ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mainline.event_cue (
  cue_id       UUID   NOT NULL DEFAULT gen_random_uuid(),
  event_id     UUID   NOT NULL REFERENCES mainline.event (event_id),
  site_id      UUID   NOT NULL,
  scope_id     UUID   NOT NULL,                 -- ONE ROW PER ARCHIVAL LEVEL (LMB)
  scope_level  INT2   NOT NULL CHECK (scope_level BETWEEN 1 AND 3),
  facet        STRING NOT NULL CHECK (facet IN
    ('mechanism','precondition','control_failure','recurrence_test','narrative')),
  taxonomy_ver INT4   NOT NULL,
  cue_text     STRING NOT NULL,
  source_span  INT8[2] NULL,
  is_derived   BOOL   NOT NULL DEFAULT true,
  gen_model    STRING NOT NULL,
  prompt_version STRING NOT NULL,
  tsv          TSVECTOR AS (to_tsvector('english', cue_text)) STORED,
  CONSTRAINT event_cue_pk PRIMARY KEY (cue_id),
  CONSTRAINT event_cue_one_per_scope_facet_prompt
    UNIQUE (event_id, scope_id, facet, prompt_version),
  INVERTED INDEX cue_tsv (tsv)
);

-- ── migration 0046, the bond writer's target ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mainline.event_bond (
  event_id     UUID   NOT NULL REFERENCES mainline.event (event_id),
  scope_id     UUID   NOT NULL REFERENCES mainline.activity_node (scope_id),
  taxonomy_ver INT4   NOT NULL,
  bond_basis   STRING NOT NULL CHECK (bond_basis IN ('coded','llm_induced','human')),
  CONSTRAINT event_bond_pk PRIMARY KEY (event_id, scope_id, taxonomy_ver),
  INDEX bond_by_scope (scope_id, taxonomy_ver, event_id)
);
