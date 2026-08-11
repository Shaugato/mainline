<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-demo-api` — the read API the console has been asking for

One AWS Lambda handler over CockroachDB. **No web framework.** Twelve GET resources, one
envelope, a provenance chip beside every claim, and a health check cheap enough to run
from a cron for eight days without costing anything.

Until this distribution existed, `grep -rl "fastapi\|flask\|starlette\|uvicorn\|aiohttp.web"`
over every `.py` and `.toml` outside `.venv` returned **nothing**. The console declares
sixteen resources in `apps/console/src/data/resources.ts` and holds the JSON Schema for
each in `apps/console/contracts/`; nothing implemented any of them. This implements the
twelve GETs and the spine the four POSTs plug into.

---

## What it is, in five files

| File | What it owns |
|---|---|
| `app.py` | The routing table and `handler(event, context)`. The whole server. |
| `envelope.py` | The read envelope, the five provenance chips, and the driver-value → contract-shape encoding. |
| `db.py` | One connection per container, the DSN from SSM, and the `40001` retry. |
| `reads.py` | The twelve GET resources. |
| `health.py` | `GET /v1/health`. |

`mainline_demo_api.transitions` — the four POSTs — is a **separate worker's module** in the
same package. `app.py` imports it lazily and answers `501` naming it when it is absent, so
the read surface is deployable before the write surface exists. The signature is fixed:

```python
handle_transition(resource_key, path_params, body, conn) -> tuple[int, dict]
```

## Why there is no framework

A Lambda invocation is already a function call with a dict argument. Putting Mangum in
front of FastAPI would translate that dict into an HTTP request so a framework could parse
it back into a dict — three dependencies, a cold-start penalty, and a second routing table
to keep in sync with `resources.ts`. The dependency closure is `psycopg` **and the standard
library**, including the SigV4 signing for the one SSM call, and
`tests/test_envelope.py::test_the_only_third_party_import_in_the_read_spine_is_psycopg`
is what keeps that sentence true rather than aspirational.

Build the deployment package the way the deployment lead measured it (21 MB unzipped,
against Lambda's 250 MB limit):

```bash
pip install --target build/python \
    --platform manylinux2014_x86_64 --implementation cp --python-version 3.13 \
    --only-binary=:all: psycopg==3.3.4 psycopg-binary==3.3.4
