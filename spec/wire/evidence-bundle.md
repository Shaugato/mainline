<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Wire format — the evidence bundle

**Normative. Version `v1.0`, frozen 2026-08-07.** Media type:
`application/vnd.trappoint.evidence-bundle+json`. Canonical encoding: RFC 8785 (JCS) under
`canon_v1`.

**One JSON file. Self-describing. Emailable.** A stranger who receives it needs no
credential, no network, no cooperation from us, and nothing installed but Python and
`cryptography`:

```console
$ uvx trappoint-verify verify --bundle bundle.json
checkpoint chain OK · inclusion OK · consistency OK (n=5) · 0 findings
```

That sentence being *true when a hostile expert tests it* is the deliverable of the whole
custody domain. This document is what makes it implementable by someone who is not us.

The key words MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT and MAY are to be interpreted as
in BCP 14 (RFC 2119, RFC 8174).

---

## 1. Design rules the shape obeys

1. **Self-describing.** Every hash names its algorithm's version through `payload_ver` and
   `canon_src_sha256`; nothing is "obviously SHA-256 because everything is".
2. **No indirection to us.** No URL in the bundle is required to be fetched. Online checks
   exist (`--s3`, `--kms-pubkey`, `--tile-url`) and are strictly opt-in; without them the
   affected checks report `SKIP(offline)` rather than silently passing.
3. **Bytes, not renderings.** `canon_bytes` is carried verbatim (base64) alongside the
   parsed `payload`. A verifier hashes the bytes and MUST NOT re-canonicalise the parsed
   payload to obtain them — that would test our canonicaliser against itself.
4. **Absence is a value.** Every optional section, when absent, downgrades a specific named
   check to `SKIP(reason)`. A bundle that omits `witness_cosignatures` does not quietly
   pass check 7.
5. **Append-only vocabulary.** Unknown members MUST be ignored by a verifier, so a bundle
   from a later minor version still verifies under `v1.0`.

---

## 2. Top level

```jsonc
{
  "bundle_version": 1,                  // integer, MUST be 1
  "generated_at":   "2026-08-07T02:15:00.000Z",
  "generator":      "trappoint-ledger 0.1.0",
  "origin":         "mainline.example/site/BLK-07",
  "site_code":      "BLK-07",
  "canon": { "payload_ver": 1, "canon_src_sha256": "260ed37d…d659" },

  "checkpoints":         [ /* §3 */ ],   // REQUIRED, >= 1, ascending tree_size
  "consistency_proofs":  [ /* §4 */ ],   // REQUIRED when checkpoints.length > 1
  "leaves":              [ /* §5 */ ],   // REQUIRED, >= 0, ascending seq
  "inclusion_proofs":    [ /* §6 */ ],   // REQUIRED, one per leaf
  "receipts":            [ /* §7 */ ],   // OPTIONAL -> check 15 SKIP(no-receipts)
  "witness_cosignatures":[ /* §8 */ ],   // OPTIONAL -> check 7  SKIP(no-witnesses)
  "schema_attestations": [ /* §9 */ ],   // OPTIONAL -> check 11 SKIP(no-attestation)
  "closure_generations": [ /* §10 */ ],  // OPTIONAL -> check 14 SKIP(no-closure-rows)
  "webauthn_assertions": [ /* §11 */ ],  // OPTIONAL -> check 12 SKIP(no-assertions)
  "archive":             { /* §12 */ },  // OPTIONAL -> check 8  SKIP(no-archive-metadata)
  "notes":               "free text, never load-bearing"
}
```

`generated_at` and `generator` are provenance, not evidence, and no check reads them.

All binary values are **base64** (RFC 4648 §4, padded) unless the member name ends in
`_hex`, in which case they are lowercase hexadecimal. Both forms appear because hashes are
compared by eye in reports (hex) and carried in bulk (base64), and mixing them silently is
how a verifier ends up comparing a hex string to a base64 string and passing.

---

## 3. `checkpoints[]`

```jsonc
{
  "tree_size":  5,
  "root_hex":   "00c5dddf…359e",
  "note":       "<the complete signed note, verbatim, including signature lines>",
  "log_key":    "mainline.example/site/BLK-07+e74111d1+AjBZMBM…/3c=",
  "tsa_tokens": [ { "issuer": "freetsa.org", "token_b64": "MIIF…" } ],
  "observed_at":"2026-08-07T02:14:07.481Z"
}
```

