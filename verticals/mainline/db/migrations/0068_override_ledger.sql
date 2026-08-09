-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0068_override_ledger.sql
-- CREATE TABLE mainline.override_ledger — the escalation ladder, scoped to the person
--
-- MI: MI29
-- I: I10
-- COUNSEL-GATED: yes
-- RATIONALE: A per-subject override budget resets whenever a new subject is raised, so the
--            fortieth override is as cheap as the first and the emergency constructor
--            becomes the normal one. Scoping the ladder to the signer and the site is what
--            makes each successive override cost a higher rank; prior_override_count is
--            projected from this table onto the disposition, so the count cannot be
--            supplied by the person being counted, and there is no ceiling because a
--            ceiling is the rung every heavy user would live on.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0068_override_ledger.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- SUBJECT-POLYMORPHIC UNDER RULING D2, over the 2 gated subject(s) declared:
--   permit -> mainline.permit (permit_id)
--   change_request -> mainline.change_request (cr_id)
--
-- §5.5 gives this table `permit_id UUID NOT NULL`, for the same pre-S16 reason
-- `disposition` did. If a change request can carry an obligation — and MI30 says it must
-- — then it can carry an emergency override, and a ledger that cannot record one would
-- make the CR path the cheap way around the ladder. That is a worse failure than the
-- brick wall, because it is invisible: every constraint stays green while the escalation
-- silently stops counting half the overrides.
--
-- APPEND-ONLY, AND THE APPEND IS NOT THE WRITER'S CHOICE. Rows here are written by the
-- disposition family's AFTER trigger, never by an application. `fk_override_disposition`
-- is what makes that structural rather than conventional: an override row must name a
-- disposition that already exists, so the append cannot happen in a BEFORE trigger and
-- cannot name a signature that was never made. §5.5 leaves the column unreferenced; the
-- foreign key is added here because an override ledger whose disposition_id points at
-- nothing is a ladder made of numbers rather than of signatures.
--
-- `at` IS THE SERVER CLOCK AND THE LADDER'S ONLY ORDERING. A client-supplied timestamp
-- would let an override be back-dated out of the window that counts it, which is the
-- one edit that would defeat this table without touching a single constraint.
--
-- THE INDEX IS NAMED FOR ITS TABLE, not `by_signer` as §5.5 writes it. Migration 0023
-- already ruled on this for the same reason: index names are exhibits, and an exhibit
-- called `by_signer` in a schema with several by-signer indexes names nothing. It is
-- declared INLINE because a single-statement file is the rule (ruling D7) and the index
-- is not a separately diagnosable object here — an override ledger without its window
-- index is not a degraded ledger, it is an unusable one.
--
-- NO ROW-LEVEL TTL. The ladder is monotone across the person's whole history at the
-- site; a background deleter would silently reset it, and "the count went down because a
-- job ran" is not a sentence that can be said in a deposition.

CREATE TABLE mainline.override_ledger (
  override_id    UUID NOT NULL DEFAULT gen_random_uuid(),
  site_id        UUID NOT NULL,
  signer_sub     STRING NOT NULL,
  subject_kind   STRING NOT NULL,
  permit_id      UUID NULL REFERENCES mainline.permit (permit_id),
  cr_id          UUID NULL REFERENCES mainline.change_request (cr_id),
  disposition_id UUID NOT NULL,
  at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT fk_override_disposition FOREIGN KEY (disposition_id)
    REFERENCES mainline.disposition (disposition_id),
  CONSTRAINT override_subject_kind_known
    CHECK (subject_kind IN ('permit', 'change_request')),
  CONSTRAINT exactly_one_subject
    CHECK ((permit_id IS NULL) <> (cr_id IS NULL)),
  CONSTRAINT subject_matches
    CHECK ((subject_kind = 'permit' AND permit_id IS NOT NULL)
        OR (subject_kind = 'change_request' AND cr_id IS NOT NULL)),
  CONSTRAINT override_signer_sub_stated CHECK (signer_sub <> ''),
  CONSTRAINT pk_override_ledger PRIMARY KEY (override_id),
  INDEX override_ledger_by_signer (site_id, signer_sub, at DESC)
);
