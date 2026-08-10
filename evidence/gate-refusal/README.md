<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `evidence/gate-refusal/`

Every file here is `proof-<UTC>.json`, written by
[`scripts/proof/gate_refusal.py`](../../scripts/proof/README.md), plus a REUSE
`.license` sidecar. Nothing here is hand-written, and nothing here should ever be
hand-edited: an evidence file is a transcript of what one cluster did at one instant,
and an edited transcript is not evidence.

To produce one:

```bash
python scripts/proof/gate_refusal.py \
    --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable
```

## How to read one in ninety seconds

```jsonc
{
  "verdict": "PROVEN",              // or "NOT PROVEN" — and then `failures` says which half
  "cluster":  { "version": "CockroachDB CCL v26.2.5 …",
                "zone": { "gc_ttlseconds": 4500 } },
  "chain":    { "applied_count": 246, "files": 261,
                "reached_0115_fn_permit_merge_gate": true,
                "failures_unexplained": [],                       // must be empty
                "failures_attributable_to_an_unproduced_table": [ … ] },
  "refusal":       { "sqlstate": "23514", "constraint": "gate_closed_when_issued" },
  "drift_refusal": { "sqlstate": "P0001", "constraint": "mainline.fn_permit_merge_gate" },
  "admission":     { "outcome": "ADMITTED", "merge_record": { … } }
}
```

**Read `verdict` last.** The three sections above it are the claim; `verdict` is only the
arithmetic over them, and a reader who trusts the summary without the sections has
learned nothing a marketing page could not have told them.

| Field | What it settles |
|---|---|
| `chain.reached_0115_fn_permit_merge_gate` | Whether the merge-gate function was in the schema at all. If this is `false`, nothing below it is a statement about the gate. |
| `chain.failures_unexplained` | Migrations that failed for a reason **other** than one of the five enumerated tables with no producer. This list being non-empty is a red proof, whatever the refusals say. |
| `chain.failures_attributable_to_an_unproduced_table` | The known gaps, each with file name, SQLSTATE and the table it needed. These are recorded, never invented — a new table needs a number the allocation table grants. |
| `refusal.constraint` | The **exhibit**. A refusal with the right SQLSTATE and the wrong constraint name is the right outcome for the wrong reason. |
| `refusal.constraint_source` | `reported` when the driver supplied it; `parsed` when it had to be recovered from the message. `spec/errors.md` §3.1: `diag.constraint_name` is empty for `P0001`, so every `P0001` exhibit here is `parsed`, and saying so is the difference between a diagnosis and a guess. |
| `refusal.refusal_ledger` | The row the database itself stored. Its CHECKs cross-check the payload against the columns, so a row that misdescribes its own refusal cannot be written. |
| `admission.merge_record.clearance_digest` | SHA-256 over the sorted `(check_id, disposition_id)` set, computed **server-side**: exactly which obligations were cleared, by which signatures, at the instant of the merge. |
| `history.open_blocking_counter_written_by` | Who wrote the projected counter. See the caveat below. |
| `caveats` | Read these. They are the parts of the picture the run could not obtain honestly. |

## The caveat that is currently on every run

`0121_trg_check_materialised.sql` is the trigger that increments
`mainline.permit.open_blocking`. It cannot apply, because its function writes to
`mainline_ops.outbox` and that table has no migration in this tree. The proof therefore
writes the counter itself, to the value the gate independently re-derives from
`blocking_check` anti-joined against live `disposition` rows, and says so in both
`caveats` and `history.open_blocking_counter_written_by`.

This does **not** weaken the refusal. The refusal is still the database's: `CF-01` is a
`CHECK` on `mainline.permit` firing on the completing row, and `CF-03` is the gate
function re-deriving the count for itself and disagreeing with whatever the counter says
— which is exactly the case where a counter written by anyone at all is not trusted.

When the outbox migration lands, `history.projection_trigger_check_materialised_present`
flips to `true`, the counter is trigger-written, and the caveat disappears without anyone
editing this file.

## Retention

These are artefacts, not logs. Keep the run that a release or a claim cites; there is no
value in keeping every local iteration. The CI lane uploads its own copy as a build
artifact, so a run that only ever existed in CI is still recoverable from there.
