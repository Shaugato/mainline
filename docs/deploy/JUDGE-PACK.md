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
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

> **UPDATED 2026-08-14 — THE APPLY HAS RUN AND THIS LINE IS NO LONGER A PLACEHOLDER.**
> The token `<DEMO-URL-PENDING-APPLY>` stood here, above the paragraph beginning *"This is a
> placeholder and it is deliberately not a hostname"*, and the paragraph is kept below
> because the reasoning in it is still the reasoning: **an invented hostname is the one
> failure this project will not commit**, so the token stayed until there was a real one to
> replace it with. There is now.
>
> **UPDATED AGAIN 2026-08-15 — THE DATABASE IS WIRED AND THE FOUR BEATS RUN THROUGH IT.**
> The 2026-08-14 reading below is kept because a page whose credibility rests on showing its
> own movement may not quietly delete where it moved from:
>
> | request | 2026-08-14 | 2026-08-15 |
> |---|---|---|
> | `GET /` | **`200`**, 4,655 B, 1.52 s — the console shell serves | **`200`**, 4,655 B |
> | `GET /v1/health` | **`503`**, `ok=false`, `reason="dsn_unset"` | **`200`**, `ok: true`, `mainline_demo`, deploy chain `271` of `271` files |
> | `POST /v1/demo/gate-run` | **`503`**, `kind="dsn_unset"`, 174 bytes — and **not** a `404`: the route existed and was reachable | **`200`**, 10,499 bytes, `verdict: PROVEN`, four beats, one `SERIALIZABLE` transaction, rolled back |
>
> The 2026-08-14 column is the reading [`RUNBOOK.md`](RUNBOOK.md) §5.10 describes and §5.11
> says how to re-run; it is kept because the *behaviour* it records — an endpoint that names
> the SSM parameter it could not read instead of pretending — is the behaviour we want back
> the next time something is missing.
>
> The right-hand column is `evidence/demo/live-beats.json`, generated `2026-08-15T14:11:35Z`
> by pointing `scripts/proof/live_beats.py` at this hostname with **no credential of any
> kind** — eleven requests, `failures: []`, `target_is_local_emulator: false`. What closed
> the gap was a DSN written into SSM by an operator and five missing `SELECT` grants found
> one HTTP request at a time; the account of it, including the finding that **there is not
> one `GRANT` statement in the 271 migrations**, is `evidence/deploy/LIVE.md`.
>
> **Every row of that table is regenerable by one command that needs no credential of ours:**
> `python scripts/deploy/judge_walk.py --base-url` followed by the hostname above, or
> `.venv/Scripts/python.exe scripts/proof/live_beats.py --base-url` and the same hostname.
> **§1.1** is what the walk does and what its three outcomes mean. Run one of them rather
> than believing this note.
>
> `docs/submission/SUBMISSION.json` still holds `"demo_url": "UNRESOLVED"` — that file is
> not this page's to write, and the two disagree until its owner resolves it. **Where they
> disagree, the wire wins and this note is the record of the disagreement.**

The paragraph this line used to carry, kept because its arithmetic is still the arithmetic:

~~**This is a placeholder and it is deliberately not a hostname.** Terraform has never been applied,
so no origin exists yet.~~ **SUPERSEDED 2026-08-14 — the apply has run and the hostname above is the
one it produced.** `evidence/deploy/terraform-plan-furl.txt` remains a *plan*
(`Plan: 24 to add, 0 to change, 0 to destroy` at line 843) and is still what the count below is read
from; it is a record of what was going to be created, not a claim that nothing was.
The count is **24, not the 11 an earlier revision of this page quoted**:
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
`grep -n '^Plan:' evidence/deploy/terraform-plan-furl.txt`. The apply printed a Lambda Function
URL of the shape `https://<id>.lambda-url.ap-southeast-1.on.aws`, and **that string, not an
invented one, is what replaced the token above**. It has **not** yet gone into
`docs/submission/SUBMISSION.json`, which still holds `"demo_url": "UNRESOLVED"` — that file
belongs to the submission domain and is not this page's to write. Until its owner resolves it,
the two disagree, and this page says so rather than quietly agreeing with either.

There is no CloudFront hostname on this page because there is no CloudFront distribution: the AWS
account carries a verification hold — `AccessDenied: Your account must be verified before you can
add new CloudFront resources.`, verbatim with its `RequestID` in
[`RUNBOOK.md`](RUNBOOK.md) Appendix A — proven by a real apply attempt, so the origin is the
Function URL itself.

