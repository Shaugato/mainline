<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CR-GATE ROUTE PLAN — giving the second gated subject an HTTP path to the gate the database already enforces

**Change-request gate lead · 2026-08-16 · repo HEAD `240cff1`**
Live origin measured: `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
Local kernel measured: `postgresql://root@localhost:26257/mainline_demo` — CockroachDB CCL v26.2.5

---

## 0 · WHAT I MEASURED BEFORE I PLANNED ANYTHING

Nothing below is transcribed from the brief. Every number and every SQLSTATE in this
document came out of the live origin or out of the seeded local kernel, in this session.

### 0.1 · The live route table

`GET /v1/routes` 404s and the 404 body lists what IS declared. Seventeen **paths**:

```
/v1/audit                                    /v1/permits/{permit_id}
/v1/change-requests/{cr_id}                  /v1/permits/{permit_id}/blocking-checks
/v1/checks/{check_id}/disposition            /v1/permits/{permit_id}/checks:materialise
/v1/clauses/{clause_uuid}/ancestry           /v1/permits/{permit_id}/merge
/v1/clauses/{clause_uuid}/versions/{commit_id}   /v1/permits/{permit_id}/silence
/v1/demo/gate-run                            /v1/permits/{permit_id}/suspend
/v1/demo/subjects                            /v1/recall-runs/{run_id}
/v1/ledger                                   /v1/receipts/{receipt_id}
/v1/lessons/{lesson_id}/propagation
```

**Seventeen paths is EIGHTEEN `Route` rows.** `/v1/checks/{check_id}/disposition` is
declared twice — `GET disposition`, `POST sign_disposition` — and the 404 body dedupes by
path. `app.py::_routes()` returns eighteen tuples and
`test_routes_gate_run.py::test_the_table_and_the_console_declaration_are_the_same_eighteen`
counts rows. **Every worker counts ROWS, never the 404 body.** After this wave: twenty
rows, nineteen paths, and that test's name and body both change.

### 0.2 · Driven against the live origin, this session

| request | live answer |
|---|---|
| `GET /v1/change-requests/dec0de00-000c-…` | **200** — `state: checks_materialised`, `open_blocking: 1`, four named CHECKs returned from `pg_constraint` |
| `GET /v1/checks/dec0de00-000d-…/disposition` | **200** — `virulence: blood_major`, five lattice rows, three defeater options, `signed: null` |
| `GET /v1/demo/subjects` | **200** — already returns `cr_id` |
| `GET /v1/change-requests/{cr_id}/checks` | **404** |
| `GET /v1/change-requests/{cr_id}/blocking-checks` | **404** |
| `POST /v1/change-requests/{cr_id}/merge` | **404** |
| `POST /v1/demo/gate-run` | **200**, 10,499 B, 2.82 s, `verdict: PROVEN`, `persisted: false`, beats `00000 / 23514 gate_closed_when_issued / P0001 mainline.fn_permit_merge_gate / 00000` |

The four named CHECKs the live CR read returns, verbatim:
`cr_gate_closed_when_merged`, `cr_merge_evidence`, `cr_conflicts_resolved_when_merged`,
`cr_identity_conserved_when_merged`. **Note the brief's `cr_merge_gate` is the TRIGGER
(0131), not the CHECK.** The CHECK is `cr_gate_closed_when_merged`. Both are real, they are
different objects, and a worker who writes the wrong one on screen has written a claim the
kernel does not make.

### 0.3 · The four-beat probe, run for real against the seeded local kernel

One `SERIALIZABLE` transaction, each beat savepoint-fenced, whole transaction rolled back:

