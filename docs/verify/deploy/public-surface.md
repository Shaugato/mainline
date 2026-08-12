<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# W2 — the public surface, abused route by route

**Worker:** W2 (deploy-verification pass, lead plan `docs/leads/deploy-verify-plan2.md`).
**Date:** 2026-08-11. **Account:** `0229REDACTED8246`. **Region:** `ap-southeast-1`.
**Subject:** every endpoint the committed plan exposes at `authorization_type = "NONE"`.

**Every line below is a probe, not a reading of a guard.** The handler was driven over HTTP
by `scripts/deploy/local_furl.py`, which translates an HTTP request into a Lambda payload
format 2.0 event and calls `mainline_demo_api.app.handler` — the same module the artefact
carries — under the environment `evidence/deploy/terraform-plan-furl.json` sets. The
database behind it is a local scratch database `w_w2` on the pinned CockroachDB v26.2.5
Docker node, built by running the migration chain (`271/271 applied, 0 failed`) and then
`scripts/deploy/seed_demo.py`, so it is row-for-row the shape of Cloud `mainline_demo`.

The Cloud cluster was touched **read-only** — `SET default_transaction_read_only = on`,
`SELECT` only — for one question the lead posed and nothing else. No `terraform` ran. No
credential is printed here or in the evidence file.

Raw measurements: `evidence/deploy/verify/public-surface-probe.json`.

**Verdict is at the bottom and it is NO-GO, with a one-line fix.**

---

## 0. The artefact under review is the one I probed

```
out/lambda/mainline-demo-api-arm64.zip   sha256(b64) = yF1/AKVXbkEt+wEkrZPEAQR1cBEXnQApNh2ajbW4pLA=
plan  module.api[0].aws_lambda_function.this
      .source_code_hash                  = yF1/AKVXbkEt+wEkrZPEAQR1cBEXnQApNh2ajbW4pLA=
```

Identical. 206 entries; 75 of them under `web/`, 26 of those under `web/bundle/`. That last
number is load-bearing and §2 explains why.

The planned environment, read from the plan JSON rather than the HCL:

| variable | value | consequence |
|---|---|---|
| `MAINLINE_DEMO_PERMIT_ID` | `077a6fdd-…-8e3c8352504d` | the only subject `_demo_guard` protects |
| `MAINLINE_SCENARIO_PERMIT_ID` | same value | read by nothing |
| `MAINLINE_DSN_PARAM` | `/mainline/demo/cockroach_dsn` | a name, never a value |
| `MAINLINE_DEMO_DATABASE` | `mainline_demo` | **read by no module in the package** |
| `MAINLINE_WEB_ROOT` | `/var/task/web` | the static surface |
| `MAINLINE_DEBUG` | **absent** | `traceback` is `null` in every 500 — confirmed in §5 |
| `MAINLINE_DEMO_ALLOW_MUTATION` | **absent** | the guard is armed |
| `MAINLINE_DSN` | **absent** | the DSN is fetched from SSM at runtime |

---

## 1. The whole surface, measured

`app.ROUTES` is **17** rows — 12 `GET`, 5 `POST` — confirmed by importing the module, not by
counting the source. `/v1/health` is **not** one of them: it is matched before the table is
consulted, so the reachable `/v1` surface is eighteen endpoints. Everything outside `/v1`
falls through to `static_site.serve`.

`mutates` is `transitions.TRANSITION_RESOURCES`' own third element, not my reading of the
code. Timings are the worst of three warm samples against a one-permit database; bytes are
the response body.