- `note` is the **whole note** as specified in [`checkpoint.md`](checkpoint.md) §2,
  byte-for-byte, newlines included. `tree_size` and `root_hex` are **redundant** with it on
  purpose: a verifier MUST parse the note and MUST compare, and a disagreement is a finding
  (a bundle whose index disagrees with its own contents has been assembled by something
  that did not read them).
- `log_key` is a C2SP vkey. The verifier trusts it only if it was also supplied out of band
  (`--log-key`) or pinned; a bundle that carries its own trust anchor proves nothing, and
  the report says so — `PASS(self-asserted-key)` is a distinct verdict from `PASS`.
- `tsa_tokens[]` are RFC 3161 `TimeStampToken`s over `SHA-256(note text)`, giving the upper
  time bound. Zero tokens → check 5 `SKIP(no-tsa-token)`.
- Checkpoints MUST be listed in ascending `tree_size` with no duplicates.

---

## 4. `consistency_proofs[]`

```jsonc
{ "from_size": 3, "to_size": 5, "path_hex": ["…", "…"] }
```

**A proof MUST be present for every consecutive pair of checkpoints in the bundle.** This
is the check that catches attack **A1** — delete leaf *k*, renumber, recompute every
`link_hash` in one `UPDATE … FROM generate_series`. The link chain recomputes perfectly
after that attack; the consistency proof does not, because the earlier root was already
outside our reach.

A gap in the sequence of pairs is a finding, not a shrug: it is exactly where a rewritten
interval would be hidden.

---

## 5. `leaves[]`

```jsonc
{
  "seq":            3,
  "entry_id":       "018f3a2f-9a01-7e42-8b0d-51f6b2c30d44",
  "entry_kind":     "disposition",
  "subject_id":     "018f3a2f-1104-7c88-b3aa-77c1de40e2b1",
  "payload_ver":    1,
  "canon_bytes_b64":"eyJjaGVja19pZCI6…",
  "payload":        { /* the parsed object, for humans */ },
  "leaf_hash_hex":  "7210abaa…a103",
  "link_hash_hex":  "519a8994…908f",
  "prev_link_hash_hex": "b6934b32…6281",
  "is_sandbox":     false,
  "actor":          "auth0|4f2c",
  "actor_kind":     "human",
  "recorded_at":    "2026-08-07T02:11:42.006Z",
  "batch_id":       "018f3a30-9f00-7a11-8c22-4d5e6f708192"
}
```

Checks this section feeds:

| Member | Check |
|---|---|
| `canon_bytes_b64` + `payload_ver` | **1** — `leaf_hash == SHA-256(0x00 ‖ canon_bytes)`, dispatched on `payload_ver` |
| `seq` | **9** — dense `0..n−1`, no gaps. A gap MEANS tampering, because there is no sequence generator that could have produced one |
| `link_hash_hex`, `prev_link_hash_hex` | **9** — chain recomputation, genesis 32 zero bytes |
| `is_sandbox` | **13** — no leaf in an evidentiary bundle may be `true` |
| `actor`, `actor_kind` | ISO/IEC 27037 chain of custody: every leaf names who, and of what kind |

`payload` is a **convenience rendering** and is never hashed. A verifier that hashes
`payload` instead of `canon_bytes_b64` has tested its own JSON library, not our ledger, and
`trappoint-verify` reports a finding if the two disagree — which is how a substitution
attack (**A3**, swap the payload, leave `canon_bytes`) surfaces as a legible discrepancy
rather than as nothing at all.

`actor_kind` ∈ `human | agent | service | external`. `prev_link_hash_hex` is present on
every leaf including `seq = 0`, where it is 64 zeroes — an explicit genesis beats a special
case, and the `UNIQUE (site_code, prev_link_hash)` constraint that makes a fork impossible
depends on it existing.

---

## 6. `inclusion_proofs[]`

```jsonc
{ "seq": 3, "tree_size": 5, "path_hex": ["…", "…", "…"] }
```

One per leaf, against a `tree_size` that appears in `checkpoints[]`. This is check **2**,
and it is the one that answers *"this was never in the log"* — a proposition nobody can
rebut with a chain, only with a tree.

---

## 7. `receipts[]`

SDR envelopes exactly as in [`receipt.md`](receipt.md) §3. Check **15**: every receipt
verifies, and every receipt whose MMD has expired has its leaf present. A receipt inside
its MMD with no leaf is `SKIP(within-mmd)`; outside, it is a **FAIL naming log
misbehaviour**.

---

