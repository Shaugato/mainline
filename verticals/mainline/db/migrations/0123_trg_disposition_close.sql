-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0123_trg_disposition_close.sql
-- CREATE TRIGGER disposition_close — one signature closes exactly one obligation
--
-- MI: MI02, MI29, MI30
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: AFTER INSERT, because the disposition must survive every CHECK and every
--            foreign key on its own row before it is allowed to move a counter that governs
--            a merge. A gate closed by a disposition that was then refused would be a gate
--            closed by nothing.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0103 mainline.fn_disposition_close · 0066 mainline.disposition
--           · 0068 mainline.override_ledger
-- sqlstate: P0001 when the disposition names no gated subject; 23514 on the counter
--           non-negativity CHECK if one were ever closed twice.
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER disposition_close AFTER INSERT ON mainline.disposition
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_disposition_close();
