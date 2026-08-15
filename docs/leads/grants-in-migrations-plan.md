<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# PRIVILEGE AS CODE — the plan, and the ruling that changes its shape

**Lead:** privilege-as-code · **Date:** 2026-08-15 · **Repo:** `D:/CoackroachDBxAWS/mainline`,
branch `master`, HEAD `e88b8b6` · **Live URL measured before writing this:**
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

---

## 0. WHAT I MEASURED BEFORE I DECOMPOSED

`GET /v1/health` on the live URL, 2026-08-15:

```
ok=true  database=mainline_demo  cluster_version=CockroachDB CCL v26.2.5
deploy_chain_applied=271  deploy_chain_files=271  migrations_applied=0
schema_fingerprint=ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339
seconds=0.0152
```

Local CockroachDB v26.2.5 answers on `localhost:26257` and already carries ~150 ephemeral
worker databases, so every leg of this plan is buildable and falsifiable offline.

---

## 1. RULINGS

These are rulings, not opinions. Each names its authority. Workers do not relitigate them;
a worker who finds a ruling false brings the measurement that falsifies it and stops.

### R1 — The brief's premise is factually wrong, and I correct it in writing.

The brief and `evidence/deploy/LIVE.md:66` both say *"There is not one GRANT statement in the
271 migrations."* Measured:

```
$ grep -rlE "^\s*(GRANT|REVOKE)" verticals/mainline/db/migrations/ | wc -l
10
```

Those ten are `0007a`–`0007e` (five `REVOKE`s stripping `public` from the five schemas),
`0009a`–`0009d` (the `GRANT CREATE`/`GRANT USAGE` floor) and `0009f`
(`REVOKE CREATE ON SCHEMA public`). Seventeen further migrations — `0006a`–`0006i` and
`0180a`–`0180h` — `CREATE ROLE`. **Authority: the files on disk.** The sentence in `LIVE.md`
is wrong and is corrected by W5 rather than quietly deleted.

### R2 — The absence of the *rest* of the grants is a documented decision, and I do not overturn it.

`verticals/mainline/db/migrations/0009e_default_privileges_floor.sql` states the reasoning at
exactly the point in the numbered sequence where a reader goes looking for `GRANT` statements
and does not find them:

> Roles and grants are CLUSTER state that a RESTORE into a fresh cluster does not carry, so
> they cannot be applied once by a forward-only migration and assumed thereafter.

and closes with the sentence that decides this whole wave:

> The control was never the GRANT. It is the privilege probe that asserts 42501 for every
> (role, object) pair the matrix does NOT name: a GRANT is a claim about intent, a 42501 is
> evidence about behaviour.

`GRANTS.yaml`'s header (557 lines, `verticals/mainline/db/GRANTS.yaml`) says the same thing
twice more, and names the probe — not the matrix — as the real control.

**Nothing in today's five outages contradicts that reasoning.** The outages were not caused by
grants living outside migrations. They were caused by the role that the public endpoint runs as
living outside the declarative matrix *entirely*. Moving privilege into the migration chain
would not have caught a single one of them, because the missed grants were never declared
anywhere at all. **Authority: `0009e` and `GRANTS.yaml`'s header, neither of which this wave
produced evidence against.**

### R3 — The real defect, which the brief did not name: `mainline_api` is not in `GRANTS.yaml`.

`GRANTS.yaml` declares nineteen roles. `mainline_api` is not among them, and neither is
`mainline_judge`. Their entire privilege surface is five Python tuples in a deploy script:
`API_READ`, `API_GATE_READ`, `API_WRITE`, `AUDIT_VIEWS`, `API_MEMBERSHIPS` in
`scripts/deploy/cloud_roles.py`.

Worse: **`trappoint migrate grants apply` never runs against the cloud demo cluster at all.**
`scripts/deploy/deploy.sh` runs `cloud_chain.py` (271 files) then `seed_demo.py`, with
`cloud_roles.py` invoked out of band at line 397. `grep -n "grants apply" scripts/deploy/deploy.sh`
returns nothing.

So the privilege-as-code machinery this repository already owns and already tests has never
been pointed at the one role an anonymous caller on a `authorization_type = NONE` Function URL
actually executes as. **That is the class.** It is a bigger finding than the eight grants.

### R4 — The hand-fix was applied to the cluster and never to the code. Measured, offline.

Thirty-nine schema-qualified relations are referenced by the shipping demo-api source under
`verticals/mainline/apps/demo-api/src/mainline_demo_api/`. **Eleven of them are named nowhere in
`scripts/deploy/cloud_roles.py`:**

