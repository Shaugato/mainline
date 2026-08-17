<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# 02 · One request, four beats

**You are here:** chapter 2 of 5. [Front door](../ARCHITECTURE.md) · [previous: the
mechanism](01-the-mechanism.md) · [glossary](GLOSSARY.md) · [next: where the obligation came
from](03-memory-and-blame.md).

Chapter 01 set out the mechanism. This chapter follows **one HTTP request** — from a judge's
laptop, over the public internet, into a database in Singapore, and back — and then opens up the
four things that request does once it arrives.

## 1. Sixty seconds

Press one button on the demo page, or send one `curl`, and you get back a transcript of a short
argument with a database. The subject of the argument is a [**permit**](GLOSSARY.md#permit): a
written authorisation for one specific dangerous job, at one place, for one window of time. Nobody
starts work until it is issued. This permit has one unfinished item attached — an
[**obligation**](GLOSSARY.md#obligation), meaning a past incident this job resembles that somebody
competent has to answer before the permit may be issued. Nobody has answered it.

1. **Read.** The demo reads the permit and says what it found: one obligation still open.
2. **Issue it anyway.** The database refuses.
3. **Cheat.** The demo reaches in and sets the permit's *"how many obligations are still open"*
   counter to zero. It answers nothing; it just changes the number. Then it tries the same issue
   again. **The database refuses again — and for a different reason.** It did not believe the
   counter. It went back to the underlying rows and counted for itself.
4. **Do it honestly.** One named competent person records a signed answer to the obligation — a
   [**disposition**](GLOSSARY.md#disposition) — and the same issue goes straight through.

Then all four are thrown away. Nothing is saved. The next person to press the button meets the same
permit with the same open obligation, untouched.

Three sentences carry the weight, and the rest of this chapter is their evidence. **Beat 3 is the
beat that matters:** a rule saying *"the counter must read zero"* is satisfied the moment somebody
sets the counter to zero, and this one is not, because the database recomputes the counter from the
underlying rows before it will accept the write — the difference between a rule about a number and a
rule about the world. **Beat 4 is not decoration:** a [gate](GLOSSARY.md#gate) that always refuses is
broken, not safe, and indistinguishable from a database that is down. **Everything rolling back is
what makes the demo public:** no per-visitor state, no reset button, no session table, no lock, and
fifty judges may press it at once.

Measured against the deployed URL: permit run `verdict: PROVEN`, `persisted: false`
[src: `qa/live1.json#/data/verdict`, observed `2026-08-16T21:11:56Z`]. The endpoint's own health
check, re-read on 2026-08-17 while writing this chapter, answers `CockroachDB CCL v26.2.5`, database
`mainline_demo`, `deploy_chain_applied: 271`.

## 2. The request path

Every box below is a thing that exists at a path, a URL or a database object, and carries where it is.

```
  A JUDGE · curl, or the console page in a browser tab
    │  POST /v1/demo/gate-run over TLS · no API key, no cookie, empty body
    ▼
  ┌─ AWS LAMBDA FUNCTION URL · region ap-southeast-1 (Singapore) ───────────────────┐
  │ https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws       │
  │ authorization_type = NONE — anyone at all may call it, by the founder's choice  │
  │ infra/envs/demo/variables.tf:105 (auth type) · :49 (region default)             │
  └────────────────────────────────────────────────────────────────────────────────┘
    │  ONE PYTHON DICT — API Gateway payload format 2.0:
    │  {rawPath, requestContext.http.method, headers, body, isBase64Encoded}
    ▼
  ┌─ handler(event, context) · app.py:522 · THERE IS NO WEB FRAMEWORK HERE ─────────┐
  │ logbudget.begin() :561 opens this invocation's log-byte allowance · then        │
  │ ratelimit.check() :562 — FIRST statement on purpose, so a refused request reads │
  │ no file and opens no db connection · static_site.is_api_path :578 forks on      │
  │ "/v1" (static_site.py:505); everything else is the console page, not the API    │
  └────────────────────────────────────────────────────────────────────────────────┘
    │  the path string, matched against twenty compiled regexes
    ▼
  ┌─ ROUTE TABLE · ROUTES, app.py:320, built by _routes() at app.py:283–317 ────────┐
  │ twenty rows over nineteen paths: fourteen GETs, six POSTs                       │
  │   row 18  POST /v1/demo/gate-run     -> "demo_gate_run"   app.py:306            │
  │   row 20  POST /v1/demo/cr-gate-run  -> "cr_gate_run"     app.py:316            │
  │ NO PATH PARAMETER on either: the subject is resolved server-side, so a caller   │
  │ cannot point a demo driver at somebody else's row                               │
  └────────────────────────────────────────────────────────────────────────────────┘
    │  a matched Route -> db.connection(), called app.py:614
    ▼
  ┌─ db.resolve_dsn() · db.py:311 — the connection string, and it is a SECRET ──────┐
  │ $MAINLINE_DSN if set; otherwise ONE SSM GetParameter, SigV4-signed by hand out  │
  │ of hashlib/hmac (db.py:214), for SecureString /mainline/demo/cockroach_dsn      │
  │ (infra/envs/demo/variables.tf:321). Cached per container; never logged, because │
  │ db.redact() (db.py:185) is what the one tempted caller prints instead           │
  └────────────────────────────────────────────────────────────────────────────────┘
    │  psycopg 3.3.4 over pgwire, TLS. One connection per warm container, proved
    │  alive with SELECT 1 on every acquisition — db.connection, db.py:598
    ▼
  ┌─ transitions.handle_transition(key, params, body, conn) · transitions.py:1455 ──┐
  │ lazily imported at app.py:687 — a missing module is 501, never 404              │
  │   "cr_gate_run"   -> _demo_cr_gate_run  transitions.py:1506                     │
  │   "demo_gate_run" -> _demo_gate_run     transitions.py:1507                     │
  │        -> gate_run.gate_run(conn, scenario)  gate_run.py:519 — see diagram 2    │
  └────────────────────────────────────────────────────────────────────────────────┘
    │  BEGIN · SERIALIZABLE · four beats · ROLLBACK
    ▼
  ┌─ CockroachDB CCL v26.2.5 · Cloud Basic tier · aws-ap-southeast-1 ───────────────┐
  │ database mainline_demo · 271 of 271 deploy-chain files applied                  │
  │ the gate:  CHECK    gate_closed_when_issued   0050_permit.sql:114               │
  │            TRIGGER  permit_merge_gate         0130_trg_permit_merge_gate.sql:38 │
  │            FUNCTION mainline.fn_permit_merge_gate  0115_fn_permit_merge_gate.sql│
  └────────────────────────────────────────────────────────────────────────────────┘

  AND BACK OUT THE SAME WIRE, carrying the database's own words and nothing added:
    psycopg.Error ─▶ refusal.diagnose(exc) refusal.py:184 — reads exc.sqlstate,
                     exc.diag.constraint_name, message_primary. Composes nothing.
                  ─▶ refusal.refusal_payload(…) refusal.py:286 — adds the minimal
                     unsatisfiable subset and nearest admissible alternative from
                     trappoint.explain_refusal, the SAME ENGINE that produced the
                     refusal, so explanation and refusal cannot disagree
                  ─▶ app._response(200, payload) app.py:470 — the assembled beats,
                     413 above 139,264 bytes (136 * 1024, static_site.py:323)
                  ─▶ Function URL ─▶ TLS ─▶ the judge's terminal
```

**Bedrock is not on this path.** It runs in this repository; it does not run inside this request.
Checkable rather than asserted: the deployed handler's whole dependency closure is
`psycopg==3.3.4` and `psycopg-binary==3.3.4`
(`verticals/mainline/apps/demo-api/pyproject.toml:47–50`), there is no `boto3` in it, and
`grep -rin bedrock verticals/mainline/apps/demo-api/src/` returns nothing. The only AWS API call
the handler makes is the one `GetParameter` above, skipped entirely when `$MAINLINE_DSN` is set.
There is likewise no web framework, no CDN, no S3 bucket and no API Gateway — one origin serves both
the JSON API and the console page, which is why no CORS header is set (`app.py:473`).

## 3. The four beats

One transaction. One isolation level. Three savepoints. One rollback at the end that undoes all of
it — including the beat that succeeded. A [**SQLSTATE**](GLOSSARY.md#sqlstate) is the
five-character code a SQL database returns to say what it did: `00000` accepted · `23514` a `CHECK`
rule refused it · `P0001` a stored procedure refused it deliberately.

```
  BEGIN                                             ← psycopg, autocommit OFF
  SET TRANSACTION ISOLATION LEVEL SERIALIZABLE      gate_run.py:603
  SELECT cluster_logical_timestamp()  → opened_ts   gate_run.py:604
  │
  ├─ BEAT 1 · READ                           gate_run.py:648–662       [00000]
  │    no savepoint — read-only. Reports BOTH counters, and counters_agree: true
  │      open_blocking_projected = 1    ← the number stored ON the permit row
  │      open_blocking_derived   = 1    ← the number RECOUNTED from the rows
  ├─ SAVEPOINT gate_run_beat_2               gate_run.py:667
  │  │  CALL mainline.merge_permit(…)        gate_run.py:669           [23514]
  │  │  REFUSED by CHECK  gate_closed_when_issued
  │  │  constraint_source: "reported"   ← the DRIVER carried the name
  │  │  "failed to satisfy CHECK constraint ((state != 'merged') OR (open_blocking = 0))"
  │  └─ ROLLBACK TO SAVEPOINT :671  ·  RELEASE :686
  ├─ SAVEPOINT gate_run_beat_3               gate_run.py:693
  │  │  UPDATE mainline.permit SET open_blocking = 0      gate_run.py:695
  │  │      ↑ THE FORGERY, out of band. Nothing was answered.
  │  │  counter_forced_to: 0       ← the CHECK above is now SATISFIED
  │  │  open_blocking_derived: 1   ← and the world has not changed
  │  │  CALL mainline.merge_permit(…)        gate_run.py:709           [P0001]
  │  │  REFUSED ANYWAY by  mainline.fn_permit_merge_gate
  │  │  constraint_source: "parsed"    ← recovered from the message; see §7.1
  │  │  "MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open
  │  │   obligation count is 1 while the projected counter reads zero"
  │  └─ ROLLBACK TO SAVEPOINT :711  ·  RELEASE :727
  ├─ SAVEPOINT gate_run_beat_4               gate_run.py:760
  │  │  INSERT INTO mainline.disposition (…) gate_run.py:764
  │  │      disposition_id = uuid4() minted HERE  ← remember this; §6 turns on it
  │  │  CALL mainline.merge_permit(…)        gate_run.py:803           [00000]
  │  │  ADMITTED. merge_record read back INSIDE the savepoint:
  │  │    clearance_digest — computed by the SERVER over the (check, disposition) set
  │  │    permit_state: merged · permit_open_blocking: 0 · head_seq: 3
  │  └─ ROLLBACK TO SAVEPOINT :839  ·  RELEASE :840
  │
  SELECT cluster_logical_timestamp()  → closed_ts   gate_run.py:844
  ROLLBACK                                          gate_run.py:851
  ▲
  └── THE WHOLE TRANSACTION, INCLUDING BEAT 4. Nothing above this line survives.

  single_transaction: opened_ts == closed_ts        gate_run.py:945–948
    cluster_logical_timestamp() is constant WITHIN a CockroachDB transaction and moves
    between them, so equal endpoints are a read-only WITNESS that all four beats shared
    one transaction — not a claim the code makes about itself.
```

## 4. Beat 3: a projection is enforced, never trusted

`mainline.permit.open_blocking` is a [**projection**](GLOSSARY.md#projection) — a value the
database writes onto the row *by itself*, derived from other rows, overwriting whatever a writer
supplied. It is a cached count of how many obligations are still open.

Beat 2 shows a `CHECK` constraint doing what a `CHECK` does: `state <> 'merged' OR open_blocking = 0`
(`verticals/mainline/db/migrations/0050_permit.sql:114`). Read it literally and the hole is visible.
It is a rule **about a column**. Set the column to zero and the rule is satisfied — no obligation
answered, no incident addressed, just a number changed. That is
[**projection drift**](GLOSSARY.md#drift): what a disarmed projector, a botched migration or one
careless `UPDATE` leaves behind. Beat 3 performs exactly that write, on purpose, and asks for the
same [merge](GLOSSARY.md#merge). The database refuses again, and from elsewhere:

```sql
-- verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:62–69
SELECT count(*) INTO v_derived
  FROM mainline.blocking_check bc
 WHERE bc.permit_id = v_subject
   AND NOT EXISTS (SELECT 1 FROM mainline.disposition d
                    WHERE d.check_id = bc.check_id
                      AND d.retracted_by IS NULL
                      AND (d.expires_at IS NULL OR d.expires_at > now()));
-- :76–81
IF v_derived <> 0 AND v_projected = 0 THEN
  RAISE EXCEPTION USING ERRCODE = 'P0001',
    MESSAGE = 'MAINLINE: merge refused by mainline.fn_permit_merge_gate' || …;
END IF;
```

The gate never reads `open_blocking` as an answer. It **re-derives** the count from `blocking_check`
left-joined to `disposition` and compares. The forged zero is not a bypass; it is the *evidence of
the attack*, because the only way to reach that branch is for the two numbers to disagree in that
exact direction.

**And the gate is welded to the table, not to the procedure** — `CREATE TRIGGER permit_merge_gate
BEFORE UPDATE ON mainline.permit FOR EACH ROW WHEN ((NEW).state = 'merged' …)`
(`0130_trg_permit_merge_gate.sql:38–41`). A caller who skips `mainline.merge_permit` entirely, which
is precisely what an attacker does, and issues a bare `UPDATE … SET state = 'merged'`, meets the
same named trigger and the same named `CHECK`. Neither mechanism depends on the other — the `CHECK`
catches the honest case, the trigger the forged one, and `0115`'s header notes the `CHECK` survives
when the trigger is disabled.

Beat 3's *explanation* is honestly incomplete, and the payload says so. `trappoint.explain_refusal`
has no declarative decomposition for `mainline.fn_permit_merge_gate`, so it returns
`diagnosis: "none"`, `naa: null`, `naa_reason: "not_computable"` and a single `capability_gap`
naming the function [src: `qa/live1.json#/data/beats/2/refusal/diagnosis`]. Beat 2, which the engine
*can* decompose, comes back `diagnosis: "declarative"` with a
[minimal unsatisfiable subset](GLOSSARY.md#mus) of one obligation and a
[nearest admissible alternative](GLOSSARY.md#naa) that names it. A confident superset for beat 3
would be exactly what the honest-incompleteness shape exists to prevent.

## 5. Beat 4: a gate that always refuses is broken, not safe

A demo that only ever refuses proves nothing. It is indistinguishable from a database that is down,
a permission that is missing, or a rule that refuses everything unconditionally — worthless in the
field, because a permit system nobody can satisfy is a permit system people work around. So beat 4
answers the obligation properly. One `mainline.disposition` row is inserted: a named competent
person, a kind, a stated reason, a signature, and the digest of the option set they were shown. The
projection trigger recounts, `open_blocking` falls to zero *because the underlying rows changed*,
and the same `CALL mainline.merge_permit(…)` returns `00000`. The permit is issued and the database
— not the API — computes the receipt:

```
clearance_digest  8da7db6a8c5df3675e676e642e90f09d7bf73c0a19a87a3d94f69efc706b72f3
permit_state      merged        permit_open_blocking  0        head_seq  3
```
[src: `qa/live1.json#/data/beats/3/observed/merge_record`]

One scoping this page will not skip: the WebAuthn assertion on that disposition is **synthesised** —
this demo has no authenticator and nothing in the schema verifies a signature. Every other column on
the row is projected from authoritative rows and is real. The beat is also *skipped*, with its
reason in the payload, if the obligation changed between the opening read and the transaction
(`gate_run.py:742–758`).

## 6. Nothing persists — and the payload proves it rather than asserting it

Because the whole transaction is rolled back at `gate_run.py:851`, the demo needs **no per-visitor
state, no reset button, no session table, no cleanup sweeper and no lock**. Fifty judges can press
the button at once; each drives the real gate against the real seeded history, and the database is
exactly as they found it. That removes the largest piece of complexity a public demo of a *write*
path would otherwise need, by construction rather than by policing. `persisted: false` is then a
**conclusion the caller can check**, not a promise — two readings sit in the response:

```jsonc
"persistence_check": {
  "identical": true,           // the ten unscoped whole-table counts did not move
  "concurrent_writes": null,   // so nobody else wrote either
  "self_persisted": false,     // THIS RUN persisted nothing — and here is why
  "self_evidence": {
    "minted_disposition_id": "812ab806-5885-48ea-971d-c8a04c48b841",
    "minted_disposition_rows_after_rollback": 0,
    "subject_row_counts_before": {"mainline.merge_record": 0, "mainline.permit_event": 2, …},
    "subject_row_counts_after":  {"mainline.merge_record": 0, "mainline.permit_event": 2, …},
    "permit_row_identical": true
  }
}
```
[src: `qa/live1.json#/data/persistence_check`]

The `uuid4` beat 4 minted for its disposition is **the one identifier in the whole transaction that
no other writer could have produced** (`gate_run.py:761`). Beat 4 is the only beat the database
accepts, and every other row it causes is written by `mainline.merge_permit` inside the same
transaction as that disposition — so if the minted id is gone after the rollback, that transaction
did not commit and none of its rows are here either. Beats 2 and 3 were refused, so there was
nothing to undo; and beat 3's out-of-band `UPDATE` changes a column without changing any count,
which is why `permit_row_identical` is read by **value** (`_PERMIT_ROW_SQL`, `gate_run.py:299`).

### 6.1 The amendment of 2026-08-14, stated honestly

**Nothing was narrowed.** The fingerprint is still ten unscoped whole-table `count(*)`s over every
table the four beats can write (`_FINGERPRINT_SQL`, `gate_run.py:235–246`; `_FINGERPRINT_TABLES`,
`:248–259`), `identical` is still computed over all ten, and all ten are still in the response.

What changed is which of two claims the **verdict** is read off. Ten unscoped counts answer *"did
the database move"*. The payload was reading them as an answer to *"did THIS RUN persist
anything"*, and those are different questions the moment anybody else is connected. One row
committed by any other caller into any of those ten tables, between the two readings, made this
endpoint answer `NOT PROVEN` with the sentence *"the transaction was supposed to persist nothing"*
— about a transaction that had persisted nothing, with its own subject's row demonstrably
untouched. Not a laboratory condition: the demo URL is bounded-but-open by the founder's choice and
the console exposes four *committing* transitions, so one judge signing a disposition while another
presses gate-run moves `mainline.disposition`, and the second judge is told the demo persisted
something.

**The fix was to add a reading the run can be held to, not to narrow the counts.** A check that
only looked where the run was *expected* to write could not see a write nobody expected — and beat
3 mutates a column without changing any count at all. Narrowing would have deleted the demo's only
evidence for its central claim while leaving the claim in the payload. So `self_persisted` was
added beside `identical`, the verdict keys on `self_persisted` (`gate_run.py:889–893`, `:921`), and
a delta that is nobody's doing is reported as `concurrent_writes` — a fact about a shared database
— rather than as this run's failure. Argued at `docs/deploy/gate-run-contract.md` §3 under
`docs/leads/cloud-hardening-final.md` ruling **R2**; reproduced at
`docs/diagnosis/gate-run-fingerprint.md`. **And the check can still fail:**
`tests/test_transitions.py::test_a_run_that_really_persists_is_caught` plants a run that keeps beat
4's admission and commits it, and requires `self_persisted: true` with the minted disposition
present and the verdict `NOT PROVEN`. A check that had quietly stopped being able to fail would be
worse than the red it replaced.

## 7. Four things a first-time reader will otherwise trip over

### 7.1 Why every `P0001` says `parsed`, and why that is the weaker answer

Beat 2's exhibit is `reported`: the driver's error object carried the constraint name. Beat 3's is
`parsed`: it was recovered from the message text by a deliberately narrow regular expression that
accepts a lower-case, dot-qualified SQL identifier and nothing else (`refusal.py:127`) — a looser
pattern would let a message smuggle in a name the database never used.

That is a platform measurement, not a preference. On CockroachDB v26.2.5 through psycopg 3.3.4 a
PL/pgSQL `RAISE` arrives with `diag.constraint_name` = `None` (expected — `spec/errors.md` §3.1),
`diag.context` = `None` (**not** expected — PostgreSQL populates a PL/pgSQL context stack and
CockroachDB does not), and `diag.source_function` naming a CockroachDB Go internal, so the *message*
is the only channel left. **`parsed` is a weakened diagnosis and the payload declares it**, so a run
whose exhibits were inferred never looks like one whose exhibits were reported. When neither channel
yields a name the diagnosis is `absent` and the caller must not claim a refusal at all
(`refusal.py:219`; `Diagnosis.is_refusal`, `refusal.py:172–175`): a refusal with no exhibit is not
evidence.

### 7.2 `40001` is an undecided transaction, and no statement is ever re-sent

`40001` is CockroachDB saying *the transaction could not be serialised — ask again*. It is **not** a
refusal: the gate never got to speak, so there is no reason set to report. `refusal.classify`
returns `retry` for it, and `spec/wire/refusal.schema.json` excludes it from the `sqlstate` enum for
the same reason. If any beat raises it the run stops, the transaction is rolled back, and the
payload returns `outcome: "retry"` with `transaction.retry_sqlstate: "40001"` — HTTP `503`, never
`409`, carrying no `refusal` member.

Stated exactly, because the distinction is the point: **`gate_run` never retries anything** and
there is no retry helper inside it; one call is exactly one attempt. One level up,
`transitions._demo_gate_run` re-runs the **whole function from `BEGIN`** under
`retry.run_transaction` (`transitions.py:1329`; `retry.py:307`), bounded at `max_attempts = 5`
(`retry.py:167`) — legitimate precisely because the unit re-run is an entire transaction that
persists nothing, not a statement replayed into a poisoned one. A helper that re-sent a *merge*
because a socket closed is a helper that can issue a permit twice.

### 7.3 A client error is `{error, detail}` — never an envelope

An unknown resource key, a malformed identifier, an absent subject, a body that cannot be honoured:
4xx and a plain `{"error": …, "detail": …}` object (`transitions._error`, `transitions.py:250–252`;
`app._problem`, `app.py:514`). Never a response envelope. The console's transport classifies a
non-2xx body that is *not* an envelope as a transport failure, the correct diagnosis for "the client
asked wrongly"; dressing a client mistake as a gate refusal would put a fabricated exhibit in front
of a reader. For the same reason a demo history that is simply not in this database is
`422 demo_history_not_seeded` — *"the gate did not refuse"* and *"there was nothing to ask"* are
different findings, and only one is about the product.

### 7.4 `423 Locked` on the shared demo subject

The four kernel transitions the console declares — `materialise_checks`, `sign_disposition`,
`merge_permit`, `suspend_permit` — really commit, and they are irreversible on the seeded demo
permit, which is a single shared public copy: a permit is never un-merged. One judge must not be
able to brick the demo for the next. So a mutating transition aimed at the demo subject is refused
`423 Locked` with `demo_subject_write_protected`, naming `POST /v1/demo/gate-run` as the endpoint
to use instead (`transitions.py:543–555`). `MAINLINE_DEMO_ALLOW_MUTATION=1` lifts it in a
deployment you own (`transitions.py:478`).

The guard also **fails closed when it cannot say which subject it is protecting**, refusing
`423 demo_subject_unidentified` rather than assuming (`transitions.py:557–574`) — added after an
unset environment variable was measured on 2026-08-13 arming it at an identifier no caller sends,
leaving `materialise_checks` and `sign_disposition` answering 200 to an anonymous caller
[src: `evidence/deploy/demo-guard-armed.json`]. The two demo drivers take the `param_name is None`
branch and never reach the guard — there is nothing to guard, because the transaction rolls back.

## 8. Both use cases, as the live URL answers them

Both captured against `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`.

**USE CASE 1 — the permit.** `POST /v1/demo/gate-run`
[src: `qa/live1.json`, `observed_at 2026-08-16T21:11:56Z`]

| beat | outcome | SQLSTATE | exhibit | source |
|---|---|---|---|---|
| 1 read | `read` | `00000` | — | — |
| 2 merge | `refused` | `23514` | `gate_closed_when_issued` | `reported` |
| 3 forge + merge | `refused` | `P0001` | `mainline.fn_permit_merge_gate` | `parsed` |
| 4 admit | `admitted` | `00000` | server-computed `clearance_digest` | — |

`verdict: PROVEN` · `failures: []` · `persisted: false` · `identical: true` ·
`self_persisted: false` · `single_transaction: true` · savepoints `gate_run_beat_2 / _3 / _4`.

**USE CASE 2 — the change request.** `POST /v1/demo/cr-gate-run`
[src: `qa/live2.json`, `observed_at 2026-08-16T21:11:57Z`]

| beat | outcome | SQLSTATE | exhibit | source |
|---|---|---|---|---|
| 1 read | `read` | `00000` | — | — |
| 2 merge | `refused` | `23514` | `cr_gate_closed_when_merged` | `reported` |
| 3 forge + merge | `refused` | `P0001` | `mainline.fn_cr_merge_gate` | `parsed` |

`verdict: PROVEN` · `persisted: false` · `identical: true` · `self_persisted: false` · savepoints
`cr_gate_run_beat_2 / _3`.

**`admission_beat: null`, and the page says so rather than rounding up.** Three beats here, not
four, and the missing one is beat 4. The reason is two rows in the grant matrix, not an omission in
the code: a disposition's composite foreign key lands on `(check_id, receipt_id)`, so signing one
requires an exposure receipt that actually showed the obligation; no such receipt exists for this
change request, and the login this endpoint runs as holds `SELECT` and not `INSERT` on
`mainline.exposure_receipt` and `mainline.exposure_line` (`verticals/mainline/db/GRANTS.yaml:644`,
`:647`), so it cannot mint one. The payload carries `admission_absent_reason` in words, those two
grant rows, and `admission_proved_by: "POST /v1/demo/gate-run"` — where the admission *is* proved,
against the subject that can carry it. A fourth beat marked "skipped" and dressed to look passing
would be a fabricated exhibit.

That run also plays its refusals with a **bare `UPDATE`** rather than a `CALL`
(`cr_gate_run.py:275–279`), stating why as `kernel_procedure_absent_sqlstate: "42501"`: as the role
the deployed Function URL executes as, the kernel procedure answers a privilege error, and *a
privilege error is not a gate refusal* — it says the writer never reached the gate. The bare
statement is the stronger exhibit anyway, because the gate is welded to the table
(`CHECK cr_gate_closed_when_merged`, `0051_change_request.sql:85`; `CREATE TRIGGER cr_merge_gate`,
`0131_trg_cr_merge_gate.sql:38–41`).

**What is still not checked here.** No full JSON Schema validation of the gate-run payload has ever
run: `jsonschema` is not installed in this workspace, re-measured this session as
`python -c "import jsonschema"` → `ModuleNotFoundError`. A hand-written structural check runs
instead, reading `contracts/gate-run.schema.json` and the normative `spec/wire/refusal.schema.json`
from disk and asserting required members, closed enums, `additionalProperties: false` compliance and
the conditional invariants. It is a floor, not a substitute, and it is the one skip in the demo-api
suite (`tests/test_gate_run.py::test_payload_validates_against_the_json_schema`).

## 9. Where the obligation came from in the first place

Everything above takes the open obligation as given. Beat 1 reads it, beat 2 is refused because of
it, beat 3 tries to make it disappear by changing a number, and beat 4 answers it. But an obligation
is not a to-do item somebody typed in: it is a row that exists because a past incident was recorded,
a rule was written in response, and a walk over that history found the rule reaches this job.
**Where the obligation came from in the first place** is [chapter 03](03-memory-and-blame.md).
