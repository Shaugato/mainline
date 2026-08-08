-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI24, MI01
-- I: I04, I01
-- COUNSEL-GATED: no
-- RATIONALE: THE LEDGER SEQUENCE IS DENSE AND FORK-FREE (MI24), and it is dense and fork-free by
-- COMPARE-AND-SWAP rather than by a sequence — which is the only reason the sentence "a gap MEANS
-- tampering" is worth saying. Sequence increments survive rollback, so a sequence-numbered ledger
-- has legitimate gaps and a gap means nothing; a CAS-numbered ledger has none, so verifier check 9
-- can treat one as evidence. This file is where that claim is either true or false.
--
-- migration:  0073_ledger_leaf
-- band:       0072-0079z · custody · AUTHORED — verticals/mainline/db/migrations.allocation.toml;
--             see the OWNERSHIP note in 0072
-- statements: 1
-- source:     ARCHITECTURE.md §5.6 (base shape) · §16 MI24 · §18 slot 0073 ·
--             spec/custody/ledger-schema.md §1 (CU-1, NORMATIVE ADDENDUM) and §2 (CU-2) ·
--             docs/leads/custody.md CU-1, CU-2 · spec/invariants/I04-linear-head.md (CF-63) ·
--             spec/wire/evidence-bundle.md §leaf record · spec/custody/attacks.yaml A1, A2, A6
-- requires:   0020a mainline.site · 0072 mainline.ledger_intake
-- owes:       `fn_refuse_mutation` on this table, band 0130-0199 — UPDATE and DELETE raise P0001
--             with NO exception. Attack A1 (delete_and_relink) is ONE `UPDATE … FROM
--             generate_series` away for anyone who can reach this table; the trigger raises the
--             cost of that statement from zero to "disable a trigger first", and the checkpoint
--             that already left the building is what makes either version detectable.
-- grants:     `fk_intake` requires `SELECT ON mainline.ledger_intake` for every role that inserts
--             here — see the MEASURED PLATFORM FACT block in 0072. `agent_sequencer` already
--             holds it in GRANTS.yaml ("it reads what it sequences"), so this FK costs nothing.
-- sqlstate:   23505 on ledger_leaf_pkey (two leaves at one position — CF-63) ·
--             23505 on ledger_linear (two leaves claiming the same predecessor — attack A6) ·
--             23505 on ledger_leaf_entry_unique (the same intake entry sequenced twice) ·
--             23503 on fk_intake (a leaf for an entry that does not exist, or for an entry
--             belonging to a different site) · 23514 on the shape CHECKs
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- CU-1 — REFUSAL DEPTH 2 ON APPEND. This is the addendum `spec/custody/ledger-schema.md` §1 makes
-- normative, and it is the reason `prev_link_hash` is a stored column rather than a derivation.
--
--   PRIMARY KEY (site_code, seq)          ← two appenders collide on position
--   UNIQUE      (site_code, prev_link_hash) ← two appenders collide on PREDECESSOR
--
-- Drop either one and the concurrent write still fails. That is the architecture's own
-- `UNIQUE (permit_id, prev_seq)` compare-and-swap idiom, transplanted from the gate to the
-- ledger, so the ledger is held to exactly the standard the kernel holds the gate to and the
-- unwelding suite can prove it one constraint at a time (attacks.yaml A6). A fork becomes
-- PHYSICALLY impossible rather than merely unlikely — even at READ COMMITTED, and even under a
-- hypothetical primary-key bypass — because two leaves cannot both claim the same predecessor.
--
-- GENESIS IS 32 ZERO BYTES, not NULL. `seq = 0` therefore stops being a special case in every
-- reader, the `NOT NULL` holds uniformly, and — because a UNIQUE constraint over a non-NULL
-- value refuses duplicates — a site can have exactly ONE genesis leaf. Under a nullable
-- `prev_link_hash` the genesis rows would all be distinct to the UNIQUE index and the first leaf
-- would be the one position a fork was allowed.
--
-- WHY `prev_link_hash` IS REDUNDANT-BY-DERIVATION AND LOAD-BEARING-BY-CONSTRAINT.
-- `link_hash = SHA-256(prev_link_hash ‖ leaf_hash)`, so the predecessor's link hash is already
-- inside `link_hash`. Storing it separately buys the thing derivation cannot: the verifier's
-- chain recomputation (check 9) reads the CLAIMED predecessor instead of inferring it from
-- `seq` — which is exactly the case that matters when `seq` is what was tampered with
-- (attacks.yaml A2, renumber_only). Redundancy a constraint reads is not duplication.
--
-- WHAT CU-1 DOES NOT BUY, stated because the domain's whole discipline is saying this out loud:
-- a T1 adversary with schema rights drops the constraint. This is REFUSAL depth, not
-- tamper-EVIDENCE. The tamper-evidence is the signed checkpoint that already left the trust
-- boundary; a hash chain inside a table the adversary owns is a checksum.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- CU-2 — HOW `seq` IS PRODUCED, AND THE ONE RETRYABLE 23505 IN THE REPOSITORY.
--
--   seq := COALESCE((SELECT max(seq) FROM mainline.ledger_leaf WHERE site_code = $1), -1) + 1
--
-- derived INSIDE the appending transaction. `CREATE SEQUENCE`, `nextval()`, `SERIAL` and
-- `unique_rowid()` are banned repository-wide and `trappoint migrate lint` enforces it on every
-- migration and every rendered template; the ban is load-bearing rather than stylistic because
-- `CREATE SEQUENCE` SUCCEEDS on the target cluster (docs/adr/0002 F4) — nothing but the lint
-- stands between this schema and a ledger whose gaps mean nothing.
--
-- The resulting 23505 on `ledger_leaf_pkey` or `ledger_linear` is the ONLY retryable 23505 in
-- the repository. The sequencer's CAS loop matches on CONSTRAINT NAME — never on SQLSTATE — is
-- bounded at 8 attempts, and is asserted by a test that a 23505 on any OTHER constraint ESCAPES
-- the loop. That test is the important one: without it, the single legitimate retry becomes a
-- laundry for real refusals, which is a far worse defect than the contention it absorbs. The
-- constraint names in this file are therefore an interface, not decoration, and renaming one is
-- a breaking change to `mainline_sequencer.append`.
--
-- `ledger_leaf_entry_unique` IS THE IDEMPOTENCE CONSTRAINT. Replaying a batch is a no-op because
-- the same `entry_id` cannot be sequenced twice — which matters precisely because CockroachDB
-- has NO ADVISORY LOCKS, so the sequencer cannot hold one across a batch and must instead be
-- safe to re-run. It is deliberately NOT named `ledger_leaf_pkey` or `ledger_linear`: a 23505 on
-- this constraint means "already done", which is a different fact from "somebody else got this
-- position", and the CAS loop must be able to tell them apart by name.
--
-- WHY THE FOREIGN KEY IS COMPOSITE. ARCHITECTURE.md §5.6 writes `entry_id UUID NOT NULL
-- REFERENCES mainline.ledger_intake (entry_id)`. This file takes the FK onto
-- `(site_code, entry_id)` instead — which is strictly stronger, since `entry_id` is intake's
-- primary key — because under the single-column form the leaf's `site_code` is a value the
-- SEQUENCER asserts, and a value the writer asserts is not a fact. With the composite FK, a leaf
-- can only ever join a tree whose site its own intake row declared: smuggling an entry from one
-- site's intake into another site's evidentiary tree is 23503, from every writer, forever. The
-- cost is one UNIQUE constraint on intake (`intake_site_entry_unique`, migration 0072).
--
-- `batch_id` IS NOT A KEY AND ORDERS NOTHING. It records which sequencer run produced the leaf,
-- so a run can be reconstructed from the ledger for operational forensics. It carries no
-- constraint because it commits to nothing: the evidentiary commitments are `leaf_hash` (to the
-- content) and `link_hash` (to the whole prefix).
--
-- THE LENGTH CHECKS ARE NOT COSMETIC. A truncated or empty digest inserted into an evidentiary
-- chain is a value that will verify against nothing, forever, and it would be discovered at
-- verification time — years later, by the person least able to do anything about it. Thirty-two
-- bytes is what SHA-256 produces; anything else is a bug in the client, caught at the row.
--
-- NO ROW-LEVEL TTL ON THIS TABLE, EVER. See 0072.