```
CALL mainline.merge_change_request(...)  from checks_materialised
    -> REFUSED 23503  constraint = cr_legal_edge
       insert on table "cr_event" violates foreign key constraint "cr_legal_edge"

after advancing checks_materialised -> dispositioned (ADMITTED, head_seq 1 -> 2):
CALL mainline.merge_change_request(...)
    -> REFUSED 23514  constraint = cr_gate_closed_when_merged
       failed to satisfy CHECK ((state != 'merged') OR (open_blocking = 0))

after UPDATE mainline.change_request SET open_blocking = 0:
CALL mainline.merge_change_request(...)
    -> REFUSED P0001  constraint = <none>
       MAINLINE: merge refused by mainline.fn_cr_merge_gate — re-derived open
       obligation count is 1 while the projected counter reads zero

cluster_logical_timestamp() first == last   -> one transaction
after ROLLBACK: state='checks_materialised', open_blocking=1, head_seq=1, cr_event rows=1
```

And the same gate reached by the bare statement instead of the procedure:

```
UPDATE mainline.change_request SET state='merged', head_seq=head_seq+1,
       merged_commit=digest('probe','sha256') WHERE cr_id=… AND head_seq=1
    -> REFUSED 23514  constraint = cr_gate_closed_when_merged
  same statement with open_blocking forced to 0:
    -> REFUSED P0001  mainline.fn_cr_merge_gate — re-derived … is 1 while the
       projected counter reads zero
after ROLLBACK: state='checks_materialised', open_blocking=1, head_seq=1, merged_commit=NULL
```

**The mirror is exact and it needs no new rule, no migration, no seed change and no grant.**

### 0.4 · Facts that decide the design, each measured

| # | measurement | source |
|---|---|---|
| M1 | `('change_request','checks_materialised','merged')` is **not** in `mainline.subject_transition`. The CR's legal edges are `draft→checks_materialised`, `draft→abandoned`, `checks_materialised→checks_materialised`, `checks_materialised→dispositioned`, `dispositioned→checks_materialised`, `dispositioned→merged`, `merged→suspended`, `merged→closed`, `suspended→closed`. | `SELECT * FROM mainline.subject_transition` |
| M2 | `mainline_api` holds **SELECT only** on `mainline.cr_event`. No INSERT. | `GRANTS.yaml:761` |
| M3 | `mainline_api` holds **SELECT, UPDATE** on `mainline.change_request`. | `GRANTS.yaml:755` |
| M4 | Every relation `fn_cr_merge_gate` (0116) and `fn_cbm_gate_cr` (0140d) read is already SELECT-granted to `mainline_api`: `blocking_check` (630), `disposition` (633), `cr_clause` (758), `clause_blame_current` (664), `cbm_account` (681), `identity_residue` (764). | `GRANTS.yaml` |
| M5 | There is **no exposure receipt covering the CR's obligation.** `mainline.exposure_receipt` holds one row, `subject_kind='permit'`; the one `exposure_line` points at the permit's check `dec0de00-0007-…`, not the CR's `dec0de00-000d-…`. | local `SELECT` |
| M6 | `mainline_api` holds **SELECT only** on `exposure_receipt` (644) and `exposure_line` (647). | `GRANTS.yaml` |
| M7 | `mainline.clause_blame_current` **does** carry the authority row for the cited `(clause_uuid, commit_id)`, so arm 3 of `fn_cr_merge_gate` (CF-06) does not fire. `mainline.cbm_account` carries the cited commit with `residue_open = 0` and `identity_residue` open count is 0, so `z_cbm_gate_cr` passes. | local `SELECT` |
| M8 | An out-of-band `UPDATE … SET open_blocking = 0` on the CR is **admitted** and persists inside the transaction — neither `cr_merge_gate` nor `z_cbm_gate_cr` fires, because both carry `WHEN NEW.state = 'merged'`. | local probe |
| M9 | `console/contracts/blocking-check.schema.json` is **already subject-polymorphic**: its `data` requires `subject_kind`, `subject_id`, `gate_epoch`, `checks` — there is no `permit_id` in the required set. | schema read |
| M10 | `envelope.schema.json`'s `resource` is a free string with pattern `^[a-z][a-z0-9_]*$` — **no enum.** New resource keys need no envelope-contract change. | schema read |
| M11 | `console/src/data/resources.ts` already declares **eighteen** resources including `demo_gate_run` and `demo_subjects`. The stale paragraph in `app.py::_routes()` claiming the console "still does not declare it" is wrong and W2 fixes it. | source read |
| M12 | `operator/change/ChangeScreen.ts` **already probes** `/v1/change-requests/{cr_id}/blocking-checks` and renders the deployment's own 404 as evidence, and its header rule 4 says in words that there is no `POST /v1/change-requests/{cr_id}/merge` to point the approve control at. | source read |

