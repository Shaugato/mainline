-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI24
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: The commit id IS the hash of the envelope, so an edit to any ancestor invalidates every descendant by arithmetic rather than by policy; `envelope_bytes` stores the exact JCS bytes that were hashed, because a hash over bytes we cannot reproduce proves nothing.
--
-- migration:  0024_commit_obj
-- band:       0024-0031, 0047-0049 · dm-spine · AUTHORED, allocated by
--             verticals/mainline/db/migrations.allocation.toml (MR-6 lock 1)
-- statements: 1
-- source:     ARCHITECTURE.md §5.2 (verbatim shape; constraints named per DM-10, index and
--             families inline per DM-6) · §4 (the two DAGs) · §4.1 laws 8 and 9
-- requires:   0001a CREATE SCHEMA mainline
-- projects:   `gen` is PARENT-DERIVED (1 + max(parent.gen)) and is guarded, not defaulted — see
--             THE `gen` CONTRACT below and 0025 mainline.commit_edge
-- sqlstate:   23514 on id_is_sha256 / gen_positive / envelope_bytes_present;
--             23505 on commit_obj_pk (the same content addressed twice is the same commit)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- THIS IS THE HISTORY DAG. It answers exactly one question — "when did the text change" — and it
-- must never be asked the other one. "What wrote this control" is the BLAME DAG (0033-0037), and
-- the entire diachronic gate is computable only because the two are stored separately and never
-- conflated. A commit is not evidence of a hazard; an event is. A commit is evidence of an EDIT.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY CONTENT ADDRESSING, AND WHAT IT BUYS THAT A UUID DOES NOT. Three things at once, and the
-- third is the one people miss:
--
--   1. THE COMMIT BECOMES A MERKLE NODE. `commit_id = sha256(envelope_bytes)` and the envelope
--      names the parents by their ids, so editing any ancestor changes every descendant id. You
--      cannot rewrite history quietly; you can only fork it visibly. That is not a database
--      feature, it is the reason a nine-year-old procedure clause can be shown to a court.
--   2. NO INDEX-TAIL HOTSPOT. SHA-256 keys distribute uniformly across the keyspace, so an
--      append-heavy table spreads across ranges with no hash-sharded index and no sequence.
--      A monotonically increasing key would put every write on one range leaseholder — and the
--      obvious fix for that (a sequence, a shard column) is exactly what §4.1 law 9 bans.
--   3. THE ID IS STABLE ACROSS EXPORT. A UUID minted by this cluster means nothing in a bundle a
--      stranger verifies offline. `commit_id` is recomputable from `envelope_bytes` by anyone
--      with a SHA-256 implementation, so an exhibit can NAME the commit and the name checks out.
--
-- `envelope` AND `envelope_bytes` ARE BOTH STORED, AND THAT IS NOT REDUNDANCY.
-- §4.1 law 8: `JSONB` reorders keys. CockroachDB stores JSONB in a normalised internal form, so
-- serialising the `envelope` column back out is NOT guaranteed to reproduce the byte sequence the
-- client hashed. If we hashed the re-serialisation we would be hashing a different document that
-- happens to mean the same thing — and RFC 8785 exists precisely because "means the same thing"
-- is not a property a hash respects. So the authoritative artefact is `envelope_bytes`: the exact
-- octets that went into SHA-256. `envelope` is the QUERYABLE COPY, for humans and for SQL, and it
-- is never the thing that is hashed. `trappoint-verify` recomputes sha256(envelope_bytes) and
-- compares it to `commit_id`; it does not look at `envelope` at all.
--
-- THE `gen` CONTRACT — parent-derived, never a sequence, and deliberately not a DEFAULT.
-- `gen = 1 + max(parent.gen)`, which makes bisect a PK-ORDERED RANGE SCAN over
-- (clause_uuid, gen, commit_id) in 0029 rather than a graph walk with a recursive CTE per probe.
-- It cannot be a sequence (§4.1 law 9: sequences commit outside the transaction and gap on
-- rollback, and a gap in this repository must MEAN tampering). It cannot be a DEFAULT either,
-- because at the moment this row is inserted its parent edges do not exist yet — 0025 is written
-- after 0024, per commit. So the shape is: the committer computes `gen` from the envelope it just
-- hashed, the plain CHECK here refuses a negative, and the REFUSAL that makes it true lives on
-- mainline.commit_edge, where both ends of the edge are known and `parent_gen` is projected from
-- THIS table. See 0025. Until the guard trigger in band 0130-0199 lands, `gen` is asserted by the
-- writer and this file says so rather than implying otherwise.
--
-- ROOT COMMITS HAVE gen = 0, WHICH IS WHY THE CHECK IS `>= 0` AND NOT `>= 1`. A site's first
-- commit has no parents, so `max(parent.gen)` is over the empty set. Naming that 0 (rather than
-- NULL, or 1) makes the edge law on 0025 total: every edge satisfies child.gen >= parent.gen + 1,
-- including the first one that exists.
--
-- `sig` IS NULLABLE ON PURPOSE. A commit is a repository fact; a SIGNATURE is a human act. Most
-- commits are machine-authored ingestion steps and forcing a signature onto them would either
-- fabricate one or block ingestion. The signatures that carry legal weight are on DISPOSITIONS
-- (band 0066-0071), where a named person clears a named precursor. Requiring a signature here
-- would dilute exactly the artefact whose scarcity is its meaning.
--
-- THE TWO FAMILIES. `f_hot` is every column the DAG walk, the bisect and the branch listing
-- touch; `f_cold` is the payload (`message`, `envelope`, `envelope_bytes`, `sig`), which is
-- kilobytes per row and is read only when a specific commit is opened. Splitting them means a
-- reachability walk over ten thousand commits does not drag ten thousand envelopes through the
-- KV layer. NOTE for anyone adding a changefeed later: §4.1 law 11 — CDC queries FAIL on
-- multi-family tables. This table is deliberately not a changefeed source; mainline_ops.outbox is
-- the only one in the system.
--
-- `by_branch_gen` STORES ONLY NON-KEY COLUMNS. `commit_id` is the primary key and is therefore
-- implicitly present in every secondary index; CockroachDB REFUSES a primary-key column in a
-- STORING clause. This is a correction to the DDL as printed in §5.2, made here rather than
-- discovered at apply time — see also 0029, where the same correction removes `clause_uuid` from
-- `by_commit`'s STORING list. Nothing is lost: the column is in the index either way.
--
-- UNVERIFIED ON THIS MACHINE (honesty, per the build discipline): no CockroachDB v26.2 was
-- reachable from the machine this band was authored on — no `cockroach` binary, no live Docker
-- daemon — so this statement has not been executed. `length(BYTES)` returning a byte count,
-- inline `INDEX … STORING`, and inline `FAMILY` are all documented CockroachDB syntax; the
-- combination is what is untested. tests/integration/schema/test_mi_spine.py executes it the
-- moment a cluster is reachable, and reports a skip with a reason rather than a pass when one is
-- not.

