-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- seed:      00-lattice/subject_transition
-- table:     mainline.subject_transition   (migration 0017)
-- rows:      18 = 9 edges × 2 subject kinds
-- owner:     dm-foundation
-- MI:        MI10 — only legal state transitions occur
-- I:         I03 — epoch pin
-- determinism: no now(), no gen_random_uuid(); the key is entirely natural (DM-12)
--
-- THE PERMIT AND THE CHANGE_REQUEST CARRY THE IDENTICAL EDGE SET (S16). Not "similar": identical.
-- MI30 — a change_request merges only with zero open blocking checks — is a statement about the
-- same state machine the permit runs, and the moment the two alphabets diverge the repository
-- stops being a protected branch in the same sense the permit is.
--
-- The nine edges, and why each exists:
--
--   draft               → checks_materialised   recall has run
--   draft               → abandoned             the only way out of draft that is not forward
--   checks_materialised → checks_materialised   A LATER RECALL RUN FOUND MORE. Self-loop, on
--                                               purpose: a second precursor must not need a new
--                                               state to be recorded in
--   checks_materialised → dispositioned         every open obligation now carries a signature
--   dispositioned       → checks_materialised   THE LATE-ARRIVAL EDGE. SERIALIZABLE orders writes;
--                                               it does not prevent a precursor being inserted at
--                                               T+ε (§4.1 law 3). Without this edge the system
--                                               must either refuse the late precursor — losing the
--                                               fact — or merge over it
--   dispositioned       → merged                ← THE TRANSITION THE DATABASE REFUSES
--   merged              → suspended             merged, then stopped. Still merged, historically
--   merged              → closed                terminal
--   suspended           → closed                terminal
--
-- WHAT IS ABSENT IS THE DESIGN, exactly as in clearance_legal:
--   * nothing reaches `merged` except from `dispositioned`;
--   * nothing leaves `merged` for any pre-merge state, so a subject cannot be reopened to
--     work around the epoch pin;
--   * `abandoned` is reachable only from `draft` — you cannot abandon a subject that has
--     obligations, you must disposition or suspend it;
--   * there is no edge into `draft` from anywhere. Draft is where subjects are born.
--
-- Adding an edge here is a change to what the database will permit, so it belongs in a migration
-- with its own MI entry and its own red test — never in a hotfix to this file.

INSERT INTO mainline.subject_transition (subject_kind, from_state, to_state) VALUES
  ('permit',         'draft',               'checks_materialised'),
  ('permit',         'draft',               'abandoned'),
  ('permit',         'checks_materialised', 'checks_materialised'),
  ('permit',         'checks_materialised', 'dispositioned'),
  ('permit',         'dispositioned',       'checks_materialised'),
  ('permit',         'dispositioned',       'merged'),
  ('permit',         'merged',              'suspended'),
  ('permit',         'merged',              'closed'),
  ('permit',         'suspended',           'closed'),
  ('change_request', 'draft',               'checks_materialised'),
  ('change_request', 'draft',               'abandoned'),
  ('change_request', 'checks_materialised', 'checks_materialised'),
  ('change_request', 'checks_materialised', 'dispositioned'),
  ('change_request', 'dispositioned',       'checks_materialised'),
  ('change_request', 'dispositioned',       'merged'),
  ('change_request', 'merged',              'suspended'),
  ('change_request', 'merged',              'closed'),
  ('change_request', 'suspended',           'closed');
