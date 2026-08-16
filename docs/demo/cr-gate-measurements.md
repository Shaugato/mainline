<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CR-GATE MEASUREMENTS — W1

**Worker W1 · live grant and gate measurement · 2026-08-16 · repo HEAD `240cff1`**
Lead plan: `docs/demo/cr-gate-route-plan.md`. Its rulings bind this file; where a measurement
here contradicts the plan, the measurement wins and says so out loud.

Live origin measured, read-only: `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
Kernel measured: `postgresql://root@localhost:26257/mainline_demo` — **LOCAL NODE ONLY**,
CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5).

**Nothing in this file is transcribed from the brief or from the plan.** Every status code,
byte count, elapsed time, SQLSTATE, constraint name and message below came out of an HTTP
response or out of psycopg's `Diagnostic` object in this session. Raw transcripts are under
`evidence/demo/cr-gate/`, indexed in §8.

**Nothing touched AWS.** No `terraform apply`, no redeploy, no SSM parameter, no credential
printed or read. No `GRANT` was issued to the cloud cluster; the one node that was granted
is the Docker CockroachDB on `localhost:26257`. Nothing was committed.

---

## 0 · THE ONE FACT W3 IS WAITING FOR

> ### Beat 2 answers **`42501`**, not `23503 cr_legal_edge`. **DROP BEAT 2.**

Driven as `mainline_api`, `CALL mainline.merge_change_request(...)` on
`dec0de00-000c-4000-8000-000000000001` from `checks_materialised` is refused with:

```
SQLSTATE        42501
constraint      None          (the driver reported no constraint name)
table           None          (the driver reported no table name)
message_primary user mainline_api does not have INSERT privilege on relation cr_event
```

Ruling **R3** says: *"If the deployed cluster answers `42501` rather than `23503` … beat 2 is
**dropped**, and the measurement is recorded in W1's evidence file with the SQLSTATE that
caused the drop. A privilege error on screen is not a gate refusal."* That condition is met.
**Beat 2 is dropped.** The run keeps three beats — `read`, `merge`, `projection_drift_attack`
— and each of those is measured below and answers exactly what R3 wrote it against.

**Why, measured rather than reasoned.** Step 5 of `mainline.merge_change_request` is the
procedure's *first write* and it is unconditionally `INSERT INTO mainline.cr_event` (migration
`0118_proc_merge_change_request.sql`, "── 5 · APPEND THE TRANSITION EVENT ──"). CockroachDB
checks the privilege on that statement before it evaluates `cr_legal_edge`. So there is **no
change-request state from which this procedure reaches the gate as `mainline_api`** — not
`checks_materialised`, not `dispositioned`. The plan's R2 predicted the `42501` for the
`dispositioned` arm and the `23503` for the `checks_materialised` arm; the measurement says
both arms give `42501`, because it is the same statement in both.

**EXECUTE was NOT the obstacle, and no EXECUTE grant was issued.** Measured:

```
has_function_privilege('mainline_api',
    'mainline.merge_change_request(UUID, BYTES, STRING, STRING, JSONB, BYTES, INT2, BYTES)',
    'EXECUTE')                                   ->  true
pg_proc.proacl for mainline.merge_change_request ->  NULL  (no explicit ACL)
has_function_privilege('public', <same signature>, 'EXECUTE')
                                                 ->  true
```

`GRANTS.yaml` declares no `EXECUTE` row and `scripts/deploy/cloud_roles.py::API_ROUTINES` is
`("mainline.merge_permit", "trappoint.explain_refusal")` — `merge_change_request` is in
neither. The `true` above is CockroachDB's platform default for `PUBLIC` on a routine with a
`NULL` ACL. The procedure runs; it dies on the table privilege inside it.

**A control attempt proves the role switch was real.** Before beat 2, the same transaction
issued a bare `INSERT INTO mainline.cr_event (...)` and got back the identical message —
`42501`, *"user mainline_api does not have INSERT privilege on relation cr_event"*. The
session was genuinely de-privileged; `SET ROLE` did what it claims.

---

## 1 · THE LIVE-ORIGIN BASELINE — READ-ONLY, RE-DRIVEN THIS SESSION

Nine requests, `2026-08-16T03:53:05Z`. Eight are `GET`. The one `POST` is
`/v1/demo/gate-run`, which the deployment's own contract rolls back — and which reported
`persisted: false` off its own fingerprint on this run, as it must.

