<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The custody threat model

**Normative.** Machine-readable companion: [`attacks.yaml`](attacks.yaml). Check registry:
[`checks.yaml`](checks.yaml).

> **A hash chain inside a table the adversary owns is a checksum, not evidence.**

Every artefact in the custody layer declares the highest tier it defeats, and
`evidence/CUSTODY_ATTACK_MATRIX.md` is the machine proof of that declaration. The
declarations are in this file because the crypto was chosen by the threat model, not the
other way round.

---

## 1. The tiers

| Tier | Adversary | Capability |
|---|---|---|
| **T0** | Application user | Writes through the MAINLINE API only |
| **T1** | **Rogue DBA** | Arbitrary SQL: `UPDATE`, `DELETE`, `ALTER`, `DROP`, and **recompute every hash in the table** |
| **T2** | Cloud-org admin | T1 **+** delete S3 objects, disable CloudTrail, schedule KMS key deletion, revoke IAM |
| **T3** | Managed-service operator (Cockroach Labs / AWS staff) | Storage-layer access outside our IAM entirely |
| **T4** | T2 colluding with the signer | Can mint valid-looking history **going forward** |

### 1.1 The failure mode this file exists to prevent

**The entire literature failure mode is designing for T0 and claiming T1.**

A T1 attacker does not attack the hash. They delete leaf *k*, renumber `k+1..n`, and
recompute every `link_hash` in one `UPDATE … FROM generate_series`. The table is afterwards
perfectly self-consistent, every internal check passes, and the record of the incident is
gone. Sequence gap-freedom becomes evidence **only when an independent party already holds
a commitment to the head**.

So the design question was never "which hash". It was: *how fast can a commitment leave our
control, and who is holding it?* The answer is 60 seconds, an RFC 3161 authority, an S3
Object Lock COMPLIANCE bucket in a separate account, and witnesses in adverse trust
domains.

### 1.2 What "defeats" means here

An artefact **defeats tier T** if an adversary with T's capabilities cannot make a false
custody claim true *without detection*. It does not mean prevention. Nothing in this design
prevents a T1 adversary from corrupting the tables; the claim is that every corrupted state
fails verification against commitments they can neither forge nor recall.

---

## 2. Tier declarations, per artefact

| Artefact | Defeats up to | Why it stops there |
|---|---|---|
| `link_hash` chain in `ledger_leaf` | **T0** | A T1 adversary recomputes the whole chain in one statement. It is kept because it is jury-legible, not because it is strong. |
| `PRIMARY KEY (site_code, seq)` + `UNIQUE (site_code, prev_link_hash)` | **T0** | Refuses a fork at write time even under READ COMMITTED. A T1 adversary drops the constraint. |
| `fn_refuse_mutation` append-only triggers | **T0** | Same: `ALTER TABLE … DISABLE TRIGGER` is one statement for a T1 adversary. Its value is that the drop is loud. |
| RFC 6962 tree + consistency proofs | **T1**, given an external commitment | Without an anchored earlier root, a consistency proof proves nothing — the adversary supplies both roots. |
| KMS `ECC_NIST_P256` log signature | **T1** | A T1 adversary has arbitrary SQL and no path to `kms:Sign`. Falls to **T2** (key policy change) and **T4** (collusion). |
| RFC 3161 TSA tokens (≥ 2 independent) | **T4** | The one control a colluding signer cannot retroactively defeat: they cannot make a third party's past timestamp say something else. |
| Public beacons (drand + NIST) | **T2** | Bounds below. Against **T4** it is only as strong as the log signature, because cosignature types `0x04`/`0x06` do not cover extension lines. |
| S3 Object Lock COMPLIANCE, separate account | **T2** | *"A protected object version can't be overwritten or deleted by any user, including the root user."* Falls to **T3**. |
| Adverse witness cosignatures | **T4**, *when adverse* | Today *q* = 1 over our own infrastructure — **not adverse in the legal sense**. See §4. |
| `trappoint-verify`, offline | **T2** | The verifier itself is outside our control once shipped; a stranger runs their own copy. It cannot help if every commitment it checks came from us. |
| The custodian patrol (`ccloud` audit, schema fingerprint, IAM snapshot) | **T1** | Makes a T1 `DROP CONSTRAINT` an attested ledger leaf within one cycle. Does not stop it. |

