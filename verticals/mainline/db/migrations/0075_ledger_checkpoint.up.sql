-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI18
-- I: I01, I16
-- COUNSEL-GATED: no
-- RATIONALE: THIS ROW IS THE ONLY THING IN THE DATABASE THAT IS EVIDENCE. Everything else in the
-- custody plane is a checksum computed by the future defendant over its own records. A checkpoint
-- is a signed commitment to the whole tree that LEFT THE TRUST BOUNDARY — to an RFC 3161 TSA, to
-- S3 Object Lock COMPLIANCE in a second account, to witnesses — before we could change our minds
-- about what the tree contained. The row here is the local copy of something a stranger already
-- holds; its value is entirely in the fact that we cannot reach the other copies.
--
-- migration:  0075_ledger_checkpoint
-- band:       0072-0079 · cu-ledger-ddl (custody) · see OWNERSHIP note in 0072
-- statements: 1
-- source:     ARCHITECTURE.md §5.6 (base shape), §7.3 · §18 slot 0075 · spec/wire/checkpoint.md
--             v1.0 §8 (storage binding, NORMATIVE) · docs/leads/custody.md CU-3, CU-4 ·
--             spec/custody/attacks.yaml A7, A8, A9
-- requires:   0002 CREATE SCHEMA mainline · 0021 mainline.site
-- owes:       (a) `fn_refuse_mutation` on this table, band 0130-0199;
--             (b) `admissible` is a PROJECTION and nothing yet writes it — see the OPEN
--                 CONTRADICTION section below, which is the most important paragraph in this file.
-- grants:     `fk_site` requires `SELECT ON mainline.site` for `agent_sequencer` — see the
--             MEASURED PLATFORM FACT block in 0072.
-- sqlstate:   23503 on fk_site · 23505 on ledger_checkpoint_pkey (two checkpoints at one tree
--             size — attack A7, checkpoint_swap) · 23514 on the shape CHECKs
-- forward-only; no .down.sql exists at or below the protected floor (DM-14).
--
-- THE STORAGE BINDING IS FROZEN. `spec/wire/checkpoint.md` v1.0 §8 maps each wire element to a
-- column of this table, and that document is the interface an opposing expert writing their own
-- verifier in Rust implements against. Renaming a column here is a documentation change; changing
-- what one MEANS is a migration of EVIDENCE, and there is no mechanism for reissuing a checkpoint.
--
--   body              the C2SP tlog-checkpoint note TEXT — the exact bytes that were signed
--   log_sig           the type-0x02 (ECDSA P-256) signature, DER exactly as AWS KMS returns it
--   root_hash         the 32-byte RFC 6962 Merkle Tree Hash at `tree_size`
--   canon_src_sha256  SHA-256 over the source of the canonicaliser that produced the leaves
--   beacon            the parsed drand + NIST extension lines
--   tsa_token         the RFC 3161 TimeStampToken over the note text
--   s3_version        the Object Lock COMPLIANCE version id of the published note
--
-- `body` STORES THE NOTE TEXT, NOT THE WHOLE NOTE. The signatures live in `log_sig` and in
-- `mainline.cosignature` precisely so that a cosignature arriving late is an INSERT into a second
-- table rather than an UPDATE of a row in an append-only one. That is not a storage optimisation;
-- it is what makes "append-only, no exceptions" survive contact with a witness network whose
-- replies arrive whenever they arrive.
--
-- TWO BEACONS, AND ONLY ONE OF THEM LOAD-BEARING OFFLINE (CU-4). `beacon` carries BOTH a drand
-- `quicknet` round and a NIST Randomness Beacon 2.0 pulse. drand's BLS12-381 G1 signature cannot
-- be verified by `cryptography`, so verifying it would break the verifier's one-dependency floor;
-- the NIST pulse is RSA-PKCS#1v1.5 / SHA-512 with an X.509 certificate and IS verifiable under
-- that floor. The verifier fully verifies the NIST pulse (check 6a), verifies drand's round→time
-- mapping arithmetically, and reports the BLS signature as SKIP(optional-extra) unless the extra
-- is installed (check 6b). Two independent lower bounds on time; neither silently assumed.
--
-- `tsa_token` AND `s3_version` ARE NULLABLE BECAUSE ANCHORING IS FANOUT, NOT A TRANSACTION. The
-- checkpoint is signed and recorded first; the TSA round-trip and the S3 PUT happen after, and
-- either can fail. A schema that required them would make an unreachable TSA a reason not to
-- record a checkpoint, which inverts the priority: recording the commitment is what we must never
-- fail to do. An unanchored checkpoint is a WEAKER exhibit and the verifier says so per check;
-- it is not an absent one. The 60-second window of undetectable mutation is real, is the honest
-- number, and is alarmed on rather than buried.
--
-- ═════════════════════════════════════════════════════════════════════════════════════════════
-- OPEN CONTRADICTION — `admissible`, and why this file ships it as specified anyway.
--
-- ARCHITECTURE.md §5.6 gives `admissible BOOL NOT NULL DEFAULT false` and calls it "projected:
-- quorum + diversity satisfied". `spec/wire/checkpoint.md` §5.3 says it is "a projection computed
-- from the cosignatures actually received … never a value a writer supplies". Migration 0112
-- (`fn_recall_policy_anchored`, already landed) READS it: a recall run may cite a policy only
-- when some admissible checkpoint has committed to a tree at least as large as the policy anchor.
--
-- But cosignatures arrive AFTER the checkpoint — `mainline.cosignature` has a foreign key onto
-- this table, so the checkpoint must exist first — and `spec/custody/ledger-schema.md` §3 makes
-- this table append-only with NO exception, the single carve-out in the whole custody surface
-- being `unwitnessed_debt.discharged_tree_size`. A column that starts false, can only become true
-- later, and can never be UPDATEd, is a column that is false forever. Under that reading MI18
-- refuses every recall run for all time.
--
-- This file does NOT resolve that by inventing a mechanism. It ships the column exactly as
-- specified and names the resolution, which belongs to the custody lead and the datamodel lead
-- jointly: `ledger_checkpoint.admissible` needs the same treatment `unwitnessed_debt
-- .discharged_tree_size` already has — a MONOTONE false→true carve-out in `fn_refuse_mutation`,
-- permitted on that column alone, only in that direction, and only when the quorum genuinely
-- holds in `mainline.cosignature` at that instant. A cosignature arriving late is a fact about
-- the world arriving late, not a rewrite of what was recorded, which is precisely the argument
-- §3 already accepted for discharge.
--
-- Until that trigger lands, `admissible` is FALSE for every row and every reader must treat it as
-- "not yet established" rather than as "established false". Both readings refuse; only one of them
-- is honest, and the difference matters in an exhibit. The alternative resolutions — computing
-- admissibility in a view, or writing it at insert time from a quorum that cannot exist yet — are
-- recorded here as considered and rejected: the first breaks 0112, which reads the column on this
-- table; the second makes the writer the author of its own admissibility, which is the exact
-- shape of the finding this projection discipline exists to close.
-- ═════════════════════════════════════════════════════════════════════════════════════════════
--
-- `issued_at` IS AN ADDITION TO §5.6, AND IT IS NOT A TIME BOUND. It is the local wall clock of
-- the node that recorded the checkpoint. It exists for exactly two operational readers: the K2
-- cadence measurement (`evidence/k2-checkpoint-cadence.json`, which must be a MEASUREMENT and not
-- an assumption) and the `checkpoint_age_seconds` deadman, which is DEFINED in K2 and FIRES from
-- K6 — an alarm invented after the incident is not an alarm. It is not evidence, no exhibit may
-- cite it as a time, and the verifier never reads it: the defensible statements about when a
-- checkpoint existed are the beacon (lower bound) and the RFC 3161 token (upper bound), which is
-- the entire reason both are collected. Backdating this column is attack A8/A9 and is caught by
-- checks 5 and 6 precisely because they do not consult it.
--
-- `tree_size = 0` IS LEGAL AND MUST STAY LEGAL. `root_hash` is then SHA-256(""), and a verifier
-- MUST accept a size-0 checkpoint (spec/wire/checkpoint.md §7.3): the alternative is a log that
-- cannot prove it was empty when it was empty. `tree_size_non_negative` therefore admits 0.
--
-- NO ROW-LEVEL TTL ON THIS TABLE, EVER. See 0072.