| request | status | bytes | elapsed |
|---|---:|---:|---:|
| `GET /v1/health` | 200 | 409 | 0.852 s |
| `GET /v1/routes` *(any undeclared path)* | 404 | 631 | 0.264 s |
| `GET /v1/change-requests/dec0de00-000c-…` | 200 | 3,295 | 0.398 s |
| `GET /v1/checks/dec0de00-000d-…/disposition` | 200 | 3,850 | 0.329 s |
| `GET /v1/demo/subjects` | 200 | 8,941 | 0.330 s |
| `GET /v1/change-requests/dec0de00-000c-…/checks` | **404** | 684 | 0.263 s |
| `GET /v1/change-requests/dec0de00-000c-…/blocking-checks` | **404** | 693 | 0.277 s |
| `POST /v1/change-requests/dec0de00-000c-…/merge` | **404** | 684 | 0.264 s |
| `POST /v1/demo/gate-run` | 200 | 10,500 | 2.484 s |

**`/v1/health`**, verbatim in `evidence/demo/cr-gate/raw/health.json`:
`ok: true`, `database: mainline_demo`, `deploy_chain_applied: 271` of `deploy_chain_files: 271`,
`migrations_applied: 0`,
`schema_fingerprint: ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339`,
`cluster_version: CockroachDB CCL v26.2.5 …`, `seconds: 0.023`.

**The 404 route table** lists **seventeen paths**, unchanged from the plan's §0.1:

```
/v1/audit                                      /v1/permits/{permit_id}
/v1/change-requests/{cr_id}                    /v1/permits/{permit_id}/blocking-checks
/v1/checks/{check_id}/disposition              /v1/permits/{permit_id}/checks:materialise
/v1/clauses/{clause_uuid}/ancestry             /v1/permits/{permit_id}/merge
/v1/clauses/{clause_uuid}/versions/{commit_id} /v1/permits/{permit_id}/silence
/v1/demo/gate-run                              /v1/permits/{permit_id}/suspend
/v1/demo/subjects                              /v1/recall-runs/{run_id}
/v1/ledger                                     /v1/receipts/{receipt_id}
/v1/lessons/{lesson_id}/propagation
```

The `POST …/merge` 404 body says, in the deployment's own words:
`"detail": "no resource is declared at POST /v1/change-requests/dec0de00-000c-4000-8000-000000000001/merge"`.
**Seventeen paths is eighteen `Route` rows** — every worker counts rows, never the 404 body
(plan §0.1).

**The CR read** returns `state: checks_materialised`, `open_blocking: 1`, `open_conflicts: 0`,
`open_residue: 0`, `head_seq: 1`, `gate_epoch: 1`, `merged_commit: null`,
`external_ref: DEMO-MOC-0001`, `ref_name: refs/changes/demo-0001`, and four named CHECKs read
out of `pg_constraint`: `cr_gate_closed_when_merged`, `cr_merge_evidence`,
`cr_conflicts_resolved_when_merged`, `cr_identity_conserved_when_merged`. All four carry
`blamed_by_refusal: false` — nothing has been refused yet, because there is no route to try.

**The obligation read** returns `virulence: blood_major`, `signed: null`,
`reading_floor: null`, five `lattice` rows — all `blood_major`, all `policy_version cl-1.0`:
`applied` (rank 3), `mitigated` (rank 3), `escalated` (rank 3), `mechanism_absent` (rank 4,
the only one requiring a predicate), `emergency_override` (rank 5); every one but `applied`
requires a second signer — and
three defeater options sharing `vocab_sha256 d9c837c25bb174d1afd6b22f9496dcb197ffa6c69e5562b8fe76e3300fea3bbe`:
`CONTROL_PRESERVED_BY_EDIT`, `EDIT_OUTSIDE_BLAMED_ANCHOR`, `PRECURSOR_ANSWERED_ELSEWHERE`.

**The gate run**, `run_id e3fcc34b-f17b-4d6b-954b-b8bf2bf8fcd0`: `verdict: PROVEN`,
`outcome: completed`, `persisted: false`, `persistence_check.identical: true`,
`persistence_check.self_persisted: false`, `transaction.single_transaction: true`,
`transaction.disposition: rolled_back`, `isolation: SERIALIZABLE`, opened and closed logical
timestamps both `1786852385164377793.0000000000`, savepoints
`gate_run_beat_2 / gate_run_beat_3 / gate_run_beat_4`. Its four beats:

```
1 read                       00000
2 merge                      23514  gate_closed_when_issued
3 projection_drift_attack    P0001  mainline.fn_permit_merge_gate
4 admit                      00000
```

all four `matched_expectation: true`.

**Two numbers moved between the plan's run and mine, and both are honest.** The plan recorded
10,499 B / 2.82 s; I measured **10,500 B / 2.484 s**. The body carries a fresh `run_id` and
fresh timestamps on every call, so the byte count is not stable to the byte and the latency is
not stable at all. The payload's own `elapsed_ms` was **2050.872** — the server's measure —
against my **2.484 s** wall clock, the difference being transport and Lambda. **Anyone putting
a byte count or a latency on screen must re-derive it from the filmed run** (R9, R10).

---

## 2 · THE LOCAL ROLE — WHAT WAS GRANTED, AND THE PROOF THAT NOTHING ELSE WAS

`mainline_api` existed on the local node with **zero** table privileges in `mainline_demo`
before this session; so did `auditor_ro`, `agent_gate`, `svc_disposition` and
`mainline_judge`. The three memberships `GRANTS.yaml` declares for `mainline_api` were
**already** in place and were not issued by me.

**The statements were not hand-typed.** `verticals/mainline/db/GRANTS.yaml` was parsed by the
repository's own `trappoint_migrate.grants`, the document was filtered to the rows naming
`mainline_api`, and the repository's own builders rendered **72 statements** from that
filtered document — which is, statement for statement, what `trappoint migrate grants` would
apply for this one role. Deliberately excluded, each for a stated reason:

* every row naming another role — this node carries other workers' fixtures;
* `revocations:` — both rows target `public`, not `mainline_api`;
* `EXECUTE` on routines — `GRANTS.yaml` declares none (see §0).

**Readback against the matrix, in both directions** (`evidence/demo/cr-gate/grants-verified.json`):

| dimension | declared | in cluster | **extra in cluster** |
|---|---:|---:|---|
| table privileges | 76 | 75 | **none** |
| schema privileges (granted to this role) | 5 | 5 | **none** |
| memberships | 3 | 3 | **none** |

`no_privilege_beyond_the_matrix: true`. The one declared privilege that did not land is
`trappoint.deploy_chain:SELECT`, refused `42P01` — **that relation is not in this local
database**. It is a local fidelity gap, not a grant that was withheld, and it touches nothing
on the CR path.

**The two rows that decide everything below:**

```
mainline.change_request   SELECT, UPDATE
mainline.cr_event         SELECT            <- no INSERT
```

and the write surface, measured with `has_table_privilege` rather than read off the YAML:

```
                            SELECT  INSERT  UPDATE  DELETE
mainline.change_request       yes     no      yes     no
mainline.cr_event             yes     no      no      no
mainline.blocking_check       yes     no      yes     no
mainline.disposition          yes     yes     no      no
mainline.exposure_receipt     yes     no      no      no
mainline.exposure_line        yes     no      no      no
```

The last two lines are the standing `materialise_checks` finding, measured. **No `INSERT` was
granted on `mainline.cr_event`, `mainline.exposure_receipt` or `mainline.exposure_line`, and
none is proposed.** Widening the write surface of an endpoint on a Function URL carrying
`authorization_type = NONE` is the founder's call and he has not made it.

**One inherited reach, recorded because it is not nothing.** `SHOW GRANTS … FOR mainline_api`
expands role membership. Separating the rows by grantee shows `mainline_qa:USAGE` held by
`agent_gate`, `auditor_ro` and `svc_disposition` on this local node — so `mainline_api`
*reaches* `mainline_qa` by inheritance, though nothing granted it there. `GRANTS.yaml`'s own
header says `mainline_api` "holds … nothing whatever in `mainline_qa`" and that the schema is
revoked from it on every provisioning run (S14). This was pre-existing local state, I did not
create it, no CR-path statement touches `mainline_qa`, and it is the same open coupling
`GRANTS.yaml` already records about the three memberships. **Reported, not acted on.**

---

