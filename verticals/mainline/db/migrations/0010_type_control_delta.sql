-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0010_type_control_delta.sql
-- CREATE TYPE mainline.control_delta — the control lattice
--
-- MI: MI23
-- I: I12
-- COUNSEL-GATED: no
-- RATIONALE: The direction a clause moved, and the only axis on which propagation across a
--            fleet is permitted. Only tightenings travel; a weakening is a local decision
--            with a local signature, so the ordering of these five values is what a fleet-
--            propagation CHECK compares against.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0010_types.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Ownership   ⟨V⟩ vertical
-- Cardinality 5 values, closed. Consumed inside CHECK constraints and
--             composite foreign keys, so a value added later is cheap and a value
--             renamed or removed later is not.

CREATE TYPE IF NOT EXISTS mainline.control_delta AS ENUM (
  'introduce',
  'strengthen',
  'restate',
  'weaken',
  'remove'
);
