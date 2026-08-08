-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI24
-- I: I01, I04
-- COUNSEL-GATED: no
-- RATIONALE: L0 of the custody ledger. Intake is where a fact enters the evidentiary record, and
-- the ONE thing that must be true of it is that the bytes we hashed are the bytes we stored, so a
-- stranger with no access to this cluster can recompute `leaf_hash` and get the same 32 bytes.
-- `canon_bytes` is therefore stored verbatim next to the parsed `payload`, never derived from it.
--
-- migration:  0072_ledger_intake
-- band:       0072-0079 · cu-ledger-ddl (custody) · see OWNERSHIP note below
-- statements: 1
-- source:     ARCHITECTURE.md §5.6 (verbatim column shape) · §18 slot 0072 ·
--             spec/custody/ledger-schema.md §§3-6 · docs/leads/custody.md CU-2, CU-5 ·
--             docs/leads/datamodel.md DM-10 (every constraint named), DM-11 (vocabularies are FKs)
-- requires:   0002 CREATE SCHEMA mainline · 0021 mainline.site
-- owes:       (a) `fn_refuse_mutation` on this table, band 0130-0199 — UPDATE and DELETE raise
--                 P0001, with NO exception (spec/custody/ledger-schema.md §3);
--             (b) FK `entry_kind` → `mainline.ledger_entry_kind`, band 0108-0129 per DM-11 —
--                 this file deliberately ships NO `CHECK (entry_kind IN (…))`, because a
--                 free-text vocabulary and an FK'd vocabulary are two different mechanisms and
--                 shipping both means the second one never lands;
--             (c) a COMMENT ON the `hlc` column — migration 0072a, because CockroachDB DDL is
--                 one statement per file and `COMMENT ON` is a statement.
-- grants:     `fk_site` REQUIRES `GRANT SELECT ON mainline.site` to every role that inserts here
--             (`agent_relay`, `agent_gate`, `agent_projector`, `mainline_ledger`). This is a
--             MEASURED platform fact, not a preference — see MEASURED PLATFORM FACT below.
-- sqlstate:   23503 on fk_site (a ledger entry for a site nobody provisioned) ·
--             23505 on ledger_intake_pkey / intake_site_entry_unique ·
--             23514 on the shape CHECKs · P0001 from the append-only trigger once (a) lands ·
--             42501 at INSERT if the writing role lacks SELECT on mainline.site (see grants)
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- OWNERSHIP. ARCHITECTURE.md §18 places slots 0072-0079 inside the datamodel lead's 0072-0129
-- band, and `spec/custody/ledger-schema.md` §9 says custody SPECIFIES the ledger and the
-- datamodel lead IMPLEMENTS it. This file is that implementation, written by the custody domain
-- against that specification, exactly as the recall domain implemented its own 0080-0088. The
-- band boundary is recorded here so a reviewer knows which plan to read, not to claim territory:
-- if the datamodel lead lands a second file for this slot, `trappoint migrate` refuses the tree
-- with "two files claim version '0072_ledger_intake'" — which is the correct outcome and is why
-- the collision is loud rather than silent.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- MEASURED PLATFORM FACT — FOREIGN KEY VALIDATION REQUIRES `SELECT` ON THE REFERENCED TABLE.
-- Measured 2026-08-07 against `cockroachdb/cockroach:v26.2.5` (single node, `start-single-node
-- --insecure`), not inferred from documentation:
--
--   * a role holding only `INSERT ON mainline.ledger_intake` and `USAGE ON SCHEMA mainline`
--     fails this insert with `42501: user … does not have SELECT privilege on relation site`;
--   * `GRANT REFERENCES ON TABLE …` is a SYNTAX ERROR — CockroachDB v26.2 has no PostgreSQL-style
--     `REFERENCES` privilege, so there is no narrower grant to reach for;
--   * `GRANT SELECT ON mainline.site` makes the insert succeed, and the same role STILL cannot
--     `SELECT` from `mainline.ledger_intake` (42501) — which was verified explicitly, because the
--     property that actually matters is preserved.
--
-- THIS CONTRADICTS A STATED PROPERTY OF `verticals/mainline/db/GRANTS.yaml` and the contradiction
-- is recorded here rather than resolved silently. That file describes `agent_relay` as "INSERT on
-- ledger_intake and NOTHING ELSE — not even SELECT. A relay that cannot read cannot be induced to
-- exfiltrate." With `fk_site` in place, `agent_relay` must also hold `SELECT ON mainline.site`.
--
-- The trade was made in favour of the foreign key, deliberately, for three reasons. Migration
-- 0021 is normative and emphatic — `mainline.site` is THE authoritative source for every
-- `site_code` in the schema, and it names `ledger_intake.site_code` as one of the columns that
-- previously had no table behind it; a scope token the writer supplies is a scope token the
-- writer chooses. `mainline.site` holds four columns of provisioning metadata — site code, RLS
-- role name, tenant id, taxonomy generation — and no incident, person, clause or permit content,
-- so what a compromised relay gains is the ability to ENUMERATE SITES, while the exfiltration
-- risk the grant matrix is actually defending against (reading the record) is untouched and was
-- measured to be untouched. And the failure mode of the alternative is silent: a typo'd or forged
-- `site_code` produces a perfectly well-formed intake row that lands in a tree that should not
-- exist, and nothing in the system notices until a verifier cannot find the site.
--
-- The same fact applies to `fk_cp` (0076), `fk_permit` and `fk_discharge` (0077) — both of which
-- are VERBATIM from ARCHITECTURE.md §5.6 — so the grant matrix was already under-specified with
-- respect to the architecture's own foreign keys, independently of anything decided here.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- WHY A RANDOM UUID PRIMARY KEY. Intake is the highest-write table in the deployment and every
-- write is an append. A monotonic key would put every insert on one range and one leaseholder;
-- `gen_random_uuid()` spreads them across the cluster, so intake throughput scales with the
-- cluster instead of with one range. This is also why intake is SEPARATE from sequencing at all:
-- Certificate Transparency splits submission from merge for the same reason, and the price —
-- the Maximum Merge Delay — is paid with a Signed Disposition Receipt (spec/wire/receipt.md)
-- rather than with a lock.
--
-- WHY `canon_bytes` AND `payload` BOTH EXIST, AND MAY NEVER BE CONFLATED.
-- `leaf_hash = SHA-256(0x00 ‖ canon_bytes)` — RFC 6962 §2.1 leaf-domain separation. The hash is
-- computed by the CLIENT, under RFC 8785 JCS, by `trappoint_jcs.canon_v1`, and `payload_ver`
-- records which canonicaliser so the verifier can dispatch on it decades later.
--
--   DO NOT COMPUTE `leaf_hash` IN SQL. CockroachDB's `sha256()` returns a hex STRING, not BYTES
--   (cockroach#73896), and JSONB normalises and reorders keys — so `sha256(payload::STRING)` is
--   a value no third party can reproduce, which is the one property an evidentiary hash must
--   have. `payload` is here for humans and for `mainline_audit` views; `canon_bytes` is the
--   evidence. A verifier hashes `canon_bytes` and reports a DISCREPANCY when `payload`
--   disagrees, which is how attack A3 (payload_substitute) surfaces as a legible finding
--   instead of as nothing at all.
--
-- WHY THERE IS NO FLOAT ANYWHERE IN A PAYLOAD (CU-5). `canon_v1.canonicalise_payload()` raises
-- `NonEvidentiaryNumber` on an IEEE-754 float. No evidentiary quantity is a binary float, and the
-- ES6 number-serialisation path (exponent thresholds at −7/21, where Python's are −5/16) is the
-- single largest interoperability risk in a scheme whose whole value is that a stranger
-- reproduces our bytes. The ban is enforced in the client, not here, because the database sees
-- only opaque BYTES by then — recorded in this header so nobody reintroduces it from the SQL side.
--
-- `hlc` IS ADVISORY AND NOTHING MAY READ IT. `crdb_internal.cluster_logical_timestamp()` returns
-- the transaction's PROVISIONAL commit timestamp, which the KV layer may push before the
-- transaction commits (cockroach#79591). It is an ordering HINT for batch selection and nothing
-- else: the authoritative order is the sequencer's `seq`, and the authoritative TIME bracket is
-- the beacon (lower bound) and the RFC 3161 token (upper bound) on the checkpoint. No constraint,
-- no CHECK, no trigger and no proof in this repository may read `hlc`, and any query ordering by
-- it outside the sequencer's batch-selection anti-join is a defect. Migration 0072a puts that
-- sentence in the database itself, where `SHOW CREATE TABLE` shows it.
--
-- `recorded_at` IS A LOCAL CLOCK AND IS NOT A TIME BOUND. It is the wall clock of whichever node
-- served the insert. It is useful for operations and it is worthless as evidence of when
-- anything happened; the only defensible statements about time are the bracketed ones on the
-- checkpoint. Stated here so that no exhibit ever cites this column as a time.
--
-- SEQUENCED-NESS IS DERIVED, NEVER WRITTEN. There is no `sequenced` flag on this table and there
-- must never be one. The sequencer's batch is an anti-join against `mainline.ledger_leaf`
-- (spec/custody/ledger-schema.md §4), so the entire ledger write path is INSERT + SELECT — which
-- is why `mainline_ledger` holds exactly those grants, why `agent_relay` holds INSERT and not
-- even SELECT, and why the Managed MCP server's insert-only write surface is a genuine
-- structural match rather than a coincidence we oversell.
--
-- `intake_site_entry_unique` LOOKS REDUNDANT AND IS NOT. `entry_id` is already unique by primary
-- key, so `(site_code, entry_id)` is trivially unique too. It exists because a UNIQUE constraint
-- on exactly those two columns is what lets `mainline.ledger_leaf` take a COMPOSITE foreign key
-- onto them (migration 0073) — which is the only way a leaf's `site_code` is provably the site
-- its intake row declared, rather than a value the sequencer asserted. Redundancy a constraint
-- reads is not duplication; it is the difference between a fact enforced and a fact promised.
--
-- `subject_id` CARRIES NO FOREIGN KEY, DELIBERATELY. It is polymorphic across permits, change
-- requests, clauses, commits, checks and migrations — the ledger records facts about all of them
-- — and a `subject_kind` discriminator with eight conditional FKs would be a worse lie than an
-- honest UUID: it would be enforceable only for the kinds somebody remembered to add. The
-- binding that matters is `payload`, which names the subject in canonical bytes that were signed.
--
-- NO ROW-LEVEL TTL ON THIS TABLE, EVER. The TTL allowlist is exactly three tables
-- (`mainline_ops.outbox`, `mainline_meas.model_cache`, `mainline_meas.receipt_render_cache`) and
-- no `ledger_*` table is or may become a fourth. Silent expiry of an evidentiary row is document
-- destruction performed by a scheduler, which is worse than destruction performed by a person
-- because nobody decided to do it — see the Crimes (Document Destruction) Act 2006 (Vic), and
-- `tests/integration/custody/test_k2_exit.py::test_no_ttl_on_ledger`, which reads the live schema.

CREATE TABLE mainline.ledger_intake (
  entry_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
  site_code   STRING      NOT NULL,   -- FK to mainline.site: the ledger partition key has a source
  entry_kind  STRING      NOT NULL,   -- FK'd to mainline.ledger_entry_kind in band 0108-0129 (DM-11)
  subject_id  UUID        NOT NULL,   -- polymorphic by design; see header
  actor       STRING      NOT NULL,   -- ISO/IEC 27037 chain of custody: every leaf names who
  actor_kind  STRING      NOT NULL,   -- … and of what kind
  payload     JSONB       NOT NULL,   -- for humans and for mainline_audit views
  canon_bytes BYTES       NOT NULL,   -- RFC 8785 JCS bytes, produced by the CLIENT, stored verbatim
  payload_ver INT2        NOT NULL,   -- which canonicaliser; the verifier dispatches on it
  leaf_hash   BYTES       NOT NULL,   -- SHA-256(0x00 || canon_bytes)  [RFC 6962 §2.1]
  is_sandbox  BOOL        NOT NULL DEFAULT false,   -- guest-sandbox containment (D13); check 13
  hlc         DECIMAL     NOT NULL,   -- ADVISORY ordering hint ONLY. Nothing may read it. See 0072a
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),   -- local clock; NOT a time bound
  CONSTRAINT ledger_intake_pkey PRIMARY KEY (entry_id),
  CONSTRAINT intake_site_entry_unique UNIQUE (site_code, entry_id),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT actor_kind_known
    CHECK (actor_kind IN ('human', 'agent', 'service', 'external')),
  CONSTRAINT entry_kind_stated CHECK (entry_kind <> ''),
  CONSTRAINT actor_stated CHECK (actor <> ''),
  CONSTRAINT payload_ver_positive CHECK (payload_ver >= 1),
  CONSTRAINT canon_bytes_present CHECK (length(canon_bytes) > 0),
  CONSTRAINT leaf_hash_is_sha256 CHECK (length(leaf_hash) = 32),
  INDEX by_site_hlc (site_code, hlc ASC)
);
