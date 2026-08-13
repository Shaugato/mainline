<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Byte-valued derived material (hash / HMAC / digest / canonicalisation) — divergence census

**Analyst:** `w2-derived-digests` · **Date:** 2026-08-13 · **Mode:** READ-ONLY
**Worlds built for this report:** `d_w2_derived_digests` (digest arithmetic only) and
`d_w2_chain` — chained 271/271 by `scripts/chain/apply_chain.py`, then seeded by applying
`db/seeds/demo/demo_world.sql` and `demo_permit.sql` verbatim, i.e. the world
`scripts/deploy/seed_demo.py` puts into Cloud `mainline_demo`.

## Verdict

**33 recipes enumerated, 26 executed on both ends. 4 DIVERGENT, 9 LATENT, 13 HELD.**

The headline is that **the beat-4 signer-FK defect is still in the tree.** It was removed
from `gate_run.py` and replaced by `credentials.resolve_credential_id`, but
`transitions.py:971` and `:973` still bind `_sha("cred","signer")` / `_sha("cred","cosigner")`
as `signer_credential_id` / `countersigner_credential_id` on `POST /v1/checks/{check_id}/disposition`
— a routed, committing, unauthenticated kernel endpoint. I drove the real handler against
the real seed and got `409 · 23503 · disposition_signer_credential_id_fkey`, reported to the
caller as `outcome: "refused", class: "gate"` — the exact "an exhibit the gate never produced"
failure `credentials.py`'s own docstring says must not happen. The AST guard written on
2026-08-13 to stop this recurring (`test_credentials.py:453-470`) parses **only**
`GATE_RUN_SOURCE`, so it cannot see the surviving copy; and the test that exercises the
surviving copy (`test_transitions.py:562`) runs against a world seeded by
`scripts/proof/gate_refusal.py:844`, which computes `_sha("cred","signer")` — the same
expression the code under test uses. Test and code agree because they share the expression;
both differ from the only seed that is deployed. That is the census's defect shape, intact.

Two more executed divergences: `cloud_chain.py`'s local re-statement of the
`tree_fingerprint` recipe produces a different digest from the authority it claims to
mirror (measured, same tree, `05b36242…` vs `278093ae…`), and the **deployed Lambda cannot
import `trappoint_jcs` at all** — `build_lambda.sh` packages only `mainline_demo_api`,
`psycopg`, `psycopg_binary` and `web/` — so every gate run in production takes the
`except ImportError` branch of `gate_run.canonical_json` and reports a canonicalisation
string that no test and no sealed bundle has ever contained.

The good news is real and was measured, not assumed: **RFC 6962 and RFC 8785 agree
byte-for-byte across Python and TypeScript** (leaf, node, MTH n=0..7, `k` for n=2..9, and
the three documented JCS traps), the console's hand-written FIPS 180-4 SHA-256 agrees with
node's on all six probes including a megabyte, `db.py`'s SigV4 key derivation reproduces
AWS's published vector exactly, and the two server-computed digests (`chain_digest`,
`clearance_digest`) have exactly one definition each and are verified by triggers.

**The systemic observation for the next wave:** every derived-byte column in this schema is
protected by `CHECK (length(x) = 32)` and nothing else — `disposition_evidence_is_sha256`,
`disposition_vocab_is_sha256`, `disposition_competency_is_sha256`, `leaf_hash_is_sha256`,
`merge_commit_sized`, `merge_clearance_digest_sized`. A length CHECK admits any 32 bytes.
The only derived value in the whole disposition row that the database actually *owns* is
`signer_credential_id`, and that is precisely the one this API still derives on one of its
two writing paths.

---

## Inventory

`held by` = the executable mechanism that fails when the two ends stop agreeing, or `NOTHING`.

### A · Credential identity (FK-backed — the only load-bearing derived bytes)

| # | value | definition A (file:line) | definition B (file:line) | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | `signer_credential_id` | `transitions.py:971` `_sha("cred","signer")` → `487adc50…` | `demo_world.sql:124` `digest('mainline-demo/credential/demo.signer','sha256')` → `ff356d14…` | **DIVERGENT** | NOTHING (FK fires at runtime; the AST guard covers `gate_run.py` only) | **HIGH** |
| A2 | `countersigner_credential_id` | `transitions.py:973` `_sha("cred","cosigner")` → `916b6121…` | `demo_world.sql:132` `digest('mainline-demo/credential/demo.countersigner','sha256')` → `8d7b089f…` | **DIVERGENT** | NOTHING (same) | **HIGH** |
| A3 | same, `gate_run` path | `gate_run.py:456-457` `resolve_credential_id(conn, …)` — reads the row | `demo_world.sql:124/132` | HELD | `disposition_signer_credential_id_fkey` + `test_credentials.py:453` AST walk + measured `verdict PROVEN` | — |
| A4 | same, proof seeder | `gate_refusal.py:844` `_sha("cred","signer")`/`("cred","cosigner")` | `demo_world.sql:124/132` | DIVERGENT-by-design (its own world) | it seeds `proof.signer`, not `demo.signer` | LOW |

### B · Digests written by the demo and *projected away* (inert, not wrong)

| # | value | definition A | definition B | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | `competency_sha256` | `gate_run.py:624` / `transitions.py:978` `_sha("competency", sub)` → `8c7a0b03…` | `demo_world.sql:102` `digest('mainline-demo/competency/demo.signer','sha256')` → `c63cf763…` | DIVERGENT **but INERT** | `0102_fn_disposition_project.sql:221` `NEW.competency_sha256 := v_competency_sha256` overwrites the client value from `mainline.person` | LOW |
| B2 | `competency_sha256` (countersigner) | `gate_refusal.py:872` → `fd457c67…` | `demo_world.sql:112` → `83b4bf73…` | DIVERGENT **but INERT** | same trigger | LOW |