---

## 3. T3 is not defeated

**Cockroach Labs staff have a privileged storage path to our data, and AWS staff have one to
our objects. No in-database mechanism can address that.** Only Object Lock and external
witnesses touch it, and neither is complete.

This is stated to the customer, in the README, first — because saying it first is the only
version of the sentence that helps us, and because a competent opposing expert reaches it
in about four minutes. Saying it second is called being caught.

It is also an argument *for* this architecture rather than against it: a design whose
integrity rested on the honesty of a managed-service provider would have no answer at all,
and most designs in this space do not.

---

## 4. What must not be claimed

Bound into the README, the deck, the video script and the MSA, and enforced by a CI grep
over the custody paths:

1. **Split-view resistance**, until at least one genuinely adverse witness is live. A *q* = 1
   quorum over our own S3 plus our own `ccloud` audit stream is not adverse.
2. **A zero window of undetectable mutation.** It is ~60 seconds. That is the honest number,
   it is stated rather than buried, and `checkpoint_age_seconds` is a deadman alarm.
3. **That RLS defends against a rogue admin.** Table owners bypass policies absent
   `FORCE ROW LEVEL SECURITY`, and an admin can `ALTER` them away. RLS is tenancy hygiene.
4. **That SERIALIZABLE is what makes the ledger trustworthy.**
   `PRIMARY KEY (site_code, seq)` prevents fork-by-duplicate even at READ COMMITTED.
   SERIALIZABLE is what makes the *gate* correct. Conflating the two is the first thing a
   competent opposing expert pulls apart.
5. **That a disposition can be distinguished from a rubber stamp.** The chain makes
   rubber-stamping *measurable*, which sharpens the exhibit in both directions.
6. **Enclave-attested signing.** KMS Nitro Enclave attestation condition keys
   (`kms:RecipientAttestation:ImageSha384`) apply to `Decrypt`, `DeriveSharedSecret`,
   `GenerateDataKey(Pair)` and `GenerateRandom`. **`Sign` is not in that list.** You cannot
   attestation-gate KMS signing directly. The working pattern — generate the key inside the
   enclave, wrap it under an attestation-gated KMS key, unwrap and sign locally — is real
   engineering and is a phase-2 item. Claiming it now would be false.
7. **Multi-month `AS OF SYSTEM TIME`.** `gc.ttlseconds` is 4 h. MVCC history is not a time
   machine, and no demo beat may rest on it.

---

## 5. Where the design deliberately spends nothing

- **Content authenticity** of an ingested document is out of scope. **Provenance** — who
  submitted it, when, its hash, its Object Lock version — is in scope. We do not claim the
  narrative inside a PDF is true.
- **Coercion.** Non-repudiation is cryptographic, not moral. A WebAuthn assertion proves a
  credential was exercised with user verification; it does not prove the person was free.
- **Exhaustion of the corpus.** We claim exhaustion of the *retrieval that ran*, which is a
  different and smaller claim, and we log the difference.

---

## 6. How this file is kept true

`attacks.yaml` lists fifteen attacks against these tiers. The nemesis harness executes each
one against a disposable single-node cluster and a real bundle, and emits
`evidence/CUSTODY_ATTACK_MATRIX.md` — attack × detecting check × detection latency — from
the run rather than from this document. CI fails if any attack is detected by zero checks
and flags any detected by exactly one.

If a tier declaration in §2 is wrong, the matrix disagrees with it and the build says so.
That is the point: a threat model nobody can falsify is a marketing document.

---

## References

- `research/05-architecture/custody-tamper-evidence.md` §1
- ARCHITECTURE.md §7.6, §11.1, §11.7
- `docs/leads/custody.md` §1.1, §1.5, §6
- AWS S3 Object Lock overview; AWS KMS Nitro Enclaves condition keys
