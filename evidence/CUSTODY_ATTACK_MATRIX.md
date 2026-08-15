<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0

GENERATED FILE — do not edit.
Produced by tests/integration/custody/nemesis/matrix.py from a nemesis run against a
real, disposable CockroachDB. Regenerate with:
  python -m pytest tests/integration/custody/nemesis
-->

# ATTACK-DEPTH — the custody attack matrix

**Generated from a run, not written by hand.** Each row below is what happened when the attack was executed as real SQL against a disposable single-node CockroachDB seeded with the reference log, and a bundle exported from the mutated database was then put through the check set.

- attacks executed: **14** of 15
- reported `SKIP`: **1** — A15
- detected by zero checks: **0**
- detected by exactly one check (flagged, not failed): **4**
- verifier that produced these rows: trappoint-verify 0.1.0; checks 4, 5, 6, 7, 8, 11, 12 answered by the nemesis-local fallback because no runner has landed for them

| Environment | |
|---|---|
| cluster | $MAINLINE_TEST_DSN |
| cryptography | available |
| generated_at | 2026-08-15T16:29:01Z |
| schema | reduced nemesis fixture (see nemesis_harness.py) |
| verifier | trappoint-verify 0.1.0; checks 4, 5, 6, 7, 8, 11, 12 answered by the nemesis-local fallback because no runner has landed for them |

## The matrix

| Attack | Tier | Detected by (observed) | Latency | Expected (registry) | Agrees |
|---|---|---|---|---|---|
| **A1** `delete_and_relink` | T1 | check 3 *(primary)* · check 2 · check 16 | 151 ms | check 3, check 2, check 16 | yes |
| **A2** `renumber_only` | T1 | check 9 *(primary)* · check 2 · check 3 · check 16 | 153 ms | check 9, check 3, check 16 | yes (+extra) |
| **A3** `payload_substitute` | T1 | check 1 *(primary)* | 162 ms | check 1, check 16 | yes |
| **A4** `canon_substitute` | T1 | check 2 *(primary)* · check 3 · check 15 | 196 ms | check 2, check 3, check 16 | yes (+extra) |
| **A5** `canon_version_downgrade` | T1 | check 1 · check 16 | 200 ms | check 10, check 1, check 2 | yes (+extra) |
| **A6** `fork` | T1 | check 2 · check 9 · check 16 | 166 ms | check 3, check 9 | yes (+extra) |
| **A7** `checkpoint_swap` | T4 | check 5 *(primary)* · check 3 | 178 ms | check 3, check 5, check 7, check 8 | yes |
| **A8** `backdate_forward` | T4 | check 5 *(primary)* · check 3 · check 6 · check 16 | 163 ms | check 5 | yes (+extra) |
| **A9** `backdate_backward` | T4 | check 6 *(primary)* · check 5 | 159 ms | check 6 | yes (+extra) |
| **A10** `closure_mass_rewrite` | T1 | check 14 *(primary)* · check 11 | 162 ms | check 14, check 16 | yes (+extra) |
| **A11** `prev_digest_forgery` | T1 | check 11 *(primary)* | 159 ms | check 11 | yes |
| **A12** `sandbox_smuggle` | T0 | check 13 *(primary)* · check 2 · check 16 | 161 ms | check 13, check 16 | yes (+extra) |
| **A13** `trigger_disable` | T1 | check 11 *(primary)* | 165 ms | check 11, check 14 | yes |
| **A14** `receipt_orphan` | T1 | check 15 *(primary)* | 160 ms | check 15 | yes |
| **A15** `object_lock_downgrade` | T2 | — SKIP(no-credentials) | not run | check 8 | n/a |

Latency is measured from the moment the attack commits to the moment the first finding exists — the question a reader is actually asking is *how long after the attack would somebody know?* For attacks whose primary defence is a database refusal the honest answer is *before it happened*, and those refusals are listed below rather than folded into a millisecond count.

## Single-detector attacks — flagged, not failed

A single detector is a single point of failure in the argument, not in the code. These are listed so that the next detector is a known piece of work rather than a discovery.

- A3 (payload_substitute) is detected by exactly one check (check 1)
- A11 (prev_digest_forgery) is detected by exactly one check (check 11)
- A13 (trigger_disable) is detected by exactly one check (check 11)
- A14 (receipt_orphan) is detected by exactly one check (check 15)

## What each attack did, and what the database said

### A1 · `delete_and_relink` (T1)

> Delete leaf k, renumber k+1..n, and recompute every link_hash in one UPDATE ... FROM generate_series. The table is left perfectly self-consistent.

the ledger table is left perfectly self-consistent: dense seq, every link_hash recomputes. Nothing inside the database can see it.

Findings (first six):

- check 2: 72 of 72 leaves unproven [inclusion-proof-failed]
- check 3: 3 of 7 consecutive pairs unproven [consistency-proof-failed]
- check 16: 7 totality finding(s) — read no other verdict as complete [bundle-not-total]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A2 · `renumber_only` (T1)

> Shift seq values without re-linking, e.g. to close a gap left by a delete.

seq is dense again and every prev_link_hash now points at the wrong predecessor. No re-linking was attempted, which is what separates this from A1.

