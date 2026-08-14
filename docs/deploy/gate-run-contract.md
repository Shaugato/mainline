<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `POST /v1/demo/gate-run` — the contract, the transaction discipline, and why the demo persists nothing

**Owner:** `w4-api-transitions`.
**Implementation:** `verticals/mainline/apps/demo-api/src/mainline_demo_api/gate_run.py`.
**Governing schema:** `verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`
(`$id` `https://console.mainline.trappoint.org/contracts/1.0/gate-run.schema.json`).
**Measured:** 2026-08-10, CockroachDB CCL v26.2.5, local single node, database
`w_w4_api_transitions`, migration chain **271/271 applied, 0 failed**.

---

## 1. What the endpoint is for

One HTTP call plays the whole product in four beats and returns what the **database** said
at each one:

| # | Beat | Expected outcome | SQLSTATE | Exhibit | How the exhibit was obtained |
|---|---|---|---|---|---|
| 1 | `read` | `read` | `00000` | — | — |
| 2 | `merge` | `refused` | `23514` | `gate_closed_when_issued` | **reported** by the driver |
| 3 | `projection_drift_attack` | `refused` | `P0001` | `mainline.fn_permit_merge_gate` | **parsed** from the message |
| 4 | `admit` | `admitted` | `00000` | — | server-computed `clearance_digest` |

Beat 3 is the one that matters most and the one a reader should look at twice.
`mainline.permit.open_blocking` is forced to zero **out of band** — precisely what a
disarmed projector or a careless `UPDATE` leaves behind — so `gate_closed_when_issued`
is now satisfied and would admit the merge. The merge is refused anyway, because
`mainline.fn_permit_merge_gate` **re-derives** the open count from
`blocking_check LEFT JOIN disposition` instead of trusting the column. That is rule P-2 —
a projection is *enforced, never trusted* — and it is the beat that distinguishes this
product from a `CHECK` constraint.

Beat 4 is not decoration either. **A gate that always refuses is broken, not safe.** One
signed disposition closes the counter through the projection trigger and the same merge
succeeds, with a `merge_record` row and a clearance digest the *server* computed over the
sorted `(check_id, disposition_id)` set.

Observed on the local node, verbatim:

```
beat 2  REFUSED  [23514] gate_closed_when_issued        (reported)
        failed to satisfy CHECK constraint ((state != 'merged') OR (open_blocking = 0))
beat 3  REFUSED  [P0001] mainline.fn_permit_merge_gate  (parsed)
        MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open
        obligation count is 1 while the projected counter reads zero
beat 4  ADMITTED [00000] clearance_digest
        c283343729c7a787b9d102ae461c6d795b9335341fbcf8fd276325d020d78990
VERDICT PROVEN
```

---

## 2. The transaction discipline

```
BEGIN                                     ← non-autocommit connection
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE
SELECT cluster_logical_timestamp()        ← opened_logical_timestamp
  beat 1  read the permit and its open obligation        (no savepoint; read-only)
  SAVEPOINT gate_run_beat_2
    CALL mainline.merge_permit(…)         → 23514
  ROLLBACK TO SAVEPOINT gate_run_beat_2 ; RELEASE SAVEPOINT gate_run_beat_2
  SAVEPOINT gate_run_beat_3
    UPDATE mainline.permit SET open_blocking = 0
    CALL mainline.merge_permit(…)         → P0001
  ROLLBACK TO SAVEPOINT gate_run_beat_3 ; RELEASE SAVEPOINT gate_run_beat_3
  SAVEPOINT gate_run_beat_4
    INSERT INTO mainline.disposition (…)
    CALL mainline.merge_permit(…)         → 00000, merge_record read back
  ROLLBACK TO SAVEPOINT gate_run_beat_4 ; RELEASE SAVEPOINT gate_run_beat_4
SELECT cluster_logical_timestamp()        ← closed_logical_timestamp
ROLLBACK                                  ← the whole transaction, including beat 4
```

Four properties are load-bearing, and each was measured before the code was written.

**A constraint refusal does not kill the transaction.** CockroachDB honours
`ROLLBACK TO SAVEPOINT` after `23514` and after `P0001`; the transaction keeps taking
statements. Measured by the deployment lead
(`evidence/deploy/lead/savepoint-probe-20260810.txt`) and again by this worker
(`tests/test_gate_run.py`).