### C · Digests written by the demo that survive the write (no owner, no FK)

| # | value | definition A | definition B / owner | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | `defeater_vocab_sha256` | `gate_run.py:608` / `transitions.py:967` `_sha("defeater-vocab")` → `7ad8d49c…` | `mainline.defeater_option.vocab_sha256` — **0 rows in the deployed seed** | **DIVERGENT** (asserts a vocabulary the database does not hold) | `CHECK (length(defeater_vocab_sha256)=32)` only; no FK | MEDIUM |
| C2 | `evidence_sha256` | `gate_run.py:610` `_sha("evidence", disposition_id)` | none — synthetic, per-run | HELD (single definition) | `CHECK length = 32` | — |
| C3 | `authenticator_data` | `gate_run.py:618` `_sha("authenticator", disposition_id)` | none — synthetic | HELD (single definition) | `CHECK length > 0` | — |
| C4 | `client_data_json` | `gate_run.py:619` `canonical_json({"challenge":…, "type":"webauthn.get"})` | none — synthetic | LATENT (see F-03: two canonicalisers) | `CHECK length > 0` | LATENT |
| C5 | exposure `receipt_digest` | `transitions.py:783` `_sha("exposure", receipt_id, json)` → per-call | `demo_permit.sql:241` `digest('mainline-demo/receipt/dec0de00-0008','sha256')` → `993c00c3…` | different rows, not a pair | `CHECK` on shape only | LOW |
| C6 | exposure-line `payload_digest` | `transitions.py:807` `_sha("line", check_id)` → `6e4092de…` | `demo_permit.sql:249` `digest('mainline-demo/exposure-line/dec0de00-0007','sha256')` → `d48e0eb9…` | different rows, not a pair | NOTHING | LOW |

### D · `merged_commit` — one column, two byte layouts

| # | value | definition A | definition B | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | `merged_commit` | `scenario.py:213` `demo_uuid("commit").bytes + demo_uuid("commit").bytes` → `4fbbd371…4fbbd371…` (a uuid5 written twice) | `gate_refusal.py:846` `_sha("commit","permit-merge")` → `df88ffa7…` (a sha256) | LATENT — two incompatible layouts for one column | `merge_commit_sized CHECK (length(merged_commit)=32)` — a **length** guard, not a value guard | LATENT |
| D2 | `merged_commit` at rest | `0117_proc_merge_permit.sql:157` stores `a_merged_commit` verbatim | `demo_permit.sql` seeds **none** (the permit is unmerged) | HELD (no second definition at rest) | measured: gate_run beat 4 lands `4fbbd371…4fbbd371…` | — |

### E · Commit ids, ledger roots, recall roots (proof world vs demo world)

| # | value | definition A (`gate_refusal.py`) | definition B (`demo_*.sql`) | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | clause-v1 commit | `:845` `_sha("commit","clause-v1")` → `a92e16e2…` | `demo_world.sql:169` → `9f12114d…` | two worlds, not one pair | each is self-consistent within its seed | LOW |
| E2 | root commit | (none) | `demo_world.sql:158` → `bbaa7455…` | single definition | — | — |
| E3 | `cose_public_key` | `:883` `_sha("cose", sub)` → `fa11abd6…` | `demo_world.sql:126` → `7299197b…` | two worlds | — | LOW |
| E4 | `aaguid` (16 B) | `:883` `_sha("aaguid", sub)[:16]` → `5110860f…` | `demo_world.sql:127` `substring(digest(…) FROM 1 FOR 16)` → `3aec9d61…` | two worlds; **the truncation rule agrees** (first 16 bytes, 1-indexed inclusive) | executed | LOW |
| E5 | ledger `root_hash` | `:1031` `_sha("root", site_code)` → `d28cd808…` | `demo_world.sql:406` → `74f0845f…` | two worlds | — | LOW |
| E6 | `canon_src_sha256` | `:1035` `_sha("canon-src")` → `ee8c5891…` | `demo_world.sql:412` → `23a20be3…` | two worlds | — | LOW |
| E7 | `calibration_set_sha256` | `:1054` `_sha("calibration")` → `e152337e…` | `demo_world.sql:454` → `0711336f…` | two worlds | — | LOW |
| E8 | recall `corpus_root` | `transitions.py:773` **reads** it from `mainline_meas.silence_receipt` | `demo_permit.sql:237` `digest('mainline-demo/recall/corpus-root','sha256')` → `91e35cc5…` | HELD — read, not derived | the read itself | — |

### F · Server-computed digests (one definition each)

| # | value | definition | second definition? | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | `permit_event.chain_digest` | `0059_permit_event.sql:55` `BYTES AS (digest(prev_digest \|\| payload::STRING::BYTES,'sha256')) STORED` | **none** — every caller READs the predecessor (`0117:107`, `transitions.py:588`, `demo_permit.sql:296`, `_world.py:1005`). Nothing recomputes it in Python or TypeScript. | HELD | `fn_permit_event_chain` (0105) re-derives and refuses `P0001`; `trg_permit_event_chain` (0125) welds it | — |
| F2 | `cr_event.chain_digest` | `0060_cr_event.sql:55` — identical recipe | none | HELD | `fn_cr_event_chain` (0106) | — |
| F3 | `clearance_digest` | `0117_proc_merge_permit.sql:110-118` `digest(string_agg(check\|\|':'\|\|disp, '\|' ORDER BY …), 'sha256')` | none | HELD | server-side; `CHECK length = 32`; measured empty-set case = `e3b0c442…` = `sha256(b"")` in Python | — |