Findings (first six):

- check 2: 72 of 72 leaves unproven [inclusion-proof-failed]
- check 3: 4 of 7 consecutive pairs unproven [consistency-proof-failed]
- check 9: 1 chain finding(s) [link-chain-broken]
- check 16: 7 totality finding(s) — read no other verdict as complete [bundle-not-total]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A3 · `payload_substitute` (T1)

> Swap ledger_intake.payload while leaving canon_bytes and leaf_hash untouched.

the console would show 'advisory' where the tree commits to 'disposition': the exhibit and the proof would describe different documents.

Findings (first six):

- check 1: 1 leaf finding(s) [payload-disagrees-with-canon-bytes]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A4 · `canon_substitute` (T1)

> Swap canon_bytes and recompute leaf_hash together, so check 1 passes.

check 1 passes: the bytes and the hash agree. They agree about a lie.

Findings (first six):

- check 2: 73 of 73 leaves unproven [inclusion-proof-failed]
- check 3: 5 of 7 consecutive pairs unproven [consistency-proof-failed]
- check 15: 1 of 16 receipts are not covered [receipt-orphaned]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A5 · `canon_version_downgrade` (T1)

> Re-canonicalise an old leaf under a different payload_ver to change its bytes legitimately-looking.

the leaf now claims a canonicaliser the signed checkpoint does not name; canon_src_sha256 is inside the signature, so the downgrade cannot be hidden.

Findings (first six):

- check 1: payload_ver [2] is not a canonicaliser this verifier holds [unknown-payload-ver]
- check 16: 1 totality finding(s) — read no other verdict as complete [unknown-payload-ver]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A6 · `fork` (T1)

> Two ledger_leaf rows claiming the same head, producing two divergent histories.

two leaves now name the same predecessor a2ac416106215cc0…, which is two histories with one past. Refusal depth 2 held until BOTH constraints were dropped; at verify time the fork is a single-detector finding, because the forked leaf sits beyond the newest checkpoint and no proof covers it yet — which is exactly the ~60 s window this design states rather than denies.

Database refusals observed on the way:

- `both constraints armed, colliding seq -> 23505: duplicate key value violates unique constraint "ledger_leaf_pkey"`
- `ledger_linear dropped, ledger_leaf_pkey alone -> 23505: duplicate key value violates unique constraint "ledger_leaf_pkey"`
- `ledger_linear alone, fresh seq -> 23505: duplicate key value violates unique constraint "ledger_linear"`

Findings (first six):

- check 2: 1 of 74 leaves unproven [inclusion-proof-missing]
- check 9: 1 chain finding(s) [link-chain-broken]
- check 16: 1 totality finding(s) — read no other verdict as complete [bundle-not-total]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A7 · `checkpoint_swap` (T4)

> Replace a checkpoint body with a different, internally self-consistent one over a different tree, signed with the same key.

internally self-consistent and signed by the right key — re-signed with the committed fixture log key (T4: the signer is complicit). The RFC 3161 token is over the note that WAS there, and cannot be re-minted with yesterday's date.

Findings (first six):

- check 3: 2 of 7 consecutive pairs unproven [consistency-proof-failed]
- check 5: size 50: the RFC 3161 messageImprint is not SHA-256(note text) — the note travelling with this token is not the note that was timestamped

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A8 · `backdate_forward` (T4)

> Mint history and claim it existed earlier than the timestamp authority saw it.

a 97-leaf tree carrying the timestamp of the log's first checkpoint, re-signed with the committed fixture log key (T4: the signer is complicit). The authority is not ours and will not re-date anything.

Findings (first six):

- check 3: 1 of 8 consecutive pairs unproven [consistency-proof-missing]
- check 5: size 97: the RFC 3161 messageImprint is not SHA-256(note text) — the note travelling with this token is not the note that was timestamped
- check 5: size 97 is timestamped 20260807020232Z, earlier than the smaller tree at size 73 (20260807020832Z): history was minted and dated backwards
- check 6: size 97: the checkpoint quotes drand round 31088382, issued at 1786068510, which is AFTER the RFC 3161 genTime 1786068152 — it quotes a round that did not yet exist
- check 16: 1 totality finding(s) — read no other verdict as complete [bundle-not-total]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A9 · `backdate_backward` (T4)

> Claim a checkpoint existed BEFORE the beacon round it quotes.

the quoted round is issued ~7 days after the note was timestamped, and the note was re-signed with the committed fixture log key (T4: the signer is complicit).

Findings (first six):

- check 5: size 34: the RFC 3161 messageImprint is not SHA-256(note text) — the note travelling with this token is not the note that was timestamped
- check 6: size 34: the checkpoint quotes drand round 31288322, issued at 1786668330, which is AFTER the RFC 3161 genTime 1786068332 — it quotes a round that did not yet exist

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A10 · `closure_mass_rewrite` (T1)

> UPDATE mainline.clause_blame_closure SET max_severity = 0 WHERE site_id = $1, from the closure projector's Lambda execution role.

the append-only trigger refuses the UPDATE; DISABLE TRIGGER succeeds and then it lands. Every coverage view still reports full coverage.

