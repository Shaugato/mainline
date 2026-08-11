-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
--
-- MI: MI01
-- I: I15
-- COUNSEL-GATED: yes
-- RATIONALE: SEC-3 permits a derived authority level about a named person only if it is computed from a pre-committed, versioned, customer-signed policy that PREDATES the data it scores. This table is that policy, as a row. It is what makes "counsel-gated" a state the database requires rather than a state the project remembers being in: with no row here, `mainline_meas.standing` has no insertable value at all, because `standing.policy_id` is NOT NULL and references this key. The two CHECKs are the pre-dating, and they are named after what they assert rather than after the column they touch, because the name is what a reader meets in the refusal.
--
-- migration:  0089a_person_measure_policy
-- domain:     producers (measurement zone)
-- band:       0080-0089z · recall · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- invariants: MI01 — evidentiary tables are append-only. The weld is 0149b
--                    (`mainline.fn_refuse_mutation`, migration 0107), and it is not
--                    optional here: see THE WELD IS THE ARGUMENT below.
--             I15  — the allegation firewall, condition (2). A score derived from a policy
--                    that did not exist when the data was made is an allegation.
-- source:     ARCHITECTURE.md §5.7 (verbatim, line 1543) — every column name, type,
--             nullability and predicate is transcribed, not chosen · §11.5 (SEC-3
--             conditions 1-4) · spec/invariants/I15-allegation-firewall.md ·
--             docs/adr/0001-g0-counsel.md
-- requires:   0002 CREATE SCHEMA mainline_meas (RENDERED; template 0001_schemas.sql.j2) ·
--             0020 mainline.adm_decision_class (the APP 1.7 register; FK target)
-- sqlstate:   23514 on the `measure_class` vocabulary, on `notice_precedes_effect`, on
--             `instrument_precedes_effect`, and on either digest-size constraint ·
--             23503 on an `adm_class_id` that is not a registered decision class ·
--             P0001 on UPDATE or DELETE once 0149b lands
-- forward-only; no .down.sql exists at or below the protected floor (DM-14). Under MR-5
--             there is no .up.sql either: the suffix named a counterpart that is illegal
--             by construction.
--
-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md
--
-- ═════════════════════════════════════════════════════════════════════════════
-- M10 SHIPS INERT, AND THE INERTNESS IS ITSELF A DATED OBJECT
-- ═════════════════════════════════════════════════════════════════════════════
-- ADR 0001 records that G0 was not sought and the pre-committed conservative
-- default was executed. Under that default, per-approver dwell timing is OFF and
-- "any per-person measurement family remains opt-in behind `person_measure_policy`
-- and is not enabled in the demo or in any default configuration". §11.5 says the
-- same thing from the other side: M10 ships INERT — W = 1.0 for every hazard
-- class, i.e. quorum = one signature = today's behaviour — with the inertness
-- itself a dated object.
--
-- THIS TABLE IS THAT DATED OBJECT, and shipping it empty is the whole point.
-- An empty `person_measure_policy` is not a stub and not a placeholder: it is the
-- deployment's statement, in the schema, that no per-person measurement family is
-- authorised, made in a form that a third party can query and a court can read.
-- Activating one is then an INSERT with an officer's name, an approval date, a
-- notice date, a jurisdiction and two digests on it — a discoverable, dated act.
--
-- The alternative — leave the table out until counsel answers — makes the
-- activation a DEPLOYMENT rather than a row, and a deployment leaves no record of
-- who authorised it or when. That is why the conservative reading ships the DDL
-- and withholds the data, rather than withholding the DDL.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- THE WELD IS THE ARGUMENT (0149b), AND IT IS NOT DECORATION
-- ═════════════════════════════════════════════════════════════════════════════
-- SEC-3's entire case is that the authorising instrument PREDATES the data it
-- scores. `instrument_precedes_effect` and `notice_precedes_effect` assert exactly
-- that — but a CHECK constrains a row, and an UPDATE produces a new row that also
-- satisfies the CHECK. If `approved_at`, `notice_given_at` or `instrument_sha256`
-- can be edited after the fact, then conditions (2) and (3) are UNFALSIFIABLE:
-- every policy row is, at the moment you look at it, correctly ordered, and no
-- reader can distinguish one that was ordered when it was written from one that
-- was reordered afterwards.
--
-- 0149b welds this table append-only against `mainline.fn_refuse_mutation` (0107).
-- A superseding instrument is a NEW ROW with a new `policy_id`, and the pair of
-- rows is the record of what changed. That is the difference between a policy
-- register and a policy document.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- WHY `adm_class_id` CARRIES A FOREIGN KEY, AND WHY IT IS STILL NULLABLE
-- ═════════════════════════════════════════════════════════════════════════════
-- §5.7 annotates this column "APP 1.7 automated-decision disclosure" and types it
-- `STRING NULL`. `mainline.adm_decision_class` (0020) keys on
-- `class_id STRING NOT NULL PRIMARY KEY` — checked against
-- db/seeds/00-lattice/adm_decision_class.sql, whose six rows are natural string
-- keys (`recall_admission`, `blocking_check_materialisation`, `cue_synthesis`,
-- `clearance_legality`, `override_escalation`, `standing_quorum`). The key types
-- match exactly, so the reference is expressible and it is taken.
--
-- What it buys is the drift the seed's own header names: "a privacy policy
-- paragraph and the system it describes are usually maintained by different
-- people on different cycles, and the gap between them is the finding". Both
-- `mainline_qa.v_standing_components` and `mainline_qa.v_my_record` disclose
-- `adm_class_id` to a reader — the QA function and the scored person respectively
-- — and an unregistered string in that column would disclose a decision class the
-- APP 1.7 register does not contain. 23503 at write time is a better answer than
-- a dangling identifier at disclosure time.
--
-- It stays NULLABLE because §5.7 types it so and because not every measurement
-- family is an automated decision about an individual: `calibration` measures the
-- system, not a person. A NOT NULL here would force an inapplicable register entry
-- to be invented, and an invented register entry is the exact defect the register
-- exists to expose. FK on a NULL column is MATCH SIMPLE and admits the NULL.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- TWO DIGEST-SIZE CONSTRAINTS, BECAUSE BOTH DIGESTS ARE READ BACK AS HEX
-- ═════════════════════════════════════════════════════════════════════════════
-- `0171_v_standing_components` returns `encode(instrument_sha256, 'hex')` and
-- `0172_v_my_record` returns both `encode(instrument_sha256, 'hex')` and
-- `encode(notice_sha256, 'hex')`. `encode()` will happily render four bytes as
-- eight hex characters, so a truncated digest disclosed to the scored person
-- reads as a digest and verifies against nothing. The tree's convention for this
-- is `CHECK (length(<col>) = 32)` — sixteen other migrations carry it — and
-- `length()` over BYTES on CockroachDB v26.2.5 is the byte count, measured, not
-- the character count.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- WHAT THIS TABLE IS NOT
-- ═════════════════════════════════════════════════════════════════════════════
-- 1. IT IS NOT A CONSENT RECORD. `notice_given_at` and `notice_sha256` record that
--    notice was GIVEN and what was given, which is what a workplace-surveillance
--    statute asks. Whether notice was adequate, and whether consent was required
--    instead, is a legal question about a deployment and this schema does not
--    answer it (spec/invariants/I15 NOT CLAIMED, item 3).
-- 2. IT DOES NOT MAKE THE MEASUREMENT FAIR. It makes it pre-committed,
--    recomputable and disclosable. Fairness is argued FROM those three properties;
--    it is not supplied by them.
-- 3. IT IS NOT OURS TO SIGN. `approved_by_sub` is the CUSTOMER's officer — §5.7
--    says so in a comment on the column — because a measurement authority the
--    vendor grants itself is not an authority.
--
-- ═════════════════════════════════════════════════════════════════════════════
-- A NOTE ON CONSTRAINT NAMING, SO THE DEPARTURE IS DECLARED AND NOT DISCOVERED
-- ═════════════════════════════════════════════════════════════════════════════
-- The column list, the types, the nullability and the predicates are verbatim from
-- §5.7. The one departure is that the PRIMARY KEY and the FOREIGN KEY are written
-- as NAMED table-level constraints rather than inline, following 0080, 0084, 0086
-- and 0049z. The refusal exhibit IS the constraint name; CockroachDB's generated
-- name for an inline constraint is not a contract, and a conformance case that
-- asserts an exhibit cannot assert a generated one. `notice_precedes_effect` and
-- `instrument_precedes_effect` keep the names §5.7 gave them, unchanged. The
-- closed `measure_class` vocabulary stays inline and unnamed, which is what 0084
-- and 0086 do with their vocabularies.

