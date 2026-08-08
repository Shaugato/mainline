-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI25, MI01
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The vector lives in a SIDECAR with ONE index declared inline at CREATE TABLE on an EMPTY table, because CockroachDB refuses IMPORT INTO on a vector-indexed table entirely and blocks writes during a backfill when the index is added later — so t=0 is the only moment at which creating this index costs nothing.
--
-- migration:  0031_clause_embedding
-- band:       0024-0031, 0047-0049 · dm-spine · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.3 (verbatim shape; constraints named per DM-10) · §4.1 laws 6
--             and 7 · §6.3 (the prefix shape) · docs/adr/0002-g1-platform-ground-truth.md GT-04,
--             GT-06, GT-06b · docs/leads/datamodel.md DR-1
-- requires:   0029 mainline.clause_version
-- projects:   site_id ← mainline.clause_version.site_id · activity_root ← mainline.clause (0028)
--             via mainline.clause_version (P2). Owed to TRIGGER-MAP.yaml and to
--             `fn_clause_prefix_project` in band 0130-0199, which must RAISE P0001 when the
--             parent version is absent. THE PREFIX IS NOT A FILTER — see below.
-- sqlstate:   23503 on fk_version; 23514 on embed_model_stated / index_gen_stated;
--             23505 on clause_embedding_pk
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE SECOND-HIGHEST-RISK FILE IN THE SET, AND ITS FALLBACK IS PRE-WRITTEN.
-- If this statement is refused by v26.2, DR-1 is a RENDER-TIME CAPABILITY SWITCH and not a
-- redesign. The two branches, both committed and both readable (kernel D5):
--   inline    THIS FILE — CREATE TABLE with the VECTOR INDEX declared inline at t = 0
--   fallback  verticals/mainline/db/ext/vector_fallback/clause_embedding_table.sql
--             + .../clause_embedding_ann_index.sql, rendered into this slot as
--             0031_clause_embedding.sql + 0031a_clause_embedding_ann.sql
-- Selected by `[capabilities] inline_vector_index` in verticals/mainline/vertical.toml, answered
-- in packages/trappoint-sql/g1-attestation.json. The fallback pair carries the same column
-- definitions and lives OUTSIDE the apply path — never as a sibling of this file, because a
-- sibling is either applied (creating the table twice) or refused by name (killing the whole
-- tree). MR-5, and it was measured both ways before it was written down.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY A SIDECAR AND NOT A COLUMN ON mainline.clause_version (§4.1 law 7). Three reasons, and the
-- third is the one that would be discovered too late:
--
--   1. ONE VECTOR INDEX PER TABLE. Vectors live in sidecars so that each embedding space —
--      clause bodies here, event cues in 0041, the coarse tenant sweep in 0042 — gets its own
--      table and therefore its own single index. A second vector index on one table is not a
--      configuration we are choosing against; it is a shape the platform does not offer.
--   2. IMPORT INTO IS UNSUPPORTED ON A VECTOR-INDEXED TABLE. Putting the vector on
--      clause_version would make the ENTIRE clause corpus unloadable by bulk import, forever,
--      for the sake of one column. The sidecar confines that limitation to the sidecar.
--   3. DIMENSION AND OPCLASS CHANGES ARE NEW TABLES, NEVER `ALTER`s. Re-embedding at a different
--      dimension, or switching from cosine to inner product, is an expand/contract migration: a
--      new sidecar, a read view over both, one cutover migration, then the old table is dropped.
--      NEVER `ALTER TABLE … ALTER COLUMN embedding TYPE VECTOR(n)`. If the vector were a column
--      on clause_version, that cutover would mean rebuilding the spine's central table.
--
-- ── THE PREFIX IS NOT A FILTER. IT SELECTS THE TREE THAT IS SEARCHED. ────────────────────────
--
-- C-SPANN maintains a SEPARATE k-means partition tree per distinct prefix value. `(site_id,
-- activity_root)` therefore does not narrow a result set after the fact — it decides WHICH INDEX
-- STRUCTURE the ANN query descends. The consequences are not intuitive and both matter:
--
--   * AN INSERTER WHO CHOOSES THESE TWO VALUES CHOOSES REACHABILITY. A clause embedded under the
--     wrong activity root is not ranked lower. It is unreachable, by every arm, forever, with no
--     refusal anywhere in the system and no row anywhere that is wrong. A fatality-written
--     obligation filed under the wrong root is a precursor that will never be recalled, and the
--     gate it should have armed will open cleanly. That is why P2 has to reach one hop past the
--     gate scalar and all the way to the INDEX PARTITION: both prefix columns are overwritten by
--     a trigger from mainline.clause_version / mainline.clause on every insert, and that trigger
--     RAISEs P0001 when the parent version is absent. Until band 0130-0199 lands they are
--     client-supplied, and this file records that rather than implying otherwise.
--   * EVERY PREFIX COLUMN MUST BE CONSTRAINED TO A SINGLE VALUE FOR THE INDEX TO BE USED. `IN
--     (...)` does not work. An ancestor walk across k activity roots is k separate ANN queries,
--     `UNION ALL`-ed and re-ranked — never one query with a disjunction. That rule is unchanged
--     by anything measured at G1 and it is asserted in CI by the recall band's EXPLAIN tests.
--
-- ── WHAT G1 MEASURED, AND THE ONE THING IT CHANGED ───────────────────────────────────────────
--
-- GT-04: `VECTOR(n)` plus a prefix-column vector index CREATES AND POPULATES on the free Basic
-- tier. The largest platform risk in the architecture is retired — no paid tier, no self-hosting.
--
-- GT-06: at ~5,200 rows an UNHINTED prefix-constrained ANN query does NOT use the index; the plan
-- is top-k → render → filter → scan. GT-06b: the same query with `FROM tbl@index_name` DOES
-- traverse it. So the optimizer is the variable, not the index, and every ANN arm in this system
-- PINS THE INDEX EXPLICITLY:
--
--     SELECT … FROM mainline.clause_embedding@ce_ann
--      WHERE site_id = $1 AND activity_root = $2
--      ORDER BY embedding <=> $3 LIMIT $4
--
-- That is not a workaround. A plan that flips on table statistics must not sit beneath a safety
-- gate: a corpus that shrinks would otherwise turn ANN recall into a full scan silently, changing
-- latency without changing behaviour. `ce_ann` is a NAME THAT QUERIES DEPEND ON, which is another
-- reason it is declared here with an explicit name rather than left to the server to generate.
--
-- ── COLUMNS ──────────────────────────────────────────────────────────────────────────────────
--
-- `embed_model` records WHICH model produced the vector ('amazon.titan-embed-text-v2:0', verified
-- present in ap-southeast-2 at G1). `index_gen` is the generation label that feeds M4's
-- `index_fingerprint`, and it exists because of a specific platform gap: CockroachDB's `INSPECT`
-- SKIPS vector indexes, so vector-index corruption is undetectable by the database's own
-- integrity tool. M4's fingerprint is the only structural tripwire we have. (Operational note for
-- the custodian patrol, recorded where it will be read: always run `INSPECT` with the default
-- `INDEX ALL` and NEVER name an index — a directly-requested unsupported index makes the
-- statement fail before it starts, which reads as a broken patrol rather than a skipped check.)
--
-- `VECTOR(1024)` matches Titan v2's default output dimension. Changing it is the expand/contract
-- migration described above, never an `ALTER`.
--
-- THE TWO FAMILIES. `f_vec` isolates the 4 KiB embedding from the metadata, so a query that reads
-- `index_gen` across the corpus (the fingerprint patrol) does not drag every vector through the
-- KV layer. Column families with vector indexes are supported on this platform — cockroachdb
-- #147307 fixed vector retrieval through the primary key when families are in use, and that fix
-- predates v26.2. The interaction of INLINE families with an INLINE vector index was the one part
-- of this statement that had never been executed; it has now been, on v26.2.5, and it is accepted
-- — see VERIFIED at the end of this header.
--
-- ── THE FALLBACK IS NOT A SIBLING, AND THAT IS THE FIX ───────────────────────────────────────
-- THIS file is in the lock; the fallback branch is not in the lock because it is not in the
-- migrations directory at all. It used to be: `0031_clause_embedding.fallback.sql` and
-- `0031a_clause_embedding_ann.fallback.sql` sat right here, and the second dot in each name
-- survived `_version_of()` (which strips only `.sql` / `.up.sql`), so the stem failed
-- `^\d{4}[a-z]*_[a-z0-9_]+$` and `discover()` refused the ENTIRE directory. Not "the fallback was
-- skipped" — nothing in MAINLINE applied at all, because of two files that were never meant to be
-- applied. The earlier reading was that the runner should special-case `*.fallback.sql`; MR-5
-- rejects that, because a runner taught to ignore a second dot would one day ignore
-- `0031_clause_embedding.v2.sql` too, and a looser regex would have APPLIED both variants and
-- created this table twice. The variant moved to verticals/mainline/db/ext/vector_fallback/ and
-- is chosen at render time (D5), which is the one place a choice between two SQL files belongs.
--
-- VERIFIED: executed on CockroachDB v26.2.5 (local node, in-memory single node) as part of a
-- 0001-0049 forward apply from clean. `SHOW CREATE TABLE mainline.clause_embedding` reports
-- exactly one vector index, `ce_ann`, and the table is created empty. The inline `VECTOR INDEX`
-- IN COMBINATION WITH the inline `FAMILY` declarations — the one thing GT-04 left untested — is
-- therefore measured PASS on this platform, and the fallback branch above stays unselected.

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
