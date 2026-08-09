<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Wire format — the candidate commitment (Proof of Exhausted Recall)

**Normative. Version `v1`, frozen 2026-08-08.** Media type:
`application/vnd.trappoint.per-receipt+json`. Reference implementation:
`packages/trappoint-recall/src/trappoint_recall/per/`. Reference verifier:
**`python -m trappoint_recall.per`** — that invocation is the normative one and is asserted end
to end, on an interpreter started with `-S` so that no installed distribution is reachable, by
`tests/integration/recall_run/test_per_verifier.py`. The console-script alias
`trappoint-recall-verify-per` is declared in the distribution's `[project.scripts]`; where that
declaration is absent the same test reports a skip naming it, because a published command that
does not resolve is a claim this document is not entitled to make.

This document is what an opposing expert implements from — plausibly in Rust, plausibly
hostile, certainly without asking us anything. Everything in it is specified to the byte for
that reason.

The key words MUST, MUST NOT, REQUIRED, SHOULD, SHOULD NOT and MAY are to be interpreted as in
BCP 14 (RFC 2119, RFC 8174).

---

## 1. The bound — read this before anything else

> **PER proves exhaustion of the retrieval that ran, not of the corpus.**

That sentence is reproduced **verbatim** in `packages/trappoint-recall/src/trappoint_recall/
per/receipt.py` (as `PER_BOUND_SENTENCE`), in every receipt this format defines (field
`claim_bound`) and in every verifier report. A change to its wording is a change to what the
product claims and requires an ADR.

`tests/integration/recall_run/test_claim_bound_grep.py` is the grep. It anchors on the two words
that open the claim and then works in two rings. Inside the recall domain — this directory,
`packages/trappoint-recall/` and the recall agent — the sentence must appear byte for byte.
Everywhere else in the repository, whatever follows that anchor must still be **this** claim
once case, whitespace and markdown emphasis are folded away: another domain may shout the
emphasis in its own medium, but it may not change what is being asserted. The realistic failure
is not that someone deletes the caveat; it is that someone rewrites it. Any artefact outside this
domain that *names* Proof of Exhausted Recall in prose owes the verbatim sentence; where such an
artefact does not exist yet, the grep reports a skip with its reason rather than a pass.

One consequence, stated so the next editor does not trip over it: **prose in this document may
not quote the anchor words on their own.** The grep is deliberately dumb — a dumb grep is a
grep that cannot be argued with — so a sentence *about* the claim reads to it exactly like a
sentence *making* the claim.

C-SPANN is an approximate index and its trees mutate on every insert. A receipt therefore
carries `index_generation`, and the run it belongs to carries `index_plan_digest` and an M4
CUE HORIZON coverage certificate, precisely so that the reach of the retrieval is a stated,
checkable quantity rather than an implied one. **A proof that overclaims is worse than none.**

What PER *does* establish, exactly:

1. the candidate multiset was committed, score-sorted, to a root fixed at run time;
2. the cut at `theta` is where the receipt says it is, proved against that root;
3. no candidate can have been removed, inserted, reordered or re-scored after the fact
   without changing the root — because every leaf carries its own ordinal;
4. `tau` was fixed before the run, under a policy anchored inside a cosigned checkpoint
   (MI18, `fn_recall_policy_anchored`).

What it does not establish: that the corpus held nothing else.

---

## 2. Quantisation

Let `p` be a candidate's calibrated `p_relevant` and `t` its applied `tau`, each an IEEE-754
binary64 in `[0, 1]`.

```
score_q      = Q(p)
tau_applied  = Q(t)

Q(x) = round_half_up( exact_value_of(x) * 1_000_000 )
```

`exact_value_of(x)` is the **exact rational value of the binary64**, not its shortest decimal
rendering. `round_half_up` rounds a value ending in exactly one half **away from zero**; since
`x >= 0` here, that is toward `+infinity`.

> Implementers: this is `Decimal(x) * 1000000` quantised with `ROUND_HALF_UP` in Python,
> `BigDecimal::from(x).mul(1e6).round(RoundingMode::HalfUp)` in a Rust `bigdecimal`, and
> **not** `(x * 1e6).round()` in any language — that rounds the product of two approximations.