**The refusals are the database's.** Real SQLSTATEs, real constraint names, from a real
procedure call — not a story the API tells. Nothing in `gate_run.py` composes a message.

**The successful beat is rolled back too.** Beat 4 genuinely commits nothing. The
`merge_record` row is read back *inside* the savepoint, so the response can quote a
clearance digest that existed, and then it is undone.

**All four beats really did share one transaction.** `cluster_logical_timestamp()` is
constant within a CockroachDB transaction and moves between them, so it is captured at the
first beat and after the last. `transaction.single_transaction` is `true` iff the two are
equal — a read-only *witness*, not an assertion the driver makes about itself.

### `40001` is an undecided transaction, not a failure

If any beat raises `40001`, the run stops, the transaction is rolled back, and the payload
comes back with `outcome: "retry"` and `transaction.retry_sqlstate: "40001"`. There is
**no retry helper anywhere on this path and there will not be one.** A helper that
re-sent a merge because a socket closed is a helper that can issue a permit twice. The
caller decides whether to press the button again — a human pressing a button again is a
decision with an author.

`spec/wire/refusal.schema.json` excludes `40001` from its `sqlstate` enum for the same
reason: an undecided transaction has no reason set. `outcome: "retry"` therefore carries
no `refusal` payload, and the HTTP status is `503`, never `409`.

---

## 3. Why the demo persists nothing — and what that buys

Because the transaction is rolled back, **the demo needs no per-visitor state, no reset
button, no session table, no cleanup sweeper and no lock.** Fifty judges can press the
button simultaneously and each drives the real gate against the real seeded history; the
database is exactly as they found it. The fifth judge sees what the first did.

This removes the single largest piece of complexity a public demo of a *write* path would
otherwise need, and it removes it by construction rather than by policing.

`persisted: false` is not taken on trust. The payload proves it:

```json
"persistence_check": {
  "before": { "row_counts": { "mainline.merge_record": 0, … },
              "permit_row": { "state": "dispositioned", "open_blocking": 1, … } },
  "after":  { … },
  "identical": true
}
```

Row counts over every table the four beats can write — `permit`, `permit_event`,
`merge_record`, `disposition`, `ledger_intake`, `refusal_ledger`, `blocking_check`,
`exposure_receipt`, `exposure_line`, `mainline_ops.outbox` — taken **before** the
transaction opens and **after** it closes, plus `mainline.permit`'s own column values,
because beat 3 mutates a column without changing a count.

`tests/test_gate_run.py::test_every_table_row_count_is_identical_across_a_gate_run` goes
further and counts **every base table** in `mainline`, `mainline_meas`, `mainline_ops` and
`trappoint` — 89 on the current chain — before and after a run, and requires every one to
be unchanged. A claim that nothing persisted should be checked against everything, not
against the list the code under test happened to choose.

### The amendment of 2026-08-14 — two claims that were one sentence

**Everything above still stands and none of those counts was narrowed.** What changed is
which of two different claims the *verdict* is read off, and the change is made here, on the
record, under `docs/leads/cloud-hardening-final.md` ruling **R2**, which permits this
contract to move only by argument and never by a silent edit.

The ten counts are **unscoped whole-table `count(*)`s**. They therefore answer *"did the
database move"*. The payload was reading them as an answer to *"did THIS RUN persist
anything"*, and those are different questions the moment anybody else is connected. One row
committed by any other caller into any of those ten tables, between the two readings, made
this endpoint answer

```
verdict: NOT PROVEN
failures: ["the affected tables are NOT byte-identical before and after the run;
            the transaction was supposed to persist nothing"]
```

— about a transaction that had persisted nothing, with its own subject's row demonstrably
untouched. Constructed, reproduced and attributed row by row in
[`docs/diagnosis/gate-run-fingerprint.md`](../diagnosis/gate-run-fingerprint.md).

