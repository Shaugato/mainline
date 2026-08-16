<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# VERDICT — TWO USE CASES

**Verifier pass, 2026-08-16. Tree at HEAD `240cff1` plus the uncommitted two-cases wave.**

## VERDICT: **NOT READY**

Not because the engineering is wrong. The engineering is the strongest thing in this wave and
every claim it makes about the database is true, measured, and reproducible. It is NOT READY
because **use case two has never been driven over HTTP** (it is not deployed), **two film
documents disagree about the shape of the new material**, **one primary spoken line is a
sentence this film disproves thirty seconds earlier**, and **the repository's own regression
gate goes red on a stale constant**. All four are hours of work, and all four have a
determinate fix. None of them requires new product code.

---

## 1 · NOTHING IS FAKED — swept, and it holds

| swept for | result |
|---|---|
| hard-coded SQLSTATEs on a demo surface | **none.** The literals in `app/refusal.ts`, `design/sqlstate.ts`, `design/glossary.ts` and `types.generated.ts` are *classification vocabularies* (code → semantic class), not displayed exhibits. `features/propagation/model.ts:62`'s `'23514'` is a **stated law** about a CHECK that exists. |
| canned refusal text | **none.** `operator/change/cr-gate.ts` reads `sqlstate`, `constraint`, `constraint_source` and `message` out of the payload row (`str(row,…)`). Where a field is absent it renders `not stated` and prints the raw bytes. |
| simulated latency / mocked fetch | **none in the demo path.** The only `setTimeout`s are `Counter.tsx` and `Digest.tsx` UI affordances. `ChangeScreen.ts` and `HazardCard.ts` both state the no-artificial-delay rule in-file. |
| a beat dressed to look passing | **the opposite.** `cr_gate_run` declares its two ABSENT beats in the payload — `admission_beat: null` and `kernel_procedure_beat: null` — each with a prose reason and the `db/GRANTS.yaml` line numbers behind it. I checked those grant rows against the live database and **they are exactly right** (below). |
| the proof script | honest. Constants at `scripts/proof/cr_gate_refusal.py:170-181` are **expectations** compared against `observed=pointer_get(payload,…)`. When the route 404'd it wrote `verdict: "UNANSWERABLE", exit_code: 2` into `qa/cr-gate-live.json` for **both** phases rather than reporting a pass. |

**No faked beat found anywhere.** The wave's instinct throughout is to declare an absence with
its evidence rather than to omit it, and that instinct is correct under the contest's
"must function as depicted" rule.

---

## 2 · USE CASE ONE STILL WORKS — no regression, this outranks everything

Driven against the **live origin** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`:

```
POST /v1/demo/gate-run  →  200, 10,500 B, 2.65 s
verdict PROVEN · persisted False · outcome completed · failures []
  beat 1 read                     read      00000
  beat 2 merge                    refused   23514  gate_closed_when_issued
  beat 3 projection_drift_attack  refused   P0001  mainline.fn_permit_merge_gate
  beat 4 admit                    admitted  00000
identical True · self_persisted False · rolled_back · single_transaction True
```

`regression_guard.py --only KERNEL` → **GREEN, all 7 checks**, verdict PROVEN, **caveats (none)**.
`regression_guard.py --only LIVE` → **GREEN, all 4 checks**, 271 migrations applied.

**Use case one is intact.**

---

## 3 · USE CASE TWO WORKS — against the kernel, not yet over HTTP

`POST /v1/demo/cr-gate-run` answers **404 on the live origin** — the deployed bundle still
declares 17 routes. The wave measured this itself and recorded it as UNANSWERABLE. So I drove
the endpoint's own code against the seeded local CockroachDB (`mainline_demo`, v26.2.5):

```
verdict PROVEN · persisted False · outcome completed · failures []
  beat 1 read                     read     00000
  beat 2 merge                    refused  23514  cr_gate_closed_when_merged   (reported)
      failed to satisfy CHECK constraint ((state != 'merged') OR (open_blocking = 0))
  beat 3 projection_drift_attack  refused  P0001  mainline.fn_cr_merge_gate    (parsed)
      MAINLINE: merge refused by mainline.fn_cr_merge_gate — re-derived open
      obligation count is 1 while the projected counter reads zero