CREATE TABLE mainline.ledger_checkpoint (
  site_code        STRING      NOT NULL,
  tree_size        INT8        NOT NULL,   -- 0 is legal: a log must be able to prove it was empty
  root_hash        BYTES       NOT NULL,   -- RFC 6962 MTH at tree_size; SHA-256("") when size 0
  body             STRING      NOT NULL,   -- C2SP tlog-checkpoint note TEXT — the signed bytes
  beacon           JSONB       NOT NULL,   -- parsed drand round + NIST pulse (CU-4)
  log_sig          BYTES       NOT NULL,   -- KMS ECDSA_SHA_256 over body, DER as returned (CU-3)
  tsa_token        BYTES       NULL,       -- RFC 3161 TimeStampToken => UPPER time bound
  s3_version       STRING      NULL,       -- Object Lock COMPLIANCE version id of the note
  canon_src_sha256 BYTES       NOT NULL,   -- SHA-256 of the canonicaliser source that made the leaves
  admissible       BOOL        NOT NULL DEFAULT false,  -- PROJECTED; see OPEN CONTRADICTION above
  issued_at        TIMESTAMPTZ NOT NULL DEFAULT now(),  -- local clock; NOT a time bound; see above
  CONSTRAINT ledger_checkpoint_pkey PRIMARY KEY (site_code, tree_size),
  CONSTRAINT fk_site FOREIGN KEY (site_code) REFERENCES mainline.site (site_code),
  CONSTRAINT tree_size_non_negative CHECK (tree_size >= 0),
  CONSTRAINT root_hash_is_sha256 CHECK (length(root_hash) = 32),
  CONSTRAINT canon_src_is_sha256 CHECK (length(canon_src_sha256) = 32),
  CONSTRAINT body_stated CHECK (body <> ''),
  CONSTRAINT log_sig_present CHECK (length(log_sig) > 0),
  CONSTRAINT tsa_token_present_if_stated CHECK (tsa_token IS NULL OR length(tsa_token) > 0),
  CONSTRAINT s3_version_stated_if_present CHECK (s3_version IS NULL OR s3_version <> '')
);
