<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE CLOUD DATABASE — `mainline_demo` on CockroachDB Cloud

**What this page is.** The demo runs against one database on one managed CockroachDB cluster in
Singapore. This is how that database is built, who may connect to it, what is in it, and how to
check every sentence below without trusting this page.

> ## ⚠ NO REAL INCIDENT. NO REAL SITE. NO REAL FATALITY.
>
> Everything seeded into this database is synthetic and corresponds to nobody. The operator, the
> four people, the document, the clause and the 2019 incident are invented for this demonstration.
> That sentence is `verticals/mainline/demo/DEMO-HONESTY.md`'s, and it is repeated here, at the
> head of the page that describes the data, because a disclosure filed somewhere else is a
> disclosure nobody reads at the moment it matters. Every seeded row is also flagged synthetic in
> the data itself — see §4.

---

## 0 · The state of it, measured

Every number in this table was produced by a program in `scripts/deploy/`, against the live Cloud
cluster, and is readable in the evidence file named beside it. Nothing here is documentation of an
intention.

| | | Artefact |
|---|---|---|
| Cluster | `mainline-dev`, SERVERLESS/Basic, `aws-ap-southeast-1`, routing id `mainline-dev-31219` | `evidence/deploy/cloud-chain.json` → `target` |
| Server | CockroachDB CCL **v26.2.5** | same, `target.version` |
| Database | **`mainline_demo`** | same, `target.database` |
| Migrations | **271 files, 271 applied, 0 failed** | same, `applied` / `failed` / `rows` |
| Chain wall clock | **359.1 s** applying, 388.9 s including create + bootstrap | same, `chain_seconds` / `total_seconds` |
| Bootstrap | `trappoint migrate bootstrap`, 8.1 s, as its own step | same, `bootstrap` |
| Files needing a `40001` retry | **0** | same, `files_that_needed_a_retry`, `retried_files` |
| Connection drops mid-chain | **0** | same, `connection_reconnects` |
| `gc.ttlseconds` | requested 4500, **accepted**, read back as **4500** | same, `zone` |
| Slowest file | `0180_disposition_peer_visible.sql`, **8.99 s** | same, `slowest` |
| Tree fingerprint | `fe27b620…db7a1a15` | same, `tree_fingerprint` |
| Live fingerprint | `06b0ad84…ce24a79b` | same, `live_fingerprint` |
| Seeded permit | `dec0de00-0006-4000-8000-000000000001` (`DEMO-PTW-0001`) | `evidence/deploy/cloud-seed.json` → `subject` |
| Its merge | **REFUSED `23514` `gate_closed_when_issued`**, constraint name *reported* by the driver | same, `verification` |
| After rollback | permit still `dispositioned`, `open_blocking` still 1, **0** merge records | same, `verification.after_rollback` |

**The chain is complete.** `docs/HONESTY.md` says five tables have consumers and no producer, and
the deploy lead measured 246 of 261 applying to Cloud this morning with fifteen `42P01` failures.
That is no longer the state of the tree: W1 landed the producers, the tree is 271 files, and all
271 applied to Cloud. The evidence file's `failures` array is empty and its
`failures_by_missing_object` map has no keys — which is a claim you can falsify by opening it.

---

## 1 · Three programs, in this order

```bash
# 1 — the schema.  ~6.5 minutes on Cloud, ~2 minutes on the local node.
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --recreate

# 2 — the two logins.  Prints two passwords ONCE.  Capture them.
.venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate

# 3 — the demo world, and the proof that the seeded permit is refusable.
.venv/Scripts/python.exe scripts/deploy/seed_demo.py

# 4 — and now that the permit exists, re-probe the API login end to end.
.venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate
```

All three read `COCKROACH_DSN` from the repo-root `.env`, which is not committed. **No program in
`scripts/deploy/` ever prints a DSN, a password, or a query string that could carry one**;
`cloud_chain.redact()` is the single chokepoint every printed and persisted string passes through,
and it is applied to driver error messages too, because `psycopg.OperationalError` quotes the
connection string on almost every failure path.

`uv` is not installed on this machine, so nothing here goes through `uv run`. The interpreter is
`.venv/Scripts/python.exe` and the console script is `.venv/Scripts/trappoint.exe`, named
explicitly.

### Re-running changes nothing