The result MUST be an integer in `[0, 1_000_000]`. A value outside that range is a malformed
leaf and the receipt MUST be rejected.

**Why integers.** `score_q` is the sort key of the entire proof. Two implementations that
disagreed about the text of a float — `0.35` versus `0.35000000000000003` — would produce
different leaf hashes, and a receipt nobody else can reproduce is not evidence. `tau_applied`
is quantised the same way because the custody evidentiary payload profile (ruling CU-5)
refuses binary floats in a hashed preimage, and a leaf that is canonicalisable under one
profile and not the other is a trap for whoever wires PER into the ledger next.

`silence_receipt.theta` is a `FLOAT8` for human display and is **not** authoritative. The
receipt's `theta_q` integer is. A verifier MUST check `|theta - theta_q / 1e6| < 1e-9` and MUST
use `theta_q` for every comparison.

---

## 3. The leaf

### 3.1 Preimage

```
leaf_object = { "ord": <int>, "event_id": <string>, "score_q": <int>,
                "tau_applied": <int>, "outcome": <string> }
```

| Member | Type | Constraint |
|---|---|---|
| `ord` | integer | 1-based position in the committed sequence, `1 <= ord <= n` |
| `event_id` | string | `mainline.event.event_id` as **lowercase** RFC 4122 text, `8-4-4-4-12` |
| `score_q` | integer | `Q(p_relevant)`, `0 <= score_q <= 1000000` |
| `tau_applied` | integer | `Q(tau_applied)`, `0 <= tau_applied <= 1000000` |
| `outcome` | string | one of `blocking`, `advisory`, `silenced`, `deduped` |

Exactly these five members. An object with a sixth member, or a missing member, is malformed
and MUST be rejected — an extra member changes the hash and would let a writer smuggle a
distinguishing field past a verifier that ignored it.

`ord` is *inside* the preimage. That is the whole anti-excision mechanism: deleting leaf *k*
renumbers every leaf after it, changing `n - k` leaf hashes and therefore the root.

### 3.2 Canonicalisation

`canon_bytes = JCS(leaf_object)` — RFC 8785, restricted to a flat object of integer and string
members:

* members are ordered by **UTF-16 code unit** of the member name (RFC 8785 §3.2.3);
* integers are rendered as ECMAScript `Number.prototype.toString` would, which for the range
  permitted here is plain decimal with no sign, no leading zero and no exponent;
* strings are minimally escaped: `"` → `\"`, `\` → `\\`, U+0008 → `\b`, U+0009 → `\t`,
  U+000A → `\n`, U+000C → `\f`, U+000D → `\r`, any other code point below U+0020 → `\u00xx`
  with **lowercase** hex, everything else literal UTF-8;
* no whitespace anywhere.

With the five member names above, the emitted order is fixed and is:

```
{"event_id":…,"ord":…,"outcome":…,"score_q":…,"tau_applied":…}
```

Worked example — `ord=7`, `event_id=0f4a3b21-8c5d-4e6f-9a0b-1c2d3e4f5061`, `score_q=451200`,
`tau_applied=450000`, `outcome=silenced`:

```
{"event_id":"0f4a3b21-8c5d-4e6f-9a0b-1c2d3e4f5061","ord":7,"outcome":"silenced","score_q":451200,"tau_applied":450000}
```

### 3.3 Leaf hash

```
leaf_hash = SHA-256( 0x00 || canon_bytes )
```

RFC 6962 §2.1 leaf domain separation, identical to the custody ledger's
`leaf_hash = SHA-256(0x00 || canon_bytes)` (`spec/custody/ledger-schema.md` §6), so a PER leaf
and a ledger leaf can never be confused for one another inside the same tree.

---

## 4. Commitment order

The committed sequence is the candidate set sorted by:

```
1.  score_q   DESCENDING
2.  event_id  ASCENDING   (byte order of the lowercase RFC 4122 text)
```

`ord` is then assigned `1..n` over that order.

The tie-break is normative, not incidental. Two candidates that quantise to the same `score_q`
would otherwise be ordered by whatever the retrieval happened to emit, and a receipt rebuilt
from `mainline_meas.recall_candidate` on a later day would produce a different root for the
same set. A verifier MUST reject a disclosed set that is not in this order.

`event_id` MUST appear at most once. `mainline_meas.recall_candidate` is keyed
`(run_id, event_id)`; a candidate found by three channels is one candidate, and counting it
more than once would break `candidates_conserved` (MI17).

---

## 5. The Merkle tree

RFC 6962 §2.1, verbatim:

```
MTH({})      = SHA-256()                                  -- the empty string
MTH({d(0)})  = leaf_hash(0)
MTH(D[n])    = SHA-256( 0x01 || MTH(D[0:k]) || MTH(D[k:n]) )
               where k is the largest power of two STRICTLY LESS THAN n
