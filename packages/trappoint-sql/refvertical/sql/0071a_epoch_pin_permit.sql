-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0071a_epoch_pin_permit.sql
-- ALTER TABLE trappoint_ref.merge_record ADD CONSTRAINT epoch_pin_permit — the pin
--
-- MI: MI07
-- I: I03
-- COUNSEL-GATED: no
-- RATIONALE: Late-arriving recall is not a serializability failure and cannot be answered
--            by an isolation level: a precursor inserted after a merge is a perfectly
--            serializable history. Once this foreign key references (subject_id, epoch), ON
--            UPDATE RESTRICT makes any change to that epoch impossible, and every new
--            obligation must change it — so attaching a precursor to a completed subject
--            fails on referential integrity before any policy is consulted. CASCADE appears
--            in neither position because a cascade rewrites history, which is the offence
--            this substrate exists to detect.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0071_merge_record.sql.j2
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Declared as an ALTER rather than inline with the table, because one statement per file
-- is not negotiable and because the two pins reference two tables that are created in two
-- earlier migrations; a single CREATE TABLE naming both would be a file whose failure
-- mode nobody can diagnose.
--
-- Under MATCH SIMPLE this constraint is enforced on exactly those rows whose
-- `permit_id` is non-null, which is exactly the rows completing a
-- permit. A row for the other kind leaves the column NULL and the constraint does
-- not apply to it. That is the "partial-FK pair, one per kind" of §5.5, spelled out.

ALTER TABLE trappoint_ref.merge_record
  ADD CONSTRAINT epoch_pin_permit
  FOREIGN KEY (permit_id, gate_epoch)
  REFERENCES trappoint_ref.permit (permit_id, gate_epoch)
  ON UPDATE RESTRICT ON DELETE RESTRICT;