That is the property the deploy is built around, and it is demonstrated rather than asserted:

```
$ .venv/Scripts/python.exe scripts/deploy/cloud_chain.py      # second run, no flags
outcome       unchanged
chain         271/271 applied, 0 failed
wall clock    18.3s
```

`cloud_chain.py` writes a marker row into `trappoint.deploy_chain` holding the tree fingerprint
(what the migration files say) and the live fingerprint (what the cluster holds). A later run
recomputes the live fingerprint and compares both:

| Situation | What happens | Exit |
|---|---|---|
| both fingerprints match | reports `unchanged`, applies nothing | 0 |
| the migration tree changed | **refuses**, names `--recreate`, changes nothing | 3 |
| the live schema drifted | **refuses**, names `--recreate`, changes nothing | 3 |
| the database exists with no marker | **refuses**, names `--recreate`, changes nothing | 3 |

Refusing is the deliberate choice. Migration files are forward-only and are not written
`IF NOT EXISTS`; replaying them over a live database produces a wall of `42P07` that says nothing
about whether the schema is right. **A deploy tool that cannot tell "already correct" from
"differently wrong" should say so and stop.**

The `unchanged` run does *not* overwrite the evidence file, either. The per-file timings and
attempt counts only exist on the run that applied the chain, so a no-op run merges itself into the
existing document as a `rechecks` entry and leaves the 271 rows where they are. An idempotent
deploy that deleted its own measurements on every re-run would be a poor bargain.

`seed_demo.py` is idempotent by construction — fixed UUIDs, fixed timestamps, deterministic
`digest(...)` values — and it was run three times against Cloud. `row_counts`, `observed` and
`verification` were byte-identical across runs apart from timings.

---

## 2 · The `40001` retry, and the honest size of the claim

The first attempt to build this database on Cloud, using `scripts/proof/gate_refusal.py`
unmodified, died:

```
gate_refusal: could not reach the cluster: restart transaction:
TransactionRetryWithProtoRefreshError: TransactionRetryError:
retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)
```

A single-node Docker cluster never produces that. A managed multi-node cluster does, and neither
`trappoint migrate up` nor the proof script retries. So every applier in `scripts/deploy/` shares
one executor (`cloud_chain.Applier`) that retries `40001` up to six times with a linear-scaled
backoff (0.25 s × attempt), re-establishes a dropped connection rather than counting it as a file
failure, and **reports how many files needed a retry**.

On the run recorded here, and on the lead's earlier run, that number was **zero**.

That is stated plainly because the alternative is worse. Retry here is insurance against a failure
mode observed once in three runs, not a workaround for a constant. Publishing "0" is what makes
the loop's presence a measurement rather than a superstition — and if it ever becomes non-zero,
`retried_files` in the evidence names the files.

---

## 3 · The two logins

`scripts/deploy/cloud_roles.py` creates exactly two, and nothing else.

### `mainline_api` — what the Lambda connects as

| Holds | Why |
|---|---|
| `CONNECT` on `mainline_demo` | |
| `USAGE` on `mainline`, `mainline_meas`, `mainline_audit`, `mainline_ops` | |
| `SELECT` on 31 enumerated tables and views | the demo's read surfaces (`API_READ`) |
| `SELECT` on 10 further tables | **what the gate transaction's trigger chain reads** (`API_GATE_READ`) |
| `SELECT` on the 14 `mainline_audit` views | enumerated by name, never wildcarded |
| `UPDATE` on `permit`, `blocking_check`, `change_request` | what `merge_permit` and the disposition triggers write |
| `INSERT` on `permit_event`, `merge_record`, `refusal_ledger`, `disposition`, `disposition_citation`, `override_ledger`, `ledger_intake`, `mainline_ops.outbox` | ditto |
| `EXECUTE` on `mainline.merge_permit` | the merge itself |
| Membership in `auditor_ro`, `agent_gate`, `svc_disposition` | **row-level-security scope — see below** |
| **Nothing at all in `mainline_qa`** | S14, re-revoked on every run |
| **No `DELETE`, anywhere** | MI01 |

