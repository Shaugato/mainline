<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STORE → RETRIEVE → SHOWN TO → ACT

**The artefact:** `evidence/demo/memory-loop.json`
**The generator:** `scripts/proof/memory_loop.py`
**Measured:** 2026-08-15, against
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
**Verdict:** `PROVEN` — 40 rows, 23 of 23 assertions held, exit 0.

```
.venv/Scripts/python.exe scripts/proof/memory_loop.py \
    --base-url https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

Regenerate it and you get the same forty rows off the same five routes, with fresh
`observed_at` stamps. `--base-url` has no default: a default origin here would be a value the
artefact took from its own source, which is the one thing it must never do.

---

## 1 · What the loop is, and where each word lives

An incident happened in 2019. It named a clause. Seven years later a permit relies on that
clause, a retrieval pass finds the incident, ten seconds later the finding becomes an
obligation on the permit, and from that instant a `CHECK` in the database will not let the
permit be issued. **That is the memory. You do not see it by reading it back — you see it by
what it stops.**

Each word is already a live `GET`. **No endpoint was added to make this filmable** — ruling R7
of `docs/demo/proof-and-polish-plan.md`, against the route table at
`verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:229-252`:

| word | route | what it answers |
|---|---|---|
| **STORE** | `GET /v1/clauses/{clause_uuid}/ancestry` | the blame edge from the 2019 event to the clause version |
| **RETRIEVE** | `GET /v1/recall-runs/{run_id}` | when it was read back, under which policy, and how many it found |
| **SHOWN TO** | `GET /v1/receipts/{receipt_id}` | who was shown it, when, and the digest of what they saw |
| **ACT** | `GET /v1/permits/{permit_id}/blocking-checks` | the obligation the memory became |
| **ACT** | `GET /v1/permits/{permit_id}` | the counter it drove, and the `CHECK` written over that counter |

Nothing in the artefact is composed on the client. Every value arrives in an HTTP response
body; the program contributes only **addresses** — route templates, RFC 6901 pointers and
relation names — and even the relation names are confirmed against the `statement_refs` each
response publishes about itself, so a row whose relation is wrong turns the verdict red
instead of reading plausibly. All forty rows confirmed (`every_relation_was_confirmed_by_the_response`,
`40/40`).

### Set the four shell variables first

Every identifier below comes out of the deployment, never out of a file. This is the first
curl, and it is where the other four come from:

```sh
BASE=https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws

CLAUSE=$( curl -s "$BASE/v1/demo/subjects" | jq -r '.data.clause_uuid' )
RUN=$(    curl -s "$BASE/v1/demo/subjects" | jq -r '.data.run_id' )
RECEIPT=$(curl -s "$BASE/v1/demo/subjects" | jq -r '.data.receipt_id' )
PERMIT=$( curl -s "$BASE/v1/demo/subjects" | jq -r '.data.permit_id' )
```

`scripts/proof/memory_loop.py` does exactly this and there is **no UUID literal in it**
(`uuid_literals_in_the_source: 0`). An id transcribed into a source file is a claim about a
deployment made by a file that cannot see it.

### No `jq`? One line, standard library only

Every row in `evidence/demo/memory-loop.json` carries an RFC 6901 `pointer` — the same address
the `jq` filters below spell out. This resolves any of them, and it was run to produce the two
answers shown:

```sh
mlq() { python -c "import json,sys,urllib.request as u,functools as f;print(f.reduce(lambda d,k: d[int(k) if k.isdigit() else k], sys.argv[2].split('/')[1:], json.load(u.urlopen(sys.argv[1]))))" "$1" "$2"; }

