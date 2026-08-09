-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0120_trg_check_project.sql
-- CREATE TRIGGER check_project — the projection becomes true here
--
-- MI: MI25
-- I: I02
-- COUNSEL-GATED: no
-- RATIONALE: The function at 0100 is inert until it is attached. BEFORE INSERT because the
--            projection must be written onto NEW before the row lands and before any CHECK
--            over it is evaluated; FOR EACH ROW because the question is about one clause
--            version and one closure. This is the weld that makes MI25 a property of the
--            database rather than a property of the code that happens to call it.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0100 trappoint_ref.fn_check_project · 0058 trappoint_ref.blocking_check
-- sqlstate: P0001 when the blame closure is absent; otherwise the row is silently rewritten,
--           which is the entire product.
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER check_project BEFORE INSERT ON trappoint_ref.blocking_check
  FOR EACH ROW EXECUTE FUNCTION trappoint_ref.fn_check_project();