| # | method | template | key | mutates | auth | measured | worst-case cost |
|---|---|---|---|---|---|---|---|
| — | GET | `/v1/health` | `health` | no | **none** | `200` 9 ms 305 B | one round trip, no joins |
| 1 | GET | `/v1/permits/{permit_id}` | `permit` | no | **none** | `200` 188 ms 5 691 B | 5 statements incl. `pg_constraint` |
| 2 | GET | `/v1/permits/{permit_id}/blocking-checks` | `blocking_checks` | no | **none** | `200` 17 ms 2 408 B | SQL `LIMIT 512` |
| 3 | GET | `/v1/permits/{permit_id}/silence` | `silence` | no | **none** | `200` 24 ms 2 342 B | `LIMIT 512` + `LIMIT 1` |
| 4 | GET | `/v1/change-requests/{cr_id}` | `change_request` | no | **none** | `404` 11 ms 254 B | one row; Cloud holds 0 |
| 5 | GET | `/v1/checks/{check_id}/disposition` | `disposition` | no | **none** | `200` 23 ms 2 822 B | `LIMIT 16/32/1` |
| 6 | GET | `/v1/receipts/{receipt_id}` | `exposure_receipt` | no | **none** | `200` 38 ms 1 817 B | `LIMIT 512` lines |
| 7 | GET | `/v1/clauses/{clause_uuid}/versions/{commit_id}` | `clause_version` | no | **none** | `200` 16 ms 3 230 B | `LIMIT 64` witnesses |
| 8 | GET | `/v1/clauses/{clause_uuid}/ancestry` | `clause_ancestry` | no | **none** | `200` 211 ms 3 744 B | 6 statements; `512/512/2048/512/512` |
| 9 | GET | `/v1/ledger` | `ledger` | no | **none** | `200` 53 ms 2 265 B | `64/512/2048/64/64` |
| 10 | GET | `/v1/recall-runs/{run_id}` | `recall_run` | no | **none** | `200` 13 ms 2 223 B | capped |
| 11 | GET | `/v1/lessons/{lesson_id}/propagation` | `propagation` | no | **none** | `200` 66 ms 4 041 B | staged; probes for a table that does not exist |
| 12 | GET | `/v1/audit` | `audit` | no | **none** | `200` 443 ms 19 438 B | **slowest read**; 14 views × 25 rows / 10 KiB each |
| 13 | POST | `/v1/permits/{permit_id}/checks:materialise` | `materialise_checks` | **YES** | **none** | `500` 16 ms | `conn.commit()` at `transitions.py:698` |
| 14 | POST | `/v1/checks/{check_id}/disposition` | `sign_disposition` | **YES** | **none** | `422` 14 ms | `conn.commit()` at `transitions.py:861` |
| 15 | POST | `/v1/permits/{permit_id}/merge` | `merge_permit` | **YES** | **none** | `500` 16 ms | `conn.commit()` at `transitions.py:422` |
| 16 | POST | `/v1/permits/{permit_id}/suspend` | `suspend_permit` | **YES** | **none** | `500` 15 ms | `conn.commit()` at `transitions.py:560` |
| 17 | POST | `/v1/demo/gate-run` | `demo_gate_run` | rolls back | **none** | `422` 11 ms | four beats, one transaction, `ROLLBACK` |
| — | GET/HEAD | everything else | `static_site.serve` | no | **none** | `200` 4 ms 4 655 B (`/`), 5 ms 8 435 B (`/bundle/manifest.json`) | one file read; no database |

Router behaviour, probed rather than assumed: `GET` on a POST-only path → `405` naming the
allowed methods; `POST /v1/permits/{id}` → `405`; `GET /v1/nope` → `404 no_route` listing
the declared templates; `OPTIONS` anywhere → `204`; `POST /v1/health` → `405`. The static
surface answers `405` to `POST` and `DELETE` and `200` + `index.html` to any unknown path.

**The twelve GETs and `/v1/health` changed no committed row.** Snapshot before, thirteen
requests, snapshot after, over twelve counters including `permit.state`, `head_seq`,
`open_blocking`, `permit_event`, `disposition`, `exposure_receipt`, `merge_record` and
`mainline_ops.outbox`: the delta is `{}`.

---

## 2. THE CENTRAL QUESTION — and the answer is not the one the guard implies