CREATE TABLE mainline.ledger_leaf (
  site_code      STRING NOT NULL,
  seq            INT8   NOT NULL,   -- 0-based, DENSE. Derived in-txn (CU-2); never a sequence
  entry_id       UUID   NOT NULL,
  leaf_hash      BYTES  NOT NULL,   -- SHA-256(0x00 || canon_bytes), copied from the intake row
  prev_link_hash BYTES  NOT NULL,   -- genesis = 32 zero bytes (CU-1); never NULL
  link_hash      BYTES  NOT NULL,   -- SHA-256(prev_link_hash || leaf_hash)
  batch_id       UUID   NOT NULL,   -- which sequencer run; commits to nothing
  CONSTRAINT ledger_leaf_pkey PRIMARY KEY (site_code, seq),
  CONSTRAINT ledger_linear UNIQUE (site_code, prev_link_hash),
  CONSTRAINT ledger_leaf_entry_unique UNIQUE (site_code, entry_id),
  CONSTRAINT fk_intake FOREIGN KEY (site_code, entry_id)
    REFERENCES mainline.ledger_intake (site_code, entry_id),
  CONSTRAINT seq_zero_based CHECK (seq >= 0),
  CONSTRAINT leaf_hash_is_sha256 CHECK (length(leaf_hash) = 32),
  CONSTRAINT prev_link_hash_is_sha256 CHECK (length(prev_link_hash) = 32),
  CONSTRAINT link_hash_is_sha256 CHECK (length(link_hash) = 32)
);