---

## 1 · RULINGS

Each names its authority. Where the authority is a measurement, the measurement is above.

---

### R1 · A SECOND DEMO ENDPOINT, `POST /v1/demo/cr-gate-run`. NOT a subject parameter on `/v1/demo/gate-run`.

**Authority: mine as CR-gate lead, on four measured grounds.**

1. `gate_run.py`'s persistence proof binds the permit **positionally**: `_PERMIT_ROW_SQL`
   and `_SUBJECT_COUNTS_SQL` each take `permit_id`, and `_fingerprint(conn, permit_id)`
   has it in its signature. `ResolvedScenario.as_json()` emits `"subject_kind": "permit"`
   as a literal. A `subject` parameter forks every one of those.
2. `gate-run.schema.json` is copied **verbatim** into `console/src/data/contracts.ts` and
   pinned JSON-pointer-by-JSON-pointer **in both directions** by
   `console/tests/unit/data/contracts.test.ts`, and its `$id` is repeated inside the
   payload so the console validates the response before rendering it. Changing its shape
   is a two-package edit against a 998-collected baseline, for no gain.
3. `app.py:245-248` and `resources.ts`'s `demo_gate_run` comment both state the property
   deliberately: *the template takes no path parameter, and that is the point* — a
   stranger holding the public URL must not be able to aim the driver. A `subject` body
   member is that parameter arriving through a different door.
4. The two runs' beats **differ in kind** (R3). One schema admitting both would assert
   neither.

The new endpoint copies gate-run's safety properties exactly: ONE `SERIALIZABLE`
transaction, every write beat fenced by its own `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`, the
whole transaction `ROLLBACK`-ed, `persisted: false` **proved** by a fingerprint the
endpoint measured before and after and returned in the payload, and
`cluster_logical_timestamp()` captured at the first beat and after the last as the
read-only witness that the beats shared one transaction.

---

### R2 · THE MERGE ATTEMPT IS A BARE `UPDATE mainline.change_request`, NOT `CALL mainline.merge_change_request`.

**Authority: measurements M1, M2, M3, M4, plus the brief's standing prohibition on
widening the write surface of an unauthenticated endpoint.**

`mainline.merge_change_request` cannot reach the gate as the anonymous role:

* From `checks_materialised` it dies at step 5 on `23503 cr_legal_edge` (M1) — the FK onto
  `mainline.subject_transition`. It never reaches the CHECK.
* From `dispositioned` it would still die, because step 5 INSERTs into
  `mainline.cr_event` and `mainline_api` holds SELECT only there (M2). That is `42501`
  in front of a judge.
* Getting to `dispositioned` at all needs the same INSERT.

**Granting INSERT on `mainline.cr_event` is FORBIDDEN in this wave.** It is the same class
as the standing `materialise_checks` / `exposure_receipt` finding: widening the write
surface of an endpoint on a Function URL carrying `authorization_type = NONE` is the
founder's call and he has not made it. Do not grant it. Do not propose granting it in a
comment. Record the measurement and route around it.

The bare `UPDATE` needs exactly `UPDATE mainline.change_request` — held (M3) — plus the
SELECTs the trigger cascade already has (M4). Measured: `23514 cr_gate_closed_when_merged`,
and under a forged counter `P0001 mainline.fn_cr_merge_gate`.

