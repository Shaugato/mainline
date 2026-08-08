-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0012_type_disposition_kind.sql
-- CREATE TYPE mainline.disposition_kind — the disposition constructors
--
-- MI: MI11
-- I: I10
-- COUNSEL-GATED: no
-- RATIONALE: mechanism_absent, never not_applicable. The verdict a signer reaches is a
--            constructor with a name that survives cross-examination, and the legal set of
--            constructors is a function of ancestral severity held in clearance_legal.
--            Renaming one of these values would silently re-open a cell the lattice
--            deliberately leaves empty.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0010_types.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Ownership   ⟨K⟩ kernel — a vertical may never redefine this type
-- Cardinality 6 values, closed. Consumed inside CHECK constraints and
--             composite foreign keys, so a value added later is cheap and a value
--             renamed or removed later is not.

CREATE TYPE IF NOT EXISTS mainline.disposition_kind AS ENUM (
  'applied',
  'mitigated',
  'mechanism_absent',
  'escalated',
  'accept_residual',
  'emergency_override'
);
