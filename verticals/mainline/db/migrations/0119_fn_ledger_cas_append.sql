-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MAINLINE · 0119_fn_ledger_cas_append.sql
-- CREATE OR REPLACE FUNCTION mainline.fn_ledger_cas_append() — gap-free by compare-and-swap, so a gap MEANS tampering
--
-- MI: MI24
-- I: I04
-- COUNSEL-GATED: no
-- RATIONALE: A sequence would make a gap ambiguous: crash, rollback, cache loss and
--            tampering would all look alike, and the ledger asserts nothing it cannot
--            distinguish. Deriving seq inside the serializable transaction as
--            coalesce(max(seq)+1, 0) makes the primary key itself the compare-and-swap, so
--            two writers racing for one position collide on 23505 and the surviving
--            sequence is dense by construction rather than by convention.
--
-- @rendered-by  trappoint render
-- @template     packages/trappoint-sql/templates/0117_proc_merge.sql.j2
-- @binding      verticals/mainline/vertical.toml
-- DO NOT EDIT. `trappoint render --check` is a zero-diff assertion in CI, so a
-- hand edit here is a red build, not a silent divergence.
--
-- THE BAN IS THE POINT. `CREATE SEQUENCE`, `nextval(`, `SERIAL` and `unique_rowid()`
-- are refused by `trappoint render` and by `trappoint migrate lint` (ruling D10), and
-- that lint is LOAD-BEARING rather than decorative: ground-truth finding F4 measured
-- that `CREATE SEQUENCE` succeeds on this cluster. One future migration reintroducing
-- one would make every gap in the ledger deniable, and deniability is the only thing
-- the custody chain exists to remove.
--
-- TWO COMPARE-AND-SWAPS, NOT ONE. `ledger_leaf_pkey (site_code, seq)` refuses a
-- duplicate position; `ledger_linear (site_code, prev_link_hash)` refuses a fork at
-- the same predecessor. Either alone would leave the other anomaly representable, and
-- both are enforced against every writer, including one holding a psql session.
--
-- `prev_link_hash` IS NEVER NULL. Genesis is 32 zero bytes (custody CU-1), so the
-- link function is total and a verifier never branches on NULL.
--
-- SEQUENCED-NESS IS DERIVED, NEVER WRITTEN: there is no `sequenced` flag on
-- `ledger_intake` and this function does not write one. The sequencer's batch is an
-- anti-join, which is what keeps the whole ledger path INSERT + SELECT.
--
-- RETURNS the position it took, so a caller can build the Signed Disposition Receipt
-- without a second round trip.

CREATE OR REPLACE FUNCTION mainline.fn_ledger_cas_append(
  a_site_code STRING,
  a_entry_id  UUID,
  a_leaf_hash BYTES,
  a_batch_id  UUID
) RETURNS INT8 LANGUAGE PLpgSQL AS $fn$
DECLARE
  v_seq  INT8;
  v_prev BYTES;
BEGIN
  -- Derived INSIDE the caller's serializable transaction. Two appenders that read the
  -- same max() both try to write the same position, and the primary key decides.
  SELECT coalesce(max(l.seq) + 1, 0) INTO v_seq
    FROM mainline.ledger_leaf l
   WHERE l.site_code = a_site_code;

  SELECT l.link_hash INTO v_prev
    FROM mainline.ledger_leaf l
   WHERE l.site_code = a_site_code AND l.seq = v_seq - 1;

  INSERT INTO mainline.ledger_leaf
              (site_code, seq, entry_id, leaf_hash, prev_link_hash, link_hash, batch_id)
       VALUES (a_site_code, v_seq, a_entry_id, a_leaf_hash,
               coalesce(v_prev, decode(repeat('00', 32), 'hex')),
               digest(coalesce(v_prev, decode(repeat('00', 32), 'hex')) || a_leaf_hash, 'sha256'),
               a_batch_id);
  RETURN v_seq;
END $fn$;
