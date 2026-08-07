-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI15, MI14, MI01
-- I: I05, I11
-- COUNSEL-GATED: no
-- RATIONALE: PRIMARY KEY (clause_uuid, gen, commit_id) puts `gen` BEFORE `commit_id` so that "what did this clause say at generation N" is a PK-ordered range scan and bisect is a binary search over an index rather than a graph walk; and the BLOODLINE columns carry severity-monotone lineage on the row itself so MI15 can be a per-row guard instead of an ancestry query in a hot trigger.
--
-- migration:  0029_clause_version
-- band:       0024-0031, 0047-0049 · dm-spine
-- statements: 1
-- source:     ARCHITECTURE.md §5.3 (verbatim shape; constraints named per DM-10, indexes and
--             families inline per DM-6) · §3.3 M2 BLOODLINE · §16 MI15 · §4.1 laws 1 and 4
-- requires:   0024 mainline.commit_obj · 0027 mainline.doc · 0028 mainline.clause
--             · 0010 CREATE TYPE mainline.control_delta
-- projects:   gen ← mainline.commit_obj.gen (P2) · sev_max, blood_root, blood_peaks, blood_size
--             ← the parent version plus the blame edges landed in this commit (P2, via
--             mainline.clause_blame_current — DM-9: that view is the ONLY read path to the
--             closure). Owed to TRIGGER-MAP.yaml and to the BEFORE INSERT BLOODLINE guard in band
--             0130-0199, whose refusal is MI15 / P0001.
-- sqlstate:   23503 on fk_clause / fk_commit / fk_doc / fk_parent_version;
--             23514 on sev_range / delta_basis_closed / cat_confidence_closed /
--             canon_sha256_is_sha256 / blood_root_is_sha256 / blood_size_nonneg /
--             model_named_when_model_used; 23505 on clause_version_pk / cv_clause_commit_unique;
--             P0001 from the BLOODLINE guard once band 0130-0199 lands (MI15)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THE HEAVIEST FILE IN THE BAND. Four separate mechanisms meet on this row: clause identity
-- (0028), the history DAG (0024), the delta lattice (`control_delta`), and M2 BLOODLINE. Read the
-- five sections below in order; each explains one column group and why it is shaped that way.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- ── 1. THE PRIMARY KEY, AND WHY `gen` COMES BEFORE `commit_id` ────────────────────────────────
--
-- PRIMARY KEY (clause_uuid, gen, commit_id).
--
-- The question this schema is asked more than any other is *"what did clause X say at the time of
-- commit C"*, and its adversarial form is *"which edit first weakened clause X"* — a bisect. With
-- `gen` in the second position, both are a RANGE SCAN over one contiguous stretch of the primary
-- index: every version of one clause, already sorted by generation, no join, no recursive CTE, no
-- graph walk. Bisect becomes a binary search over that range.
--
-- Put `commit_id` second instead and the same question becomes: collect every version of the
-- clause, join each to mainline.commit_obj for its generation, sort, then search. On a clause with
-- four hundred versions across nine years that is four hundred point lookups to answer a question
-- the index could have answered by seeking. The ordering of two columns in a PK is the difference
-- between a bisect that runs under the gate's latency budget and one that does not — and a bisect
-- that does not run under the budget is a bisect nobody runs.
--
-- `commit_id` is third and is REQUIRED, not decorative: two versions of one clause can share a
-- generation when history forks (two branches at the same depth), so (clause_uuid, gen) is not
-- unique. The third column disambiguates by content address.
--
-- `cv_clause_commit_unique UNIQUE (clause_uuid, commit_id)` EXISTS TO BE POINTED AT. Three tables
-- take a composite FK onto it — mainline.clause_embedding (0031), mainline.clause_band (0030),
-- and mainline.blocking_check / mainline.permit_clause in band 0050-0065 — and a composite FK
-- requires a UNIQUE on exactly those columns in exactly that order. It is also the semantically
-- right constraint on its own: one commit produces at most one version of any given clause. A
-- second one would mean the commit said two different things about the same obligation.
--
-- ── 2. `canon_text` IS THE ONLY TEXT OFFSETS ARE EVER INTO ───────────────────────────────────
--
-- `raw_text` is what the document said. `canon_text` is that text after canonicalisation at
-- `canon_version`: whitespace, quotation marks, ligatures, unit spellings, hyphenation. EVERY
-- offset in this system — anchor spans, CAT extraction spans, highlight ranges in the console,
-- citation targets — IS INTO `canon_text`. Never `raw_text`. Not sometimes, not by convention.
--
-- The reason is that `raw_text` is not stable under re-ingestion of the same source: a PDF
-- re-extracted with a newer text layer differs in whitespace and ligatures while meaning exactly
-- the same thing. An offset into it therefore silently slides, and a highlight that slides is a
-- citation pointing at the wrong sentence — which, in a disclosure bundle, is worse than no
-- citation at all. `canon_version` records WHICH canonicaliser produced `canon_text`, so an
-- offset can always be interpreted, and re-canonicalising is a NEW VERSION ROW rather than an
-- UPDATE. `canon_sha256` is the digest of `canon_text` and is what `by_digest` indexes, so
-- "has this exact normalised text appeared before" is a lookup and not a scan.
--
-- ── 3. `control_delta` AND `delta_basis` — WHAT KIND OF EDIT THIS WAS, AND WHO SAID SO ───────
--
-- `control_delta` is the lattice verdict: introduce · strengthen · restate · weaken · remove. It
-- is the input to the whole gate — `weaken` over blood-written ancestry is what materialises a
-- blocking check — so `delta_basis` records the EVIDENTIAL STANDING of that verdict:
--
--   'lattice'            derived deterministically from the Control Assertion Tuple. No model.
--   'lattice+model'      the lattice was inconclusive and a model's reading resolved it.
--   'abstain_to_weaken'  THE RATCHET. The model abstained, or was low-confidence, or the text was
--                        opaque — and the system therefore recorded the SAFE answer, `weaken`,
--                        which arms the gate. Abstention must cost the writer, never the reader:
--                        the failure mode of a classifier is silence, and silence that resolves to
--                        "no change" is a gate that opens on uncertainty. This value is the reason
--                        an unreadable clause raises a gate instead of passing one.
--   'human'              a person overrode the machine, and their name is on the commit.
--
-- MI14 — a model-rated severity never arms the gate — is enforced on mainline.event (band
-- 0032-0039), where severity is set, not here. What this table carries is the audit trail of how
-- the DELTA was reached, which is the other half of the same principle: the record must always be
-- able to say whether a machine or a person decided, and `model_named_when_model_used` refuses a
-- row that claims a model was involved without naming it.
--
-- ── 4. M2 BLOODLINE — WHY FOUR COLUMNS INSTEAD OF AN ANCESTRY QUERY ──────────────────────────
--
--   blood_root  BYTES    MMR (Merkle Mountain Range) root over {H(event_id || severity)} of this
--                        version's entire blame ancestry.
--   blood_peaks BYTES[]  the MMR peaks. O(log n) to append, and no tree table to maintain.
--   blood_size  INT8     how many ancestral blame facts are accumulated in that root.
--   sev_max     INT2     the maximum ancestral severity, 0-5. THE SCALAR EVERYTHING READS.
--
-- The point of an MMR rather than a recomputed hash: appending one ancestor is O(log n) peak
-- merges, the root is a commitment to the whole multiset, and a stranger can be given a proof
-- that a specific event is inside `blood_root` without being given the whole ancestry. That last
-- property is what makes a disclosure bundle bounded — you prove the one obligation that matters
-- rather than exporting nine years of a mine's records.
--
-- MI15: BLAME ANCESTRY NEVER SHRINKS. `sev_max` and `blood_size` are MONOTONE along the version
-- chain. A rewrite may reword an obligation, retitle it, renumber it and move it to another
-- document; it may NOT reduce the recorded severity of what wrote it. That is the O-Ring Ratchet:
-- once a control is written by a fatality, no subsequent edit can quietly make it look routine.
--
-- The guard is a BEFORE INSERT trigger in band 0130-0199 that reads the parent version — reachable
-- in one seek because of `fk_parent_version` below — and RAISEs P0001 when the child's `sev_max`
-- or `blood_size` is lower. It is a trigger and not a CHECK because §4.1 law 1 forbids a CHECK
-- from seeing another row, and the parent is another row. `sev_range` is the plain-column half:
-- it refuses a severity outside 0-5 for every writer regardless of triggers.
--
-- UNTIL THAT TRIGGER LANDS, MI15 IS NOT ENFORCED AND THIS FILE SAYS SO. The RED test is
-- test_mi_spine.py::test_mi15_bloodline_may_not_shrink, which inserts a child version with a
-- lower `sev_max` than its parent and asserts a refusal. It FAILS TODAY, for exactly that reason,
-- and mi_catalogue.yaml carries MI15 as `pending`. A suite that has never been red asserts
-- nothing (PL-2), and for a product whose deliverable is a REFUSAL that is not a slogan.
--
-- ── 5. `fk_parent_version` — A SELF-FK §5.3 DOES NOT SPECIFY, AND WHY IT IS ADDED ────────────
--
-- FOREIGN KEY (clause_uuid, parent_version) REFERENCES mainline.clause_version (clause_uuid,
-- commit_id). Composite, MATCH SIMPLE, self-referential.
--
-- MATCH SIMPLE is what makes it correct rather than merely strict: CockroachDB treats a composite
-- FK as satisfied when ANY of its columns is NULL, so a BIRTH version (`parent_version IS NULL`)
-- is accepted with no special case, while a non-NULL pointer must resolve. And because
-- `clause_uuid` is repeated on both sides, the pointer cannot cross clauses: version lineage is
-- confined to one obligation by referential integrity rather than by a convention the matcher is
-- trusted to follow.
--
-- It is added because the MI15 guard READS this pointer. A guard whose input can dangle is a
-- guard with a bypass: point `parent_version` at a commit that has no version row and the trigger
-- finds nothing to compare against. Making the pointer FK-enforced means the only remaining way
-- to present no parent is to declare NULL — a visible claim ("this is a birth version") that the
-- residue machinery in 0049 and the matcher can both interrogate, rather than an invisible one.
--
-- ── PLATFORM CORRECTIONS TO THE DDL AS PRINTED IN §5.3 ───────────────────────────────────────
--
-- (a) `by_commit`'s STORING list drops `clause_uuid`. CockroachDB refuses a PRIMARY KEY column in
--     a STORING clause, and secondary indexes carry the PK columns implicitly, so nothing is
--     lost. Same correction as 0024's `by_branch_gen`.
-- (b) `cv_trgm`, the trigram index over `canon_text`, is NOT declared inline here. It ships as
--     0029a_clause_version_trgm.up.sql. CockroachDB documents the operator-class form only for
--     the standalone `CREATE INVERTED INDEX … (col gin_trgm_ops)` statement; whether an operator
--     class may be given inside a CREATE TABLE index definition is undocumented and could not be
--     executed from the machine this band was authored on. DR-3 in docs/leads/datamodel.md
--     accepts the risk that the trigram index is rejected on v26.2 and names its degradation
--     (application-side computation; the lexical channel is already explicit BM25 tables in band
--     0040-0046) — so the risk is isolated into a file whose failure costs one convenience index,
--     rather than left inline where it would take the spine's central table down with it. This is
--     a deliberate, recorded deviation from the brief's "both declared INLINE".
--     `cv_anchors`, which needs no operator class, IS inline as DM-6 requires.
--
-- ── UNVERIFIED ON THIS MACHINE, AND WHAT TO DO IF EACH PART IS REFUSED ───────────────────────
--
-- No CockroachDB v26.2 was reachable from the machine this band was authored on — no `cockroach`
-- binary, no live Docker daemon — so this statement has not been executed. Two constructs here
-- are more than routine, and each has a one-file remediation so nobody has to redesign under
-- pressure:
--
--   (i)  `fk_parent_version` — a COMPOSITE, SELF-REFERENTIAL foreign key declared inline, pointing
--        at a UNIQUE constraint declared in the same CREATE TABLE. Standard SQL, PostgreSQL
--        accepts it, and CockroachDB documents both self-referencing foreign keys and composite
--        ones (a composite FK requires a unique index on exactly those columns in that order,
--        which `cv_clause_commit_unique` provides). If v26.2 refuses the combination inline, move
--        it to `0029b_clause_version_parent_fk.up.sql` as
--        `ALTER TABLE mainline.clause_version ADD CONSTRAINT fk_parent_version FOREIGN KEY
--         (clause_uuid, parent_version) REFERENCES mainline.clause_version (clause_uuid,
--         commit_id)`. The table is empty at migration time, so the ALTER is free.
--   (ii) `INVERTED INDEX cv_anchors (anchor_set)` inline over a `STRING[]`. Inline inverted
--        indexes are documented in the CREATE TABLE grammar; only the operator-class form is not,
--        which is why the trigram index was split out into 0029a and this one was not.
--
-- tests/integration/schema/test_mi_spine.py executes the whole band the moment a cluster is
-- reachable, and reports a skip with a reason rather than a pass when one is not.

