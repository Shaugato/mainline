<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `scripts/proof/` — the claim, made runnable

One script lives here. It exists because for most of this repository's life the central
claim was a sentence in a design document:

> **The database refuses a permit merge when a recalled precursor carries no signed
> disposition.**

A sentence is not evidence. `gate_refusal.py` turns it into a command that a skeptic can
run on a laptop against a single-node CockroachDB, and into a JSON file that names the
SQLSTATE, the constraint, the subject and every migration that did not apply.

As of 2026-08-10 it says something stronger, because every clause of it is now a value
in the evidence rather than a claim in prose:

> **The trigger projected the counter, emitted the CDC signal, bumped the epoch, and the
> gate refused.**

```bash
python scripts/proof/gate_refusal.py \
    --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable
```

Exit `0` means proven. Exit `1` means **not** proven, and the evidence file is written
anyway — publish it. Exit `2` means there was no database to ask, which is a different
thing entirely and is kept separate on purpose.

---

## What it actually does, in order

| # | Step | Why it is there |
|---|---|---|
| 1 | `DROP`/`CREATE` a throwaway database, `CONFIGURE ZONE USING gc.ttlseconds = 4500` | Nothing is proven on a cluster somebody else has been writing to. 4500 is what CockroachDB Cloud enforces; local defaults to 14400, which is *more* permissive, so local-only testing can hide a time-travel assumption. |
| 2 | `trappoint migrate bootstrap` | Kernel ruling **D6**: the `trappoint` bookkeeping schema is created outside the numbered sequence. `0119a_fn_explain_refusal.sql` needs it. Applying raw files without bootstrapping makes 0119a fail for a reason that is not a defect — the runner is the correct entry point, and this step is what makes that visible instead of arguable. |
| 3 | Apply all **271** migrations in allocation order, **continuing past failures** | `trappoint migrate up` is forward-only and halts on the first refusal. That is right for a deploy and useless for a census. Every failure is recorded with its file name and SQLSTATE. |
| 4 | Classify every failure | It is *unexplained*, and unexplained fails the proof. There is no longer a second category — see "The ratchet" below. |
| 5 | Assert the gate objects exist | Asked of `information_schema`, not of the file tree. "The file is on disk" and "the object is in the schema" are different claims. |
| 6 | Seed the history | A clause, a severity-4 incident whose blame ancestry reaches it, a blame closure banding it `blood_major`, a permit that relies on that clause version, and one blocking check standing for the recalled precursor. The permit is then walked `draft → checks_materialised → dispositioned` through its own hash-chained event log. That last edge is **the client claiming every obligation is disposed of.** It is not. |
| 7 | **Measure the projection** | `mainline.permit` is read immediately before and immediately after the one `INSERT INTO mainline.blocking_check`, and `mainline_ops.outbox` is read back for the row the trigger emitted. Ten assertions, each of which can turn the verdict red. |
| 8 | **Attempt the merge** | `CALL mainline.merge_permit(...)` under `SERIALIZABLE`. |
| 9 | **Force the counter to zero and attempt again** | The disarmed-projector history. |
| 10 | **Sign a disposition and attempt a third time** | The half that stops this from being a proof that nothing can ever merge. |

## The four outcomes

```
PROJECTION    10/10 held · open_blocking 0->1 · gate_epoch 0->1 ·
              outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
```

* **The projection** — `fn_check_materialised` (0121, AFTER INSERT) raised
  `open_blocking` 0 → 1, raised `gate_epoch` 0 → 1, and emitted one row into
  `mainline_ops.outbox` with `kind = 'check_opened'` and `subject_id = check_id`. The
  counters are read with **nothing between the two readings but that single INSERT**, so
  the delta belongs to the weld. The signal's `max_severity` reads `4` where the script
  supplied `0`, which is `fn_check_project` (0120, BEFORE INSERT) and
  `fn_check_materialised` (0121, AFTER INSERT) both having run, in that order,
  demonstrated rather than asserted.
* **CF-01** — one open obligation, no disposition. `23514`, exhibit
  `gate_closed_when_issued`. The trigger deliberately does **not** pre-empt the CHECK:
  a synthetic `P0001` would carry no constraint name, and the constraint name is the
  product.