### 2.1 What is actually in the Cloud database (read-only measurement)

```
mainline_demo @ mainline-dev, aws-ap-southeast-1, session read_only = on
  permit_count                = 1
  permits                     = dec0de00-0006-4000-8000-000000000001
                                state=dispositioned open_blocking=1 head_seq=2 gate_epoch=1
  permit 077a6fdd-…-8e3c8352504d present = FALSE
  change_request = 0   disposition = 0   merge_record = 0   live exposure_receipt = 1
```

So the lead's §0.2 question — *does `mainline_demo` contain a permit other than the seeded
one?* — has a cleaner and worse answer than expected. **It contains exactly one permit, and
it is not the one the guard protects.**

`transitions._demo_guard` (`transitions.py:261`) refuses with `423` **if and only if**
`subject_id == scenario.permit_id`, and `scenario.from_env()` takes that from
`MAINLINE_DEMO_PERMIT_ID`, which the plan sets to `077a6fdd-…`. The seed
(`scripts/deploy/seed_demo.py`, and `evidence/deploy/cloud-seed.json`) creates
`dec0de00-0006-…`. **The guard is armed at a row that does not exist and covers nothing that
does.**

### 2.2 Is the real permit id discoverable by an anonymous caller?

The lead asked specifically about `/v1/ledger` and `/v1/audit`. Both were probed against
Cloud data shapes, and both are clean:

| surface | discloses a permit id | what it does carry |
|---|---|---|
| `GET /v1/ledger` | **no** | one uuid: the *clause*, as `ledger_intake.subject_id` |
| `GET /v1/audit` | **no** | 14 views, 0 permit ids; `v_open_gate_summary.permits` is a **count** |

**But the answer is yes by another door, and it is in the zip Terraform is about to upload.**

```
web/bundle/manifest.json        (served at GET /bundle/manifest.json, same hostname, no auth)
  dec0de00-0001-…  site
  dec0de00-0004-…  clause
  dec0de00-0006-…  THE PERMIT
  dec0de00-0007-…  the obligation
  dec0de00-0008-…  the exposure receipt
  dec0de00-0009-…  the recall run
```

Four more files in `web/bundle/` name it too. Measured: `GET /bundle/manifest.json` → `200`,
8 435 B, 5 ms. So the attack is two requests: read the manifest, then aim a `POST` at the id
it hands you.

### 2.3 What that `POST` actually does — before/after, row level

Two experiments, both against the local scratch database, both under the plan's
`MAINLINE_DEMO_PERMIT_ID = 077a6fdd-…`.

**Experiment A — HEAD, over HTTP.** Eleven POSTs including all four mutating routes against
the seeded permit and its obligation, with a full committed-state snapshot around each.

| probe | status | committed delta |
|---|---|---|
| merge / suspend / materialise on `077a6fdd-…` | `423` ×3 | `{}` — the guard fires on the absent id |
| merge on a fabricated uuid | `404 no_such_permit` | `{}` |
| `POST /v1/demo/gate-run` | **`422 demo_history_not_seeded`** | `{}` |
| merge / suspend / materialise on `dec0de00-0006-…` | **`500 internal_error`** ×3 | `{}` |
| sign disposition on `dec0de00-0007-…` | **`422`** | `{}` |

Nothing committed — **and not because the guard held.** The guard never ran on the seeded
permit. All four handlers raise before their first write:

```
db.connection()          row_factory = psycopg.rows.dict_row
conn.execute(...).fetchone()  ->  {'gate_epoch': 1, 'head_seq': 2, 'state': 'dispositioned'}
transitions._permit_epoch, transitions.py:287
    return (int(row[0]), int(row[1]), row[2]) if row else None
                 ~~~^^^
KeyError: 0
```

