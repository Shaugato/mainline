<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Wire format — the Signed Disposition Receipt (SDR)

**Normative. Version `v1.0`, frozen 2026-08-07.** Media type:
`application/vnd.trappoint.sdr+json`. The MAINLINE analogue of Certificate Transparency's
Signed Certificate Timestamp.

The key words MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT and MAY are to be interpreted as
in BCP 14 (RFC 2119, RFC 8174).

---

## 1. The problem it answers

Splitting intake (`ledger_intake`, random primary key, no hot row) from sequencing
(`ledger_leaf`, dense, fork-free) is what gives the ledger `B / L_batch` throughput instead
of `1 / L`. It is exactly CT's submission→merge split, and it inherits exactly CT's cost: a
**Maximum Merge Delay**. Between the moment a disposition is recorded and the moment it
appears under a signed checkpoint, there is a window — ours is **60 seconds** — in which
the record exists but is not yet covered by anything that left our trust boundary.

CT answers this with a promise that is itself a signed object, and so do we.

> **An SDR is a signed promise that a specific leaf will appear in a checkpoint within the
> MMD. A receipt whose leaf never appears is not a missing record — it is affirmative,
> portable proof of log misbehaviour, held by the person we gave it to.**

That inversion is the whole point. Without it, a leaf that quietly never gets sequenced is
invisible. With it, the party who signed the disposition is walking around with a signed
statement from us that contradicts our own log.

---

## 2. What is signed

The signed bytes are the **RFC 8785 (JCS) canonical encoding** of the receipt object,
produced by `canon_v1.canonicalise_payload`.

> **Deviation, stated.** ARCHITECTURE.md §7.2 writes the receipt as
> `Sign_KMS(entry_id ‖ leaf_hash ‖ site ‖ issued_at ‖ MMD)`. A bare concatenation of
> variable-length fields is **ambiguous** — different field values can produce identical
> byte strings — and an ambiguous signature input is a canonicalisation attack waiting to
> be written up. This format fixes the framing as JCS, which is injective, is already the
> framing every leaf uses, and is verifiable with the canonicaliser the verifier already
> vendors. The covered fields are unchanged.

### 2.1 The receipt object

Exactly these members, all REQUIRED, no others permitted:

| Member | Type | Meaning |
|---|---|---|
| `typ` | string | MUST be `"MAINLINE-SDR-v1"`. Domain separation: without it, a signature over one JCS object could be replayed as a signature over another with the same shape. |
| `entry_id` | string | The `ledger_intake.entry_id` UUID, lowercase. |
| `leaf_hash` | string | 64 lowercase hex characters. `SHA-256(0x00 ‖ canon_bytes)`. |
| `site_code` | string | The site whose log this leaf belongs to. |
| `origin` | string | The log origin, identical to line 1 of the checkpoint note. Binds the receipt to **which** log must contain it. |
| `payload_ver` | integer | The canonicaliser version used for `canon_bytes`. |
| `issued_at` | string | RFC 3339 UTC with milliseconds and a literal `Z`. Server clock at intake. |
| `mmd_seconds` | integer | The Maximum Merge Delay. MUST be `60` for `v1.0`. |

Numbers are integers. `mmd_seconds` and `payload_ver` are the only numeric members and
both are exact — the payload profile bans IEEE-754 floats
([ADR 0042](../../docs/adr/0042-float-ban-in-evidentiary-payloads.md)).

`issued_at` is **our** clock, and the receipt makes no claim that it is right. It is the
lower edge of an interval whose upper edge is a checkpoint's RFC 3161 `genTime`; a receipt
alone brackets nothing.

### 2.2 The signature

`ECDSA_SHA_256` over NIST P-256, ASN.1 DER encoding, from the **same AWS KMS key that
signs checkpoints for that origin** — so verifying a receipt requires no key material a
verifier does not already need, and a compromise of the receipt path is a compromise of the
log path, not a second, weaker path.

```
signature = KMS.Sign(
    KeyId          = <log key for origin>,
    Message        = canonicalise_payload(receipt),
    MessageType    = 'RAW',
    SigningAlgorithm = 'ECDSA_SHA_256',
).Signature
```

---

## 3. The envelope

What the intake API returns, and what a holder keeps:

```json
{
  "sdr_version": 1,
  "receipt": { ...the object from §2.1... },
  "key_id": "<8 lowercase hex characters>",
  "sig": "<base64 DER signature>"
}
```

`key_id` is the C2SP `0x02` key ID — `SHA-256(DER SPKI)[:4]` — identical to the one in the
checkpoint signature line, so a holder can tell which key to fetch without parsing a
certificate. The envelope itself is **not** signed; only `receipt` is. A verifier MUST
re-canonicalise `receipt` and MUST NOT verify over the envelope bytes as received.

---

## 4. Verification

`trappoint-verify receipt-audit`, given a receipt and a bundle:

1. `typ == "MAINLINE-SDR-v1"`, all eight members present, no extras.
2. Re-canonicalise `receipt` under `canon_v1`; verify `sig` against the log key for
   `origin`, matching on `key_id`.
3. If the bundle contains the leaf: `leaf_hash` matches, and an inclusion proof to some
   checkpoint's root verifies. → **PASS**.