**This is not a laboratory condition.** The demo URL is bounded-but-open by the founder's
choice and the console exposes four *committing* transitions — `merge_permit`,
`sign_disposition`, `materialise_checks`, `suspend_permit`. One judge signing a disposition
while another presses gate-run moves `mainline.disposition`, and the second judge is told
the demo persisted something. (What does **not** cause it, measured and now asserted, is two
judges pressing *gate-run* at once: neither run persists anything, so neither can move the
other's counts.)

**Why the fix is not to scope the counts down.** R2: the broad check is asked for on
purpose, and it gives its own reason — a check that only looked where the run was *expected*
to write could not see a write nobody expected, and beat 3 mutates a column without changing
any count at all. Narrowing it would delete the demo's only evidence for its central claim
while leaving the claim in the payload. So nothing was narrowed: `_FINGERPRINT_SQL` is
byte-for-byte the same ten statements, `_FINGERPRINT_TABLES` still names all ten, `identical`
is still computed over all of them and is still in the response.

**What was added instead** is a reading the run can be held to, built from the one identifier
in the whole transaction that no other writer could have produced:

```json
"persistence_check": {
  "identical": false,                         // the DATABASE moved — somebody wrote
  "concurrent_writes": { "mainline.permit": [780, 781] },
  "self_persisted": false,                    // THIS RUN did not — and here is why
  "self_evidence": {
    "minted_disposition_id": "…the uuid4 beat 4 minted…",
    "minted_disposition_rows_after_rollback": 0,
    "subject_row_counts_before": { "mainline.merge_record": 0, "mainline.permit_event": 2, … },
    "subject_row_counts_after":  { "mainline.merge_record": 0, "mainline.permit_event": 2, … },
    "permit_row_identical": true
  }
}
```

Beat 4 is the only beat the database *accepts*, and every other row it causes is written by
`mainline.merge_permit` inside the same transaction as that disposition — so if the minted
`disposition_id` is gone after the rollback, that transaction did not commit and none of its
rows are here either. Beats 2 and 3 were refused, so the database wrote nothing to refuse,
and beat 3's out-of-band `UPDATE` is caught by `permit_row`, exactly as before.

`verdict` now keys on `self_persisted`. A delta that is nobody's doing is reported as
`concurrent_writes` — a fact about a shared database — rather than as this run's failure.

**And it can still fail.** `test_transitions.py::test_a_run_that_really_persists_is_caught`
plants a run that keeps beat 4's admission and commits it, and requires `self_persisted` to
come back `true` with the minted disposition present and the verdict `NOT PROVEN`. A check
that had quietly stopped being able to fail would be a worse outcome than the red it
replaced.

---

## 4. The refusal payload comes from the database, not from this API

Every `refusal` member in the response satisfies `spec/wire/refusal.schema.json` and is
assembled from exactly two sources:

1. **The driver's error object.** `sqlstate`, `constraint`, `constraint_source` and
   `message` come out of `psycopg`'s exception through
   `mainline_demo_api.refusal.diagnose`. `constraint_source` is `reported` when
   `diag.constraint_name` carried the name and `parsed` when it was recovered from the
   kernel's own `refused by <schema>.<object>` clause.
2. **`trappoint.explain_refusal`** (migration `0119a`) supplies `mus`, `naa`,
   `naa_reason`, `diagnosis`, `probe_calls`, `gate_epoch`, `spec_version` and `profile` —
   produced by the same engine that produced the refusal, so the explanation cannot
   disagree with it.

The API adds `refusal_id` and `observed_at` and nothing else.

### Why every `P0001` is `parsed`

Measured on CockroachDB CCL v26.2.5 through psycopg 3.3.4, a PL/pgSQL `RAISE` arrives with:

| field | value |
|---|---|
| `diag.constraint_name` | `None` — expected; `spec/errors.md` §3.1 says so |
| `diag.context` | `None` — **not** expected; PostgreSQL populates a PL/pgSQL context stack, CockroachDB does not |
| `diag.source_function` | a CockroachDB Go internal; names nothing |

So the driver cannot report the raising object on this platform, and `spec/errors.md` §2.5
requires the *message* to make it recoverable. `parsed` is a **weakened** diagnosis and the
payload says so, so a run whose exhibits were inferred never looks like a run whose
exhibits were reported.

### Beat 3's diagnosis is honestly incomplete

`trappoint.explain_refusal` has no declarative decomposition for
`mainline.fn_permit_merge_gate`, so it returns `diagnosis: "none"`, `naa: null`,
`naa_reason: "not_computable"` and a single `capability_gap` atom naming the function. That
is the contract's own shape for honest incompleteness. Shipping a superset labelled
`declarative` would be the one failure invariant I14 exists to prevent.

The call is fenced by its own `SAVEPOINT`, because `0119a` *raises* rather than emit a
plausible reason set when the counter it would decompose has drifted — and an unfenced
raise would abort the transaction the four beats depend on.

---

## 5. `verdict`, and the refusal to grade on a curve

Every beat carries the `expected` outcome it was written against and a
`matched_expectation` boolean. `verdict` is `PROVEN` only when **all four** matched and the
persistence check came back identical; otherwise `NOT PROVEN`, with one sentence per
failure in `failures`.

A run that observed `ADMITTED` where it expected `REFUSED` still returns HTTP 200. It says
`NOT PROVEN` and prints why. **A truthful red beats a fabricated green**, and a demo whose
only possible answer is "everything is fine" is not evidence of anything.

---

## 6. The seeded subject

`scenario.py` holds the identifiers, **derived rather than copied**, so the seed
(`w2-cloud-database`) and the API cannot silently disagree:

```
namespace = uuid5(NAMESPACE_URL, "https://mainline.trappoint.org/demo/2026-08")
          = c82d4e5f-961f-590a-95bb-7ea3db2858db
permit_id = uuid5(namespace, "permit") = 077a6fdd-2167-559c-b2ff-8e3c8352504d
site_id   = uuid5(namespace, "site")   = c333eb17-a6c8-5729-8e73-8d49a7ab3971
```

The literal values are committed alongside the derivation and checked against it at import;
the module refuses to load if they ever disagree. Every identifier is overridable with
`MAINLINE_DEMO_<NAME>` for a deployment that seeded a different history.

**Fixed here / read from the database.** Fixed: what the *seed* chooses — site, permit,
clause, precursor event, signer subjects. Read at request time: the obligation, the
exposure receipt, the counters, the state. A derived identifier the API pinned would be the
API asserting a fact about rows it did not write; reading it back means the demo describes
the database it actually found, and says so when it finds nothing —
`ScenarioNotSeeded` → HTTP 422, never a refusal. *"The gate did not refuse"* and
*"there was nothing to ask"* are different findings and only one of them is about the
product.

The demo subject must be in state `dispositioned` with at least one open obligation.
`dispositioned → merged` is the only legal inbound edge to `merged` in
`mainline.subject_transition`, and the open obligation is what beats 2 and 3 are about.

---

## 7. The other four resources, and the write protection

`handle_transition(resource_key, path_params, body, conn) -> (http_status, payload)` also
serves the four kernel transitions the console declares.

| resource | HTTP | outcome mapping |
|---|---|---|
| `materialise_checks` | `POST /v1/permits/{permit_id}/checks:materialise` | committed 200 · refused 409 · retry 503 |
| `sign_disposition` | `POST /v1/checks/{check_id}/disposition` | committed 200 · refused 409 · retry 503 |
| `merge_permit` | `POST /v1/permits/{permit_id}/merge` | committed 200 · refused 409 · retry 503 |
| `suspend_permit` | `POST /v1/permits/{permit_id}/suspend` | committed 200 · refused 409 · retry 503 |

`payload` is the **complete response envelope**, not the bare `data` member —
`envelope_version`, `resource`, `schema_id`, `staged`, `provenance`, `data` — because
`resource` and `schema_id` are functions of the resource key and a second module
re-deriving them is a second place for them to be wrong. `app.py` passes it through
unchanged.

A **client error** (unknown resource, malformed identifier, absent subject, a body that
cannot be honoured) returns 4xx and a plain `{"error", "detail"}` object, **never an
envelope**. The console's transport treats a non-2xx body that is not an envelope as a
transport failure, which is the correct diagnosis for "the client asked wrongly". Dressing
a client mistake as a gate refusal would put a fabricated exhibit in front of a reader.

### The demo subject is write-protected — `423 Locked`

The seeded demo permit is a single shared public copy, and these transitions are
irreversible on it: a permit is never un-merged, and `dispositioned → checks_materialised`
does not come back. One judge pressing one button must not be able to brick the demo for
the next, so a mutating transition aimed at the demo subject is refused with `423` and a
message naming `POST /v1/demo/gate-run` instead. `MAINLINE_DEMO_ALLOW_MUTATION=1` lifts it
in a deployment you own.

### What these endpoints refuse to fabricate

* **`materialise_checks` does not invent obligations.** `blocking_check` rows are written
  by the recall pass. What this endpoint materialises is the **exposure receipt** — what
  was actually shown, to whom, when — one `exposure_line` per obligation, and the
  `checks_materialised` transition on the subject's own event chain. A permit with no
  `mainline_meas.silence_receipt` behind it gets `422`, not a manufactured one: a
  fabricated Proof of Exhausted Recall asserts that a corpus was searched when it was not.
* **`sign_disposition` is `staged: true`, and the envelope says exactly why.** The WebAuthn
  assertion is synthesised — this demo has no authenticator and nothing in the schema
  verifies a signature. Every other column on the row is projected by
  `fn_disposition_project` from authoritative rows and is real. That is what
  `envelope.staged` exists to declare, and the console's honesty chrome renders it.
* **`suspend_permit` on a permit that never merged is `23503` on `legal_edge`.** The legal
  edge set is data in `mainline.subject_transition`, so an illegal transition is a foreign
  key against a row that is not there. A later commit can delete an `if` statement; it
  cannot delete a foreign key without a migration.

---

## 8. Running it

```bash
# both suites, against the local node; the scratch database is built once and reused
cd verticals/mainline/apps/demo-api
MAINLINE_TEST_DSN="postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable" \
  ../../../../.venv/Scripts/python.exe -m pytest tests/test_gate_run.py tests/test_transitions.py -q

# force a cold rebuild of the scratch database (271 migrations, ~50 s)
MAINLINE_W4_REBUILD=1 … -m pytest tests/ -q
```

Measured 2026-08-10: **38 passed, 1 skipped** warm in 11.8 s; **38 passed, 1 skipped** cold
in 119 s including the full chain build. `ruff check` and `mypy --strict` are both clean
over the four modules and the two test files. The skip is
`test_payload_validates_against_the_json_schema` — `jsonschema` is not a workspace
dependency, so the JSON Schema is enforced today by a hand-written structural check that
reads both `contracts/gate-run.schema.json` and the normative
`spec/wire/refusal.schema.json` from disk and asserts required members, closed enums,
`additionalProperties: false` compliance and the conditional invariants. It is a floor, not
a substitute, and it turns into the real validator the day the dependency lands.

---

## 9. Known gaps

* **`jsonschema` is not installed in this workspace**, so no full JSON Schema validation of
  the gate-run payload has ever run. Measured, not assumed: `ModuleNotFoundError` on
  2026-08-10. The structural check above is what runs.
* **`POST /v1/demo/gate-run` is not yet routed.** `app.py`'s route table
  (`w3-api-core-reads`) declares the four kernel POSTs and no demo route, so the endpoint
  404s until a `Route("POST", "/v1/demo/gate-run", "demo_gate_run")` and a
  `SCHEMA_IDS["demo_gate_run"]` entry are added. The handler itself is complete and is
  reachable today through `handle_transition("demo_gate_run", {}, {}, conn)`.
* **The console does not declare `demo_gate_run`.** `resources.ts` declares sixteen
  resources; a seventeenth is needed for the console to drive this endpoint through its
  own transport.
* **Two test harnesses build two scratch databases.** `tests/conftest.py`
  (`w3-api-core-reads`) declares `demo_database` and `conn`; this worker's files declare
  `w4_database` and `w4_conn` and seed `w_w4_api_transitions` from
  `scripts/proof/gate_refusal.py`. The names were deliberately kept apart — a module-level
  fixture shadows a conftest one silently, and a silent shadow is worse than a duplicate —
  but the two should converge on the conftest once it settles, which is not this worker's
  file to change.
* **`tests/test_envelope.py::test_a_post_answers_501_naming_the_module_that_owes_it` is now
  stale.** It asserted the 501 path taken when `transitions` is absent, and passes
  `conn=None`; with the module present the call reaches `handle_transition` and raises
  `AttributeError` on the `None` connection. `w3-api-core-reads` owns that test.
* **The repository-root `pyproject.toml` does not collect this suite.** `testpaths` is
  `["tests", "packages", "verticals/*/packages/*/tests"]`, so
  `verticals/*/apps/*/tests` never runs under a bare `pytest` at the root. These tests run
  only when pytest is invoked from `verticals/mainline/apps/demo-api`.
* **Nothing here has run against CockroachDB Cloud.** Every number in this document is
  from the local single node. The chain applies on Cloud (deployment lead, §1.1 of
  `docs/leads/deploy-plan.md`), and the retry path this module deliberately does *not*
  automate is the one difference a managed multi-node cluster will expose.
