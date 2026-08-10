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

## The files on disk, and why the old ones stay

| File | Chain | Caveats | What it is |
|---|---|---|---|
| `proof-20260809T213857Z.json` | 246 / 261 applied, 15 failed | 2 | The first green. Fifteen migrations failed for want of five tables that had no producer, and `open_blocking` was written by the script. |
| `proof-20260810T004200Z.json` | 246 / 261 applied, 15 failed | 2 | The same picture, re-run. This is the file the producer-completion lead differenced to find the *seventh* missing table. |
| **`proof-20260810T054407Z.json`** | **271 / 271 applied, 0 failed** | **0** | The current record. The projection is asserted, not assumed: 10 / 10 `projection.assertions` held. |

The older two are kept deliberately. They are what the claim looked like before the
producers landed, and a repository that deletes its weaker evidence has made its
stronger evidence unfalsifiable.

## How to read one in ninety seconds

```jsonc
{
  "verdict": "PROVEN",              // or "NOT PROVEN" — and then `failures` says which half
  "cluster":  { "version": "CockroachDB CCL v26.2.5 …",
                "zone": { "gc_ttlseconds": 4500 } },
  "chain":    { "applied_count": 271, "files": 271, "failed_count": 0,
                "reached_0115_fn_permit_merge_gate": true,
                "unproduced_tables_enumerated": [],                // must be EMPTY
                "failures_unexplained": [] },                      // must be EMPTY
  "projection": { "assertions_held": 10, "assertions_total": 10,
                  "open_blocking": { "before": 0, "after": 1 },
                  "gate_epoch":    { "before": 0, "after": 1 },
                  "outbox": { "row": { "kind": "check_opened", … } } },
  "refusal":       { "sqlstate": "23514", "constraint": "gate_closed_when_issued" },
  "drift_refusal": { "sqlstate": "P0001", "constraint": "mainline.fn_permit_merge_gate" },
  "admission":     { "outcome": "ADMITTED", "merge_record": { … } },
  "caveats":       []                                              // present, and empty
}
```

**Read `verdict` last.** The four sections above it are the claim; `verdict` is only the
arithmetic over them, and a reader who trusts the summary without the sections has
learned nothing a marketing page could not have told them.

| Field | What it settles |
|---|---|
| `chain.reached_0115_fn_permit_merge_gate` | Whether the merge-gate function was in the schema at all. If this is `false`, nothing below it is a statement about the gate. |
| `chain.unproduced_tables_enumerated` | The tables this proof is willing to *forgive* a migration failure for. **It is now empty, and that is the ratchet** — with nothing enumerated, `_classify` cannot attribute any failure, so every failure lands in `failures_unexplained` and turns the verdict red. |
| `chain.failures_unexplained` | Migrations that failed. Since the list above emptied, this means *any* migration that failed. Non-empty is a red proof, whatever the refusals say. |
| `refusal.constraint` | The **exhibit**. A refusal with the right SQLSTATE and the wrong constraint name is the right outcome for the wrong reason. |
| `refusal.constraint_source` | `reported` when the driver supplied it; `parsed` when it had to be recovered from the message. `spec/errors.md` §3.1: `diag.constraint_name` is empty for `P0001`, so every `P0001` exhibit here is `parsed`, and saying so is the difference between a diagnosis and a guess. |
| `refusal.refusal_ledger` | The row the database itself stored. Its CHECKs cross-check the payload against the columns, so a row that misdescribes its own refusal cannot be written. |
| `admission.merge_record.clearance_digest` | SHA-256 over the sorted `(check_id, disposition_id)` set, computed **server-side**: exactly which obligations were cleared, by which signatures, at the instant of the merge. |
| `history.open_blocking_counter_written_by` | Who wrote the projected counter. On a healthy run this reads `trigger check_materialised -> mainline.fn_check_materialised`; anything else is a failed assertion, not a footnote. |
| `caveats` | Read these. They are the parts of the picture the run could not obtain honestly. **On the current record run the list is present and empty**, and the console prints `caveats       (none)` so that an empty list cannot be confused with a missing field. |

## `projection` — the block this wave added

Retiring a caveat is a subtraction. This block is the addition that replaces it, and it
is what lets the artefact say

> **the trigger projected the counter, emitted the CDC signal, bumped the epoch, and the
> gate refused**

with every clause backed by a value rather than by a sentence.

