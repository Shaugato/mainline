<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MAINLINE

**Read the story below knowing it is invented.** Kestrel Resources is fictional, Marrindal is
fictional, `INC-2013-044` never happened. The mechanism is real; the inputs are authored.[^src-fiction]

In 2011 a gas plant sets the alarm on a compressor seal to 150 °C. On 2013-06-12 that seal catches
fire and two contractors are burned. On 2013-08-04 an engineer lowers the alarm to 135 °C. The
revision history carries one line: *"Lowered 150 → 135 after seal fire INC-2013-044 — two contractors
burned."*[^src-story]

Then ordinary things happen to the clause. In 2016 it is retypeset and renumbered from 7.3 to 5.2.1.
In 2019 it moves into a different standard and becomes 9.2.1. In 2021 the engineer leaves the company.

Today someone proposes putting the alarm back to 150 °C. They are not careless. The manufacturer
specifies 150, and the alarm trips on hot afternoons. The clause on their screen reads *"shall be set
at 135 °C"* and gives no reason. The fire is two documents and three clause numbers away, written by
somebody who no longer works there.

**Every permit-to-work system we surveyed approves that change.** We read six commercial products
against HSG250, the UK Health and Safety Executive's guide.[^src-survey] It lists the thirteen
essential elements of a permit form. Each system checks the world as it is now: isolation in place,
gas test valid, signature present. **None of the thirteen is *why*.** The answer existed and
somebody wrote it down. Nothing carried it to the person who needed it.

## What this is

MAINLINE holds a site's safety memory underneath the systems that site already uses. Every clause of a procedure
carries a pointer to the event that caused it to be written. We call that pointer **blame** — who wrote this line, and why.

A permit to work is then handled like a change to code, and issuing it is a merge. Before that merge lands, the
database looks up what wrote each clause the permit leans on. Any earlier event nobody has answered for becomes an
**obligation** — one open question attached to that permit. While an obligation is open, the permit cannot be issued.
A named competent person has to record a **disposition** first: a signed answer to that one question.

The load-bearing word is *cannot*. This is not a banner somebody dismisses, and not a check in application code that
a second program could skip. It is a rule held inside CockroachDB, applied to every writer including ours. Switch
the user interface off and the permit still will not issue.[^src-gate]

**The reminder is not shown beside the decision. It is a precondition of the decision.**

Two pages belong before the rest of this one. [`docs/HONESTY.md`](docs/HONESTY.md) sets out what is proven, what is
authored and what is not built; [`docs/submission/MUST-NOT-CLAIM.md`](docs/submission/MUST-NOT-CLAIM.md) lists the
flattering sentences this project is not entitled to say, beside the true ones.

## See it refuse — live, with no account

Open the address below in any browser. There is nothing to install and nobody to sign up with.

| Devpost asks for | This entry |
|---|---|
| **Demo URL** | `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` |
| **Judge access — free and unrestricted** | No account, no login, no credential of ours; the origin takes anonymous callers by design.[^src-open] Reading our ledger in your own SQL client is a separate read-only login, in [`docs/deploy/JUDGE-PACK.md`](docs/deploy/JUDGE-PACK.md) §2 |
| **Video, under three minutes** | `https://youtu.be/PmAjaesCMHE` — **2:59**, public, verified playable signed-out |
| **Which CockroachDB tools and AWS services, and how** | [`docs/TOOL-USAGE.md`](docs/TOOL-USAGE.md) — every tool and every service with a file, a line number, and a verdict saying whether it has actually run |
| **Repository and licence** | `https://github.com/Shaugato/mainline`, public since 2026-08-11; the root [`LICENSE`](LICENSE) is Apache-2.0 |

Those rows render from [`docs/submission/SUBMISSION.json`](docs/submission/SUBMISSION.json), the one file where a submission address may be written; this page never edits it. That file writes the literal token `UNRESOLVED` into every such field at birth, so a blank is never mistaken for a forgotten placeholder. All three are resolved.[^src-video]