```

`candidate_root = MTH(leaf_hashes)`, 32 bytes, stored in
`mainline_meas.silence_receipt.candidate_root` and carried on the wire as lowercase hex.

Audit paths are RFC 6962 §2.1.1 `PATH(m, D[n])`. Verification is RFC 6962 §2.1.1's algorithm,
which consumes **both** the leaf index and the tree size to decide, at each level, whether the
sibling is applied on the left or the right. A path issued for index *i* therefore does not
verify at index *i+1*; that index-dependence is what the boundary disclosure rests on and it
is asserted directly in `tests/integration/recall_run/test_boundary_proof.py`.

---

## 6. `theta`, `s` and `n`

```
n        = the number of committed leaves
theta_q  = min { score_q : outcome in {blocking, advisory} }        if any were raised
         = 1 + max { score_q }                                      if none were raised
         = 0                                                        if n = 0
s        = | { leaf : leaf.score_q >= theta_q } |
```

Because the sequence is score-sorted, that set is a prefix and `s` is a position.
`0 <= s <= n` — the same statement as `mainline_meas.silence_receipt`'s `boundary_sane` CHECK.

**`theta` is the lowest score the system actually showed a human.** It is deliberately *not*
"the threshold": Severity-Graded Admission applies a different `tau` per severity
(`tau(5)=0.35 … tau(1)=0.85`, calibrated), so no single number describes the admission rule and
publishing one as if it did would be exactly the species of overclaim this mechanism exists to
refuse. Each leaf carries its own `tau_applied`, so the severity-graded arithmetic stays
auditable per candidate.

The claim the receipt makes is therefore precisely: **every leaf beyond position `s` scored
below `theta`** — below the lowest score that reached anybody. It is checkable, and it is true.

A writer MUST NOT emit a receipt in which a `blocking` or `advisory` leaf has `ord > s`. Such a
receipt would assert that everything past `s` was below the display floor while having
displayed one of those items.

---

## 7. The boundary proof

```json
"boundary_proof": {
  "leaf_at_s":       { "index": <int>, "leaf": <leaf_object>, "path": [<hex>, …] },
  "leaf_at_s_plus_1": { "index": <int>, "leaf": <leaf_object>, "path": [<hex>, …] }
}
```

* `index` is **0-based**: `index = ord - 1`.
* `path` is the RFC 6962 audit path, leaf-most sibling first, each entry 64 lowercase hex
  characters.
* `leaf_at_s` is `null` if and only if `s = 0` (nothing was raised, so there is no leaf at the
  cut). `leaf_at_s_plus_1` is `null` if and only if `s = n` (nothing lies beyond the cut).
  Absent halves MUST be present as JSON `null` rather than omitted: which half is missing is
  information about the run.

Disclosing this pair, and only this pair, is what makes PER a **privilege log rather than a
disclosure**. It establishes where the cut is without revealing a single suppressed candidate's
identity, text or score. A privilege log that had to publish the privileged material would not
be a privilege log.

---

## 8. The receipt object

```json
{
  "per_version": 1,
  "run_id": "<uuid>",
  "permit_id": "<uuid>",
  "policy_version": "<string>",
  "index_generation": "<string>",
  "corpus_root": "<64 hex>",
  "candidate_root": "<64 hex>",
  "theta": <float>,
  "theta_q": <int>,
  "s": <int>,
  "n": <int>,
  "boundary_proof": { … },
  "certificate_verdict": "complete" | "partial" | "UNDETERMINED",
  "not_exhaustive": <bool>,
  "claim_bound": "PER proves exhaustion of the retrieval that ran, not of the corpus."
}
```

`per_version` MUST be `1`. A verifier that does not implement a version it is handed MUST
refuse rather than guess at another profile's leaf encoding.

`certificate_verdict` is the M4 CUE HORIZON verdict for the run
(`mainline_meas.recall_certificate.verdict`).

**`certificate_verdict = "UNDETERMINED"` REQUIRES `not_exhaustive = true`.** Where coverage
cannot be certified, the reach of the retrieval is unknown and PER may not claim exhaustion of
it. The reference builder refuses to construct such a receipt otherwise, and a verifier MUST
fail the `exhaustion_claim_bounded` check on one that reaches it anyway.

---

## 9. Verification

### 9.1 Boundary mode — the receipt alone

This is what an opposing expert, a regulator or an insurer receives.

1. `per_version` is implemented.
2. `0 <= s <= n`.
3. `|theta - theta_q / 1e6| < 1e-9`.
4. Each boundary half is present exactly when its ordinal lies in `1..n`.
5. For each present half: `leaf.ord == expected_ordinal` and `index == expected_ordinal - 1`.
6. `leaf_at_s.score_q >= theta_q`; `leaf_at_s_plus_1.score_q < theta_q`.
7. Each present half's audit path verifies `leaf_hash(leaf)` at `(index, n)` against
   `candidate_root`.
8. `certificate_verdict != "UNDETERMINED"` or `not_exhaustive` is true.

### 9.2 Full mode — with the disclosed candidate set

This is what a discovery order produces: the `mainline_meas.recall_candidate` rows.

Everything in §9.1, plus:

9. the disclosed set has exactly `n` entries;
10. ordinals are `1..n` contiguous;
11. the set is in the commitment order of §4;
12. every `event_id` appears once;
13. `MTH` over the recomputed leaf hashes equals `candidate_root`;
14. `s` equals the number of leaves with `score_q >= theta_q`;
15. no `blocking` or `advisory` leaf has `ord > s`;
16. `theta_q` equals the §6 derivation over the disclosed set;
17. each disclosed boundary leaf equals the entry at its ordinal in the set.

**Removing one candidate fails 9, 13, 14 and 17.** That is the property `done_when` names, and
it is asserted in `tests/integration/recall_run/test_per_verifier.py`.

A verifier MUST report every check rather than stopping at the first failure. A verifier handed
a hostile bundle that crashed would be telling its operator nothing, and "the receipt is
malformed" is itself a finding.

---

## 10. Dependency floor

The reference verifier imports the **Python standard library and nothing else** — not
`pydantic`, not `cryptography`, not `trappoint_jcs`. This is a requirement of the format, not
a property of one implementation: the person this artefact is for does not trust us, so the
tool they check it with cannot be ours to change.

`tests/integration/recall_run/test_leaf_canon_agrees_with_jcs.py` canonicalises randomised
leaves with both the restricted canonicaliser in `trappoint_recall.per.canon` and the full
RFC 8785 implementation in `trappoint_jcs`, and asserts the bytes are identical. The narrow
implementation is narrow, not different.

---

## 11. Extending this format

Additive, optional members MAY be added to the **receipt object** (§8) at any time; a verifier
MUST ignore members it does not recognise there.

The **leaf object** (§3.1) MUST NOT be extended. Adding a member changes every historical leaf
hash, which is a migration of evidence rather than of data. A new leaf shape is a new
`per_version` with its own domain tag, shipped alongside the old one, and every historical
version is retained forever — the same discipline `spec/custody/canon-registry.yaml` applies to
the canonicalisers.