```

**The SQLSTATEs the database returned: `23514` on `cr_gate_closed_when_merged`, and `P0001`
from `mainline.fn_cr_merge_gate`.** The route that returns them is `POST /v1/demo/cr-gate-run`,
dispatched through `transitions._demo_cr_gate_run`.

### It persists nothing, and proves it from its own fingerprint

```
counter_forced_to                  0     ← the write THIS run made
counter_after_savepoint_rollback   1     ← fence 1: beat 3's ROLLBACK TO SAVEPOINT
counter_before / counter_after     1 / 1 ← fence 2: the transaction's ROLLBACK
subject_row_counts   before == after  (cr_event 1, merge_record 0)
identical True · self_persisted False
opened_logical_timestamp == closed_logical_timestamp  → single_transaction True
```

The run-scoped witness is real: beat 3 forces `open_blocking` to `0`, a value no other caller
wrote, and **both** fences are read back separately so the claim is visible rather than
asserted. `_FINGERPRINT_SQL` / `_FINGERPRINT_TABLES` are **imported from `gate_run`**, not
copied — so the ten unscoped counts cannot drift apart. Verified as the same objects.

### Verified as `mainline_api` — the role the deployed Function URL executes as

This is the check that matters, and it passes:

```
BEAT2  sqlstate 23514 | cr_gate_closed_when_merged
BEAT3  FORCE admitted, counter → 0; then P0001 mainline.fn_cr_merge_gate
after rollback: head_seq 1, open_blocking 1, state checks_materialised   (unchanged)
```

Grants on the live database confirm every claim the payload makes:

| table | `mainline_api` holds | payload's claim |
|---|---|---|
| `change_request` | SELECT, **UPDATE** | the bare merge is reachable ✓ |
| `cr_event` | SELECT only | why `CALL` would answer `42501`, not a gate refusal ✓ |
| `exposure_receipt` / `exposure_line` | SELECT only | why no admission beat can be played honestly ✓ |

The docstring's reasoning — that a privilege error says the writer *never reached the gate*, so
presenting one as a refusal would be fabrication — is correct and is the right call.

> **One honest gap.** The full `cr_gate_run` function could not be run end-to-end as
> `mainline_api` *locally*, because the local role lacks SELECT on `mainline.ledger_intake`
> (a fingerprint table). This is a **local role artefact, not a defect**: the deployed
> `mainline_api` reads it fine — live `gate-run` reports `ledger_intake: 5` using the *same
> imported* statement. Every component was verified as `mainline_api` separately.

---

## 4 · NO COMMITTING PUBLIC ROUTE WAS ADDED — confirmed

* `TRANSITION_RESOURCES["cr_gate_run"] = (None, None, False)` — **no path parameter, no kernel
  procedure, does not mutate.** The in-file note explains that a `{cr_id}` mutating route would
  fall *past* `_demo_guard` (which decides on `subject_id == scenario.permit_id`) — a correct
  and important piece of reasoning.
* The other new route, `GET /v1/change-requests/{cr_id}/blocking-checks`, is **pure SELECT**
  (`reads.read_cr_blocking_checks`), reuses `blocking-check.schema.json`, no new contract.
* **`_demo_guard` still answers `423 Locked`** — verified live on both `/merge` and `/suspend`
  for the seeded permit, with the `demo_subject_write_protected` body intact.
* **`db/GRANTS.yaml` is untouched** (`git diff` empty). **No migration added.** No `INSERT`
  granted to `mainline_api` anywhere. The standing `materialise_checks` / `exposure_receipt`
  finding is left open and explicitly named as not this wave's to close — correct.
* `DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024` and `_MINIMUM_HEADROOM_BYTES = 1024` both unmoved.
  `HONESTY.md`, `CI-STATE.md` and the ratchets untouched. No `continue-on-error`, no `|| true`.

---

## 5 · THE FILM — it fits, but two documents disagree and one line is false

### Timing: measured, and it fits

`BEATS.yaml` is arithmetically exact and contiguous — every `t` equals the previous `ends`, and
the durations sum to **172 s = 2:52**: demo 148 + close 22 + end card 2. That is the target
exactly, 2 s inside the 174 s hard stop and 8 s inside the 3:00 ceiling.

I hand-verified the declared word counts against the actual lines — B2 = 25 w, B5 = 25 w,
B8 = 11 w, B9 = 20 w, B10 = 20 w — **every one accurate**. Delivered speech is ~259 demo words
+ 36 close words = **295 words across 170 speaking seconds = 1.74 w/s**. That is a deliberate,
clear documentary pace with the holds the script budgets, and it is comfortably deliverable by
a non-professional narrator. **The film fits.**

Both candidate shapes for the new material total 24 s, so 2:52 holds either way.

### The on-screen lists survived — Devpost's requirement is met

`ONSCREEN-TEXT.yaml`'s `k2` card carries **every** AWS service and CockroachDB feature verbatim
in two columns: Lambda, Function URL, SSM, IAM, S3, CloudWatch+SNS+Budgets, the Bedrock
exception with its residency split, and CockroachDB Cloud, SERIALIZABLE, the CHECK, the PL/pgSQL
trigger function, the user-defined enum, composite foreign keys, the recursive CTE, the three
*"It did not run in this request."* lines and the no-scale concession. **Nothing was dropped.**
The 50 s → 22 s compression is of *delivery*, as claimed — with one exception, below.

### Register: matches

*"Then change the rule instead."* · *"Same paragraph. Same incident behind it."* — concrete,
short, no uncashed jargon. This is the standard of *"Nobody typed that four"*. B0b's *"Years
ago"* is honest: the precursor's `occurred_at` is `2019-03-14`, and the line names no year, no
site, no injury and no person, consistent with a seeded incident that describes nobody.

### ⚠ FILM BLOCKER A — two documents specify the same 24 seconds differently

| shape | files | blocks |
|---|---|---|
| **TWO blocks** | `BEATS.yaml` (the spine), `VO-DEMO.md` | B9 `[2:04]` 12 s + B10 `[2:16]` 12 s |
| **THREE blocks** | `VO-DEMO-CR.md`, `CLICKS-CR.md` (the choreography) | B9 `[2:04]` 10 s + B10 `[2:14]` 6 s + B11 `[2:20]` 8 s |

Declared honestly in `VO-DEMO-CR.md` §0.3 as *"the collision the film lead must resolve"*, and
nothing before B9 renumbers under either choice. But the founder **records voice first, then
picture, then matches them** — and the voice document and the picture document currently
describe different films. This must be resolved before the red light, not during the match.

### ⚠ FILM BLOCKER B — `VO-DEMO-CR.md` B11's primary line is barred, and is false

`VO-DEMO-CR.md` B11 opens with:

> "You can't use the clause."

`CLAIMS-CLEARANCE.md` row 30 and its §6 table bar **exactly that**, unscoped, and give the
reason: **`b7` shows the permit ISSUED on that same clause thirty seconds earlier**, so the flat
form *"is contradicted by this film, in this film."* `VO-DEMO.md` found and fixed this — its
B10 reads *"You can't **just** use the clause"*, cleared at **D32** as an improvement, so both
halves of the mirror carry scope.

`VO-DEMO-CR.md` transcribed R-7's four-item bar list and **dropped the fifth item — the one its
own primary line violates.** The two shapes are therefore not equal in honesty.

**Resolution is already determined: adopt `VO-DEMO.md`'s scoped line.** This also settles
Blocker A in favour of the two-block shape, which is what `BEATS.yaml` encodes.

### ⚠ FILM BLOCKER C — `D35`, an open REFUSE against the close, undischarged

`CLAIMS-CLEARANCE.md` §12.9 is the wave's **final re-read against what actually landed**, and it
files `D35` **✗ REFUSE** against `VO-CLOSE.md` `k2`'s spoken line:

> "Everything here is either in that request or in the apply. Bedrock — not in this path."

The compression removed *"is exercised in this repository"* — the positive half that makes the
denial credible, and which the **on-screen card still carries in full**. A card that only denies
reads as a card hiding something. This is the one place the 50 → 22 compression **did** cost
content. Replacement already written, 14 words, inside budget:

> **"Every line says which. Bedrock is exercised in this repository — not in this path."**

`D31` **~ REWORD** is also open: `VO-DEMO.md` B10's *"a different constraint guards edits"* names
the wrong object — the predicate refuses the **merge**. Fix supplied: *"guards the change."*
(`VO-DEMO-CR.md`'s B10 already uses the corrected wording.)

---

## 6 · NO REGRESSION — with one stale constant that turns the gate red

**Suite** (`demo-api/tests` + `tests/deploy`, `--crdb=reuse`, from the `--junitxml` root):

```
1070 collected · 1069 passed · 0 failed · 0 errors · 1 skipped   (265.96 s)
baseline:  998 collected ·  997 passed · 0 failed · 0 errors · 1 skipped
```

**+72 tests, nothing lost, nothing red.** The one skip is the same one as before.
The wave's own new tests pass on their own: 91 across `test_cr_gate_run.py`,
`test_routes_gate_run.py`, `test_transitions.py`. `test_static_site.py` 100 passed.

### ⚠ BLOCKER E — `regression_guard.py` reports REGRESSION on a stale baseline

```
SUITES  collected  FAIL  expected 998   observed 1070
SUITES  passed     FAIL  expected 997   observed 1069
SUITES  failed     PASS · errors PASS · skipped PASS
VERDICT  REGRESSION - 2 of 5 checks FAILED in SUITES
```

`SUITE_BASELINE` at `scripts/qa/regression_guard.py:237` was not re-recorded. **Nothing
regressed** — the guard uses strict equality and its own docstring says the figure is
"RE-RECORDED UPWARD, AND ONLY EVER UPWARD". It must be moved to 1070/1069 before the
orchestrator runs the one-command gate, or the wave lands looking broken when it is not.

### Console bundle — inside the headroom, but the margin is now thin

```
check-budgets: all budgets held
  PASS  entry-chunk-wire   134.8 KB gzip / 135 KB   (191 B left, widest of 43)
  PASS  operator-surface    39.6 KB gzip / 136 KB   (98,728 B left)