```
mainline.control_failure          mainline.ledger_leaf         trappoint.deploy_chain
mainline.defeater_option          mainline.ledger_node         trappoint.schema_attestation
mainline.delta_witness            mainline.receipt_expiry      trappoint.schema_migration
mainline.event_edge               mainline_meas.silence_ledger
```

That set is precisely the "`mainline.defeater_option` and 7 others", "schema `trappoint`
USAGE", "`trappoint.deploy_chain` + 2" and "`mainline_meas.silence_ledger`" that
`evidence/deploy/LIVE.md:60-64` records as hand-granted against the live cluster on 2026-08-14.

**Consequence, stated plainly: re-running `cloud_roles.py` against a fresh cluster today would
reproduce all five outages.** The live cluster has been repaired; the repository has not. This
is an unrecorded live regression and it is the single most important thing in this wave.

### R4b — A sixth gap, not yet triggered, found while measuring R4.

`transitions.py:891` issues `INSERT INTO mainline.exposure_receipt` and `transitions.py:969`
issues `INSERT INTO mainline.exposure_line`. Both relations appear in `API_READ` (SELECT only).
**Neither appears in `API_WRITE`.** Either that path is unreachable from the deployed surface —
in which case the fact must be recorded, not assumed — or it is a `42501` waiting for the first
judge who drives it. W1's census makes this determinable and W4's probe makes it decidable.
No worker may "fix" it by adding a grant until one of them has established which it is.

### R5 — NO 272nd MIGRATION TODAY. Three independent reasons, each sufficient.

The brief explicitly permits this outcome: *"If you conclude the chain cannot safely take one
right now, say so with evidence and deliver the conformance test alone."* I so conclude.

**(a) R2.** Privileges are cluster state. `0009e` is the standing ruling and this wave produced
no evidence against it.

**(b) The chain is fingerprinted, and I cannot deploy.** `/v1/health` reports
`deploy_chain_files 271`, `deploy_chain_applied 271`,
`schema_fingerprint ec9b1ce70a8df066…`. A 272nd file makes the repository say 272 while the
live cluster says 271, and the only instrument that reconciles them is a deploy — which is
absolutely prohibited to me and which this wave has not asked the orchestrator to perform.
Adding a migration today would turn a caveat-free green health check into a divergence, hours
before a judge sees it, in exchange for a control that R6 delivers without touching the chain.

**(c) The band that would own it is `mode = "rendered"`.** `0009*` carries
`-- @rendered-by trappoint render` with template
`packages/trappoint-sql/templates/0006_roles.sql.j2` and binding
`verticals/mainline/vertical.toml`. Per `migrations.allocation.toml`, a change to a rendered
file is a change to its **template followed by a re-render of BOTH bindings** — which drags
`packages/trappoint-sql/refvertical/sql/` into the blast radius for a role (`mainline_api`)
that does not exist in the reference vertical and should not be invented there. The zero-diff
`trappoint render --check` assertion in CI makes any hand edit a red build, correctly.

### R6 — Where privilege-as-code actually goes, therefore.

Not a migration. **`GRANTS.yaml`**, which is already declarative, already parsed by
`packages/trappoint-migrate/src/trappoint_migrate/grants.py`, already applied idempotently by
`trappoint migrate grants apply`, already censused by `scripts/chain/apply_chain.py:386-441`,
and already understood by the whole repository as the home for exactly this. Three moves:

1. **`mainline_api` and `mainline_judge` become first-class roles in `GRANTS.yaml`** — with
   `login: true`, memberships, schema privileges, table privileges, and denials. **No password
   ever enters that file**; the credential lifecycle stays in `cloud_roles.py`, which is the
   only place in the repository that may hold one.
2. **`cloud_roles.py` stops carrying its own copy of the lists and reads them from the matrix.**
   One authority. The drift measured in R4 becomes *unrepresentable* rather than merely
   detectable — which is strictly better than catching it.
3. **The conformance test** — the deliverable — compares what the code needs against what the
   role can reach, in two independent legs, and fails naming the difference.

### R7 — The conformance test has two legs. Both are required; neither is sufficient alone.

**Leg A — the census (static, hermetic, no cluster).** Enumerate every schema-qualified
relation and routine the demo-api source references. Enumerate what `GRANTS.yaml` declares
`mainline_api` may reach. Fail naming the difference **in both directions**: demanded-but-not-
granted (today's outage) *and* granted-but-never-demanded (tomorrow's over-grant on a
`authorization_type = NONE` endpoint). Runs in any lane, on any machine, in milliseconds, and
would have gone red before the first deploy.