mlq "$BASE/v1/clauses/$CLAUSE/ancestry"            /data/events/0/occurred_at   # 2019-03-14T06:20:00Z
mlq "$BASE/v1/permits/$PERMIT/blocking-checks"     /data/checks/0/severity      # 4
```

---

## 2 · The four words, one curl per row

Every row carries the four things: the **word**, the schema-qualified **`table.column`**, the
**live route** that returned it, and the **value with its timestamp**. The timestamp column is
named per row — `occurred_at` for the memory, `started_at` for the retrieval, `issued_at` for
the receipt, `materialised_at` for the obligation, `opened_at` for the subject.

### STORE — `GET /v1/clauses/{clause_uuid}/ancestry`

Timestamp column: `mainline.event.occurred_at` (except where noted).

| `table.column` | value | timestamp | curl |
|---|---|---|---|
| `mainline.event.external_ref` | `DEMO-INC-0001` | `2019-03-14T06:20:00Z` | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.events[0].external_ref'` |
| `mainline.event.occurred_at` | `2019-03-14T06:20:00Z` | *(is the value)* | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.events[0].occurred_at'` |
| `mainline.event.severity_gate` | `4` | `2019-03-14T06:20:00Z` | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.events[0].severity_gate'` |
| `mainline.event.severity_basis` | `human_rated` | `2019-03-14T06:20:00Z` | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.events[0].severity_basis'` |
| `mainline.blame_edge.event_id` | `dec0de00-0005-…-000000000001` | `2019-03-14T06:20:00Z` | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.blame_edges[0].event_id'` |
| `mainline.blame_edge.clause_uuid` | `dec0de00-0004-…-000000000001` | `2019-03-14T06:20:00Z` | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.blame_edges[0].clause_uuid'` |
| `mainline.blame_edge.commit_id` | `9f12114d…49a39` | `2026-01-08T00:00:00Z` (`mainline.commit_obj.committed_at`) | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.blame_edges[0].commit_id'` |
| `mainline.clause_blame_current.max_severity` | `4` | `2026-08-10T02:57:43.852434Z` (`computed_at`) | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.closure.max_severity'` |
| `mainline.clause_blame_current.virulence` | `blood_major` | `2026-08-10T02:57:43.852434Z` | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.closure.virulence'` |
| `mainline.clause_blame_current.ancestor_count` | `1` | `2026-08-10T02:57:43.852434Z` | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.closure.ancestor_count'` |
| `mainline.clause_blame_current.as_of_commit` | `9f12114d…49a39` | `2026-08-10T02:57:43.852434Z` | `curl -s "$BASE/v1/clauses/$CLAUSE/ancestry" \| jq -r '.data.as_of_commit'` |

**The edge names a commit, not a clause.** `blame_edge.commit_id` is the *version* of the
clause the incident reached, which is why the memory cannot slide onto a later rewrite of the
same paragraph without somebody deciding it should.

### RETRIEVE — `GET /v1/recall-runs/{run_id}`

Timestamp column: `mainline_meas.recall_run.started_at` for every row.

| `table.column` | value | curl |
|---|---|---|
| `mainline_meas.recall_run.started_at` | `2026-08-02T03:00:00Z` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.started_at'` |
| `mainline_meas.recall_run.n_candidates` | `1` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.counts.n_candidates'` |
| `mainline_meas.recall_run.n_blocking` | `1` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.counts.n_blocking'` |
| `mainline_meas.recall_run.n_silenced` | `0` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.counts.n_silenced'` |
| `mainline_meas.recall_run.policy_version` | `demo-recall-1.0` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.policy_version'` |
| `mainline_meas.recall_run.index_generation` | `g1` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.index_generation'` |
| `mainline_meas.recall_run.index_plan_digest` | `d98e50a8…39b` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.index_plan_digest'` |
| `mainline_meas.recall_run.corpus_commit` | `9f12114d…49a39` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.corpus_commit'` |
| `mainline_meas.recall_run.run_id` | `dec0de00-0009-…-000000000001` | `curl -s "$BASE/v1/recall-runs/$RUN" \| jq -r '.data.run_id'` |

`n_silenced` is `0`, and that is a claim, not a blank: nothing was suppressed on the way to the
signer. `index_plan_digest` is what makes the retrieval reproducible rather than merely
recalled — and `corpus_commit` is byte-identical to `as_of_commit` above, which the artefact
asserts (`retrieve_ran_over_the_clause_version_store_wrote`).

### SHOWN TO — `GET /v1/receipts/{receipt_id}`

Timestamp column: `mainline.exposure_receipt.issued_at` for every row.