* **CF-03** — `open_blocking` forced to `0` out of band, the way a bad `UPDATE` or a
  disarmed projector leaves it. The gate re-derives the open count from
  `blocking_check` anti-joined against live `disposition` rows, disagrees with the
  counter, and raises `P0001` naming `mainline.fn_permit_merge_gate`. **No CHECK can
  hold this case** — the "live" test carries `expires_at > now()`, and `now()` is not
  immutable — which is precisely why rule P-2 says a projection is *enforced, never
  trusted*.
* **The admission** — one signed disposition, and the same merge writes a
  `merge_record`, a `ledger_intake` row and a fourth link in the permit's event chain.
  **A gate that always refuses is a broken gate, not a safe one.**

Both refusals are then written to `mainline.refusal_ledger` and read back. That table's
own CHECKs are the reason it is worth doing: `refusal_payload_names_the_exhibit`,
`refusal_payload_names_the_code` and `refusal_p0001_exhibit_is_parsed` mean **a row that
misdescribes the refusal it records cannot be inserted at all.** A refusal this script
invented would be refused by the table that stores refusals.

## The ratchet: `UNPRODUCED_TABLES` is empty

This script used to enumerate five tables that had consumers and no producer:

```
mainline_ops.outbox            mainline.identity_assignment    mainline.patrol_run
mainline_meas.agent_action     mainline_meas.standing
```

Fifteen migrations failed because of them. Each failure was *classified* rather than
merely counted, so the day a producer landed the list would shrink in a reviewable diff.
**That day was 2026-08-10.** The producer-completion wave authored all five, plus two
gaps no SQLSTATE census could see — `mainline_meas.person_measure_policy`, shadowed by
`standing` in both views that join it, and `mainline_ops.site_register_signal`, named
only by an RLS negative assertion — because CockroachDB reports only the **first** absent
relation in a statement.

`UNPRODUCED_TABLES` is therefore `()`, and that is not tidiness. `apply_chain` classifies
a failure as *explained* only when it is attributable to a listed table, so an **empty
tuple turns any residual failure into `chain.failures_unexplained`, which is a hard NOT
PROVEN.** The proof no longer forgives anything.

It still refuses to create a table that has no migration. If a future tree acquires a
genuine gap, the honest move is to name it in that tuple so the failure is classified —
never to mint the table here. A new table takes a number from a band whose owner and
mode match in `verticals/mainline/db/migrations.allocation.toml`, and this script owns no
band. **A recorded gap is a finding; an invented table is a lie about what the schema
is.**

## What it will still not claim

The `--keep` database is thrown away, the run is a single node, and two conformance cases
are not seventy-one. What the script *will* do, if the projection is broken, is finish
all three refusal beats anyway and then report `NOT PROVEN` — because "the gate refused
but nothing projected it" and "the gate admitted" are different findings and the reader
needs to see which one happened.

## Options worth knowing

| Flag | Default | Note |
|---|---|---|
| `--database` | `w_qr_gate_refusal_proof` | Dropped and recreated every run. |
| `--migrations` | `verticals/mainline/db/migrations` | Point it at a copy of the tree to make the proof go red on purpose — that is how the projection assertions were observed failing before they were green. |
| `--out` | `evidence/gate-refusal/proof-<utc>.json` | A REUSE `.license` sidecar is written beside it. |
| `--gc-ttlseconds` | `4500` | Cloud's value, not local's. |
| `--connect-timeout` | `10` | libpq waits this long **per resolved address**. On a host where `localhost` resolves to a dead `::1` before `127.0.0.1`, an unset timeout costs a measured **130 seconds per connection**. |
| `--keep` | off | Leave the database behind for inspection. |

With no `--dsn`, the script reads `MAINLINE_TEST_DSN`, `TRAPPOINT_DSN`, `COCKROACH_URL`,
`CRDB_URL`, then `LOCAL_DSN` — the spellings every cluster fixture in this repository
already honours, so it joins the session cluster rather than starting a fourteenth one.

## Where the proof is asserted

* `tests/release/test_gate_refusal_proof.py` — runs this script and asserts each half,
  now including the projection clause by clause and `caveats == []`. Observed **RED
  before GREEN** (PL-2) twice; both transcripts are verbatim in
  `docs/release/gate-refusal-proof.md`.
* `.github/workflows/release-proof.yml` — the same thing on a pinned
  `cockroachdb/cockroach:v26.2.5`, uploading the evidence JSON as an artifact.
