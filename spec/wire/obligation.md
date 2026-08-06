<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Wire format — the obligation record

**Normative.** TRAPPOINT `1.0.0-rc.1`. Media type: `application/vnd.trappoint.obligation+json`.

An **obligation** is the materialised claim that a gated subject may not complete until this
particular thing has been disposed of. In the database it is a row; on the wire it is this record.
Three consumers read it — the console that shows a signer what they are being asked to sign, the
recall pipeline that proposes it, and the conformance runner that asserts it — and the differences
between what those three may *write* are the whole content of this document.

---

## 1. The record

```jsonc
{
  "spec_version": "1.0.0-rc.1",
  "obligation_id": "3d0b6b17-6c3a-4d6b-a0f4-8e5b0a9d1c22",

  "subject_kind": "permit",
  "subject_id":   "6f1c7f0e-2b7c-4c0e-9f1b-77a1f0d3c2aa",
  "site_id":      "1b0e4b2a-2b1e-4b7c-8e0a-2b6c5d4e3f10",

  "clause_id":  "b21e9a7c-5d4e-4a3b-9c2d-1e0f8a7b6c5d",
  "commit_id":  "9f2c1b0a7e6d5c4b3a291807f6e5d4c3b2a19087",
  "precursor_event_id": "9ac4f1d2-3b4c-4d5e-8f90-1a2b3c4d5e6f",

  "origin": "weaken_over_blood",
  "control_delta": "weaken",

  "severity":    5,
  "virulence":   "blood_fatal",
  "closure_gen": 41,
  "projection_source": "mainline.clause_blame_current",

  "evidence_summary": "control weakened over blame ancestry holding severity 5",
  "materialised_at":  "2026-08-04T02:11:53.204Z",
  "dedupe_key": "sha256:4b1c...",

  "state": "open",
  "disposition_id": null,
  "gate_epoch_at_materialisation": 7,

  "ext": {}
}
```

---

## 2. Field semantics, and who may write each

The column headed **Producer may set** is the load-bearing one. It is the wire-level statement of
[`I02`](../invariants/I02-projected-refusal.md): the classification of an obligation is a
**projection**, never an input.

| Field | Type | Producer may set | Notes |
|---|---|---|---|
| `spec_version` | semver string | yes | contract version |
| `obligation_id` | uuid | no — server-assigned | |
| `subject_kind` | identifier | **yes** | must be a kind declared in the binding |
| `subject_id` | uuid | **yes** | exactly one subject reference is legal |
| `site_id` | uuid | **yes** | tenancy scope |
| `clause_id` | uuid | **yes** | the cited clause |
| `commit_id` | hex string | **yes** | the clause **version**; the pair is a foreign key |
| `precursor_event_id` | uuid or null | **yes** | null is legal and is *not* an absence of cause |
| `origin` | identifier | **yes** | closed per binding, e.g. `weaken_over_blood` |
| `control_delta` | identifier or null | **yes** | the edit's direction, where one applies |
| `severity` | integer 0–5 | **NO — projected** | overwritten from the authority source |
| `virulence` | identifier | **NO — projected** | overwritten from the authority source |
| `closure_gen` | integer | **NO — projected** | which generation of the authority source armed it |
| `projection_source` | identifier | no — server-set | the relation the three projections came from |
| `evidence_summary` | string | **yes** | human-readable justification |
| `materialised_at` | RFC 3339 | no — **server clock** | a client-supplied time is a reconstructed timestamp and is refused |
| `dedupe_key` | digest | no — derived | the idempotency key (§4) |
| `state` | enum | no — derived | `open` · `dispositioned` · `retracted` · `expired` |
| `disposition_id` | uuid or null | no — derived | the live disposition, if any |
| `gate_epoch_at_materialisation` | integer | no — server-set | the epoch this obligation pushed the subject to |
| `ext` | object | **yes** | vertical extension; never read by the substrate |

### 2.1 The projection rule, stated as a wire obligation

- **O-1.** A producer MUST NOT rely on `severity`, `virulence` or `closure_gen` surviving the write.
  It MAY send them; the database overwrites them from the declared authority source regardless of
  what was sent, and regardless of whether the sent value agrees.