**§0.2 stands on its own and needs no deployment of ours at all.** That was written when the line
above was a token, and it is the reason this submission leads with the ledger rather than with a
URL. It is still the strongest thing on this page: **the origin can be down, half-configured, or
serving a recording, and §0.2 is unaffected**, because it puts a judge's own SQL client against the
deployed cluster with none of our code in the path. ~~Today the origin is up and half-configured
(§0.4)~~ **— on 2026-08-14 it was, which is precisely the case §0.2 was written to survive. On
2026-08-15 it is up and wired**, and §0.2 is no less true for it: a page that only worked once
the deployment did would have been the wrong page to write.

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
| ~~**That the demo is deployed.** It is not. Terraform has never been applied and no hostname exists.~~ **SUPERSEDED 2026-08-14: it is deployed.** ~~What we do not claim is narrower and sharper — **that the deployed origin can run the four beats.** It cannot: the Lambda has no DSN, and `POST /v1/demo/gate-run` answers `503 dsn_unset` naming the missing SSM parameter. Nor do we claim the deployed console talks to that kernel: the artefact on the URL is a **REPLAY** build (`buildId:"dev"`) and every byte on its screen is a recording.~~ **SUPERSEDED AGAIN 2026-08-15: the origin runs the four beats** (`verdict: PROVEN`, `target_is_local_emulator: false`), **and the entry chunk it serves compiles `VITE_MAINLINE_API_BASE:"/"` beside `VITE_MAINLINE_BUNDLE_URL:"./bundle/"` — both sources, LIVE by default, REPLAY one control away** (`src/app/source-select.ts`'s three rules). What we do not claim is narrower again: **that the operator screens are on that origin.** They are not yet — `GET /operator.html` returns the console shell byte-for-byte identical to `GET /`, which is the SPA fallback, measured 2026-08-15. §0.4, §1 | `evidence/demo/live-beats.json#verdict`; entry chunk read off the origin, rule in [`console-build.md`](console-build.md) §7.1 |
| **That the acceptance run was taken through the public demo URL.** It was not. Both acceptance artefacts carry `target_is_local_emulator: true`, read from a header the target volunteered. ~~there is no Function URL to point them at yet~~ **CORRECTED 2026-08-14: the URL exists and still cannot host the run** — it has no DSN and answers `503 dsn_unset`, so a re-capture against it would transcribe a 503, not four beats. The **database** underneath the Cloud run is the deployed one. **CORRECTED AGAIN 2026-08-15: a transcript through the public URL now exists** — `evidence/demo/live-beats.json`, `target_is_local_emulator: false`. It was taken by `scripts/proof/live_beats.py` rather than by `demo_acceptance.py`, so the sentence about the two *acceptance* artefacts stands exactly as written and is not retro-fitted. | `evidence/deploy/cloud-acceptance.json` → `target_provenance`, §6; `evidence/demo/live-beats.json` |
| **That beat 4's signature was shown, over the wire, to pin the vocabulary the rows carry.** The gate-run payload does not publish the digest it bound. A credential-free caller can prove the vocabulary *resolved*; the equality is asserted in-process by a test. | `cloud-acceptance.json` → `signature_path.not_established_here`, §6 |
| **That there is end-to-end Australian data residency. Any claim of one is false here.** The database is in Singapore (`aws-ap-southeast-1`); Bedrock inference is in Sydney (`ap-southeast-2`), because `ap-southeast-2` is Advanced-tier only on CockroachDB Cloud. | `docs/HONESTY.md` § *GEOGRAPHY AND LATENCY* |
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
| Demo URL | ~~**NOT YET DEPLOYED.**~~ ~~**DEPLOYED AND SERVING, HALF-CONFIGURED.**~~ **DEPLOYED, WIRED, AND ANSWERING THE FOUR BEATS.** `GET /` → `200`. `GET /v1/health` → `200`, `ok: true`, `mainline_demo`, deploy chain `271` of `271` files. `POST /v1/demo/gate-run` → `200`, `verdict: PROVEN`. Measured 2026-08-15 with no credential [src: `evidence/demo/live-beats.json`]. §0.1, §1 |
| Read-only SQL login | **LIVE, rotated 2026-08-11, verified from the other side** — 14/14 views readable, 11/11 refusals at `42501`. §2 |
| Managed MCP | **available on Basic and working.** The key is deliberately not published and §4 says exactly why |
| Acceptance gate | **GREEN, against the deployed database.** `PROVEN`, twice, all four beats, with the row census unmoved before and after — `evidence/deploy/cloud-acceptance.json`, 2026-08-14. Reproduced locally in `evidence/deploy/acceptance.json`. **Neither of those two runs reached the public URL** — both carry `target_is_local_emulator: true`. ~~and the URL cannot run the beats until the DSN parameter exists~~ **A third transcript, taken 2026-08-15 through the public URL itself, now does**: `evidence/demo/live-beats.json`, `target_is_local_emulator: false`. §6 |
| Operator screens | **BUILT IN THE TREE, NOT YET ON THIS ORIGIN.** `/operator.html#/permit` and `/operator.html#/change`; measured 2026-08-15, `GET /operator.html` on the live URL returns the console shell **byte-for-byte identical** to `GET /` — the SPA fallback, which is what a not-yet-deployed second entry point looks like. §1.2 |

**The one thing this page is for — a judge reading the ledger with none of our code in the path —
works right now, over §0.2 and §2.** ~~The demo URL exists and is a **partial** obligation: the
origin serves, and the kernel behind it cannot reach a database.~~ **DISCHARGED 2026-08-15: the
kernel reaches the database and the four beats run through the URL.** The two outstanding items
this table used to carry were (1) an operator writing `/mainline/demo/cockroach_dsn` — a secret
step, deliberately not scripted and deliberately not in this repository — and (2) the console
artefact rebuilt against its own origin. **Both have happened**, and the account of what it took,
including five privilege gaps found one HTTP request at a time, is `evidence/deploy/LIVE.md`. The
packaging guard that refuses the wrong combination is
[`console-build.md`](console-build.md) §7.3 and is now a required declaration rather than
unreachable code. **What is still outstanding is one thing and it is named above:** the two
operator screens are in the tree and are not on this origin.

### 0.5 · The one placeholder left on this page, and nothing else

Everything on this page is a real, checkable value except exactly one token:

| token | who fills it | why it is not here |
|---|---|---|
| ~~`<DEMO-URL-PENDING-APPLY>`~~ | ~~the operator, after the apply, from the Terraform `function_url` output~~ | **RESOLVED 2026-08-14.** The apply ran and the hostname it produced is in §0.1 and §1. The reasoning stands and is why the token existed: *an invented hostname is the one failure this project will not commit.* |
| `<PASSWORD-FROM-THE-SUBMISSION-FORM>` | the submission form's credentials field | **a live database password committed to a public repository is a published password.** §2.1 |

**There is no second fill-in token.** Three other angle-bracketed strings appear on this page and
none of them is one: `<id>` in `https://<id>.lambda-url.ap-southeast-1.on.aws` is *shape notation*
for a hostname AWS generates, `<date>` in §7 step 3 describes a future edit to this file, and
`<DEMO-URL-PENDING-APPLY>` now survives **only** in the places that record it as resolved — the
struck row above and the §0.1 note — because a token deleted is a token nobody can tell was ever
filled. Anything else in angle brackets is a defect — re-derived with
`grep -o '<[A-Za-z][A-Za-z0-9 ._-]*>' docs/deploy/JUDGE-PACK.md | sort -u`, which returns exactly
these four.

> **CORRECTED 2026-08-15.** This paragraph used to end *"and `grep -n 'DEMO-URL-PENDING-APPLY'
> docs/deploy/JUDGE-PACK.md`, which returns exactly those two lines and no third."* **That
> grep returns FOUR lines, not two**, and always did: the two that record the token as
> resolved, plus the two lines of this very paragraph, which name it in order to describe the
> check. A self-check that does not count itself is a self-check that goes red the first time
> somebody runs it, and it was written by somebody who reasoned about the file instead of
> grepping it — on a page whose entire claim is *"you do not have to take our word for
> anything."* The `grep -o … | sort -u` above **is** exact and returns exactly the four
> tokens named; only the second grep's count was wrong, and it is removed rather than
> re-numbered, because a count that includes the sentence stating the count is a number that
> changes whenever the sentence is reworded.

---

## 1 · The demo URL

```
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

[`RUNBOOK.md`](RUNBOOK.md) is the deploy procedure, §5.10 of it is what that hostname serves
today, and [`terraform-plan.md`](terraform-plan.md) reads the committed plan.

Check it yourself, from outside, with no credentials and no checkout. These are the three
requests this page's claims rest on, and the answers measured on **2026-08-15**. The
2026-08-14 answers are kept beside them in §0.1's table, because a page that deletes its own
earlier reading is a page you cannot check for movement:

```bash
curl -s -o /dev/null -w '%{http_code} %{size_download}\n' \
  https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/
#  200 4655        — the console shell serves

curl -s https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health
#  200, "ok": true, "database": "mainline_demo",
#       "deploy_chain_applied": 271, "deploy_chain_files": 271, "migrations_applied": 0

curl -s -X POST -H 'content-type: application/json' -d '{}' \
  https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/demo/gate-run
#  200, "verdict": "PROVEN"  — four beats, one SERIALIZABLE transaction, rolled back
```

~~Both API answers carry the same `detail` and it names the cause exactly:
`SSM GetParameter '/mainline/demo/cockroach_dsn' in ap-southeast-1 answered HTTP 400:
{"__type":"ParameterNotFound"}`. **An operator has not finished, and the endpoint says so
rather than pretending.**~~ **SUPERSEDED 2026-08-15 — the operator finished.** The sentence is
kept because the behaviour it describes is the behaviour we want back the next time something
is missing: that is the demo's own thesis applied to its own deployment.

`migrations_applied` reads `0` and that is **true, not broken**: two appliers write two ledgers,
and this database was built by `scripts/deploy/cloud_chain.py`, which writes
`trappoint.deploy_chain` rather than `trappoint.schema_migration`. The endpoint reports both and
names which one it is quoting.

**Two things this page used to say it would not overstate, and where each stands now.**

1. ~~**The kernel cannot run the four beats yet.** It has no DSN.~~ **SUPERSEDED 2026-08-15.**
   The parameter was written by an operator, out of band and out of this repository, exactly as
   this page said it would have to be — and then five `SELECT` grants had to be added by hand,
   because **there is not one `GRANT` statement in the 271 migrations**. That finding is open
   and is recorded in `evidence/deploy/LIVE.md` rather than closed quietly.
2. ~~**The console artefact currently on that origin is a REPLAY build.** Measured off the
   JavaScript the URL serves: `VITE_MAINLINE_API_BASE:""`, `VITE_MAINLINE_BUNDLE_URL:"./bundle/"`,
   `buildId:"dev"`, and zero occurrences of `gate-run` in the bundle.~~ **SUPERSEDED 2026-08-15,
   measured the same way, off the same entry chunk the origin serves
   (`/assets/index-LoN3Sn_L.js`, 138,177 wire bytes):** `VITE_MAINLINE_API_BASE:"/"` beside
   `VITE_MAINLINE_BUNDLE_URL:"./bundle/"`, and `gate-run` occurs **12** times where it occurred
   zero. By `src/app/source-select.ts`'s own three rules, a build carrying **both** sources is
   LIVE by default with REPLAY one control away. The compiled literals, why the packer did not
   catch the earlier build, and the guard that now refuses that combination are
   [`console-build.md`](console-build.md) §7. **The guard keyed on the variable NAME and never
   on its VALUE, so it was unreachable code that had never once executed, and the founder found
   the defect by opening the URL — no test in this repository did.**

Verify the whole path with the acceptance program, which is stricter than the three requests above:

```bash
python scripts/deploy/demo_acceptance.py --url https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

That program fetches `/`, asserts the console loads, calls `GET /v1/health`, then calls
`POST /v1/demo/gate-run` **twice** and requires the two runs to agree. It exits non-zero if the
gate did not refuse and then admit. ~~**Pointed at the URL today it exits non-zero, at the health
check, and that is the correct answer** — a program that passed against a kernel with no database
would be worth nothing.~~ **That sentence described 2026-08-14 and this page has not re-run the
program against the URL since the DSN landed, so it prints no exit code for it.** A remembered
exit code is exactly the kind of number this page refuses to carry. What **has** been run against
the URL since is `scripts/proof/live_beats.py` — §1.2.

**Where the beats HAVE been proven, and against what.** `evidence/deploy/cloud-acceptance.json` is
a run of the same program that came back `PROVEN`, twice, all four beats, against the **deployed
CockroachDB Cloud database** — but over a local socket, not this hostname. It carries
`target_is_local_emulator: true`, read from a header the target volunteered, so a transcript taken
against the emulator can never be mistaken for one taken against the deployment. §6 is that run.
`evidence/deploy/acceptance.json` is the local reproduction. **And since 2026-08-15 there is a
third, taken through this hostname**: `evidence/demo/live-beats.json`,
`target_is_local_emulator: false` — §1.2.

### 1.1 · The judge's walk — one command that regenerates every claim in §0.1 and §1

**You should not have to trust the three `curl`s above, and you do not have to run them one at a
time.** `scripts/deploy/judge_walk.py` takes **a URL and nothing else** — no AWS credential, no
`terraform`, no state file, no build — and writes a document of what the deployment answered:

```bash
python scripts/deploy/judge_walk.py \
  --base-url https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
#  -> evidence/deploy/judge-walk.json
```

It does five things, in this order, and the fourth is the one worth knowing about:

1. `GET /` — is it 200, and are the bytes a console shell (a doctype, the `#root` mount, at
   least one `./assets/*.js` and one `./assets/*.css`)?