```

Terraform's `handler` may be `mainline_demo_api.app.handler` or
`mainline_demo_api.app.lambda_handler`; both names are exported.

---

## The contract is not ours to change

`apps/console/src/data/transport.ts::finishExchange` validates every byte this API emits
and enforces four post-conditions in order: the body parses; it satisfies the resource's
contract; `envelope.resource` equals the key requested; `envelope.schema_id` is the exact
`$id` the console holds. On the last one it is unforgiving, and says why:

> *A payload that names a contract we do not hold is not forward compatibility; it is an
> unverifiable claim.*

So `envelope.SCHEMA_IDS` is a **transcription** of `resources.ts`, not a derivation — six
of the sixteen resources name a contract file whose stem is not their key — and
`tests/test_envelope.py` re-parses that TypeScript on every run and fails the build if the
two ever drift. The same test compares the routing table and the declared path/query
parameters.

### The envelope

```jsonc
{
  "envelope_version": 1,
  "resource": "permit",
  "schema_id": "https://console.mainline.trappoint.org/contracts/1.0/permit.schema.json",
  "observed_at": "2026-08-10T02:38:57.470133Z",
  "server_date": "2026-08-10T02:38:57.470133Z",   // the DATABASE's now(), not the Lambda's
  "staged": false,
  "staged_note": null,
  "statement_refs": [{ "kind": "table", "object": "mainline.permit", "text": null }],
  "provenance": [{ "pointer": "/counters/open_blocking", "chip": "db:column" }],
  "data": { }
}
```

`server_date` is read from the database's own `now()`. The console subtracts it from
`Date.now()` to render clock skew in the honesty chrome; stamping a Lambda's clock there
would show a judge how well AWS keeps time — a true statement about the wrong machine.

### The five chips, and what each actually claims

| Chip | Claim |
|---|---|
| `db:column` | The database wrote this value into that column. Not "a query returned it" — a *column*. |
| `db:constraint` | The name or text of a CHECK/FK exactly as the catalog reports it. |
| `recomputed` | The **console** re-derived it from signed bytes in a Worker (D6). **This API never emits it** — an emitter cannot vouch for a recomputation the reader has not performed. |
| `derived` | Computed by this API from columns it names in `statement_refs`. |
| `staged` | Hand-authored, with no cluster behind it. |

A pointer absent from the list gets **no chip**, which is the contract's own instruction:
*an unclaimed provenance is better than a comfortable default.* The list is capped at 256
entries, so long arrays get their computed fields chipped first and the rest go unclaimed
rather than being swept under one coarse `db:column`.

---

## What is honest about this API, in the places it matters

**`propagation` is staged in full, and says so in words.**
`mainline.lesson`, `mainline.propagation` and `mainline.merge_conflict` are consumed by
`propagation.schema.json` and produced by **no migration in this repository** — `to_regclass`
returns `NULL` for all three, and the probe that establishes it is carried in
`statement_refs` on every response. The contract requires a `lesson` object with eight
non-null members, so there is no way to answer from columns at all. The response is
`staged: true` with a note naming all three tables, every pointer chipped `staged`, and the
console renders STAGED across the surface. **It is not an empty list** — an empty list is
the claim *there are no lessons*, which is a different sentence and a false one. The staged
payload is byte-stable (UUID5 identifiers, digests that are SHA-256 of their own labels),
which is the most a fabricated payload can honestly offer: not evidence, but
reproducibility. The probe runs on every request, so the day a migration produces those
tables this resource reports `501` instead of quietly continuing to serve fiction.

**`silence` flags exactly one field.** Everything in a silence payload is a column of
`mainline_meas.silence_ledger`, `silence_receipt` or `recall_run` — except
`receipt.bound.statement`, the bounding sentence the contract requires on every exhibit,
which no column carries. It is reproduced verbatim from `spec/wire/candidate-commitment.md`
and `trappoint_recall.per.receipt.PER_BOUND_SENTENCE`, chipped `staged`, and the envelope's
note names the one field and lists the columns that produced the rest.

**`truncation.cap` is read out of the CHECK that declares it.** `ancestry.schema.json`
requires the ancestor cap; this API does not carry its own copy of `512`. It parses
`CONSTRAINT ancestor_count_within_cap CHECK (ancestor_count <= 512)` out of
`pg_get_constraintdef` and chips it `db:constraint`. A migration that raised the cap moves
this number with no Python edit.

**The gate constraints come from the catalog, not from a list.** A gate refusal is a CHECK
whose predicate mentions the literal `'merged'`. On `mainline.permit` that selects seven of
thirteen — the six gate constraints plus `merge_evidence`, which is exactly what the
contract says the array holds — and on `mainline.change_request` it selects four. Neither
number is known to this code in advance.

**`blocking_check.open` is `derived`, and `severity` is `db:column`.** There is no `open`
column; it is the absence of a live row in `mainline.disposition`. Meanwhile `severity`,
`virulence` and `closure_gen` are chipped `db:column` *precisely because nobody who wrote
the check chose them* — `fn_check_project` overwrites all three from `clause_blame_current`
on the way in. The chip is not "we read a column"; it is "the writer did not choose this".

**Inclusion and consistency proofs are computed, labelled `derived`, and only when they
can be honest.** RFC 6962 §2.1.1/§2.1.2, over the stored leaf hashes, and **only** when the
leaf window is dense from `seq = 0` and covers the checkpoint's `tree_size`. Anything else
would be a proof over a subset presented as a proof over the tree; when the window does not
qualify the arrays are empty. `tests/test_reads.py` verifies every emitted proof against
the checkpoint root with an independently written verifier.

**A row the contract cannot express is a `409`, not a fudge.** `exposure.schema.json`
requires `permit_id`; `mainline.exposure_receipt.permit_id` is nullable because a receipt
may belong to a change request. Asked for such a receipt this API answers `409` naming the
field and the row rather than inventing an id or dropping the resource to `null`. Same for
a disposition whose subject is a change request, and for a `silence_receipt` whose stored
`boundary_proof` lacks `leaf_s`.

**`reading_floor` is `null`.** S19's arithmetic (tau0, rho, t_min) is on no table in this
tree. `mainline.disposition` records `reading_floor_met` as a projected boolean and
`mainline.permit` projects `unmet_floor_count`; the components are nowhere. `null` is the
contract's own provision for that, and it is truthful where a reconstructed tau0 would not
be.

---

## Configuration

| Variable | Meaning |
|---|---|
| `MAINLINE_DSN` | A DSN, used directly. **Wins when set.** This is what lets the whole read surface run on a laptop with no AWS credentials. |
| `MAINLINE_DSN_PARAM` | The **name** of the SSM SecureString holding the DSN. Read once per cold start, cached for the container's life, never logged. |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | Which SSM endpoint to address. |
| `MAINLINE_DEBUG` | `1` adds a six-frame traceback to a `500` body. Off in the deployed stack. |

The DSN carries the `mainline-sql` password. It is written by the deploy script with
`aws ssm put-parameter`, **never by Terraform** — a Terraform-managed secret is a plaintext
secret in the state file. Terraform is given the parameter *name*; the Lambda role gets
`ssm:GetParameter` + `kms:Decrypt` on that one ARN. `db.redact()` exists so the one place
that would otherwise print a DSN has something correct to print.

### `40001` is retried on reads, and only on reads

A single-node Docker cluster never produces `RETRY_SERIALIZABLE`. A managed multi-node
cluster does — the deployment lead's first Cloud run of 2026-08-10 died on exactly that,
with no retry loop anywhere in the repository. `db.read()` retries the **whole callable**,
because the retry unit of a serializable transaction is the transaction; re-running one
statement of an aborted one is how you get `25P02`.

It is deliberately **not** offered to the POST side. A transition is not idempotent,
`40001` there means UNDECIDED, and `transport.ts` bans a blanket retry for that reason:
*a helper that re-sends a merge because a socket closed is a helper that can issue a permit
twice.*

Each read runs inside `SET TRANSACTION READ ONLY`, so several statements see one snapshot
and a stray write fails with `25006` — measured on CockroachDB v26.2.5,
`cannot execute INSERT in a read-only transaction`. It is applied per transaction, not per
session, because `app.py` hands the same connection to `handle_transition`.

---

## Routes

| Method | Path | Resource |
|---|---|---|
| GET | `/v1/health` | — (not an envelope) |
| GET | `/v1/permits/{permit_id}` | `permit` |
| GET | `/v1/permits/{permit_id}/blocking-checks` | `blocking_checks` |
| GET | `/v1/permits/{permit_id}/silence` | `silence` |
| GET | `/v1/change-requests/{cr_id}` | `change_request` |
| GET | `/v1/checks/{check_id}/disposition` | `disposition` |
| GET | `/v1/receipts/{receipt_id}` | `exposure_receipt` |
| GET | `/v1/clauses/{clause_uuid}/versions/{commit_id}` | `clause_version` |
| GET | `/v1/clauses/{clause_uuid}/ancestry?as_of=` | `clause_ancestry` |
| GET | `/v1/ledger?site_code=&from_seq=&to_seq=` | `ledger` |
| GET | `/v1/recall-runs/{run_id}` | `recall_run` |
| GET | `/v1/lessons/{lesson_id}/propagation` | `propagation` (staged) |
| GET | `/v1/audit` | `audit` |
| POST | four transitions | `mainline_demo_api.transitions` |

Statuses: `200` an envelope · `400` a parameter this resource cannot use · `404` no such
subject · `405` the path exists under another method · `409` the row exists and the
contract cannot express it · `501` the transitions module is not deployed · `503` no DSN or
no database · `500` everything else, with the SQLSTATE when the driver gave one.

A refused transition is **not** an error: it arrives from `transitions` as an `invoke`
envelope with `outcome: "refused"` and is passed through untouched.

### `GET /v1/health`

One round trip, no joins — `version()`, `current_database()`, `now()` and two scalar
subqueries over the `trappoint` bookkeeping tables. Nothing touches `mainline.*`, so the
cost does not grow with the demo's data.

```json
{"ok": true, "cluster_version": "CockroachDB CCL v26.2.5 …", "database": "…",
 "schema_fingerprint": "<64 hex>", "migrations_applied": 271,
 "server_date": "…Z", "seconds": 0.0121}