CREATE TABLE mainline.clause_version (
  clause_uuid          UUID     NOT NULL,
  gen                  INT8     NOT NULL,   -- PROJECTED from mainline.commit_obj.gen (P2)
  commit_id            BYTES    NOT NULL,
  site_id              UUID     NOT NULL,
  doc_id               UUID     NOT NULL,
  activity_root        STRING   NOT NULL,
  parent_version       BYTES    NULL,       -- NULL ⇒ birth version; see fk_parent_version

  ordinal              INT8     NOT NULL,   -- presentation only, NEVER identity
  printed_label        STRING   NULL,       -- '7.3.2(b)' — the @eId analogue
  raw_text             STRING   NOT NULL,
  canon_text           STRING   NOT NULL,   -- ALL offsets in this system are into THIS column
  canon_version        INT2     NOT NULL,
  canon_sha256         BYTES    NOT NULL,
  anchor_set           STRING[] NOT NULL,   -- tags, setpoints, citations, CAS numbers, roles
  cat_key              STRING   NULL,       -- hash of the normalised Control Assertion Tuple
  cat_json             JSONB    NULL,
  cat_confidence       STRING   NOT NULL DEFAULT 'ok',
  control_delta        mainline.control_delta NOT NULL,
  delta_basis          STRING   NOT NULL,   -- 'abstain_to_weaken' is the ratchet. See section 3.
  delta_model          STRING   NULL,
  delta_prompt_version STRING   NULL,

  -- M2 BLOODLINE: severity-monotone lineage accumulator. MI15 guards these four.
  blood_root           BYTES    NOT NULL,   -- MMR root over {H(event_id||severity)} of ancestry
  blood_peaks          BYTES[]  NOT NULL,   -- MMR peaks: O(log n) append, no tree table
  blood_size           INT8     NOT NULL,
  sev_max              INT2     NOT NULL DEFAULT 0,   -- the scalar every gate reads

  CONSTRAINT clause_version_pk PRIMARY KEY (clause_uuid, gen, commit_id),
  CONSTRAINT cv_clause_commit_unique UNIQUE (clause_uuid, commit_id),
  CONSTRAINT fk_clause FOREIGN KEY (clause_uuid) REFERENCES mainline.clause (clause_uuid),
  CONSTRAINT fk_commit FOREIGN KEY (commit_id) REFERENCES mainline.commit_obj (commit_id),
  CONSTRAINT fk_doc FOREIGN KEY (doc_id) REFERENCES mainline.doc (doc_id),
  CONSTRAINT fk_parent_version FOREIGN KEY (clause_uuid, parent_version)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  CONSTRAINT sev_range CHECK (sev_max BETWEEN 0 AND 5),
  CONSTRAINT gen_nonneg CHECK (gen >= 0),
  CONSTRAINT ordinal_nonneg CHECK (ordinal >= 0),
  CONSTRAINT canon_version_positive CHECK (canon_version >= 1),
  CONSTRAINT canon_sha256_is_sha256 CHECK (length(canon_sha256) = 32),
  CONSTRAINT blood_root_is_sha256 CHECK (length(blood_root) = 32),
  CONSTRAINT blood_size_nonneg CHECK (blood_size >= 0),
  CONSTRAINT cat_confidence_closed CHECK (cat_confidence IN ('ok', 'low', 'opaque')),
  CONSTRAINT delta_basis_closed CHECK (delta_basis IN
    ('lattice', 'lattice+model', 'abstain_to_weaken', 'human')),
  CONSTRAINT model_named_when_model_used
    CHECK (delta_basis <> 'lattice+model' OR delta_model IS NOT NULL),
  INDEX by_commit (site_id, commit_id) STORING (canon_sha256, control_delta, sev_max),
  INDEX by_digest (site_id, canon_sha256),
  INDEX by_doc    (doc_id, gen),
  INVERTED INDEX cv_anchors (anchor_set),
  FAMILY f_hot  (clause_uuid, gen, commit_id, site_id, doc_id, activity_root, parent_version,
                 ordinal, printed_label, canon_version, canon_sha256, cat_key, cat_confidence,
                 control_delta, delta_basis, delta_model, delta_prompt_version,
                 blood_root, blood_size, sev_max),
  FAMILY f_cold (raw_text, canon_text, anchor_set, cat_json, blood_peaks)
);