2. **The transport badge, read out of the shipped JavaScript rather than off a screen.** It
   fetches the entry chunks the shell references, extracts the compiled `VITE_MAINLINE_*`
   literals, and applies `src/app/source-select.ts`'s own rule — empty and whitespace are
   **unset**, exactly as they are in your browser. This is how the REPLAY finding §0.3 and §0.4
   record — and now record as superseded — was established, and you can re-establish it
   yourself against whatever the origin serves today.
3. `GET /v1/health`.
4. **Every request the artefact itself declares.** The console ships an EvidenceBundle whose
   `manifest.json` enumerates every request it makes; the walk reads that manifest *from the
   origin*, at the bundle URL compiled into the served bytes, and drives all **18** frames. It
   does not use a list written by us — a hand-written list drifts from the console in silence.
5. `POST /v1/demo/gate-run` — the headline beat.

**Three outcomes, and the reason vocabulary is closed and written down.** `SATISFIED`,
`REFUSED` *(for a named reason from a fixed table)*, `FAILED`. `REFUSED` with a reason outside
that table is not representable — the program raises rather than inventing one. **`dsn_unset` is
a `REFUSED`**, because a 503 that names the SSM parameter it could not read is a *correct*
deployment telling you an operator has not finished. Measured on 2026-08-14 against this URL:

```
23 steps: 2 satisfied, 20 refused (dsn_unset), 1 FAILED (transport: REPLAY)  -> exit 1
```

**Exit 1, and we are showing you the exit code rather than a summary.** The one failure is the
REPLAY artefact, which is the defect §0.3 and §0.4 already declare — not a surprise, and not
filed in the same drawer as the SSM step, because a missing secret is somebody's remaining work
and a wrong artefact is a wrong artefact. `--allow-replay` will downgrade it to a named refusal
and exit 0, it must be typed on the command line, and any document produced that way is stamped
`allow_replay_declared: true` so it can never be quoted as a reading of a LIVE build. **When the
corrected artefact is deployed, the bare command exits 0.** That transition is the check to
apply to this page, and it needs no word from us.

> **The transition has happened and this page prints no new exit code for it, on purpose.**
> The two conditions that produced the `exit 1` above are both gone as of 2026-08-15 —
> `GET /v1/health` answers `200 ok:true` and the served entry chunk compiles
> `VITE_MAINLINE_API_BASE:"/"` with `gate-run` in it (§1). **`judge_walk.py` has not been
> re-run against the URL since, so `evidence/deploy/judge-walk.json` still carries the
> 2026-08-14 walk and its `exit_code: 1`.** Run the command above and read what it says today;
> a number written here from a prediction about a walk nobody took would be the exact defect
> this page exists to refuse.