**What a judge presses.** Each run is a short sequence of steps, and we call each step a **beat**. A **SQLSTATE** is the five-character code the database itself returns for a step; `00000` means the write went through. The refusal comes from a `CHECK` constraint — a rule the database enforces on every write, from every client. An **obligation** is a lesson from a past incident that this job has not answered yet. Beat three is an attack: the cached count of open obligations is forced to zero out of band, then the merge is tried again. `persisted: false` means the whole run rolls back and leaves the world as it found it.

| | **1 · Permit to work** | **2 · Management of change** |
|---|---|---|
| **Who is on the screen** | a site supervisor issuing a permit to work | a safety engineer merging a change to a written procedure |
| **What to press** | `/operator.html#/permit`, or `POST /v1/demo/gate-run` | `/operator.html#/change`, or `POST /v1/demo/cr-gate-run` |
| **What the database answers** | read `00000` · merge refused **`23514`** on `gate_closed_when_issued` · forged count refused **`P0001`** from `mainline.fn_permit_merge_gate` · admit `00000` · `persisted: false` | read `00000` · merge refused **`23514`** on `cr_gate_closed_when_merged` · forged count refused **`P0001`** from `mainline.fn_cr_merge_gate` · `persisted: false` |
| **Artefact** | [`evidence/demo/live-beats.json`](evidence/demo/live-beats.json) — `verdict PROVEN`, `2026-08-15T14:11:35Z`, `base_url` is the address above, `target_is_local_emulator false`, no credential used | [`qa/live2.json`](qa/live2.json) — `verdict PROVEN`, `2026-08-16T21:11:57Z`; where it ran is settled in [`LIVE-STATUS.md`](docs/submission/LIVE-STATUS.md) §2 |

**Two things we will not round up**, both in full in [`docs/submission/LIVE-STATUS.md`](docs/submission/LIVE-STATUS.md). Use case two plays three beats and declines two — `admission_beat: null` and `kernel_procedure_beat: null` — each with the reason its own payload gives, because a beat dressed to look passing would be a fabricated exhibit. And we have driven use case one over the public address but not use case two, so we claim the first beat-for-beat over that address and not the second.

**Three read-only commands hand a judge the same evidence**, with the address and nothing else — no account, no AWS access, no database of ours. Each is documented under [`docs/demo/`](docs/demo/):

| command | what it answers |
|---|---|
| `scripts/demo/demo_ready.py` | *is the world ready to film?* — eight facts, read-only, zero writes |
| `scripts/proof/live_beats.py --base-url <the address above>` | drives use case one off the deployed address and records the SQLSTATE the database produced for each beat |
| `scripts/proof/memory_loop.py --base-url <the address above>` | STORE → RETRIEVE → ACT — an incident names a clause, a retrieval pass finds it, and it becomes an obligation that blocks the permit |

[^src-survey]: `docs/demo/research/r3-operator.md` §1–§2 — HSG250 Figure 1's thirteen elements transcribed verbatim, and six products read from their own documentation: iPermit/IAMTech, Evotix, Intelex, DNV Synergi Life, FacilityBot and pisys. **We could not obtain product screenshots** — every vendor gates them behind a demo request — so this is what their documentation states, not what we saw on a screen. Six products is what we read; it is not a census of the market.
[^src-fiction]: This is `docs/submission/MUST-NOT-CLAIM.md` §3 in that section's own wording.
[^src-story]: Every date, label and setpoint above is transcribed from `verticals/mainline/fixtures/corpus/answer-key/spine.json` — `dates`, `revisions` and `proposed_2026`. The quoted revision-history line is `commit_message_2013` in `verticals/mainline/demo/script/CAMERA-STRINGS.yaml`, whose own header calls the arrow and the em dash load-bearing; `verticals/mainline/demo/script/validate_shotlist.py` asserts it byte-equal across the shot list.
[^src-gate]: `scripts/proof/gate_refusal.py` attempts the merge over SQL with no console and no application in the path, and records the refusal `23514 gate_closed_when_issued` [src: evidence/gate-refusal/proof-20260810T054407Z.json]. What that run does and does not entitle us to say is in the sections below.
[^src-open]: `docs/submission/SUBMISSION.json#judge_access.how` — the Function URL is `authorization_type NONE`; `evidence/demo/live-beats.json#credentials_used` reads `none - no DSN, no AWS profile, no token; a stranger with the URL`.
[^src-video]: `docs/submission/SUBMISSION.json#notes.video_url`. Resolved 2026-08-19; verified signed-out before it was written — `playabilityStatus: OK`, `lengthSeconds` 179, which is 2:59 against the three-minute rule.