Database refusals observed on the way:

- `P0001: MAINLINE: this table is append-only; write a new row`

Findings (first six):

- check 11: mainline.clause_blame_closure.append_only: the mechanism attested at migration 0128j_trg_refuse_mutation_clause_blame_closure is not present and enabled in the live catalogue. The exhibit can no longer show the source of the mechanism that refused
- check 14: 8 closure finding(s) over 8 (clause, commit) pairs [closure-severity-decreased]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A11 · `prev_digest_forgery` (T1)

> Insert a permit_event carrying a fabricated prev_digest, forging the state-machine chain.

the primary defence is a P0001 refusal, not a verifier finding. Check 11 is what catches the case where the trigger was removed first.

Database refusals observed on the way:

- `P0001: MAINLINE: prev_digest does not match the predecessor chain digest`

Findings (first six):

- check 11: mainline.permit_event.permit_event_chain: the mechanism attested at migration 0125_trg_permit_event_chain is not present and enabled in the live catalogue. The exhibit can no longer show the source of the mechanism that refused

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A12 · `sandbox_smuggle` (T0)

> Land an is_sandbox = true leaf inside an evidentiary tree, from the guest demo surface.

a demo write is now inside the tree an inspector would be handed.

Findings (first six):

- check 2: 1 of 74 leaves unproven [inclusion-proof-missing]
- check 13: 1 leaf of 74 leaves carry is_sandbox = true [sandbox-leaf-present]
- check 16: 1 totality finding(s) — read no other verdict as complete [bundle-not-total]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A13 · `trigger_disable` (T1)

> ALTER TABLE ... DISABLE TRIGGER on the merge gate, then merge a permit with open blocking checks.

the gate refused; DISABLE TRIGGER succeeded; the permit is now 'merged' with an undischarged obligation. The trigger is still in pg_trigger but disabled, which is exactly the state check 11 has to notice.

Database refusals observed on the way:

- `P0001: MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero`

Findings (first six):

- check 11: mainline.permit_merge_gate: the mechanism attested at migration 0130_trg_permit_merge_gate is not present and enabled in the live catalogue. The exhibit can no longer show the source of the mechanism that refused

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A14 · `receipt_orphan` (T1)

> Issue a Signed Disposition Receipt and never sequence its leaf.

intake accepted it, the sequencer never did, and the holder can prove it.

Findings (first six):

- check 15: 1 of 17 receipts are not covered [receipt-orphaned]

Checks that reported SKIP during this run, printed as loudly as a failure:

- check 4 `log_signature`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 5 `rfc3161_upper_bound`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 6 `beacon_lower_bound`: `SKIP(optional-extra: the drand BLS12-381 G1 signature and the NIST pulse signature are not verified — `cryptography` has no BLS, and the pulse itself is an online fetch. Only the round->time arithmetic ran [nemesis-local fallback; trappoint-verify has no runner for check 6 yet])`
- check 7 `witness_quorum`: `SKIP(not-adverse: quorum is q=1 over infrastructure we operate. `adverse` is a claim about legal interest, not a cryptographic property, and split-view resistance is NOT claimed [nemesis-local fallback; trappoint-verify has no runner for check 7 yet])`
- check 8 `archive_object_lock`: `SKIP(offline: --s3 not given; archive metadata is a claim by us [nemesis-local fallback; trappoint-verify has no runner for check 8 yet])`
- check 11 `gate_self_attestation`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`
- check 12 `webauthn_reverification`: `SKIP(not-implemented in trappoint-verify, and the nemesis-local fallback found nothing to report)`

### A15 · `object_lock_downgrade` (T2)

> Call PutObjectRetention to shorten a COMPLIANCE retention, or DeleteObjectVersion on a checkpoint object.

**SKIP(no-credentials)** — this attack was not executed by this run, and is recorded here rather than omitted.

The static defence is proven instead by policy-as-code over the OpenTofu plan JSON (`infra/policy/custody/object_lock.rego`, `scripts/custody/check_evidence_plan.py`): the bucket must declare `object_lock_enabled` AT CREATION and versioning, and no principal in the write account may hold `s3:DeleteObject*`, `s3:PutObjectRetention`, `s3:PutObjectLegalHold` or `s3:BypassGovernanceRetention`. GT-18 is a one-shot: Object Lock cannot be retrofitted, so it must be right the first time.

## What is not defeated

- **T3** — a managed-service operator with storage-path access is outside every mechanism in the database. Only Object Lock in a separate account and external witnesses touch that adversary, and neither is a complete answer.
- **T4** — a cloud-org admin colluding with the signer can mint valid-looking history *going forward*. What they cannot do is change history a timestamp authority already timestamped or a witness already cosigned. The window of undetectable mutation is ~60 seconds and that is the honest number.
- **Insincerity** — nothing here detects a rubber-stamped disposition. The chain makes rubber-stamping *measurable*; it does not make it impossible.

Cross-referenced to [`spec/custody/attacks.yaml`](../spec/custody/attacks.yaml) and [`spec/custody/checks.yaml`](../spec/custody/checks.yaml).

