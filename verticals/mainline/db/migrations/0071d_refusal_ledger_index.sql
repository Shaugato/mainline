-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0071d_refusal_ledger_index.sql
-- CREATE INDEX refusal_ledger_by_subject — the refusal history of one subject, newest first
--
-- MI: MI01
-- I: I14
-- COUNSEL-GATED: no
-- RATIONALE: The two questions asked of this table are what was refused on this subject and
--            in what order, and which constraint refused it. One index answers both: the
--            key orders a subjects refusals newest first, and STORING carries the exhibit,
--            the code and the diagnosis so the console renders a refusal history without
--            touching the payload. Reading the exhibit must not require parsing the
--            evidence.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0071c_refusal_ledger.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- Newest first is the read pattern, not a preference: the console shows the current
-- refusal and its immediate predecessors, and an ascending index would make the common
-- query a full-partition scan in reverse.
--
-- The stored columns are exactly the four a refusal list renders. `payload` is
-- deliberately NOT stored: it is unbounded, the index would carry the whole ledger twice,
-- and a consumer that wants the reason set is asking for one row by primary key.

CREATE INDEX refusal_ledger_by_subject
  ON mainline.refusal_ledger (subject_kind, subject_id, observed_at DESC)
  STORING (constraint_name, sqlstate, diagnosis, naa_kind);