## 8. `witness_cosignatures[]`

```jsonc
{
  "tree_size":    5,
  "witness_id":   "witness.icam.example",
  "trust_domain": "regulator",        // regulator | insurer | union_hsr | external_auditor | operator
  "adverse":      true,
  "sig_line":     "— witness.icam.example Bh1q0k…",
  "witness_key":  "witness.icam.example+9a3c11f0+ATzS…",
  "received_at":  "2026-08-07T02:14:31.900Z"
}
```

Check **7** requires ≥ *q* cosignatures over the **same** `(tree_size, root)`, across ≥ *q*
distinct `trust_domain` values, with at least one `adverse: true`. Two signatures from one
domain count once.

> **`adverse` is a claim about legal interest, not a cryptographic property, and the
> verifier says so.** With *q* = 1 over our own infrastructure the verdict is
> `PASS(not-adverse)` — a distinct verdict, printed as such. **Split-view resistance is not
> claimed by this format** and MUST NOT be claimed by any report generated from it until a
> genuinely adverse witness is live.

---

## 9. `schema_attestations[]`

```jsonc
{
  "captured_at":   "2026-08-07T01:58:00.000Z",
  "migration":     "0073_ledger_leaf",
  "object":        "mainline.permit_merge_gate",
  "kind":          "trigger",              // trigger | constraint | function | table
  "definition":    "CREATE TRIGGER permit_merge_gate BEFORE UPDATE ON mainline.permit …",
  "definition_sha256_hex": "…",
  "source":        "pg_get_triggerdef",    // or "SHOW CREATE TABLE" (coarse)
  "leaf_seq":      0
}
```

Check **11**, **the gate is self-attesting**: the trigger definition the database reported
at migration time is inside the ledger, hashed into the tree, under a signed checkpoint. An
exhibit can therefore show not only that a merge was refused, but the **exact source of the
mechanism that refused it**, committed before the incident.

`source` is load-bearing. `GT-05` (whether CockroachDB v26.2 implements
`pg_get_triggerdef()`) is unanswered at the time of freezing. If it is unavailable the
fallback is `SHOW CREATE TABLE`, which loses per-trigger granularity; check 11 then reports
**`PASS(coarse)`** and the claim softens in the same breath. A bundle MUST record which one
produced the text, because a report that cannot tell them apart is a report that overstates
one of them.

---

## 10. `closure_generations[]`

```jsonc
{
  "clause_uuid":   "018f3a30-2200-7d10-9f31-0c9a4e77bb02",
  "as_of_commit":  "018f3a31-0000-7000-8000-000000000001",
  "closure_gen":   2,
  "max_severity":  5,
  "ancestor_count":41,
  "truncated":     false,
  "leaf_seq":      6
}
```

Check **14**, and the reason it exists is adversarial-review finding **S2**: the blame
closure sits under *every* ancestry gate and was, in the reviewed design, mutable,
un-granted, un-ledgered and unguarded. One `UPDATE … SET max_severity = 0` from a Lambda
execution role — the least-protected identity in the architecture — would evaporate every
weakening gate while every dashboard reported full coverage.

The check is: for each `(clause_uuid, as_of_commit)`, generations are **dense from 1** and
`max_severity` is **non-decreasing** across generations. A mass rewrite downward
(attack **A10**) either violates monotonicity or leaves a generation gap, and either way it
is visible offline to someone who has never touched the cluster.

---

## 11. `webauthn_assertions[]`

```jsonc
{
  "disposition_id":     "018f3a2f-1104-7c88-b3aa-77c1de40e2b1",
  "credential_id_b64":  "…",
  "cose_public_key_b64":"…",          // the ENROLLED key, from signing_credential
  "authenticator_data_b64": "…",
  "client_data_json_b64":   "…",
  "signature_b64":      "…",
  "sign_count":         42,
  "uv_required":        true,
  "challenge_inputs": {
    "receipt_digest_hex":  "…",
    "check_id":            "018f3a2f-1104-7c88-b3aa-77c1de40e2b1",
    "defeater_code":       "D-114",
    "rationale_sha256_hex":"…",
    "disposition_kind":    "controlled",
    "gate_epoch":          7
  }
}
```

Check **12** does two things, and the second is the one that matters:

1. The assertion verifies against the **enrolled** COSE key — not against a key carried in
   the assertion.
2. The challenge **reconstructs** from `challenge_inputs`:
   `SHA-256(receipt_digest ‖ check_id ‖ defeater_code ‖ SHA-256(rationale) ‖
   disposition_kind ‖ gate_epoch)`, and equals the challenge inside `client_data_json`.