```

`migrations_applied` is `count(*)` of `trappoint.schema_migration` in state `applied` — the
bookkeeping ledger `trappoint migrate up` writes, **not** a count of files on disk. Against
this distribution's own test fixture it is **0**, because `conftest._apply_chain` executes
each migration directly so it can continue past a failure and report the whole census; the
deployed cluster, migrated with the real command, reports 271. The fingerprint is real
either way: `trappoint migrate bootstrap` writes the genesis attestation and that is the row
this endpoint reads.

`200` if and only if `ok`. `503` with `reason: "dsn_unset"` when nobody told the function
where the database is; `503` with `reason: "unreachable"` when it did not answer; `503`
with `reason: "no_bookkeeping"` when it answered and has no `trappoint` schema — a real
state, and reporting it as healthy would make this a liveness probe for a Lambda rather
than a health check for a demo. Every `503` body names the failure.

This endpoint is what the GitHub Actions cron checks. The alternative was priced and
refused: one CloudWatch Synthetics canary at five-minute intervals is **$10.37/month**,
thirty times the cost of the rest of the stack combined.

---

## Running the tests

```bash
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests --crdb=reuse
```

`--crdb=reuse` is the repository convention: one shared node per session, never a container
per module. `conftest.py` reads the four DSN names `trappoint-testkit` publishes and then
`127.0.0.1:26257`, and **skips with the reason there is none** — a skip with no reason is
indistinguishable from a deleted test.

The fixture builds a database named for the SHA-256 of every migration's name and bytes,
applies all 271 files (46.7 s on this machine), seeds a history that has something true to
say about all twelve resources, and records the fingerprint and the seeded identifiers in
`w3_fixture.ready`. A second run reuses it; one edited migration builds a new one.

`jsonschema` is not installed in this repository's virtualenv and installing it would
change shared state no worker owns, so `conftest.py` implements the subset of draft 2020-12
that `console/contracts/` actually uses — twenty-six keywords, enumerated by walking the
sixteen documents, with an **unimplemented keyword raising rather than passing**. It reads
the very files `console/src/data/schema.ts` reads; validating against a re-typed copy would
be testing the copy.

Measured on 2026-08-10: **113 tests in this distribution's two modules, all passing**;
`ruff check` and `ruff format --check` clean over all nine files.

---

## Known limits

* **`recall_run.arms` is omitted.** No per-arm table exists; `mainline_meas.recall_run`
  carries only the aggregate `arms_degraded`. The field is optional in the contract, and an
  empty array would claim there were no arms.
* **`audit.unreachable` reports `not_probed`.** The negative assertion the contract wants —
  that the Managed-MCP service account cannot reach `mainline_qa` — is not one this API is
  entitled to make: it connects as the demo's own read role, so a probe from here would
  answer a different question.
* **`checkpoint.log_key` and `cosignature.witness_key` are `null`.** No column carries a
  C2SP verification key on this tree. The contract already says a bundle carrying its own
  trust anchor proves nothing; `null` is the honest value.
* **A ledger leaf with no `mainline.ledger_intake` row is not rendered.** The join is inner,
  because the contract requires `entry_kind`, `canon_bytes_b64`, `actor` and `recorded_at`
  and all four live on the intake row.
* **`exposure_line.payload_digest` is passed through, not verified.** The console re-derives
  it in a Worker; that is `recomputed`, and it is the reader's chip, not ours.