4. If it does not, and the newest checkpoint's timestamp is **within** `mmd_seconds` of
   `issued_at`: → `SKIP(within-mmd)`, with the deadline printed.
5. If it does not, and the newest checkpoint's timestamp is **beyond** the MMD: →
   **FAIL — log misbehaviour**. This is the only verifier finding that accuses the log
   operator of an act rather than reporting a mismatch, and it is worded that way in the
   report.

Step 5 is what makes the receipt worth issuing. Steps 1–3 alone would make it a nice
acknowledgement.

Verification requires: the receipt, the log's public key, and a canonicaliser. It requires
**no access to our database** — this is verifier check 15.

---

## 5. Worked test vector

The key is the one in [`checkpoint.md` §7.1](checkpoint.md#71-the-key) — the deliberately
public P-256 key, key ID `e74111d1`. The leaf is `seq 3` of that document's five-leaf tree,
the `disposition` entry.

**The receipt object:**

```json
{
  "typ": "MAINLINE-SDR-v1",
  "entry_id": "018f3a2f-9a01-7e42-8b0d-51f6b2c30d44",
  "leaf_hash": "7210abaaa02da99e69515827e6b73629f0ebb503fa248214980de321d9d7a103",
  "site_code": "BLK-07",
  "origin": "mainline.example/site/BLK-07",
  "payload_ver": 1,
  "issued_at": "2026-08-07T02:11:42.310Z",
  "mmd_seconds": 60
}
```

**The signed bytes** — `canonicalise_payload(receipt)`, 287 bytes, members in UTF-16 code
unit order:

```text
{"entry_id":"018f3a2f-9a01-7e42-8b0d-51f6b2c30d44","issued_at":"2026-08-07T02:11:42.310Z","leaf_hash":"7210abaaa02da99e69515827e6b73629f0ebb503fa248214980de321d9d7a103","mmd_seconds":60,"origin":"mainline.example/site/BLK-07","payload_ver":1,"site_code":"BLK-07","typ":"MAINLINE-SDR-v1"}
```

```text
SHA-256(signed bytes) = a503ba06ed004b542a3fe9aebe316021ae5ea156cd17cd19fabd29dd411b5c64
```

**The envelope:**

```json
{
  "sdr_version": 1,
  "receipt": {
    "typ": "MAINLINE-SDR-v1",
    "entry_id": "018f3a2f-9a01-7e42-8b0d-51f6b2c30d44",
    "leaf_hash": "7210abaaa02da99e69515827e6b73629f0ebb503fa248214980de321d9d7a103",
    "site_code": "BLK-07",
    "origin": "mainline.example/site/BLK-07",
    "payload_ver": 1,
    "issued_at": "2026-08-07T02:11:42.310Z",
    "mmd_seconds": 60
  },
  "key_id": "e74111d1",
  "sig": "MEUCIQDidhgEM1fGO6zlKrLOiDhjJiB+oWA1CZsj1q7qvB9SrAIgSkjGgpMK1fn4W0jg/LwbYaQgL/tDQWDX1+Jk567u4go="
}
```

This receipt's `leaf_hash` is the `seq 3` leaf of the tree whose root is
`00c5dddf89d15dfbf9fb2349e0adadbcc4a5131b6612adfc85ad0df2005d359e`, so
`receipt-audit` against that bundle returns **PASS** with an inclusion proof at index 3 of
5.

> As in the checkpoint vector: ECDSA is randomised, so a conforming implementation MUST
> verify these bytes and MUST NOT be expected to reproduce them.

---

## 6. Operational rules

- **A receipt is issued at intake, before sequencing.** Issuing one after the leaf is
  already sequenced is permitted but pointless; issuing one for a leaf that was never
  inserted is attack **A14** (`receipt_orphan`) and is what step 5 of §4 detects.
- **A receipt is never revoked**, and there is no revocation format. A receipt that turns
  out to be wrong is evidence about us, and deleting evidence about ourselves is the
  behaviour this system exists to make impossible.
- **Receipts are handed to the signing party**, surfaced in the console beside the
  disposition, and included in every evidence bundle that contains their leaf.
- **`is_sandbox` leaves get receipts too**, and those receipts carry the sandbox origin. A
  sandbox receipt presented against an evidentiary bundle fails on `origin`, which is
  cheaper than discovering the mix-up later (attack **A12**).

---

## 7. Conformance

An implementation conforms to `v1.0` if it:

1. verifies the vector in §5 against the key in `checkpoint.md` §7.1;
2. rejects it after any single-byte mutation of any member value;
3. rejects a receipt with an unknown member, a missing member, or `typ != "MAINLINE-SDR-v1"`;
4. reproduces the 287 canonical bytes exactly from the object in §5;
5. reports `SKIP(within-mmd)` rather than `FAIL` for an unsequenced leaf inside the MMD,
   and `FAIL` outside it.

---

## References

- RFC 6962 §3 (Signed Certificate Timestamp — the analogue), RFC 8785 (JCS), RFC 3339
- [`checkpoint.md`](checkpoint.md), [`evidence-bundle.md`](evidence-bundle.md)
- `spec/custody/checks.yaml` check 15; `spec/custody/attacks.yaml` A14
- ARCHITECTURE.md §5.6, §7.2
