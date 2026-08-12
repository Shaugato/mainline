<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# SUBMISSION FINALISATION — plan 2, written from measurements taken 2026-08-12

**Lead:** submission-finalisation. **Workers:** 10, disjoint paths, briefs below.
**Repo:** `github.com/Shaugato/mainline`, PUBLIC, default branch `master`, HEAD `1d41442`.
**Deadline:** 2026-08-18 21:00 UTC. `check_submission_ready.py` says 6d 8h remain.

---

## 0 · The brief I was given was stale in one place and incomplete in three

The brief named one defect: `app.py:120 _routes()` omits `POST /v1/demo/gate-run`.

**That defect is already fixed.** Commit `b0fe884` added the seventeenth route. Measured
today:

```
app.ROUTES -> 17 rows, including Route(POST /v1/demo/gate-run -> demo_gate_run)
```

`verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:_routes()` carries a
docstring that already says so in the past tense, and
`evidence/deploy/gate-run-reachable.json` is the artefact. `tests/test_routes_gate_run.py`
pins it.

The headline beat still does not answer, for **four** reasons instead. I proved three of
them on this machine in under ten minutes and the fourth by reading the committed plan.
Two of them are recorded in the repository already — `docs/deploy/JUDGE-PACK.md` §6 lists
them honestly, which is exactly the discipline this project claims and evidently keeps.
Two are new.

---

## 1 · DEFECT A — `row_factory=dict_row` against positional row access · PROVEN TODAY

`verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:309` opens every production
connection with `row_factory=dict_row`. `reads.py` was written to that convention — 43
`row["name"]` accesses, zero positional. `scenario.py`, `gate_run.py` and `transitions.py`
were not.

`scenario.resolve()` at `scenario.py:274` does:

```python
row = conn.execute(_RESOLVE_SQL, (sc.permit_id,)).fetchone()
(external_ref, state, head_seq, gate_epoch, open_blocking,
 open_derived, check_id, site_code) = row
```

Unpacking a `dict` yields its **keys**. `check_id` becomes the literal string
`"check_id"`, which is then bound as `$2` of `_RECEIPT_SQL` (`scenario.py:294`).

Reproduced against the pinned local node, `w_s08_demo_state`:

```
$ python -c "... db.connection(dsn=...); scenario.resolve(conn)"
row_factory: <function dict_row>
RESOLVE FAILED: InvalidTextRepresentation error in argument for $2:
  could not parse "check_id" as type uuid: uuid: incorrect UUID length: check_id
DETAIL: statement summary "SELECT r.receipt_id FROM mainline.exposure_receipt AS r..."
```

That is **character-for-character** the failure `evidence/deploy/acceptance.json` records
for both gate runs against the emulated Function URL:

```
"POST /v1/demo/gate-run (run 1) returned 500, expected 200 — database_error ·
 resource=demo_gate_run · [22P02] error in argument for $2: could not parse "check_id"
 as type uuid"
```

Forcing `conn.row_factory = tuple_row` makes `resolve()` succeed immediately
(`check=4800ba2e-… state=dispositioned open=1`). So the diagnosis is complete and the
fix direction is decided: **make the three modules dict-aware**, matching `reads.py` and
`db.py`. Do **not** flip `db.py` to `tuple_row` — that breaks 43 call sites in `reads.py`
and the twelve read endpoints they serve.

Positional-index census in the affected modules: `scenario.py` 1, `transitions.py` 10
(lines 287, 650, 802 among them), `gate_run.py` 47 of which most are `beats[n]` list
indexing and a handful — 509, 580, 596 — are row accesses. Every one must be inspected,
not pattern-replaced.

**Why the tests never caught it:** `tests/test_gate_run.py` connects with
`psycopg.connect(w4_database, autocommit=False)` — psycopg's default `tuple_row`. The
production path and the test path use different row factories, so the contract that
matters was never asserted. **W1 must add that assertion**, not just the fix.

---

## 2 · DEFECT B — the deployed Lambda would point at a permit that is not there · BLOCKER ON THE APPLY

The founder has authorised `terraform apply` conditional on this verification returning
GO. **It must not return GO until this is corrected**, because the apply as planned ships
a demo that answers `422 demo_history_not_seeded` to every judge.

`evidence/deploy/terraform-plan-furl.txt:304-312`, the committed plan the founder read:

```
+ environment {
    + variables = {
        + "MAINLINE_DEMO_DATABASE"      = "mainline_demo"
        + "MAINLINE_DEMO_PERMIT_ID"     = "077a6fdd-2167-559c-b2ff-8e3c8352504d"
        + "MAINLINE_SCENARIO_PERMIT_ID" = "077a6fdd-2167-559c-b2ff-8e3c8352504d"
```

`scripts/deploy/seed_demo.py:104` — the script that seeded the live Cloud database:

```python
PERMIT_ID = "dec0de00-0006-4000-8000-000000000001"
```

`verticals/mainline/db/seeds/demo/demo_permit.sql:230` inserts that same `dec0de00-…`
row, and `evidence/deploy/acceptance.json`'s `permit_invariant` block read
`dec0de00-0006-4000-8000-000000000001` back out of `mainline_demo`. The `077a6fdd-…`
value is `scenario.demo_uuid("permit")` — a uuid5 derivation
(`scenario.py:77`) that nothing has ever seeded.

Three files carry the wrong default: `infra/modules/demo-api/variables.tf:234`,
`infra/modules/demo-api/README.md:766-767`, and the two committed plan artefacts.
`docs/deploy/JUDGE-PACK.md` §6 item 3 already names the disagreement. Nobody has changed
the value the apply would use.

W2 corrects the Terraform default, **re-runs `terraform plan`** (init/validate/plan/show
only — `apply` is the orchestrator's and no worker may run it), regenerates both
committed plan artefacts, and proves by read-only query which permit ids actually exist
in `mainline_demo`. If the plan's `11 to add, 0 to change, 0 to destroy` shape moves for
any reason other than the two env strings, that is a finding and it is reported, not
smoothed.

---

## 3 · DEFECT C — the exposure receipt expires two hours after seeding · NEW, AND FIVE TESTS ARE RED FOR IT RIGHT NOW

`scenario._RECEIPT_SQL` requires `r.expires_at > now()`. With no live receipt,
`resolved.receipt_id is None`, and `gate_run.py:541` **skips beat 4** — the admission.
A skipped beat 4 makes the verdict `NOT PROVEN`. The demo's whole point is that the gate
refuses *and then admits*; without beat 4 it is a gate that only ever says no, which
`gate_run.py` itself calls broken.

Measured on `master` today:

```
$ pytest tests/test_gate_run.py -q
5 failed, 11 passed, 1 skipped in 9.41s
FAILED test_gate_run_verdict_is_proven
  AssertionError: ["beat 4 (admit): expected {'outcome':'admitted','sqlstate':'00000'},
                    observed outcome='skipped'"]
FAILED test_beat_four_admits_with_a_server_computed_clearance_digest
FAILED test_every_table_row_count_is_identical_across_a_gate_run
FAILED test_two_consecutive_runs_see_the_same_subject
FAILED test_concurrent_runs_do_not_collide
```

The committed evidence claims `209 passed, 1 skipped`. That measurement is stale.

Cause, read straight off the rows:

```
w_s08_demo_state  receipt eb537556  issued 2026-08-11T05:40Z  expires 2026-08-11T07:50Z
                                                       now()  2026-08-12T12:27Z
w_w4_api_transitions  every receipt expired 2026-08-11
```

`verticals/mainline/apps/demo-api/tests/conftest.py:650` and
`scripts/proof/gate_refusal.py:1152` both insert `expires_at = now() + INTERVAL '2 hours'`.
That is a *correct* TTL for a fresh run. It becomes a time bomb because
`conftest.py:756-766` **reuses an existing fixture database whenever its marker row is
present** — so a database seeded yesterday is adopted today with a dead receipt, and the
suite reports a product failure that is really a fixture failure.

**The live Cloud demo is NOT exposed to this.** `demo_permit.sql:226-243` sets
`expires_at = 2027-01-01`, with a comment saying exactly why and pointing at
`DEMO-HONESTY.md`'s STAGED column. That is the right call and it stays.

What must change is the fixture and the local seeder: the marker check must verify the
receipt is *live*, not merely that the database *exists*, and `seed_demo_state.py` must
print the wall-clock instant after which a local demo run will start skipping beat 4 —
because `VIDEO-KIT.md` sends the founder to that script before a shoot, and a shoot that
overruns by two hours currently yields silent `NOT PROVEN` on camera.

Do **not** widen the TTL blindly. `0066_disposition.sql:185` bounds
`expires_at <= signed_at + max_ttl_hours * INTERVAL '1 hour'`. The demo seed's long
window is legal under the demo policy row; a test fixture's may not be.

---

## 4 · DEFECT D — two prose violations the submission gate already catches

`scripts/submission/check_submission_prose.py` exits non-zero today:

```
FAIL docs/submission/JUDGING-AXES.md:175 [SUB-05-conformance-passes]
  "and the conformance suite was demonstrated end to end for the first time"
  WHY The conformance suite has NEVER been demonstrated.
FAIL docs/submission/VIDEO-KIT.md:179 [SUB-06-migration-count]
  WHY The migration count MOVES. Quote the artefact, or re-derive it.
2 submission-prose violation(s), 0 claim-hygiene violation(s)
```

These are the repository's own rules firing on the repository's own documents. They are
cheap and they are exactly the sort of thing a judge who reads carefully will find.

---

## 5 · What else is stale, measured

| claim | where | truth on 2026-08-12 |
|---|---|---|
| repository is PRIVATE | `STATE-OF-THE-BUILD.md` §3.3 heading and §5 row; `DEVPOST.md:211`; `RULES-MATRIX.md` R1 and the `repo_public` row | **PUBLIC.** `check_submission_ready.py` no longer reports `repo_public` as a failing row |
| `audit_public_readiness.py` VERDICT: NOT READY | the script, `PUBLIC-READINESS.md` | still emitted, and now describes a flip that already happened. Needs a post-flip mode: the findings become a *disclosure register*, not a gate |
| "the flip publishes all 45 commits" / "53 commits" / "38 commits" | three documents, three numbers | `check_submission_ready.py` measures **47** today. Re-derive, never remember |
| Bedrock never executed | `STATE-OF-THE-BUILD.md` §3.3's premise, superseded by `evidence/deploy/aws-live.json` | Bedrock **executes**: `sts:GetCallerIdentity` req `04018eca-…`, `bedrock:ListFoundationModels` req `d8c940e8-…`, Titan v2 200 / 1024-d / L2 1.00000006, `au.anthropic.claude-haiku-4-5` 200 `end_turn`. Total spend USD 0.00006 |
| tool-usage census fresh | `capture_tool_evidence.py --check` | **STALE by 1 byte** on `crdb-features.json`. One byte, and it is still a red gate — regenerate it |
| `RULES-MATRIX.md` §2 generated table | rows `repo_public`, `remote_sync` (94 uncommitted paths), `disclosure` (38 commits), `deadline` (7d 14h) | every one of those four numbers has moved |
| `POST /v1/demo/gate-run` is not routed | `JUDGE-PACK.md` §6 item 1 | fixed at `b0fe884`; 17 routes |

`docs/TOOL-USAGE.md` is in good shape — 4 CockroachDB tools with 10 engine features,
12 AWS services, every row already carrying a verdict. What it lacks is the **AWS request
ids** now that they exist, and a re-measure of the Lambda/IAM/SSM row, which stays
DESIGNED until the apply happens and must not be pre-promoted.

---

## 6 · Sequencing

```
W1 rowfactory ─┐
W2 permit-id  ─┼──> W4 acceptance ──┬──> W5 JUDGE-PACK
W3 receipt-ttl ┘                    └──> W8 RULES-MATRIX + SUBMISSION.json
W6 TOOL-USAGE    ── independent
W7 DEVPOST       ── independent
W9 VIDEO-KIT     ── independent
W10 stale sweep  ── independent
```

W1, W2, W3 are the critical path and start immediately. W4 cannot begin until all three
land, because its deliverable is a `PROVEN` acceptance transcript and it must not
hand-wave one. W5 and W8 quote W4's verdict, so they finish last.

---

## 7 · Binding rules for every worker

1. **NO WORKER MAY RUN `terraform apply`.** `init`, `validate`, `plan`, `show`, and
   read-only AWS/CRDB calls only. The orchestrator applies.
2. **Never print a credential** into output, into a file, or into a structured result.
   The `mainline_judge` password is not to be rotated, echoed, or referenced by value.
   `JUDGE-PACK.md` keeps a placeholder; the orchestrator fills it.
3. **Fix causes.** `continue-on-error`, `|| true`, and lowered ratchets are banned. A red
   that reports true incompleteness stays red with a sharper message.
4. **Re-derive every number you write.** Quote the command and its output. A remembered
   count is a claim you cannot defend to a stranger, and the repository is public.
5. **File ownership is absolute.** If you need a file you do not own, record the finding
   in your evidence artefact and name the owner. Do not edit it.
6. **No TODOs.** No placeholder prose except the two the orchestrator fills: the judge
   credential and the two `UNRESOLVED` submission fields.
7. Python is `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`. Windows
   `PYTHONPATH` separator is `;`. Local DSN
   `postgresql://root@localhost:26257/defaultdb?sslmode=disable`.
8. `CREATE SEQUENCE` / `nextval` / `SERIAL` / `unique_rowid()` are banned; `FAMILY` is
   reserved. Cloud needs a `40001 RETRY_SERIALIZABLE` retry loop.

---

## 8 · The GO/NO-GO this lead owes the orchestrator

**Current answer: NO-GO on the apply**, for Defect B alone. The plan the founder approved
would deploy a Lambda whose `MAINLINE_DEMO_PERMIT_ID` names a permit that has never been
seeded into `mainline_demo`. Everything else about the plan — 11 to add, `authorization_type
= NONE`, ap-southeast-1, ~USD 0.02/month, CloudFront correctly excluded — reads sound.

GO requires, in order: W2's corrected plan artefacts; W1 and W3 landed; W4 returning a
`PROVEN` acceptance transcript from the real handler over HTTP with no work-arounds.
