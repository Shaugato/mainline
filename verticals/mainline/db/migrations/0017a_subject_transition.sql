-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0017a_subject_transition.sql
-- CREATE TABLE mainline.subject_transition — the legal edge set as data
--
-- MI: MI10
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: A transition table is a foreign-key target, and a foreign-key target
--            constrains every writer including the one nobody anticipated. Holding the
--            state machine as data rather than as code is what makes an illegal transition
--            23503 with a constraint name attached, which is the exhibit; an application-
--            level guard produces a stack trace, which is not.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0017_subject_transition.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Kinds admitted: permit, change_request — declared by the binding, not by this template.
-- Every kind carries the identical edge set (finding S16).

CREATE TABLE mainline.subject_transition (
  subject_kind STRING NOT NULL,
  from_state   mainline.subject_state NOT NULL,
  to_state     mainline.subject_state NOT NULL,
  CONSTRAINT subject_transition_kind_known
    CHECK (subject_kind IN ('permit', 'change_request')),
  CONSTRAINT pk_subject_transition PRIMARY KEY (subject_kind, from_state, to_state)
);