## How it works

A **`CHECK` constraint** is a rule the database applies to every write, from every client, with no way to
ask it nicely. Application code can be patched, bypassed or forgotten; a `CHECK` cannot. So the design is
one move: take a fact that lives across many rows, write it as a number on the row being written, and put
a `CHECK` on that number. Every permit system we surveyed is **synchronic** — it gates on the current state
of the world. This one is **diachronic**: it gates on *blame ancestry*, the chain of past events that
wrote the rule. Three steps, each stated plainly and then precisely.

**PROJECT.** When an obligation appears, the database itself writes onto the permit how many are
outstanding. An *obligation* is a lesson a past incident left behind that someone must sign off; a
*projection* is that cross-row fact copied onto a plain column of the subject row. A row-level trigger
derives it from an authoritative table, never from whoever is writing, and overwrites any supplied value
unconditionally, so a correct guess confers no privilege [src: spec/invariants/I02-projected-refusal.md].

**PIN.** Once a permit is merged, nobody can quietly attach a new obligation to it. An *epoch* is a counter that ticks
every time a new obligation lands. The merge record takes a composite foreign key onto `(subject_id, gate_epoch)` that
refuses both updates and deletes, which makes attaching an obligation to a completed transition physically impossible
rather than merely disallowed [src: spec/invariants/I03-epoch-pin.md].