## 3 · THE PROBE — ONE `SERIALIZABLE` TRANSACTION, SAVEPOINT-FENCED, ROLLED BACK

Driven as `mainline_api` (`session_user = root`, `current_user = mainline_api`, confirmed
again from inside the transaction). `SHOW transaction_isolation` returned **`serializable`**.
`cluster_logical_timestamp()` at the first beat and after the last were **identical** —
`1786853730469766074.0000000000` — the read-only witness that all five attempts shared one
transaction. The transaction was terminated by **`ROLLBACK`**.
Raw: `evidence/demo/cr-gate/role-probe.json`.

| # | attempt | outcome | SQLSTATE | constraint | driver's `message_primary` |
|---|---|---|---|---|---|
| A0 | control — `INSERT INTO mainline.cr_event (…)` | REFUSED | `42501` | *(none)* | `user mainline_api does not have INSERT privilege on relation cr_event` |
| A1 | `CALL mainline.merge_change_request(…)` | REFUSED | **`42501`** | *(none)* | `user mainline_api does not have INSERT privilege on relation cr_event` |
| A2 | bare merge `UPDATE` | REFUSED | **`23514`** | **`cr_gate_closed_when_merged`** | `failed to satisfy CHECK constraint ((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))` |
| A3a | `UPDATE … SET open_blocking = 0` out of band | **ADMITTED** | `00000` | — | — |
| A3b | the same merge `UPDATE`, under the forged counter | REFUSED | **`P0001`** | *(none)* | `MAINLINE: merge refused by mainline.fn_cr_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero` |

The statements, exactly as issued:

```sql
-- A1
CALL mainline.merge_change_request(%s, %s, %s, %s, %s, %s, %s, %s)

-- A2 and A3b (identical text, run twice)
UPDATE mainline.change_request
   SET state = 'merged', head_seq = head_seq + 1,
       merged_commit = digest('probe', 'sha256')
 WHERE cr_id = %s AND head_seq = %s

-- A3a
UPDATE mainline.change_request SET open_blocking = 0 WHERE cr_id = %s
```

**A2 and A3b are the exhibits, and `mainline_api` reaches both.** They need exactly
`UPDATE mainline.change_request` — held — plus the `SELECT`s the trigger cascade already has.
Neither needs a grant this wave does not have, and neither touches `mainline.cr_event`.

**A3a is admitted, and that is the point of A3b.** Both triggers on the table carry a `WHEN`
clause that does not fire on a counter-only write. Verbatim from `pg_get_triggerdef`:

```
CREATE TRIGGER cr_merge_gate BEFORE UPDATE ON mainline_demo.mainline.change_request
  FOR EACH ROW WHEN ((new).state = 'merged':::mainline.subject_state)
                AND ((old).state != 'merged':::mainline.subject_state)
  EXECUTE FUNCTION mainline_demo.mainline.fn_cr_merge_gate()

CREATE TRIGGER z_cbm_gate_cr BEFORE UPDATE ON mainline_demo.mainline.change_request
  FOR EACH ROW WHEN ((new).state = 'merged':::mainline.subject_state)
                AND ((old).state != 'merged':::mainline.subject_state)
  EXECUTE FUNCTION mainline_demo.mainline.fn_cbm_gate_cr()
```

**Note the second conjunct.** The brief and the plan both say these triggers carry
`WHEN NEW.state = 'merged'`; they also carry `AND OLD.state != 'merged'`. Anyone quoting a
trigger definition on screen must quote both halves or quote neither.

**The gate is welded to the TABLE, not to the procedure** — a `CHECK` on the column and two
`BEFORE UPDATE` triggers. Measured from `pg_constraint` on the local node, the four CHECKs the
live read also returns:

```
cr_gate_closed_when_merged         CHECK ((state != 'merged') OR (open_blocking = 0))
cr_merge_evidence                  CHECK ((state != 'merged') OR (merged_commit IS NOT NULL))
cr_conflicts_resolved_when_merged  CHECK ((state != 'merged') OR (open_conflicts = 0))
cr_identity_conserved_when_merged  CHECK ((state != 'merged') OR (open_residue = 0))
```

---

## 4 · THE ROOT CONTRAST — SO "THE DIFFERENCE IS THE GRANT" IS MEASURED, NOT ASSUMED