The program never applies anything, never redeploys, knows no AWS API, never reads or writes
`/mainline/demo/cockroach_dsn`, and masks every database URL, embedded password and bare
twelve-digit account number before anything reaches the screen or the file. Its own honest
caveat: three of the eighteen frames are `POST` merges, so a walk against a seeded live cluster
**writes** — exactly as clicking the console writes.

### 1.2 · The three commands a judge is handed, and the two screens the film is shot in

Each takes a URL and nothing else. No account, no credential, no AWS access, no database, no
build. `uv` is not on PATH on the machine these were measured on and is not needed.

| command | what it answers | what it writes |
|---|---|---|
| `.venv/Scripts/python.exe scripts/demo/demo_ready.py` | *is the world ready to film?* — eight facts about the deployed demo, **read-only, zero writes** | nothing; `--check` is the default |
| `.venv/Scripts/python.exe scripts/proof/live_beats.py --base-url <the URL>` | the four beats off this hostname, each with the SQLSTATE the database produced, two clocks and a byte count per request | `evidence/demo/live-beats.json` |
| `.venv/Scripts/python.exe scripts/proof/memory_loop.py --base-url <the URL>` | STORE → RETRIEVE → SHOWN TO → ACT as forty rows, each with a table, a column, a route and an RFC 6901 pointer | `evidence/demo/memory-loop.json` |