`db.py` hands `transitions.py`, `scenario.py` and `gate_run.py` a dict-row connection and all
three index rows positionally. `_sign_disposition` unpacks four **column names** out of the
dict and hands the literal string `'permit_id'` to `_demo_guard` — so that route's guard
cannot fire even when the identifier is right — then `int('gate_epoch')` raises and the
handler answers `422`. `POST /v1/demo/gate-run` fails the same way with
`500 [22P02] could not parse "check_id" as type uuid`, which
`evidence/deploy/acceptance.json` already records verbatim as its `NOT PROVEN` reason.

With the identifier corrected (`MAINLINE_DEMO_PERMIT_ID = dec0de00-0006-…`) the guard does
hold — `423` on merge, suspend and materialise — while `sign_disposition` still answers
`422` and `gate-run` still answers `500`.

**Experiment B — the same calls with the row factory corrected.** `transitions.handle_transition`
called in-process with exactly the arguments `app._transition` passes and a `tuple_row`
connection, otherwise the plan's environment. This is a **simulation of the fix**, labelled
as one, and it is the state the tree will be in the moment anyone makes the demo endpoint
work.

| # | call | status | outcome | committed delta |
|---|---|---|---|---|
| 1 | `merge_permit` on `dec0de00-0006-…` | `409` | refused `23514 gate_closed_when_issued` | `{}` |
| 2 | `suspend_permit` | `409` | refused `23503 legal_edge` | `{}` |
| 3 | **`materialise_checks`** | **`200`** | **committed** | `state: dispositioned → checks_materialised`, `head_seq: 2 → 3`, `permit_event: 2 → 3`, `exposure_receipt: 1 → 2`, `exposure_line: 1 → 2` |
| 4 | `sign_disposition` | `409` | refused `23503 disposition_signer_credential_id_fkey` | `{}` |
| 5 | `merge_permit` again | `409` | refused **`23503 legal_edge`** | `{}` |
| 6 | `suspend_permit` again | `409` | refused `23503 legal_edge` | `{}` |

Read row 3 and then row 5 together. **One anonymous HTTP request permanently moves the demo
subject out of `dispositioned`, and the headline exhibit silently changes from
`23514 gate_closed_when_issued` — the central claim of the whole submission — to
`23503 legal_edge`, an unrelated refusal about a state machine edge.**

It is not recoverable by re-running the seed. The repository's own seeder says so:

```
$ scripts/deploy/seed_demo.py --database w_w2      # after the single POST above
  state         checks_materialised  open_blocking=1  gate_epoch=1  head_seq=3
  MERGE         REFUSED [23503] legal_edge (reported)
  ! the seeded permit is in state 'checks_materialised', not 'dispositioned'
  ! the merge was refused with [23503] 'legal_edge', expected [23514] 'gate_closed_when_issued'
VERDICT       WRONG STATE
```

The seed files are `ON CONFLICT DO NOTHING` and `mainline.permit_event` is append-only, so
recovery means rebuilding the database.

**What did NOT become possible, stated because it matters to the size of the finding:** the
gate itself never yields. `merge` on a pristine permit is refused by `23514`; `suspend` by
`23503 legal_edge`; a disposition cannot be forged because the synthesised WebAuthn
credential fails `disposition_signer_credential_id_fkey`. Nothing here weakens the central
claim as a claim about CockroachDB. It removes the exhibit that demonstrates it.

**No other project's data is reachable.** `mainline_demo` holds one site, one permit, one
obligation. `mainline_api`'s catalog privileges are confined to `mainline`, `mainline_meas`,
`mainline_audit` and `INSERT` on `mainline_ops.outbox`; nothing in `mainline_qa`.

---

## 3. Traversal — sixteen vectors, all refused, one leak