```

Headroom against the production ceiling is now **≈1,215 B**, down from **1,325 B** — the wave
spent ~110 B. **Still passing, still above the 1,024 B floor.** The operator screens correctly
landed in the **second HTML entry** (`operator.html`), not the console's import closure, which
is why 580 lines of `cr-gate.ts` cost the entry chunk almost nothing. **But 191 B of margin
over the CI floor means the next console change of any size goes red.** Worth saying out loud.

### Console unit suite — one failure, and it is pre-existing

`vitest`: **1 failed / 2550 passed.** `operator-a11y.test.ts` — *"every revealed beat can
receive programmatic focus"*, naming **permit** beats 1–4 including `beat 4 (admit)`, WCAG
2.4.3, dated **2026-08-15**, owner **W5 (`src/operator/issue/ActionBar.ts`)**. Neither the test
nor its target is in this wave's diff. **Pre-existing and untouched — not a regression**, but it
is red and it is real.

---

## 7 · MY OWN PERTURBATION, DECLARED

To validate the payload against its contract I ran `pip install jsonschema`. That installed five
packages **and un-skipped** `test_gate_run.py::test_payload_validates_against_the_json_schema`,
which then **failed**:

```
PointerToNowhere: '/$defs/uuid_or_token' does not exist within {…}
```

The cause is a latent bug **at `test_gate_run.py:1302`**, which builds
`Draft202012Validator(contract["$defs"]["gate_run"])` — passing the extracted subschema
*without carrying `$defs`*, so `#/$defs/uuid_or_token` cannot resolve. **`gate-run.schema.json`
is unmodified by this wave and does define `uuid_or_token`.** The defect is pre-existing and
masked by `pytest.importorskip`. I **uninstalled all five packages** and re-ran clean; the
1070/1069/0/0/1 figures above are from the restored environment. Worth fixing separately — the
test is a no-op today and would fail the moment `jsonschema` becomes a workspace dependency.

