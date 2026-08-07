# CUSTODY LEAD — evidence that survives a hostile expert witness

**Domain implementation plan.** Milestone K2 (THE CHAIN) in full, plus the K2-shaped slices of K6
(the evidence stack in OpenTofu) and K9 (anchoring, witnesses) that must be *designed and welded*
now because they cannot be retrofitted later. Authority: `ARCHITECTURE.md` §5.6, §5.11, §7, §11.4,
§11.6, §16 (MI01, MI24), §18, §19 (GT-05, GT-17, GT-18); `BUILD_PLAN.md` §3 (K2), §6 (K9);
`research/05-architecture/custody-tamper-evidence.md`; `research/08-synthesis/review-adversarial.md`
(S9). Nothing here re-litigates a decision those documents made. Where they leave a genuine choice,
or contain a shape that does not compile, §2 rules on it in one line.

---

## 0. What this domain must be true of, in one paragraph

> **A hash chain inside a table the adversary owns is a checksum, not evidence.**

Everything I build exists to move a commitment to the log head **outside the reach of the future
defendant** — which is us — fast enough that the window of undetectable mutation is ~60 seconds, and
to put a **verifier in a stranger's hands** that needs no credential, no network and no cooperation
from us. The deliverable is not the ledger. The deliverable is the sentence *"checks 1–3, 7, 9, 10,
12, 13, 14, 15 and 16 require no access to our database"* being **true when a hostile expert tests
it**, and `evidence/reference-ledger/bundle.json` being the thing they test it on. Four
propositions must survive cross-examination: **existence at a bracketed time T**, **non-alteration**,
**non-omission** (the one plaintiffs actually attack), and **provenance of process**. The fourth is
the one most designs lose, in Australia, on s.69(3) — see §3.

---

## 1. Strategy

### 1.1 The threat model is the design input, and it is tiered in code

`spec/custody/threat-model.md` is normative and machine-readable (`spec/custody/attacks.yaml`).
T0 app user · **T1 rogue DBA** (arbitrary SQL, can recompute every hash in the table) · T2 cloud-org
admin (delete S3 objects, disable CloudTrail, schedule KMS deletion) · T3 managed-service operator
(Cockroach Labs / AWS storage path) · T4 T2 colluding with the signer.

The entire literature failure mode is designing for T0 and claiming T1. Every artefact I ship
declares the highest tier it defeats, and `evidence/CUSTODY_ATTACK_MATRIX.md` (§1.5) is the machine
proof of that declaration. **T3 is not defeated and is stated to the customer**, because saying it
first is the only version of that sentence that helps us.

### 1.2 Red before green: the K2 exit criteria are a committed failing test

`PL-2` is satisfied mechanically. Worker 1 lands `tests/integration/custody/test_k2_exit.py`
containing exactly the six K2 exit criteria as executable assertions — tamper-caught-by-consistency-
proof, closure-rewrite-caught-by-check-14, bundle-verifies-on-a-machine-that-never-touched-the-
cluster, checkpoint cadence measured, `spec/wire/checkpoint.md` tagged `v1.0`, migration attestation
chained with a fingerprint stable across two computations — **before a single line of ledger code
exists**. The job is red; its run URL is the proof artefact and goes into
`docs/adr/0040-custody-red-before-green.md`. No other worker may edit that file. They make it green
by building artefacts, never by editing assertions.

The same discipline binds the verifier: a check may report `PASS`, `FAIL`, or `SKIP(reason)`, and
**`SKIP` is printed as loudly as `FAIL`**. `spec/custody/checks.yaml` carries a `status` field per
check ∈ `{implemented, skipped_with_reason, deferred}`; a CI totality test fails if any check is
`implemented` without a module and a test, or if any check silently changed status without an ADR
reference in the commit body. A verifier that quietly passes because it did not look is the single
worst artefact this domain could ship.

### 1.3 The interface is frozen before the first real leaf

`spec/wire/checkpoint.md` v1.0 is frozen in Worker 1, before any leaf is written, because the wire
format is what an **opposing expert writing their own verifier in Rust** implements, and changing it
after a million rows is a migration of *evidence*, not of data. Same for
`spec/wire/evidence-bundle.md` (the single self-describing JSON file a stranger can be emailed) and
`spec/wire/receipt.md` (the Signed Disposition Receipt). Every one ships with test vectors in the
spec directory and a decoder test that reads the vectors out of the markdown fence, so the document
and the code cannot drift.