| `table.column` | value | curl |
|---|---|---|
| `mainline.exposure_receipt.actor_sub` | `demo.signer` | `curl -s "$BASE/v1/receipts/$RECEIPT" \| jq -r '.data.actor_sub'` |
| `mainline.exposure_receipt.issued_at` | `2026-08-02T03:05:00Z` | `curl -s "$BASE/v1/receipts/$RECEIPT" \| jq -r '.data.issued_at'` |
| `mainline.exposure_receipt.receipt_digest` | `993c00c3…af46` | `curl -s "$BASE/v1/receipts/$RECEIPT" \| jq -r '.data.receipt_digest'` |
| `mainline.exposure_receipt.policy_version` | `demo-recall-1.0` | `curl -s "$BASE/v1/receipts/$RECEIPT" \| jq -r '.data.policy_version'` |
| `mainline.exposure_line.check_id` | `dec0de00-0007-…-000000000001` | `curl -s "$BASE/v1/receipts/$RECEIPT" \| jq -r '.data.lines[0].check_id'` |
| `mainline.exposure_line.payload_digest` | `d48e0eb9…c55b` | `curl -s "$BASE/v1/receipts/$RECEIPT" \| jq -r '.data.lines[0].payload_digest'` |

A memory nobody was shown cannot bind anybody. The receipt is digested **per line**, so
*"I was never told about that one"* is a checkable claim rather than an argument. The receipt's
`policy_version` is the run's `policy_version` — asserted, across two responses
(`retrieve_and_shown_to_share_the_policy`).

> **Stated as staged, not glossed over.** `expires_at` on this receipt is `2027-01-01`. In the
> product a receipt's TTL is hours; the long window exists so the demo keeps working for the
> whole judging period. `docs/deploy/cloud-database.md` §5 records it, and so does the payload.

### ACT — `GET /v1/permits/{permit_id}/blocking-checks` and `GET /v1/permits/{permit_id}`

Timestamp column: `mainline.blocking_check.materialised_at`, or `mainline.permit.opened_at`
(`2026-08-02T00:00:00Z`) for the permit's own rows.

| `table.column` | value | curl |
|---|---|---|
| `mainline.blocking_check.materialised_at` | `2026-08-02T03:00:10Z` | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].materialised_at'` |
| `mainline.blocking_check.origin` | `blame_ancestry` | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].origin'` |
| `mainline.blocking_check.precursor_event_id` | `dec0de00-0005-…-000000000001` | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].precursor_event_id'` |
| `mainline.blocking_check.recall_run_id` | `dec0de00-0009-…-000000000001` | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].recall_run_id'` |
| `mainline.blocking_check.severity` | `4` — **projected**, see §4 | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].severity'` |
| `mainline.blocking_check.virulence` | `blood_major` — **projected**, see §4 | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].virulence'` |
| `mainline.disposition.disposition_id` | `null` — still open | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].disposition_id'` |
| `mainline.blocking_check.check_id` | `dec0de00-0007-…-000000000001` | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].check_id'` |
| `mainline.blocking_check.commit_id` | `9f12114d…49a39` | `curl -s "$BASE/v1/permits/$PERMIT/blocking-checks" \| jq -r '.data.checks[0].commit_id'` |
| `mainline.permit.open_blocking` | `1` | `curl -s "$BASE/v1/permits/$PERMIT" \| jq -r '.data.counters.open_blocking'` |
| `mainline.permit.gate_epoch` | `1` | `curl -s "$BASE/v1/permits/$PERMIT" \| jq -r '.data.gate_epoch'` |
| `mainline.permit.state` | `dispositioned` | `curl -s "$BASE/v1/permits/$PERMIT" \| jq -r '.data.state'` |
| `pg_catalog.pg_constraint.conname` | `gate_closed_when_issued` | `curl -s "$BASE/v1/permits/$PERMIT" \| jq -r '.data.constraints[] \| select(any(.counters[]?; .column=="open_blocking")) \| .constraint'` |
| `pg_catalog.pg_constraint` · `pg_get_constraintdef(oid)` | `CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))` | `curl -s "$BASE/v1/permits/$PERMIT" \| jq -r '.data.constraints[] \| select(any(.counters[]?; .column=="open_blocking")) \| .predicate'` |

Three of those rows are the whole product in one line:

* `state` is `dispositioned`. That is the client **claiming** every obligation is disposed of.
* `open_blocking` is `1`. That is the database saying it is not.
* the predicate is `open_blocking = 0`, from `pg_catalog` — so `merged` is unreachable.

The artefact locates that constraint **by the counter column it reads**, never by array
position, and records how (`the_gate_constraint_was_located.by`). It then asserts three things
about it: the predicate demands zero, the counter is not zero, and the counter equals the
number of obligations actually open — `open_blocking=1  open_obligations=1`, which is the
projection agreeing with the base rows rather than being taken on trust.

---

## 3 · The ten seconds, computed

