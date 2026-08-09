-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0106_fn_cr_event_chain.sql
-- CREATE FUNCTION mainline.fn_cr_event_chain — the change_request event chain is verified against its predecessor
--
-- MI: MI01, MI09, MI24
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: Finding S9: chain_digest was a server-computed hash over a client-supplied
--            prev_digest, so a writer could start a second chain from any digest it liked
--            and every row would still be well-formed. The server was faithfully hashing a
--            lie. This function reads the predecessor by primary key and refuses unless the
--            supplied prev_digest equals its chain_digest, which is what the column comment
--            always claimed and never did. seq = 0 is exempt because a genesis row has no
--            predecessor, and the primary key admits exactly one of those per subject.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0105_fn_event_chain.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- migration:  0106_fn_cr_event_chain
-- band:       0100-0109z · kernel/projection-triggers · RENDERED
-- statements: 1
-- invariants: MI09 (at most one merge per subject; no forked history — this function guards the
--             DIGEST half; `UNIQUE (cr_id, prev_seq)` guards the FORK half and this
--             function deliberately does not pre-empt it)
-- source:     ARCHITECTURE.md §5.11 item 8 · §2.2 S9 · §5.5
-- requires:   mainline.cr_event (migration 0060,
--             RENDERED, kernel `subject-and-pin`) with columns seq, prev_seq, prev_digest and
--             the STORED chain_digest
-- provides:   mainline.fn_cr_event_chain() — welded to cr_event by 0126
-- sqlstate:   P0001 on a missing predecessor and on a digest mismatch. NEVER a synthetic 23505
--             for the fork case: `linear` produces that one, with its name (spec/errors.md §3.3).
-- forward-only; no .down.sql and no .up.sql (MR-5).
--
-- ACYCLICITY. BEFORE INSERT on cr_event, reading one earlier row of the same table by
-- primary key and writing nothing. Trigger depth contributed: 0.

CREATE FUNCTION mainline.fn_cr_event_chain() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE
  v_existing INT8;
  v_expected BYTES;
BEGIN
  IF (NEW).seq = 0 THEN
    RETURN NEW;
  END IF;

  -- The one aggregate this body is allowed (§4.1 law 4), and the genesis test that survives both
  -- spellings of "first row": ARCHITECTURE §5.11's `seq = 0` and the shipped table's
  -- `seq = 1, prev_seq = 0` under CHECK (seq > prev_seq AND prev_seq >= 0), which makes seq = 0
  -- unreachable. The table is append-only, so this count only rises and the exemption is taken
  -- once per subject; a later row claiming genesis falls through to the predecessor lookup below
  -- and is refused there, with `UNIQUE (cr_id, prev_seq)` as the structural backstop.
  SELECT count(*) INTO v_existing
    FROM mainline.cr_event e0
   WHERE e0.cr_id = (NEW).cr_id;
  IF v_existing = 0 THEN
    RETURN NEW;
  END IF;

  SELECT e.chain_digest INTO v_expected
    FROM mainline.cr_event e
   WHERE e.cr_id = (NEW).cr_id
     AND e.seq = (NEW).prev_seq;

  IF v_expected IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no predecessor event for the declared prev_seq';
  END IF;

  -- IS DISTINCT FROM rather than <>. A NULL on either side makes <> yield NULL, an IF on NULL
  -- does not execute, and the guard would pass silently on exactly the row it exists to catch.
  IF v_expected IS DISTINCT FROM (NEW).prev_digest THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: prev_digest does not match the predecessor chain digest';
  END IF;
  RETURN NEW;
END $$;
