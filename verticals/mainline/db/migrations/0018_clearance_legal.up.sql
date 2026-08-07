-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI11, MI28
-- I: I10
-- COUNSEL-GATED: no
-- RATIONALE: The legal set of clearing verdicts is a function of ANCESTRAL severity, and holding it as versioned data with a named customer approver is what turns "you cannot dismiss a control a fatality wrote" from a policy someone can be persuaded to relax into a 23503 that has no persuadable party.
--
-- migration:  0018_clearance_legal
-- band:       0001-0023 · dm-foundation
-- statements: 1
-- source:     ARCHITECTURE.md §5.0 (verbatim; constraints named per DM-10) · §16 MI11
-- requires:   0002 CREATE SCHEMA mainline · 0012 disposition_kind · 0013 virulence_class
-- seeds:      verticals/mainline/db/seeds/00-lattice/clearance_legal.sql (21 rows, 3 absent cells)
-- sqlstate:   23503 on fk_clearance, declared by mainline.disposition in band 0066-0071
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- THE HARDEST CONSTRAINT IN THE SCHEMA, AND THE SIMPLEST TABLE.
--
-- `disposition` composite-FKs to (virulence, kind) here. `virulence` on the disposition is
-- PROJECTED by a trigger from the blame closure — never supplied by the signer — so the pair being
-- checked is (what the ancestry actually is, what you are trying to sign). Three of the twenty-four
-- cells in that 4 × 6 grid have no row:
--
--     (blood_fatal, mechanism_absent)   (blood_fatal, accept_residual)   (blood_major, accept_residual)
--
-- The absence IS the mechanism. There is no flag, no warning, no reviewer queue, no "are you sure".
-- Signing one of those three is 23503 on `fk_clearance`, for every writer, including a DBA and
-- including the Managed-MCP insert path. A refusal you cannot configure your way out of at 3 a.m.
-- is a different species of control from one you can.
--
-- WHY IT IS DATA AND NOT A CHECK. Three reasons, and the third is the one that survives contact
-- with a customer:
--   1. `req_*` and `min_signer_rank` vary per cell and would otherwise be a CHECK expression
--      nobody can read.
--   2. `policy_version` makes the lattice versioned, so a disposition signed in 2027 can be
--      re-evaluated in 2033 against the lattice that was live when it was signed.
--   3. `approved_by_sub` is the CUSTOMER's officer, not ours. Contesting a cell — and
--      (blood_major, accept_residual) is the one a customer may reasonably contest — is then an
--      amendment with a signature and a date, not a code change and a deploy. We are not the
--      authority on what this company's officers may accept; we are the authority on the fact that
--      they decided it, when, and that nothing was signed outside it.
--
-- COUNSEL-GATED: no — but read this. The G0-gated files are 0066-0069 and 0086 (DM-17). This table
-- is counsel-INDEPENDENT because its DDL does not move whatever counsel decides; the SEED does,
-- and the conservative default (the three cells stay absent) lives in
-- verticals/mainline/db/seeds/00-lattice/clearance_legal.sql with its variant under
-- verticals/mainline/db/ext/disposition_ext/. A DDL fork per legal answer would be two schemas to
-- test and one to get wrong.
--
-- `max_ttl_hours` NULL means unbounded, which is legal only for the kinds that do not decay
-- (`applied`, `mitigated`, `mechanism_absent`, `escalated`). MI28 — a bounded window means bounded,
-- not merely present — is enforced on `disposition` in band 0066-0071 by reading this column, so
-- `max_ttl_hours_bounded_if_present` here is a precondition of that check being meaningful:
-- a zero or negative TTL would make "expires" arithmetic that has already elapsed.
--
-- `min_signer_rank` shares person.rank's 1-9 lattice by named CHECK. The two columns are compared
-- directly by `rank_floor` in the disposition band; if their domains ever diverged, the comparison
-- would still typecheck and would silently mean something else. That is precisely the failure this
-- constraint costs one line to prevent.

CREATE TABLE mainline.clearance_legal (
  virulence          mainline.virulence_class  NOT NULL,
  kind               mainline.disposition_kind NOT NULL,
  req_compensating   BOOL        NOT NULL DEFAULT false,
  req_second_signer  BOOL        NOT NULL DEFAULT false,
  req_foreign_org    BOOL        NOT NULL DEFAULT false,
  req_predicate      BOOL        NOT NULL DEFAULT false,
  req_reassert       BOOL        NOT NULL DEFAULT false,
  min_signer_rank    INT2        NOT NULL DEFAULT 1,
  max_ttl_hours      INT4        NULL,
  policy_version     STRING      NOT NULL,
  approved_by_sub    STRING      NOT NULL,   -- the CUSTOMER's officer, not ours
  approved_at        TIMESTAMPTZ NOT NULL,
  CONSTRAINT clearance_legal_pk PRIMARY KEY (virulence, kind),
  CONSTRAINT min_signer_rank_in_person_lattice CHECK (min_signer_rank BETWEEN 1 AND 9),
  CONSTRAINT max_ttl_hours_bounded_if_present CHECK (max_ttl_hours IS NULL OR max_ttl_hours > 0),
  CONSTRAINT policy_version_not_blank CHECK (policy_version <> ''),
  CONSTRAINT approved_by_sub_not_blank CHECK (approved_by_sub <> '')
);
