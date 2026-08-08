-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0014_type_blame_basis.sql
-- CREATE TYPE mainline.blame_basis — the evidential force of a blame edge
--
-- MI: MI13
-- I: I11
-- COUNSEL-GATED: no
-- RATIONALE: An inferred link is a claim about the past. Making it block a permit converts
--            every model error directly into a rubber stamp, and rubber stamps are the
--            discoverable exhibit that ends the argument. inferred_semantic is therefore a
--            value the active state can never accompany.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0010_types.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Ownership   ⟨V⟩ vertical
-- Cardinality 4 values, closed. Consumed inside CHECK constraints and
--             composite foreign keys, so a value added later is cheap and a value
--             renamed or removed later is not.

CREATE TYPE IF NOT EXISTS mainline.blame_basis AS ENUM (
  'asserted_document',
  'asserted_human',
  'derived_documentary',
  'inferred_semantic'
);