```jsonc
"projection": {
  "trigger":  { "name": "check_materialised", "timing": "AFTER INSERT",
                "on": "mainline.blocking_check",
                "function": "mainline.fn_check_materialised",
                "migration": "0121_trg_check_materialised.sql", "present": true },
  "fired_by": "one INSERT INTO mainline.blocking_check, with no other statement between
               the before and after readings",
  "open_blocking": { "before": 0, "after": 1 },
  "gate_epoch":    { "before": 0, "after": 1, "moved": true },
  "severity": { "supplied_by_this_script": 0, "projected_onto_the_check": 4,
                "virulence_projected": "blood_major" },
  "outbox": { "relation": "mainline_ops.outbox", "rows_in_table": 1,
              "rows_for_this_check": 1,
              "row": { "signal_id": "…", "kind": "check_opened",
                       "subject_id": "<the check_id>", "site_id": "<the site_id>",
                       "max_severity": 4, "emitted_at": "…", "expires_at": "…" } },
  "assertions": [ { "id": "…", "claim": "…", "holds": true, "observed": "…" }, … ],
  "assertions_held": 10, "assertions_total": 10
}
```

| Field | What it settles |
|---|---|
| `trigger.present` | Asked of `information_schema.triggers`, not of the file tree. "The migration is on disk" and "the weld is in the schema" are different claims. |
| `fired_by` | The permit's counters are read **immediately before and immediately after the one `INSERT INTO mainline.blocking_check`**, with no statement in between. The delta is therefore attributable to that weld and to nothing else in the seed. |
| `open_blocking.before → after` | `0 → 1`. The gate closes because a row landed, not because a script decided it should. |
| `gate_epoch.before → after` | `0 → 1`, **strictly** increasing. MI07: the completion record's composite FK carries `ON UPDATE RESTRICT`, so moving the epoch is what makes attaching a precursor to an already-issued subject physically impossible. An epoch that stands still is a pin that does not pin. |
| `severity.*` | The sharpest field on the page. The script writes `severity = 0`; `fn_check_project` (BEFORE INSERT, 0120) overwrites it from `clause_blame_current`; `fn_check_materialised` (AFTER INSERT, 0121) copies `(NEW).severity` into the signal. **A signal carrying `4` where the client wrote `0` demonstrates that both triggers ran, in that order.** |
| `outbox.row` | The row the trigger emitted into the deployment's single CDC-query source (§4.1 law 11). `kind` must be `check_opened`; `subject_id` must be the `check_id`; `site_id` is denormalised because a CDC query permits no joins. `payload` is `{}` — pointers and digests only, because a changefeed bypasses row-level security entirely. |
| `outbox.rows_in_table` vs `rows_for_this_check` | Both `1`. The whole seeded history emitted exactly one signal, and it is this one. |
| `assertions[]` | Each entry is a claim that **can turn the verdict red**, with the value that was observed. A populated field proves nothing, because nobody reads it; an assertion is read by the exit code. |

### What a broken projection looks like

Measured, by running the proof against a tree with `0121_trg_check_materialised.sql`
removed (`--migrations` pointed at a copy):

```
chain         270/270 applied, 0 failed
PROJECTION    1/10 held · open_blocking 0->0 · gate_epoch 0->0 · outbox None severity None
  ! trigger_present: present=False
  ! open_blocking_projected: 0 -> 0
  ! gate_epoch_strictly_increased: 0 -> 0
  ! outbox_row_emitted: rows_for_this_check=0
  …
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
VERDICT       NOT PROVEN
```

Note that **all three refusal beats still landed.** That is deliberate: the run does not
abort on a broken projection, because a reader has to be able to see *which* half failed.
The verdict is still `NOT PROVEN` and the exit code is still `1`.

## The caveat that used to be on every run, and is not any more

`0121_trg_check_materialised.sql` is the trigger that increments
`mainline.permit.open_blocking`. Until 2026-08-10 it could not apply, because its
function writes to `mainline_ops.outbox` and that table had no migration in this tree.
The proof therefore wrote the counter itself, to the value the gate independently
re-derives, and said so in both `caveats` and
`history.open_blocking_counter_written_by`.

`0099_outbox.sql` landed. The caveat retired **itself** — the probe and the caveat were
already conditional on the same flag, so no line of the proof script had to change for
it to disappear — and `history.projection_trigger_check_materialised_present` flipped to
`true` on the next run. That was verified empirically before anything was written about
it, and the artefact was then made to say something stronger than "no apology": the
`projection` block above.

## Retention

These are artefacts, not logs. Keep the run that a release or a claim cites; there is no
value in keeping every local iteration. The CI lane uploads its own copy as a build
artifact, so a run that only ever existed in CI is still recoverable from there.
