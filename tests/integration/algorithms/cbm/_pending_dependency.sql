-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS IS NOT A MIGRATION AND IT MUST NEVER BECOME ONE.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- It lives under tests/ and not under verticals/mainline/db/migrations/ on purpose: MR-5's
-- filename convention and `trappoint migrate lint` govern that directory, this file is owned by
-- nobody's band, and a hand-authored twin of another worker's table inside the apply path is
-- exactly the failure the migration reconciliation ruling exists to end (MR-1 consequence 2:
-- CI green, deploy dead).
--
-- WHY IT EXISTS. The CBM ledger reads three objects this worker does not own:
--
--     mainline.clause_blame_closure   datamodel/dm-blame, allocation band 0032-0039
--     mainline.clause_blame_current   datamodel/dm-blame, the same band (the view)
--     mainline.identity_assignment    algorithms/margin-assignment (W8), band 0049a-0049z
--
-- At the time this suite was authored no migration in the tree created any of them: the tree
-- carries 0032-0036 and jumps to 0040, and 0049a is `delta_witness`. A suite that skipped until
-- they landed would verify nothing at all about a refusal that is the flagship claim, and a
-- suite that invented convenient shapes would prove that the test file is self-consistent.
--
-- The middle course, and its rules:
--
--   1. `_cbm_sql_support.spine_migrations()` resolves each of the three against the REAL
--      migration tree by content FIRST. This file is used only for the ones no migration
--      creates, and `stood_in_objects()` names them.
--   2. Every fixture prints which objects were stood in, so no run is silently synthetic.
--   3. `test_cbm_pending_dependency.py` refuses the dangerous combination: a real migration
--      creating one of these AND this file still shadowing it.
--   4. The DDL below is transcribed from the authoritative sources and cites them line by line.
--      It is deliberately MINIMAL — only what the CBM derivation reads — and deliberately not
--      "close enough": a column this worker guessed at is a column this worker's tests would
--      pass against and the deployment would not.
--
-- SOURCES, VERBATIM:
--   clause_blame_closure / clause_blame_current — ARCHITECTURE.md section 5.4, the block
--     beginning "The blame closure — append-only, generation-versioned, monotone, ledgered
--     (S2)". Transcribed including PRIMARY KEY (clause_uuid, as_of_commit, closure_gen), the
--     sev_range and gen_positive CHECKs, and the DISTINCT ON view that keeps max(closure_gen)
--     discipline out of every call site (DM-9).
--   identity_assignment — docs/leads/workers.json, algorithms/margin-assignment, brief item (6):
--     "(site_id, commit_id, ancestor_clause_uuid, descendant_clause_uuid NULL, relation CHECK IN
--     ('matched','split','merge','absent'), stage, score, margin, policy_sha256, computed_by,
--     computed_at) append-only, PK over (commit_id, ancestor_clause_uuid, coalesced descendant)".
--
-- WHAT IS DELIBERATELY OMITTED, so that nobody mistakes this for the real thing: the closure's
-- inverted and severity indexes, `fn_closure_guard` and the append-only trigger (0108/0127 in
-- the kernel's band, which exist and are applied when present), the ledger_intake write, W8's
-- append-only trigger, and every FK that would order this file against migrations it must not
-- depend on. None of them affect what the CBM derivation counts.

CREATE TABLE IF NOT EXISTS mainline.clause_blame_closure (
  clause_uuid     UUID   NOT NULL,
  as_of_commit    BYTES  NOT NULL,
  closure_gen     INT8   NOT NULL,
  site_id         UUID   NOT NULL,
  ancestor_events UUID[] NOT NULL,
  ancestor_count  INT4   NOT NULL,
  max_severity    INT2   NOT NULL,
  virulence       mainline.virulence_class NOT NULL,
  depth           INT4   NOT NULL,
  truncated       BOOL   NOT NULL DEFAULT false,
  computed_by     STRING NOT NULL,
  projector_ver   STRING NOT NULL,
  computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (clause_uuid, as_of_commit, closure_gen),
  CONSTRAINT fk_version FOREIGN KEY (clause_uuid, as_of_commit)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  CONSTRAINT sev_range CHECK (max_severity BETWEEN 0 AND 5),
  CONSTRAINT gen_positive CHECK (closure_gen >= 0)
);

CREATE VIEW mainline.clause_blame_current AS
SELECT DISTINCT ON (clause_uuid, as_of_commit) *
  FROM mainline.clause_blame_closure
 ORDER BY clause_uuid, as_of_commit, closure_gen DESC;

CREATE TABLE IF NOT EXISTS mainline.identity_assignment (
  site_id                UUID   NOT NULL,
  commit_id              BYTES  NOT NULL,
  ancestor_clause_uuid   UUID   NOT NULL,
  descendant_clause_uuid UUID   NULL,
  relation               STRING NOT NULL,
  stage                  STRING NOT NULL,
  score                  FLOAT8 NULL,
  margin                 FLOAT8 NULL,
  policy_sha256          BYTES  NOT NULL,
  computed_by            STRING NOT NULL,
  computed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  descendant_key         UUID   NOT NULL AS (
                           coalesce(descendant_clause_uuid,
                                    '00000000-0000-0000-0000-000000000000'::UUID)
                         ) STORED,
  CONSTRAINT identity_assignment_pk
    PRIMARY KEY (commit_id, ancestor_clause_uuid, descendant_key),
  CONSTRAINT relation_closed
    CHECK (relation IN ('matched', 'split', 'merge', 'absent')),
  CONSTRAINT absent_has_no_descendant
    CHECK (relation <> 'absent' OR descendant_clause_uuid IS NULL)
);
