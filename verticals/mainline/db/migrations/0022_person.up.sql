-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI27, MI01
-- I: I09
-- COUNSEL-GATED: no
-- RATIONALE: Without this table six constraints and the entire deliberation measurement are decorative — a disposition's rank, org and competency are PROJECTIONS of a person row, and a missing person row must refuse (MI27), which is only expressible if there is a person table to be missing from.
--
-- migration:  0022_person
-- band:       0001-0023 · dm-foundation
-- statements: 1
-- source:     ARCHITECTURE.md §5.1 (verbatim; constraints named per DM-10) · §16 MI27 · S7
-- requires:   0002 CREATE SCHEMA mainline
-- seeds:      none. We never mint an identity for a human.
-- sqlstate:   23514 on rank_in_lattice / enrolment_assurance_closed;
--             P0001 from fn_disposition_project (band 0130-0199) when no person row exists
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- IDENTITY FIRST (S7). This table is numbered before the spine, the blame DAG and the gate because
-- six later constraints read it and a constraint whose authoritative table arrives afterwards is a
-- constraint that was decorative for the length of the build.
--
-- WE NEVER MINT AN IDENTITY FOR A HUMAN. Rows here are written by the IdP sync and mirror the
-- customer's HR/LMS record. `identity_source` is the IdP issuer URL; `enrolment_assurance` is
-- THEIR assertion about how the person was verified, recorded as theirs. MAINLINE does not
-- identity-proof anyone, and saying we do is on the must-not-claim list (§11.7).
--
-- APPEND-ONLY, AND THE PRIMARY KEY IS THE MECHANISM. `PRIMARY KEY (signer_sub, effective_from
-- DESC)` makes the table a temporal series: a promotion, a competency renewal or a separation is
-- a NEW ROW, never an UPDATE. The DESC ordering means the current row for a signer is the first
-- one the primary index yields — the read the projection triggers perform on every disposition,
-- so it is the read that must be cheap. CockroachDB honours ASC/DESC in a PRIMARY KEY definition,
-- which is why this shape is available at all; PostgreSQL would need a separate index.
--
-- WHY THIS MATTERS AT A GATE (CF-19). A signer supplies `signer_rank = 6` on a disposition. The
-- projection trigger reads THIS table, finds the person's live rank is 2, overwrites the supplied
-- value, and `rank_floor` then returns 23514 against `clearance_legal.min_signer_rank`. The client
-- is not consulted, warned or trusted. If no person row exists at all, the trigger RAISEs P0001
-- rather than defaulting — a missing authority is a refusal, not a zero.
--
-- `competency_sha256` and `competency_source_id` are what make the snapshot admissible: the JSONB
-- is a copy, and a copy with no pointer to the primary record and no digest of it is hearsay
-- about a ticket. `competency_snapshot` is FROZEN at the moment the row is written, which is what
-- lets DM-4 replace the JSONB-operator-in-a-CHECK problem with a trigger-projected
-- `has_isolation_authority BOOL` written by the same trigger that freezes the snapshot.
--
-- `rank` is a 1-9 lattice shared by `clearance_legal.min_signer_rank`; the two are compared
-- directly, and both carry the same named CHECK so the domains cannot silently diverge.
--
-- `separated_at` is nullable and is NOT a delete. A person who left the company in 2028 still
-- signed what they signed in 2027, and the record must still name them. Revoking their credential
-- (0023) never invalidates history either.
--
-- NO FOREIGN KEY FROM signing_credential.signer_sub TO HERE, deliberately: this table's primary
-- key is composite (signer_sub, effective_from), so a single-column reference would require a
-- separate UNIQUE index on signer_sub — which would be false, because a signer has many rows by
-- design. The binding is enforced at enrolment by the service and asserted by the projection
-- triggers, and it is recorded here so that the absence reads as a decision rather than an
-- oversight.

CREATE TABLE mainline.person (                    -- append-only; written by the IdP sync
  signer_sub           STRING      NOT NULL,
  effective_from       TIMESTAMPTZ NOT NULL,
  org                  STRING      NOT NULL,
  rank                 INT2        NOT NULL,
  competency_source_id UUID        NOT NULL,      -- the HR/LMS record this row mirrors
  competency_sha256    BYTES       NOT NULL,
  competency_snapshot  JSONB       NOT NULL,      -- authorisations, tickets, expiries. FROZEN.
  identity_source      STRING      NOT NULL,      -- IdP issuer URL
  enrolment_assurance  STRING      NOT NULL,
  separated_at         TIMESTAMPTZ NULL,
  CONSTRAINT person_pk PRIMARY KEY (signer_sub, effective_from DESC),
  CONSTRAINT rank_in_lattice CHECK (rank BETWEEN 1 AND 9),
  CONSTRAINT enrolment_assurance_closed CHECK (
    enrolment_assurance IN ('self_asserted', 'in_person_verified', 'hr_system_of_record')),
  CONSTRAINT signer_sub_stated CHECK (signer_sub <> ''),
  CONSTRAINT identity_source_stated CHECK (identity_source <> '')
);
