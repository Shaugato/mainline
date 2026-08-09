-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0052_permit_clause.sql
-- CREATE TABLE mainline.permit_clause — declared scope, pinned to an exact clause version
--
-- MI: MI05
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: Declared scope is a claim and is stored as one; what the gate reads is its
--            consequence. The foreign key is onto the (clause_uuid, commit_id) PAIR rather
--            than onto the clause, so a re-authored clause does not silently carry an old
--            declaration forward into text nobody read — the same discipline that makes a
--            disposition un-inheritable across a revision. The relation vocabulary is
--            closed and differs by subject kind because a work permit that claimed to
--            introduce a clause would be asserting an authorship it does not have.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0052_subject_clause.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- permit_clause: what the crew works UNDER.
--
-- PRIMARY KEY (permit_id, clause_uuid, relation)
--   `relation` is IN the key, not beside it. One subject may both weaken a clause and
--   rely on it, and those are two different declarations with two different consequences
--   for the slice; collapsing them onto one row would make the second overwrite the
--   first and the slice would then be computed from a claim nobody made.
--
-- NO ON DELETE CASCADE on either foreign key. A cascade rewrites history: deleting a
-- subject would silently erase what it declared it touched, which is the single most
-- useful row in a post-incident reconstruction. Deletes are revoked at the grant layer
-- as well; RESTRICT is the structural half that survives a grant being edited.

CREATE TABLE mainline.permit_clause (
  permit_id    UUID   NOT NULL,
  clause_uuid  UUID   NOT NULL,
  commit_id    BYTES  NOT NULL,
  relation     STRING NOT NULL,
  CONSTRAINT permit_clause_relation_known
    CHECK (relation IN ('waives', 'weakens', 'relies_on', 'cites')),
  CONSTRAINT permit_clause_commit_sized CHECK (length(commit_id) = 32),
  CONSTRAINT fk_permit_clause_subject FOREIGN KEY (permit_id)
    REFERENCES mainline.permit (permit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT fk_permit_clause_version FOREIGN KEY (clause_uuid, commit_id)
    REFERENCES mainline.clause_version (clause_uuid, commit_id)
    ON UPDATE RESTRICT ON DELETE RESTRICT,
  CONSTRAINT pk_permit_clause PRIMARY KEY (permit_id, clause_uuid, relation)
);
