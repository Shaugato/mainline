-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0071_merge_record.sql
-- CREATE TABLE mainline.merge_record — at most one completion per subject, ever
--
-- MI: MI07, MI09
-- I: I03, I04
-- COUNSEL-GATED: no
-- RATIONALE: The completion record is what the epoch pin hangs from, and its primary key is
--            what makes a double merge 23505 rather than two rows nobody compares. It is
--            subject-polymorphic because both gated kinds complete into it: one nullable
--            reference per kind plus a composite foreign key per kind, which under MATCH
--            SIMPLE is enforced exactly when its reference is present — the only way this
--            platform can express a conditional foreign key. Three CHECKs bind the
--            polymorphic subject_id to whichever reference is non-null, so a record can
--            never pin one subject while claiming to complete another.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0071_merge_record.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- clearance_digest      sha256 over the sorted (obligation_id, disposition_id) set that
--                       cleared this gate. It is the answer to "what exactly was signed
--                       off, at the moment of issue" that does not depend on those rows
--                       still being joinable years later.
-- checkpoint_tree_size  the custody ledger's tree size at issue, NULLABLE on purpose: a
--                       merge that happened while the ledger was unwitnessed is recorded
--                       honestly as unwitnessed rather than given a fabricated size. The
--                       unwitnessed-debt table is where that gap is accounted.
-- merged_by             the acting identity, as a subject claim, not a foreign key: the
--                       person table is versioned by (signer_sub, effective_from) and a
--                       single-column reference would demand a UNIQUE index on
--                       signer_sub, which is false by design.
--
-- NOTE ON ORDERING. This row is written BEFORE the subject reaches its completing state
-- (spec §5.3 steps 5 then 7). DEFERRABLE INITIALLY DEFERRED is unimplemented on this
-- platform, so every intermediate state must be legal at a statement boundary and THE
-- LAST WRITE MUST BE THE ONE THAT TRIPS. Writing the completion record first is what puts
-- the pin in place before the state change the CHECKs guard.

CREATE TABLE mainline.merge_record (
  subject_kind         STRING NOT NULL,
  subject_id           UUID   NOT NULL,
  permit_id            UUID   NULL,
  cr_id                UUID   NULL,
  gate_epoch           INT8   NOT NULL,
  merged_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  merged_by            STRING NOT NULL,
  merged_commit        BYTES  NOT NULL,
  clearance_digest     BYTES  NOT NULL,
  checkpoint_tree_size INT8   NULL,

  CONSTRAINT merge_subject_kind_known
    CHECK (subject_kind IN ('permit', 'change_request')),
  -- MATCH SIMPLE made explicit: exactly one reference is present, so exactly one of the
  -- two composite pins is enforced on any given row.
  CONSTRAINT merge_exactly_one_subject
    CHECK ((permit_id IS NULL) <> (cr_id IS NULL)),
  -- The polymorphic key and the foreign-key columns are the SAME subject. Without this,
  -- a record could pin one subject's epoch while claiming to complete another.
  CONSTRAINT merge_subject_id_bound
    CHECK (subject_id = COALESCE(permit_id, cr_id)),
  CONSTRAINT merge_subject_matches
    CHECK ((subject_kind = 'permit') = (permit_id IS NOT NULL)
       AND (subject_kind = 'change_request') = (cr_id IS NOT NULL)),
  CONSTRAINT merge_epoch_nonneg           CHECK (gate_epoch >= 0),
  CONSTRAINT merge_merged_by_stated       CHECK (merged_by <> ''),
  CONSTRAINT merge_commit_sized           CHECK (length(merged_commit) = 32),
  CONSTRAINT merge_clearance_digest_sized CHECK (length(clearance_digest) = 32),
  CONSTRAINT merge_checkpoint_nonneg
    CHECK (checkpoint_tree_size IS NULL OR checkpoint_tree_size >= 0),
  -- UNNAMED ON PURPOSE. CockroachDB derives `merge_record_pkey`, which is the exhibit the
  -- conformance manifest fixes for CF-09 and CF-44. Naming it here would rename the
  -- exhibit and both cases would fail on the constraint name while passing on the code.
  PRIMARY KEY (subject_kind, subject_id)
);
