-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0131_trg_cr_merge_gate.sql
-- CREATE TRIGGER cr_merge_gate ON trappoint_ref.change_request — the weld
--
-- MI: MI30
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: A gate function nothing calls is a comment. This is the weld, and its WHEN
--            clause is the acyclicity argument: every obligation trigger updates this same
--            row, so a merge gate without the restriction would re-enter on every
--            materialised obligation and would be evaluated in states it was never designed
--            for. Written in the trigger definition rather than as an early return in the
--            body, because a reader of SHOW CREATE TABLE can see this one and a future edit
--            cannot quietly delete it.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0130_triggers_merge_gate.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- SUBJECT: change_request. Fires only on the transition INTO 'merged', and only
-- from a state that is not already 'merged' — so a re-merge of an already
-- merged subject does not re-run the gate. That second conjunct is not redundant with
-- the first: `UPDATE … SET state = 'merged'` against a row already in
-- that state is a legal statement, and MI09 (at most one merge per subject) is
-- enforced by merge_record's primary key rather than by this clause.
--
-- BEFORE, not AFTER. The function returns NEW and the table's own CHECK constraints
-- are then evaluated on the returned row — measured in that order on v26.2.5, which
-- is what makes conformance case CF-01 produce `23514` on
-- `cr_gate_closed_when_merged` rather than a P0001 from the trigger. An AFTER trigger
-- would fire only once the CHECKs had already passed, which would make the
-- re-derivation unable to refuse anything at all.

CREATE TRIGGER cr_merge_gate BEFORE UPDATE ON trappoint_ref.change_request
  FOR EACH ROW WHEN ((NEW).state = 'merged'
                     AND (OLD).state <> 'merged')
  EXECUTE FUNCTION trappoint_ref.fn_cr_merge_gate();