### 1.4 Proof order — what is proven before what

```
W1 spec + threat model + RED
      │
      ├──► W2 JCS canon (+ vendoring guard)          ─┐
      ├──► W3 RFC 6962 merkle / proofs / link chain  ─┤
      │                                                ├──► W4 note · signer · SDR
      │                                                │        │
      │                                                │        ├──► W5 sequencer (CAS, anti-join)
      │                                                │        ├──► W8 anchor fanout + evidence IaC
      │                                                │        └──► W9 witness + custodian patrol
      │                                                │
      └────────────────────────────────────────────────┴──► W6 trappoint-verify core (structural)
                                                                 │
                                                                 └──► W7 verify crypto / anchor checks
                                                                          │
   W10 reference ledger · nemesis attack matrix · CI  ◄──────────────────┘
```

Strictly: **canonical bytes before hashes** (a hash of bytes nobody can reproduce is not evidence) →
**tree before signature** (signing a root you cannot prove inclusion into is theatre) → **signature
before anchor** (anchoring an unsigned root anchors nothing) → **verifier before ledger content**
(the verifier is the specification's executable form; content written before it is content written
against nothing) → **attack matrix last** (an attack harness is only meaningful against a complete
defence).

### 1.5 ATTACK-DEPTH — the custody analogue of the kernel's refusal depth

This is my domain's flagship artefact and it is ours, not borrowed. The kernel proves *refusal
depth ≥ 2* by unwelding one mechanism at a time. I prove **detection depth** the same way:
`tests/integration/custody/nemesis/` executes each T1/T2 attack as a real script against a real
cluster and a real bundle —

| attack | shape |
|---|---|
| `A1 delete_and_relink` | delete leaf *k*, renumber `k+1..n`, recompute every `link_hash` in one `UPDATE … FROM generate_series` |
| `A2 renumber_only` | shift `seq` without re-linking |
| `A3 payload_substitute` | swap `payload` leaving `canon_bytes` |
| `A4 canon_substitute` | swap `canon_bytes` and `leaf_hash` together |
| `A5 canon_version_downgrade` | re-canonicalise an old leaf under a newer `payload_ver` |
| `A6 fork` | two `ledger_leaf` rows claiming the same head |
| `A7 checkpoint_swap` | replace a checkpoint body with a self-consistent one over a different tree |
| `A8 backdate_forward` / `A9 backdate_backward` | mint history outside the TSA/beacon bracket |
| `A10 closure_mass_rewrite` | S2 — rewrite `clause_blame_closure` generations downward |
| `A11 prev_digest_forgery` | S9 — insert a `permit_event` with a fabricated `prev_digest` |
| `A12 sandbox_smuggle` | land an `is_sandbox = true` leaf inside an evidentiary tree |
| `A13 trigger_disable` | `ALTER TABLE … DISABLE TRIGGER` on the gate, then merge |
| `A14 receipt_orphan` | issue an SDR and never sequence its leaf |
| `A15 object_lock_downgrade` | attempt `PutObjectRetention` to shorten COMPLIANCE retention |

— and emits `evidence/CUSTODY_ATTACK_MATRIX.md`: **attack × detecting check × detection latency**.
CI fails if any attack is detected by **zero** checks, and flags (does not fail) any detected by
exactly one. `A15` runs only when live credentials exist and is reported `SKIP(no-credentials)`
otherwise — never silently absent. This converts "tamper-evident" from an adjective into a matrix a
regulator can read in ten minutes, and it is the artefact I would put on screen in the demo.

### 1.4a Vendoring is a CI equality, not a promise

`trappoint-verify`'s one-dependency claim dies the moment the vendored canonicaliser drifts from the
one the sequencer used. `scripts/custody/check_vendored_canon.py` asserts
`sha256(packages/trappoint-verify/src/trappoint_verify/vendor/canon_v1.py) ==
 sha256(packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py)` byte-for-byte, and
`spec/custody/canon-registry.yaml` pins the sha256 of **every canonicaliser ever shipped**. A PR that
modifies or deletes a shipped `canon_v*` fails CI with the message *"removing a canonicaliser is a
breaking change to evidence"*. Retention is forever; the registry is the enforcement.

---

## 2. Decisions (one line of justification each)

Twelve rulings. Seven are choices the documents left open; five correct residual drift that would
otherwise ship as a defect.

