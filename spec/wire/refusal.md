<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Wire format — the refusal payload

**Normative.** TRAPPOINT `1.0.0-rc.1`. Schema: [`refusal.schema.json`](refusal.schema.json)
(JSON Schema draft 2020-12). Media type: `application/vnd.trappoint.refusal+json`.

This is the artefact that makes [`I14`](../invariants/I14-minimal-refusal.md) real. A gate that only
says "no" gets routed around, and an invariant that is routed around is not an invariant. Every
REFUSE-class outcome ([`../errors.md`](../errors.md) §1) is emitted in this shape, by the gate
service to the console, by the diagnoser to the ledger, and by the conformance runner to its report.
All three parse the same bytes.

---

## 1. The shape

```jsonc
{
  "spec_version": "1.0.0-rc.1",
  "refusal_id":   "018f3a2e-6c40-7b21-9c55-2a5c9e0f1b77",
  "observed_at":  "2026-08-04T02:14:07.481Z",
  "profile":      "mainline",

  "class":      "gate",
  "sqlstate":   "23514",
  "constraint": "gate_closed_when_issued",
  "message":    "MAINLINE: merge refused — undispositioned precursor in blame ancestry",

  "subject_kind": "permit",
  "subject_id":   "6f1c7f0e-2b7c-4c0e-9f1b-77a1f0d3c2aa",
  "gate_epoch":   7,

  "diagnosis":   "declarative",
  "probe_calls": 0,

  "mus": [
    { "kind": "obligation", "obligation_id": "3d0b...", "origin": "weaken_over_blood",
      "clause_id": "b21e...", "event_id": "9ac4...", "severity": 5, "virulence": "blood_fatal" }
  ],

  "naa": {
    "kind": "dispose_obligations",
    "cardinality": 1,
    "obligation_ids": ["3d0b..."],
    "legal_kinds": ["applied", "mitigated", "escalated", "emergency_override"],
    "description": "one obligation remains open; four clearance kinds are legal at blood_fatal"
  },
  "naa_reason": null,

  "evidence": [
    { "kind": "ledger_entry", "ref": "mainline:41207", "digest": "sha256:1f3b..." },
    { "kind": "exposure_receipt", "ref": "a71e...", "digest": "sha256:88c0..." }
  ],

  "ext": {}
}
```

---

## 2. Field semantics

| Field | Required | Meaning |
|---|---|---|
| `spec_version` | yes | the TRAPPOINT version whose contract this payload claims to satisfy |
| `refusal_id` | yes | UUID minted by the emitter; the ledger key for this refusal |
| `observed_at` | yes | RFC 3339 UTC instant at which the refusal was observed by the emitter |
| `profile` | no | conformance profile the emitting deployment claims |
| `class` | yes | always `"gate"` — only REFUSE-class outcomes are payloads (`errors.md` §5) |
| `sqlstate` | yes | one of `23514`, `23503`, `23505`, `P0001` |
| `constraint` | yes | the **exhibit name**, per `errors.md` §3.1; never empty, never inferred silently |
| `constraint_source` | no | `"reported"` when taken from the driver's diagnostics, `"parsed"` when recovered from the message — a `"parsed"` payload is a **weakened diagnosis** and consumers MUST render it as such |
| `message` | yes | the database's message, verbatim, including its `MAINLINE:` / `TRAPPOINT:` prefix |
| `subject_kind` | yes | the gated subject kind, as declared in the binding (`permit`, `change_request`, …) |
| `subject_id` | yes | the subject's UUID |
| `gate_epoch` | yes | the subject's epoch **at the moment of refusal**; a payload without it cannot be replayed |
| `diagnosis` | yes | `"declarative"`, `"quickxplain"` or `"none"` — how the MUS was obtained |
| `probe_calls` | yes | oracle calls consumed; `0` for a declarative diagnosis |
| `mus` | yes | the minimal unsatisfiable subset (§3) |
| `naa` | yes | the nearest admissible alternative, or `null` (§4) |
| `naa_reason` | conditional | REQUIRED and non-null when `naa` is `null`; MUST be `null` otherwise |
| `evidence` | yes | pointers a third party can follow; MAY be empty |
| `ext` | no | vertical-specific extension object; the substrate never reads it |

`additionalProperties` is `false` at every level. A new top-level field is a MINOR bump when
optional; making one required is MAJOR.

---

## 3. `mus` — the minimal unsatisfiable subset

`mus` is the **irreducible** set of facts whose joint presence caused the refusal: remove any one
element and the transition would have been admissible; remove none and it would not.

Atoms are tagged by `kind`, over the four fact families the specification recognises plus the
obligation family that carries them:

| `kind` | Required fields | Means |
|---|---|---|
| `obligation` | `obligation_id` | an open obligation; the most common atom |
| `clause` | `clause_id` | a cited clause whose ancestry armed the gate |
| `event` | `event_id` | a precursor event bonded into the ancestry |
| `authority_gap` | `relation`, `key` | the authority source holds **no row** for this key — the gate failed closed |
| `capability_gap` | `capability`, `detail` | a required verdict does not exist at this classification, or a required signer/credential/predicate property is absent |