### G · Canonicalisation and leaf hashing (cross-language and cross-path)

| # | value | definition A | definition B | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| G1 | canonical bytes, demo-api | `gate_run.py:227` `trappoint_jcs.canonicalise` | `gate_run.py:229-234` `json.dumps(sort_keys, compact)` fallback | **DIVERGENT in what production runs** — the Lambda package has no `trappoint_jcs` | NOTHING; the `try/except ImportError` is silent and the deciding fact is in `build_lambda.sh` | MEDIUM |
| G2 | canonical bytes, capture | `capture_demo_bundle.py:472` `trappoint_jcs` / `:465` fallback | same pair | LATENT (same shape, offline tool) | NOTHING | LATENT |
| G3 | JCS, Python vs TypeScript | `trappoint_jcs.canonicalise` | `console/src/verify/jcs.ts` | **HELD** — byte-identical on 5 probes incl. the 3 documented traps (`1e-5`/`1e17` layout, UTF-16 ordering of U+1F602 vs U+FB33, ` `/U+007F/solidus escaping) | vectors captured from Python and committed under `console/tests/vectors/` | — |
| G4 | `leaf_hash = SHA-256(0x00 ‖ canon)` | `gate_run.py:240-243` `_leaf` | `transitions.py:522` inline; `gate_refusal.py:1261`; `trappoint_ledger…tree.hash_leaf:94`; `console/src/verify/rfc6962.ts:46` | HELD by value (all executed equal, e.g. `abc` → `609f6e36…`); **4 copies of the expression** | `leaf_hash_is_sha256 CHECK (length = 32)` only — a length guard; value equality is coincidence of 4 literal copies | LATENT |
| G5 | RFC 6962 `MTH` / `nodeHash` / `k` | `trappoint_ledger/merkle/tree.py:94,105,112` | `console/src/verify/rfc6962.ts:46,51,60,74` | HELD by measurement (n=0..7 and k=2..9 identical) but **no shared vector file** — Python uses inline CT vectors, TypeScript uses `console/tests/vectors/rfc6962.json`; no test reads both | NOTHING cross-language | LATENT |
| G6 | SHA-256 itself, in TypeScript | `console/src/verify/sha256.ts:70` hand-written FIPS 180-4 | WebCrypto / node `createHash` | HELD | `tests/unit/verify/sha256.test.ts` asserts the two agree; independently measured here, 0 mismatches on 6 probes incl. 1 MB | — |

### H · Fingerprints and signing keys

| # | value | definition A | definition B | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | `tree_fingerprint` | `trappoint_migrate/fingerprint.py:142-186` (authority) | `scripts/deploy/cloud_chain.py:511-519` (local "same rule" fallback) | **DIVERGENT** — `278093ae…` vs `05b36242…` on the identical 271-file tree | NOTHING; the fallback is only reached when the workspace is not importable, i.e. exactly when nobody is looking | HIGH |
| H2 | `live_fingerprint` | `trappoint_migrate.fingerprint.live_fingerprint` | `cloud_chain.py:535+` catalogue fallback | LATENT — the docstring admits the fallback is weaker and records which ran | the recorded `mode` field | LATENT |
| H3 | SigV4 signing key | `db.py:156-158` `HMAC` chain `AWS4|date|region|service|aws4_request` | AWS's published spec | HELD by value (reproduces `c4afb1cc…` for the AWS example vector) — but **held by NOTHING in this repository**: `test_envelope.py:475-476` asserts only the `Authorization` prefix and the credential scope, never a key or signature | NOTHING | LATENT |
| H4 | frame content address | `capture_demo_bundle.py:266-267` (Python) | `console/scripts/capture-bundle.ts:90-95` (TypeScript) | HELD for every real key (3/3 identical); **LATENT** for a key with a leading space: Python yields `frames/-<hex>.json`, TypeScript yields `frames/REQ-<hex>.json` | `capture-bundle.ts check` re-derives; nothing compares the two languages | LATENT/LOW |
| H5 | bundle-file `sha256` | `bundle_manifest.py:170` `_sha256_file` | `console/scripts/capture-bundle.ts:115` `sha256Hex`; verified in-browser by `features/evidence/audit.ts:150` | HELD | the console's audit screen recomputes and reports mismatch | — |

### I · Seed-internal digest/text pairs

| # | value | definition A | definition B | status | held by | severity |
| --- | --- | --- | --- | --- | --- | --- |
| I1 | `clause_version.canon_sha256` | `demo_world.sql:242` `digest('SYNTHETIC — Before any intrusive work…','sha256')` | `demo_world.sql:~236` `canon_text`, the same 120-character literal typed a second time | LATENT — measured equal (`9b152601…` == `digest(canon_text)` == Python `sha256(canon_text)`) | NOTHING; two hand-typed copies of one string in one file | LATENT |
| I2 | `blood_root` genesis | `demo_world.sql:245` `'\x00…00'::BYTES` (32 zero bytes) | `0117:145` `decode(repeat('00',32),'hex')`; `rfc6962.ts:43` `GENESIS_LINK = new Uint8Array(32)` | HELD (all three are 32 zero bytes) | executed | — |

---

## Findings

### F-01 The beat-4 signer-FK defect is still live in `transitions.py` — severity: **HIGH**

