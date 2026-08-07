-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- seed:      00-lattice/retention_class
-- table:     mainline.retention_class   (migration 0019)
-- rows:      8
-- owner:     dm-foundation
-- MI:        MI01 — evidentiary tables are append-only; destruction is a recorded, reviewed act
-- I:         I01
-- determinism: entirely natural keys and literals; no now(), no gen_random_uuid() (DM-12)
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS SEED IS A CONSERVATIVE DEFAULT SCHEDULE. IT IS NOT LEGAL ADVICE AND IT IS NOT A CUSTOMER'S
-- APPROVED SCHEDULE. Like `clearance_legal`, it is versioned data that the customer's records
-- authority signs off; unlike `clearance_legal` it has no `approved_by_sub` column, so the fact
-- that it is unapproved is recorded HERE, in the file, rather than in a row.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- ON THE CITATIONS. Exactly one row carries a pinpoint statutory citation — `notifiable_incident`,
-- taken verbatim from ARCHITECTURE §5.10, where the WHS Act's five-year record obligation for a
-- notifiable incident is the worked example. Every other row names its instrument in GENERAL terms
-- and says so. That is deliberate: a confidently wrong pinpoint citation in a product whose entire
-- proposition is evidentiary reliability is worse than an honest general one, and a records
-- authority who has to correct a specific section number learns less about our care than one who
-- reads "period pending your confirmation" and supplies it.
--
-- Where no statutory minimum was identified, the row says so in the basis rather than inventing
-- an instrument. `permit_to_work` is the clearest case: the seven years is a commercial default
-- borrowed from the general business-records period, and pretending it is a WHS obligation would
-- be a fabrication sitting in a table a court can read.
--
-- `min_years` IS A FLOOR, NEVER A CEILING. Nothing in MAINLINE deletes on a schedule: row-level
-- TTL is prohibited outside the three-table allowlist and schema `mainline` holds none of them.
-- These numbers gate the earliest moment a reviewed two-person destruction may be RECORDED, and
-- an open `legal_hold` overrides all of them unconditionally.
--
-- `privacy_rectification` is the one honest exception, and it is a visible row rather than an
-- operator's judgement call: min_years 0, two-person still TRUE. An individual's correction right
-- over a record with no evidentiary role is real, and the way to honour it without opening a hole
-- is to make it a named class that leaves a destruction_record like every other class does.
--
-- FORMATTING NOTE: every string literal below is written on ONE line, however long. Adjacent
-- string-literal concatenation across newlines is standard SQL, but this band was authored with no
-- CockroachDB cluster reachable to prove the lexer accepts it, and a seed that fails to parse in
-- an unattended provisioning run is a worse trade than a long line.

INSERT INTO mainline.retention_class
  (class_id, min_years, statutory_basis, destruction_requires_two_person) VALUES
  ('notifiable_incident', 5,
   'WHS Act s.38(7) — notifiable incident record',
   true),
  ('incident_blame_record', 30,
   'No single instrument. Retained for the longest period any identified limitation or statutory record obligation could require, because this is the class the product exists to protect: the event, its severity, and the blame edges that carry it into a control. Period pending the customer records authority.',
   true),
  ('custody_ledger', 30,
   'No single instrument. The ledger is the tamper-evidence layer; destroying it destroys the ability to prove that anything else was not destroyed, so it outlives everything it covers. Period pending the customer records authority.',
   true),
  ('health_monitoring', 30,
   'WHS Regulations — health monitoring records for hazardous chemicals and airborne contaminants. Pinpoint provision and period pending confirmation by the customer records authority; 30 years is the conservative default, not a determination.',
   true),
  ('exposure_monitoring', 30,
   'WHS Regulations — atmospheric and air monitoring results. Pinpoint provision and period pending confirmation by the customer records authority; 30 years is the conservative default, not a determination.',
   true),
  ('permit_to_work', 7,
   'No specific statutory minimum identified. Seven years mirrors the general business-records period in the Corporations Act 2001 (Cth) s.286(2) and is a commercial default, not a WHS obligation.',
   true),
  ('operational_telemetry', 2,
   'No statutory minimum. Held only while operationally useful. Destruction still writes a destruction_record, because a class with no obligation is not a class with no record.',
   true),
  ('privacy_rectification', 0,
   'Privacy Act 1988 (Cth) APP 13 — correction of personal information. Applies only to records with no evidentiary role; two-person review stays mandatory so that the exception is exercised visibly rather than quietly.',
   true);
