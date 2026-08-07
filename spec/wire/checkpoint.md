<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Wire format — the signed checkpoint

**Normative. Version `v1.0`, frozen 2026-08-07.** Media type:
`application/vnd.trappoint.checkpoint`. Profile of
[c2sp.org/tlog-checkpoint](https://c2sp.org/tlog-checkpoint) over
[c2sp.org/signed-note@v1.0.0](https://c2sp.org/signed-note).

This document is frozen **before a single real leaf is written**. It is the interface an
opposing expert writing their own verifier — plausibly in Rust, plausibly hostile —
implements from. Changing it after a million rows is not a migration of data; it is a
migration of *evidence*, and every checkpoint signed under the old shape becomes a thing
that has to be explained rather than verified. Extending it is cheap
([§9](#9-extending-this-format)); changing it is not.

The key words MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT and MAY are to be interpreted
as in BCP 14 (RFC 2119, RFC 8174).

---

## 1. What a checkpoint is, and what it is for

A checkpoint is a signed statement of the form *"at tree size **n**, the root of this log's
RFC 6962 Merkle tree is **r**"*, plus two independent statements about **when**.

It is the only object in the custody design that **leaves our trust boundary**. Everything
else — the ledger tables, the tree, the link chain — lives inside a database the future
defendant owns, and is therefore a checksum rather than evidence. The checkpoint is what an
RFC 3161 authority timestamps, what S3 Object Lock COMPLIANCE holds, and what a witness in
an adverse trust domain cosigns. Its wire format is the whole interface to those parties.

Four propositions the format is designed to support, and the part of it that does the work:

| Proposition | Carried by |
|---|---|
| **Existence at a bracketed time T** | the beacon extension lines (lower bound) + the RFC 3161 token over the note text (upper bound) |
| **Non-alteration** | the root hash, signed |
| **Non-omission** | consistency proofs between consecutive checkpoints, which the root hashes make checkable |
| **Provenance of process** | the `canon:` extension line, which names the code that produced the bytes underneath |

---

## 2. The note format

A checkpoint is a **signed note**. Byte-exactly:

```
<note text, ending in U+000A>
<U+000A>
<one or more signature lines, each ending in U+000A>
```

- The note text is separated from the signatures by the **last empty line** in the note.
  The note text **includes** its own final newline and **excludes** the separating blank
  line. The signed bytes are the note text and nothing else.
- Each signature line is: em dash **U+2014**, space **U+0020**, key name, space,
  base64 signature, newline.
- The base64 alphabet throughout is standard Base 64 (RFC 4648 §4), **with** padding.
- The signature value decodes to `4-byte big-endian key ID ‖ signature bytes`.
- The whole note MUST be valid UTF-8 and MUST NOT contain any ASCII control character
  below U+0020 other than newline.

A verifier MUST accept at least 16 signature lines and MUST **ignore signature lines whose
key it does not know**. That rule is what lets witnesses cosign, and what lets us add an
Ed25519 log signature later, without any change to this document.

> The em dash is U+2014 (UTF-8 `e2 80 94`), not a hyphen and not U+2013. Getting this wrong
> produces a note that parses as one long text with no signatures, which then fails
> verification for the wrong reason. It is the single most common implementation error in
> the format.

---

## 3. The note text

At least three non-empty lines, newline-separated:

| Line | Field | Rule |
|---|---|---|
| 1 | **origin** | Non-empty. The log identity. MUST be `mainline.<domain>/site/<site_code>` for MAINLINE logs — one log per site, because a site is the unit a permit belongs to and the unit an inspector asks about. No Unicode spaces, no `+`. |
| 2 | **tree size** | ASCII decimal, **no leading zeroes**, `0` for the empty tree. This is the number of leaves, not the number of intake rows. |
| 3 | **root hash** | base64 of the 32-byte RFC 6962 Merkle Tree Hash at that size. For `tree_size = 0` this is base64 of `SHA-256("")`. |
| 4+ | **extension lines** | Non-empty. Defined in [§4](#4-extension-lines). |

Nothing else. No trailing blank line inside the text (the blank line belongs to the
framing, not to the text).

`origin` is an identifier, not a URL to fetch. A verifier MUST NOT dereference it and MUST
NOT assume it resolves.

---

## 4. Extension lines

C2SP says extension-line use is NOT RECOMMENDED, "as they are not auditable by log
monitors". We use three, deliberately, and state the cost rather than hide it.

Each extension line is `<name>: <value>`, where `<name>` matches `[a-z][a-z0-9.]*`, the
separator is exactly a colon and one space, and `<value>` contains no newline. A verifier
MUST ignore an extension line whose name it does not recognise, and MUST NOT treat an
unrecognised name as an error — that is what keeps [§9](#9-extending-this-format) cheap.
Extension lines MUST appear in the order given below, and each name MUST appear at most
once, so that the note text is a function of its content.

### 4.1 `canon:` — the scheme's own code, inside the scheme

```
canon: <payload_ver decimal> <64 lowercase hex characters>
```

The hex value is `canon_src_sha256`: SHA-256 over the source of the canonicaliser that
produced the `canon_bytes` of every leaf in this tree, **over LF-normalised bytes**.

> **Normative hashing rule.** The digest is taken over the source file's bytes with every
> CRLF sequence replaced by LF, and nothing else normalised. Without that rule the value
> fingerprints whether the checkout ran on Windows with `core.autocrlf=true` rather than
> fingerprinting the code, and two honest verifiers would disagree.
> `trappoint_jcs.canon_v1.canon_src_sha256()` computes exactly this value, and
> `spec/custody/canon-registry.yaml` pins it.

This is verifier **check 10**. It converts *"we canonicalised correctly"* from a claim into
a comparison: the verifier hashes the canonicaliser it is itself running and refuses to
agree that the leaves check out if the two differ. It also makes a canonicaliser downgrade
(attack **A5**) visible — re-canonicalising an old leaf under a newer version changes this
line, and this line is signed.

### 4.2 `drand:` — the unpredictability lower bound

```
drand: <64 hex chain hash> <round decimal> <64 hex randomness>
```

The drand **quicknet** chain, `bls-unchained-g1-rfc9380`, chain hash
`52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971`, period 3 s, genesis
`1692803367`. A round's value cannot be known before it is issued, so a checkpoint quoting
round *r* **cannot have been constructed before** `genesis + (r − 1) × period`.

Round-to-time is arithmetic and is verifiable offline with no dependency:

```
round_time = 1692803367 + (round − 1) × 3
```

The BLS12-381 G1 signature over the round is **not** verifiable under the verifier's
dependency floor (`cryptography` has no BLS12-381). Verifier check 6b therefore reports
`SKIP(optional-extra)` unless `trappoint-verify[beacon]` is installed. **The `drand:` line
alone is not a lower bound a stranger can check.** That is why there are two beacons.

### 4.3 `nist:` — the verifiable lower bound

```
nist: 2.0 <chainIndex>.<pulseIndex> <128 hex outputValue>
```

A NIST Interoperable Randomness Beacon 2.0 pulse. Its signature is RSA PKCS#1 v1.5 over
SHA-512 with an X.509 certificate, **all of which `cryptography` verifies**, so this is the
lower bound that survives the dependency floor. Verifier check 6a fully verifies it.

Two beacons, two independent issuers, and only one of them load-bearing offline — stated
here so that nobody later reads the `drand:` line as proof of something a verifier never
checked.

### 4.4 The honest cost of using extension lines

The `0x02` log signature covers the **entire note text, extension lines included**. A
cosignature of type `0x04` or `0x06` (`c2sp.org/tlog-cosignature`) does **not** cover
extension lines. Therefore:

> **The beacon lower bound is exactly as strong as the log signature, and no stronger.** A
> witness cosignature attests to `(origin, size, root)`; it does not attest to the beacon
> lines. A T4 adversary — the cloud admin colluding with the signer — can mint a checkpoint
> with any beacon lines they like, and the witnesses will still cosign it.

The bound that survives T4 is the **RFC 3161 token over the note text** plus the witness's
own record of when it saw size *n*. This paragraph exists so that no MAINLINE document,
deck or report can claim otherwise without contradicting a normative specification.

---

## 5. Signatures

### 5.1 The log signature — profile ruling CU-3

**Signature type `0x02`: ECDSA over NIST P-256 with SHA-256.**

| Element | Value |
|---|---|
| Key | AWS KMS `ECC_NIST_P256`, `SIGN_VERIFY`, in an account separate from both the database and the archive |
| KMS call | `Sign(MessageType='RAW', SigningAlgorithm='ECDSA_SHA_256')` over the note text |
| Signature bytes | **the ASN.1 DER encoding, exactly as KMS returns it**: `SEQUENCE { r INTEGER, s INTEGER }` |
| Key ID | `SHA-256(DER SPKI public key)[:4]`, big-endian |
| Key name | the origin line |

**The DER-versus-`r‖s` ruling is normative and is not ours to invent.** C2SP defines
`0x02` as "ECDSA signatures as implemented by github.com/transparency-dev/witness", whose
verifier calls Go's `ecdsa.VerifyASN1` over `SHA-256(note text)` — that is DER. AWS KMS
returns DER for `ECDSA_SHA_256`. The two agree, so MAINLINE stores KMS's bytes verbatim and
adds no re-encoding step. An implementer who assumed fixed-width `r‖s` (the JOSE/COSE
convention, 64 bytes) will fail verification; §7 exists so they find that out in ten
seconds rather than in a deposition.

Note that the `0x02` key ID rule is **different from the Ed25519 one**. For `0x01` the key
ID is `SHA-256(name ‖ 0x0A ‖ 0x01 ‖ pubkey)[:4]`; for `0x02` it is the truncated SHA-256 of
the DER SPKI **alone** — no name, no algorithm byte. This is what C2SP specifies and what
the reference implementation computes. Deriving it the Ed25519 way produces a key ID
mismatch and a note that "verifies" against nothing.

**Why not Ed25519.** `0x01` is what the public witness ecosystem prefers, and KMS cannot
produce it. The alternative is a software Ed25519 key living in a Lambda's memory, which
destroys the entire rogue-DBA argument: the point of KMS is that a T1 adversary with
arbitrary SQL has no path to `kms:Sign`. We take the less fashionable algorithm and keep
the property. Adding an Ed25519 line later is purely additive ([§9](#9-extending-this-format)).

### 5.2 Verifier key encoding

```
<origin>+<8 hex key ID>+<base64(0x02 ‖ DER SPKI)>
```

This is the C2SP *vkey* form. It is what a witness is configured with and what
`trappoint-verify --log-key` accepts.

> **Parse on the first two `+` only.** The third field is standard base64, whose alphabet
> includes `+`, so splitting on every plus produces four fields for most keys and three for
> the rest — a bug that passes in testing and fails on the next key you generate. C2SP
> forbids `+` in a key name precisely so that the first two separators are unambiguous. A
> conforming parser MUST use a two-split-limit, and MUST verify that
> `SHA-256(DER SPKI)[:4]` equals the hex key ID rather than trusting the field.

### 5.3 Witness cosignatures

Additional signature lines, one per witness, each with its own key name and key ID. A
checkpoint's `admissible` flag is a **projection** computed from the cosignatures actually
received (≥ *q* distinct trust domains, ≥ 1 adverse); it is never a value a writer
supplies, and it is not part of this wire format. A checkpoint below quorum is still a
valid checkpoint and is still recorded — it is marked **unwitnessed debt**, because going
dark must remain possible and must self-report.

**Split-view resistance is not claimed by this document.** Until a genuinely adverse
witness runs the cosigner, the quorum is *q* = 1 over our own infrastructure, which is not
adverse in the legal sense.

---

## 6. The verification algorithm, in order

A conforming verifier, given a note and a set of trusted keys:

1. Split at the **last** empty line. Everything before it, plus its own trailing newline,
   is the **signed text**. Everything after is signature lines.
2. Reject if any byte outside the signature lines is an ASCII control character other than
   U+000A, or if the whole note is not valid UTF-8.
3. Parse the signed text: origin, tree size (decimal, no leading zeroes), base64 root
   (MUST decode to exactly 32 bytes), then extension lines.
4. For each signature line: em dash, space, name, space, base64. Decode; the first 4 bytes
   are the key ID. If `(name, key ID)` is not a known key, **ignore the line**.
5. For each known key, verify. `0x02`: `ECDSA_P256_SHA256_Verify(pubkey, SHA-256(signed
   text), DER signature)`.
6. If any signature from a known key fails, reject the whole note. If no signature from a
   known key verified, reject the note.
7. Only then read the tree size, root and extensions. **Unverified note text is not data.**

Step 7 is not decoration. A verifier that parses first and checks later has already let
attacker-chosen bytes into its state machine.

---

## 7. Worked test vector

Everything below is exact. `trappoint-verify` and `trappoint_ledger.note` both read these
values out of this file, so this document and the code cannot drift.

### 7.1 The key

**NOT SECRET.** This private key is published deliberately so that anyone can reproduce
every value in this section. It signs nothing but this document's example. It is not, and
never was, a MAINLINE log key.

```text
d (hex) = 5ae1b3c0f2d48e7691a0c5b4837f2e1d9c6b0a5849372615f4e3d2c1b0a99887
```

```pem
-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgWuGzwPLUjnaRoMW0
g38uHZxrClhJNyYV9OPSwbCpmIehRANCAATO703slMVritEAJlRDmWJegr2+PCaJ
C5zsORhE60cA1crG2AyXcm4aVrIdz+CBgjVfu8NPJwBbjs2IJuq5XP93
-----END PRIVATE KEY-----
```

```pem
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEzu9N7JTFa4rRACZUQ5liXoK9vjwm
iQuc7DkYROtHANXKxtgMl3JuGlayHc/ggYI1X7vDTycAW47NiCbquVz/dw==
-----END PUBLIC KEY-----
```

| Derived value | |
|---|---|
| DER SPKI (hex) | `3059301306072a8648ce3d020106082a8648ce3d03010703420004ceef4dec94c56b8ad10026544399625e82bdbe3c26890b9cec391844eb4700d5cac6d80c97726e1a56b21dcfe08182355fbbc34f27005b8ecd8826eab95cff77` |
| `SHA-256(DER SPKI)` | `e74111d1f8b1e206f6308994350f725f3f239e3528fb0c47651d9bfb29fc4c4f` |
| **key ID** | `e74111d1` |

Verifier key (vkey):

```text
mainline.example/site/BLK-07+e74111d1+AjBZMBMGByqGSM49AgEGCCqGSM49AwEHA0IABM7vTeyUxWuK0QAmVEOZYl6Cvb48JokLnOw5GETrRwDVysbYDJdybhpWsh3P4IGCNV+7w08nAFuOzYgm6rlc/3c=
```

### 7.2 The tree — five leaves, end to end

Each leaf's `canon_bytes` is `canonicalise_payload(payload)` under `canon_v1`
(`payload_ver = 1`), and `leaf_hash = SHA-256(0x00 ‖ canon_bytes)` per RFC 6962 §2.1.

```text
seq 0  canon_bytes (115 bytes)
{"applied_at":"2026-08-07T01:58:00.000Z","entry_kind":"schema","migration":"0073_ledger_leaf","site_code":"BLK-07"}
leaf_hash 70c5e3eb5ac6f166d38308eda90eb814a0fab95f7c5a7864578677c2d985f565

seq 1  canon_bytes (152 bytes)
{"advisory":12,"blocking":2,"candidates":41,"entry_kind":"recall","permit_id":"018f3a2e-6c40-7b21-9c55-2a5c9e0f1b77","silenced":27,"site_code":"BLK-07"}
leaf_hash 9dab2ac9240f71f0b83ad7bee9e3529ae44c6ca980efa513091a2dead5fea71a

seq 2  canon_bytes (190 bytes)
{"check_id":"018f3a2f-1104-7c88-b3aa-77c1de40e2b1","clause_uuid":"018f3a30-2200-7d10-9f31-0c9a4e77bb02","entry_kind":"check_open","severity":5,"site_code":"BLK-07","virulence":"blood_fatal"}
leaf_hash b4d70447185d01f04fb4974602e9fb592065462156344d5dca6e0521893f1a74

seq 3  canon_bytes (212 bytes)
{"check_id":"018f3a2f-1104-7c88-b3aa-77c1de40e2b1","disposition_kind":"controlled","entry_kind":"disposition","issued_at":"2026-08-07T02:11:42.006Z","signer_rank":4,"signer_sub":"auth0|4f2c","site_code":"BLK-07"}
leaf_hash 7210abaaa02da99e69515827e6b73629f0ebb503fa248214980de321d9d7a103

seq 4  canon_bytes (151 bytes)
{"entry_kind":"merge","merged_at":"2026-08-07T02:13:55.417Z","open_blocking":0,"permit_id":"018f3a2e-6c40-7b21-9c55-2a5c9e0f1b77","site_code":"BLK-07"}
leaf_hash 1976041b3afddddb75272afed810b6e45ed0f5be5092a87844f685673afc0e6d
```

The **link chain** — `link_hash[0] = SHA-256(0x00…00 ‖ leaf_hash[0])`, thereafter
`link_hash[i] = SHA-256(link_hash[i−1] ‖ leaf_hash[i])`, genesis being 32 zero bytes:

```text
0  55b8d43b5df9834c483e55d69c45665aa04b573bb72c690fbc7dc9782eda4abb
1  cbb447ff927810641bbb21d4753b11c006b18603cd1467b40620013b03f28df8
2  b6934b321ccac22e4bd9cabd955bd501fa4e19965743c802a1f7243dfeeb6281
3  519a899406c29465c1734251bcbbcddc2e253482389a89a0fcd31d427265908f
4  f1661ad080f19c06b85c9bfc415922d0ee01e1769aa05c288138c7325a7c14c0
```

The **RFC 6962 Merkle Tree Hash** at size 5, `MTH(D[0:5]) = SHA-256(0x01 ‖ MTH(D[0:4]) ‖
MTH(D[4:5]))`:

```text
root (hex)    00c5dddf89d15dfbf9fb2349e0adadbcc4a5131b6612adfc85ad0df2005d359e
root (base64) AMXd34nRXfv5+yNJ4K2tvMSlExtmEq38ha0N8gBdNZ4=
```

The link chain and the Merkle tree are both kept, because they fail differently and because
they persuade differently: the tree is what *proves* non-omission, the chain is what
*explains* it to a jury — "entry 4 names entry 3".

### 7.3 The note text (the signed bytes)

446 bytes, ending in a newline. `SHA-256` of these bytes is
`1f335bff3e6d18be003327ce5b564ff2a85402d4297ab0c1d9068a424a53ddec`.

```text
mainline.example/site/BLK-07
5
AMXd34nRXfv5+yNJ4K2tvMSlExtmEq38ha0N8gBdNZ4=
canon: 1 260ed37ddc610f1fb94ddce98998fe4ae5ce883698ad5c7033839cd258dcd659
drand: 52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971 31088494 7d045d05caf218eff9f7bafe0acb452b94a8c369d138ce23c4807b4b62ce46c7
nist: 2.0 2.29255654 d7a6237ed272c6c48bfa16552709fa2c564448e263906af4ba6a740aacef3cd40431e945cdfcfc855f321c14056ac89a94b47b50472cc92aab890ceafa42baad
```

The drand round is arithmetically consistent with the checkpoint's stated issue time:
`1692803367 + (31088494 − 1) × 3 = 1786068846` = **2026-08-07T02:14:06Z**. A verifier
recomputes that and compares it against the RFC 3161 `genTime`; if the beacon time is
*after* the timestamp, the checkpoint claims to quote a round that did not yet exist, which
is attack **A9**.

### 7.4 The signature

```text
DER signature (hex)
3045022100e04abf2882fec769c7156a2ec6366e6f96b6ec46827e947db747ee1d2ece299a
022040677922ce51a00cb2f2d2bd9d79e9a3694c29fd8b211da305c5ed99850fdebb

base64(key ID ‖ DER signature)
50ER0TBFAiEA4Eq/KIL+x2nHFWouxjZub5a27EaCfpR9t0fuHS7OKZoCIEBneSLOUaAMsvLSvZ156aNpTCn9iyEdowXF7ZmFD967
```

(The DER value is shown wrapped across two lines for legibility; it is one 71-byte string.)

> ECDSA is randomised. Re-signing this note text with the same key produces **different**
> signature bytes that also verify. The vector is a *verification* vector, not a *signing*
> vector: a conforming implementation MUST verify the bytes above, and MUST NOT be expected
> to reproduce them.

### 7.5 The complete note

`SHA-256` of the whole note is
`5c21973142e1350788c572c6838a8f53e14843b8bb519a6bb52c72ff8afbd800`.

```text
mainline.example/site/BLK-07
5
AMXd34nRXfv5+yNJ4K2tvMSlExtmEq38ha0N8gBdNZ4=
canon: 1 260ed37ddc610f1fb94ddce98998fe4ae5ce883698ad5c7033839cd258dcd659
drand: 52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971 31088494 7d045d05caf218eff9f7bafe0acb452b94a8c369d138ce23c4807b4b62ce46c7
nist: 2.0 2.29255654 d7a6237ed272c6c48bfa16552709fa2c564448e263906af4ba6a740aacef3cd40431e945cdfcfc855f321c14056ac89a94b47b50472cc92aab890ceafa42baad

— mainline.example/site/BLK-07 50ER0TBFAiEA4Eq/KIL+x2nHFWouxjZub5a27EaCfpR9t0fuHS7OKZoCIEBneSLOUaAMsvLSvZ156aNpTCn9iyEdowXF7ZmFD967
```

### 7.6 The empty tree

```text
mainline.example/site/BLK-07
0
47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=
```

`47DEQpj8…` is base64 of `SHA-256("")`, which RFC 6962 §2.1 defines as `MTH({})`. A
verifier MUST accept a size-0 checkpoint; the alternative is a log that cannot prove it was
empty when it was empty.

---

## 8. Storage binding

| Wire element | Column |
|---|---|
| the whole note text (signed bytes) | `mainline.ledger_checkpoint.body STRING` |
| the `0x02` signature bytes (DER) | `ledger_checkpoint.log_sig BYTES` |
| tree size | `ledger_checkpoint.tree_size INT8` (PK with `site_code`) |
| root hash | `ledger_checkpoint.root_hash BYTES` |
| `canon:` hex value | `ledger_checkpoint.canon_src_sha256 BYTES` |
| `drand:` / `nist:` values, parsed | `ledger_checkpoint.beacon JSONB` |
| RFC 3161 token over the note text | `ledger_checkpoint.tsa_token BYTES` |
| S3 Object Lock version of the note | `ledger_checkpoint.s3_version STRING` |
| each cosignature line | one `mainline.cosignature` row |

`body` stores the note **text**, not the whole note: the signatures live in `log_sig` and
`cosignature` so that a cosignature arriving later is an INSERT rather than an UPDATE of a
row in an append-only table.

---

## 9. Extending this format

**Additive changes — MINOR, no version bump of consumers:**

- a new signature line, of any type, for any key (a verifier ignores unknown keys);
- a new extension line name (a verifier ignores unknown names);
- a new `payload_ver` in the `canon:` line, alongside a new registry entry.

**Breaking changes — a new document version, and every existing checkpoint stays valid
under `v1.0` forever:**

- changing the meaning or order of lines 1–3;
- changing the log signature type, encoding or key-ID derivation;
- removing an extension line that was present;
- changing the `canon:` hashing rule.

There is no mechanism for reissuing a checkpoint. A checkpoint found to be defective is
answered by a **new** entry recording the defect, never by a corrected old one — repairing
history to make verification pass is precisely the behaviour this product exists to detect.

---

## 10. Conformance

An implementation conforms to `v1.0` if it:

1. verifies the note in [§7.5](#75-the-complete-note) against the vkey in
   [§7.1](#71-the-key);
2. rejects that note after any single-byte mutation anywhere in the note text;
3. accepts a note carrying an **additional** signature line from an unknown key, still
   verifies the known one, and preserves the unknown line byte-for-byte on re-encode;
4. recomputes the root in [§7.2](#72-the-tree--five-leaves-end-to-end) from the five
   `canon_bytes` values;
5. accepts the empty-tree checkpoint in [§7.6](#76-the-empty-tree);
6. rejects a tree size with a leading zero, a root that does not decode to 32 bytes, an
   extension line that is empty, and a signature line using U+002D or U+2013 in place of
   U+2014;
7. parses the vkey in [§7.1](#71-the-key) — whose base64 field contains a `+` — into
   exactly three fields, and recomputes its key ID rather than trusting it;
8. recomputes the `drand:` round time as `1692803367 + (round − 1) × 3` and reports a
   finding when it falls after the RFC 3161 `genTime`.

`packages/trappoint-ledger` is the reference implementation and
`tests/integration/custody/test_k2_exit.py` asserts the freeze.

---

## References

- [c2sp.org/tlog-checkpoint](https://c2sp.org/tlog-checkpoint), [c2sp.org/signed-note](https://c2sp.org/signed-note)
- RFC 6962 §2.1 (Merkle Tree Hash), RFC 8785 (JCS), RFC 4648 §4 (base64), RFC 3161 (TSP)
- `github.com/transparency-dev/formats/note` — the `0x02` reference verifier (`ecdsa.VerifyASN1`, key ID = `SHA-256(DER)[:4]`)
- `docs/adr/0041-checkpoint-wire-format.md`, `docs/adr/0043-log-signature-ecdsa-p256-note-type-02.md`, `docs/adr/0044-two-beacons.md`
- `docs/leads/custody.md` §2 CU-3, CU-4
