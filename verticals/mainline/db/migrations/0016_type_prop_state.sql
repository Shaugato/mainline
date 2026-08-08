-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0016_type_prop_state.sql
-- CREATE TYPE mainline.prop_state — fleet propagation state
--
-- MI: MI23
-- I: I12
-- COUNSEL-GATED: no
-- RATIONALE: A lesson offered to a sister site is a proposal with a lifecycle, including
--            declined. Recording a decline is what stops fleet propagation from being a
--            broadcast: the sites that said no are part of the record, and their reasons
--            are citable the next time the same lesson arrives.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0010_types.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Ownership   ⟨V⟩ vertical
-- Cardinality 6 values, closed. Consumed inside CHECK constraints and
--             composite foreign keys, so a value added later is cheap and a value
--             renamed or removed later is not.

CREATE TYPE IF NOT EXISTS mainline.prop_state AS ENUM (
  'proposed',
  'already_present',
  'conflicted',
  'adopted',
  'declined',
  'revoked'
);