The identical statements in the identical transaction shape, as a fully privileged role.
Raw: `evidence/demo/cr-gate/root-contrast.json`. One transaction, rolled back, row unchanged.

| # | attempt | as `root` | as `mainline_api` |
|---|---|---|---|
| 1 | `CALL mainline.merge_change_request(…)` | **`23503 cr_legal_edge`** — `insert on table "cr_event" violates foreign key constraint "cr_legal_edge"` | **`42501`** — no `INSERT` on `cr_event` |
| 2 | bare merge `UPDATE` | `23514 cr_gate_closed_when_merged` | `23514 cr_gate_closed_when_merged` |
| 3a | force `open_blocking = 0` | ADMITTED `00000` | ADMITTED `00000` |
| 3b | merge under the forged counter | `P0001 mainline.fn_cr_merge_gate` | `P0001 mainline.fn_cr_merge_gate` |

**The difference between `23503` and `42501` is exactly one privilege — `INSERT` on
`mainline.cr_event` — and nothing else.** Rows 2, 3a and 3b are identical under both roles,
which is what makes the three surviving beats safe to ship.

Confirming the plan's **M1** on the local node: `('change_request', 'checks_materialised',
'merged')` is **not** an edge. `mainline.subject_transition` holds, for `change_request`:
`draft→checks_materialised`, `draft→abandoned`, `checks_materialised→checks_materialised`,
`checks_materialised→dispositioned`, `dispositioned→checks_materialised`,
`dispositioned→merged`, `merged→suspended`, `merged→closed`, `suspended→closed`.
So `cr_legal_edge` is a real refusal that a privileged caller really gets — it is simply not
one an anonymous caller can ever reach.

---

## 5 · AFTER THE `ROLLBACK` — NOTHING MOVED

Read back on a fresh statement after the transaction closed, with `RESET ROLE`:

| column | before | inside the txn, after A3a | after `ROLLBACK` |
|---|---|---|---|
| `state` | `checks_materialised` | `checks_materialised` | `checks_materialised` |
| `open_blocking` | `1` | **`0`** | **`1`** |
| `open_conflicts` | `0` | `0` | `0` |
| `open_residue` | `0` | `0` | `0` |
| `head_seq` | `1` | `1` | `1` |
| `gate_epoch` | `1` | `1` | `1` |
| `merged_commit` | `NULL` | `NULL` | `NULL` |
| `cr_event` rows for this CR | `1` | `1` | `1` |
| `merge_record` rows for this CR | `0` | `0` | `0` |

`unchanged_after_rollback: true` — the whole before-row and the whole after-row compared
equal, not column by eye.

**That `0` in the middle column is the run-scoped witness R4 asks for.** It is a value this
transaction wrote and no other caller did; it was visible inside the transaction and it is
gone after it. The same readback under `root` (§4) is also unchanged.

---

## 6 · R7 — THE HAZARD, RECORDED FOR THE FOUNDER. NOTHING PROPOSED, NOTHING CHANGED.

Read from `git show HEAD:verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py`
— **at HEAD `240cff1`, not from the working tree**, because other workers are editing that
file in this session and a quotation contaminated by an in-flight edit would be worthless.
Raw: `evidence/demo/cr-gate/r7-demo-guard.json`.

```python
# line 509
    if subject_id == scenario.permit_id:
        return _error(423, "demo_subject_write_protected", …)

# line 523
    if _demo_subject_is_established(conn, scenario):
        return None

# line 473, inside _demo_subject_is_established
        row = positional(conn, _DEMO_SUBJECT_SQL, (scenario.permit_id,)).fetchone()

