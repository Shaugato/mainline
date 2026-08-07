<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The evidentiary map

**Normative.** A table, not an essay. Every row names a **live artefact** and a **live
test**, and CI fails if either is missing — because a compliance mapping whose right-hand
column is aspirational is the most expensive kind of lie a system like this can tell.

> **Nothing in this file is legal advice, and MAINLINE has not obtained a legal opinion on
> it.** Gate `G0` (a paid consultation with an Australian WHS/safety lawyer) was
> deliberately not sought — see [ADR 0001](../../docs/adr/0001-g0-counsel.md). What this
> file records is the *engineering* the statutes and standards imply, built to the
> conservative reading. A later opinion may narrow it; it will not widen it.

---

## 1. The map

| Standard | Requirement | Artefact | Test |
|---|---|---|---|
| Evidence Act 1995 (Cth) **s.69** | a business record made in the ordinary course of business | the merge is **refused** without a covered disposition leaf — the ledger is what lets work start | `test_k2_exit.py::test_gate_depends_on_ledger` |
| **s.69(3)** / **s.147(3)** | **NOT** prepared in contemplation of a proceeding | vocabulary ruling CU-12, enforced by grep; the gate is load-bearing by construction | `test_k2_exit.py::test_no_litigation_vocabulary` |
| **s.146 / s.147** | the device/process presumption | a deterministic, versioned, third-party-runnable verifier; `canon_src_sha256` in every checkpoint | `test_k2_exit.py::test_verifier_determinism` |
| **ISO/IEC 27037** — acquisition | evidence is acquired without alteration, at the point of collection | client-side RFC 8785 canonicalisation + a Signed Disposition Receipt at intake | `packages/trappoint-ledger/tests/test_receipt.py::test_receipt_roundtrip` |
| **ISO/IEC 27037** — preservation | evidence is protected from alteration after collection | `infra/envs/evidence` — Object Lock COMPLIANCE, versioned, separate account — proven by policy-as-code over the plan JSON | `scripts/custody/check_evidence_plan.py` |
| **ISO/IEC 27037** — chain of custody | who handled the item, when, in what capacity | `actor`, `actor_kind` and the signing credential on every leaf; required fields in the bundle schema | `packages/trappoint-verify/tests/test_structural_checks.py::test_bundle_schema` |
| **ISO/IEC 27042** — reproducibility | an independent analyst reaches the same result | an offline, deterministic, versioned verifier plus a committed reference bundle | `tests/integration/custody/nemesis/test_ledger_attacks.py::test_reference_bundle_verifies` |
| Crimes (Document Destruction) Act 2006 (Vic) | no silent destruction of a document reasonably likely to be required in evidence | row-level TTL allowlist excludes every `ledger_*`; permitted deletion writes a `destruction_record` | `tests/integration/custody/test_k2_exit.py::test_no_ttl_on_ledger` |

---

## 2. The trap that kills most designs, stated plainly

**s.69(3)** excludes representations *"prepared or obtained for the purpose of conducting,
or for or in contemplation of or in connection with, an Australian or overseas
proceeding"*, and **s.147(3)** carries the mirror carve-out.

> **A ledger built to be evidence is not a business record.**

This is an architectural requirement, not a legal footnote. MAINLINE satisfies it **by
construction**: the permit merge is refused unless each recalled precursor's disposition
leaf exists, so the ledger is the thing that lets work start. Its evidentiary value is
incidental to its operational function — which is the correct order, and the only order
that survives s.69(3).

The corollary is a marketing constraint with teeth. **Copy that leads with "defence
exhibit" actively damages admissibility**, because it is discoverable and it is an
admission of purpose. CU-12 therefore fails the build on the strings `defence exhibit`,
`for litigation` and `court-ready` anywhere in the custody paths.

The sentence every artefact uses instead:

> *"This bundle records the preconditions the database enforced before work was permitted
> to start."*

Lead with the gate. The exhibit is a consequence.

---

## 3. Prior art, cited as accepted practice — deliberately

**SQL Server 2022 / Azure SQL Ledger does this shape**: SHA-256 transaction hashing plus
periodic digests pushed to immutable storage. Citing it is not modesty; it is the fastest
way to move the conversation from *"is this a real technique"* to *"is this implementation
sound"*, and the second question is one we can answer.

We are a **superset** of that shape: RFC 6962 Merkle proofs (not just a chain), an RFC 3161
upper time bound, public-beacon lower bounds, external witnesses in adverse trust domains,
and an offline verifier a stranger runs without us.

**Dead end, never proposed:** Amazon QLDB reached end of support 31 July 2025, and AWS's own
migration guidance points to Aurora PostgreSQL, **losing cryptographic verifiability**.
There is currently no AWS-native verifiable ledger service. That is a market gap, not a gap
in this design, and it is worth saying out loud to anyone who asks why we built it.

---

## 4. Retention, hold and destruction

| Rule | Mechanism |
|---|---|
| Row-level TTL is prohibited outside a three-table allowlist | migration-time assertion; no `ledger_*` table is on it |
| Permitted deletion is a reviewed two-person job | writes a `destruction_record` row; the deletion and its authorisation are both in the ledger |
| **Crypto-shredding is document destruction** | the KMS key policy denies `ScheduleKeyDeletion` and `DisableKey` to every principal except a two-person break-glass role, **unconditionally while any `legal_hold` row is open** |
| A recreated key is the same offence committed by accident | the demo/prod split reuses the key across rebuilds; `infra/envs/evidence` has no `destroy` path |

**Class E — evidentiary integrity incident** is a severity class with three rules:
**never silently fix** (a corrected checkpoint is a *new* entry recording the defect, never
a reissued old one — repairing history to make verification pass is the exact behaviour
this product exists to detect); **bound the blast radius in checkpoint terms**, not
wall-clock (*"checkpoints 41 209–41 260 are affected; all others verify"*); **notify within
24 hours**. An integrity incident may involve no personal information at all and still be
the more urgent notification.

---

## 5. What the map does not claim

- Not that a disposition was **sincere**.
- Not that the narrative in an ingested document is **true** (provenance is in scope;
  content authenticity is not).
- Not that any **court has ruled** on a WebAuthn-signed safety record. No such precedent is
  cited anywhere in MAINLINE's materials, because none exists.
- Not that **privilege** attaches to operational records, or that a self-critical-analysis
  privilege exists in Australian law. It does not.
- Not that the person behind a credential was **not coerced**.

---

## References

- Evidence Act 1995 (Cth) ss.69, 146, 147; ALRC Report 102 ch.8 (business records)
- Crimes (Document Destruction) Act 2006 (Vic)
- ISO/IEC 27037 (identification, collection, acquisition, preservation) and ISO/IEC 27042
  (analysis, interpretation, reproducibility)
- ARCHITECTURE.md §11.6; `docs/leads/custody.md` §3; `docs/adr/0001-g0-counsel.md`
