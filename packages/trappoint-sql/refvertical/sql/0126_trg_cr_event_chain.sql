-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: Apache-2.0
--
-- TRAPPOINT_REF · 0126_trg_cr_event_chain.sql
-- CREATE TRIGGER cr_event_chain — the change_request chain verifies its own input
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
-- @binding      packages/trappoint-sql/refvertical/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- band: 0120-0129z · kernel/projection-triggers · RENDERED · statements: 1
-- requires: 0106 trappoint_ref.fn_cr_event_chain
--           · trappoint_ref.cr_event
-- sqlstate: P0001 on a missing predecessor or a digest mismatch. The FORK case is 23505 on
--           `linear`, raised by that constraint and deliberately not pre-empted here.
-- forward-only; no .down.sql and no .up.sql (MR-5).

CREATE TRIGGER cr_event_chain BEFORE INSERT ON trappoint_ref.cr_event
  FOR EACH ROW EXECUTE FUNCTION trappoint_ref.fn_cr_event_chain();