- **O-2.** A consumer MUST treat the values returned by the database as authoritative and the values
  it sent as advisory. Where the two disagree, the disagreement is a fact worth logging and is
  **never** an error.
- **O-3.** When the authority source holds no row for `(clause_id, commit_id)`, the insert is refused
  with `P0001` naming the projection trigger. **An obligation whose severity cannot be established is
  not an obligation of unknown severity; it is not insertable.** Absence of evidence refuses.
- **O-4.** `materialised_at` is the server clock. A queue-and-sync design that manufactures
  obligations with reconstructed timestamps is non-conformant, because a reconstructed timestamp on
  an evidentiary row is the single worst artefact this system could produce.

---

## 3. State, and how it changes

```
            materialise                 dispose                    retract
   (none) ─────────────► open ──────────────────► dispositioned ──────────────► open
                          │                            │        (gate_epoch++)
                          │ disposition expires        │
                          └──────────◄─────────────────┘
                                   expired
```

Normative:

- **S-1.** `state` is **derived**, never written. A producer that sets it is sending a value the
  database ignores.
- **S-2.** `open → dispositioned` requires a live disposition whose `(receipt, obligation)` pair was
  materialised to that actor in that transaction ([`I09`](../invariants/I09-exposure-binding.md)).
- **S-3.** `dispositioned → open` by retraction MUST increment the subject's `gate_epoch`. A
  retraction after the subject has completed is refused by the epoch pin — `23503` — which is the
  correct answer, not a bug.
- **S-4.** `dispositioned → expired` happens by the passage of time and **re-blocks**. Expiry MUST
  NOT be implemented as a de-escalation: an expired disposition leaves the obligation open, never
  silently cleared ([`I12`](../invariants/I12-no-decay-without-evidence.md)).
- **S-5.** An obligation is never deleted. Row-level TTL MUST NOT be applied to the obligation table.

---

## 4. `dedupe_key` and idempotence

Most obligation noise is *repetition*, not wrongness: the same precursor firing on the fortieth
materially identical subject. Deduplication is therefore a first-class part of the record, and it is
a **digest**, not a unique index over nullable columns — because NULLs are distinct in a unique
index, so a naive `ON CONFLICT DO NOTHING` silently fails to dedupe every origin whose
`precursor_event_id` is null.

**D-1.** `dedupe_key` is the digest of the tuple

```
subject_reference | clause_id | commit_id | precursor_event_id | origin
```

with a fixed sentinel (`-`) substituted for each null component, under SHA-256.

**D-2.** The obligation table carries `UNIQUE (dedupe_key)`, and a duplicate materialisation is
**absorbed**, not refused: the second insert affects zero rows and the subject's counters do not
move. This is an ADMIT-class outcome, and conformance case `CF-11` asserts it.

**D-3.** Absorption MUST NOT be implemented by a pre-read (`SELECT` then `INSERT`), which is a race.
It is a single statement whose conflict target is the digest.

**D-4.** Where the platform cannot compute the digest in a stored generated column, the binding
selects the client-computed fallback (`capabilities.stored_digest = "client_computed"`), the column
carries a length `CHECK`, and the claim weakens from *"the server computes the key, the inserter
cannot lie"* to *"the trigger verifies the key the inserter supplied"*. The invariant survives; the
sentence changes; both are written down in the same commit.

---

## 5. What an obligation record deliberately does not carry

- **No score, rating or characterisation of a named human.** Not the proposer's, not the signer's,
  not the original author's. `signer_sub` is a fact about who acted, never a measure
  ([`I15`](../invariants/I15-allegation-firewall.md)).
- **No recommendation of a disposition kind.** Suggesting the verdict is the one thing a memory
  system must not do; the legal kinds come from the typed clearance table and the choice is a human
  act with a signature attached.
- **No confidence score presented as a threshold.** A retrieval's arithmetic belongs in the silence
  ledger ([`I13`](../invariants/I13-silence-logged.md)), where it is recorded with its inputs, not on
  the obligation where it would look like a licence to ignore.
- **No free-form status.** `state` is derived from rows, so it cannot drift from them.

---

## 6. Stability

Adding an optional field or a new `origin` value is MINOR. Changing which fields a producer may set,
adding a required field, or altering the `dedupe_key` tuple is **MAJOR** — the last of those changes
the identity of every obligation ever materialised.
