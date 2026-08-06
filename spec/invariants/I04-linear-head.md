<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I04 — Linear head

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** kernel; every event chain and ledger
- **MAINLINE schema invariants that instantiate it:** `MI02`, `MI09`, `MI10`, `MI24`
- **Conformance cases:** 10 (9 on the reference profile)

---

## NORMATIVE STATEMENT

**A subject's history MUST be a chain, not a tree, enforced by a compare-and-swap that holds even if
isolation is downgraded.**

- Each event row MUST declare the sequence position it extends (`prev_seq`) and MUST be constrained
  by `UNIQUE (subject_id, prev_seq)`. Two writers extending the same head MUST collide.
- Sequence positions MUST be **derived inside the transaction**. `CREATE SEQUENCE`, `nextval()`,
  `SERIAL` and `unique_rowid()` MUST NOT appear anywhere in a conformant implementation: sequence
  allocations commit immediately and are not rolled back, so a sequence gap means nothing and cannot
  be evidence of anything. **A gap in a conformant chain MUST mean tampering.**
- Each event MUST carry the digest of its predecessor, and the predecessor digest MUST be
  **verified** against the stored predecessor by trigger, not trusted from the writer.
- At most one completion record per subject MUST be enforced by primary key.
- The linearity guarantee MUST NOT depend on the isolation level.

---

## MECHANISM

| Role | SQL object |
|---|---|
| the CAS | `linear` — `UNIQUE (permit_id, prev_seq)`; `cr_linear` on the change-request chain |
| one completion | `merge_record_pkey` — `PRIMARY KEY (subject_kind, subject_id)` |
| chain verification | `fn_permit_event_chain()` / `fn_cr_event_chain()` — refuse when the declared predecessor is absent or its digest disagrees |
| the server-side chain | a generated `chain_digest` column over the normalised payload |
| the ledger CAS | `PRIMARY KEY (site_code, seq)` with `seq` derived in-transaction |
| the ban | a repository lint failing on `CREATE SEQUENCE`, `nextval(`, `SERIAL`, `unique_rowid()` in any migration or rendered template |

The generated chain digest is **not** the evidentiary hash: a third party cannot reproduce the
database's own key ordering. The evidentiary hash lives in the custody ledger under RFC 8785 JCS,
client-side. Both exist because they fail differently.

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| two events extending the same head | `23505` | `linear` (or `cr_linear`) |
| two completion records for one subject | `23505` | `merge_record_pkey` |
| two ledger leaves at one position | `23505` | `ledger_leaf_pkey` |
| an event whose predecessor digest disagrees | `P0001` | `mainline.fn_permit_event_chain` |
| an event naming a predecessor that does not exist | `P0001` | `mainline.fn_permit_event_chain` |
| N parallel completions | exactly one succeeds; losers `23505` | `merge_record_pkey` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-09`](../conformance/manifest.toml) | Merge the same subject twice | `23505` | `merge_record_pkey` | both | 2 |
| [`CF-13`](../conformance/manifest.toml) | Transition a permit straight from draft to merged | `23503` | `legal_edge` | both | 1 |
| [`CF-14`](../conformance/manifest.toml) | Two permit_event rows appended from the same head | `23505` | `linear` | both | 1 |
| [`CF-15`](../conformance/manifest.toml) | Two cr_event rows appended from the same head | `23505` | `cr_linear` | both | 1 |
| [`CF-16`](../conformance/manifest.toml) | Append a permit_event whose prev_digest does not match the predecessor's chain_digest | `P0001` | `mainline.fn_permit_event_chain` | both | 1 |
| [`CF-17`](../conformance/manifest.toml) | Append a permit_event declaring a prev_seq with no predecessor row | `P0001` | `mainline.fn_permit_event_chain` | both | 1 |
| [`CF-44`](../conformance/manifest.toml) | N parallel merges of one permit yield exactly one merge record | `23505` | `merge_record_pkey` | both | 2 |
| [`CF-45`](../conformance/manifest.toml) | Run the entire gate history at READ COMMITTED | `23514` | `gate_closed_when_issued` | both | 2 |
| [`CF-46`](../conformance/manifest.toml) | Reconstruct the subject's state at a past instant from the event chain, and prove AS OF SYSTEM TIME cannot reach it | `00000` | `mainline.permit_event.chain_digest` | both | 1 |
| [`CF-63`](../conformance/manifest.toml) | Write two ledger leaves at the same sequence position | `23505` | `ledger_leaf_pkey` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **A hash chain inside a database the adversary owns is a checksum, not evidence.** This invariant
  makes the chain *internally* consistent and fork-free. What makes it evidence is a signed
  checkpoint leaving the trust boundary, which is a different layer with a different specification.
- **It does not claim gap-freeness proves nothing was hidden.** It proves nothing was *removed from
  the middle*. A fact never written was never in the chain, and this invariant is silent about it —
  which is precisely why the silence ledger ([`I13`](I13-silence-logged.md)) exists.
- **It does not claim ordering is time.** The sequence is a causal order within one subject or one
  site, not a global clock, and any hybrid-logical timestamp stored alongside it is an advisory
  ordering hint that MUST NOT be presented as a provable time.
- **It does not claim the chain digest is reproducible by a stranger.** It is not: it is computed
  over the database's own normalisation. The reproducible digest is the canonicalised one in the
  custody layer.