**CU-1 · `ledger_leaf` gains `prev_link_hash BYTES NOT NULL` and `CONSTRAINT ledger_linear UNIQUE
(site_code, prev_link_hash)`**, genesis being 32 zero bytes. — *the architecture's own
`UNIQUE (permit_id, prev_seq)` CAS idiom transplanted to the ledger; it gives the append **refusal
depth 2** (PK + linearity) so the ledger is held to the same standard as the gate, and it makes a
fork impossible even under a hypothetical PK bypass.* Normative addendum in
`spec/custody/ledger-schema.md`; the datamodel lead applies it to migration `0073`.

**CU-2 · `seq` is derived in-transaction as `COALESCE(max(seq),-1)+1` and the resulting `23505` is
the ONLY retryable `23505` in the repository.** The sequencer's CAS loop matches on **constraint
name** (`ledger_leaf_pkey`, `ledger_linear`), never on SQLSTATE, is bounded at 8 attempts, and is
asserted by a test that a `23505` on any other constraint escapes. — *`CREATE SEQUENCE` is banned
because sequence updates survive rollback, so a gap must MEAN tampering; that claim is only worth
anything if the derivation is a genuine compare-and-swap and if the one legitimate retry cannot
launder a real refusal.*

**CU-3 · The log signature is AWS KMS `ECC_NIST_P256` / `ECDSA_SHA_256`, encoded as a C2SP
signed-note signature of type `0x02`, with the signature bytes being the DER encoding exactly as
returned by KMS `Sign`.** — *C2SP registers `0x02` for ECDSA P-256, so we are standards-compliant
without a private-use byte; Ed25519 (type `0x01`) is what the public witness network prefers but KMS
cannot produce it, and a software Ed25519 key living in a Lambda's memory destroys the entire
rogue-DBA argument.* The note format ignores unknown signature lines, so adding an Ed25519 line later
is purely additive. `spec/wire/checkpoint.md` states the DER-vs-`r‖s` choice **normatively with a
test vector**, because C2SP leaves it unspecified for `0x02` and an opposing expert's verifier must
not have to guess.

**CU-4 · Two beacons, not one, and only one of them is load-bearing offline.** The checkpoint body
carries both a drand `quicknet` round (`bls-unchained-g1-rfc9380`, 3 s cadence, chain hash
`52db9ba7…e971`) and a NIST Randomness Beacon 2.0 pulse. — *drand's BLS12-381 G1 signature cannot be
verified by `cryptography`, so verifying it would break the one-dependency floor; the NIST pulse is
RSA-PKCS#1v1.5 / SHA-512 with an X.509 certificate and **is** verifiable under the floor.* The core
verifier fully verifies the NIST pulse (check 6a) and verifies drand's round→time mapping
arithmetically while reporting the BLS signature as `SKIP(optional-extra)` unless
`trappoint-verify[beacon]` is installed (check 6b). Two independent lower bounds; neither one
silently assumed.

**CU-5 · The ledger payload profile bans IEEE-754 floats.** `canon_v1` implements RFC 8785 **in
full**, including the ES6 number serialisation, and is tested against the cyberphone test vectors —
but `canon_v1.canonicalise_payload()` raises `NonEvidentiaryNumber` on any `float`. — *no evidentiary
quantity is a binary float, and the ES6 `toString` path (exponent thresholds at −7/21 vs Python's
−5/16) is the single largest interoperability risk in a scheme whose whole value is that a stranger
reproduces our bytes; we keep conformance and remove the dependency on it.*

**CU-6 · The reference ledger is signed by a committed, deliberately public P-256 key.**
`evidence/reference-ledger/keys/reference-log.NOT-SECRET.key.pem`, with a README sentence in the
bundle directory: *"this key is public by design — the reference bundle proves the verifier works,
not that MAINLINE's production log is honest."* — *a reference fixture a stranger cannot regenerate
is a screenshot; and implying production custody from a fixture is exactly the overclaim this domain
exists to refuse.* `just evidence-regen` is byte-deterministic (fixed clock, `uuid5` identity, fixed
key) and CI asserts zero diff, mirroring `trappoint render`.

**CU-7 · `trappoint-verify` makes no network call on any default path**, asserted by a test that
patches `socket.socket` to raise and runs the full suite. Online checks (`--s3`, `--kms-pubkey`,
`--tile-url`) are opt-in flags whose absence downgrades the relevant check to `SKIP(offline)`.
— *"requires no cooperation from us" must be a 200 ms test, not a promise.*