**Leg B — the probe (behavioural, against an ephemeral local database).** Build a database,
apply the chain, apply the matrix, connect **as the role**, and assert `42501` exactly where
the matrix does not name and success exactly where it does. Leg A catches the class before a
deploy. Leg B catches the case where the matrix is right and the cluster disagrees — which
`GRANTS.yaml`'s own header says is the only evidence that counts.

**The vacuity guard is mandatory.** `verticals/mainline/apps/demo-api/tests/test_seed_covers_every_console_resource.py`
is the precedent and its discipline is binding: *"a second copy of a list is a second thing to
drift."* Lists are parsed from their authority, never restated in the test. A scanner that
silently stops matching must produce a **red**, not an empty parametrisation that certifies
nothing — so the census asserts a floor on what it found and asserts its two independent
extraction paths agree.

### R8 — Prohibitions, restated, binding on all five workers.

- **NEVER** `terraform apply`, redeploy, update the Lambda, write SSM, or make any AWS call.
  Build and verify locally. The ORCHESTRATOR deploys.
- **NEVER** print a DSN, a password, or any credential; never write one to a file or an
  evidence artefact.
- **NEVER invent.** No fabricated row, no faked seal, no hard-coded green tick, no reshaping of
  `demo_world.sql` to match a code constant — that was tried once here and was reverted. If a
  test has no subject, the honest fixes are to seed the subject or to address the seeded
  subject.
- **NEVER weaken a claim to make something pass.** No lowering a floor, no raising a ceiling,
  no known-red exemption. `DEFAULT_MAX_RESPONSE_BYTES` stays `136 * 1024`.
- `continue-on-error` and `|| true` are **banned**. Do not weaken `HONESTY.md` or `CI-STATE.md`.
- **Do not commit.** Leave the tree for the orchestrator.
- **Do not add a grant to close a red until you have established the red is real.** An
  unreachable code path and a missing privilege look identical from the test's side and are
  different findings (R4b).

---

## 2. THE FIVE WORKERS

Paths are literally enumerated and disjoint by **write**. Several workers *read* `GRANTS.yaml`;
only **W2** writes it.

| # | worker | writes |
|---|---|---|
| W1 | the census (Leg A) | `packages/mainline-boundary/src/mainline_boundary/sqlrefs.py`, `packages/mainline-boundary/tests/test_sqlrefs.py`, `verticals/mainline/apps/demo-api/tests/test_privilege_census.py` |
| W2 | the matrix | `verticals/mainline/db/GRANTS.yaml` |
| W3 | the deploy script | `scripts/deploy/cloud_roles.py`, `tests/deploy/test_cloud_roles_reads_the_matrix.py` |
| W4 | the probe (Leg B) | `tests/integration/schema/test_privilege_conformance.py`, `scripts/qa/privilege_conformance.py` |
| W5 | wiring + evidence | `justfile`, `.github/workflows/db-schema.yml`, `.github/workflows/cluster-tests.yml`, `docs/verify/deploy/privilege-conformance.md`, `evidence/deploy/LIVE.md` |

**Sequencing.** W1 and W2 start together. W1's census test is expected to be **RED until W2
lands** — that is the intended sequence, not a failure, and W1 must make the red say so by
name. W3 depends on W2's shape. W4 is independent of all of them until its final assertion.
W5 lands last.

---

## 3. WORKER BRIEFS

### W1 — THE CENSUS: what the code demands

Owns exactly `packages/mainline-boundary/src/mainline_boundary/sqlrefs.py`,
`packages/mainline-boundary/tests/test_sqlrefs.py`, and
`verticals/mainline/apps/demo-api/tests/test_privilege_census.py`. Writes nothing else.

Build the scanner that enumerates every schema-qualified relation and routine the demo-api
source references, then the test that diffs it against what `GRANTS.yaml` declares
`mainline_api` may reach — failing in both directions with the difference named.

`mainline_boundary/astscan.py` is the model for tone and for the three-legged design: a direct
scan, a guard that unparseable input is a violation rather than a pass, and a visible escape
hatch. Follow it. The scanner should walk the AST of every `.py` under
`verticals/mainline/apps/demo-api/src/mainline_demo_api/`, collect string constants (including
f-string literal parts and `textwrap.dedent` bodies), and extract schema-qualified names
following `FROM`, `JOIN`, `INTO`, `UPDATE`, `CALL` and `EXECUTE` for the schemas `mainline`,
`mainline_meas`, `mainline_audit`, `mainline_ops` and `trappoint`. It must classify the verb:
`SELECT` demand vs `INSERT`/`UPDATE` demand vs `EXECUTE` demand, because granting `SELECT`
where an `INSERT` is issued is exactly R4b.