```
mainline_meas.recall_run.started_at        2026-08-02T03:00:00Z   GET /v1/recall-runs/{run_id}
mainline.blocking_check.materialised_at    2026-08-02T03:00:10Z   GET /v1/permits/{permit_id}/blocking-checks
                                           ─────────────────────
                                           10.0 s
```

Both are **columns**. They arrive in **two different responses**. The gap is the subtraction of
one ISO-8601 string from the other, performed in `compute_gap()`; the number ten is nowhere in
the program (`"stated_anywhere_in_this_program": false`).

It is then **corroborated against the repository**, and reported with its own status so that
*not found* can never be read as *agreed*. The instants the deployment served are re-spelled in
the seed's `TIMESTAMPTZ` form and searched for:

| | status | where |
|---|---|---|
| RETRIEVE `2026-08-02 03:00:00+00` | `AGREES` | `verticals/mainline/db/seeds/demo/demo_permit.sql:250` |
| ACT `2026-08-02 03:00:10+00` | `AGREES` | `verticals/mainline/db/seeds/demo/demo_permit.sql:321` |

Ten seconds is what the retrieval-to-obligation path costs in this seeded world. It is a
narrative interval in a synthetic history, not a benchmark of the running system, and the
artefact says so by naming the two columns rather than calling it a latency.

---

## 4 · Every `4` names the thing that wrote it (ruling R9)

**Three different `4`s appear in this loop and three different things wrote them.** A `4` with
no provenance is a number somebody could have typed, so the artefact attaches a `written_by`
block to each one — and to each `blood_major`.

| where | value | written by | projected? |
|---|---|---|---|
| `mainline.event.severity_gate` | `4` | the seed, **and the row says so**: `severity_basis` = `human_rated`, at `/data/events/0/severity_basis` | no |
| `mainline.clause_blame_current.max_severity` / `.virulence` | `4` / `blood_major` | `computed_by` = `verticals/mainline/db/seeds/demo/demo_world.sql`, `projector_ver` = `demo-1` — **both columns, both in the response body** | no — this is the ancestry fact the projector reads *from* |
| `mainline.blocking_check.severity` / `.virulence` | `4` / `blood_major` | **`mainline.fn_check_project`**, invariant **MI25**, welded `BEFORE INSERT FOR EACH ROW` by `0120_trg_check_project.sql` | **yes** |

The third row is the one that matters, and here is what stands behind it — three citations,
each **located by search** so the artefact carries the file, the line and the literal line
rather than a sentence somebody typed:

```
verticals/mainline/db/migrations/0120_trg_check_project.sql:7
    -- MI: MI25

verticals/mainline/db/seeds/demo/demo_permit.sql:318
      0, 'routine', 0,                       -- projected over by fn_check_project (MI25)

docs/deploy/cloud-database.md:808
    overwritten by `fn_check_project` from `mainline.clause_blame_current` (invariant MI25).
```

The seed writes **`0` and `'routine'`** onto that obligation. The deployment serves **`4` and
`blood_major`**. Those are parsed off the seed line and compared against the wire, as two
assertions that can turn the verdict red:

```
severity_was_projected_not_typed     wire=4              seed=0
virulence_was_projected_not_typed    wire='blood_major'  seed='routine'
the_projection_took_the_ancestry_severity   clause_blame_current.max_severity=4 == blocking_check.severity=4
the_projection_took_the_ancestry_band       clause_blame_current.virulence='blood_major' == blocking_check.virulence='blood_major'
```

*Nobody typed the four* is one of the strongest sentences this project owns, and it is only
true because the projection ran. So the sentence is never printed without the projector's name.

---

## 5 · Why this is a stronger memory proof than teach → restart → recall

The field's usual demonstration of agentic memory is **teach → restart → recall**: tell the
agent something, restart the process, watch it repeat the thing back. That shows persistence.
It is worth having and it is not what is happening here.

**Teach.** The 2019 incident and the blame edge are written once, by a seed applied through
psql — `verticals/mainline/db/seeds/demo/demo_world.sql`, the event at line 272 and the edge at
299. `occurred_at` is 2019 **on purpose**: it is far outside any garbage-collection window on
any CockroachDB tier, so the history the demo shows lives in the commit DAG and in that row —
never in MVCC, never in a cache, never in a context window.