- **Divergence:** `verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py:971`
  binds `_sha("cred", "signer")` = `487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765`
  as `signer_credential_id`, and `:973` binds `_sha("cred", "cosigner")` =
  `916b6121c8188a00ec5deff08e61ea034a58ed16d8ec85115c40cf7cb049d7fb` as
  `countersigner_credential_id` ·
  `verticals/mainline/db/seeds/demo/demo_world.sql:124` enrols
  `digest('mainline-demo/credential/demo.signer','sha256')` =
  `ff356d1461921438bbbc5d644db8793669cb948a46bddc2e8fb5ebef959bdf0c` and `:132` enrols
  `8d7b089f4c0aec7d890810a5aca3ebd9f57e2ae8786e2749e576200019b18ebe`.
  The column is `BYTES NOT NULL REFERENCES mainline.signing_credential (credential_id)`
  (`0066_disposition.sql:117-118`, and `:122-123` for the countersigner).

- **Command** — the digests, both ends, executed:
  ```
  $ .venv/Scripts/python.exe scratchpad/pairs.py
  credential/demo.signer  (transitions.py:971 vs demo_world.sql:124)
      py   487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765
      sql  ff356d1461921438bbbc5d644db8793669cb948a46bddc2e8fb5ebef959bdf0c
      ->   *** DIVERGENT ***
  credential/demo.countersigner (transitions.py:973 vs demo_world.sql:132)
      py   916b6121c8188a00ec5deff08e61ea034a58ed16d8ec85115c40cf7cb049d7fb
      sql  8d7b089f4c0aec7d890810a5aca3ebd9f57e2ae8786e2749e576200019b18ebe
      ->   *** DIVERGENT ***
  ```

- **Command** — the real handler, against the real seed (`d_w2_chain`, chained 271/271 then
  `demo_world.sql` + `demo_permit.sql` applied verbatim; `MAINLINE_DEMO_ALLOW_MUTATION=1`,
  which is the lift the 423 message itself instructs an operator to use):
  ```
  $ PYTHONPATH=verticals/mainline/apps/demo-api/src .venv/Scripts/python.exe scratchpad/sign_proof.py
  ```
- **Output** (verbatim, trimmed to the decisive lines):
  ```
  HTTP 409
      "procedure": "trappoint.sign_disposition",
      "outcome": "refused",
      "refusal": {
        "class": "gate",
        "constraint": "disposition_signer_credential_id_fkey",
        "sqlstate": "23503",
        "message": "insert on table \"disposition\" violates foreign key constraint
                    \"disposition_signer_credential_id_fkey\"",
        "constraint_source": "reported"
  ```
  For contrast, on the **same database**, the repaired path is clean:
  ```
  $ … from mainline_demo_api.gate_run import gate_run …
  verdict PROVEN
  failures []
  ```

- **Command** — which world each side actually enrols, across every chained database on the
  local node:
  ```
  $ .venv/Scripts/python.exe -c "… SELECT signer_sub, encode(credential_id,'hex') FROM mainline.signing_credential …"
  w_w4_api_transitions: creds=2 permits=31 [('proof.countersigner','916b6121…'), ('proof.signer','487adc50…')]
  w_w3_demotruth:       creds=2 permits=1  [('demo.countersigner','8d7b089f…'), ('demo.signer','ff356d14…')]
  d_demolead:           creds=2 permits=1  [('demo.countersigner','8d7b089f…'), ('demo.signer','ff356d14…')]
  ```
  `w_w4_api_transitions` is the world `test_transitions.py` runs against. **Its two credential
  ids are literally the two constants `transitions.py` derives.**