Property 2 is what refutes *"he signed a summary, not the warning"* by arithmetic:
`receipt_digest` is the Merkle digest of the exact payloads that were rendered to that
person. The human signature becomes as independently checkable as the log signature.

`uv_required: true` means a PIN or biometric was performed — the difference between "a token
was present" and "a person authenticated". A `sign_count` regression is reported as an
**alarm, not a failure**: refusing a safety sign-off because a counter went backwards is an
availability failure at a workface, and this system does not block work on paperwork.

> This section carries personal data. Bundles containing it are produced only under an
> explicit disclosure decision, and `--redact-webauthn` emits the bundle with this section
> replaced by `{"redacted": true, "count": n}` — which downgrades check 12 to
> `SKIP(redacted)` rather than removing the section silently.

---

## 12. `archive`

```jsonc
{
  "bucket":  "mainline-evidence-<account>",
  "objects": [
    { "tree_size": 5, "key": "checkpoints/BLK-07/000005.note",
      "version_id": "3sL4kqtJlcpXroDTDmJ+rmSpXd3dIbrHY+MTRCxf3vjVBH40Nr8X8gdRQBpUMLUo",
      "object_lock_mode": "COMPLIANCE",
      "retain_until": "2033-08-07T02:14:07.000Z",
      "last_modified": "2026-08-07T02:14:09.112Z",
      "etag_hex": "…" }
  ]
}
```

Check **8** compares these against the live object when `--s3` is given, and reports
`SKIP(offline)` otherwise. Offline, the metadata is a **claim by us about our own archive**
and the report labels it as such. Object Lock COMPLIANCE is the control that defeats T2 —
a protected object version cannot be overwritten or deleted by any user, including the root
user — and stating the retention date in the bundle lets a reader see, without any AWS
access, what we have asserted and can therefore be held to.

---

## 13. Determinism

Given the same ledger state, the same tool version and the same selection arguments, bundle
generation MUST be **byte-deterministic**: the same JCS bytes, every time. `generated_at`
is the one exception and MUST be taken from an explicit `--as-of` when determinism is
required. `evidence/reference-ledger/` is regenerated in CI and asserted zero-diff.

This is not tidiness. Evidence Act 1995 (Cth) ss.146–147 grant a presumption that a device
or process which ordinarily produces an outcome did so on the occasion in question; a
generator whose output varies run to run has no "ordinarily" to appeal to.

---

## 14. Vocabulary

The bundle, and every report generated from it, describes itself as *"a record of the
preconditions the database enforced before work was permitted to start."* The strings
**`defence exhibit`**, **`for litigation`** and **`court-ready`** MUST NOT appear in this
format, its implementations, or its output, and a CI grep enforces that across the custody
paths.

This is an admissibility requirement, not a style guide. Evidence Act 1995 (Cth) s.69(3)
and s.147(3) exclude representations prepared in contemplation of a proceeding. **A ledger
built to be evidence is not a business record.** MAINLINE's ledger is operationally
load-bearing by construction — the merge is refused unless the disposition leaf exists — so
its evidentiary value is a consequence. Marketing copy that leads with the exhibit actively
damages the thing it is boasting about.

---

## 15. Conformance

An implementation conforms to `v1.0` if, given `evidence/reference-ledger/bundle.json`, it:

1. verifies every checkpoint note against the supplied log key;
2. recomputes every `leaf_hash` from `canon_bytes_b64` and every `link_hash` from its
   predecessor;
3. verifies every inclusion proof and every consecutive consistency proof;
4. asserts `seq` is dense `0..n−1` and no leaf is `is_sandbox: true`;
5. emits a distinct, named `SKIP` for each absent optional section, and prints
   **`NOT CHECKED`** at the top of any report containing one;
6. produces byte-identical output on two consecutive runs.

---

## References

- [`checkpoint.md`](checkpoint.md), [`receipt.md`](receipt.md), [`refusal.md`](refusal.md)
- `spec/custody/checks.yaml` (the check registry), `spec/custody/attacks.yaml` (A1–A15)
- `spec/custody/evidentiary-map.md`, `spec/custody/threat-model.md`
- RFC 6962 §2.1.1–2.1.2, RFC 8785, RFC 4648 §4
- ARCHITECTURE.md §7.4, §11.4; `research/08-synthesis/review-adversarial.md` S2