CREATE TABLE mainline_meas.person_measure_policy (
  policy_id           UUID        NOT NULL DEFAULT gen_random_uuid(),
  measure_class       STRING      NOT NULL CHECK (measure_class IN
    ('deliberation','particularity','standing','calibration','peer_prediction')),
  instrument_sha256   BYTES       NOT NULL,      -- the customer's signed WHS/QA policy document
  instrument_title    STRING      NOT NULL,
  approved_by_sub     STRING      NOT NULL,      -- the customer's officer, not ours
  approved_at         TIMESTAMPTZ NOT NULL,
  notice_given_at     TIMESTAMPTZ NOT NULL,      -- surveillance: notice is a precondition
  notice_sha256       BYTES       NOT NULL,
  notice_jurisdiction STRING      NOT NULL,
  adm_class_id        STRING      NULL,          -- APP 1.7 automated-decision disclosure
  effective_from      TIMESTAMPTZ NOT NULL,
  effective_to        TIMESTAMPTZ NULL,
  CONSTRAINT person_measure_policy_pk PRIMARY KEY (policy_id),
  CONSTRAINT instrument_sha256_is_a_digest CHECK (length(instrument_sha256) = 32),
  CONSTRAINT notice_sha256_is_a_digest     CHECK (length(notice_sha256) = 32),
  CONSTRAINT notice_precedes_effect        CHECK (notice_given_at <= effective_from),
  CONSTRAINT instrument_precedes_effect    CHECK (approved_at    <= effective_from),
  CONSTRAINT fk_adm_class FOREIGN KEY (adm_class_id)
    REFERENCES mainline.adm_decision_class (class_id)
);
