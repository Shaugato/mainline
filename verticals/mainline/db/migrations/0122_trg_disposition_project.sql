-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0122_trg_disposition_project.sql
-- CREATE TRIGGER disposition_project — identity and virulence become projections
--
-- MI: MI11, MI27, MI28, MI29
-- I: I09, I10
-- COUNSEL-GATED: no
-- RATIONALE: BEFORE INSERT, because every column this function writes is read by a CHECK or
--            a foreign key on the same row: rank_floor compares the projected rank,
--            fk_clearance keys on the projected virulence, and override_escalates compares
--            the projected override count. A projection that landed after those evaluated
--            would be decoration.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0102 mainline.fn_disposition_project · 0066 mainline.disposition
-- sqlstate: P0001 on an unknown check, absent closure, absent or expired receipt, unknown signer.
--           23503 on fk_clearance and 23514 on rank_floor are raised BY THOSE CONSTRAINTS, after
--           this trigger has written the values they compare (conformance cases CF-07, CF-19).
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER disposition_project BEFORE INSERT ON mainline.disposition
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_disposition_project();