**Why memberships and not only grants.** Four tables carry `FORCE ROW LEVEL SECURITY`
(`RLS-MATRIX.yaml`: `permit`, `change_request`, `disposition`, `mainline_meas.standing`), and under
FORCE, *"if RLS is enabled but no policies apply to a given combination of user and SQL statement,
access is denied by default."* A bare `GRANT SELECT ON mainline.permit` therefore buys **zero
rows, silently** — the worst failure an audit surface can have, because it is indistinguishable
from a clean site. The policies are written `TO <role>` and match any member, so `mainline_api` is
made a member of the three roles the demo's three beats impersonate: `auditor_ro` (`fleet_scope`,
`disposition_service_read`), `agent_gate` (`service_read`, `gate_insert`, `gate_write`) and
`svc_disposition` (`gate_write`, `disposition_insert`).

The memberships buy **scope**, not privileges: `GRANTS.yaml`'s table matrix is applied by
`trappoint migrate grants apply`, and on a freshly migrated database
`information_schema.table_privileges` for those three roles returns **no rows**. So every table
privilege is granted directly. Relying on inheritance would have produced a login that can see
nothing.

**The gate-read list was discovered by running it, not by reading the schema.** No trigger function
in migrations 0100–0149 is `SECURITY DEFINER` — `GRANTS.yaml` records that as an open coupling
rather than hiding it — so the merge transaction's triggers read tables no demo screen ever shows.
The method was a loop: run the three beats as `mainline_api`, parse the `42501`, grant exactly the
named privilege on the named relation, repeat. Thirteen grants, in the order they were demanded:

```
UPDATE blocking_check · SELECT change_request · INSERT ledger_intake · SELECT identity_residue
SELECT permit_boundary · SELECT permit_slice · SELECT override_ledger · SELECT unwitnessed_debt
SELECT disposition_citation · SELECT mechanism_predicate · UPDATE change_request
SELECT cr_clause · SELECT cr_event
```

The `change_request` entries are there because `fn_disposition_close` and `fn_check_materialised`
branch on `subject_kind` and touch the change-request arm even when the subject is a permit.
Guessing this list from the architecture would have produced a login that fails in the middle of
the demo's second beat, in front of a judge, with a privilege error.

### `mainline_judge` — what a judge gets

`SELECT` on the fourteen `mainline_audit` views. That is the whole of it.

It also holds `USAGE` on `mainline`, `mainline_meas` and `mainline_ops` — **and that is not a
loophole, it is a measured requirement.** On CockroachDB v26.2.5 a view runs the underlying query
with its owner's *table* privileges, but the *schema* `USAGE` check is made against the invoker
regardless:

```
with USAGE on mainline_audit only:
  SELECT count(*) FROM mainline_audit.v_open_gate_summary
    → 42501  user mainline_judge does not have USAGE privilege on schema mainline

with USAGE additionally on mainline, mainline_meas, mainline_ops:
  SELECT count(*) FROM mainline_audit.v_open_gate_summary   → OK, rows=1
  SELECT count(*) FROM mainline.permit
    → 42501  user mainline_judge does not have SELECT privilege on relation permit
```

`USAGE` is the right to name a schema; it is not the right to read anything in it, and the second
probe is the evidence rather than the assurance. `mainline_qa` is absent from that list and always
will be — without `USAGE` the schema is not even nameable, which is a stronger position than a
revoked `SELECT`.

### The probes, which are the actual control

`GRANTS.yaml`'s own header says it: *a GRANT is a claim about intent, a `42501` is evidence about
behaviour.* `cloud_roles.py` connects **as each login** and asserts in both directions. Seventeen
probes, all agreeing, against the Cloud cluster:

```
probes        mainline_api
  ok [00000] read the gated subject (RLS must let it through)      rows=1
  ok [00000] read the obligation                                   rows=1
  ok [00000] read the corpus                                       rows=1
  ok [00000] read the recall pass                                  rows=1
  ok [00000] read the audit surface                                rows=1
  ok [42501] mainline_qa is unreachable (S14)
  ok [42501] mainline_qa per-person view is unreachable (S14)
  ok [42501] no DELETE anywhere (MI01)
  ok [23514] drive the demo's first beat (CALL mainline.merge_permit)  gate_closed_when_issued

probes        mainline_judge
  ok [00000] read the audit surface                                rows=1
  ok [00000] read the silence summary                              rows=0
  ok [00000] read the conservation law                             rows=1
  ok [42501] the base tables are unreachable
  ok [42501] the corpus is unreachable
  ok [42501] mainline_meas is unreachable
  ok [42501] mainline_qa is unreachable (S14)
  ok [42501] no write path exists
```