| vector | probe | status |
|---|---|---|
| literal `..` | `/../../../../etc/passwd` | `403 path_refused` `dot_dot` |
| `..` toward Windows | `/../../../../Windows/win.ini` | `403` `dot_dot` |
| single-encoded | `/%2e%2e/%2e%2e/%2e%2e/Windows/win.ini` | `403` `dot_dot` |
| encoded separator | `/..%2f..%2f..%2fWindows/win.ini` | `403` `dot_dot` |
| **double-encoded** | `/%252e%252e/%252e%252e/Windows/win.ini` | `200` index.html |
| absolute unix | `//etc/passwd` | `200` index.html |
| drive letter | `/C:/Windows/win.ini` | `403` `drive` |
| drive letter encoded | `/C%3a/Windows/win.ini` | `403` `drive` |
| backslash | `/..\..\Windows\win.ini` | `403` `backslash` |
| backslash encoded | `/%5c..%5cWindows%5cwin.ini` | `403` `backslash` |
| NUL byte | `/index.html%00.txt` | `403` `nul` |
| `..` mid-path | `/assets/../../app.py` | `403` `dot_dot` |
| overlong-ish UTF-8 | `/%c0%ae%c0%ae/app.py` | `200` index.html |
| sibling package file | `/../mainline_demo_api/db.py` | `403` `dot_dot` |
| **symlink → directory outside root** | `/escape/db.py` | `403` `escapes_root` |
| **symlink → file outside root** | `/escape.txt` | `403` `escapes_root` |

The two symlinks are real ones I planted inside the served web root, pointing at the package
directory and at a file in a scratch directory. Both were refused **after** `resolve()`, by
the `is_relative_to(root)` assertion — the containment check earns its keep.

The three `200`s are correct, not misses. `%252e%252e` decodes **once** to a literal
`%2e%2e` segment, which is a filename, not a traversal; it misses and falls through to the
SPA fallback. Same for the empty first segment of `//etc/passwd` and for `%c0%ae`. In every
case the bytes returned are `index.html`, 4 655 B — no file outside the root was read.

**One disclosure.** The `403 escapes_root` body names the resolved absolute path:

```json
{"error":{"detail":"the request path resolves to <…>\\outside-secret.txt, which is outside
 the web root","kind":"path_refused","path":"/escape.txt","status":403,"vector":"escapes_root"}}
```

In the deployed stack that reveals `/var/task/web/…`. Low value; it is still an
unauthenticated echo of server filesystem layout, and the `vector` token alone would carry
the diagnostic value the message exists for.

---

## 4. Credential leakage — `db.redact()` holds; `/v1/health` still names the login

`db.redact()` was exercised on five DSN shapes with fabricated passwords. The password
survives none of them, including the awkward one where the password itself contains `@` and
`:` — `rpartition("@")` is doing real work there.

| input shape | output | password survives |
|---|---|---|
| `postgresql://user:secret@host…/db?sslmode=verify-full` | `postgresql://user:***@host…/db?sslmode=verify-full` | no |
| `postgresql://user:p@ss:word@host:26257/db` | `postgresql://user:***@host:26257/db` | no |
| `postgresql://root@localhost:26257/defaultdb` (no password) | unchanged | n/a |
| libpq keyword string `host=… password=…` | `***` (whole string) | no |
| `postgres://u:pw@h/d` | `postgres://u:***@h/d` | no |

`GET /v1/health` **200** body keys: `cluster_version`, `database`, `migrations_applied`,
`ok`, `schema_fingerprint`, `seconds`, `server_date`. **No DSN field.**

`GET /v1/health` **503 `unreachable`** body does carry one, from `health.py:133`. Measured
with a fabricated password against a black-holed address:

```json
{"detail":"[-----] connection timeout expired","dsn":"postgresql://mainline_api:***@
 10.255.255.1:26257/mainline_demo?sslmode=verify-full","ok":false,"reason":"unreachable", …}
```

The password is gone. The **login name**, host, port, database and sslmode are published to
the anonymous internet. The cluster hostname is already public in
`evidence/deploy/cloud-seed.json`, so the incremental disclosure is `mainline_api` plus
confirmation the endpoint is live — small, and avoidable: `db.dsn_source()` already exists
and returns a *name*, which is what that field wants.

**500 bodies.** Verbatim, under the planned environment:

```json
{"error":{"detail":"KeyError: 0","kind":"internal_error","resource":"merge_permit",
 "status":500,"traceback":null}}
```

No traceback (`MAINLINE_DEBUG` is absent from the plan — confirmed from the plan JSON, not
from the HCL), no SQL text, no DSN. The database-error branch emits `[SQLSTATE] first line`
only; probed `409` refusals carry a constraint **name**, never a statement.

---

## 5. Unbounded work — there is no `limit` or `offset` parameter anywhere

`reads._DECLARED_PARAMS` is the whole caller-facing surface, and an undeclared parameter is
a `400` that names the declared set (`/v1/ledger?limit=1` → `400`, measured).

| resource | caller-facing knobs | the actual cap |
|---|---|---|
| `/v1/ledger` | `site_code` (≤64 chars), `from_seq`, `to_seq` | **no row parameter.** SQL `LIMIT`: 64 checkpoints, 512 leaves, 2 048 nodes, 64 cosignatures, 64 debt. `?from_seq=0&to_seq=99999999` → `200`, 2 265 B, 48 ms |
| `/v1/audit` | **none** | `AUDIT_ROW_CAP = 25` and `AUDIT_BYTE_CAP = 10240` **per view**, `LIMIT 32` views, `LIMIT 128` agent actions. **No cap across views:** worst case ≈ 32 × 10 KiB ≈ 340 KiB, well inside the 6 MB Lambda response cap |
| `clause_ancestry` | `as_of` (hex, validated) | 512 events, 512 control failures, 2 048 event edges, 512 blame edges, 512 commit chain; `truncation.cap` is parsed out of the `ancestor_count_within_cap` CHECK rather than carried in Python |
| everything else | path parameters only, `^[A-Za-z0-9._~-]{1,128}$` | single row, or `LIMIT 512` |

Bad input is cheap: `from_seq=-1` → `400`, `from_seq=abc` → `400`, both under 35 ms.

**The worst request is not a read. It is any request while the cluster is not answering.**

```
DSN pointed at an unroutable address, handler called directly:
  GET /v1/health                      503   10 022.9 ms
  GET /v1/ledger                      503   10 046.7 ms
  GET /v1/permits/{id}                503   10 028.4 ms
```

`db.CONNECT_TIMEOUT_SECONDS = 10` against a function `timeout = 15`. So a caller cannot make
one invocation cost more than ~10 s — the ceiling is real — but the day the cluster stops
answering (a CockroachDB Basic spend cap, a maintenance window) **every** request costs 10 s
of billed duration instead of ~20 ms. That is a ~500× step change in Lambda cost per
request, triggered by an event on the *database* side. Handed to W4.

*Not a deployment measurement:* the first request to a fresh emulator process took 10.1 s.
That is a local artefact — `localhost` resolves to `::1` first, the Docker node publishes
only on IPv4, and libpq waits out `connect_timeout` before falling back. Connecting to
`127.0.0.1` takes **3.0 ms**. Recorded so nobody quotes it as a cold-start number.

---

## 6. CORS — the HCL's reasoning is false as deployed, and the delta is smaller than it reads

`infra/modules/demo-api/main.tf` argues that omitting the `cors` block keeps the property
*"any page may make a request and not read the answer"*. `app._response` (`app.py:272`) sets
`access-control-allow-origin: *` on **every** `/v1` response — `200`, `4xx`, `5xx`, and the
`204` answer to `OPTIONS`. Measured with `Origin: https://evil.example`. The static surface
sets no CORS header at all, so the two halves of one origin disagree.

The real delta, stated precisely rather than escalated:

1. **The written justification is false.** Any page can read every `/v1` response
   cross-origin. This repository is public and that sentence is auditable.
2. **The confidentiality delta is zero.** `authorization_type = NONE`, no cookie, no
   `Authorization` header, no credential anywhere. Everything a page can now read
   cross-origin, anyone can read by typing the URL.
