-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0124_trg_disposition_retract_only.sql
-- CREATE TRIGGER disposition_retract_only — the one permitted UPDATE, guarded
--
-- MI: MI01, MI07
-- I: I01, I03
-- COUNSEL-GATED: no
-- RATIONALE: BEFORE UPDATE, because the refusal must happen before the row changes and
--            because the guard compares OLD with NEW, which only a BEFORE trigger can do
--            while the write is still preventable. This weld is what makes disposition an
--            append-only table with exactly one stated exception rather than a mutable one
--            with a convention.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0104 mainline.fn_disposition_retract_only · 0066 mainline.disposition
-- sqlstate: P0001 on a re-retraction, an un-retraction, or any other column changing.
--           23503 on the epoch pin when the subject has already merged.
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER disposition_retract_only BEFORE UPDATE ON mainline.disposition
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_disposition_retract_only();
