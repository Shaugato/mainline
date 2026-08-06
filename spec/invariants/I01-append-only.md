<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I01 — Append-only

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** kernel; every evidentiary relation
- **MAINLINE schema invariants that instantiate it:** `MI01`, `MI24`, `MI26`
- **Conformance cases:** 5 (4 on the reference profile)

---

## NORMATIVE STATEMENT

**A relation declared evidentiary MUST admit `INSERT` only.**

- `UPDATE` and `DELETE` against an evidentiary relation MUST be refused, **for every role**,
  including the relation's owner and including any future application code.
- A binding MAY declare **at most one** exception per relation: a single **retraction** column whose
  update is permitted **only** when (a) it is the only column whose value changes and (b) its prior
  value was `NULL`. Every other update to that relation, including a second retraction, MUST be
  refused.
- Retraction MUST NOT erase. It MUST leave the retracted row readable and MUST increment the
  subject's `gate_epoch` (see [`I03`](I03-epoch-pin.md)), so that a retraction after a completed
  transition is itself refused.
- Row-level TTL MUST NOT be enabled on an evidentiary relation. A retention policy that deletes
  evidence by timer is not a retention policy; it is a shredder on a schedule.
- Enforcement MUST use **three independent layers, in this order**: revoked grants first, an
  unconditional trigger second, restrictive row-level security third. **No layer is sufficient
  alone; each MUST be separately testable.**

---

## MECHANISM

| Layer | SQL object |
|---|---|
| grants | `REVOKE UPDATE, DELETE ON <relation> FROM PUBLIC` and from every application role; no application role holds DDL |
| trigger | `fn_refuse_mutation()` — an unconditional `RAISE`, attached `BEFORE UPDATE OR DELETE FOR EACH ROW` to every evidentiary relation |
| the one exception | `fn_disposition_retract_only()` — attached `BEFORE UPDATE` to the disposition relation; refuses unless `retracted_by` is the only changed column and `OLD.retracted_by IS NULL`; re-opens the gate and bumps the epoch |
| RLS | `RESTRICTIVE` policies `USING (false)` for `UPDATE`/`DELETE`, plus an explicit permissive write policy for the gate role so a forced-RLS table does not lock the gate out |
| absence | no `ttl_expiration_expression`, no `ttl_expire_after`, on any evidentiary relation |

The trigger is *unconditional* on purpose. A conditional append-only guard is a policy with an
`IF` in it, and the `IF` is where the next exception goes.

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| `UPDATE`/`DELETE` on an evidentiary relation | `P0001` | `mainline.fn_refuse_mutation` |
| `UPDATE` of any disposition column other than the retraction column | `P0001` | `mainline.fn_disposition_retract_only` |
| second retraction of an already-retracted row | `P0001` | `mainline.fn_disposition_retract_only` |
| the same write attempted by a role whose grant was revoked | `42501` | `grant:UPDATE:<relation>:<role>` |

Message prefix per [`../errors.md`](../errors.md) §3.2, e.g.
`MAINLINE: this table is append-only; write a new row`.

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-08`](../conformance/manifest.toml) | Rewrite the blame closure: as an UPDATE, then as a new generation with a lowered severity | `P0001` | `mainline.fn_refuse_mutation` | both | 2 |
| [`CF-16`](../conformance/manifest.toml) | Append a permit_event whose prev_digest does not match the predecessor's chain_digest | `P0001` | `mainline.fn_permit_event_chain` | both | 1 |
| [`CF-38`](../conformance/manifest.toml) | UPDATE a disposition column other than retracted_by | `P0001` | `mainline.fn_disposition_retract_only` | both | 1 |
| [`CF-39`](../conformance/manifest.toml) | UPDATE and DELETE against an append-only obligation table | `P0001` | `mainline.fn_refuse_mutation` | both | 2 |
| [`CF-48`](../conformance/manifest.toml) | The application role attempts to drop the merge-gate trigger | `42501` | `grant:DDL:mainline.permit:agent_gate` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **This is not tamper-evidence.** A principal holding DDL can `DROP TRIGGER` and then update
  freely. The control for that adversary is the external custody ledger and the schema attestation,
  not this invariant. Any claim that append-only defends against a privileged operator is a claim a
  competent expert takes apart in one question.
- **It does not claim the rows are true.** Append-only constrains *mutation*, not *accuracy*. A false
  row, appended honestly, stays.
- **It does not extend to `BACKUP`, `RESTORE`, `IMPORT`, replication or changefeeds**, which do not
  evaluate triggers or RLS. A restore from an altered backup is outside this invariant's reach and
  inside the ledger's.
- **It does not claim deletion never happens.** Lawful destruction exists; it is a reviewed,
  two-person, recorded act that writes a destruction record, and it is a different mechanism with a
  different name.