**And it is the stronger exhibit.** The gate is welded to the TABLE — a `CHECK` on the
column and two `BEFORE UPDATE` triggers — not to the procedure. A caller who skips the
kernel's own procedure entirely, which is precisely what an attacker does, meets the same
named CHECK and the same named trigger function. The beat's label must say that plainly.

---

### R3 · FOUR BEATS, AND THE FOURTH IS NOT AN ADMIT. THE ABSENCE IS DECLARED, NEVER FAKED.

**Authority: measurements M5, M6.**

A CR admission beat is **impossible to play honestly.** `mainline.disposition` cannot be
signed without an exposure receipt that actually showed the obligation — the composite
foreign key on `(check_id, receipt_id)` says so — no such receipt exists for the CR's check
(M5), and minting one needs INSERT on `exposure_receipt` / `exposure_line`, which
`mainline_api` does not hold (M6) and which this wave may not grant.

So the run has no admitted beat, **and the payload says so in words, with the two grant
rows cited, and points at the endpoint where the admission IS proved.** A field —
`admission_beat: null` with a stated `admission_absent_reason` and
`admission_proved_by: "POST /v1/demo/gate-run"` — is the honest form. A fifth beat with
`outcome: "skipped"` dressed to look passing is not, and neither is silence.

The beats:

| # | name | statement | expectation, as measured |
|---|---|---|---|
| 1 | `read` | the CR row, its projected `open_blocking` **beside** the count re-derived by the gate's own anti-join, its four named CHECKs, and the obligation's `severity_gate`, `virulence` and `origin` | `00000`, read-only, `counters_agree: true` |
| 2 | `kernel_procedure` | `CALL mainline.merge_change_request(...)` — what a legitimate caller does | **`23503` `cr_legal_edge`** — refused before the gate, because `checks_materialised → merged` is not an edge in `mainline.subject_transition`; an illegal transition here is not refused by a rule, it is **not representable** |
| 3 | `merge` | `UPDATE mainline.change_request SET state='merged', head_seq=head_seq+1, merged_commit=… WHERE cr_id=… AND head_seq=…` | **`23514` `cr_gate_closed_when_merged`**, constraint name **reported by the driver** |
| 4 | `projection_drift_attack` | `UPDATE … SET open_blocking = 0` out of band, then the same merge statement again | **`P0001` `mainline.fn_cr_merge_gate`**, message naming the re-derived count `1` against the projected `0` |

**Beat 2 is conditional and W3 must measure before shipping it.** If the deployed cluster
answers `42501` rather than `23503` — because a grant this repository declares was never
applied — beat 2 is **dropped**, and the measurement is recorded in W1's evidence file with
the SQLSTATE that caused the drop. A privilege error on screen is not a gate refusal, and
presenting one as the other would be the exact fabrication this repository refuses.

**`matched_expectation` and `verdict` work exactly as gate-run's do.** A beat that answers
something other than what it was written against still returns `200`; the run says
`NOT PROVEN`, and saying so is the whole discipline. No beat is declared successful because
it did not raise.

---

### R4 · THE PERSISTENCE PROOF IS CR-SCOPED, AND IT ADDS READINGS WITHOUT REMOVING ANY.

**Authority: `docs/deploy/gate-run-contract.md` §3 and ruling R2 in
`docs/leads/cloud-hardening-final.md`, which is what lets a persistence contract move at
all; and measurement M8.**

Three readings, taken before the transaction opens and again after it closes, both in the
payload:

1. **The ten unscoped whole-table counts, unchanged and unnarrowed.** Copy
   `_FINGERPRINT_SQL` and `_FINGERPRINT_TABLES` as they stand. No table leaves the list.
   Two tables the CR path touches — `mainline.change_request` and `mainline.cr_event` —
   are **not** in the ten; add them to the CR-scoped reading below, never by editing the
   ten. Same reason gate-run gives: the ten prove something about the DATABASE and are
   deliberately broad.