# the SQL it asks it with
_DEMO_SUBJECT_SQL: Final = "SELECT 1 FROM mainline.permit WHERE permit_id = %s"
```

**The decision trace for a change-request identifier:**

1. `subject_id` = `dec0de00-000c-4000-8000-000000000001`, a change request.
2. `scenario.permit_id` is the seeded **permit** — a different UUID, always.
3. Line 509 compares them: **false**. The `423 demo_subject_write_protected` branch is
   **not** taken.
4. Line 523 asks `_demo_subject_is_established`, which asks
   `SELECT 1 FROM mainline.permit WHERE permit_id = <the permit>`.
5. The seeded **permit** is present, so that read returns a row and the function returns
   `True`.
6. Line 524: **`return None` — let it through.**

**Consequence.** A committing `POST /v1/change-requests/{cr_id}/merge`, registered in
`TRANSITION_RESOURCES` with `mutates = True`, would be an **unguarded, irreversible,
unauthenticated write on the seeded demo change request**, on a Function URL carrying
`authorization_type = NONE`. The guard would not catch it — it would return `None`. This is
the same shape as the defect `evidence/deploy/demo-guard-armed.json` records, one subject
over.

**This wave adds no committing change-request route and does not widen `_demo_guard`.**
Widening it is only needed by a route this wave does not add, and editing it now is how that
route arrives later without the argument being had. **This is a finding for the founder. W1
proposes nothing.**

---

## 7 · CAVEATS, STATED RATHER THAN BURIED

1. **The deployed cluster was not probed as `mainline_api`.** No AWS was touched and no
   credential was read, by instruction. The local role was built from *the repository's own
   declaration* of what the deployed role holds. If the deployed cluster carries an
   **undeclared** `INSERT` on `mainline.cr_event` — drift of exactly the kind `GRANTS.yaml`'s
   header records having happened before, when thirteen relations were hand-granted against
   the live cluster and never written down — then beat 2 would answer `23503` there and not
   `42501`. **The honest default is still to drop beat 2**: shipping a beat that shows a
   privilege error as though it were a gate refusal is the fabrication this repository
   refuses, and a beat that is dropped costs nothing but seconds. **W5's live proof settles
   the question after the orchestrator deploys**; if it comes back `23503`, beat 2 can be
   reinstated on that evidence and on nothing else.
2. **`trappoint.deploy_chain` is absent from the local database** (`42P01`), so one declared
   `SELECT` did not land. It touches no CR-path statement.
3. **`mainline_qa:USAGE` is reachable by membership inheritance on this local node** — see
   §2. Pre-existing, not created here, not acted on.
4. **`mainline.merge_change_request` is `EXECUTE`-able by `mainline_api` only because
   CockroachDB defaults a `NULL` routine ACL to `PUBLIC`.** No grant in this repository says
   so. If a future revocation closes that default, beat 2 would answer `42501` for a second,
   independent reason.
5. **No admission beat is playable for the CR, and §2 measures why.** `mainline.exposure_receipt`
   holds one row, `subject_kind = permit`, and its one `exposure_line` points at the permit's
   check `dec0de00-0007-…` — not the CR's `dec0de00-000d-…`. Minting one needs `INSERT` on
   `exposure_receipt` / `exposure_line`, which `mainline_api` does not hold (measured `false`,
   §2) and which this wave may not grant. R3's `admission_beat: null` with a stated reason is
   the honest form.
6. **The CR obligation, measured on the local node:** `check_id dec0de00-000d-4000-8000-000000000001`,
   `subject_kind change_request`, `origin blame_ancestry`, `severity 4`, `virulence blood_major`
   — which agrees with the live disposition read.

---

## 8 · EVIDENCE INDEX

All under `evidence/demo/cr-gate/`.

| file | what it holds |
|---|---|
| `live-baseline.json` | the nine live requests: status, byte count, elapsed, content-type |
| `raw/*.json` | the nine response bodies **verbatim**, byte for byte as returned |
| `grant-apply.json` | the 72 rendered statements, what was applied, what was missing, before/after |
| `grants-verified.json` | matrix-vs-cluster diff in both directions; `no_privilege_beyond_the_matrix: true` |
| `role-probe.json` | the five attempts as `mainline_api`, with full driver diagnostics and the readbacks |
| `root-contrast.json` | the same statements as `root`, plus the privilege introspection |
| `kernel-objects.json` | CHECKs, trigger definitions, legal edges, procedure ACLs, the CR obligation, the write surface |
| `r7-demo-guard.json` | the guard's source at HEAD `240cff1` and the decision trace |

**Regression check.** `tests/integration/schema/test_privilege_conformance.py`,
`verticals/mainline/apps/demo-api/tests/test_privilege_census.py` and
`tests/deploy/test_cloud_roles_reads_the_matrix.py`, run from `--junitxml` after the grant
landed: **60 tests / 0 failures / 0 errors / 0 skipped**, 309.35 s. No product code was
written by W1 and the full 998-collected baseline is untouched by this worker.