The last `mainline_api` probe is the one that matters most: it calls `mainline.merge_permit` on the
seeded permit and asserts the refusal is the **product's** refusal rather than a privilege error.
The statement aborts on the refusal, so nothing is written. A login that reads everything and
cannot drive the gate would pass the other eight probes and fail the demo.

### The passwords

Generated by `secrets.token_urlsafe(24)`, printed to stdout **once**, never written to a file,
never logged, never in an evidence artefact. There is no `--password` option, deliberately: an
operator who cannot pass a password on a command line cannot leave one in shell history.

They were **rotated after this page's measurements were taken and were not retained.** Run

```bash
.venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate
```

when you are ready to capture them, and put them straight into SSM Parameter Store as
SecureStrings — which is also where the deploy plan §2.5 says the DSN belongs, written by the CLI
and never by Terraform, because a Terraform-managed secret is a plaintext secret in the state file.

A re-run **without** `--rotate` leaves existing passwords alone and says so. A deploy script that
silently rotated a secret would take the demo down every time somebody re-ran it.

**Building an application DSN.** Take `COCKROACH_DSN`, swap the userinfo, keep everything else —
host, port, `sslmode=verify-full` and any `options` — because a Cloud Basic DSN's query string is
load-bearing:

```
postgresql://mainline_api:<password>@mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257/mainline_demo?sslmode=verify-full
```

---

## 4 · The demo world

Two SQL files, both readable by a judge, both idempotent:

* `verticals/mainline/db/seeds/demo/demo_world.sql` — the static corpus
* `verticals/mainline/db/seeds/demo/demo_permit.sql` — one permit, one open obligation

### What is in it, measured after seeding

| Table | Rows | | Table | Rows |
|---|---|---|---|---|
| `mainline.site` | 1 | | `mainline.permit` | 1 |
| `mainline.person` | 2 | | `mainline.permit_clause` | 1 |
| `mainline.signing_credential` | 2 | | `mainline.permit_event` | 2 |
| `mainline.commit_obj` | 2 | | `mainline.boundary_certificate` | 1 |
| `mainline.commit_edge` | 1 | | `mainline.blocking_check` | 1 |
| `mainline.doc` | 1 | | `mainline.exposure_receipt` | 1 |
| `mainline.clause` | 1 | | `mainline.exposure_line` | 1 |
| `mainline.clause_version` | 1 | | `mainline_meas.recall_policy` | 1 |
| `mainline.event` | 1 | | `mainline_meas.recall_run` | 1 |
| `mainline.blame_edge` | 1 | | `mainline_meas.silence_receipt` | 1 |
| `mainline.clause_blame_closure` | 1 | | `mainline_ops.outbox` | 1 |
| `mainline.cbm_account` | 1 | | **`mainline.disposition`** | **0** |
| `mainline.ledger_checkpoint` | 1 | | **`mainline.merge_record`** | **0** |
| `mainline.cosignature` | 1 | | | |

The two zeros are the demonstration. Everything else is the history a real permit would carry; the
one thing missing is a human's signed answer to the one obligation the recall pass raised.

### Everything is flagged synthetic *in the data*

Not only in this page, and not only in `DEMO-HONESTY.md`:

* external references are prefixed `DEMO-` (`DEMO-INC-0001`, `DEMO-PTW-0001`, `DEMO-SOP-0001`)
* every free-text field opens with `SYNTHETIC —` (title, narrative, commit message, attribution)
* every JSONB payload carries `"synthetic": true` and names the seed file that wrote it
* every provenance column names the seed file (`computed_by`, `projector_ver`, `wrote_as`)
* every principal is prefixed `demo.` (`demo.signer`, `demo.countersigner`)
* every identifier begins `dec0de00`, so a demo row is greppable in a log by eight characters

`SELECT ... WHERE narrative LIKE 'SYNTHETIC%'` is a census anyone can run.

### The state the seed produces, and what "open" means

```
permit.state          = 'dispositioned'    the client's claim that everything is answered
permit.open_blocking  = 1                  written by the trigger, not by the seed
blocking_check        = 1 row, severity 4, virulence 'blood_major'   (both PROJECTED)
disposition           = 0 rows
```

