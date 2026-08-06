-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- PREREQUISITE FIXTURE — NOT PART OF THE DEPLOYED SCHEMA, NOT A MIGRATION.
--
-- The recall band (0040-0046, 0080-0088, 0112-0114, 0136-0139) CONSUMES tables owned by other
-- workers: `mainline.activity_node` and `mainline.event` (0032-0033, `dm-blame`),
-- `mainline.blocking_check` (0058, `dm-gate`), and `mainline.ledger_checkpoint` /
-- `mainline.cosignature` (0072-0079, custody). Until those migrations land in this repository
-- there is nothing for the recall DDL to reference, and this file is what makes the recall band
-- applicable in isolation.
--
-- EVERY STATEMENT IS `IF NOT EXISTS`, so when the real migrations are applied first this file
-- becomes a no-op and the suite runs against the deployed shapes rather than against these.
--
-- `activity_node`, `event`, `ledger_checkpoint` and `cosignature` are copied VERBATIM from
-- ARCHITECTURE.md §5.4 and §5.6, because the recall triggers read their columns and a fixture
-- that drifts from the real shape tests nothing.
--
-- `blocking_check` is DELIBERATELY A STUB and is labelled as one. The deployed table (§5.5) is
-- large — GSAC addressing, a computed `dedupe_key`, virulence, control_delta, evidence_summary,
-- the epoch pin — and none of it is this domain's to define. The stub carries exactly the four
-- columns `mainline.fn_bonded_sev5` reads (`permit_id`, `precursor_event_id`) plus enough shape
-- to insert a row. NO MAINLINE ENFORCEMENT LIVES IN THIS FILE: there are no projection triggers
-- on the stub, so nothing in this suite can pass because of something the fixture did.

CREATE SCHEMA IF NOT EXISTS mainline;
CREATE SCHEMA IF NOT EXISTS mainline_meas;

-- ── §5.4 verbatim ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mainline.activity_node (
  scope_id      UUID   NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id       UUID   NOT NULL,
  level         INT2   NOT NULL CHECK (level BETWEEN 1 AND 3),
  parent_scope  UUID   NULL REFERENCES mainline.activity_node (scope_id),
  label         STRING NOT NULL,
  activity_root STRING NOT NULL,
  taxonomy_ver  INT4   NOT NULL,
  induced_by    STRING NOT NULL CHECK (induced_by IN ('icmm_mue','llm_induced','human')),
  frozen        BOOL   NOT NULL DEFAULT false,
  UNIQUE (site_id, taxonomy_ver, level, label),
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

-- ── §5.6 verbatim ────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mainline.ledger_checkpoint (
  site_code    STRING NOT NULL,
  tree_size    INT8   NOT NULL,
  root_hash    BYTES  NOT NULL,
  body         STRING NOT NULL,
  beacon       JSONB  NOT NULL,
  log_sig      BYTES  NOT NULL,
  tsa_token    BYTES  NULL,
  s3_version   STRING NULL,
  canon_src_sha256 BYTES NOT NULL,
  admissible   BOOL   NOT NULL DEFAULT false,
  PRIMARY KEY (site_code, tree_size)
);

CREATE TABLE IF NOT EXISTS mainline.cosignature (
  site_code    STRING NOT NULL,
  tree_size    INT8   NOT NULL,
  witness_id   STRING NOT NULL,
  trust_domain STRING NOT NULL,
  adverse      BOOL   NOT NULL,
  sig          BYTES  NOT NULL,
  received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (site_code, tree_size, witness_id),
  CONSTRAINT fk_cp FOREIGN KEY (site_code, tree_size)
    REFERENCES mainline.ledger_checkpoint (site_code, tree_size)
);

-- ── STUB. Not §5.5. See the header. ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mainline.blocking_check (
  check_id           UUID   NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_kind       STRING NOT NULL CHECK (subject_kind IN ('permit','change_request')),
  permit_id          UUID   NULL,
  cr_id              UUID   NULL,
  site_id            UUID   NOT NULL,
  precursor_event_id UUID   NULL REFERENCES mainline.event (event_id),
  origin             STRING NOT NULL,
  severity           INT2   NOT NULL DEFAULT 0,
  materialised_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT exactly_one_subject CHECK ((permit_id IS NULL) <> (cr_id IS NULL))
);
