<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I02 — Projected refusal

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** kernel; every gate
- **MAINLINE schema invariants that instantiate it:** `MI02`, `MI03`, `MI04`, `MI05`, `MI06`, `MI11`, `MI22`, `MI25`, `MI27`, `MI30`
- **Conformance cases:** 23 (16 on the reference profile)

---

## NORMATIVE STATEMENT

**Every cross-row gate condition MUST be a trigger-maintained scalar column of the subject row,
enforced by a `CHECK` constraint on that column, derived from a declared authority source.**

- A value supplied by the writer for such a column MUST NOT survive the write. The projection
  trigger MUST overwrite it **unconditionally**, whether or not the supplied value agrees, so that a
  correct guess confers no privilege.
- The authority source MUST be declared in the binding under `[[authority_source]]`, MUST NOT be a
  relation the writing role can write, and MUST be looked up by columns of the row being written.
- When the authority source holds **no row**, the write MUST be refused. Defaulting, inferring,
  admitting-and-flagging, or treating absence as a benign value are all non-conformant. **Absence of
  evidence refuses.**
- A projected column MUST NOT be nullable.
- **Each independently nameable refusal MUST have its own `CHECK`, with its own name.** Collapsing
  several conditions into one counter is non-conformant even where logically equivalent.
- Procedural code MUST NOT pre-empt a `CHECK` that can express the condition; it re-derives from base
  tables and refuses only on **drift** or on a condition no `CHECK` can hold.

---

## MECHANISM