`mainline.subject_state` has no member called `open` — the alphabet is
draft / checks_materialised / dispositioned / merged / suspended / closed / abandoned (migration
0011). `dispositioned` is the state from which `merged` is the next legal transition, and it is the
state in which the client is *claiming* every obligation now carries a signed disposition. It does
not. That claim is what the gate exists to disbelieve.

**The counter is not written by the seed.** `open_blocking` is incremented by the trigger
`check_materialised` (0121 → `fn_check_materialised`, 0101). `scripts/proof/gate_refusal.py` writes
that counter by hand, because on the tree it was written against `mainline_ops.outbox` had no
producer and 0121 could not apply. On `mainline_demo` it applies, so the projection is the
projection — and `seed_demo.py` records `projection_trigger_check_materialised_present: true` and
`re_derived_open_obligations: 1` in the evidence, because "the trigger wrote it" is a claim that
should carry its check.

`severity` and `virulence` are supplied as `0` / `'routine'` by the seed and are immediately
overwritten by `fn_check_project` from `mainline.clause_blame_current` (invariant MI25). The
evidence reads them back as `4` / `blood_major`, which is how you know the projection ran.

### Two things about these files that are the schema's decision, not a preference

1. **`mainline.site.site_code` is the site's own UUID rendered as text.**
   `mainline.fn_recall_policy_anchored` (0112, fired by 0136) checks
   `WHERE cp.site_code = ((NEW).site_id)::STRING`, so the custody ledger's partition key for a site
   *is* its identifier. Renaming that seam to make the seed prettier would be seeding a different
   schema from the one that ships.

2. **The recall run lives in `demo_permit.sql`, not in `demo_world.sql`.**
   `mainline_meas.recall_run.permit_id` is `NOT NULL REFERENCES mainline.permit`: a recall run in
   this schema is a permit-scoped fact and cannot exist before its permit. CockroachDB validates
   foreign keys per statement and has no deferrable constraints, so no ordering of the two files
   puts the run in the static corpus.

### One thing that is STAGED, and is named as staged

The seeded exposure receipt expires on **2027-01-01**. In the product a receipt's TTL is hours —
`mainline.exposure_receipt` constrains only `expires_at > issued_at` and the application picks the
window. The long window exists so the admission beat keeps working for every judge for the whole
judging period rather than for two hours after somebody ran the deploy. It belongs in
`DEMO-HONESTY.md`'s STAGED column and it is written into `demo_permit.sql` beside the row, so that
nobody reads it as the product's default.

`DEMO-HONESTY.md` §3 already lists the pre-seeded permit under STAGED for the same reason: the
permit's existence is staged, **the gate evaluation is not**, and no part of either seed file
touches the gate.

### Idempotence, and the one trap in it

`ON CONFLICT DO NOTHING` does **not** suppress an exception a BEFORE INSERT trigger has already
raised — conflict resolution happens after the trigger runs. Measured: a second run of
`demo_world.sql` raised

```
P0001  MAINLINE: closure generations must be dense and monotone
```

from `fn_closure_guard` and aborted the whole batch. That is the guard working correctly —
generation 0 has already been used for that (clause, commit). So the three tables whose INSERT
fires a BEFORE trigger that can raise (`clause_version`, `clause_blame_closure`, `cbm_account`) use
`INSERT ... SELECT ... WHERE NOT EXISTS`, which never offers the row. The two `permit_event` rows
use the same form for a different reason: the second event's `prev_digest` must read the first
event's trigger-computed `chain_digest`, and only an `INSERT ... SELECT` can.

---

## 5 · The verification, which is a rolled-back merge

`seed_demo.py` does not stop at counting rows. Counting rows proves the seed ran; it does not prove
the seed produced *the state the demo needs*. A permit with an open obligation **and** a missing
boundary certificate also has one blocking check and also refuses — with a different SQLSTATE,
naming a different exhibit, for a reason that has nothing to do with the product's central claim.

So the script asks the database, and rolls the whole thing back:

```
MERGE         REFUSED [23514] gate_closed_when_issued (reported)
rollback      nothing_persisted=True
```

`constraint_source: "reported"` means the exhibit came from `diag.constraint_name` — the driver's
own field, not a string parsed out of a message. `spec/errors.md` §3.1 requires that distinction to
be recorded, because a parsed exhibit is a weaker diagnosis.

