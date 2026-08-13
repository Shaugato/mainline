<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# For the judges — how to interrogate the ledger yourself

**You do not have to take our word for anything on this page.** Everything below is a credential,
a command, or a statement you can run against the same cluster the demo runs against. Where a
claim cannot be checked from outside, it is marked and the reason is given.

---

## 0 · The first screen

Three things, before anything else: what to click, what to run, and what we are **not** claiming.

### 0.1 · What to click

```
<DEMO-URL-PENDING-APPLY>
```

**This is a placeholder and it is deliberately not a hostname.** Terraform has never been applied
(`evidence/deploy/terraform-plan-furl.txt` is a *plan*, `Plan: 24 to add, 0 to change, 0 to destroy` at line 843),
so no origin exists yet. The count is **24, not the 11 an earlier revision of this page quoted**:
the plan now creates 11 resources in `module.api[0]` and 13 in `module.guard[0]`, because
`infra/envs/demo/main.tf:631` instantiates the cost guard that used to be written and never
wired in. The guard module declares 14 `resource` blocks and the plan creates 13 of them, so
the arithmetic is checked rather than assumed: the fourteenth is
`aws_sns_topic_subscription.email` at `infra/modules/cost-guard/main.tf:337`, which is
`for_each = toset(var.notification_emails)` over a `guard_notification_emails` that defaults to
`[]` (`infra/envs/demo/variables.tf:619`), so it plans **zero** instances. An unconfirmed email
subscription is a control that looks present and is not, which is why the default is empty and
why nothing here is silently missing. 11 + 13 = 24 creates, plus one data-source read
(`module.guard[0].data.aws_iam_policy_document.topic`) for 25 `resource_changes` in
`evidence/deploy/terraform-plan-furl.json`. Re-derive it rather than believing this paragraph:
`grep -n '^Plan:' evidence/deploy/terraform-plan-furl.txt`. When the apply runs it prints a Lambda Function
URL of the shape `https://<id>.lambda-url.ap-southeast-1.on.aws`, and **that string, not an
invented one, is what replaces the token above** and what goes into
`docs/submission/SUBMISSION.json`, which holds `"demo_url": "UNRESOLVED"` until then.

There is no CloudFront hostname on this page because there is no CloudFront distribution: the AWS
account carries a verification hold — `AccessDenied: Your account must be verified before you can
add new CloudFront resources.`, verbatim with its `RequestID` in
[`RUNBOOK.md`](RUNBOOK.md) Appendix A — proven by a real apply attempt, so the origin is the
Function URL itself.

**If the token above is still a token when you read this, the demo is not deployed, and §0.2 is
the whole of what you can do.** That is not a workaround: it is the path this submission leads
with, and it needs no deployment of ours at all.

### 0.2 · What to run — the ledger in your own SQL client, no checkout, no build

```bash
psql "postgresql://mainline_judge:<PASSWORD-FROM-THE-SUBMISSION-FORM>@mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257/mainline_demo?sslmode=verify-full"
```

```sql
\set VERBOSITY verbose

-- what the database is refusing to merge right now
SELECT site_id, state, permits, open_blocking FROM mainline_audit.v_open_gate_summary;

-- now try to read the table that view is built on
SELECT count(*) FROM mainline.permit;
--  ERROR:  user mainline_judge does not have SELECT privilege on relation permit
--  SQLSTATE: 42501
```

That is the shortest path from zero to a refusal you can see. The full five-minute walkthrough —
six statements, four of them refusals, each with the SQLSTATE it returns — is **§2.4**. The login
reaches fourteen `mainline_audit` views and nothing else (§2.2), and every one of those refusals
was re-measured on a local CockroachDB v26.2.5 node on **2026-08-13** against a view-only role
shaped the same way; the messages in §2.4 are the server's, character for character.

