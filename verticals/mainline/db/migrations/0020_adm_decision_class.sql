-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01
-- I: I15
-- COUNSEL-GATED: no
-- RATIONALE: APP 1.7 is live from 10 December 2026 and requires a privacy policy to describe the kinds of automated decisions that use personal information and their effect, so the register of those kinds must be a queryable, dated, diff-able table rather than a paragraph on a website that nobody can prove was current.
--
-- migration:  0020_adm_decision_class
-- band:       0019-0020a · dm-foundation · AUTHORED
--             Allocated by verticals/mainline/db/migrations.allocation.toml, which is the
--             authority (MR-6 lock 1); the prose tables in the reconciliation ruling are its
--             rendering. `adm_decision_class` is VERTICAL, not substrate (MR-2): the APP 1.7
--             register is MAINLINE's disclosure obligation, not a TRAPPOINT conformance
--             object, so it is authored here rather than emitted from a template.
-- statements: 1
-- source:     ARCHITECTURE.md §5.10 (verbatim; constraints named per DM-10) · §11.5 (SEC-3)
-- requires:   0001a CREATE SCHEMA mainline  (RENDERED; template 0001_schemas.sql.j2)
--             0008a ALTER SCHEMA mainline OWNER TO mainline_owner (RENDERED)
-- seeds:      verticals/mainline/db/seeds/00-lattice/adm_decision_class.sql
-- sqlstate:   —  (this table refuses nothing; it is a disclosure register)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5 there
--             is no .up.sql either: the suffix named a counterpart that is illegal by
--             construction, and `discover()` raises on .down.sql.
--
-- MI CITATION, HONESTLY. This file cites MI01 because the register must be append-only like every
-- other evidentiary table, and I15 (the allegation firewall) because the register is what makes
-- I15 auditable from outside: if a decision class here declares `personal_info_used` non-empty,
-- SEC-3's four conditions apply to it and the scored person must be able to obtain their own score
-- and its derivation. There is no MI whose refusal this table implements, and pretending otherwise
-- would be the kind of citation-padding the catalogue exists to prevent.
--
-- WHY A REGISTER AT ALL. The Attribution Rule (SEC-3) permits MAINLINE to persist a derived
-- characterisation of a named person only if it (1) is a precondition of a state transition the
-- database enforces, (2) is computed from a pre-committed, versioned, signed customer policy that
-- predates the data it scores, (3) is recomputable from primary facts by a third party, and (4)
-- the scored person can obtain their own score and its derivation. Conditions (2) and (4) are
-- unprovable without a dated register of what the automated decisions ARE. This table is that
-- register, and `disclosure_text` is the sentence the customer's privacy policy actually carries —
-- stored next to the decision so the two cannot drift.
--
-- `personal_info_used STRING[]` is empty for most classes and that is the interesting case: the
-- kernel's refusal is computed from blame ancestry and control deltas, not from anyone's identity.
-- M10 ships INERT (W = 1.0 for every hazard class, quorum = one signature = today's behaviour) and
-- the inertness is itself a dated object. A register with three empty arrays and one populated one
-- is a stronger disclosure than a vague paragraph claiming less.

CREATE TABLE mainline.adm_decision_class (
  class_id             STRING   NOT NULL,
  description          STRING   NOT NULL,
  personal_info_used   STRING[] NOT NULL,   -- empty array = this decision reads no personal information
  effect_on_individual STRING   NOT NULL,
  disclosure_text      STRING   NOT NULL,   -- the sentence the customer's privacy policy carries
  CONSTRAINT adm_decision_class_pk PRIMARY KEY (class_id),
  CONSTRAINT description_stated CHECK (description <> ''),
  CONSTRAINT effect_stated CHECK (effect_on_individual <> ''),
  CONSTRAINT disclosure_text_stated CHECK (disclosure_text <> '')
);