`after_rollback` reads the permit and `merge_record` back in a fresh transaction: state still
`dispositioned`, `open_blocking` still 1, zero merge records. **This is the property the whole demo
rests on** — the deploy plan §1.4 measured that a full `ROLLBACK` leaves the seeded row untouched,
so every judge drives the real gate against the real seeded history, concurrently, and finds the
database exactly as the last one left it. No per-visitor state, no reset button, no cleanup
sweeper. `seed_demo.py` exercises that property on every run, so if it ever stops holding, this is
where it is found out.

The full three-beat sequence — refuse, refuse-under-forged-counter, admit-after-one-signature — was
also driven end to end as `mainline_api` under `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`:

```
beat1   [23514] gate_closed_when_issued
beat2   [P0001] MAINLINE: merge refused by mainline.fn_permit_merge_gate
                — re-derived open obligation count is 1 while the projected counter reads zero
sign    [00000]
beat3   [00000]
```

That is the demo. The second beat is the one no `CHECK` can hold: the projected counter is forced
to zero out of band — exactly what a disarmed projector or a bad `UPDATE` would leave — and the
gate refuses anyway, because it **re-derives** the count instead of trusting the column.

---

## 6 · How to check that this page is not lying

```bash
# the schema, and that a second run changes nothing
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py            # expect: outcome unchanged, exit 0

# the seed, and the refusal, without applying anything
.venv/Scripts/python.exe scripts/deploy/seed_demo.py --check      # expect: REFUSED [23514], exit 0

# the two logins, in both directions (needs the passwords)
MAINLINE_API_PASSWORD=... MAINLINE_JUDGE_PASSWORD=... \
  .venv/Scripts/python.exe scripts/deploy/cloud_roles.py --verify --password-from-env

# and the same three programs against a throwaway local database, on a laptop
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py \
    --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable \
    --database w_scratch --recreate
```

The local rehearsal is worth running. It applies the same 271 files to the same server version, in
about two minutes, and it is where every behaviour on this page was found before it was claimed
about Cloud. Note one honest difference: the local development node runs `--insecure` and
CockroachDB refuses to hold a password there at all — *"setting or updating a password is not
supported in insecure mode"* — so `cloud_roles.py` creates the logins without one and says so on
every probe line. A passing rehearsal is not a passing deployment, and the output never lets the
two be confused.

---

## 7 · Cost

The database contributes **$0.00/month**. CockroachDB Cloud Basic's free allowance (100 M RU,
10 GiB) covers a demo whose entire working set is 27 rows and whose gate run is four statements,
and the cluster's `spend_limit` is a hard ceiling: the cluster stops before the bill does.

The `--recreate` path costs one full chain apply (≈390 s of DDL). Everything after that is the
`unchanged` path, which is two fingerprint computations and a `SHOW ZONE CONFIGURATION`.

---

## 8 · What is not here

* **No `mainline_qa` access, for anybody, on any tier.** S14. Both logins are re-revoked on every
  run and both are probed for `42501`. The judge pack's own envelope names `mainline_qa` as
  never-issued and this deployment keeps that true.
* **No second cluster.** `verticals/mainline/demo/judge/PACK.md` names a cluster
  `mainline-verify` that does not exist. This deployment uses one cluster, `mainline-dev`, because
  a second Basic cluster splits the same free allowance for no isolation the demo needs. That
  discrepancy belongs to the judge-pack owner and is recorded here rather than quietly patched.
* **No `AS OF SYSTEM TIME` anywhere.** The GC window on this database is 4500 seconds and the
  demo's ancestry reaches back to 2019. Long-horizon history is the application-level commit DAG
  and the `occurred_at` column, both of which are ordinary data.
* **No adverse witness.** The cosignature in `demo_world.sql` §8 is our own. The mechanism is
  exercised; the row is not an independent party's signature, and `DEMO-HONESTY.md` §4 already says
  adverse witnesses are not running.
* **Row-level security is not a defence against a cluster administrator.** It is tenancy hygiene
  and information partitioning between principals who all legitimately hold the privilege.
  `RLS-MATRIX.yaml`'s SEC-1 header says it first and this page repeats it, because the login that
  built this database can read past every policy on it.
