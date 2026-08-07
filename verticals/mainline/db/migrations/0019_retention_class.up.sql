-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: The retention schedule must be data carrying its own statutory basis, because "why is this row still here in 2041" and "why is this row gone" are both questions with a legal answer, and an answer that lives in a runbook is an answer that was not given under oath.
--
-- migration:  0019_retention_class
-- band:       0001-0023 · dm-foundation
-- statements: 1
-- source:     ARCHITECTURE.md §5.10 (verbatim; constraints named per DM-10) · §11.6
-- requires:   0002 CREATE SCHEMA mainline
-- seeds:      verticals/mainline/db/seeds/00-lattice/retention_class.sql
-- sqlstate:   23503 on destruction_record.class_id (band 0072-0129)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- THE SCHEDULE IS DATA, WITH ITS STATUTE. `destruction_record` FKs to this table, so a permitted
-- deletion cannot be recorded without naming the class it was performed under — and a deletion
-- that is not recorded is not permitted, because row-level TTL is prohibited outside the
-- three-table allowlist and schema `mainline` has none of the three.
--
-- WHAT THIS TABLE IS NOT. It is not a licence to delete. Row-level TTL's verified limitation is
-- that expired rows are not filtered from query results, including UPDATE and DELETE (F5), which
-- alone disqualifies it for evidentiary data; the Crimes (Document Destruction) Act 2006 (Vic)
-- supplies the reason that matters more. Permitted deletion is a reviewed two-person job that
-- writes a `destruction_record` with a hash tombstone: the tombstone proves policy, not panic.
--
-- `destruction_requires_two_person` defaults TRUE and is per-class rather than global because the
-- one honest exception — an individual's rectification right over a record with no evidentiary
-- role — should be recorded as a class with its own basis, not smuggled in by an operator with a
-- justified-sounding reason. Making the exception a visible row is the point.
--
-- Crypto-shredding is document destruction. The KMS key policy denies ScheduleKeyDeletion and
-- DisableKey to every principal except a two-person break-glass role, unconditionally while any
-- `legal_hold` row is open. A recreated key means yesterday's ledger is unreadable, which is the
-- same offence committed by accident.
--
-- SEED HONESTY: the rows in seeds/00-lattice/retention_class.sql are a CONSERVATIVE DEFAULT
-- SCHEDULE. `min_years` and `statutory_basis` are versioned data the customer's records authority
-- signs off, exactly like `clearance_legal.approved_by_sub`. The seed says so in its own header
-- and does not pretend to be legal advice.

CREATE TABLE mainline.retention_class (
  class_id                        STRING NOT NULL,
  min_years                       INT4   NOT NULL,
  statutory_basis                 STRING NOT NULL,   -- e.g. 'WHS Act s.38(7) — notifiable incident record'
  destruction_requires_two_person BOOL   NOT NULL DEFAULT true,
  CONSTRAINT retention_class_pk PRIMARY KEY (class_id),
  CONSTRAINT min_years_non_negative CHECK (min_years >= 0),
  CONSTRAINT statutory_basis_stated CHECK (statutory_basis <> '')
);
