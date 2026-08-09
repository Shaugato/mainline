-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0125_trg_permit_event_chain.sql
-- CREATE TRIGGER permit_event_chain — the permit chain verifies its own input
--
-- MI: MI01, MI09, MI24
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: BEFORE INSERT, because a chain link whose parent digest is wrong must never
--            exist, not even inside the transaction that would have rolled it back. The
--            STORED chain_digest column hashes whatever prev_digest it is given; this weld
--            is what makes the input to that hash verified rather than trusted, which is
--            what the column comment claimed and finding S9 found to be false.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0120_triggers_projection.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0105 mainline.fn_permit_event_chain
--           · mainline.permit_event
-- sqlstate: P0001 on a missing predecessor or a digest mismatch. The FORK case is 23505 on
--           `linear`, raised by that constraint and deliberately not pre-empted here.
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();
