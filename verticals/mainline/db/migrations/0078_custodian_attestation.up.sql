-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01
-- I: I01, I16
-- COUNSEL-GATED: no
-- RATIONALE: CUSTODY OF THE CUSTODIAN. Every other table in this band records what the database
-- was asked to do. This one records what was done TO the database — who held the keys, which
-- triggers were installed, what the cloud control plane logged, whether the Object Lock retention
-- was still what we said it was. The classic failure of a tamper-evident log is that it proves
-- its own contents beautifully and can say nothing at all about the platform underneath it, so an
-- adversary with cloud-admin rights (T2) simply changes the platform. This table is the periodic,
-- hashed, Object-Locked answer to "and who was watching the watchers".
--
-- migration:  0078_custodian_attestation
-- band:       0072-0079 · cu-ledger-ddl (custody) · see OWNERSHIP note in 0072
-- statements: 1
-- source:     ARCHITECTURE.md §5.6 (verbatim shape, including the `kind` vocabulary) · §18 slot
--             0078 · §9.3 (ccloud CLI) · docs/leads/custody.md worker 9, §6 risk 4 ·
--             spec/custody/threat-model.md tiers T2/T3
-- requires:   0002 CREATE SCHEMA mainline
-- owes:       `fn_refuse_mutation` on this table, band 0130-0199.
-- sqlstate:   23505 on custodian_attestation_pkey · 23514 on kind_known, window_ordered,
--             payload_sha256_is_sha256, payload_object_key_stated, row_count_non_negative
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- ONLY THE HASH LIVES HERE. The collected JSON — a `ccloud` audit page, an IAM snapshot, the KMS
-- key policy, `pg_get_triggerdef()` output — goes to S3 with Object Lock COMPLIANCE in the second
-- account, and this row keeps `payload_object_key` and `payload_sha256`. Two reasons, and the
-- second is the real one: an IAM snapshot is large and unbounded, so storing it here would make an
-- append-only table grow without limit; and a copy held in the database we are attesting ABOUT is
-- a copy the adversary being attested about can rewrite. The hash is small enough to sit inside
-- the Merkle tree, and the object it names is somewhere we cannot delete it from.
--
-- THE `kind` VOCABULARY IS CLOSED AND IS TRANSCRIBED FROM §5.6 VERBATIM. Unlike
-- `ledger_intake.entry_kind` — which an out-of-schema writer supplies and which therefore becomes
-- an FK'd lookup table under DM-11 — every value here is produced by ONE program, the custody
-- patrol, inside this repository. A CHECK is the right instrument for a vocabulary whose only
-- writer ships in the same commit as the constraint: adding a kind should be a migration, because
-- adding a kind means adding a collector, and a collector nobody wrote a migration for is a
-- collector nobody reviewed.
--
--   ccloud_audit         the CockroachDB Cloud audit-log stream, folded into the ledger
--   ccloud_backup        backup inventory and retention, from the same CLI
--   inspect_database     the cluster's own consistency reporting
--   schema_fingerprint   the normalised, order-stable digest of the whole schema
--   trigger_definitions  the self-attesting gate: what the triggers ACTUALLY are, not what the
--                        migrations said they would be (verifier check 11 — see the caveat below)
--   kms_key_policy       who may use, disable or schedule deletion of the log signing key
--   s3_object_lock       the retention mode and period actually configured on the bucket
--   iam_snapshot         who could have done any of the above
--
-- CHECK 11 IS THE HIGHEST-VALUE ONE HERE AND IT RESTS ON AN UNANSWERED PLATFORM QUESTION.
-- `trigger_definitions` assumes `pg_get_triggerdef()` is available on the target cluster (GT-05,
-- open). If it is not, the fallback is `SHOW CREATE TABLE`, which loses per-trigger granularity;
-- check 11 then reports PASS(coarse) and the claim SOFTENS IN THE SAME COMMIT rather than being
-- quietly left at its stronger wording. That sentence is in the schema because that is where
-- somebody will look for it.
--
-- THE WINDOW IS A CLOSED INTERVAL AND IT IS ALLOWED TO BE A POINT. `window_ordered` admits
-- `window_from = window_to` because a snapshot-shaped attestation (IAM, KMS policy, schema
-- fingerprint) is a statement about an instant, while a stream-shaped one (audit, backup) covers a
-- period. Requiring a strict interval would force the snapshot collectors to invent an end time,
-- and an invented time in an evidentiary row is exactly what this band refuses everywhere else.
--
-- THERE IS NO `site_code`. Custody of the custodian is a CLUSTER-WIDE and ACCOUNT-WIDE fact: one
-- KMS key, one IAM account, one schema, many sites. Scoping these rows per site would either
-- duplicate them or imply a per-site key policy that does not exist.
--
-- NO ROW-LEVEL TTL ON THIS TABLE, EVER. See 0072.

CREATE TABLE mainline.custodian_attestation (
  attestation_id     UUID        NOT NULL DEFAULT gen_random_uuid(),
  kind               STRING      NOT NULL,
  window_from        TIMESTAMPTZ NOT NULL,
  window_to          TIMESTAMPTZ NOT NULL,
  payload_object_key STRING      NOT NULL,   -- the Object-Locked S3 key; the JSON lives there
  payload_sha256     BYTES       NOT NULL,   -- … and only its digest lives here
  row_count          INT8        NULL,       -- NULL for snapshot kinds; a count for stream kinds
  collected_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT custodian_attestation_pkey PRIMARY KEY (attestation_id),
  CONSTRAINT kind_known CHECK (kind IN (
    'ccloud_audit', 'ccloud_backup', 'inspect_database', 'schema_fingerprint',
    'trigger_definitions', 'kms_key_policy', 's3_object_lock', 'iam_snapshot')),
  CONSTRAINT window_ordered CHECK (window_to >= window_from),
  CONSTRAINT payload_sha256_is_sha256 CHECK (length(payload_sha256) = 32),
  CONSTRAINT payload_object_key_stated CHECK (payload_object_key <> ''),
  CONSTRAINT row_count_non_negative CHECK (row_count IS NULL OR row_count >= 0),
  INDEX by_kind_window (kind, window_from DESC)
);
