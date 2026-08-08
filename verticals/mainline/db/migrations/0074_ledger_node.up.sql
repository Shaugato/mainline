-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI24
-- I: I01, I04
-- COUNSEL-GATED: no
-- RATIONALE: The persisted RFC 6962 interior hashes. Without them, producing an inclusion or
-- consistency proof means re-hashing every leaf in the tree, so proof cost grows with the log and
-- the verifier's "prove leaf 12 is in the tree of size 400,000" degrades from milliseconds to
-- minutes. A proof nobody can afford to generate is a proof that stops being generated.
--
-- migration:  0074_ledger_node
-- band:       0072-0079 · cu-ledger-ddl (custody) · see OWNERSHIP note in 0072
-- statements: 1
-- source:     ARCHITECTURE.md §5.6 (verbatim shape) · §18 slot 0074 · RFC 6962 §2.1 ·
--             C2SP tlog-tiles (tile addressing) · docs/leads/custody.md worker 3
-- requires:   0002 CREATE SCHEMA mainline · 0021 mainline.site
-- owes:       `fn_refuse_mutation` on this table, band 0130-0199 — UPDATE and DELETE raise P0001.
--             An interior hash is a commitment to a fixed set of leaves; if it can be rewritten,
--             every proof through it can be rewritten, and the proof is what the stranger checks.
-- grants:     `fk_site` requires `SELECT ON mainline.site` for `agent_sequencer` — see the
--             MEASURED PLATFORM FACT block in 0072.
-- sqlstate:   23503 on fk_site · 23505 on ledger_node_pkey · 23514 on the shape CHECKs
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ADDRESSING. `(level, idx)` is the RFC 6962 node coordinate: level 0 is the leaf row, level L
-- node I covers leaves [I·2^L, (I+1)·2^L). `level` is allowed to be 0 rather than starting at 1
-- because C2SP `tlog-tiles` addresses LEAF tiles at level 0, and a schema that cannot represent
-- the addressing scheme the tile server serves would force a translation layer whose only job is
-- to be off by one somewhere.
--
-- THE TABLE IS A CACHE OF A DERIVATION, AND IT IS STILL APPEND-ONLY. Every row here is
-- recomputable from `mainline.ledger_leaf` alone; nothing is lost if the table is empty, and a
-- verifier NEVER trusts it — `trappoint-verify` recomputes the Merkle Tree Hash from the leaves
-- in the bundle. So why refuse UPDATE on a cache? Because the proofs WE serve to a witness, to
-- the console and to the tile endpoint are read from here, and a mutable cache in front of an
-- immutable log is a way to serve two different trees to two different audiences while the log
-- itself stays pristine. A split view is the one attack witness diversity exists to catch, and
-- there is no reason to build a cheaper way to mount it. A recomputed node is IDENTICAL to the
-- node it replaces, so refusing UPDATE costs a correct implementation exactly nothing.
--
-- `hash_is_sha256` catches a truncated interior hash at the row instead of at the first proof
-- that fails to verify, which is a much later and much worse place to find out.
--
-- NO ROW-LEVEL TTL ON THIS TABLE, EVER. See 0072.

CREATE TABLE mainline.ledger_node (
  site_code STRING NOT NULL,
  level     INT2   NOT NULL,   -- 0 = leaf level, per C2SP tlog-tiles addressing
  idx       INT8   NOT NULL,   -- node index within the level
  hash      BYTES  NOT NULL,   -- RFC 6962 interior hash: SHA-256(0x01 || left || right)
  CONSTRAINT ledger_node_pkey PRIMARY KEY (site_code, level, idx),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT level_non_negative CHECK (level >= 0),
  CONSTRAINT idx_non_negative CHECK (idx >= 0),
  CONSTRAINT hash_is_sha256 CHECK (length(hash) = 32)
);
