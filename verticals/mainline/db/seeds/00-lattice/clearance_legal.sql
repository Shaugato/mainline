-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- seed:      00-lattice/clearance_legal   ← THE CONSERVATIVE DEFAULT (DM-17)
-- table:     mainline.clearance_legal     (migration 0018)
-- rows:      21 present, 3 DELIBERATELY ABSENT out of the 4 × 6 grid
-- owner:     dm-foundation
-- MI:        MI11 — no disposition kind dismisses a fatality-written control
-- I:         I10 — typed clearance
-- determinism: `approved_at` is the FIXED literal '2026-08-05T00:00:00Z', never now() (DM-12).
--              The schema+seed fingerprint is the dev/demo/prod parity gate, and a now() in a
--              seed makes parity unprovable — the same twenty-one rows would hash differently in
--              every environment, so the one artefact that proves the demo cluster and the
--              production cluster hold the same lattice would prove nothing.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--                     THE THREE CELLS THAT ARE NOT HERE ARE THE PRODUCT
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
--     (blood_fatal, mechanism_absent)     (blood_fatal, accept_residual)     (blood_major, accept_residual)
--
-- `disposition` composite-FKs to (virulence, kind). `virulence` on the disposition is PROJECTED
-- from the blame closure by a trigger and is never supplied by the signer. So the pair being
-- checked is (what this clause's blame ancestry actually is, what you are trying to sign). If the
-- ancestry contains a fatality, there is NO ROW here for "the mechanism cannot arise" and NO ROW
-- for "we accept the residual risk". The INSERT returns 23503 on `fk_clearance`.
--
-- Not a warning. Not a flagged event. Not a reviewer queue. Not an "are you sure?". A refusal,
-- for every writer, including a DBA and including the Managed-MCP insert path — and one that no
-- amount of pressure at 3 a.m. can be talked out of, because there is no party to talk to.
--
-- (blood_major, accept_residual) is the one a customer may reasonably contest, and that is exactly
-- why the lattice is DATA with `policy_version` and `approved_by_sub`: contesting it is an
-- amendment with a named approver and a date, not a code change and a deploy. We are not the
-- authority on what this company's officers may accept. We are the authority on the fact that
-- they decided it, when, and that nothing was ever signed outside it.
--
-- COUNSEL GATE G0 (DM-17). This file IS the conservative default: the three cells stay absent.
-- The switchable surface is verticals/mainline/db/ext/disposition_ext/, not a DDL fork — a DDL
-- fork per legal answer is two schemas to test and one to get wrong. If counsel rules otherwise,
-- a variant seed lands there with its own policy_version; migration 0018 does not move.
--
-- `approved_by_sub = 'SEED'` IS A PLACEHOLDER AND A FINDING. It means "no customer officer has
-- approved this lattice yet". A production cluster still carrying 'SEED' has an unapproved legal
-- surface, and the day-1 verification script is where that must surface as a failure rather than
-- as a row nobody read. It is left visible here rather than filled with a plausible-looking name,
-- because a fabricated approver is the single worst row this table could contain.
--
-- READING THE COLUMNS:
--   req_compensating   a compensating control must be cited (mitigated, at every virulence)
--   req_second_signer  a DIFFERENT credential must countersign — which is what defeats the
--                      shared-tablet workaround, since a countersignature means a different key
--   req_foreign_org    the second signer must come from another organisation. This is the
--                      contractor-marking-their-own-homework control
--   req_predicate      a `mechanism_predicate` row must be cited: a falsifiable, re-verifiable
--                      factual assertion about the plant. This is what makes `mechanism_absent`
--                      a claim that can be proven wrong rather than a dismissal
--   req_reassert       the disposition must be re-asserted on a schedule; it does not persist
--   min_signer_rank    compared directly against the PROJECTED person.rank, never the claimed one
--   max_ttl_hours      NULL = does not expire. A number = MI28, bounded means bounded
--
-- The escalation across virulence bands is the shape to read: at `routine`, accept_residual needs
-- rank 2 and 4380 hours (six months). At `serious` it needs rank 4, a second signer, a
-- re-assertion, and 2190 hours. At `blood_major` and `blood_fatal` it does not exist.
-- `emergency_override` never has a NULL TTL at any band — 24 hours at routine and serious,
-- 12 at both blood bands — because an emergency that has lasted a week is not an emergency.

INSERT INTO mainline.clearance_legal
  (virulence, kind, req_compensating, req_second_signer, req_foreign_org,
   req_predicate, req_reassert, min_signer_rank, max_ttl_hours, policy_version,
   approved_by_sub, approved_at) VALUES
  ('routine',     'applied',            false, false, false, false, false, 1, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('routine',     'mitigated',          true,  false, false, false, false, 1, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('routine',     'mechanism_absent',   false, false, false, true,  false, 1, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('routine',     'escalated',          false, true,  false, false, false, 1, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('routine',     'accept_residual',    false, false, false, false, false, 2, 4380, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('routine',     'emergency_override', false, true,  false, false, false, 3, 24,   'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('serious',     'applied',            false, false, false, false, false, 2, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('serious',     'mitigated',          true,  false, false, false, false, 2, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('serious',     'mechanism_absent',   false, false, false, true,  true,  3, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('serious',     'escalated',          false, true,  false, false, false, 2, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('serious',     'accept_residual',    false, true,  false, false, true,  4, 2190, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('serious',     'emergency_override', false, true,  true,  false, false, 4, 24,   'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_major', 'applied',            false, false, false, false, false, 3, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_major', 'mitigated',          true,  true,  false, false, false, 3, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_major', 'mechanism_absent',   false, true,  true,  true,  true,  4, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_major', 'escalated',          false, true,  false, false, false, 3, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_major', 'emergency_override', false, true,  true,  false, false, 5, 12,   'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_fatal', 'applied',            false, false, false, false, false, 4, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_fatal', 'mitigated',          true,  true,  true,  false, false, 4, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_fatal', 'escalated',          false, true,  false, false, false, 4, NULL, 'cl-1.0', 'SEED', '2026-08-05T00:00:00Z'),
  ('blood_fatal', 'emergency_override', false, true,  true,  false, false, 6, 12,   'cl-1.0', 'SEED', '2026-08-05T00:00:00Z');

-- DELIBERATELY ABSENT, and asserted absent by
-- tests/integration/schema/test_mi_foundation.py::test_clearance_lattice_absent_cells:
--   ('blood_fatal', 'mechanism_absent',  …)   ← there is no "the mechanism cannot arise" over a death
--   ('blood_fatal', 'accept_residual',   …)   ← there is no "we accept it" over a death
--   ('blood_major', 'accept_residual',   …)   ← the cell a customer may reasonably contest