`information_schema.*` and `pg_catalog.*` references are **not** privilege demands and must be
excluded by name with a comment saying why. `mainline_audit.*` views are reached by name
through a helper in `reads.py` — resolve them, do not silently drop them.

**The vacuity guard is the point of the file.** Two independent extraction paths (AST literal
walk, and a regex sweep over the raw bytes) must agree on the set; disagreement is red. Assert
a floor: at minimum the 39 relations measurable today. A scanner that finds 3 must fail, never
pass. A `.py` file the scanner cannot parse is a violation, not a skip.

The census test loads `GRANTS.yaml` through
`trappoint_migrate.grants` (do not write a second YAML parser) and computes two differences:
**demanded-but-not-granted** and **granted-but-never-demanded**. Both are red, and the failure
message must print the fully-qualified name, the verb, and the source file and line that
demands it, so an operator can act without reading this plan.

Until W2 lands, `GRANTS.yaml` has no `mainline_api` role. Your test must then fail with a
message naming W2's deliverable explicitly — **never `pytest.skip`**, never a soft pass. A
skip here is the exact failure mode this whole wave exists to end.

Do not add a grant. Do not edit `GRANTS.yaml`, `cloud_roles.py`, or any migration. Do not
touch AWS, do not deploy, do not print a DSN or a password. Do not invent a relation to make
the diff empty; if the diff is non-empty that is the finding. Do not weaken a floor, add
`continue-on-error`, or commit. Report R4b's verdict — whether `exposure_receipt` and
`exposure_line` carry an `INSERT` demand from a reachable path — as a written finding, and do
not resolve it yourself.

**Done when:** `sqlrefs.py` has unit tests that prove it catches a name added to a demo-api SQL
string and refuses to parse-and-pass a malformed file; `test_privilege_census.py` runs in the
hermetic lane, and its failure output names every difference with verb and provenance.

### W2 — THE MATRIX: `mainline_api` becomes a declared role

Owns exactly `verticals/mainline/db/GRANTS.yaml`. Writes nothing else, ever.

Add `mainline_api` and `mainline_judge` to the matrix as first-class roles, so that the role an
anonymous caller on the public Function URL executes as is declared in the same document as
every other role in this system. Read the file's own 60-line header first: it is a contract
with `trappoint migrate grants apply`, its `apply_order` is authoritative, `since:` names the
migration at which each object first exists, `denials:` are **never applied** and exist for the
probe to read, and unknown keys are ignored so documentation fields are welcome.

The source material is `scripts/deploy/cloud_roles.py`: `API_READ` (33 relations),
`API_GATE_READ` (10), `API_WRITE` (11 pairs), `AUDIT_VIEWS` (14 views, granted to both logins),
`API_MEMBERSHIPS` (`auditor_ro`, `agent_gate`, `svc_disposition` — for RLS scope, **not**
privileges) and `FORBIDDEN_SCHEMAS` (`mainline_qa`, re-revoked every run). Carry all of it
across faithfully. **Carry the reasoning across too**: that module's comments explain why
`cr_event` is on the list (a trigger branches on `subject_kind`), why `mainline_ops.outbox` is
written by the invoking role, why the judge needs `USAGE` on schemas it may read nothing in,
and why memberships exist at all under `FORCE ROW LEVEL SECURITY`. Those paragraphs are the
most valuable text in the file. Move them into `why:` / `purpose:` fields; do not delete them.

Then add the eleven relations of R4 that no code in this repository grants:
`mainline.control_failure`, `mainline.defeater_option`, `mainline.delta_witness`,
`mainline.event_edge`, `mainline.ledger_leaf`, `mainline.ledger_node`,
`mainline.receipt_expiry`, `mainline_meas.silence_ledger`, `trappoint.deploy_chain`,
`trappoint.schema_attestation`, `trappoint.schema_migration` — plus `USAGE ON SCHEMA trappoint`,
without which the `EXECUTE` grant already present is unusable. **Every row you add must cite
its evidence in a comment**: the demo-api file and line that references it, or the trigger that
needs it. A row you cannot justify does not go in — an over-grant on an anonymous endpoint is a
defect, not a safety margin.

