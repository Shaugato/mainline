-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
--
-- MI: MI25, MI01
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: A corpus-scale ANN measurement needs corpus-scale rows behind the real ce_ann index, and the production sidecar sits behind a write gate whose entire purpose is to refuse rows that did not come through it; so the clause_embedding statement below is byte-identical to migration 0031 and the parent it references is an openly-declared two-column stub, which buys every claim about the INDEX on the real shape and forfeits every claim about the GATE, deliberately and in writing.
--
-- ══════════════════════════════════════════════════════════════════════════════════════════════
-- ann_evidence_schema.sql — THE ANN EVIDENCE DATABASE.  NOT A MIGRATION.
-- ══════════════════════════════════════════════════════════════════════════════════════════════
--
-- THIS FILE IS NOT IN THE APPLY PATH AND CANNOT ENTER IT BY ACCIDENT.  `discover()` globs
-- `verticals/mainline/db/migrations/*.sql`; this directory is not that one, carries no band
-- number, and is absent from `migrations.allocation.toml` and `migrations.lock.json`.  It is
-- rendered by `scripts/aws/load_vectors.py` into a SEPARATE DATABASE, `mainline_ann_evidence`,
-- and it never issues a statement against `mainline_demo`.
--
-- WHY IT EXISTS.  `mainline_demo.mainline.clause_embedding` is the production sidecar.  Its
-- parent, `mainline.clause_version`, carries three triggers — `append_only`,
-- `z_delta_witness_required`, `clause_version_guard` — and the whole point of those triggers is
-- to refuse a version row that was not produced by the pipeline.  Loading a thousand-document
-- corpus therefore means either forging writes past a gate built to stop exactly that, or
-- measuring the index somewhere the gate is not.  This fleet does the second and says so.  The
-- production table gets exactly ONE row — a real Bedrock vector for the one real
-- `clause_version` that already exists — and that row is the only claim made about the gate.
-- Everything else is measured here, where the DDL is identical and the parent is a stub.
--
-- WHAT THE STUB COSTS.  Stated in full in README.md in this directory, and once more here so a
-- reader who opens only the SQL still gets it:
--
--   * `mainline.clause_version` below has **2 of the production table's 25 columns** and **0 of
--     its 3 triggers**.  It has no `mainline.clause`, `mainline.doc` or `mainline.commit_obj`
--     parents, no `canon_sha256`, no `blood_root`, no `control_delta`, no RLS.
--   * So a row in `mainline_ann_evidence` proves NOTHING about whether the same row could have
--     been created in production.  The write gate is precisely what is missing.
--   * What it does prove is everything downstream of the row's existence: the vector width, the
--     opclass, the prefix columns, which partition tree an ANN query descends, whether the
--     optimiser picks `ce_ann` unhinted, and what the recall numbers are.  Those are properties
--     of the `clause_embedding` statement, and that statement is byte-identical.
--
-- @connect DIRECTIVES.  Each statement is preceded by `-- @connect <target>`.  `cluster` means
-- the loader's admin connection (the DSN's own database); a database name means a connection
-- opened against that database.  The directive is machine-read, not decoration: it is how a
-- `CREATE DATABASE` and the statements that must run INSIDE it live in one reviewable file
-- without a `USE`, which CockroachDB's own shell accepts and `psql` does not.
--
-- IDENTITY CONSTRUCTS.  There is no `CREATE SEQUENCE`, no `nextval`, no `SERIAL` and no
-- `unique_rowid()` in this file or in the loader that runs it.  Every key is supplied by the
-- caller: `clause_uuid` is a UUIDv5 of a corpus identifier and `commit_id` is the SHA-256 of the
-- embedded text, so the same corpus reproduces the same primary keys on any cluster, which is
-- what makes a re-run an overwrite rather than a second copy.
--
-- PROVENANCE, LINE BY LINE.  The ranges below are not documentation — `scripts/aws/load_vectors.py`
-- parses them, requires them to be contiguous and to cover the file exactly, and byte-compares
-- every `VERBATIM` range against its named source.  A drift of one space fails the run and is
-- reported in `evidence/aws/load/schema-fidelity.json`.
--
--   @prov L001-L066 AUTHORED  this header
--   @prov L067-L071 AUTHORED  database and schema creation
--   @prov L072-L086 STUB      mainline.clause_version — 2 of 25 columns, 0 of 3 triggers
--   @prov L087-L088 AUTHORED  the @connect directive for the statement below it
--   @prov L089-L105 VERBATIM  verticals/mainline/db/migrations/0031_clause_embedding.sql L136-L152
--
-- ══════════════════════════════════════════════════════════════════════════════════════════════

-- @connect cluster
CREATE DATABASE IF NOT EXISTS mainline_ann_evidence;

-- @connect mainline_ann_evidence
CREATE SCHEMA IF NOT EXISTS mainline;

-- @connect mainline_ann_evidence
-- ── THE STUB ─────────────────────────────────────────────────────────────────────────────────
-- The minimum that satisfies `fk_version` and nothing beyond it.  The FK names
-- `(clause_uuid, commit_id)`; in production those columns are covered by
-- `UNIQUE INDEX cv_clause_commit_unique` on a table whose PRIMARY KEY is
-- `(clause_uuid, gen, commit_id)`.  Here they ARE the primary key, because `gen` is one of the
-- 23 columns this stub does not have.  That difference is the stub, in one line: the production
-- parent can hold many generations of a clause and refuses to let you write them out of order;
-- this one holds a pair of identifiers and refuses nothing.
CREATE TABLE mainline.clause_version (
  clause_uuid   UUID  NOT NULL,
  commit_id     BYTES NOT NULL,
  CONSTRAINT clause_version_stub_pk PRIMARY KEY (clause_uuid, commit_id)
);

-- @connect mainline_ann_evidence
CREATE TABLE mainline.clause_embedding (
  clause_uuid   UUID   NOT NULL,
  commit_id     BYTES  NOT NULL,
  site_id       UUID   NOT NULL,          -- prefix 1  ← PROJECTED (band 0130-0199). Not a filter.
  activity_root STRING NOT NULL,          -- prefix 2  ← PROJECTED (band 0130-0199). Not a filter.
  embed_model   STRING NOT NULL,          -- 'amazon.titan-embed-text-v2:0'
  index_gen     STRING NOT NULL,          -- generation label; feeds M4's index_fingerprint
  embedding     VECTOR(1024) NOT NULL,
  CONSTRAINT clause_embedding_pk PRIMARY KEY (clause_uuid, commit_id),
  CONSTRAINT fk_version FOREIGN KEY (clause_uuid, commit_id)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  CONSTRAINT embed_model_stated CHECK (embed_model <> ''),
  CONSTRAINT index_gen_stated CHECK (index_gen <> ''),
  VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops),
  FAMILY f_meta (clause_uuid, commit_id, site_id, activity_root, embed_model, index_gen),
  FAMILY f_vec  (embedding)
);