3. **No ambient credentials can ever be attached.** `access-control-allow-credentials` is
   unset and the origin is a literal `*`; a browser refuses to send credentials to that
   combination, and there are none to send.
4. **The preflight is incomplete, not permissive.** `OPTIONS` returns `204` with
   `access-control-allow-origin: *` and **no** `allow-methods`, **no** `allow-headers` — so a
   cross-origin `fetch` with `content-type: application/json` is blocked by the browser
   before it is sent.
5. **A CORS *simple request* is not blocked.** `content-type: text/plain;charset=UTF-8`
   carrying a JSON body reached the handler and was parsed — `app._body` ignores the content
   type. Measured: `423` from the guard, i.e. the request arrived. A third-party page can
   therefore drive any `POST` from a visitor's browser. On an unauthenticated endpoint this
   grants an attacker nothing they did not already have except attribution: the requests
   arrive from other people's addresses.
6. `Vary: Origin` is absent. Harmless while the value is a constant `*`.

**Fix, if the sentence is to stay:** either delete the header from `app._response` and drop
the paragraph's claim to what it actually is, or keep the header and rewrite the HCL comment
to say the demo deliberately allows cross-origin reads because there is nothing to protect.
Both are honest. The current pairing is not.

---

## 7. Notes for other workers

* **W3 (DSN).** Nothing in the deployment package reads `MAINLINE_DEMO_DATABASE` — only
  `scripts/deploy/deploy.{sh,ps1}` do. The Lambda connects to whatever database the SSM
  DSN's own path segment names. If that value carries `/defaultdb`, every `/v1` read answers
  `500 UndefinedTable` and `/v1/health` answers `503 no_bookkeeping`. Worth one assertion in
  the deploy script.
* **W4 (cost).** §5's 10 s-per-request floor when the cluster is unreachable.
* **Honesty, outside my slice.** `trappoint.schema_migration` is **empty** in Cloud
  `mainline_demo` (read-only measurement); `trappoint.schema_attestation` holds one row. So
  `GET /v1/health` will answer `200` with `migrations_applied: 0` while the submission and
  `health.py`'s own docstring say 271. `ok` is still `true` because it keys on the
  fingerprint. Someone should own that number.

---

## 8. Verdict

> **NO-GO.** `_demo_guard` is armed at `077a6fdd-2167-559c-b2ff-8e3c8352504d`; the only
> permit in Cloud `mainline_demo` is `dec0de00-0006-4000-8000-000000000001`, whose id the
> same public hostname hands out at `GET /bundle/manifest.json`. The write surface is inert
> today only because of an unrelated `KeyError: 0`, and that defect must be fixed for
> `POST /v1/demo/gate-run` to answer anything but `500` — at which point one anonymous
> request commits `dispositioned → checks_materialised` and swaps the demo's headline
> `23514 gate_closed_when_issued` for `23503 legal_edge`, unrecoverably.
>
> **Exact edit:** in `infra/envs/demo/main.tf`, inside `module "api"`, add
> `scenario_permit_id = "dec0de00-0006-4000-8000-000000000001"` — equivalently, change the
> default at `infra/modules/demo-api/variables.tf:234`. One environment variable on
> `module.api[0].aws_lambda_function.this`; the plan stays 11 to add / 0 to change /
> 0 to destroy. With that one line the same probe returns `423` on all three
> permit-addressed transitions.
>
> Everything else in this slice is **GO**: no read mutates committed state, no route
> discloses another project's data, no credential survives any body, traversal is refused on
> sixteen vectors including two real symlinks, and every query is capped by SQL rather than
> by trust.

*W2, deploy-verification pass. No `terraform` was run. The CockroachDB Cloud cluster was
read with `default_transaction_read_only = on` and `SELECT` only; nothing was written to it.
No credential was printed to stdout, to either of this worker's files, or to the structured
result. The account id is masked as `0229REDACTED8246`.*
