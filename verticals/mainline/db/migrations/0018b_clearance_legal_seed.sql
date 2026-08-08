-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0018b_clearance_legal_seed.sql
-- SEED mainline.clearance_legal — 21 rows, three cells deliberately absent
--
-- MI: MI11
-- I: I10
-- COUNSEL-GATED: no
-- RATIONALE: Twenty-one rows out of a twenty-four cell product. The three that are missing
--            are the product: a missing row in a foreign-key target refuses, and the
--            refusal names this table rather than an application rule. approved_by_sub is
--            SEED so that every row is visibly awaiting a named officer of the customer,
--            and approved_at is a fixed literal so the schema-and-seed fingerprint is an
--            environment-parity gate rather than a clock reading.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0018_clearance_legal.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- DELIBERATELY ABSENT — three cells, each named, each for its own reason:
--
--   (blood_fatal, mechanism_absent)
--       There is no such thing as a control written by a fatality whose mechanism is
--       absent. If the mechanism has genuinely gone, the clause is retired through a
--       change request that inherits the same ancestry — not dismissed on a permit.
--
--   (blood_fatal, accept_residual)
--       Accepting residual risk on a control a death wrote is the exhibit that ends the
--       argument. There is no rank, no countersignature and no expiry that makes this
--       cell legal, so it is not a stricter row: it is no row.
--
--   (blood_major, accept_residual)
--       The one a customer may reasonably contest. It is versioned data with a named
--       approver, so contesting it is an amendment with a signature rather than a code
--       change — which is exactly the property this table exists to have.
--
-- Every absent cell fails as 23503 on the composite foreign key from `disposition`,
-- with the constraint name attached. The constraint name is the exhibit.

INSERT INTO mainline.clearance_legal
  (virulence, kind, req_compensating, req_second_signer, req_foreign_org,
   req_predicate, req_reassert, min_signer_rank, max_ttl_hours, policy_version,
   approved_by_sub, approved_at) VALUES
  ('routine', 'applied', false, false, false, false, false, 1, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('routine', 'mitigated', true , false, false, false, false, 1, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('routine', 'mechanism_absent', false, false, false, true , false, 1, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('routine', 'escalated', false, true , false, false, false, 1, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('routine', 'accept_residual', false, false, false, false, false, 2, 4380, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('routine', 'emergency_override', false, true , false, false, false, 3, 24, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('serious', 'applied', false, false, false, false, false, 2, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('serious', 'mitigated', true , false, false, false, false, 2, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('serious', 'mechanism_absent', false, false, false, true , true , 3, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('serious', 'escalated', false, true , false, false, false, 2, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('serious', 'accept_residual', false, true , false, false, true , 4, 2190, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('serious', 'emergency_override', false, true , true , false, false, 4, 24, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_major', 'applied', false, false, false, false, false, 3, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_major', 'mitigated', true , true , false, false, false, 3, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_major', 'mechanism_absent', false, true , true , true , true , 4, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_major', 'escalated', false, true , false, false, false, 3, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_major', 'emergency_override', false, true , true , false, false, 5, 12, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_fatal', 'applied', false, false, false, false, false, 4, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_fatal', 'mitigated', true , true , true , false, false, 4, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_fatal', 'escalated', false, true , false, false, false, 4, NULL, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z'),
  ('blood_fatal', 'emergency_override', false, true , true , false, false, 6, 12, 'cl-1.0', 'SEED', TIMESTAMPTZ '2026-08-05T00:00:00Z');