`login: true` on both. **No password, no secret, no DSN, in this file or any other, ever.** The
credential lifecycle stays in `cloud_roles.py` and is W3's. `since:` must name the real
migration that creates each object — find it, do not guess; a wrong `since:` produces a
misleading warning on a partially-migrated cluster. Verify your file parses:
`.venv/Scripts/python.exe -m trappoint_migrate ... grants` render path, and
`scripts/chain/apply_chain.py --grants` census.

Do not add a migration. Do not edit any file under `verticals/mainline/db/migrations/`, and do
not touch `migrations.lock.json` or `migrations.allocation.toml` — R5 rules there is no 272nd
migration in this wave. Do not touch AWS, deploy, or update the Lambda. Do not invent a
relation, a role, or a privilege. Do not lower a floor or add an exemption. Do not commit.

**Done when:** `GRANTS.yaml` parses, both logins are declared with every privilege they
currently hold plus the eleven missing ones, every added row carries cited evidence, and no
credential appears anywhere in the diff.

### W3 — THE DEPLOY SCRIPT: one authority, not two

Owns exactly `scripts/deploy/cloud_roles.py` and
`tests/deploy/test_cloud_roles_reads_the_matrix.py` (new). Writes nothing else.

Make the drift measured in R4 unrepresentable. Today `cloud_roles.py` carries its own copy of
what `mainline_api` may reach, and that copy is eleven relations behind the cluster it
provisioned — so a rebuild from scratch reproduces all five of yesterday's outages. Refactor so
`API_READ`, `API_GATE_READ`, `API_WRITE`, `AUDIT_VIEWS` and `API_MEMBERSHIPS` are **derived
from `GRANTS.yaml`** (W2's deliverable) rather than restated, using
`trappoint_migrate.grants` to load it. A second copy of a list is a second thing to drift; this
is that lesson applied to the one list that already drifted.

What must **not** change. The password lifecycle: generated here, printed once, never written
to a file or an evidence artefact, never a `--password` option, and set only on `CREATE` or
`--rotate` so a re-run cannot take the live demo down. The insecure-cluster branch that creates
a login without a password on the local `--insecure` node and states that fact in every probe
line. The revocations, re-asserted every run because drift is additive. `gate_probe`, which
tests the whole chain by calling `mainline.merge_permit` and asserting the product's refusal
(`23514` / `gate_closed_when_issued`) rather than a privilege error. `apply_statement`'s rule
that a missing object (`42P01`, `42883`, `3F000`) is a warning naming the object, never an
abort. The per-statement `note` in the log: the operator's terminal must still name the reason
for every grant, so carry W2's `why:` text into the note rather than emitting a bare triple.

Your new test asserts the property, not the implementation: that the set of objects
`cloud_roles.py` would grant to `mainline_api` **equals** the set `GRANTS.yaml` declares, with
no hard-coded expected list in the test. It must run without a cluster.

Do not change what is granted except by picking up what W2's matrix names. Do not add a
privilege of your own. Do not touch AWS, do not run this script against the live cluster, do
not deploy, do not update the Lambda, do not write SSM. **Never print or log a DSN or a
password** — `redact()` exists for the one place that is tempted. Do not invent. Do not lower a
floor or add `|| true`. Do not commit.

**Done when:** `cloud_roles.py` holds no standalone copy of the object lists, every rationale
paragraph survives somewhere a reader will find it, the new test passes clusterlessly, and
`tests/deploy` is still green at its recorded count.

### W4 — THE PROBE: what the role can actually reach

Owns exactly `tests/integration/schema/test_privilege_conformance.py` and
`scripts/qa/privilege_conformance.py` (both new). Writes nothing else.

Build Leg B. `GRANTS.yaml`'s header is unambiguous that this is the real control: *"A GRANT is
a claim about intent. A 42501 is evidence about behaviour."* W1 compares two documents; you
ask the database.

Build an ephemeral database on the local cluster
(`postgresql://root@localhost:26257/defaultdb?sslmode=disable`) following the naming pattern
already in use (`w_*`, `d_w*`), apply the migration chain, apply the matrix, create
`mainline_api` — **without a password, because the local node runs `--insecure` and
CockroachDB refuses one there**; `cloud_roles.py`'s existing branch documents this exactly and
you must handle it the same way rather than discovering it as a failure. Then connect **as the
role** and probe both directions: every (object, verb) the matrix names must succeed, and a
sample of pairs the matrix does **not** name must return `42501`. A login that can read nothing
passes every negative test, so the positive direction is not optional.

`packages/trappoint-conformance/cases/_privilege.py` is the house treatment of `42501` — it is
the DENY class, excluded from the refusal taxonomy by definition because the writer was stopped
by the grant graph before any gate condition was evaluated. Use its `grant_exhibit` token shape
so a refusal here is legible next to every other refusal in the corpus.

`scripts/qa/privilege_conformance.py` is the operator-facing runnable: same probe, prints a
table, exits non-zero on a difference. It must be usable against any DSN passed to it, and it
must **never** print the DSN, the userinfo, or a password.

**Never pass silently.** When no cluster is reachable, `pytest.skip` with the reason stated in
the message — and make the CI lane (W5's) one that guarantees a cluster, so the skip cannot
become the normal outcome. A green that means "I did not run" is the failure mode this wave
exists to end.

Do not touch AWS. Do not run against the live cloud cluster or the demo database. Do not
deploy. Do not edit `GRANTS.yaml`, `cloud_roles.py`, or any migration. Do not invent a row, a
grant or a seal to make a probe green. Do not lower a floor, add an exemption, or use
`continue-on-error` / `|| true`. Do not commit. If the probe finds a difference, that is the
finding — report it, do not close it.

**Done when:** the test builds its own database, asserts both directions, produces a named
difference on failure, and skips only with a stated reason; the script runs standalone and
leaks no credential.

### W5 — WIRING AND EVIDENCE: the lane, and the correction

Owns exactly `justfile`, `.github/workflows/db-schema.yml`,
`.github/workflows/cluster-tests.yml`, `docs/verify/deploy/privilege-conformance.md` (new), and
`evidence/deploy/LIVE.md`. Writes nothing else.

Make the two legs run without anybody remembering to run them, and correct the record.

**The lane.** Add a `just` recipe that runs Leg A (W1, hermetic) and Leg B (W4, needs a
cluster) — mirroring the existing `conform` / `test-cluster` split rather than inventing a
shape. Wire Leg A into `db-schema.yml` and Leg B into `cluster-tests.yml`, which already
provisions a cluster. **The lane is required, not advisory.** `continue-on-error` and `|| true`
are banned; a lane that cannot fail the build is decoration. Do not weaken `HONESTY.md` or
`CI-STATE.md`; if the new lane is red on arrival, record it as red.

**The correction.** `evidence/deploy/LIVE.md:66` asserts *"There is not one GRANT statement in
the 271 migrations."* R1 measures ten. Do **not** delete the sentence — it is what was believed
on 2026-08-14 and an evidence file that quietly rewrites its own history is worth nothing. Add
a dated correction beside it carrying the measured count, the command that measures it, and the
much more important finding of R4: the eleven relations the shipping app references that
`cloud_roles.py` has never heard of, and the consequence that re-running that script on a fresh
cluster would reproduce all five outages. Record R4b as open.

**The document.** `docs/verify/deploy/privilege-conformance.md` explains the control to somebody
who was not here: what the two legs assert, why privilege lives in `GRANTS.yaml` and not in a
migration (cite `0009e` verbatim and R5's three reasons), what the census found, and how to run
both legs. Follow `docs/verify/deploy/public-surface.md` for register. The founder has asked
for an on-ramp: open with what this control refuses and why that matters before any reader
meets `apply_order` or `42501`, then let the precise detail follow intact. **An on-ramp, never
a dumbing-down — if a sentence you write makes a claim vaguer than the claim it replaces, it is
wrong.**

Do not touch AWS, deploy, update the Lambda, or write SSM. Do not print a DSN or a password.
Do not edit `GRANTS.yaml`, `cloud_roles.py`, any migration, or another worker's test. Do not
invent a measurement — every number in your documents must be one you or a named worker
actually took, with the command beside it. Do not lower a floor or add an exemption. Do not
commit.

**Done when:** both legs run from `just` and from CI as required lanes with no
`continue-on-error`; `LIVE.md` carries a dated correction that preserves the original claim;
the verify document opens at a first-time reader's level and ends at a specialist's without
losing a single precise claim.

---

## 4. WHAT SUCCESS LOOKS LIKE

Not eight grants. A comparison that did not exist yesterday and cannot be forgotten tomorrow:
the code's demand and the role's reach, diffed statically before a deploy and behaviourally
after one, both red on difference, both required in CI.

If the wave delivers only W1 and W4 — the two legs — it has closed the class. Everything else
is today's instance.