Their long forms are [`../demo/DEMO-READY.md`](../demo/DEMO-READY.md),
[`../demo/LIVE-BEATS.md`](../demo/LIVE-BEATS.md) and
[`../demo/MEMORY-LOOP.md`](../demo/MEMORY-LOOP.md); the frame-by-frame map from the film to the
artefact — the exact value, the route it came from, the command that regenerates it — is
[`../demo/JUDGE-90-SECONDS.md`](../demo/JUDGE-90-SECONDS.md).

**What `live_beats.py` recorded on 2026-08-15**, quoted rather than paraphrased:
`verdict: PROVEN`, `failures: []`, `transport_failures: []`, `target_is_local_emulator: false`,
**11** requests — 9 `GET`, one `POST /v1/demo/gate-run`, one documented `423` trap — and the four
beats at `00000` / **`23514`** `gate_closed_when_issued` *(reported)* / **`P0001`**
`mainline.fn_permit_merge_gate` *(parsed)* / `00000`.

**What `memory_loop.py` recorded three minutes later**: `verdict: PROVEN`, **40** rows,
**23 of 23** cross-response identities held, `0` failed. Its single most useful number is a
subtraction of two columns off two different routes —
`mainline.blocking_check.materialised_at` minus `mainline_meas.recall_run.started_at` = **10.0
seconds** — and the artefact records that the figure is *computed there and stated nowhere in the
program that produced it*.

**The `423` is a trap and not a refusal, and this is where it is written down.**
`POST /v1/permits/{permit_id}/merge` on the seeded demo subject answers `423`
`demo_subject_write_protected` with `use_instead: POST /v1/demo/gate-run`. It carries **no
SQLSTATE, no constraint and no minimal unsatisfiable subset**, and the transcript records it once
with `is_a_gate_refusal: false`. Rendering it in a refusal banner would put a fabricated exhibit
in front of a judge; the subject is a single shared row that a hundred judges read, and a merge on
it is irreversible.

**The two screens.** The film is shot inside the software the people in the story use, not inside
the MAINLINE console: a **permit-to-work** screen at `/operator.html#/permit` that a site
supervisor fills in, and a **management-of-change** screen at `/operator.html#/change` that a
safety engineer works in. `operator.html` is a second HTML entry point in the same Vite build
(`verticals/mainline/apps/console/operator.html`, routed by `src/operator/route.ts`), it carries
no vendor mark, and every refusal on it arrives over HTTP from this origin carrying the SQLSTATE
the database produced. **They are in the tree and they are not on this origin yet** — §0.4 carries
the measurement that establishes it.

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
  cluster today. ~~**The admission after one signed disposition is not currently reached** — §6.~~
  **SUPERSEDED 2026-08-15: it is reached, through the public URL.** Beat 4 came back
  `ADMITTED`, SQLSTATE `00000`, `open_blocking_after_signature: 0`
  [src: `evidence/demo/live-beats.json#gate_run.beat_four_exhibit`] — and then rolled back with
  the rest of the transaction, which is why the next reader still meets an open obligation.

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

### Today it is GREEN, and here is exactly which run said so

There are **two** acceptance artefacts and neither is a copy of the other. They answer two
different questions and the project needs both.

| artefact | target | what it establishes |
|---|---|---|
| [`evidence/deploy/cloud-acceptance.json`](../../evidence/deploy/cloud-acceptance.json) | the real handler over a local socket, against **CockroachDB Cloud `mainline_demo`** — the database the deployed Lambda is configured to read | what the demo will actually meet. **Cite this one.** |
| [`evidence/deploy/acceptance.json`](../../evidence/deploy/acceptance.json) | the same handler against a **local** CockroachDB seeded from the same two seed files | what a stranger with this repository and a Docker node can reproduce |

Both were taken on **2026-08-14** at tree `d098721` **plus that wave's uncommitted working tree** — <!-- claim-hygiene: quoting: a git object name is provenance for a recorded run, not a commit_id anybody chose -->
`gate_run.py`, `retry.py` and `transitions.py` were modified and not yet committed when the runs
were taken, measured with `git status` at the moment of each, and each artefact's own `note` says
so. `gate_run.py` is the module the four beats live in, so these are measurements of a working tree
and not of a clean checkout of that tree ref; the latter has not been taken and is not claimed here.

Both report `verdict: PROVEN` with an empty `failures` array. Quoted rather than paraphrased, from
the Cloud run:

```
"verdict": "PROVEN"
"failures": []
"target_provenance": { "database_under_test": {
    "reported_by_health":  "mainline_demo",
    "confirmed_by_census": "mainline_demo",
    "host": "mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257",
    "is_cockroachdb_cloud": true,
    "agree": true } }
```

The four beats, measured on Cloud, twice, with identical stable projections:

| # | beat | outcome | SQLSTATE | constraint | how the name was obtained |
|---|---|---|---|---|---|
| 1 | `read` | read | `00000` | — | — |
| 2 | `merge` | **refused** | `23514` | `gate_closed_when_issued` | **reported** by the driver |
| 3 | `projection_drift_attack` | **refused** | `P0001` | `mainline.fn_permit_merge_gate` | **parsed** out of the message |
| 4 | `admit` | **admitted** | `00000` | — | a server-computed `clearance_digest` |

Beat 4 also carries `open_blocking_after_signature: 0` — the obligation counter read *inside* the
transaction once the disposition landed — beside `GET /v1/permits/{id}` still reporting
`open_blocking: 1` after both runs. **That pair is the rollback**, measured from two endpoints in
two transactions rather than taken from the server's own flag.

### `target_is_local_emulator` is `true` in both files, and that is the honest value

The acceptance brief for this capture asked for `false`. It cannot be `false`, and writing it would
be the plainest possible falsification. The flag is **read** from the `X-Mainline-Emulator` header
the target sent, and `scripts/deploy/local_furl.py` stamps that header precisely so a transcript
taken against it can never be mistaken for one taken against a deployment. ~~There is no Function URL
to reach: `aws lambda get-function --function-name mainline-demo-api` answers
`ResourceNotFoundException`.~~ **CORRECTED 2026-08-14: a Function URL now exists** (§1) — ~~but it
still cannot host this run, for a different and equally checkable reason: it has no DSN, and
`POST /v1/demo/gate-run` against it answers `503 dsn_unset`. So the flag stays `true` on both
artefacts, and it stays true **honestly rather than by omission**: re-capturing against the
hostname today would produce a transcript of a 503, not of four beats.~~
**CORRECTED AGAIN 2026-08-15: the hostname can host a four-beat run, and one has been taken.**
The flag stays `true` **on these two artefacts** because they are recordings and a record you
edit afterwards is not a record. The run through the hostname is a **third, separate** artefact
with its own flag: `evidence/demo/live-beats.json`, `target_is_local_emulator: false`, read the
same way — from what the target volunteered, not from what a prover wanted. Neither number was
moved to agree with the other.