CREATE TABLE mainline.commit_obj (
  commit_id      BYTES       NOT NULL,   -- sha256 over the canonical (JCS) commit envelope
  site_id        UUID        NOT NULL,
  gen            INT8        NOT NULL,   -- 1 + max(parent.gen); parent-derived, never a sequence
  ref_name       STRING      NOT NULL,
  committed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  author_sub     STRING      NOT NULL,
  message        STRING      NOT NULL,
  envelope       JSONB       NOT NULL,   -- the queryable copy. NEVER the thing that is hashed.
  envelope_bytes BYTES       NOT NULL,   -- the exact BYTES that were hashed (JCS). Authoritative.
  sig            BYTES       NULL,
  CONSTRAINT commit_obj_pk PRIMARY KEY (commit_id),
  CONSTRAINT id_is_sha256 CHECK (length(commit_id) = 32),
  CONSTRAINT gen_positive CHECK (gen >= 0),
  CONSTRAINT ref_name_stated CHECK (ref_name <> ''),
  CONSTRAINT author_sub_stated CHECK (author_sub <> ''),
  CONSTRAINT envelope_bytes_present CHECK (length(envelope_bytes) > 0),
  INDEX by_branch_gen (site_id, ref_name, gen) STORING (committed_at, author_sub),
  FAMILY f_hot  (commit_id, site_id, gen, ref_name, committed_at, author_sub),
  FAMILY f_cold (message, envelope, envelope_bytes, sig)
);