If you would rather use an MCP client than `psql`, the paste-ready configuration is
[`MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md) and §4 explains, without
hedging, why the key that reaches **our** cluster is not one we will hand you.

### 0.3 · WHAT WE ARE NOT CLAIMING

The honesty documents are the point of this project, so they go here rather than at line 500.
Each line names the artefact that measures it.

| We do **not** claim | The measurement |
|---|---|
| **That the demo is deployed.** It is not. Terraform has never been applied and no hostname exists. | `evidence/deploy/terraform-plan-furl.txt` is a plan; `SUBMISSION.json.demo_url` is `UNRESOLVED` |
| **That the end-to-end acceptance run passes.** It does not. `verdict: NOT PROVEN`. Beat 4 — the admission — does not admit. | `evidence/deploy/acceptance.json`, §6 |
| **That there is end-to-end Australian data residency.** The database is in Singapore (`aws-ap-southeast-1`); Bedrock inference is in Sydney (`ap-southeast-2`). | `docs/HONESTY.md` § *GEOGRAPHY AND LATENCY* |
| **That any row is real.** Every row is synthetic: fictional operator, fictional sites, fictional people, fictional incidents. | `verticals/mainline/db/seeds/`, §5 |
| **That the WebAuthn assertion is verified.** It is synthesised and labelled `staged: true` on the wire. This deployment has no authenticator and nothing in the schema verifies a signature. | §5, `verticals/mainline/demo/DEMO-HONESTY.md` §3 |
| **That beat 3's constraint name was *reported*.** It was **parsed** out of a message. A PL/pgSQL `RAISE` on CockroachDB carries no constraint name, and `constraint_source: parsed` says so on the wire. | §6 |
| **That an MCP identity cannot read `mainline_qa`.** Over Managed MCP it can. The credential we publish refuses it; the claim as written was wider than the measurement. | `evidence/deploy/judge-run.json` → `divergences`, §4 |
| **That custody is finished.** Of 16 custody checks, 9 run and hold and **7 are unimplemented** — the entire cryptographic half. The CI lane is red for exactly that, by name. | `qa/test-state.json`, `docs/CI-STATE.md` |
| **That the published login can write anything.** It cannot — not even the one `GRANT INSERT` in its own grant file, because that table has no producer migration. See §7; the true position is *narrower* than the documents used to describe. | `verticals/mainline/db/demo/judge_grants.sql:155` |

The long forms are [`docs/HONESTY.md`](../HONESTY.md),
[`docs/CI-STATE.md`](../CI-STATE.md) and
[`verticals/mainline/demo/DEMO-HONESTY.md`](../../verticals/mainline/demo/DEMO-HONESTY.md).

### 0.4 · Status at a glance

| | |
|---|---|
| Demo URL | **NOT YET DEPLOYED.** §0.1 |
| Read-only SQL login | **LIVE, rotated 2026-08-11, verified from the other side** — 14/14 views readable, 11/11 refusals at `42501`. §2 |
| Managed MCP | **available on Basic and working.** The key is deliberately not published and §4 says exactly why |
| Acceptance gate | **RED.** `NOT PROVEN`. Beats 1–3 hold against the live cluster; beat 4 does not. §6 |

**The one thing this page is for — a judge reading the ledger with none of our code in the path —
works right now, over §0.2 and §2.** The demo URL is a separate and currently unmet obligation,
and this page does not pretend otherwise.

### 0.5 · The two placeholders on this page, and nothing else

Everything on this page is a real, checkable value except exactly two tokens:

| token | who fills it | why it is not here |
|---|---|---|
| `<DEMO-URL-PENDING-APPLY>` | the operator, after the apply, from the Terraform `function_url` output | the origin does not exist yet, and an invented hostname is the one failure this project will not commit |
| `<PASSWORD-FROM-THE-SUBMISSION-FORM>` | the submission form's credentials field | **a live database password committed to a public repository is a published password.** §2.1 |

**There is no third fill-in token.** Two other angle-bracketed strings appear on this page and
neither is one: `<id>` in `https://<id>.lambda-url.ap-southeast-1.on.aws` is *shape notation* for a
hostname AWS generates, and `<date>` in §7 step 3 describes a future edit to this file. Anything
else in angle brackets is a defect — re-derived with
`grep -o '<[A-Za-z][A-Za-z0-9 ._-]*>' docs/deploy/JUDGE-PACK.md | sort -u`, which returns exactly
these four.

---

## 1 · The demo URL

```
<DEMO-URL-PENDING-APPLY>            # shape: https://<id>.lambda-url.ap-southeast-1.on.aws
```

When the apply has run, this line carries the real hostname and
`evidence/deploy/acceptance.json` carries a run against it.
[`RUNBOOK.md`](RUNBOOK.md) is the deploy procedure and
[`terraform-plan.md`](terraform-plan.md) reads the committed plan.

Verify it yourself, from outside, with no credentials:

```bash
python scripts/deploy/demo_acceptance.py --url <DEMO-URL-PENDING-APPLY>
```

That program fetches `/`, asserts the console loads, calls `GET /v1/health`, then calls
`POST /v1/demo/gate-run` **twice** and requires the two runs to agree. It exits non-zero if the
gate did not refuse and then admit. **Today it exits non-zero** — §6 says on which beat and why.

---

## 2 · Read-only credentials — the ledger, in your own SQL client

This is the credential we publish, and §4 explains why it is this one rather than an MCP key.

```
host      mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud
port      26257
database  mainline_demo
user      mainline_judge
password  <NOT-IN-THIS-REPOSITORY — it is in the submission form's credentials field>
sslmode   verify-full
```

```bash
psql "postgresql://mainline_judge:<PASSWORD-FROM-THE-SUBMISSION-FORM>@mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257/mainline_demo?sslmode=verify-full"
```

**The password is not in this repository.** It is generated by
`scripts/deploy/judge_access.py attest`, shown once on that program's last line, and delivered with
the submission. A live database password committed to a public repository is a published password,
and this project's own `GRANTS.yaml` discipline says so. If you are judging and do not have it, it
is in the submission form's credentials field.

> **A note for our own auditors, not for judges.** The `psql` lines above and in §0.2 are flagged
> `high_entropy_secret` by `scripts/submission/audit_public_readiness.py`. **The flagged token is
> the hostname**, `mainline-dev-31219.j77.…cockroachlabs.cloud`, Shannon entropy **4.50** against a
> floor of 4.2 — *not* the placeholder, which measures **3.80** and does not trip the floor at all.
> The detector fires because a high-entropy token sits on a line that also contains the word
> `password`. That is the rule working exactly as designed, on a line where its conclusion happens
> to be wrong.
>
> The DSN shape stays, because a judge must be able to copy one line and connect, and a hostname
> published in a DNS zone is not a secret. So this is a **disclosure decision, not a bug**, and it
> is carried in `docs/submission/DISCLOSURE-DECISIONS.yaml` rather than silently allowlisted here.
> The occurrences are, by section rather than by line number — **line numbers move every time this
> page is edited, so re-run the scanner rather than trusting a number printed here**:
>
> | where | what the detector actually matched |
> |---|---|
> | this file, §0.2, §2 and §2.4 — the `psql` DSN, three times | the cluster hostname |
> | the judge MCP configuration, §4 of [`MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md) | the same hostname |
> | `scripts/deploy/judge_access.py`, module docstring and `credentials` output | this document's own repository path |
>
> Re-run on **2026-08-13**: this file and `judge_access.py` are both dispositioned
> `RECORDED-NOT-REPAIRED` in the register (`2026-08-11 w9-public-readiness`), so they are
> accounted for. **`MCP-CONFIG.md`'s occurrence is not** — it is still in the unresolved list, one
> `high_entropy_secret` hit on the `psql` line of its §4, the same hostname and the same false
> positive. `docs/submission/DISCLOSURE-DECISIONS.yaml` belongs to `w9-public-readiness`; this is
> recorded here for that owner rather than allowlisted by a worker who does not own the register.
>
> The table deliberately does **not** re-quote those tokens; writing them out here would make this
> very note generate two further findings, which an earlier draft of it did. Nothing on this page
> is allowlisted, weakened or silenced to make the check green, and the scanner is not the thing to
> change: a detector that stopped flagging high-entropy tokens next to the word *password* would be
> worse at its job in exchange for a tidier report.

### 2.1 · The credential was rotated on 2026-08-11, and why

The previous `mainline_judge` password was **echoed into a working transcript**. It never entered
the repository, so no scan of the tree would ever have found it — which is precisely why it needed
rotating and why the rotation is recorded here, in a file that *can* see it.

**A credential that has appeared in a transcript is a burned credential.** That is this product's
own idiom applied to its own operations: a `GRANT` is a claim about intent and a `42501` is
evidence about behaviour, and in the same way "nobody would have read that scrollback" is a claim
about intent while "the value existed outside the vault" is a fact about the world. The honest
move is to treat disclosure as having happened and rotate, rather than to reason about how likely
it is that anyone looked.

What was done, recorded in
[`evidence/deploy/judge-access.json`](../../evidence/deploy/judge-access.json) —
`generated_at 2026-08-11T00:23:29Z`, `rotation.performed true`, `rotation.mode "rotated"`:

| | |
|---|---|
| Statement | `ALTER USER "mainline_judge" WITH PASSWORD '…'` on the live Cloud cluster |
| New value | 32 URL-safe characters from `secrets.token_urlsafe(24)`, ~143 bits — `rotation.generator` |
| Where it went | printed once, on the program's last line, and typed into the submission form |
| Where it did **not** go | no file in this repository, no evidence artefact, no environment variable, no shell history, no argument on any command line |
| Verified afterwards | yes — the probes in §2.3 authenticated **as `mainline_judge` with the new password**, so the artefact reads `probe.verified: true` rather than `UNVERIFIED` |

Two operational details are on the record because they are the reason this is trustworthy rather
than merely asserted.

* The rotation and the proof happen **in one process** (`judge_access.py attest`). The older
  two-step — `provision --rotate --show-password`, then `judge-run --as-judge --judge-password …`
  — would have put a live credential in the process table and in shell history, which is a second
  disclosure of exactly the kind being repaired.
* The evidence file **asserts about itself** that no field in it is credential-shaped, and the
  write is aborted if that fails. `credential_hygiene` in the artefact records the scan:
  `bytes_scanned 14854`, `matches 0`, `holds true`.

### 2.2 · What this login can reach, in full

Fourteen views in `mainline_audit`, and **nothing else**:

`v_agent_actions` · `v_blame_coverage` · `v_cbm_ledger` · `v_changefeed_health` ·
`v_disposition_coverage` · `v_fixity_coverage` · `v_gate_latency_daily` · `v_ledger_health` ·
`v_open_gate_summary` · `v_recall_conservation` · `v_silence_summary` · `v_txn_restart_daily` ·
`v_unused_indexes` · `v_weakenings_without_disposition`

Fourteen is not a remembered number. It is the count of `GRANT SELECT` statements in
[`verticals/mainline/db/demo/judge_grants.sql`](../../verticals/mainline/db/demo/judge_grants.sql),
lines 136–149 — a closed, reviewable list, re-derived with
`grep -c "^GRANT SELECT ON TABLE mainline_audit" verticals/mainline/db/demo/judge_grants.sql` — and
it is the same fourteen the prover read back (`positives.readable 14 of 14`). There is no
`GRANT ... ON ALL TABLES` anywhere in that file, so a view added by a later migration is **not**
silently reachable by this login.

### 2.3 · What it cannot reach — verified from the other side, not asserted

`judge_access.py attest` connects **as `mainline_judge`, with the rotated password**, and runs both
directions. Measured against the live Cloud database on **2026-08-11**, run mode `rotated`,
`verified: true`, artefact verdict `PROVEN` with `failures: []`:

**Positive — all fourteen views answered.** `positives.readable 14 of 14`; six carry rows and
eight are empty on this seed (§3 says why that is the honest answer, not a broken view).

**Negative — eleven statements, eleven refusals, every SQLSTATE captured verbatim**
(`negatives.refused 11 of 11`). A refusal with no SQLSTATE beside it is not proof of anything, so
the code is the evidence:

| # | Statement issued as `mainline_judge` | SQLSTATE | What the server said |
|---|---|---|---|
| 1 | `SELECT count(*) FROM mainline.permit` | **`42501`** | *does not have SELECT privilege on relation permit* |
| 2 | `SELECT count(*) FROM mainline.disposition` | **`42501`** | *…on relation disposition* |
| 3 | `SELECT count(*) FROM mainline_meas.standing` | **`42501`** | *…on relation standing* |
| 4 | `INSERT INTO mainline.refusal_ledger (spec_version) VALUES (…)` | **`42501`** | *does not have INSERT privilege on relation refusal_ledger* |
| 5 | `CREATE TABLE mainline.w7_judge_probe (…)` | **`42501`** | *does not have CREATE privilege on schema mainline* |
| 6 | `DROP VIEW mainline_audit.v_open_gate_summary` | **`42501`** | *does not have DROP privilege on relation v_open_gate_summary* |
| 7–9 | `SELECT` on `mainline_qa.v_disposition_profile`, `v_my_record`, `v_standing_components` | **`42501`** | *does not have USAGE privilege on schema mainline_qa* |
| 10–11 | `SELECT` on `crdb_internal.jobs`, `crdb_internal.tables` | **`42501`** | *Access to crdb_internal and system is restricted* |

Rows 1–6 are the four claims that "read-only" actually consists of — **cannot read a base table,
cannot write a row, cannot create a relation, cannot drop one** — and the prover treats a missing
category as a failure even when every probe that *did* run was refused, because the absent probe
is exactly the one whose answer nobody knows.

Row 6 is the sharpest of them, and it is deliberately aimed at a view this login **can** read: if
`SELECT` and `DROP` were the same privilege, the whole published credential would be a lie.

> **These messages were re-derived on 2026-08-13, independently of the Cloud run.** On a local
> CockroachDB v26.2.5 node, a throwaway role holding `USAGE` on two schemas and `SELECT` on one
> view — the shape of `mainline_judge` — was asked the same six statements. The positive answered;
> the four privilege statements returned `42501` with the message text quoted above, word for
> word; `crdb_internal.jobs` returned `42501 Access to crdb_internal and system is restricted.`
> `pg_catalog` and `information_schema` answered (372 and 340 rows), which is the same behaviour
> §4 records over pgwire and the reason N03/N04 are transport claims rather than grant claims.
> **What this second measurement buys:** the SQLSTATEs on this page are a property of the engine
> and the grant shape, not of one cluster on one afternoon.

> **How probe 6 is made safe, since a mistake there would break the demo.** On CockroachDB a
> rolled-back transaction does **not** undo a schema change — re-measured on v26.2.5 on
> **2026-08-13**: `CREATE VIEW …; BEGIN; DROP VIEW …; ROLLBACK;` leaves the view **dropped**
> (`42P01 relation does not exist` afterwards), because the DDL auto-commits and closes the
> transaction out from under the `ROLLBACK`, which itself warns `25P01 there is no transaction in
> progress`. So the prover does not rely on a transaction. Before issuing the `DROP`, the admin
> connection captures `SHOW CREATE` for the view and holds it; if the statement had succeeded, the
> view would have been rebuilt in the same run and the breach recorded. **The guard has never
> fired.**

Both directions matter. **A login that can read nothing passes every negative test**, so the
positives are what make the negatives mean anything.

### 2.4 · Five minutes, from zero to a refusal you can see

No repository checkout, no build, no credentials but the one in the submission form.

```bash
# 1 · connect  (~10 s)
psql "postgresql://mainline_judge:<PASSWORD-FROM-THE-SUBMISSION-FORM>@mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257/mainline_demo?sslmode=verify-full"

# 2 · see what the database is refusing to merge right now  (~5 s)
SELECT site_id, state, permits, open_blocking FROM mainline_audit.v_open_gate_summary;
--  one site, one permit in state `dispositioned`, open_blocking = 1

# 3 · turn on the code display so the refusal is unambiguous
\set VERBOSITY verbose

# 4 · try to read the underlying table the view is built on
SELECT count(*) FROM mainline.permit;
--  ERROR:  user mainline_judge does not have SELECT privilege on relation permit
--  SQLSTATE: 42501

# 5 · try to write
INSERT INTO mainline.refusal_ledger (spec_version) VALUES ('judge');
--  ERROR:  user mainline_judge does not have INSERT privilege on relation refusal_ledger
--  SQLSTATE: 42501

# 6 · try to change the schema
DROP VIEW mainline_audit.v_open_gate_summary;
--  ERROR:  user mainline_judge does not have DROP privilege on relation v_open_gate_summary
--  SQLSTATE: 42501
```

Step 6 is safe to run. You will not break the demo for the next judge — that is the point of the
grant, and it is the same statement the prover issues in §2.3 row 6.

The one row step 2 returns is the demo's whole subject: permit
`dec0de00-0006-4000-8000-000000000001`, `state = dispositioned`, `open_blocking = 1`, read back
out of the live `mainline_demo` on **2026-08-12** by a read-only transaction and recorded verbatim
in [`evidence/deploy/permit-id-agreement.json`](../../evidence/deploy/permit-id-agreement.json)
(`permit_row_count: 1`). Exactly one permit exists on that cluster and that is it.

If you want the product's *own* refusal rather than a privilege refusal, that is beat 2 of the
demo (`23514`, `gate_closed_when_issued`) and it needs the API — §6.

Two things you can check that we want you to notice:

* **`mainline_qa` is not merely revoked, it is not nameable.** Without `USAGE` the login cannot
  discover what it is missing. That schema holds per-person deliberation measurement and is
  issued to no automated account on any tier — a claim §4 shows does **not** hold over Managed
  MCP, and which is recorded as a gap rather than narrowed.
* **The audit views come back non-empty.** Four tables carry `FORCE ROW LEVEL SECURITY`, and
  under FORCE a view's owner is not exempt — so these views would return *zero rows* without an
  explicit `view_owner_read` policy. Zero rows is the worst possible failure for an audit
  surface, because it is indistinguishable from "nothing is wrong". `judge_access.py` refuses to
  certify a run in which every view came back empty.

---

## 3 · Three questions worth asking

Run these as `mainline_judge`. They are three of the **sixteen** in
[`verticals/mainline/demo/judge/QUESTIONS.yaml`](../../verticals/mainline/demo/judge/QUESTIONS.yaml),
which is the full pack: **twelve positive** (`Q01`–`Q10C`) and **four negative** (`N01`–`N04`),
counted out of the file itself and recorded independently in
[`evidence/deploy/judge-run.json`](../../evidence/deploy/judge-run.json) as
`questions: 16, positive: 12, negative: 4`.

**What each returned on the live cluster on 2026-08-11**, run as `mainline_judge` over
`sslmode=verify-full` with the rotated credential — so you know what to expect before you type
them. The full sixteen-question run behind these three is the same artefact:
**15 of 16 as expected over Managed MCP, 12 of 16 over pgwire as this login**, with every
divergence given a reading rather than a shrug (§4).

| | Rows | |
|---|---|---|
| Q01 | **1** | the demo's subject, in state `dispositioned`, `open_blocking = 1` |
| Q02 | **0** | the demo seed plants one open obligation, not an unanswered weakening |
| Q05 | **0** | the seed runs no recall pass, so nothing was silenced |

Q02 and Q05 are **empty on this seed, and that is the honest answer, not a broken view**. They
are here because they are the questions worth asking of a real deployment, and because you should
see what an empty audit surface looks like next to a populated one — the demo seed is deliberately
one permit and one obligation, not a simulated year of operations. Six of the fourteen views carry
rows; eight are empty for the same reason. `judge_access.py` refuses to certify a deployment in
which *all fourteen* are empty, because that is what a missing RLS policy looks like.

### Q01 — *What is the database refusing to merge right now?*

```sql
SELECT site_id, state, permits, open_blocking, open_residue, overrides_30d, rows_complete
  FROM mainline_audit.v_open_gate_summary
 LIMIT 25;
```

Every column named above is a real column of that view: the projection is
`verticals/mainline/db/migrations/0156_v_open_gate_summary.sql:85-123`, where `overrides_30d` is a
correlated 30-day subquery and `rows_complete` is the `group_count <= 25` truncation flag.

Observed on the Cloud cluster: one site, one permit in state `dispositioned`, `open_blocking = 1`.
That row is the demo's whole subject — a permit that cannot merge because an obligation raised by
a recalled precursor has never been answered for.

### Q02 — *Which weakenings of controls written over severe ancestry were never answered for?*

```sql
SELECT site_id, activity_root, sev_max, n, n_removed
  FROM mainline_audit.v_weakenings_without_disposition
 LIMIT 25;
```

Projection: `0157_v_weakenings_without_disposition.sql:84`, where `n_removed` counts
`control_delta = 'remove'`. This is the question the product exists to answer, and the one a
document store cannot: it needs the blame ancestry of a clause, not its text.

### Q05 — *What did you decline to surface, and with what arithmetic?*

```sql
SELECT site_id, source, reason, severity, n, mean_score
  FROM mainline_audit.v_silence_summary
 LIMIT 25;
```

Projection: `0160_v_silence_summary.sql:80`, where `mean_score` is
`round(avg(s.score)::NUMERIC, 3)` over a 90-day window.

**Ask this one.** A recall system that reports only what it found is unfalsifiable. This view
reports what was considered and dropped, and why. It is the honesty surface of the retrieval
layer, and `rows_complete` on these views tells you when a view is showing you a truncated answer
rather than a complete one.

---

## 4 · Managed MCP — available, working, and deliberately not published

`docs/leads/deploy-plan.md` §6 listed *"Managed MCP is unavailable on Basic"* as a risk to be
measured. **That hedge is resolved in the affirmative: it is available, and it works.** Re-measured
on **2026-08-11** against the Basic cluster, `evidence/deploy/judge-access.json` → `mcp_channel`:

| | |
|---|---|
| `initialize` at `https://cockroachlabs.cloud/mcp` | HTTP 200, session established, **591.1 ms** |
| `serverInfo` | `cockroachdb-cloud` 1.0.0, protocol `2025-06-18` |
| Tools | **12**, counted from `mcp_channel.tools`, including `select_query` and `explain_query` |
| SQL identity | **`managed-mcp`** — a dedicated user, not `root`, not the database owner |
| Pack result over MCP | **15 of 16 questions as expected**, against the live cluster, 281–968 ms per question (median 691 ms) |

### The paste-ready configuration

Drop this into your MCP client's server configuration. It is the exact wiring that produced
`evidence/deploy/judge-run.json`. **The cluster id is real and is ours**
(`7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`, recorded in both `judge-access.json` →
`mcp_channel.cluster_id` and `judge-run.json` → `channels.mcp.cluster_id`); the key is **yours**.

```json
{
  "mcpServers": {
    "cockroachdb": {
      "type": "http",
      "url": "https://cockroachlabs.cloud/mcp",
      "headers": {
        "Authorization": "Bearer ${COCKROACH_CLOUD_API_KEY}",
        "mcp-cluster-id": "7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e"
      }
    }
  }
}
```

The same thing for a CLI that takes flags instead of a file:

```bash
claude mcp add --transport http cockroachdb https://cockroachlabs.cloud/mcp \
  --header "Authorization: Bearer $COCKROACH_CLOUD_API_KEY" \
  --header "mcp-cluster-id: 7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e"
```

`$COCKROACH_CLOUD_API_KEY` is a key for **your own** CockroachDB Cloud account, which goes in your
client's own secret store and never into a file you commit. Pointed at your own cluster (swap the
`mcp-cluster-id`), this snippet reproduces the mechanism; pointed at ours, it will not
authenticate, which is the intended outcome. We would rather show you the exact wiring and
withhold the key than publish a key and describe it as narrower than it is.

**Every field explained, the two argument-name traps that cost us a debugging session
(`query` not `statement`; `database` is mandatory; `explain_query` prepends its own `EXPLAIN`),
and the `psql` equivalent for a judge with no MCP client at all, are in
[`MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md)** — which carries this same
JSON block, field for field.

That 15-of-16 includes the two plan proofs (Q10, Q10C), which came back as real 18-row query
plans showing a vector index scan — asked over CockroachDB's own managed endpoint with none of
our code in the path.

### So why is the key not on this page?

Because the credential that reaches that endpoint is the account's **Cloud service-account key**,
and the surface it opens is not read-only. Measured, with the same key:

* the tool list carries `create_database`, `create_table` and `insert_rows`;
* `create_database` returned `{"success": true}` — a database really was created on the demo
  cluster and dropped again in the same session;
* `list_clusters` enumerates every cluster the account owns.

[`FALLBACK.md`](../../verticals/mainline/demo/judge/FALLBACK.md) pre-committed to a degrade path if
the key could not be published, on the assumption that the blocker would be Cockroach Labs' terms
or tier availability. The blocker turned out to be neither: **Managed MCP works fine on Basic; the
key is simply far too powerful to hand to a stranger.** That file's own rule — *"No key is ever
published on the demo cluster. Not a weaker one; none."* — is what governs, and it is followed. The
published credential is the read-only SQL login in §2, which is the degrade FALLBACK.md describes
as B1.

### One negative does not hold over MCP, and we are not hiding it

The pack's four negatives assert that an MCP identity cannot reach certain schemas. Measured:

| | over Managed MCP | over pgwire as `mainline_judge` |
|---|---|---|
| N01 `mainline_qa` | **FAILS — readable** | passes (`42501`, no USAGE) |
| N02 `crdb_internal` | passes (server blocklist) | passes (`42501`) |
| N03 `pg_catalog` | passes (server blocklist) | fails — readable by any login, 654 rows |
| N04 `information_schema` | passes (server blocklist) | fails — readable by any login, 446 rows |

N02–N04 pass over MCP because the **server** refuses them by name —
`query references a restricted schema` — which is a stronger guarantee than a grant, since no
privilege change on our side can weaken it. They do not pass over SQL because `pg_catalog` and
`information_schema` are per-user-filtered catalogues that every client needs — independently
reproduced on a local v26.2.5 node on 2026-08-13, where a view-only role read 372 and 340 rows out
of them. `FALLBACK.md` §B2 says exactly this and warns that reporting them as passing would invert
their meaning.

**N01 is a real gap.** `GRANTS.yaml` S14 and the pack's own envelope both state that `mainline_qa`
is reachable by no automated account on any tier. Over Managed MCP it is readable. The credential
we publish refuses it, so nothing a judge can reach is affected — but the claim as written is
wider than the measurement supports, and it is recorded in `evidence/deploy/judge-run.json` under
`divergences` (`disposition: "real_gap"`, `by_design: false`) rather than quietly narrowed.

---

## 5 · What is synthetic, and what is not

**Synthetic — every row.** A fictional operator, fictional sites, fictional people, fictional
incidents, fictional documents. No real person, permit, site or safety record appears anywhere in
this deployment. The seed is committed in `verticals/mainline/db/seeds/` and you can read exactly
what it plants.

**Not synthetic — the mechanism.** These are real and are the point:

* the SQLSTATEs. `23514` and `P0001` come out of CockroachDB through the driver's error object.
  Nothing in the API composes them.
* the constraint names. `gate_closed_when_issued` is a real `CHECK`;
  `mainline.fn_permit_merge_gate` is a real PL/pgSQL function that re-derives the obligation count
  instead of trusting the projected column.
* the schema. **271 migrations** — `ls verticals/mainline/db/migrations/ | wc -l` → `271` — applied
  to a real managed CockroachDB cluster.
* the refusal to merge. That is the database's decision, and it is reproduced on the live Cloud
  cluster today. **The admission after one signed disposition is not currently reached** — §6.

**Labelled `staged: true` in the wire envelope.** The WebAuthn assertion on a signed disposition
is synthesised: this deployment has no authenticator and nothing in the schema verifies a
signature. Every other column on that row is projected from authoritative rows and is real. The
console renders the staged flag rather than hiding it.

**A claim we do not make.** There is no end-to-end Australian data residency here. The database is
in Singapore and Bedrock inference is in Sydney. `docs/HONESTY.md` says so and so does §0.3.

---

## 6 · The acceptance gate, and what it says today

`scripts/deploy/demo_acceptance.py` is the program the deploy exits on. Given only a URL and no
credentials it asserts the four beats verbatim:

| # | Beat | Required | Exhibit |
|---|---|---|---|
| 1 | `read` | `00000` | the permit and its open obligation |
| 2 | `merge` | **REFUSED `23514`** | `gate_closed_when_issued`, *reported* by the driver |
| 3 | `projection_drift_attack` | **REFUSED `P0001`** | `mainline.fn_permit_merge_gate`, *parsed* |
| 4 | `admit` | **ADMITTED `00000`** | a server-computed `clearance_digest` |

plus `persisted: false`, `persistence_check.identical: true`,
`transaction.single_transaction: true`, and **two consecutive runs whose stable projections are
identical** — which is what makes the demo safe for judges pressing the button concurrently.

Beat 3 is the one to read twice. The projected counter is forced to zero out of band — exactly
what a disarmed projector or a careless `UPDATE` leaves behind — so beat 2's `CHECK` is now
satisfied and would admit the merge. It is refused anyway, because the gate re-derives the count.
That beat is the difference between this product and a `CHECK` constraint.

`constraint_source: parsed` on beat 3 is asserted deliberately. On CockroachDB a PL/pgSQL `RAISE`
arrives with no constraint name and no context stack, so the name is recovered from the message.
`parsed` is a **weakened** diagnosis and the payload says so; a run whose exhibits were inferred
must never look like a run whose exhibits were reported.

### Today it is RED, and this is exactly what the artefact says

[`evidence/deploy/acceptance.json`](../../evidence/deploy/acceptance.json), quoted rather than
paraphrased:

```
"generated_at": "2026-08-11T05:43:54Z"
"verdict":      "NOT PROVEN"
```

That run was taken against `scripts/deploy/local_furl.py` — the **unmodified**
`mainline_demo_api.app.handler` and the real console bundle, over an emulated Lambda Function URL
`payload-2.0` event, against the **live** CockroachDB Cloud database `mainline_demo`. Its four
failures, verbatim:

```
POST /v1/demo/gate-run (run 1) returned 500, expected 200 — database_error ·
  resource=demo_gate_run · [22P02] error in argument for $2: could not parse "check_id"
  as type uuid: uuid: incorrect UUID length: check_id
POST /v1/demo/gate-run (run 2) returned 500, expected 200 — …same…
fewer than two gate runs completed, so repeatability — the property that makes this demo
  safe for concurrent judges — was NOT established
the seeded permit could not be read before and after the gate runs, so the claim that
  nothing persists was NOT established from outside.
```

**What has changed in the tree since that run, and what has not.** Three things this page
previously listed as the reasons for the red are gone; the red is not.

| was listed as a reason | today |
|---|---|
| `POST /v1/demo/gate-run` is not routed — the endpoint 404s | **fixed** at commit `b0fe884`. `app.ROUTES` is **17** rows and the seventeenth is `Route(POST /v1/demo/gate-run -> demo_gate_run)`, re-derived today with `python -c "…; print(len(app.ROUTES))"`. `evidence/deploy/gate-run-reachable.json` is the artefact and `tests/test_routes_gate_run.py` pins it |
| `scenario.resolve()` unpacks an 8-tuple against `row_factory=dict_row` | **fixed** in the three modules that own it. [`evidence/deploy/rowfactory-defect.json`](../../evidence/deploy/rowfactory-defect.json) records the diagnosis, the fix shape (a cursor-level row factory, not a connection-level one) and a new contract test that makes the claim twice — once through the real production factory |
| the API and the seed disagree on the demo subject | **fixed.** [`evidence/deploy/permit-id-agreement.json`](../../evidence/deploy/permit-id-agreement.json) read the live database in a read-only transaction on 2026-08-12: exactly **one** permit exists, `dec0de00-0006-4000-8000-000000000001`. The Terraform default now carries that value — `evidence/deploy/terraform-plan-furl.txt:323,332` — and that fix changed no resource. **The plan shape has since moved for a different reason**: the artefact was regenerated on 2026-08-14 with the cost guard instantiated, and now reads `Plan: 24 to add, 0 to change, 0 to destroy` — 11 in `module.api[0]`, 13 in `module.guard[0]` — where the revision of this page that recorded the permit-id fix still said 11 |

**Two blockers remain, and they are why the verdict above has not been superseded.** Neither is a
fault in the gate; both are named with the line that causes them.

1. **`refusal.py:235` repeats the row-factory defect one module further on.**
   `return (row[0] if row and isinstance(row[0], dict) else None), None` — under `dict_row`,
   `row[0]` on the single-column result of `SELECT trappoint.explain_refusal(...)` is
   `KeyError: 0`, because CockroachDB names that column `explain_refusal`. It is reached by
   `gate_run._record_refusal` on **beats 2 and 3 of every gate run**, so there is no path through
   the demo that avoids it. Recorded in `rowfactory-defect.json` → `blocking_finding`, which also
   records that **no worker in any recorded wave owns that path** — the file was not edited by the
   worker that found it, because a fix claimed in an artefact but absent from the tree is the one
   failure mode this discipline exists to prevent.
2. **Beat 4 does not admit.** With the row-factory mismatch neutralised in a diagnostic process —
   `corroborating_run` in the same artefact, **whose own verdict is also `NOT PROVEN`** — the four
   beats came back, twice, identically:

   | beat | outcome | SQLSTATE | constraint | source |
   |---|---|---|---|---|
   | 1 `read` | read | `00000` | — | — |
   | 2 `merge` | **refused** | `23514` | `gate_closed_when_issued` | **reported** |
   | 3 `projection_drift_attack` | **refused** | `P0001` | `mainline.fn_permit_merge_gate` | **parsed** |
   | 4 `admit` | **refused** | `23503` | `disposition_signer_credential_id_fkey` | reported |

   Beat 4 requires `admitted / 00000` and got `refused / 23503`, with **no `clearance_digest`** —
   and the artefact says why in one sentence: `gate_run.py` derives `signer_credential_id` as
   `sha256('cred' + 'signer')` while `verticals/mainline/db/seeds/demo/demo_world.sql` seeds
   `digest('mainline-demo/credential/demo.signer', 'sha256')`. **Two derivations of one
   identifier.** The prover's own note records that nothing was relaxed to reach a green.

**What that means for a judge, stated plainly.** Beats 1, 2 and 3 hold against the live Cloud
cluster: the database refuses the merge with a real `CHECK`, and refuses it *again* when the
projected counter is zeroed out from under it. That is the mechanism this submission is about, and
it is proven. **Beat 4 — the admission after a signed disposition — is not proven, so the demo as a
whole is a gate that currently only ever says no**, which `gate_run.py` itself calls broken. The
gate is correct; the deployment is not ready; and the file that says so is the artefact, not this
sentence. **Read `evidence/deploy/acceptance.json`'s own `verdict` key when you open it** — if it
disagrees with this section, the artefact wins and this section is stale.

---

## 7 · Credential lifetime, and what happens after judging

| | |
|---|---|
| Issued | **2026-08-11**, by `judge_access.py attest` — a rotation, §2.1. `judge-access.json` → `rotation.at: "2026-08-11T00:23:29Z"` |
| Scope | `SELECT` on fourteen `mainline_audit` views — `judge_grants.sql:136-149`. No write privilege on any relation, no DDL, no base table |
| Rotation | any time, without downtime for anything else — nothing but a judge uses this login |
| **Revoked** | **2026-09-30**, or **within 7 days of judging closing**, whichever is sooner |

The submission deadline is `2026-08-18T21:00:00Z` (`docs/submission/SUBMISSION.json` →
`deadline_utc`), so the 2026-09-30 backstop is roughly six weeks after it — a date chosen so the
credential dies on a fixed calendar day even if nobody remembers to count seven from the close of
judging. **It is a commitment made here, not a value measured from anything**, and it is the only
forward-looking number on this page.

### What we will do, and when

1. **The role is dropped.** `DROP USER mainline_judge` on the Cloud cluster, on the earlier of the
   two dates above. From that moment the DSN in §2 authenticates nothing. The grants go with the
   role; there is no orphaned privilege to sweep, because every one of them was granted *to this
   role by name* and `judge_grants.sql` contains no `GRANT … ON ALL TABLES`.
2. **The cluster is torn down.** `mainline-dev` (`7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`, Basic,
   Singapore) is deleted once the role is gone and the submission window has closed. It holds
   nothing but synthetic rows — §5 — so there is no data-retention obligation attached to it, and
   deleting it is what takes the recurring cost to zero.
3. **This page says so, in place.** When step 1 happens, §2 is edited to read *revoked on
   `<date>`* rather than being deleted, so that a reader arriving later finds out that the
   credential is gone instead of finding a connection error and wondering whether they typed it
   wrong. The evidence artefacts stay exactly as they are: they are the record of what was true on
   2026-08-11, and a record you edit afterwards is not a record.

The teardown checklist in [`OBSERVABILITY.md`](OBSERVABILITY.md) **§8** carries steps 1 and 2 as
its first two commands. (Earlier revisions of this page cited §5; §5 is *What a judge sees when the
database is unreachable*. The checklist is §8.)

### The login has no write surface at all — and that is narrower than our own documents said

`judge_grants.sql` contains exactly one `GRANT INSERT`, at line 155, on
`mainline_meas.external_attestation`. **That table has no producer migration anywhere in the
chain**, so the grant is expected to *skip* rather than apply. Re-derived today:

```
$ git grep -l "CREATE TABLE.*external_attestation" -- verticals/mainline/db/migrations/
(no output)
$ git grep -n "external_attestation" -- verticals/mainline/db/migrations/
0089b_standing.sql:131:--    surface is `mainline_meas.external_attestation`.
```

One hit across 271 migrations, and it is a comment. `GRANTS.yaml:401` grants `INSERT` on that
relation "since `0089`", and
[`FALLBACK.md`](../../verticals/mainline/demo/judge/FALLBACK.md) built its entire Managed-MCP
write-surface argument on it. **The relation does not exist.** The `GRANT` statement stays in the
file, visibly, and its skip is reported rather than hidden — a `GRANT` against an absent relation
raises `42P01 cannot determine the target type`, which would abort a whole-file run, so
`judge_grants.sql:84-92` documents the skip as a contract rather than deleting the line.

The resulting position is **stronger than the documents described**: not "insert-only on one
table" but **no write surface at all**. `FALLBACK.md` has been corrected to say so.

---

## 8 · Discrepancies we did not fix, on purpose

Each of these is a defect we found, could have quietly patched, and instead recorded — because the
files that carry them belong to other domains, and an edit outside the lane that another session
overwrites leaves an artefact claiming a fix that is not in the tree.

**1 · `mainline-verify` does not exist.**
[`PACK.md`](../../verticals/mainline/demo/judge/PACK.md) describes a second cluster,
`mainline-verify`, as the throwaway the pack runs against. `list_clusters` over the Cloud API
returns exactly one: `mainline-dev`, `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`, Basic, Singapore.
This deployment uses that one cluster, because a second Basic cluster splits the same free
allowance to buy isolation we do not need — every row is synthetic and the judge login is
read-only. `PACK.md` is generated from `QUESTIONS.yaml`, which belongs to the agents-mcp domain;
this is recorded here and in
[`MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md) §5, where a judge configuring
a client is most likely to trip over it, and the generator is **not** edited. **Read `mainline-dev`
wherever `PACK.md` says `mainline-verify`.**

**2 · `cli.py run --via mcp` cannot reach the live surface.**
`mainline_mcp.client.ToolDialect` sends the statement as `statement=` and omits `database=`; the
live server requires `query=` and makes `database` **mandatory**, answering
`must contain exactly one statement` otherwise. The session, the auth and the cluster pin all work
— the argument names do not. That dataclass's docstring anticipates exactly this case and calls it
a one-line fix. In `evidence/deploy/judge-run.json`.

**3 · `cli.py run --via sql` raises instead of skipping.**
It calls `envelope.enforce` on every question including the negatives; `N01` names `mainline_qa`,
which the envelope refuses outright, and `QaSchemaRefused` propagates out of the runner.
`FALLBACK.md` §B2 specifies that the runner skips these "with the reason printed" — it does not.
Also in `evidence/deploy/judge-run.json`.

**4 · A correction to this page's own previous claim about the question count.** Earlier revisions
of this section and of `MCP-CONFIG.md` §5 stated that *`FALLBACK.md` refers to "eighteen
questions"*. **It does not, and it never did.** Before these corrections were written on
2026-08-13, `git grep -ni eighteen -- verticals/mainline/demo/judge/` returned exactly one line —
the footnote in `MCP-CONFIG.md` asserting the claim, not the claim itself. What was true is that
`FALLBACK.md` stated no total at all, which is a different defect and a smaller one, and one
worth naming: **two documents propagated an attribution neither had checked against the file it
named.** Both footnotes have been removed
rather than carried forward, and `FALLBACK.md` now states the count explicitly. The number, from
the file itself, is **sixteen — twelve positive (`Q01`–`Q10C`), four negative (`N01`–`N04`)** —
corroborated by `evidence/deploy/judge-run.json`'s `questions/positive/negative` keys, which were
written by the pack's own loader rather than by hand.

The sixteen questions themselves are sound: run through their own loader over a corrected
channel, 15 of 16 behaved as the pack says they should, and the one that did not — N01 — is a real
finding about the product rather than about the pack.

---

*Measured against CockroachDB Cloud `mainline-dev` (Basic, `aws-ap-southeast-1`, v26.2.5). The
credential, MCP and question-pack facts in §2, §3 and §4 were measured **2026-08-11**; the permit
facts in §2.4 and §6 **2026-08-12**; the route count, the SQLSTATE
reproduction in §2.3, the grant and migration counts, and the previous rewrite **2026-08-13**; the
Terraform-plan count in §0.1 and §6 was re-read from the artefact regenerated **2026-08-14** and
moved 11 → 24 on that reading. Every
number on this page names the command or the artefact it came from, because the repository is
public and a remembered count is a claim we cannot defend to a stranger.*