Normative rules:

- **M-1.** `mus` MUST be non-empty for `sqlstate` in `{23514, 23503, 23505}`. For `P0001` it MAY be
  a single `authority_gap` or `capability_gap` atom, and MUST NOT be empty.
- **M-2.** `mus` MUST be **minimal**: no proper subset of it is unsatisfiable. Where minimality could
  not be established within the probe budget, the emitter MUST set `diagnosis` to `"none"` and
  `naa` to `null` with `naa_reason = "probe_budget_exhausted"` rather than emit a non-minimal set
  labelled as a MUS.
- **M-3.** Atom order is not significant; consumers MUST NOT depend on it. Emitters SHOULD sort by
  `kind` then identifier so payloads are byte-stable for snapshotting.
- **M-4.** No atom may carry a score, rating, threshold, ranking or characterisation of a **named
  human**. `signer_sub` MAY appear as a fact (*who signed*), never as a measure
  ([`I15`](../invariants/I15-allegation-firewall.md)).

### 3.1 Where the MUS comes from

The primary algorithm is **declarative decomposition**: the refused constraint maps to the projected
counter behind it, and the counter's witness rows *are* the MUS. It is deterministic, needs no probe,
and covers every single-counter refusal.

The general algorithm is **QuickXplain over savepoint probes**, using the database itself as the
oracle: `SAVEPOINT p; <apply candidate subset>; <attempt the transition>; ROLLBACK TO SAVEPOINT p`.
Because the oracle is the same constraint engine that produced the refusal, the explanation **cannot
disagree with the refusal**. That is the entire point.

Two safety rules that are part of this wire contract because a consumer relies on them:

- the probe transaction is **separate** from the gate transaction and is rolled back unconditionally;
  a diagnosis can never mutate the gate;
- probing never happens on the merge path, and the budget is bounded (`probe_calls` reports it).

---

## 4. `naa` — the nearest admissible alternative

`naa` is the **minimum-cardinality** change to the attempted history that restores admissibility. It
is advice, not authority: acting on it still goes through the gate.

| `kind` | Fields | Means |
|---|---|---|
| `dispose_obligations` | `obligation_ids`, `cardinality`, `legal_kinds` | dispose exactly these obligations; these verdict kinds are legal at this classification |
| `substitute_kind` | `legal_kinds` | the attempted verdict is not legal here; these are |
| `supply_evidence` | `required`, `cardinality` | a required property is absent — a countersigner, a compensating control, a bounded predicate, a verbatim anchor |
| `materialise_authority` | `relation`, `key` | the authority source must hold a row for this key before the transition can be evaluated at all |
| `fork_subject` | `parent_subject_id` | the subject is completed and pinned; the only admissible path is a child subject |

**`naa` MUST be `null`** — with `naa_reason` set — when no admissible alternative is computable.
Legal reasons, closed set:

| `naa_reason` | Means |
|---|---|
| `probe_budget_exhausted` | the oracle budget ran out before a minimal alternative was found |
| `no_legal_verdict_exists` | **the important one**: at this ancestral severity the verdict set is empty by design; there is no disposition constructor that clears it |
| `requires_human_authority` | the alternative exists but requires an authority the requester does not hold; naming it would be advice to impersonate |
| `not_computable` | the refusal is outside the declarative decomposition and probing is unavailable |

`no_legal_verdict_exists` is not a failure of the diagnoser. It is the product working: *there is no
way to sign this away.* A consumer MUST render it as a statement about the rule, never as a defect.

---

## 5. `evidence`

Pointers a third party can follow without our cooperation. Each item is
`{ kind, ref, digest? }` with `kind` drawn from an open vocabulary; the substrate defines
`ledger_entry`, `exposure_receipt`, `checkpoint`, `object_lock` and `migration_attestation`. A
vertical MAY add kinds; consumers MUST ignore kinds they do not know.

`digest` is a prefixed multihash-style string (`sha256:<hex>`). Payload consumers MUST NOT treat a
digest as verified merely because it is present.

---

## 6. Consumer obligations

- **C-1.** A consumer MUST NOT retry on receipt of a payload; a payload only exists for REFUSE-class
  outcomes, and those are attempted exactly once, ever.
- **C-2.** A consumer MUST render `constraint` verbatim. Prettifying, translating or mapping it to a
  friendlier phrase destroys the exhibit.
- **C-3.** A consumer that persists a payload MUST persist it append-only, with the constraint name
  stored verbatim.
- **C-4.** A consumer MUST treat `constraint_source = "parsed"` as a weakened diagnosis and say so in
  its own output.
- **C-5.** A consumer MUST NOT synthesise a payload for an outcome the database did not produce. A
  refusal that did not happen has no diagnosis, and a fabricated one is the worst artefact this
  system could emit.

---

## 7. Stability

The payload is versioned by `spec_version`. Adding an optional field or an `naa.kind` is MINOR.
Adding a required field, removing a field, changing a field's type, or adding an `naa_reason` value
that existing consumers must handle is **MAJOR**. Message text is PATCH.
