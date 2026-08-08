-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0013_type_virulence_class.sql
-- CREATE TYPE mainline.virulence_class — the ancestral virulence band
--
-- MI: MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: Derived from BLAME ANCESTRY, never from the changes declared risk. This type
--            is banded exactly once, in the blame closure, and every downstream use is a
--            projection of that banding. The moment a writer can choose its own virulence,
--            the gate is enforcing a claim the writer made about itself.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0010_types.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Ownership   ⟨K⟩ kernel — a vertical may never redefine this type
-- Cardinality 4 values, closed. Consumed inside CHECK constraints and
--             composite foreign keys, so a value added later is cheap and a value
--             renamed or removed later is not.

CREATE TYPE IF NOT EXISTS mainline.virulence_class AS ENUM (
  'routine',
  'serious',
  'blood_major',
  'blood_fatal'
);
