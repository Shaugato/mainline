-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI10
-- I: I03
-- COUNSEL-GATED: no
-- RATIONALE: An illegal state transition must be a 23503 against a table, not an `if` statement in a service, because a service is a thing an operator can bypass under pressure and a foreign key is not.
--
-- migration:  0017_subject_transition
-- band:       0001-0023 · dm-foundation
-- statements: 1
-- source:     ARCHITECTURE.md §5.0 (verbatim, constraints named per DM-10) · §16 MI10
-- requires:   0002 CREATE SCHEMA mainline · 0011 mainline.subject_state
-- seeds:      verticals/mainline/db/seeds/00-lattice/subject_transition.sql (18 rows)
-- sqlstate:   23503 on fk_subject_transition, declared by permit/change_request in band 0050-0065
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- LEGAL STATE TRANSITIONS AS QUERYABLE DATA. Both gated subjects carry the identical edge set
-- (S16): the change_request is a gated subject in exactly the sense the permit is, and MI30 —
-- "a change_request merges only with zero open blocking checks" — is unsatisfiable if the two
-- subjects have different alphabets.
--
-- The edge set, seeded once per subject_kind:
--     draft               → checks_materialised
--     draft               → abandoned
--     checks_materialised → checks_materialised     (a later recall run adds obligations)
--     checks_materialised → dispositioned
--     dispositioned       → checks_materialised     (a precursor arrived after the dispositions)
--     dispositioned       → merged                  ← THE TRANSITION THE DATABASE REFUSES
--     merged              → suspended
--     merged              → closed
--     suspended           → closed
--
-- Two of those nine are the design. `checks_materialised → checks_materialised` exists because a
-- recall run that finds a second precursor must not have to invent a new state to record it.
-- `dispositioned → checks_materialised` is the late-arrival edge: SERIALIZABLE orders writes, it
-- does not prevent a precursor being inserted at T+ε (§4.1 law 3), so a subject that was fully
-- dispositioned can lawfully become un-dispositioned again. Without that edge the system would
-- have to choose between refusing the late precursor — losing the fact — and merging over it.
--
-- There is NO edge into `merged` from anywhere except `dispositioned`, and no edge out of
-- `merged` back to any pre-merge state. That is what makes the epoch pin meaningful: once
-- `merge_record` takes its composite FK on (subject_id, gate_epoch) with ON UPDATE RESTRICT,
-- attaching a new obligation to a completed transition is physically impossible (I03), and no
-- state path exists that would let a caller reopen the subject to work around it.
--
-- `subject_kind` is a STRING with a named CHECK rather than an ENUM: unlike the five types above
-- it is never compared inside a gate CHECK, it appears in GSAC's `subject_matches` as a literal,
-- and a two-value closed set does not earn a type that costs a migration to extend.

CREATE TABLE mainline.subject_transition (
  subject_kind STRING                 NOT NULL,
  from_state   mainline.subject_state NOT NULL,
  to_state     mainline.subject_state NOT NULL,
  CONSTRAINT subject_transition_pk PRIMARY KEY (subject_kind, from_state, to_state),
  CONSTRAINT subject_kind_closed CHECK (subject_kind IN ('permit', 'change_request'))
);
