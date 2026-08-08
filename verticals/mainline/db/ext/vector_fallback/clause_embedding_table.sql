-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI25, MI01
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: DR-1's pre-written escape, moved OUT of the apply path. It is column-for-column identical to verticals/mainline/db/migrations/0031_clause_embedding.sql with the inline VECTOR INDEX removed, so that if v26.2 refuses an inline vector index the response is flipping a render-time capability switch rather than redesigning a table that three others take a composite foreign key onto.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS IS NOT A MIGRATION. It has no number, it is never discovered, it is never applied.
--
-- capability:  inline_vector_index — GT-06 / DR-1. The question is whether CockroachDB v26.2
--              accepts `VECTOR INDEX <name> (<prefix…>, <col> vector_cosine_ops)` written INSIDE
--              `CREATE TABLE`, in combination with inline `FAMILY` declarations. GT-04 measured
--              that a prefix-column vector index can be created on this platform, so the construct
--              exists; the INLINE form, together with families, is the thing this file covers.
-- switch:      `[capabilities] inline_vector_index` in verticals/mainline/vertical.toml, answered
--              PASS or FALLBACK-SELECTED in packages/trappoint-sql/g1-attestation.json. Kernel
--              ruling D5: every capability under a GT-* check is a RENDER-TIME switch with
--              committed, readable SQL on both branches — never a runtime branch, and never a
--              second file sitting beside the primary in the apply path.
--                inline   → verticals/mainline/db/migrations/0031_clause_embedding.sql
--                           (one file, one statement, the index declared inline while the table
--                           is empty at t = 0)
--                fallback → THIS FILE, then clause_embedding_ann_index.sql, emitted into the 0031
--                           slot as 0031_clause_embedding.sql + 0031a_clause_embedding_ann.sql
-- status:      NOT SELECTED, and now measured rather than assumed. The inline branch was executed
--              on CockroachDB v26.2.5 (local, in-memory single node) as part of a 0001-0049
--              forward apply from clean: `SHOW CREATE TABLE mainline.clause_embedding` reports one
--              vector index, `ce_ann`, and the table is created empty. The inline `VECTOR INDEX`
--              together with inline `FAMILY` declarations — the combination GT-04 left untested —
--              is therefore PASS. This branch was also applied, into a second scratch database,
--              and produced the same index name on the same empty table.
--              The switch itself is not declared yet: `g1-attestation.json` carries no
--              `inline_vector_index` entry, so under D5 a template branching on it today is a
--              render REFUSAL, not a silent fallback. Declaring it is the precondition for taking
--              this branch; the branch is pre-written so that taking it is a one-line decision
--              rather than a redesign under pressure.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY IT LIVES HERE AND NOT BESIDE 0031 — measured, not stylistic.
-- The old filename `0031_clause_embedding.fallback.sql` carries a SECOND DOT. `_version_of()`
-- strips only the final `.sql`, so the stem it yields is `0031_clause_embedding.fallback`, and a
-- dot is not in `_VERSION_RE`'s slug class. `discover()` therefore raised `MigrationTreeInvalid`
-- for the ENTIRE directory: the whole migration tree stopped applying because of a file that was
-- never meant to be applied at all. And had the regex been looser the outcome would have been
-- worse — the file would have been applied ALONGSIDE the primary, creating
-- mainline.clause_embedding twice. MR-5 settles it: no second dot, ever; capability variants live
-- under verticals/mainline/db/ext/<topic>/ and are chosen by a render-time switch (D5).
--
-- pairs with:  clause_embedding_ann_index.sql (this directory) — the CREATE VECTOR INDEX half
-- primary:     verticals/mainline/db/migrations/0031_clause_embedding.sql
-- requires:    0029 mainline.clause_version — when, and only when, this branch is rendered into
--              the 0031 slot
-- statements:  1
-- source:      ARCHITECTURE.md §4.1 law 7 (bulk path) · docs/leads/datamodel.md DR-1
--              · docs/adr/0002-g1-platform-ground-truth.md GT-04, GT-06
--              · docs/leads/migration-reconciliation.md §5.3, MR-5
-- sqlstate:    23503 on fk_version; 23514 on embed_model_stated / index_gen_stated;
--              23505 on clause_embedding_pk
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- WHEN TO TAKE IT. Exactly one condition: v26.2 refuses `VECTOR INDEX …` inside CREATE TABLE, or
-- refuses it in combination with the inline FAMILY declarations. GT-04 created a prefix-column
-- vector index on a live cluster, so the CONSTRUCT works; what this file exists for is the inline
-- form together with families, and nothing else.
--
-- WHAT IT COSTS TO TAKE IT — said plainly, rather than presenting the fallback as free.
-- The inline branch creates the index on an EMPTY table, at t = 0, where the backfill is a no-op.
-- This branch creates it as a second statement, which is still against an empty table at migration
-- time and therefore still free — PROVIDED the two statements stay adjacent in the applied order.
-- If anyone ever inserts rows between them, `CREATE VECTOR INDEX` becomes a backfill that BLOCKS
-- TABLE WRITES until it completes and requires `sql_safe_updates` off. Hence the letter suffix on
-- the rendered pair: MR-5 orders lexicographically on the whole stem, so `0031a` follows `0031`
-- immediately and nothing can be numbered between them without a deliberate, visible edit.
--
-- IMPORT INTO REMAINS UNSUPPORTED ON THIS TABLE UNDER EITHER BRANCH, because the table carries a
-- vector index either way. The bulk load path for a demo corpus is batched INSERTs, one statement
-- per row, exactly as on the inline branch.
--
-- The columns, primary key, composite foreign key, constraint names and column families are
-- identical between the two branches — only the `VECTOR INDEX ce_ann (…)` line moves out — so
-- nothing that references mainline.clause_embedding, or the index name `ce_ann`, is affected by
-- the choice. That interchangeability is the whole claim, and it is asserted by
-- tests/integration/schema/test_mi_spine.py, column for column.

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
  FAMILY f_meta (clause_uuid, commit_id, site_id, activity_root, embed_model, index_gen),
  FAMILY f_vec  (embedding)
);