What the criterion was reaching for — *did this meet the deployed cluster, or a local imitation of
it?* — is true, and `target_provenance` carries it by separating the three things the one boolean
folds together: **the HTTP hop is emulated; the handler and console are the shipping ones; the
database is CockroachDB Cloud `mainline_demo`**, agreed by two independent readings (`/v1/health`,
with no credential, and the census's own `SELECT current_database()`). When a Function URL exists,
the same program pointed at it records `false` with no code change. **A Function URL now exists,
and `demo_acceptance.py` has not been re-pointed at it in this wave — so no `false` from *that*
program is claimed here.** The `false` this page does claim was recorded by a different program,
`scripts/proof/live_beats.py`, in its own artefact, and it is named as such every time it appears.

### Why it was safe to drive the gate against the live demo database

`POST /v1/demo/gate-run` persists nothing by construction: every beat is savepoint-fenced and the
transaction is rolled back. That is *why* it may be driven — repeatedly, and concurrently — against
a shared live database, and the permission is conditional on proving it each time. So the run
brackets itself with a **row census**: 30 tables counted read-only before the first request and
again after the last. The expected counts are read from
[`evidence/deploy/cloud-seed.json`](../../evidence/deploy/cloud-seed.json) — committed evidence, the
authoritative value — and never typed into the prover. Both readings matched it exactly and matched
each other exactly. `mainline.disposition` and `mainline.merge_record` are still `0`.

The census never touches `crdb_internal` or `system` (both restricted to this role), and it never
trusts the DSN's path segment: the committed DSN ends `/defaultdb` while the demo lives in
`mainline_demo`, so the database is selected **by name** and confirmed by the server.

### The signature path — what a judge signing actually pins

`mainline.disposition.defeater_vocab_sha256` is the digest of the option set the signer was
*shown*. Until 2026-08-14 both signing paths bound `sha256(b"defeater-vocab")` — the SHA-256 of an
ASCII string — so the signature pinned no vocabulary at all. The Cloud run walks that claim
read-only and records:

| obligation | options offered | distinct digests | `vocab_sha256` |
|---|---:|---:|---|
| `dec0de00-0007-…0001` (the permit's) | 3 | 1 | `2ccb08a3d9d1f89e…` |
| `dec0de00-000d-…0001` (the change request's) | 3 | 1 | `d9c837c25bb174d1…` |

**The negative control is the second row existing.** One digest is indistinguishable from a
constant; two obligations carrying two *different* digests cannot be produced by one, and a constant
would go on describing three options after somebody added a fourth. Neither value is
`sha256(b"defeater-vocab")` — recomputed by the prover from the ASCII string rather than quoted, so
you can reproduce the comparison. The local run reads the **same two digests**, because the same two
seed files built both databases.

**No mutating request was issued.** `POST /v1/checks/{check_id}/disposition` is the endpoint a judge
signs with and it commits irreversibly; on the demo subject `transitions._demo_guard` refuses it
`423 demo_subject_write_protected`, and
[`evidence/deploy/demo-guard-armed.json`](../../evidence/deploy/demo-guard-armed.json) is the
artefact that measured that guard firing. A probe whose safety depends on a guard holding is a probe
that writes on the day it does not, and the row it would write closes the demo's one obligation for
every judge after it. The signature is therefore observed where it is reversible — at beat 4.

### One thing about the ledger you should know before you query it

Running §0.2's SQL against `mainline.ledger_checkpoint` returns **three** checkpoints — `tree_size`
1, 2 and 4 — over a `ledger_leaf` holding **4** rows. Two of them are sound. The `tree_size = 1` row
is not: its `root_hash` **is** `digest('mainline-demo/ledger/root/1','sha256')`, a hash of a string
naming itself, and `verticals/mainline/db/seeds/demo/demo_world.sql:391` says so in its own words.
It is a **legacy row**. The current seed writes only the checkpoints at 2 and 4; the 2026-08-14
re-seed added those and did not delete the old one. So `cloud-seed.json`'s `ledger_checkpoint: 3` is
a true count of that database and *not* the output of the seed files — a clean database seeded from
them today carries **2**, which is what `acceptance.json`'s local run measured and recorded. The
difference is written down in both artefacts rather than reconciled by moving either number.

`reads.read_ledger` already refuses to emit an inclusion proof over a window it cannot cover, so the
console will not build a false exhibit out of that row — but the row is in the table and you will
see it.

### What is still not proven

1. ~~**That a public demo URL exists.** It does not; `SUBMISSION.json` holds `UNRESOLVED`.~~
   **SUPERSEDED 2026-08-14: it exists and serves `200` at `/`** (§0.1, §1). ~~What is still not
   proven is the narrower claim this line was standing in for: **that the four beats can be
   driven through it.** They cannot — the Lambda has no DSN, `POST /v1/demo/gate-run` answers
   `503 dsn_unset`, and the artefact on the origin is a REPLAY build with no gate-run control.~~
   **SUPERSEDED AGAIN 2026-08-15: the four beats have been driven through it**, with no
   credential, `verdict: PROVEN` — `evidence/demo/live-beats.json`. What is still not proven is
   narrower again and is stated in that artefact's own words rather than ours: **nothing in it
   is about a browser.** No browser ran; it is an HTTP client. That a *screen* renders these
   bytes is a separate claim needing separate evidence, and the two operator screens the film is
   shot in are not on this origin yet (§0.4, §1.2).
   `docs/submission/SUBMISSION.json` still holds `"demo_url": "UNRESOLVED"`; that file is the
   submission domain's and the disagreement is recorded in §0.1 rather than resolved here.
2. **That beat 4's signature pinned the digest those vocabulary rows carry.** The payload does not
   publish the digest it bound, so a credential-free caller can establish only that the vocabulary
   *resolved* — an absent one raises `DefeaterVocabularyAbsent` and the request is `422`, never a
   `200`. The equality is asserted in-process by
   `verticals/mainline/apps/demo-api/tests/test_judge_can_sign.py`. Publishing `defeater_code` and
   `defeater_vocab_sha256` on beat 4's `observed` block would close it over the wire.
3. **That the demo is fast.** Each Cloud gate run took ~11.3 s from this workstation against ~1.0 s
   locally — the round trip to `ap-southeast-1` multiplied by the beats' statements, not a
   regression, and what a judge in Australia will feel.

**Read each artefact's own `verdict` key when you open it.** If either disagrees with this section,
the artefact wins and this section is stale.

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
moved 11 → 24 on that reading. **The demo URL's own answers in §0.1, §0.4, §1 and §1.2, the served
entry chunk's compiled literals, and the `GET /operator.html` fallback were measured
2026-08-15**, the first two against `evidence/demo/live-beats.json` and the last two off the
origin directly. Every
number on this page names the command or the artefact it came from, because the repository is
public and a remembered count is a claim we cannot defend to a stranger.*
