-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0011_type_subject_state.sql
-- CREATE TYPE trappoint_ref.subject_state — the gated-subject state machine alphabet
--
-- MI: MI10
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: A permit and a change request share ONE alphabet (finding S16). That is what
--            turns the claim from the permit is a protected branch into the repository is a
--            protected branch and the permit is one of its refs. Legal transitions over
--            this alphabet are data in subject_transition, so an illegal transition is
--            23503 and not an if-statement somebody can delete.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0010_types.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Ownership   ⟨K⟩ kernel — a vertical may never redefine this type
-- Cardinality 7 values, closed. Consumed inside CHECK constraints and
--             composite foreign keys, so a value added later is cheap and a value
--             renamed or removed later is not.

CREATE TYPE IF NOT EXISTS trappoint_ref.subject_state AS ENUM (
  'draft',
  'checks_materialised',
  'dispositioned',
  'merged',
  'suspended',
  'closed',
  'abandoned'
);
