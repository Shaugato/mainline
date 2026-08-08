-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0021_person.sql
-- CREATE TABLE mainline.person — append-only, versioned, IdP-sourced
--
-- MI: MI27
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: Six constraints and the whole deliberation measurement are decorative without
--            this table, so it lands before the repository spine (finding S7). It is
--            append-only and versioned by effective_from: a promotion is a new row, never
--            an update, because a disposition signed last year must still be readable
--            against the rank its signer held last year.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0021_identity.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- PRIMARY KEY (signer_sub, effective_from DESC)
--   DESC is load-bearing, not cosmetic. The projection trigger wants the CURRENT row
--   for a signer, which under this key is the first row of the scan rather than a sort
--   over the signer's whole history.
--
-- competency_sha256 / competency_snapshot
--   The snapshot is what the HR or LMS system said, and the digest is what it said it
--   said. Storing both means a later dispute about a signer's authorisations is
--   answered from the record rather than from the upstream system's current state.
--
-- enrolment_assurance
--   The customer's claim about how this identity was established, in the customer's
--   vocabulary. 'self_asserted' is a legal value on purpose: recording weak assurance
--   honestly is worth more than refusing to record it and losing the signer entirely.
--
-- separated_at
--   A person who has left is not deleted. Their signatures remain valid for the period
--   they were live, and the gate can tell the difference.

CREATE TABLE mainline.person (
  signer_sub           STRING NOT NULL,
  effective_from       TIMESTAMPTZ NOT NULL,
  org                  STRING NOT NULL,
  rank                 INT2 NOT NULL,
  competency_source_id UUID NOT NULL,
  competency_sha256    BYTES NOT NULL,
  competency_snapshot  JSONB NOT NULL,
  identity_source      STRING NOT NULL,
  enrolment_assurance  STRING NOT NULL,
  separated_at         TIMESTAMPTZ NULL,
  CONSTRAINT person_rank_range CHECK (rank BETWEEN 1 AND 9),
  CONSTRAINT person_assurance_known
    CHECK (enrolment_assurance IN ('self_asserted', 'in_person_verified', 'hr_system_of_record')),
  CONSTRAINT person_digest_sized CHECK (length(competency_sha256) = 32),
  CONSTRAINT pk_person PRIMARY KEY (signer_sub, effective_from DESC)
);
