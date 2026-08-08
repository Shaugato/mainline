-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0017b_subject_transition_seed.sql
-- SEED mainline.subject_transition — 9 edges for each of 2 kinds
--
-- MI: MI10
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: Seeded as one statement so the edge set is atomic: a partially seeded
--            transition table refuses legal transitions and admits nothing illegal, which
--            is the failure mode hardest to notice because everything still looks safe. The
--            absent edges matter as much as the present ones.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0017_subject_transition.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- ABSENT AND DELIBERATE:
--   * nothing transitions INTO draft. A subject is drafted once.
--   * merged has no outward edge to checks_materialised or dispositioned. A merged
--     subject cannot re-enter the gate, which is the state-machine half of the epoch
--     pin: no obligation may be attached to a completed transition.
--   * closed and abandoned are terminal.

INSERT INTO mainline.subject_transition (subject_kind, from_state, to_state) VALUES
  ('permit', 'draft', 'checks_materialised'),   -- a subject becomes gated when its precursors are materialised
  ('permit', 'draft', 'abandoned'),   -- the only exit that skips the gate, and it merges nothing
  ('permit', 'checks_materialised', 'checks_materialised'),   -- re-materialisation: a new precursor arrives, the epoch bumps
  ('permit', 'checks_materialised', 'dispositioned'),   -- every open obligation now carries a signed disposition
  ('permit', 'dispositioned', 'checks_materialised'),   -- a precursor arrived after disposition; the gate re-opens
  ('permit', 'dispositioned', 'merged'),   -- THE TRANSITION THE DATABASE DEFENDS
  ('permit', 'merged', 'suspended'),   -- a merged subject can be stopped; it is never un-merged
  ('permit', 'merged', 'closed'),   -- the ordinary end of a merged subject
  ('permit', 'suspended', 'closed'),   -- a suspended subject closes; it does not return to merged
  ('change_request', 'draft', 'checks_materialised'),   -- a subject becomes gated when its precursors are materialised
  ('change_request', 'draft', 'abandoned'),   -- the only exit that skips the gate, and it merges nothing
  ('change_request', 'checks_materialised', 'checks_materialised'),   -- re-materialisation: a new precursor arrives, the epoch bumps
  ('change_request', 'checks_materialised', 'dispositioned'),   -- every open obligation now carries a signed disposition
  ('change_request', 'dispositioned', 'checks_materialised'),   -- a precursor arrived after disposition; the gate re-opens
  ('change_request', 'dispositioned', 'merged'),   -- THE TRANSITION THE DATABASE DEFENDS
  ('change_request', 'merged', 'suspended'),   -- a merged subject can be stopped; it is never un-merged
  ('change_request', 'merged', 'closed'),   -- the ordinary end of a merged subject
  ('change_request', 'suspended', 'closed');   -- a suspended subject closes; it does not return to merged