| Role | SQL object |
|---|---|
| project the obligation's classification | `fn_check_project()` — `BEFORE INSERT`; overwrites `severity`, `virulence`, `closure_gen` from the authority source; raises when the authority row is absent |
| project the disposition's classification and identity | `fn_disposition_project()` — `BEFORE INSERT`; re-derives from the **authority source**, never from the obligation row, so a laundered obligation cannot launder its disposition |
| move the counters | one independent trigger per counter (`fn_check_materialised`, `fn_disposition_close`, and the vertical's residue / conflict / warrant / boundary counters) |
| refuse | one `CHECK` per counter on the subject: `gate_closed_when_issued`, `identity_conserved_when_issued`, `conflicts_resolved_when_issued`, `no_open_warrant_when_issued`, `boundary_certified_when_issued`, `reading_floor_when_issued`, and their `cr_`-prefixed mirrors |
| detect drift | the merge-gate trigger's `FOR SHARE` anti-join re-derivation |
| compile-time | the Authority Source Contract — see [`../binding/authority-source.md`](../binding/authority-source.md) |

Six independently-named refusals rather than one counter is a deliberate cost. `open_blocking = 0`
alone would enforce the invariant, but *"the merge was refused by `boundary_certified_when_issued`"*
is a materially better sentence than *"a counter was non-zero"*, and one independent trigger per
counter is what makes the refusal-depth matrix meaningful.

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| complete a subject with an open obligation | `23514` | `gate_closed_when_issued` (or the mirrored `cr_gate_closed_when_merged`) |
| complete with un-dispositioned identity residue / open conflict / open warrant / uncertified boundary / unmet reading floor | `23514` | `identity_conserved_when_issued` · `conflicts_resolved_when_issued` · `no_open_warrant_when_issued` · `boundary_certified_when_issued` · `reading_floor_when_issued` |
| materialise an obligation whose authority row is absent | `P0001` | `mainline.fn_check_project` |
| complete a subject whose projection is stale or absent | `P0001` | `mainline.fn_permit_merge_gate` |
| complete a subject whose counter was tampered out of band | `P0001` | `mainline.fn_permit_merge_gate` (drift) |
| race a materialisation against a completion | `40001` | `mainline.permit.open_blocking` |

A supplied classification is not an error and produces no diagnostic. It is simply **overwritten**,
and the conformance cases assert the *stored* value, not only the refusal.

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-01`](../conformance/manifest.toml) | Merge a permit carrying one open blocking check | `23514` | `gate_closed_when_issued` | both | 2 |
| [`CF-02`](../conformance/manifest.toml) | Merge a permit whose only disposition expired before the merge | `P0001` | `mainline.fn_permit_merge_gate` | both | 2 |
| [`CF-03`](../conformance/manifest.toml) | Merge a permit whose open_blocking counter was forced to zero out of band | `P0001` | `mainline.fn_permit_merge_gate` | both | 2 |
| [`CF-04`](../conformance/manifest.toml) | Merge a permit with no merged_commit | `23514` | `merge_evidence` | both | 2 |
| [`CF-05`](../conformance/manifest.toml) | Merge a permit with an unmet reading floor and no countersignature | `23514` | `reading_floor_when_issued` | both | 2 |
| [`CF-06`](../conformance/manifest.toml) | Merge a permit citing a clause for which the authority source holds no row | `P0001` | `mainline.fn_permit_merge_gate` | both | 2 |
| [`CF-07`](../conformance/manifest.toml) | A check claiming virulence='routine', severity=1 on a clause whose closure holds max_severity=5, then a mechanism_absent disposition against it | `23503` | `fk_clearance` | both | 1 |
| [`CF-11`](../conformance/manifest.toml) | Materialise the same weaken_over_blood check twice with precursor_event_id NULL | `00000` | `blocking_check_dedupe_key_key` | both | 1 |
| [`CF-19`](../conformance/manifest.toml) | Sign with a client-supplied signer_rank of 6 on a person whose live rank is 2 | `23514` | `rank_floor` | both | 1 |
| [`CF-20`](../conformance/manifest.toml) | Disposition signed by a subject with no person row | `P0001` | `mainline.fn_disposition_project` | both | 1 |
| [`CF-22`](../conformance/manifest.toml) | Run the entire gate transaction with FORCE ROW LEVEL SECURITY active, then drop the write policy | `00000` | `gate_write` | mainline | 1 |
| [`CF-31`](../conformance/manifest.toml) | Merge a change_request carrying an undispositioned weaken_over_blood check | `23514` | `cr_gate_closed_when_merged` | both | 2 |
| [`CF-41`](../conformance/manifest.toml) | Blocking check naming both a permit and a change request | `23514` | `exactly_one_subject` | both | 1 |
| [`CF-42`](../conformance/manifest.toml) | Blocking check against a clause version that does not exist | `23503` | `fk_check_version` | both | 1 |
| [`CF-43`](../conformance/manifest.toml) | Materialise an obligation concurrently with the merge of the same permit | `40001` | `mainline.permit.open_blocking` | both | 1 |
| [`CF-45`](../conformance/manifest.toml) | Run the entire gate history at READ COMMITTED | `23514` | `gate_closed_when_issued` | both | 2 |
| [`CF-47`](../conformance/manifest.toml) | The recall role attempts to insert a blocking check | `42501` | `grant:INSERT:mainline.blocking_check:agent_recaller` | mainline | 1 |
| [`CF-49`](../conformance/manifest.toml) | Merge a permit carrying un-dispositioned identity residue | `23514` | `identity_conserved_when_issued` | mainline | 2 |
| [`CF-50`](../conformance/manifest.toml) | Merge a permit carrying an open fleet conflict | `23514` | `conflicts_resolved_when_issued` | mainline | 2 |
| [`CF-51`](../conformance/manifest.toml) | Merge a permit citing a clause under an open discordance warrant | `23514` | `no_open_warrant_when_issued` | mainline | 2 |
| [`CF-52`](../conformance/manifest.toml) | Merge a permit whose boundary certificate reports unmodelled or under-declared assets | `23514` | `boundary_certified_when_issued` | mainline | 2 |
| [`CF-53`](../conformance/manifest.toml) | Merge a permit with no boundary certificate at all | `P0001` | `mainline.fn_permit_merge_gate` | mainline | 2 |
| [`CF-70`](../conformance/manifest.toml) | A permit refused with three obligations of which two are already dispositioned emits a MUS naming exactly the third | `23514` | `gate_closed_when_issued` | both | 2 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the authority source is correct.** The invariant guarantees the projection has
  a named, reviewable source and that a missing row refuses — not that the source computed the right
  severity. Whether the ancestry is right is a vertical's problem and a different argument.
- **It does not claim the projection is atomic with respect to anything outside the database.** A
  fact that exists in the world but not yet in the authority source does not refuse; it is simply not
  yet known, and the gate fails closed only on rows it can see are missing.
- **It does not claim `READ COMMITTED` is equivalent to `SERIALIZABLE`.** The materialised conflict
  keeps the *gate* welded at `READ COMMITTED`; drift *detection* is weaker there, and the corpus says
  so rather than implying otherwise.
- **It does not claim the counters can never drift.** It claims drift is *detected* at the moment it
  would matter, by re-derivation, and refused — which is a different and more honest claim.