**REFUSE.** The merge is then refused by the constraint, for every writer, forever. A plain-column `CHECK` named
`gate_closed_when_issued` reads `(state != 'merged') OR (open_blocking = 0)`, raises SQLSTATE `23514` — the code the SQL
standard gives a violated `CHECK` — and names itself in the error text [src: evidence/gate-refusal/proof-20260816T151248Z.json#refusal].

**The attack we run against our own gate.** `just prove` does not stop at that refusal. It forces `open_blocking` to zero
out of band — the exact tampering a `CHECK` alone cannot catch, since `(open_blocking = 0)` is now satisfied — and
attempts the merge again. It is refused anyway, `P0001` from `mainline.fn_permit_merge_gate`: *re-derived open obligation
count is 1 while the projected counter reads zero* [src: evidence/gate-refusal/proof-20260816T151248Z.json#drift_refusal].
The function re-derives the count from the base tables rather than trusting the column. **Projections are enforced, never
trusted.** Both refusals are ledgered and read back, each naming the smallest unmet obligation set that explains it.

**What the trigger actually did, in the committed run.** `open_blocking` went 0 → 1 and `gate_epoch` 0 → 1. One row of
kind `check_opened` landed in the **changefeed** — the table other systems subscribe to for a live feed of what changed.
Severity **4** was projected onto a row
where the client supplied **0**, and ten of ten assertions held
[src: evidence/gate-refusal/proof-20260816T151248Z.json#projection]. A counter a client writes is a client's opinion; a
counter a trigger writes is the database's.

**One refusal in this demo is the application's, and we will not round it up.** A signer setting an obligation aside must
give a reason code. The database does not check that the code was ever offered — Python closes that gap, not a
constraint [src: docs/submission/MUST-NOT-CLAIM.md §14].

**Six more things about the gate**, each with what was measured rather than what was intended — including the two results
weaker than we hoped for — are in [`docs/submission/GATE-PROPERTIES.md`](docs/submission/GATE-PROPERTIES.md).

```
verticals/mainline/    the product (LicenseRef-FSL-1.1-ALv2)                                    ── runs on ──▼
packages/trappoint-*   the substrate — a spec, a SQL template, a conformance suite (Apache-2.0) ── enforced by ──▼
CockroachDB v26.2.5    constraints, triggers, changefeeds, and SERIALIZABLE — an isolation level
                       under which concurrent writes behave as if run one after another.
                       The refusal happens here, not above it.
```

## What it is built on

Three words carry the tables below. **EXERCISED** — it ran, and a committed file in this
repository records the result. **DESIGNED** — the code or configuration is finished and on disk,
and nothing we recorded has run it end to end. **NOT-AVAILABLE** — we checked on this platform,
it was absent, and nothing here was built on it.

**Four CockroachDB tools**, in the order the judging criterion names them. A **vector index** is a
second copy of a table's data, arranged so that *find the rows most similar to this one* can be
answered without reading every row.

| # | tool | verdict | what the agent actually did with it |
|---|---|---|---|
| 1 | Distributed vector index — C-SPANN `VECTOR INDEX` | **EXERCISED** | The retrieval step asks for the most similar earlier clauses with every prefix column pinned to one value, then reads the query plan back and asserts the index was chosen — because a query that quietly fell back to a scan returns plausible rows and hides the failure behind them. |
| 2 | MCP Server — CockroachDB Cloud's managed Model Context Protocol endpoint | **EXERCISED** | An MCP client dialled CockroachDB's own managed endpoint and drove a sixteen-question judge pack over read verbs only. The capture program enforces that at the transport rather than promising it. |
| 3 | `ccloud` CLI | **EXERCISED** | Ran `ccloud auth whoami`, then `ccloud cluster list -o json`, and parsed the structured output instead of screen-scraping it. |
| 4 | Agent Skills | **DESIGNED** | **Nothing this repository records has run them.** Two authored skills and one staged upstream contribution are on disk, each shipping a script that fails when its guarantee does not hold. No run of either is captured under `evidence/`, and this row is not promoted to make the table look even. |

**Twelve AWS services: six EXERCISED, five DESIGNED, one NOT-AVAILABLE**
[src: evidence/tool-usage/aws-services.json#totals.by_verdict]. What moved: Bedrock inference,
Bedrock embeddings and CloudWatch metric reads, then Lambda, AWS IAM and Systems Manager Parameter
Store on a `terraform apply` that created real resources [src: evidence/deploy/APPLIED.md]. What
did not: **S3 with Object Lock, KMS, CloudTrail, CloudFront and EventBridge** are DESIGNED — no
evidence bucket, no signing key, no trail, no distribution, no schedule rule. Bedrock Rerank is
NOT-AVAILABLE: AWS does not offer it where our inference runs.

**CloudFront is not DESIGNED by choice; it is blocked.** A real apply returned `AccessDenied: Your
account must be verified before you can add new CloudFront resources.`, kept verbatim with its
`RequestID` in [`docs/deploy/RUNBOOK.md`](docs/deploy/RUNBOOK.md) Appendix A. Only AWS Support can
lift that hold, so the demo's origin is the Lambda Function URL itself. **The IAM row is narrower
than its title**: what ran is the execution role's single allow, and the deny-first evidence-store
policies remain unapplied.

**Bedrock executes in this repository and NOT in the demo request path.** Inference runs in Sydney,
`ap-southeast-2`, while the database is in Singapore, `aws-ap-southeast-1`, because `ap-southeast-2`
is Advanced-tier only on CockroachDB Cloud.

Every row's file and line is in [`docs/TOOL-USAGE.md`](docs/TOOL-USAGE.md), which also files the
database itself as a fourth tool and the vector index as an engine feature.
`python scripts/aws/verify_evidence.py` re-checks the censuses with the standard library alone —
no credential, no network — and fails if any EXERCISED row's cited artefact is missing.

## How we got here, and what we found out about CockroachDB

We did not begin with a database idea. We began by reading how permits are issued. The UK Health and Safety
Executive's guide HSG250 lists thirteen essential elements of a permit form. Six permit products say what
they block on — *"locks permit progress until all mandatory checks are completed"*
[src: docs/demo/research/r3-operator.md §1–§2]. Every one of those checks is about the present, and none of
the thirteen is *why*. The information is not missing — somebody wrote it down — it is unreachable at the
moment of the decision, and a rule keeps its authority only while somebody remembers where it came from.

The obvious answer is to show the reason beside the Approve button. We did not build that. An agent writes over whatever
surface it can reach, and it does not stop being an agent when it uses `psql`, so a panel can be dismissed and a
retrieval can go unread [src: docs/submission/JUDGING-AXES.md §1]. The only version nobody can dismiss is one where the
refusal is a property of the write itself, so this memory lives in constraints and triggers, not in application code
[src: spec/invariants/I02-projected-refusal.md]. That made the database the product — which is why the findings below
cost us real time.

### Seven things we measured on CockroachDB v26.2.5. Six survived a re-check. One did not.

**Full write-up: [`docs/upstream/COCKROACHDB-FINDINGS.md`](docs/upstream/COCKROACHDB-FINDINGS.md).** Before publishing
any of it, one person who had written none of the findings re-ran every one from a cold shell, with the explicit job of
striking things — [`scripts/upstream/verify_field_notes.py`](scripts/upstream/verify_field_notes.py), output at
[`evidence/upstream/verification.json`](evidence/upstream/verification.json). **A re-check that strikes nothing did not
happen.** This one struck one whole finding and narrowed six individual claims inside the survivors.

* **F01** — asked whether a *named* user may run a routine, the database answers `true` even after that user's `EXECUTE` was revoked and the engine itself refuses the call `42501`. **A permission check built on that form can never fail.**
* **F02** — two catalogue surfaces spell one routine two ways and neither carries the other's spelling. No error, just a wrong answer. Mostly our bug — but nothing ships to normalise them.
* **F04** `42501` — `crdb_internal` and `system` are closed by default, and the refusal names an escape hatch it calls *not recommended* without ever naming the supported alternative.
* **F05** `53400` — the ~20,000 schema-object ceiling is excellent when you hit it and invisible on the way up. Our own scratch databases walked into it.
* **F06** `XXUUU` — a zone-configuration readout returns the same number whether you inherited it or set it yourself.
* **F07** `42883` — when one call is nested inside another and the *inner* one fails, the message leads with the *outer* function's name.
* Two about the tooling rather than the engine. The managed MCP endpoint caps responses at 10,240 bytes, and a cut answer is indistinguishable from a complete one — so we shaped our views to 80 % of the cap. And `ccloud` 0.6.12 has no headless login, so an agent cannot drive it from a cold start.

**F03 was struck, and it had been on this page for ten days.** We had written that at ~5,200 rows the optimizer would not
choose the vector index unless the statement named it. **We tried twice to reproduce that, and both times the database
chose the index unasked** — at 0, 200, 1,100 and 5,300 rows. Worse, the artefact this page cited as its proof,
[`evidence/aws/ann/explain-unhinted.txt`](evidence/aws/ann/explain-unhinted.txt), says so in its own body: *GT-06 did not
reproduce*. **A claim whose own cited evidence contradicts it is worse than no claim.** We struck it rather than
softening it into something vague and true, because that is how a document stops being checkable. Six further claims
were narrowed the same way — including *"`gc.ttlseconds` defaults to 4500 on Cloud Basic"*, withdrawn entirely once we
found 4500 was a value **we** had set [src: docs/upstream/STRIKE-LEDGER.md].

**What we would keep unchanged.** `CHECK` constraints and PL/pgSQL triggers under `SERIALIZABLE` carry this product, and
the refusal names the constraint that raised it — precise enough to put on screen: `23514 gate_closed_when_issued`
[src: docs/deploy/cloud-database.md]. **None of this has been reported to Cockroach Labs yet**; the one thing staged
upstream is an unrelated skill contribution [src: docs/upstream/proposal-issue.md].

## Check us — clone it and reproduce the refusal

```bash
git clone -c core.longpaths=true https://github.com/Shaugato/mainline.git
```

**The flag is not decoration.** Windows refuses a file path over 260 characters and the longest path here is 141, leaving
117 for the directory you clone into. Three real clones bracket that: 111 characters cloned cleanly, 122 failed with
`Filename too long`, and with the flag that same 122 cloned clean [src: qa/judge-dry-run.json#path_lengths]. **The flag
fixes `git` and nothing else**, so clone somewhere short, such as `D:\m`. On macOS and Linux it does nothing.

Then four commands, needing Docker, a Python interpreter, and no account of ours. Both columns are first-class, and the plain column is the one that actually ran: `just` and `uv` are not installed on the machine every number here was measured on [src: qa/judge-dry-run.json#host.tools_on_path].

| The recipe | The same thing, plain |
|---|---|
| `just doctor` | `python scripts/qa/doctor.py` |
| `just setup` | `python -m pip install -e packages/trappoint-migrate` |
| `just up` | `docker compose -f compose.yaml up -d --wait`<br>then `docker compose -f compose.yaml run --rm crdb-align` |
| `just prove` | `python scripts/proof/gate_refusal.py --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable"` |

* **`doctor.py` exits 1 on this machine, and it is right to.** The only rows it fails are `uv` and `just`; it prints a numbered remedy under each and does not block the proof.
* **The install step is not optional.** This page once said the proof needed nothing but the interpreter, and a recorded dry run falsified that: without it the script stops at `ModuleNotFoundError: No module named 'psycopg'` [src: qa/judge-dry-run.json#runs].
* **`crdb-align` pins the local node's `gc.ttlseconds` to 4500 seconds** — a deliberately tight retention window, so a time-travel assumption that passes on a laptop's roomy default is exercised against a tight one. This page used to call 4500 *the value Cloud Basic enforces*; that is withdrawn, because 4500 was a value we had set ourselves [src: docs/upstream/STRIKE-LEDGER.md §3 claim 4].

`just prove` builds a throwaway database, applies the migration chain, and attempts the same merge three times: refused,
refused again with the counter forged, then admitted. This is the committed run, in [`evidence/gate-refusal/`](evidence/gate-refusal/):

```
chain         271/271 applied, 0 failed, 63.094s
PROJECTION    10/10 held · open_blocking 0->1 · gate_epoch 0->1 · outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
VERDICT       PROVEN
```

[`VERIFY.md`](VERIFY.md) orders three ways of checking us by how much you have to take on faith, **and records what each
returns today rather than what it should return**. Tier 2 is the four commands above and asks for nothing: no credential,
no model call, 106 s, exit 0, `VERDICT PROVEN`. Tier 1 is an offline bundle check that **exits 1** — `16 checks · 8
passed · 1 failed · 7 not checked`, seven of them cryptographic checks we have not written. Tier 3 points your own agent
at CockroachDB's managed endpoint with none of our code in the path, and was **not run** for this revision.

Two artefacts repay opening on their own. [`evidence/gate-refusal/`](evidence/gate-refusal/) is what one cluster did at
one instant — the SQLSTATE, the constraint name, the counter either side of a single insert, and the caveats the run
could not honestly avoid. Earlier runs are kept beside the current one, because a document whose credibility rests on
showing its own movement may not quietly delete where it moved from. [`qa/test-state.json`](qa/test-state.json) is the
per-package test census with every skip's reason — and it **predates the producer migrations, so it describes a tree
that no longer exists.**

## What we are not claiming

[`docs/HONESTY.md`](docs/HONESTY.md) is what is proven, what is authored and what is not built, every number carrying the
artefact that produced it — and `tests/release/test_honesty_is_checkable.py` fails the build when a number and its source
disagree. [`docs/submission/MUST-NOT-CLAIM.md`](docs/submission/MUST-NOT-CLAIM.md) prints the flattering sentence we may
not say beside the true one. **The two bullets below summarise those two pages and do not replace them.**

* **The reference-ledger keys are named `NOT-SECRET` because they are** — published on purpose, so a stranger can verify the offline bundle without asking anyone for a credential.
* **Every timing in the demo is a local timing** — one single-node CockroachDB in Docker on one laptop. Inference runs on Bedrock in Sydney while the database is in Singapore, so end-to-end Australian residency is false here and the hop is unmeasured under load.

**What is not built yet, and what we are doing next, is in [`ROADMAP.md`](ROADMAP.md).** It carries the conformance
suite, the recorded model transcripts, the counted lint findings, and the automated CI lane that has never pointed at
the managed cluster.

## Repository, licence, status, corrections

| Path | Contents | Licence |
|---|---|---|
| `spec/` · `packages/trappoint-*` · `skills/` · `scripts/` | the substrate anyone may fork: specification, invariants, SQL templates, gate runtime, offline verifier, Model Context Protocol surface, the proof, and two things that are on disk without being demonstrated — Agent Skills (**DESIGNED**) and a conformance suite that runs **10 of its 71 declared cases** [src: qa/conformance-census.json#totals] | Apache-2.0 |
| `verticals/mainline/` · `infra/` | the product: domain lattice, gate service, recall agent, custody relay, console, OpenTofu modules | LicenseRef-FSL-1.1-ALv2 |
| `evidence/` · `qa/` · `docs/` | transcripts, captured tool evidence, a reference ledger a stranger can check offline, the counted ratchets, and every decision record | CC-BY-4.0 |

**That layer boundary is also the licence boundary**, enforced by `import-linter` in CI: contract 1 of `.importlinter`
refuses the build when an Apache-2.0 distribution imports a Functional Source License one, so the substrate stays
forkable. The root [`LICENSE`](LICENSE) is Apache-2.0, so GitHub shows that badge without a judge opening a file — true,
and not the whole tree. [`LICENSES/`](LICENSES) holds every text, [`REUSE.toml`](REUSE.toml) annotates the files that
cannot carry a header, [`docs/submission/LICENSING.md`](docs/submission/LICENSING.md) is the full account, and
[`TRADEMARKS.md`](TRADEMARKS.md) governs the names.

**Status.** Pre-alpha. The Actions tab is red in places, and one of those reds means nothing at all. Read
[`docs/CI-STATE.md`](docs/CI-STATE.md) before drawing a conclusion from a colour: some reds report a true
incompleteness — seven of sixteen custody checks unwritten — and others are jobs that died in the runner's network.

[`ROADMAP.md`](ROADMAP.md) accounts for one more red that neither of those categories covers: this page's own
readability gate.

**Corrections.** One row per claim this page used to make and no longer does — collected, not deleted.

| This page used to say | What is true | Evidence |
|---|---|---|
| the vector index is not chosen unless the statement names it | **struck** — the optimizer chose it unasked at every size we swept. Pinning the *prefix columns* is what matters | `docs/upstream/STRIKE-LEDGER.md` §2 |
| `gc.ttlseconds` defaults to 4500 on CockroachDB Cloud Basic | **withdrawn** — 4500 was a value we set ourselves, read back as if it were the platform's | `docs/upstream/STRIKE-LEDGER.md` §3 |
| the longest tracked path is 214 characters | those replay frames were renamed to content-addressed names. The longest tracked path is 141 and the safe clone prefix 117 — arithmetic over the tracked paths, since the probe has not been re-run | `qa/judge-dry-run.json#superseded_observations` |
| Bedrock genuinely executes, and nothing else on AWS does | a Lambda Function URL now serves the demo and the apply that created it has run: eleven requests answered over the internet, `target_is_local_emulator: false` | `evidence/deploy/aws-live.json` |
| the proof needs nothing but the interpreter | it needs one editable install as well; a recorded dry run falsified the claim twice | `qa/judge-dry-run.json#runs` |
| the operator screens are not deployed | measured again 2026-08-17: `/operator.html` is served and matches this tree byte-for-byte | `docs/submission/LIVE-STATUS.md` §3 |
