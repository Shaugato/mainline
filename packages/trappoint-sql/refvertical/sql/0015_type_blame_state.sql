-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0015_type_blame_state.sql
-- CREATE TYPE trappoint_ref.blame_state — the lifecycle of a blame edge
--
-- MI: MI15
-- I: I05
-- COUNSEL-GATED: no
-- RATIONALE: Only active edges contribute to ancestral severity, and ancestry never
--            shrinks. Retiring an edge is a state transition with a record, not a delete,
--            so the closure that armed a check last year can still be reconstructed this
--            year.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0010_types.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Ownership   ⟨V⟩ vertical
-- Cardinality 4 values, closed. Consumed inside CHECK constraints and
--             composite foreign keys, so a value added later is cheap and a value
--             renamed or removed later is not.

CREATE TYPE IF NOT EXISTS trappoint_ref.blame_state AS ENUM (
  'active',
  'provisional',
  'dormant',
  'refuted'
);