---

## 8 · IS THE FILM BETTER WITH TWO USE CASES THAN WITH ONE?

**Yes — and I would ship it, but only once the deploy lands and Blockers A–C are closed.** The
second case answers the one question a paying-attention judge inevitably asks after use case
one — *"fine, so couldn't somebody just rewrite the rule?"* — and it answers it with the
database naming a **different** guard: `cr_gate_closed_when_merged` where the permit had
`gate_closed_when_issued`, `fn_cr_merge_gate` where it had `fn_permit_merge_gate`. That is not a
repeat of the same exhibit at a second address; it is the same claim from the other side, and it
converts the film's strongest implicit weakness into its second-strongest beat. The 24 seconds
are honestly funded: 28 from a close whose *content* survives intact on screen, and 4 from
`b8`'s second half — which was already **rank 1 on the film's own pre-committed cut ladder**
precisely because that subject was *"shown read-only and told rather than driven"*, which is
exactly what use case two removes. The costs are real and the wave states them rather than
hiding them: the close loses 28 s of dwell on `C1`, the axis-1 beat, and case two ends on a
refusal with no admission to mirror `b7`. Against that, the film at 2:52 spends its entire
retake margin, depends on a deployment that has not happened, and currently ships with two
documents describing different films and one primary line the film itself disproves. **So the
honest answer is: better with two, but not yet — and if the deploy slips or the CLICKS-CR §5.1
pre-flight fails on the day, take the NO-GO path.** It is fully specified, it runs 2:32 with
every service and feature still named, and a working 2:32 film four days out is worth more than
a broken 2:52. That path being already written, costed and pre-authorised is the best single
sign of judgement in this wave.

---

## 9 · WHAT MUST HAPPEN BEFORE THIS IS READY

1. **Deploy** — `cr-gate-run` and `cr-blocking-checks` are 404 live; use case two cannot be shot
   or verified over HTTP until the orchestrator deploys. Then re-run `scripts/proof/cr_gate_refusal.py`
   and require a non-UNANSWERABLE verdict.
2. **Resolve the block collision** in favour of `VO-DEMO.md`'s two-block shape (which
   `BEATS.yaml` already encodes), and reconcile `CLICKS-CR.md`'s choreography to it.
3. **Replace `VO-DEMO-CR.md` B11's opening line** with the scoped *"You can't **just** use the
   clause."* Add the fifth bar to that file's R-7 list.
4. **Discharge `D35`** — the 14-word Bedrock replacement — and **`D31`** — *"guards the change."*
5. **Re-record `SUITE_BASELINE`** to `collected 1070 / passed 1069`.
6. Consider, separately and not in this wave: `test_gate_run.py:1302`, and the pre-existing
   `operator-a11y` focus failure.

**Nothing above requires a committing route, a new grant, a weakened guard, or a staged beat —
and none should be introduced to close any of them.**