- **What a user or judge sees:** `POST /v1/checks/{check_id}/disposition` — route 14 of 17,
  declared at `app.py:194`, unauthenticated on the Function URL — answers `409` with a
  refusal envelope whose `class` is `"gate"` and whose `constraint` is a foreign key on a
  table the signer never mentioned. The API tells the caller the GATE refused the signature.
  It did not: the gate was never consulted. This is verbatim the failure mode
  `credentials.py:38-49` was written to eliminate ("reported as though the GATE had spoken.
  It had not"), eliminated on one of the two paths.
  **Reachability, stated honestly so the severity is not inflated:** on the deployed demo
  `_demo_guard` (`transitions.py:342`) returns `423 demo_subject_write_protected` for the
  seeded permit before the INSERT is reached, and `mainline_demo` holds exactly one permit,
  so a judge pressing the demo button does not hit this. It fires the moment
  `MAINLINE_DEMO_ALLOW_MUTATION` is set to anything outside `{"", "0", "false"}`
  (`transitions.py:315`) — which is exactly what the 423 message tells an operator to do —
  or the moment a second permit exists in the database. That is why this is HIGH and not
  CRITICAL, and why it is not LOW: it is an unfixed instance of the defect that produced a
  NO-GO, sitting behind a guard, on the endpoint the product's kernel is named after.

- **What would have caught it:** **NOTHING DOES.**
  1. `test_credentials.py:453-470 test_gate_run_derives_no_credential_id` walks
     `GATE_RUN_SOURCE` only. Its own docstring narrows the scope ("The other `_sha` call
     sites in that file are left alone") and never mentions `transitions.py`, which holds a
     private `_sha` at `:257` with the identical body and two `"cred"` call sites.
  2. `test_transitions.py:562 test_sign_disposition_then_merge_commits` exercises the exact
     line and passes, because `w4_database` (`test_gate_run.py:485-497`) seeds through
     `scripts/proof/gate_refusal.py`, whose `:844` computes the same
     `_sha("cred","signer")`. The test cannot disagree with the code; it reads the same
     expression.
  3. The FK itself is the only real mechanism, and it only speaks when the code meets
     `demo_world.sql` — which no test in `verticals/mainline/apps/demo-api/tests/test_transitions.py`
     arranges. (Root cause is W4's: the test never runs against the deployed seed.)
  - **The one-line fix shape:** `transitions._sign_disposition` should call
    `credentials.resolve_credential_id(conn, signer_sub)` and
    `…(conn, countersigner_sub)` before the INSERT, exactly as `gate_run.py:456-457` does,
    and the AST guard should be re-pointed at both source files rather than one.

### F-02 `cloud_chain.py`'s `tree_fingerprint` fallback does not reproduce the authority — severity: **HIGH**

- **Divergence:** `packages/trappoint-migrate/src/trappoint_migrate/fingerprint.py:142-186`
  is the authority ·
  `scripts/deploy/cloud_chain.py:505-519` restates it locally and its docstring at `:499-503`
  claims "the same rule stated locally … so that a machine without the workspace installed
  still gets the same digest for the same tree." It does not. Four differences:
  the authority globs `FINGERPRINT_SUFFIXES = (".sql",".j2",".sql.j2")` (`fingerprint.py:71`)
  while the fallback globs `*.sql`; the authority hashes each file to a per-file digest and
  then accumulates **those digests** (`:167-181`) while the fallback accumulates the raw
  path and body; the authority's `normalise` (`:109-124`) pops trailing blank lines only
  while the fallback uses `.strip("\n")`, which also removes leading ones; and the
  authority sorts by *relpath* while the fallback sorts by absolute POSIX path.

- **Command:**
  ```
  $ .venv/Scripts/python.exe -c "
    from trappoint_migrate.fingerprint import stable_tree_fingerprint …
    <the cloud_chain.py:511-519 fallback, transcribed verbatim> …"
  ```
- **Output:**
  ```
  authority  stable_tree_fingerprint : 278093ae94ced0ab4a418f800345014921be7e653deb4825cc7b76acddbfb599
  cloud_chain.py:511-519 fallback    : 05b362422eb199a583693957159207637b4f7a6e1c1a281617c88b8436d53e85
  AGREE                              : False
  files: *.sql = 271  authority-suffixed = 271
  ```
  (The file-set is identical at 271 — so this is purely the recipe, not the inputs. The
  authority's value `278093ae…` is the one recorded at `evidence/deploy/migrations-ledger.json:105`.)

- **What a user or judge sees:** `cloud_chain.py:1119` compares the marker's stored
  `tree_fingerprint` against `tree_fingerprint(migrations)` and prints
  `"(tree <recorded> recorded, <now> now)"`; `:1371` escalates that to
  `reattest … building <verify_db> to find out whether it matters`. On any machine where
  the workspace does not import — a fresh clone, a CI runner without `pip install -e`, the
  deploy box the `except Exception` clause exists for — **every** deploy reports schema
  drift against a tree that has not changed, and offers to rebuild a verification database
  to chase it. Conversely, a marker written by the fallback and later read by the authority
  reports drift in the other direction. The fingerprint's whole job is to make "the tree
  moved" a decidable question, and this makes the answer depend on whether a package
  happened to import.

- **What would have caught it:** **NOTHING DOES.** No test executes the fallback branch —
  it is guarded by `except Exception: # noqa: BLE001`, which is unreachable in any
  environment where the test suite itself can run.

### F-03 The deployed Lambda cannot import `trappoint_jcs`; every test and the sealed bundle say it can — severity: **MEDIUM**

- **Divergence:** `gate_run.py:226-237` chooses `trappoint_jcs.canonicalise` when it imports
  and a local `json.dumps(sort_keys=True, separators=(",",":"))` when it does not, and
  reports which ran in `transaction.canonicalisation` ·
  `scripts/deploy/build_lambda.sh:722-727` copies only `mainline_demo_api/`, the console
  `dist/` and the bundle into the staging tree, and `:1051-1065` pip-installs only
  `psycopg` and `psycopg-binary` with `--no-deps --no-index`. `:744-750` asserts the package
  holds `mainline_demo_api/app.py`, `psycopg/__init__.py`, `psycopg_binary/__init__.py`,
  `web/index.html`, `web/bundle/manifest.json` — and nothing else. **There is no
  `trappoint_jcs` in the artefact.**

- **Command:**
  ```
  $ PYTHONPATH=verticals/mainline/apps/demo-api/src .venv/Scripts/python.exe -c "
      import sys, importlib.abc
      class Block(importlib.abc.MetaPathFinder):
          def find_spec(self, name, path=None, target=None):
              if name.startswith('trappoint_jcs'):
                  raise ImportError('absent from the Lambda package')
              return None
      sys.meta_path.insert(0, Block())
      from mainline_demo_api.gate_run import canonical_json
      print(canonical_json({...})[1])"
  ```
- **Output:**
  ```
  LAMBDA-SHAPED sys.path -> canonicalisation = 'mainline_demo_api.gate_run.canonical_json (sorted-key JSON; ASCII payloads only)'
  ```
  against, on the same machine with the venv intact and against the real seeded database:
  ```
  $ … gate_run(conn) …
  canonicalisation trappoint_jcs.canonicalise
  ```
  and, recorded in the sealed evidence a judge is handed:
  ```
  $ grep -rn canonicalisation evidence/
  evidence/deploy/bundle-capture.json:408:  "canonicalisation": "trappoint_jcs.canonicalise",
  ```

- **What a user or judge sees:** the live Function URL's `gate-run` payload says the leaf was
  canonicalised by `mainline_demo_api.gate_run.canonical_json (sorted-key JSON; ASCII
  payloads only)`; the offline bundle beside it, captured from a workstation, says
  `trappoint_jcs.canonicalise`. A judge comparing the two — which is precisely what the
  evidence surface is for — sees the product disagreeing with its own sealed record about
  how the custody leaf was derived. The `leaf_hash` bytes happen to coincide because the
  merge payload is three ASCII strings; the two implementations are **not** interchangeable
  in general, measured:
  ```
  jcs      b'{"a":"\xc3\xa9","b":1,"c":[1,2]}'
  fallback b'{"a":"\xc3\xa9","b":1.0,"c":[1,2]}'
  same     False
  ```
  Any payload carrying a float would produce a `leaf_hash` that no RFC 8785 verifier can
  reproduce — the exact failure `0072_ledger_intake.sql:9` says the design exists to prevent.

- **What would have caught it:** **NOTHING DOES.** Every test runs in the repo venv where
  `trappoint_jcs` imports; the `except ImportError` branch is dead in the test environment
  and is the only live branch in production. No `contracts/gate-run.schema.json` enum, no
  test, and no acceptance check pins `transaction.canonicalisation` to either value.
  (This is the `dict_row` defect's exact shape, in a different dimension: the suite runs on
  a code path production never uses.) Cross-reference W4 and W7.

### F-04 Every demo disposition records a defeater-vocabulary digest for a vocabulary the database does not hold — severity: **MEDIUM**

- **Divergence:** `gate_run.py:608` and `transitions.py:967` bind
  `_sha("defeater-vocab")` = `7ad8d49c2edd93f0a8fd3cd6b2a5d6cd225810805527a1a3f2f497aec819db3f`
  as `defeater_vocab_sha256` · the column that owns such a digest is
  `mainline.defeater_option.vocab_sha256`, and `demo_world.sql` seeds **zero** rows into it.
- **Command / Output:**
  ```
  $ … SELECT count(*), … FROM mainline.defeater_option
  defeater_option: (0, '(none)')
  $ … SELECT conname, pg_get_constraintdef(oid) … contype='f' … (filtered for vocab)
  FKs mentioning vocab: []
  $ … contype='c'
     disposition_vocab_is_sha256 = CHECK ((length(defeater_vocab_sha256) = 32))
  ```
- **What a user or judge sees:** the disposition surface renders a `defeater_vocab_sha256`
  chip claiming the signer chose `MECHANISM_PRESENT_AND_VERIFIED` from a controlled
  vocabulary identified by `7ad8d49c…`. Nothing in the database is that vocabulary. A judge
  who asks "which vocabulary?" finds an empty table. The record is not falsifiable, which is
  the one thing this product says its records always are.
- **What would have caught it:** **NOTHING DOES** — `disposition_vocab_is_sha256` checks
  length only, and `0102_fn_disposition_project.sql` does not project this column (see its
  `NEW.… :=` list, which covers `competency_sha256` at `:221` but not this one), so the
  client's value survives the write.

### F-05 `merged_commit` has two incompatible 32-byte layouts and only a length CHECK — severity: **LATENT**

- **Divergence:** `scenario.py:213` builds it as `demo_uuid("commit").bytes +
  demo_uuid("commit").bytes` — one uuid5 written twice, `4fbbd37106cf5e02b03a49ce2ba5c4aa`
  repeated · `scripts/proof/gate_refusal.py:846` builds the same column as
  `_sha("commit","permit-merge")` = `df88ffa7b1d09d9664237171f9a2c1788ccf02204fdb1afb3f28b6d0934b78c7`,
  a genuine sha256.
- **Command / Output:** measured, and confirmed at rest after a real beat 4 on the seeded
  world:
  ```
  merged_commit (scenario.py:213 uuid5*2 vs gate_refusal.py:846 _sha)
      py   4fbbd37106cf5e02b03a49ce2ba5c4aa4fbbd37106cf5e02b03a49ce2ba5c4aa
      sql  df88ffa7b1d09d9664237171f9a2c1788ccf02204fdb1afb3f28b6d0934b78c7
      ->   *** DIVERGENT ***
  $ … gate_run(conn) … beats[3].observed.merge_record.merged_commit
      "4fbbd37106cf5e02b03a49ce2ba5c4aa4fbbd37106cf5e02b03a49ce2ba5c4aa"
  $ … pg_get_constraintdef … merge_record
      merge_commit_sized = CHECK ((length(merged_commit) = 32))
  ```
- **What a user or judge sees:** the completion record's `merged_commit` is a UUID stuttered
  to 32 bytes. A reader who recognises the first half as the second half — and the value is
  rendered as hex on the merge surface, so it is visible at a glance — learns that the
  "commit this merge records" is not a commit at all. `demo_permit.sql` seeds no
  `merged_commit`, so nothing in the database contradicts it.
- **What would have caught it:** **NOTHING DOES.** `merge_commit_sized` admits any 32 bytes.
  This is the general shape the next wave should search for: six length CHECKs on derived
  columns in this schema, zero value guards.

### F-06 RFC 6962 exists twice, in two languages, with no shared vector file — severity: **LATENT**

- **Divergence:** `packages/trappoint-ledger/src/trappoint_ledger/merkle/tree.py:94,105,112`
  · `verticals/mainline/apps/console/src/verify/rfc6962.ts:46,51,60,74`.
- **Command / Output** (Python left, TypeScript right, same leaf hashes as input):
  ```
  MTH0 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  ==
  MTH1 022a6979e6dab7aa5ae4c3e5e45f7e977112a7e63593820dbec1ec738a24f93c  ==
  MTH2 b137985ff484fb600db93107c77b0365c80d78f5b429ded0fd97361d077999eb  ==
  MTH3 36642e73c2540ab121e3a6bf9545b0a24982cd830eb13d3cd19de3ce6c021ec1  ==
  MTH4 33376a3bd63e9993708a84ddfe6c28ae58b83505dd1fed711bd924ec5a6239f0  ==
  MTH5 fe14a5426fbd70c0fa73f52342afed0da0bd23c4838662ccf6b88a3070ead97b  ==
  MTH6 e069fc12e231ccfd4516bf1617945fb3ccd5cc8910d92d6265289f088f777fdd  ==
  MTH7 4ae191939f548d9934740b88dea2c5cb89bb8870fc4505cd79dec6bbfaaee9cb  ==
  K2..K9 1 2 2 4 4 4 4 8                                                 ==
  leafHash("abc") 609f6e36d2405585188d5cfd761f407c7cc46a7d3f314c88270469dde315fcd1  ==
  nodeHash(l,l)   2affb1ee66535319d17552a1d471be7c6b88b6e0ec4d2764beb6f515ae31de7c  ==
  ```
  and the vector files:
  ```
  $ find . -name rfc6962.json -not -path "*/node_modules/*"
  ./verticals/mainline/apps/console/tests/vectors/rfc6962.json
  $ grep -rn "rfc6962.json" --include=*.py .        # (no output)
  ```
  The Python suite carries its own inline CT vectors
  (`packages/trappoint-ledger/tests/test_merkle_vectors.py:137-178`); no Python test reads
  the console's file and no TypeScript test reads Python's constants.
- **What a user or judge sees:** nothing today — they agree. If they stopped agreeing, the
  console's custody surface would show a red seal on a ledger the server considers sound, or
  a green one on a ledger it does not, and both suites would stay green.
- **What would have caught it:** **NOTHING DOES.** The fix is cheap and is the same fix that
  already worked for JCS (G3): promote one vector file to a shared fixture both suites read.

### F-07 The SigV4 signing-key derivation is correct and is checked by nothing — severity: **LATENT**

- **Divergence:** `db.py:156-158` is the only implementation in the repository; its other end
  is AWS's specification.
- **Command / Output:**
  ```
  db.py _signing_key       : c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9
  AWS published vector     : c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9
  agrees                   : True
  ```
  The repository's own assertions are `test_envelope.py:475-476`, which check only that the
  header starts `AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE/` and contains
  `/ap-southeast-1/ssm/aws4_request`. Neither a signing key nor a signature is ever compared
  to a known value.
- **What a user or judge sees:** if the derivation were wrong, `_ssm_get_parameter` would get
  a `403 SignatureDoesNotMatch`, `DsnUnavailable` would be raised, and the demo would answer
  `503` on every request with no clue as to why. That is a cold-start-only failure on a path
  no local test exercises.
- **What would have caught it:** **NOTHING DOES.** One assertion against the published AWS
  example vector (four lines, no network) converts this from LATENT to HELD.

### F-08 The frame content address is computed twice, in two languages, and the method halves disagree on one input class — severity: **LOW**

- **Divergence:** `scripts/deploy/capture_demo_bundle.py:265-267`
  `method = key.split(" ",1)[0] if " " in key else "REQ"` ·
  `verticals/mainline/apps/console/scripts/capture-bundle.ts:90-95`
  `const space = key.indexOf(' '); const method = space > 0 ? key.slice(0, space) : 'REQ';`
- **Command / Output:**
  ```
  AGREE  'GET /v1/clauses/…/versions/…'   py/ts: frames/GET-0b1685813c825589.json
  AGREE  'GET /v1/receipts/018f3a32-…'    py/ts: frames/GET-1edd53744df4e30f.json
  AGREE  'GET /v1/permits/…/silence'      py/ts: frames/GET-213057f4020fbeb3.json
  AGREE  'GET'                            py/ts: frames/REQ-14e30cd163c73291.json
  *DIFF* ' GET /x'   py: frames/-b544626e58972023.json   ts: frames/REQ-b544626e58972023.json
  ```
  The sha256 half is identical in every case; only the method prefix differs, and only for a
  key beginning with a space, which no declared resource produces.
  Note also that `capture_demo_bundle.py:249` and `console/src/data/resources.ts:369` both
  name the writer as `scripts/capture-bundle.ts`; the file is at
  `verticals/mainline/apps/console/scripts/capture-bundle.ts` (a path fact for W7/W9, not a
  digest divergence).
- **What would have caught it:** `capture-bundle.ts check` re-derives within TypeScript;
  nothing compares the two languages. LOW because the divergent input class is unreachable.

### F-09 The competency digest divergence is INERT — record it so nobody "fixes" it — severity: **LOW**

- **Divergence:** `gate_run.py:624` / `transitions.py:978` bind
  `_sha("competency", "demo.signer")` = `8c7a0b03…` while `demo_world.sql:102` seeds
  `c63cf763…` on `mainline.person`.
- **Command / Output:** both computed side by side (see the Inventory, row B1), and:
  ```
  $ grep -n "NEW\.[a-z_]* :=" verticals/mainline/db/migrations/0102_fn_disposition_project.sql
  221:  NEW.competency_sha256 := v_competency_sha256;
  152:  SELECT pr.rank, pr.org, pr.competency_sha256, … INTO … FROM mainline.person pr …
  ```
- **What a user or judge sees:** nothing. The trigger overwrites the client's value with the
  person's before the row lands, so the digest on any stored disposition is the seed's.
  This answers, for the columns in my slice, the lead's §2.6 question: of the six derived-byte
  columns the demo supplies, **only `competency_sha256` is projected away**;
  `defeater_vocab_sha256`, `evidence_sha256`, `authenticator_data`, `client_data_json` and
  both credential ids survive the write exactly as supplied.

---

## Pairs checked and found to agree, with the mechanism that holds them

| pair | evidence of agreement | held by |
| --- | --- | --- |
| `gate_run` credential ids vs `demo_world.sql` | `verdict PROVEN`, `failures []`, beat 4 admitted on the seeded world | `disposition_signer_credential_id_fkey` + the AST guard `test_credentials.py:453` + `resolve_credential_id` reading the row |
| JCS: `trappoint_jcs` vs `console/src/verify/jcs.ts` | 5/5 byte-identical incl. `1e-5`→`0.00001`, `1e17`→`100000000000000000`, U+1F602 sorting below U+FB33, ` `/U+007F/`/` escaping | vectors captured from Python, committed under `console/tests/vectors/`, read by the TypeScript suite |
| RFC 6962 leaf/node hashing | `leafHash("abc") = 609f6e36…`, `nodeHash(l,l) = 2affb1ee…` in both languages; `gate_run._leaf` agrees with SQL `digest(0x00‖canon)` | 4 literal copies of the same expression — value agreement, no mechanism (see F-06) |
| RFC 6962 `MTH` and `k` | n=0..7 and k=2..9 identical | see F-06 — NOTHING cross-language |
| console software SHA-256 vs WebCrypto/node | 6/6 identical, lengths 0, 3, 55, 56, 64, 1 000 000 | `tests/unit/verify/sha256.test.ts` asserts the two agree on committed vectors |
| `chain_digest` (`0059:55` / `0060:55`) | `digest(prev ‖ payload::STRING::BYTES,'sha256')` reproduced in Python from CockroachDB's own `JSONB::STRING` rendering: `813f220d…` both ways | `fn_permit_event_chain` (0105) re-derives on insert and raises `P0001`; `trg_permit_event_chain` (0125) welds it; nothing outside SQL recomputes it |
| `clearance_digest` (`0117:110-118`) | empty-set case `digest('','sha256')` = `e3b0c442…` = Python `sha256(b"")` | server-computed from base tables; single definition |
| `aaguid` truncation rule | SQL `substring(… FROM 1 FOR 16)` and Python `[:16]` select the same 16 bytes | executed on both ends |
| genesis link (32 zero bytes) | `demo_world.sql:245` `'\x00…'`, `0117:145` `decode(repeat('00',32),'hex')`, `rfc6962.ts:43` `new Uint8Array(32)` | all three literal-equal |
| `clause_version.canon_sha256` vs its own `canon_text` | `9b152601…` == `digest(canon_text)` == Python `sha256(canon_text)` | NOTHING — two hand-typed copies of one 120-char literal in one file (LATENT, row I1) |
| bundle-file `sha256` (Python producer vs TypeScript verifier) | same primitive both sides; the console recomputes and reports mismatch on screen | `features/evidence/audit.ts:150-170` |
| `corpus_root` on the exposure receipt | `transitions.py:773` reads it from `mainline_meas.silence_receipt`; it does not derive one | the read |
| SigV4 signing key vs AWS's spec | `c4afb1cc…` reproduced exactly | NOTHING in this repository (F-07) |

## Not reached (and why)

* **`packages/trappoint-recall/per/canon.py:123 canonicalise_leaf`** and the PER/silence-root
  digests — reachable only through the recall pipeline, which the demo does not run; the seed
  supplies `corpus_root`/`candidate_root` as literals and nothing recomputes them. Left to W10
  (`spec/custody` vs `packages/trappoint-*`).
* **`packages/trappoint-ledger/note/keyid.py` and `checkpoint.ts` signature key ids** — a
  signing-identity recipe, not a demo-path one; the seed's `log_sig` and `cosig` are opaque
  literals (`demo_world.sql:411,424`) that nothing verifies. Flagged for W10.
* **`packages/mainline-boundary/sbom.py` and `mainline-agentkit/_canon.py`** — cassette and
  SBOM digests, off the demo path entirely.
* **`evidence/reference-ledger/generate.py:715,1329`** — uses `hash_leaf` from the authority
  and re-checks its own output at `:1329`, i.e. self-consistent by construction; no second
  definition to diverge from.
* **Whether the *live* Cloud Lambda's `canonicalisation` field says what F-03 predicts** —
  that needs a request to the deployed Function URL, which is W7's surface. I proved the
  package composition from `build_lambda.sh` and the branch behaviour by blocking the import;
  the last mile is one `curl` W7 is already making.
* **`0102_fn_disposition_project.sql`'s treatment of columns outside my slice** (rank, org,
  virulence, closure_gen, the requirement flags) — W1/W5/W6.

## Reproduction

```bash
cd /d/CoackroachDBxAWS/mainline
# NOTE: use 127.0.0.1, not localhost — `localhost` resolution on this box costs >120 s per connect.
.venv/Scripts/python.exe -c "import psycopg;c=psycopg.connect('postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable',autocommit=True);c.execute('CREATE DATABASE IF NOT EXISTS d_w2_chain')"
.venv/Scripts/python.exe scripts/chain/apply_chain.py --dsn "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable" --database d_w2_chain --keep --attest final --no-evidence
# 271/271, 118 s. Then apply the two seed files verbatim (seed_demo.py --dsn did not honour
# the flag on this box and looked for mainline.permit in another database):
.venv/Scripts/python.exe -c "
import pathlib, psycopg
c=psycopg.connect('postgresql://root@127.0.0.1:26257/d_w2_chain?sslmode=disable',autocommit=True)
for f in ('demo_world.sql','demo_permit.sql'):
    c.execute((pathlib.Path('verticals/mainline/db/seeds/demo')/f).read_text(encoding='utf-8'))"
```