**CU-8 · RFC 3161 verification is hand-rolled over a ~250-line minimal DER reader inside
`trappoint-verify`, not delegated to a library.** — *`cryptography` has no CMS `SignedData`
verification API (only PKCS#7 certificate extraction and, since 44, decryption), and adding
`asn1crypto`/`rfc3161ng` breaks the dependency floor, which is worth more than the code we would
save.* Tested against (a) a locally-minted TSA chain generated in-repo and (b) real tokens from
FreeTSA and the Sigstore TSA committed as fixtures by `scripts/custody/fetch_tsa_fixtures.py`. The
interop lane is marked **unverified** in `spec/custody/checks.yaml` until it runs green in CI.

**CU-9 · I specify and falsify `fn_permit_event_chain`; the datamodel lead implements it.**
`spec/custody/chain-verification.md` carries the normative PL/pgSQL body (S9: `prev_digest` verified
against the predecessor's `chain_digest`, `RAISE` on mismatch or missing predecessor except
`seq = 0`), and `scripts/custody/check_chain_fn_matches_spec.py` diffs the live
`pg_get_functiondef()` against it in CI. — *migrations have exactly one owner
(`verticals/mainline/db/migrations/**` is the datamodel lead's); a second writer would break the
lock-file discipline, and a spec with an executable conformance check is stronger than a duplicated
file anyway.*

**CU-10 · Object Lock semantics are proven by policy-as-code over the OpenTofu plan JSON, never by
`moto`.** `infra/policy/custody/*.rego` + `scripts/custody/check_evidence_plan.py` fail the merge if
the bucket lacks `object_lock_enabled` **at creation** or versioning, if any principal in the write
account holds `s3:DeleteObject*`, `s3:PutObjectRetention`, `s3:PutObjectLegalHold` or
`s3:BypassGovernanceRetention`, or if `kms:ScheduleKeyDeletion`/`kms:DisableKey` is grantable outside
the two-person break-glass role. — *moto's Object Lock enforcement is incomplete, and a green test
against a mock that does not enforce the thing is worse than no test; the plan-JSON assertion tests
the actual control (`GT-18`: it cannot be retrofitted, so it must be right the first time).* The live
smoke check exists behind `--live` and reports `SKIP(no-credentials)` today.

**CU-11 · The evidence stack is a separate OpenTofu root module with no `destroy` path.**
`infra/envs/evidence/` provisions the Object Lock bucket, the KMS signing key and CloudTrail **in a
second AWS account**, and its `justfile` target refuses `destroy` outright. — *`just destroy` must be
honest about which stacks are indelible, and a rebuilt KMS key makes yesterday's ledger unverifiable
— the same offence as destruction, committed by accident (`BUILD_PLAN` K6 "fails how").*

**CU-12 · The verifier's exhibit vocabulary leads with the gate, never with litigation.** The CLI
banner, the bundle README and every generated report say *"this bundle records the preconditions the
database enforced before work was permitted to start"* — a CI grep fails the strings
`defence exhibit`, `for litigation`, `court-ready` anywhere in my paths. — *Evidence Act 1995 (Cth)
s.69(3) and s.147(3) exclude representations prepared in contemplation of a proceeding; a ledger
**built to be evidence is not a business record**, so operational load-bearing-ness is an
architectural requirement and marketing copy is an admissibility risk.*

---

## 3. Evidentiary mapping — the column the code is written against

`spec/custody/evidentiary-map.md` is a table, not an essay, and CI asserts every row names a live
artefact and a test.

| Standard | Requirement | Artefact | Test |
|---|---|---|---|
| Evidence Act 1995 (Cth) **s.69** | business record made in the ordinary course of business | the merge is *refused* without a covered disposition leaf — the ledger is what lets work start | `test_k2_exit::test_gate_depends_on_ledger` |
| **s.69(3) / s.147(3)** | NOT prepared in contemplation of a proceeding | CU-12 vocabulary grep; the gate is load-bearing by construction | `test_no_litigation_vocabulary` |
| **s.146 / s.147** | device/process presumption | deterministic, versioned, third-party-runnable verifier; `canon_src_sha256` in every checkpoint | `test_verifier_determinism` |
| **ISO/IEC 27037** acquisition | client-side canonicalisation + SDR at intake | `trappoint_ledger.receipt` | `test_receipt_roundtrip` |
| **ISO/IEC 27037** preservation | COMPLIANCE-locked, versioned, separate account | `infra/envs/evidence` + policy-as-code | `check_evidence_plan.py` |
| **ISO/IEC 27037** chain of custody | `actor`, `actor_kind`, signing credential on every leaf | bundle schema required fields | `test_bundle_schema` |
| **ISO/IEC 27042** reproducibility | offline, deterministic, versioned verifier + committed reference bundle | `evidence/reference-ledger/` | `test_reference_bundle_verifies` |
| Crimes (Document Destruction) Act 2006 (Vic) | no silent deletion | TTL allowlist excludes every `ledger_*`; `destruction_record` required | `test_no_ttl_on_ledger` |

**Prior art cited as accepted practice, deliberately:** SQL Server 2022 / Azure SQL Ledger does this
shape (SHA-256 transaction hashing plus periodic digests to immutable storage). We are a superset —
Merkle proofs, TSA bracket, beacons, external witnesses, an offline verifier. **Dead end, never
proposed:** Amazon QLDB (end of support 31 July 2025; AWS's own migration path loses cryptographic
verifiability). There is no AWS-native verifiable ledger service — a market gap, not a design gap.

---

## 4. Interfaces this domain publishes

| Interface | Consumer | Owner |
|---|---|---|
| `spec/wire/checkpoint.md` v1.0 (C2SP note profile, type `0x02`, extension lines, test vectors) | witnesses, the verifier, any third-party implementer | W1 |
| `spec/wire/evidence-bundle.md` v1.0 — the single self-describing JSON exhibit | verifier, console exhibit renderer, opposing experts | W1 |
| `spec/wire/receipt.md` — the Signed Disposition Receipt (SCT analogue, MMD = 60 s) | gate service, intake API, `verify receipt-audit` | W1 |
| `spec/custody/checks.yaml` — check id ⇄ proves ⇄ defeats ⇄ module ⇄ test ⇄ status | verifier CLI, CI totality test, README | W1 |
| `spec/custody/attacks.yaml` + `evidence/CUSTODY_ATTACK_MATRIX.md` | nemesis harness, the demo, the regulator read | W1 / W10 |
| `spec/custody/ledger-schema.md` (CU-1 addendum), `chain-verification.md` (CU-9 normative body) | datamodel lead (migrations `0059`, `0072–0079`, `0100+`) | W1 |
| `spec/custody/canon-registry.yaml` — sha256 of every canonicaliser ever shipped | vendoring guard, verifier dispatch on `payload_ver` | W2 |
| `trappoint_jcs.canon_v1` | sequencer, intake client, verifier (vendored copy) | W2 |
| `trappoint_ledger.merkle` — MTH, inclusion, consistency, tile addressing | sequencer, verifier, witness | W3 |
| `trappoint_ledger.note` / `.signer.Signer` (Protocol) / `.receipt` | sequencer, anchor, witness, verifier | W4 |
| `trappoint_migrate.attest.LedgerSink` **implementation** (`emit(kind, subject_id, payload)`) | datamodel lead's runner — I supply the real sink against their Protocol | W5 |
| `trappoint-verify` CLI (`verify`, `receipt-audit`, `explain-check`) | Tier-1 verification, the README, the demo | W6 / W7 |
| `trappoint-witness` — C2SP `tlog-witness` service + Dockerfile | insurer / HSR / regulator / external auditor | W9 |
| `infra/modules/evidence-store` + `infra/policy/custody/*.rego` | cloud lead's root modules (consumed, never edited) | W8 |

**Consumed, never owned:** `verticals/mainline/db/migrations/**` and `packages/trappoint-migrate`
(datamodel lead) · `.importlinter`, `spec/TRAPPOINT-SPEC.md`, `spec/errors.md`, `spec/wire/refusal.md`
(kernel lead) · the `cc()` `ccloud` wrapper and `infra/envs/{demo,prod}` (cloud lead). Where I need a
capability they own, I consume it through a `typing.Protocol` with an in-process fake, so my tests
never block on their landing.

---

## 5. Worker roster

| # | id | One-line purpose |
|---|---|---|
| 1 | `custody-spec-and-red` | The frozen wire formats, the tiered threat model, the machine-readable check and attack registries, the evidentiary map — and the K2 exit criteria as a committed **failing** test. |
| 2 | `jcs-canonicaliser` | RFC 8785 in full with the ES6 number path, the float-ban payload profile, the canonicaliser registry, and the vendoring byte-equality guard. |
| 3 | `merkle-and-proofs` | RFC 6962 MTH / inclusion / consistency / tile addressing and the `link_hash` chain, pure and IO-free, property-tested and vector-tested. |
| 4 | `note-signer-receipt` | C2SP signed-note encode/decode with ECDSA type `0x02`, the `Signer` Protocol (KMS + local), checkpoint body assembly with both beacons, and the Signed Disposition Receipt. |
| 5 | `sequencer` | The lease-CAS singleton sequencer: anti-join batch, in-transaction `seq` derivation, dense fork-free append, the `LedgerSink` implementation, and the N-parallel concurrency proof. |
| 6 | `verify-core` | `trappoint-verify` CLI, bundle loader, structural checks 1·2·3·9·10·13·14·15·16, the report model with loud `SKIP`, the dependency-floor test and the no-network test. |
| 7 | `verify-crypto` | The minimal DER reader, RFC 3161 token verification, log/witness signature verification, NIST + drand beacon checks, S3 Object Lock metadata, triggerdef attestation, WebAuthn re-verification — checks 4·5·6·7·8·11·12. |
| 8 | `anchor-and-evidence-infra` | The anchor fanout behind Protocols (KMS, S3 Object Lock, TSA, beacons, tiles, witness push) and the indelible OpenTofu evidence stack with its policy-as-code merge gate. |
| 9 | `witness-and-custodian` | The ~200-line C2SP `tlog-witness` cosigner, the quorum/diversity/adverse admissibility evaluator, `unwitnessed_debt` reconciliation, and the `ccloud` / schema / IAM custodian attestation patrol. |
| 10 | `reference-ledger-and-nemesis` | The committed, byte-deterministic signed reference bundle a stranger verifies in 30 s; the fifteen-attack nemesis harness; `CUSTODY_ATTACK_MATRIX.md`; the custody CI workflow. |

---

## 6. Risks I am accepting

1. **Witness quorum is `q = 1` over our own S3 plus the `ccloud` audit stream until an insurer, HSR
   or regulator runs the cosigner.** That is **not adverse in the legal sense**, and
   `spec/custody/checks.yaml` marks check 7 `implemented-but-not-adverse`. **Split-view resistance is
   not claimed** and a CI grep enforces its absence from README, deck and video script. The mitigation
   is business development, not code: the service is 200 lines and it is shipped and Dockerised so
   the ask is "run this container", not "build this".
2. **T3 (Cockroach Labs / AWS storage-layer access) is not defeated by anything in the database.**
   Only Object Lock and external witnesses touch it. Stated to the customer, in the README, first.
3. **AWS credentials are invalid today.** W8 ships plan-JSON policy proofs and in-process fakes; every
   live path reports `SKIP(no-credentials)` and appears as such in the attack matrix. The risk is that
   an unexercised path is a broken path — mitigated by making the fakes assert the exact call shape
   (`ObjectLockMode='COMPLIANCE'`, `SigningAlgorithm='ECDSA_SHA_256'`) so the first live run fails
   loudly rather than silently succeeding wrong.
4. **`GT-05` (`pg_get_triggerdef()`) is unanswered.** Verifier check 11 — the self-attesting gate — is
   the highest-value check that depends on it. Fallback is `SHOW CREATE TABLE`, which loses per-trigger
   granularity; check 11 then reports `PASS(coarse)` and the claim softens **in the same commit**.
5. **`GT-18` is a one-shot.** Object Lock and versioning cannot be retrofitted, and backup retention is
   set once at provisioning. W8 lands the evidence stack **before any other Terraform in the repo can
   apply**, enforced by a policy test that fails if any other root module declares an S3 bucket for
   checkpoint objects.
6. **RFC 3161 interop is unproven until real tokens land in CI.** The hand-rolled DER reader is tested
   against a locally-minted chain today; FreeTSA/Sigstore fixtures are a network-dependent step. Listed
   `unverified` until green.
7. **A 60-second window of undetectable mutation is real and is the honest number.** It is stated, not
   buried, and `checkpoint_age_seconds` is a deadman alarm from K6. A ledger that claims zero window is
   lying.
8. **The nemesis harness needs a disposable cluster** (it performs destructive `UPDATE`s). It runs
   against a single-node Docker CockroachDB only, guarded by a fixture that refuses any DSN whose host
   is not `localhost`/`127.0.0.1` — because a nemesis suite that can reach production is itself a T1
   attack surface.

---

*Custody plan, K2. The chain is not the evidence. The commitment that left our control before we
could change our minds is the evidence — and the stranger who can check it without asking us.*

---

# ⚠ PLATFORM GROUND TRUTH — MANDATORY, SUPERSEDES ANY CONFLICTING ASSUMPTION ABOVE

**Measured against the live cluster on 2026-08-07. See `docs/adr/0002-g1-platform-ground-truth.md`.
These are MEASUREMENTS, not documentation. Where your brief or this plan assumed otherwise, THESE WIN.**

**Cluster:** CockroachDB CCL **v26.2.5**, cluster version 26.2, **Basic tier**, `aws-ap-southeast-1` (**Singapore**).
**Bedrock:** `ap-southeast-2` (Sydney), 8 `au.*` Claude profiles ACTIVE (incl. `au.anthropic.claude-sonnet-5`, `au.anthropic.claude-opus-5`).

## F1 — Vector index WORKS on Basic, but the optimizer will not choose it

`feature.vector_index.enabled` is **`true` by default**. `VECTOR(n)` columns and prefix-column vector indexes **create and populate successfully on the free Basic tier**. The largest platform risk is retired.

**BUT:** at 5,200 rows an unhinted prefix-constrained ANN query does **NOT** use the index — the plan is `top-k → render → filter → scan`. The index is traversed **only** when named explicitly:

```sql
SELECT id FROM tbl@tbl_prefix_emb_idx
WHERE tenant = $1 AND state = $2          -- every prefix column = a single value
ORDER BY emb <=> $3 LIMIT $4
```

**RULING:** every ANN arm **pins the index explicitly**. Any CI assertion of the form "EXPLAIN proves the ANN uses the index" must assert traversal of the **named, hinted** index — an unhinted assertion fails at demo corpus scale. This is also the more deterministic engineering: a plan that flips on table statistics must not sit beneath a safety gate.

The `IN (...)` trap is UNCHANGED: every prefix column must still be constrained to a single value, so an ancestor walk is one hinted ANN query per ancestor, `UNION ALL`-ed and re-ranked.

Tunable session vars confirmed present: `vector_search_beam_size = 32`, `vector_search_rerank_multiplier = 50`.

## F2 — The time-travel window is 75 minutes, not 4 hours

`gc.ttlseconds = **4500**` on this cluster (the architecture assumed 14400). **`AS OF SYSTEM TIME` cannot reach beyond ~1 hour.** All long-horizon versioning is the application-level commit DAG. No demo beat, claim, exhibit or test may depend on time-travel reaching further. Verified live: a query past the window is **refused**, not silently wrong — keep that as a conformance case.

## F3 — Confirmed available (build against these freely)

| Capability | Status |
|---|---|
| PL/pgSQL triggers with `RAISE EXCEPTION` | ✅ PASS |
| **CTE inside a UDF** | ✅ PASS — the "no CTE in UDFs" claim was stale (removed v25.1) |
| `ALTER TABLE … ENABLE ROW LEVEL SECURITY` | ✅ PASS |
| `STORED` computed column with `digest()` | ✅ PASS — the `dedupe_key` fix (finding S5) is implementable |
| Partial `UNIQUE` index | ✅ PASS — the one-custodian invariant is implementable |
| `kv.rangefeed.enabled` | ✅ `true` — changefeeds available |
| `amazon.titan-embed-text-v2:0` in ap-southeast-2 | ✅ PRESENT (closes a previously-flagged unverified item) |
| `cohere.embed-v4:0` in ap-southeast-2 | ✅ PRESENT — not in the original design; a benchmark candidate, not a default |
| Bedrock Rerank in ap-southeast-2 | ❌ ABSENT, as assumed. Take no dependency |

## F4 — `CREATE SEQUENCE` succeeds on this cluster

The CI lint banning `CREATE SEQUENCE` / `nextval(` / `SERIAL` / `unique_rowid()` is therefore **load-bearing, not decorative**. Gap-free-by-CAS is only meaningful while that lint holds.

## F5 — Residency: inference in Australia, database in Singapore

Sydney (`ap-southeast-2`) is **Advanced-tier only** — absent from the Basic and Standard region lists. **Any claim of end-to-end Australian data residency is FALSE for this deployment** and must not appear in the README, submission, video, console, or any comment. State the split precisely wherever residency is mentioned.
