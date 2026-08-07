-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI25, MI01
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: DR-1's pre-written escape. Column-for-column identical to 0031_clause_embedding.up.sql with the inline VECTOR INDEX removed, so that if v26.2 refuses an inline vector index the response is renaming two files rather than redesigning a table three others take a composite FK onto.
--
-- migration:  0031_clause_embedding  (FALLBACK VARIANT — NOT APPLIED, NOT IN migrations.lock.json)
-- band:       0024-0031, 0047-0049 · dm-spine
-- statements: 1
-- source:     ARCHITECTURE.md §4.1 law 7 (bulk path) · docs/leads/datamodel.md DR-1
--             · docs/adr/0002-g1-platform-ground-truth.md GT-04
-- requires:   0029 mainline.clause_version
-- pairs with: 0031a_clause_embedding_ann.fallback.sql — the CREATE VECTOR INDEX half
-- sqlstate:   23503 on fk_version; 23514 on embed_model_stated / index_gen_stated;
--             23505 on clause_embedding_pk
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS FILE IS NOT APPLIED. It is inert until someone renames it.
--
-- THE SWAP, IN FULL, SO NOBODY HAS TO RECONSTRUCT IT UNDER PRESSURE:
--   1. git mv 0031_clause_embedding.up.sql            0031_clause_embedding.inline.disabled
--   2. git mv 0031_clause_embedding.fallback.sql      0031_clause_embedding.up.sql
--   3. git mv 0031a_clause_embedding_ann.fallback.sql 0031a_clause_embedding_ann.up.sql
--   4. re-run `trappoint-migrate lint` and regenerate migrations.lock.json
-- No other file in the repository changes. The table's columns, primary key, composite foreign
-- key, constraint names and column families are byte-identical between the two variants — only
-- the `VECTOR INDEX ce_ann (…)` line moves out — so nothing that references
-- mainline.clause_embedding or the index name `ce_ann` is affected.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHEN TO TAKE IT. Exactly one condition: v26.2 refuses `VECTOR INDEX … ` inside CREATE TABLE, or
-- refuses it in combination with the inline FAMILY declarations. GT-04 created a prefix-column
-- vector index on a live Basic cluster, so the CONSTRUCT works; what is untested is the inline
-- form together with families, and that is the only thing this file exists for.
--
-- WHAT IT COSTS TO TAKE IT — say it plainly rather than presenting the fallback as free.
-- The live path creates the index on an EMPTY table, at t=0, where the backfill is a no-op. This
-- fallback creates it as a second statement, which is still against an empty table at migration
-- time and therefore still free — PROVIDED the two files stay adjacent in the applied order. If
-- anyone ever inserts rows between them, `CREATE VECTOR INDEX` becomes a backfill that BLOCKS
-- TABLE WRITES until it completes and requires `sql_safe_updates` off. Hence the letter suffix:
-- ruling D7's lexicographic ordering puts `0031a` immediately after `0031`, and nothing can be
-- numbered between them without a deliberate, visible edit.
--
-- IMPORT INTO REMAINS UNSUPPORTED ON THIS TABLE UNDER EITHER VARIANT, because the table has a
-- vector index either way. The bulk load path for a demo corpus is batched INSERTs, one statement
-- per row, exactly as in the live path.
--
-- CROSS-DOMAIN NOTE (dm-runner): `trappoint_migrate.discovery.discover()` currently RAISES
-- `MigrationTreeInvalid` on this filename — the version stem `0031_clause_embedding.fallback`
-- carries a dot and fails `^\d{4}[a-z]*_[a-z0-9_]+$`. The runner must SKIP `*.fallback.sql`
-- (and `trappoint_migrate.lint` should leave it to the same rule) before this file can sit beside
-- the live band. dm-recall-tables ships two of these for the same reason.

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