**Restart, in a stronger sense than a process restart.** Nothing about the read path shares
anything with the write path. A different **actor** wrote it (a migration-time seed) from the
one reading it (the deployed read API). A different **application** reads it — a Python Lambda
under `mainline_demo_api`, not psql. A different **session**, a different **connection**, a
different **process**, on a different day: the artefact carries both the deployment's
`observed_at` and the client's `read_at` for every row, and the closure's own
`computed_by`/`projector_ver` columns name its writer in the same body that serves it. Nothing
is handed forward in memory. The only thing shared between teaching and recalling is the
database.

**Recall — and this is where it stops resembling the usual demonstration.** The system does not
repeat the memory back. It **refuses**. `open_blocking = 1` and the `CHECK` says `merged`
requires zero, so the permit cannot be issued. The memory's effect is a door that will not open,
and you can watch it not open.

Two more things are true, and neither is measured by this artefact — they belong to files that
do measure them, and are named rather than borrowed:

* **The gate re-derives rather than trusting the counter.** Force `open_blocking` to zero out
  of band, the way a bad `UPDATE` or a disarmed projector would leave it, and the merge is
  refused **anyway**: `P0001`, `mainline.fn_permit_merge_gate`, *"re-derived open obligation
  count is 1 while the projected counter reads zero"* — conformance case CF-03, verdict
  `PROVEN`, in `evidence/gate-refusal/proof-20260815T054237Z.json`. That proof builds its own
  throwaway history rather than reading the seeded demo world, and it says so. The same beat
  against the deployment is beat 3 of `POST /v1/demo/gate-run` and belongs to the live-beats
  transcript.
* **A gate that always refuses is a broken gate, not a safe one.** Sign one disposition and the
  same merge is `ADMITTED`, `00000`, in the same artefact. The memory binds; it does not
  paralyse.

**So: most systems prove memory by recalling something. This one proves memory by refusing
something — and proves the memory is real by refusing again after the number it reads was
falsified.** That is the whole claim, and nothing beyond it is claimed here.

---

## 6 · What the artefact does to keep itself honest

`evidence/demo/memory-loop.json` carries 23 assertions and every one of them can turn the
verdict red. Four are about the artefact rather than the loop:

* **`no_measured_value_originates_in_this_source`** — the program reads its own bytes and
  searches them for every value it recorded: all forty row values, all forty timestamps, the
  subjects and the deployment identity. `hits=0  uuids=0`. **This check has already gone red
  once**, on this file, because early drafts of the docstrings quoted `human_rated` and
  `blood_major` in prose. The prose was changed; the check was not weakened. Two scoping rules
  are stated in the artefact rather than left implicit: values under five characters are
  exempt from the textual search and carry the deployment's own provenance chip instead (a
  `1` or a `4` occurs in any source file by coincidence), and a match flanked by identifier
  characters is not an occurrence — the database is called `mainline_demo` and the package that
  serves it is `mainline_demo_api`.
* **`every_relation_was_confirmed_by_the_response`** — `40/40`. Each row's `table.column` is
  checked against the `statement_refs` the response published about itself, and where the
  reader publishes its SQL, the artefact records whether the column is named directly or under
  an alias.
* **`the_superseded_year_is_absent` / `the_incident_date_is_present`** — ruling R8. The
  finished document is scanned; `2019-03-14` occurs 8 times and the year some drafts wrongly
  carried occurs `0`. Twenty hex digests are masked before the scan, because a sha256 may
  legitimately contain any four digits and a check that fires on one teaches its reader to
  ignore it.
* **`every_route_answered_200`** — the five reads, by name and status.

The artefact also publishes `published_sql`: every statement the deployment chose to disclose,
keyed by the relation it names, including the `pg_catalog.pg_constraint` query behind the
predicate above. Relations whose reader publishes nothing are listed with `null` rather than
omitted, so *"the response named this relation and did not publish its statement"* stays
visible.

### What this program does not do

`GET` only. No `POST`, not even `/v1/demo/gate-run`. No AWS client, no Terraform verb, no SSM
parameter, no credential, no header but `accept`. It writes exactly one file — and it writes it
on a red verdict too, because an artefact that can only be produced when everything is green is
an artefact that hides the day it isn't.

Exit codes: `0` PROVEN · `1` NOT PROVEN, file still written and the failed assertion named ·
`2` the deployment did not answer, which is deliberately **not** `1` so that *"there was no
deployment"* is never read as *"the loop did not close"*.