2. **A CR-scoped reading.** The `change_request` row — `state`, `head_seq`, `gate_epoch`,
   `open_blocking`, `open_conflicts`, `open_residue`, `merged_commit` — plus
   `count(*) FROM mainline.cr_event WHERE cr_id = …` and
   `count(*) FROM mainline.merge_record WHERE cr_id = …`.
3. **The run-scoped witness.** Gate-run's is a `uuid4` its admitted beat minted. This run
   admits nothing, so **the witness is the CR row itself**: beat 4 forces `open_blocking`
   to `0` in-transaction (M8 — the database admits that write), and after the rollback the
   column must read `1` again. That zero is a value **this run wrote and no other caller
   did**, and its disappearance settles this run's own claim. `self_persisted` keys on the
   CR row being identical before and after **and** on the two CR-scoped counts being
   unchanged. `identical` still reports the ten counts, and the VERDICT keys on the
   run-scoped evidence — the same split, for the same reason, as
   `docs/diagnosis/gate-run-fingerprint.md` records.

`persisted: false` in the payload is a **conclusion from readings that are in the payload
beside it**, never an assertion.

---

### R5 · THE LIST ROUTE IS `GET /v1/change-requests/{cr_id}/blocking-checks`, KEY `cr_blocking_checks`, GOVERNED BY THE EXISTING `blocking-check.schema.json`.

**Authority: measurements M9, M10, M12.**

The permit's mirror is `/v1/permits/{permit_id}/blocking-checks`; the CR's path is the same
shape with the CR's collection and parameter. Not `/checks` — the console already probes
`/blocking-checks` (M12) and a route that answers a path the console never asks for closes
nothing.

**No new contract.** `blocking-check.schema.json` already requires `subject_kind` /
`subject_id` rather than `permit_id` (M9), and `envelope.resource` has no enum (M10). The
CR read emits `subject_kind: "change_request"`, `subject_id: <cr_id>`,
`resource: "cr_blocking_checks"` and the **same** `$id`. If any pointer in that schema turns
out to be permit-shaped in practice, W4 widens it in `console/contracts/` and W2 does not
touch it.

---

### R6 · EVERY ROUTE IS DECLARED IN FOUR TABLES OR IT IS NOT SHIPPED.

**Authority: `app.py::_routes()`'s own record of the demo's headline defect — every beat
implemented and none of it reachable, because the routing table had sixteen rows.**

For each of the two new routes:

1. `app.py::_routes()` — a `Route` row.
2. `console/src/data/resources.ts` — a `declare()` call **and** an entry in
   `RESOURCE_KEYS` (the module's own load-time assertion fails otherwise).
3. `envelope.SCHEMA_IDS` (reads) or the endpoint's own `$id` constant (the demo endpoint),
   plus `reads.READS` / `transitions.TRANSITION_RESOURCES` for the implementation.
4. `console/src/data/contracts.ts` — for `cr-gate-run.schema.json`, an explicit `?raw`
   import line and a `CONTRACT_SOURCES` entry. No glob.

`test_routes_gate_run.py::test_the_table_and_the_console_declaration_are_the_same_eighteen`
becomes **twenty** and keeps its job: the two tables must be the same set, so a *second*
undeclared route is still a failure. W2 renames and updates it; the assertion may not be
weakened to a subset check.

The demo API's `contracts/cr-gate-run.schema.json` is the **original**; the copy in
`console/contracts/` is byte-for-byte, and `console/tests/unit/data/contracts.test.ts`
gains the third drift pairing on the same terms as `gate-run` and `subjects`.

---

### R7 · NO COMMITTING CHANGE-REQUEST ROUTE. AND HERE IS THE HAZARD THAT MAKES THAT MORE THAN A PREFERENCE.

**Authority: source measurement of `transitions._demo_guard`, this session.**

`_demo_guard` decides on `subject_id == scenario.permit_id`. **A CR identifier never equals
the permit identifier.** So a mutating CR transition would fall past the
`demo_subject_write_protected` branch, reach `_demo_subject_is_established`, find the
permit **is** seeded, and return `None` — *let it through*. A committing
`POST /v1/change-requests/{cr_id}/merge` added to `TRANSITION_RESOURCES` with
`mutates = True` would therefore be an **unguarded, irreversible, unauthenticated write
path on the seeded demo CR.** The guard would not catch it. That is not a hypothetical: it
is the same shape as the defect `evidence/deploy/demo-guard-armed.json` recorded, one
subject over.

Therefore:

* The CR gate run is registered as `"cr_gate_run": (None, None, False)` — the same
  `(param, procedure, mutates)` shape as `demo_gate_run` — so `handle_transition` takes the
  `param_name is None` branch and `_demo_guard` is never consulted, because there is
  nothing to guard: the transaction rolls back.
* **No worker adds a `Route` with a `{cr_id}` path parameter and a mutating resource key.**
* `transitions._demo_guard` is **not** widened in this wave. Extending it to cover CR
  identifiers would only be needed by a committing route this wave does not add, and
  editing the guard to prepare for one is how the route gets added next week without the
  argument being had. W1 records the hazard in the measurements file so the founder can
  rule on it separately.

---

### R8 · NOTHING IS GRANTED, MIGRATED, SEEDED, OR DEPLOYED.

**Authority: the brief's absolute prohibitions, plus M3/M4 which make the build possible
without any of them.**

No `GRANT`. No migration. No edit to `db/seeds/demo/demo_world.sql` — it is frozen by
`tests/ci/test_demo_seed_is_frozen.py`, the live deployment is seeded from it, and R2's
design needs nothing from it. **Never `terraform apply`, never redeploy, never touch AWS,
never write an SSM parameter, never print a credential.** The orchestrator deploys. Leave
the tree; **do not commit.**

`DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` does not move. Console headroom is **1,325 B**
(`tests/deploy/test_furl_compression.py:98`) with a guard failing below 1,024. W4 measures
before and after and spends bytes in the **`operator` entry** rather than the main chunk.

---

### R9 · THE FILM BLOCKS LAND IN A NEW FILE AND RENUMBER NOTHING.

**Authority: mine, on the working-tree state — `docs/demo/film/VO-DEMO.md` is already
modified by another hand this session, and `BEATS.yaml` / `VO-CLOSE.md` belong to the film
lead and to the close-trim worker.**

New material goes to `docs/demo/film/VO-DEMO-CR.md` as blocks **B9, B10, B11**, sited after
`B8 · NONE OF IT PERSISTED` at `[2:00]`, in the existing block format —
`### B9 · TITLE — [m:ss] · N s · **W w** · **R w/s**`, voice above, screen actions beneath.
Nothing existing is renumbered; the film lead splices.

Budget: **22-26 s across the three blocks**, which is the time the naming close returns
(50 s → ~22 s). Register is set by the existing lines and they are the standard —
*"Nobody typed that four"*, *"Not a checkbox — a question"*, *"An attacker who owns the
counter does not own the gate."* Concrete, short, no jargon that is not immediately cashed
out, no marketing.

The idea the blocks exist to land, in one sentence a judge already asked silently:
**you cannot USE a clause the blame reaches, and you cannot quietly EDIT AWAY the clause the
blame reaches either.**

---

### R10 · NO FAKING, NO REGRESSION, MEASURED NOT ASSUMED.

Every SQLSTATE, constraint name, message, latency and digest on screen or in a document is
what the kernel returned, obtained from the driver's error object through
`refusal.diagnose`. The contest rules say the project must function as depicted, so a
staged beat is a rules violation and not merely a lie.

Baseline to hold: **998 collected / 997 passed / 0 failed / 0 errors**; gate proof `PROVEN`
caveat-free. `HONESTY.md`, `CI-STATE.md`, ratchets and assertions are not weakened;
`continue-on-error` and `|| true` are banned.

---

## 2 · THE SURFACE, AFTER THIS WAVE

```
GET  /v1/change-requests/{cr_id}                     unchanged (200 today)
GET  /v1/change-requests/{cr_id}/blocking-checks     NEW   key cr_blocking_checks
                                                           blocking-check.schema.json
POST /v1/demo/cr-gate-run                            NEW   key cr_gate_run
                                                           cr-gate-run.schema.json
                                                           no path parameter, rolls back
```

Twenty `Route` rows, nineteen paths, twenty console resource declarations. No committing
change-request route, in this wave or by accident.

---

## 3 · THE SIX WORKERS

Paths are literally enumerated and disjoint. No worker edits a file another worker owns.

| id | title | owns |
|---|---|---|
| W1 | Live grant and gate measurement | `evidence/demo/cr-gate/**`, `docs/demo/cr-gate-measurements.md` |
| W2 | API surface — routing and the CR blocking-checks read | `demo-api/src/.../app.py`, `reads.py`, `envelope.py`, and four of its tests |
| W3 | The CR gate run engine and its contract | `demo-api/src/.../cr_gate_run.py` (new), `transitions.py`, `scenario.py`, `demo-api/contracts/cr-gate-run.schema.json`, two tests |
| W4 | Console — declaration, contract copy, and the change screen | `console/src/data/resources.ts`, `contracts.ts`, `console/contracts/cr-gate-run.schema.json`, `console/src/operator/change/**`, `console/src/operator/kernel/reads.ts`, three test paths |
| W5 | End-to-end proof against the live kernel | `scripts/proof/cr_gate_refusal.py` (new), `evidence/deploy/cr-gate-live.json`, `qa/cr-gate-live.json`, `tests/deploy/test_cr_gate_proof.py` |
| W6 | The film blocks | `docs/demo/film/VO-DEMO-CR.md`, `CLAIMS-CLEARANCE-CR.md`, `CLICKS-CR.md` (all new) |

**Order.** W1 first and it gates W3's beat-2 decision. W2 and W3 run in parallel and meet
at the `Route` row (W2 writes it, W3 writes the dispatcher key). W4 follows W2/W3's
resource keys. W5 runs last, after the orchestrator deploys. W6 runs in parallel with
everything but its numbers must be re-derived from W5's transcript before the film is cut.

**Coordination points, written down so they are not discovered:**

* W2 adds **both** `Route` rows, including `POST /v1/demo/cr-gate-run`. W3 adds the
  `TRANSITION_RESOURCES` key and the dispatch branch. Neither is a route until both land,
  and `test_every_routed_post_is_a_declared_transition_resource` will say so.
* W3 owns `scenario.py`; if `Scenario` gains `cr_id`, W3 writes it and keeps
  `EXPECTED` / `_selfcheck` consistent. W2 does not touch that file.
* W3 writes `demo-api/contracts/cr-gate-run.schema.json`; W4 copies it byte for byte into
  `console/contracts/` and adds the drift pairing. The demo API owns the original.

---

## 4 · WHAT WOULD MAKE THIS WAVE FAIL

* A committing CR route added because the demo endpoint felt indirect — see R7.
* `GRANT INSERT ON mainline.cr_event TO mainline_api` typed to make beat 2 work — see R2.
* A fifth beat marked "skipped" standing in for the admission that cannot be played — R3.
* A `persisted: false` that is asserted rather than read off two fingerprints in the same
  payload — R4.
* A route that works and is declared in three tables instead of four — R6.
* A number in `VO-DEMO-CR.md` typed from this document rather than re-derived from the
  filmed run — R9, R10.
