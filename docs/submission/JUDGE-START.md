<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# JUDGE START

## Sixty seconds first — no jargon, and nothing to install

**A crew is about to open a machine and work inside it.** Somebody has to approve that job
before it starts. In most organisations the approval is a signature on a form, and the form
knows nothing about the past. (Throughout this page, **merge** is the moment that approval is
recorded and the work is allowed to begin.)

**In March 2019 a worker was hurt doing this same kind of work.** The machine was declared
locked off without anyone confirming it was actually at zero pressure, and residual hydraulic
pressure released while a guard was being removed. The investigation into it named the written
rule that was meant to prevent exactly that: *"Before any intrusive work, stored energy shall
be isolated, locked and verified at zero by a competent person."*

**Seven years later a new job relies on that same rule, and nobody has answered for the 2019
failure on this particular job.** The approver presses merge. **The database refuses to store
the row.** Not a warning banner, not a policy service that the next code path can go around —
the storage engine itself declines, and hands back the one unanswered item that caused it.

Then somebody tries the obvious way round: reach into the database and set the counter that
the rule checks down to zero. **It refuses a second time**, because it does not believe that
counter — it recounts the underlying rows itself. Only after a competent person signs a proper
answer to the 2019 debt does the same merge go through. A gate that always refuses would be
broken rather than safe, so that third attempt succeeding is part of the claim, not a
footnote.

**That story is invented, and the data says so about itself.** The incident row is titled
`SYNTHETIC — Stored energy release during intrusive work` and its own narrative field reads
*"No real incident, no real site, no real fatality: this narrative was written for the
MAINLINE demonstration and describes nobody"*
(`verticals/mainline/db/seeds/demo/demo_world.sql:275`). **The three refusals are not
invented.** They happen on a public server, to anyone, with no account and no key.

**What to click.** Open the demo URL in the next paragraph. There is no sign-in step, because
there is no sign-in: everything down to Stop 5 needs no account, no key and no email from us.
If you would rather read than run, Stop 3 is those same three refusals as a committed
transcript, and the five items directly below are the parts of this project that are hardest
to find anywhere else.

---

**One path, six stops, no credential until stop 5.** Everything up to and including the
command that reproduces this project's central claim needs nothing from us — no account, no
key, no login, no email. The repository is public: `github.com/Shaugato/mainline`, Apache-2.0,
`master`.

**The demo is live and it takes no credential either:**
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` —
`GET /v1/health` answers `ok: true` on database `mainline_demo` with the deploy chain at
`271` of `271` files, and `POST /v1/demo/gate-run` answers `verdict: PROVEN`, measured
2026-08-15 with no credential [src: `evidence/demo/live-beats.json`]. Stop 6 is what that
does and does not entitle us to say. If you paused the film on a number,
[`docs/demo/JUDGE-90-SECONDS.md`](../demo/JUDGE-90-SECONDS.md) is one row per frame: the exact
value, the route or file it came from, and the one command that regenerates it.

Every figure below resolves to a file in this repository, named beside it. If a figure and
its file disagree, **the file is right and this page is stale.**

---

## ⭐ FIVE THINGS HERE THAT YOU ARE UNLIKELY TO SEE IN ANOTHER ENTRY

**Read this block before the stops if you only have five minutes.** Each item is already
committed. **No new run is asked of you and none was made to write this** — every command
below reads a file that is in your clone, or an artefact already taken against the public
origin. Each item gets three lines: what it means if you have never seen software do it, how
it actually works, and the one command that lets you check us.

---

### 1 · A test lane that plants a fault in itself to prove it is still able to fail

**What this means if you have never seen a project do this.** A green tick normally means *the
check ran and found nothing*. It can also mean *the check is broken and found nothing*. Those
two look identical from outside. So each check is broken on purpose, on every run, and
required to notice.

**How it works.** A **negative control** here means one fixed procedure: copy a lane's real
input into a scratch directory, plant exactly one defect of a kind that lane claims to catch,
run the lane's *own* checker against the mutated copy, and require it both to exit non-zero
**and** to name the planted defect in its output. That last clause is the load-bearing one:
**an assertion that a program failed, without checking why, passes when the program fails to
start.** That is not hypothetical here. The `console` lane's first three attempts all exited
non-zero for reasons that were *not* the plant — a lockfile check inside `pnpm`, a mirror
test, a scratch copy at the wrong directory depth — and a control that had asserted only
`returncode != 0` would have called all three green
([`docs/ci/anti-vacuity.md`](../ci/anti-vacuity.md) §5.2).

**Check us.** [`docs/ci/anti-vacuity.md`](../ci/anti-vacuity.md) is one row per workflow in
the repository, including the rows that admit no such control exists.

```bash
grep -n "standing negative control" docs/ci/anti-vacuity.md
```

Line 55 reads *"Seven lanes have a standing negative control after this wave, against three
before it."* The sentence immediately after it is the reason to read the page: **"Eight of the
eighteen workflows still have none, and the rows above say so rather than omitting them."**

**The same page, §7.3, records the same discipline turned on one of our own numbers.** The
`mutation-ratchet` lane damages the product deliberately and measures what proportion of the
damage the test suite catches, reported as a **Wilson lower bound** — a conservative floor on
a proportion given how many samples were taken, so it is the figure you can defend rather than
the raw ratio. Undamaged: `0.909774`. With one rule switched off: `0.802164`. The finding is
not the gap; it is that the lane's *assertion* about that gap was **satisfiable three ways
without its claim being true**, and a replay over six fixtures shows the old logic passing
three of them. It was tightened, and **it is still never a gate** — it reports, it does not
block.

---

### 2 · A planted fault that caught a defect in CockroachDB's own permission function

**What this means if you have never seen this.** We set a trap for our own code, and caught
the database instead — before the guard had ever run in anger.

**How it works.** The regression guard's privileges family asked CockroachDB
`has_function_privilege('<role>', '<procedure>', 'EXECUTE')` — *may that role run this stored
procedure?* Plant **P2** was built to make that answer `false`: revoke the permission for
real, then require the guard to go red. It would not. The built-in answered `true` for the
revoked role, for `root`, for `admin` and for `public`, while the behavioural truth of the
same call, on the same database, was — verbatim from
[`docs/regression/GUARD.md`](../regression/GUARD.md) line 378:

```
CALL as probe: REFUSED 42501 user w_rg_probe does not have EXECUTE privilege on procedure merge_permit
```

(`42501` is the five-character code the database attaches to *"you do not have permission to
do that"*.) **A check built on it cannot fail, and a check that cannot fail is decoration.**
It was replaced with a `SHOW GRANTS` read plus explicit role-membership expansion, which
*can* go red.

**And we then narrowed our own claim about it, which is the part worth your attention.** We
had written that the built-in answers `true` *"for everybody"*. Re-measured on `2026-08-17`
against CockroachDB CCL `v26.2.5`, that is too broad: only the **role-named** three-argument
form is blind. The two-argument form, where a user asks about *itself*, answers correctly —
`false` for the refused user. The defect is smaller and more specific than we said, and two
controls rule out the dull explanation that the function never resolves its arguments (a
made-up routine raises `42883`, a made-up role raises `42704`). On the same database, in the
same session, `has_table_privilege` gets the identical question right.
[`docs/upstream/STRIKE-LEDGER.md`](../upstream/STRIKE-LEDGER.md) §3 row 1 records the
retraction; [`findings/F01`](../upstream/findings/F01-has-function-privilege.md) carries the
measurement and the transcript. **`docs/regression/GUARD.md` still carries the wider wording
at its lines 381–382; it belongs to another domain and is reported here rather than edited.**
The collected feedback for CockroachDB gathers this with the other findings under
`docs/upstream/`.

**Check us.**

```bash
sed -n '370,394p' docs/regression/GUARD.md
```

---

### 3 · Two documents whose whole job is to say what is *not* built

**What this means if you have never seen this.** Most submissions carry a limitations
paragraph. Here the limitations are longer than the feature list, and one of the two documents
is enforced by a test that fails the build.

**How it works.** [`docs/HONESTY.md`](../HONESTY.md) requires every quantity on it to carry an
inline reference to the file under `qa/` or `evidence/` that produced it.
`tests/release/test_honesty_is_checkable.py` reads the document, follows every reference, and
fails the build when a number and its source disagree, when a cited file is gone, when a number
carries no reference at all — and, the newest rule, when evidence *appears* that the document
has not absorbed. Its own opening: **"This is not a disclaimer. A disclaimer is prose nobody
can falsify."** Its `## NOT YET BUILT` section runs from line 557 to line 1109.

[`docs/CI-STATE.md`](../CI-STATE.md) is the file to read *before* the Actions tab, because the
tab is red on purpose in places and this is what separates the two kinds of red — something is
broken, versus a ratchet holding a line not yet earned. Its measured board, verbatim:

> `20 workflows        8 GREEN        12 RED        0 never-run`

and the caveat printed under it: **"no lane in this repository has ever run at local HEAD …
*A repair without a run id is a plan.*"**

**Neither file was touched by this page or by the wave that wrote this block.** They are
quoted here and never softened.

**Check us.**

```bash
grep -n "^## " docs/HONESTY.md docs/CI-STATE.md
```

---

### 4 · A refusal that hands back the smallest set of blocking reasons — and admits when it cannot compute the way out

**What this means if you have never seen this.** When software says no, it usually just says
no. This one names the single fact that is blocking you and what would unblock it — and when
it cannot work that out, it says *that* instead of guessing.

**Two plain glosses before the acronyms.** A **minimal unsatisfiable set** (**MUS**) is the
smallest group of facts that together make a request impossible: take any one of them away and
it becomes possible again. A **nearest admissible alternative** (**NAA**) is the smallest
change that would let the same request through.

**How it works, measured on the public origin.** `POST /v1/demo/gate-run` runs four beats in
one transaction that rolls itself back, needs no credential, and records `persisted: false`.

* **Beat 2 — the plain `CHECK` refusal**, SQLSTATE `23514`, constraint
  `gate_closed_when_issued`. Its MUS is **one** atom: `kind: obligation`,
  `origin: blame_ancestry`, `severity: 4`, detail *"open at gate_epoch 1; no live
  disposition"*. Its NAA is `kind: dispose_obligations`, `cardinality: 1`, described as
  *"1 obligation(s) remain open on this subject; disposing of exactly those restores
  admissibility"*. `naa_reason` is `null` — an alternative *was* computed, so there is no
  reason to record.
* **Beat 3 — the same merge with the counter forced to zero**, SQLSTATE `P0001`, raised by
  `mainline.fn_permit_merge_gate`. Here `diagnosis` is `"none"`, `naa` is `null`, and
  **`naa_reason` is `"not_computable"`**. The single MUS atom is `kind: capability_gap`,
  naming the function and stating that the general algorithm is QuickXplain over savepoint
  probes, *"in a separate transaction and never on the completion path"*. **On its strongest
  refusal, the system reports that it cannot compute a nearest admissible answer rather than
  inventing one.**

**Check us.** Two committed transcripts, both taken against the public origin with no
credential: `evidence/deploy/cr-gate-live.json` (`POST /v1/demo/gate-run` → `200`,
`2026-08-16`) and `evidence/demo/live-beats.json` (`target_is_local_emulator: false`,
`2026-08-15`).

```bash
python -c "import json;b=json.load(open('evidence/deploy/cr-gate-live.json'))['gate_run']['body']['data']['beats'];print(b[1]['refusal']['naa']['description']);print(b[2]['refusal']['naa'], b[2]['refusal']['naa_reason'])"
```

It prints the NAA description, then `None not_computable`.

**One thing about that file, so it is not misread.** `cr-gate-live.json`'s own top-level
`verdict` is `UNANSWERABLE`, and that answers a *different* question — whether the **change
request** gate can be driven end to end over HTTP. It cannot:
`POST /v1/change-requests/{id}/merge` returns `404`, and the 404 body declares the whole route
table, which is how the absence was confirmed rather than assumed. The `gate_run` block quoted
above is a separate `200` inside the same file.

---

### 5 · A severity the database derived from the past, that no human typed

**What this means if you have never seen this.** The number that closed the gate was not in
the request. The database worked it out from a years-old incident and wrote it onto a row the
caller never touched.

**Two plain glosses.** **Blame ancestry** is the chain from a written rule back through the
incidents that were investigated and named it — who blamed what, kept as rows rather than as
prose. **Projection** here means the database computing a value from those rows and storing it
at the instant the triggering row is inserted, instead of the application computing it and
sending it in.

**How it works.** One `INSERT INTO mainline.blocking_check`, with no other statement between
the before and after readings, fired the `AFTER INSERT` trigger `check_materialised`
(`mainline.fn_check_materialised`, migration `0121_trg_check_materialised.sql`). Across that
single statement: `open_blocking` moved `0 → 1`; the gate epoch moved `0 → 1`; one
`check_opened` row was emitted into `mainline_ops.outbox`; and a severity of **4** was
projected onto the check, banded `blood_major` — **where the client had supplied `0`**. Ten
assertions were declared and ten held. **The client did not write the number that closed the
gate. The database did.**

**Check us.** `evidence/gate-refusal/proof-20260810T054407Z.json#projection`. **That artefact's
`cluster.database` reads `w_W8`, a throwaway local database — this is a LOCAL proof and this
block does not say otherwise**, exactly as Stop 3 does not. The same projection block, `10` of
`10`, appears in the newest committed proof (`proof-20260814T032418Z.json`) and in the printed
transcript quoted at Stop 4.

```bash
python -c "import json;p=json.load(open('evidence/gate-refusal/proof-20260810T054407Z.json'))['projection'];print(p['severity']);print(sum(a['holds'] for a in p['assertions']),'of',len(p['assertions']),'assertions held')"
```

It prints `{'supplied_by_this_script': 0, 'projected_onto_the_check': 4, …}` and then
`10 of 10 assertions held`.

---

**What these five do not say.** Agent Skills is **designed and not exercised**. Bedrock runs
in this repository and **not in the demo's request path** — both halves of that sentence
always. The change request has **no admission beat** and says so. The Managed MCP pack is
`15` of `16` at `DIVERGED — KNOWN GAP`, and the one failure is preserved rather than rounded
off (Stop 5). Nothing in this block promotes any of those.

---

## Stop 0 · How long this stays up — the obligation runs to **2026-09-15**, not to 2026-08-18

**This is the obligation no other file in this repository states.** It is recorded here
because it binds us for four weeks *after* the deadline everyone is working to, and because
the mechanism most likely to breach it is one we built on purpose.

The Official Rules, verbatim:

> "The Entrant must make the Project available free of charge and without any restriction,
> for testing, evaluation and use by the Sponsor, Administrator and Judges **until the
> Judging Period ends**."

**Two dates, and the gap between them is the whole point:**

| | date |
|---|---|
| Submission Period closes | **2026-08-18**, 17:00 EDT |
| **Judging Period runs** | **2026-08-19 → 2026-09-15** |
| **The origin must stay reachable until** | **2026-09-15** |

**So the demo must answer for twenty-eight days after the submission deadline.** Not until we
have submitted. Not until the video is uploaded. Until the Judging Period ends. A judge may
open [`the demo URL`](https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws)
for the first time in the second week of September, and it has to work then.

**Nothing you need is behind a credential.** The Function URL is
`authorization_type = NONE` — measured, and readable back off
`aws_lambda_function_url.authorization_type` rather than off our intent
(`infra/envs/demo/outputs.tf:148`). Every route in Stops 1–4 and 6 needs **no account, no
key, no login and no email from us**. Stop 5's `mainline_judge` psql login is the **one**
*deeper, optional* path for reading our own Cloud ledger; it is not required to evaluate the
project, and the rules' "if Entrant's website is private, include login credentials" clause
does not bite, because the website is not private.

### ⚠ The tension we are recording rather than resolving: the cost guard can take the demo down, and that would be a RULES BREACH

The same apply that created the origin created a cost guard, and **it is live** — of the
`24 created` resources in `evidence/deploy/APPLIED.md`, eleven are the API and **thirteen are
the guard**. What it does, from `infra/envs/demo/README.md` §"This root can stop its own demo,
and that is the point":

* Seven CloudWatch alarms — the guard's three (invocations/60 s, invocations/3600 s, log
  ingestion/300 s) plus `module.api`'s four (`-errors`, `-throttles`, `-duration-p99`,
  `-concurrency`) — and one AWS Budget publish to one SNS topic.
* Its subscriber calls `lambda:PutFunctionConcurrency(ReservedConcurrentExecutions=0)`.
* **The URL then answers `HTTP 429` with no body, to everyone.**
* **It is not self-clearing.** The responder holds an explicit `Deny` on
  `DeleteFunctionConcurrency`, so it cannot undo its own stop. Recovery is a human running
  `scripts/deploy/kill_switch.{sh,ps1} --restore` (`--status` reads state without changing
  it).

That trade — *"an outage is recoverable by one command and a bill is not"* — was chosen
deliberately, and it is the right trade for an unauthenticated endpoint. **The rules do not
care why the demo is down.** Between 2026-08-19 and 2026-09-15, a Function URL answering
`429` is a Project not "available … without any restriction … for testing, evaluation and use
by the Sponsor, Administrator and Judges". **A cost-guard stop in September is a rules breach,
not a saving.**

And the exposure is not hypothetical, because the guard's own README names it: the Function
URL has no authentication because I chose that deliberately, so **anyone at all can trip the
burst alarm and take the demo down** — including a judge running the beats a few times, or
several judges arriving at once.

**What watches it, and the one thing that has to be true for that to work.**
`.github/workflows/demo-health.yml` runs **hourly** and asserts `GET /` → 200,
`GET /v1/health` → `ok: true` with a `server_date` fresh inside a 15-minute window, and
`POST /v1/demo/gate-run` → the four beats by SQLSTATE. **It reads the URL out of
`docs/submission/SUBMISSION.json` in the checkout, and GitHub fires `schedule:` from the
default branch only.** So the heartbeat arms when — and only when — a resolved `demo_url`
is on `master`. That field now holds the origin rather than `UNRESOLVED`; until it is
committed and pushed, the lane is still failing for the "not deployed" reason and **nothing
is watching the origin**. Check in one command:

```bash
gh api repos/Shaugato/mainline/contents/docs/submission/SUBMISSION.json \
  --jq '.content' | base64 -d | jq -r .demo_url
```

**This page records the obligation; it does not act on it.** The actions are mine, and none of
them is a documentation edit:

1. **Get `demo_url` onto `master`** so the hourly heartbeat starts asserting against the
   origin instead of failing for the wrong reason.
2. **Decide the September posture before 2026-08-19** — who is notified when the guard
   trips, and who runs `--restore`. An hourly red on a repository nobody is reading during
   the judging window is not a monitor.
3. **Do not let a cost ceiling silently outrank the availability rule.** If the budget's
   backstop would fire inside the window, that is a decision to take deliberately and in
   advance, not to discover from a judge's screenshot. `docs/deploy/COST-BOUND.md` is where
   the bound is costed.

*(Recorded under [`compliance-plan.md`](compliance-plan.md) Ruling 5. No infrastructure,
budget or alarm was touched to write this — every figure above was read from committed
Terraform, committed evidence and a public workflow file.)*

---

## Stop 1 · The two documents that decide whether to believe the rest

Read these before the code. They are the differentiator, and putting them anywhere but the
top of the page would waste them.

**→ [`docs/HONESTY.md`](../HONESTY.md) — what is broken, published rather than hidden.**

It records what is broken, what is synthetic and what was never built, and every quantity on
it carries an inline reference to the file under `qa/` or `evidence/` that produced it.
`tests/release/test_honesty_is_checkable.py` reads the document, follows every reference and
**fails the build when a number and its source disagree** — and fails it again when evidence
*appears* that the document has not absorbed. A page of caveats nobody can falsify is a
disclaimer; this one is a test.

**→ [`docs/CI-STATE.md`](../CI-STATE.md) — every lane's real conclusion, with run ids.**

Read this **before** you open the Actions tab, because the tab is red and that is on
purpose. Some lanes are red because something is broken. Others are red because a ratchet is
holding a line we have not yet earned — the custody chain has 7 of 16 checks unimplemented,
the conformance suite has never been demonstrated end to end, and ~~a demo-health lane cannot
be green while no demo is deployed~~ *(there is a demo to health-check now; whether the lane
has been pointed at it is `CI-STATE.md`'s to say, not this page's)*.
`CI-STATE.md` says which is which, names the run id, and
records the rule that a red reporting true incompleteness **stays red with a sharper
message**. `continue-on-error` and `|| true` are banned in this repository.

---

## Stop 2 · The Actions tab, with that in hand

`github.com/Shaugato/mainline/actions` — public, no login.

**The lane-by-lane verdict lives in [`docs/CI-STATE.md`](../CI-STATE.md), and only there.**
This page deliberately does not carry a second copy of the green/red list: a lane list
transcribed into a document goes stale the next time a lane runs, and two lists that disagree
are worse than one. `CI-STATE.md` names each lane, its conclusion and its run id, and it
distinguishes the two kinds of red — **something is broken** from **a ratchet is holding a
line we have not yet earned**. The custody chain has 7 of 16 checks unimplemented; the
conformance suite has never been demonstrated end to end; ~~a demo-health lane cannot be green
while no demo is deployed~~ — **that last one changed on 2026-08-15 and the change is recorded
here rather than in a badge**: the demo is deployed and answers `ok: true`
[src: `evidence/demo/live-beats.json#world.health`], and whether the lane has been re-pointed
at it is `CI-STATE.md`'s to report. Those reds are the product.

A submission that showed you an all-green tab four days before a deadline would be telling you
something about its badges rather than about its software.
`continue-on-error` and `|| true` are banned in this repository.

---

## Stop 3 · Ninety seconds — the claim as a transcript

**[`evidence/gate-refusal/`](../../evidence/gate-refusal/)** — the product's central claim,
as a recording rather than a sentence.

Open the newest `proof-<UTC>.json`. It is what one CockroachDB cluster did at one instant,
written by `scripts/proof/gate_refusal.py`. The newest, taken on 2026-08-14 and read back
on 2026-08-14 [src: `evidence/gate-refusal/proof-20260814T032418Z.json`]:

| Field | Value |
|---|---|
| `generated_at_utc` | `2026-08-14T03:24:18Z` |
| `cluster` | CockroachDB CCL `v26.2.5`, database `w_qr_gate_refusal_proof`, `gc.ttlseconds` 4500 |
| `chain` | `271` of `271` applied, `0` failed, `71.797` s |
| `projection` | `10` of `10` assertions held |
| `refusal` | `REFUSED`, SQLSTATE `23514`, constraint `gate_closed_when_issued` (`reported`) |
| `drift_refusal` | `REFUSED`, SQLSTATE `P0001`, `mainline.fn_permit_merge_gate` (`parsed`) |
| `disposition` | `signed: true`, `kind: applied`, `countersigned_count_after: 1` |
| `admission` | `ADMITTED`, SQLSTATE `00000`, after one signed disposition |
| `caveats` | `[]` — nothing in this run is unproven-but-tolerated |
| `failures` | `[]` |
| `verdict` | `PROVEN` |

**`cluster.database` reads `w_qr_gate_refusal_proof`. This is a LOCAL proof and this page does
not say otherwise.** Two further artefacts record the same four beats against CockroachDB
Cloud and against a local database through the real HTTP handler
(`evidence/deploy/cloud-acceptance.json`, `evidence/deploy/acceptance.json`); both were taken
over `scripts/deploy/local_furl.py`, a local emulator of a Lambda Function URL, and both set
`target_is_local_emulator: true`. **Neither of those two is a deployed demo** — see stop 6.
**A third artefact is**: `evidence/demo/live-beats.json`, taken 2026-08-15 through the public
Function URL itself, sets `target_is_local_emulator: false` and records the same four beats
with the same two SQLSTATEs. It is a separate transcript, not a re-labelling of either of the
other two, and stop 6 keeps all three apart.

Three attempts at the same permit merge. The first is a plain `CHECK` constraint refusing a
merge while an obligation is open. The second is the same merge with the projected counter
**forced to zero out of band** — the exact attack a materialised-conflict design has to
survive — and the gate refuses anyway, because the function re-derives the count instead of
believing the column. The third is the same history admitted once a competent person signs.
A gate that always refuses is broken, not safe, so the third line is not decoration.

The `projection` block is the strongest part. One insert of one blocking check moved
`open_blocking` from
0 [src: `…proof-20260814T032418Z.json#projection.open_blocking.before`] to
1 [src: `…#projection.open_blocking.after`], bumped the gate epoch from 0 to
1 [src: `…#projection.gate_epoch`], emitted a `check_opened`
CDC row into `mainline_ops.outbox` [src: `…#projection.outbox`], and projected a severity of
4 [src: `…#projection.severity.projected_onto_the_check`]
onto a row where the client had supplied
0 [src: `…#projection.severity.supplied_by_this_script`].
**The client did not write the number that closed the gate. The database did.**

Since 2026-08-14 the fourth beat is load-bearing in a way it was not before: the admission
requires a **signed disposition**, and signing now resolves the signer's credential and the
defeater-vocabulary digest **out of the database** — `mainline.signing_credential` and
`mainline.defeater_option` — instead of deriving them in the application. Until that landed,
the digest a signature pinned was `sha256(b"defeater-vocab")`, a constant.
[`MUST-NOT-CLAIM.md`](MUST-NOT-CLAIM.md) families 13 and 14 carry what may and may not be
said about it, including the one this project is careful about: **there is no foreign key
from `mainline.disposition` onto `mainline.defeater_option`**, so *that* particular refusal
is the application's and not the database's.

---

## Stop 4 · Five minutes — reproduce it yourself, still with no credential

Four commands. Docker and a Python interpreter; **no account and no credential of ours**.
The durations are from a recorded dry run against a fresh clone
[src: `qa/judge-dry-run.json`], on a machine where `just` and `uv` were not installed
[src: `qa/judge-dry-run.json#host.tools_on_path`] — which is why the plain form is the one
on record.

```bash
git clone -c core.longpaths=true https://github.com/Shaugato/mainline.git
cd mainline
```

Clone into a **short** destination on Windows. Measured with real clones on 2026-08-10:
without the flag a working tree survived a destination of
44 characters [src: `qa/judge-dry-run.json#clone_threshold.without_longpaths.max_working_dest_chars`]
and failed at
45 [src: `…#clone_threshold.without_longpaths.first_failing_dest_chars`];
with the flag no clone failure was seen up to
140 [src: `…#clone_threshold.with_longpaths.no_failure_observed_up_to`],
but one console replay fixture then exceeded what Windows will hand to an ordinary program,
so past 44 characters `git` could read the tree and a plain `open()` could not. Unaffected on
macOS and Linux.

> **RE-MEASURED 2026-08-14, and the cliff has moved a long way out.** The 214-character
> fixture paths that caused it are gone from the tree.
> `python scripts/submission/check_path_lengths.py`, exit **0**:
>
> ```
>   tracked files                     7576
>   longest tracked path              141 chars
>   longest single name component     69 chars
>   Windows usable path               259 chars
>   MAX SAFE CLONE DESTINATION        117 chars
>   paths a 60-char destination cannot check out   0
>   budget: max_tracked_path_chars=141 files_unclonable_at_typical_prefix=0  (falling-only)
>   STATUS: OK
> ```
>
> **A destination of up to 117 characters is now safe, and zero files are unreadable at a
> typical prefix.** `qa/judge-dry-run.json` still records the 2026-08-10 numbers because it
> is a recording and is not hand-edited; the budget program above is the live reading.
> **Keep typing the flag anyway** — it costs nothing off Windows, and a judge cloning into a
> deep path is still cheaper to protect than to diagnose.

**1 · `python scripts/qa/doctor.py`** — exit
1 [src: `qa/judge-dry-run.json#runs.1.steps.0.exit_code`], in
2.788 [src: `…#runs.1.steps.0.duration_s`] seconds.

*Proves:* the preflight tells the truth about the machine it is on. It exits non-zero on
exactly two rows — `uv` and `just` are not installed — prints a numbered remedy under each,
and neither blocks the proof. A doctor that reported green here would be the first thing to
distrust.

**2 · `python -m pip install -e packages/trappoint-migrate`**

*Proves:* the setup step is real and small. `scripts/proof/gate_refusal.py` imports exactly
one workspace distribution and one third-party package, `psycopg`. Skip this and the proof
stops at `ModuleNotFoundError: No module named 'trappoint_migrate'`, which is what the dry
run's first interpreter did [src: `qa/judge-dry-run.json#findings`]. `just setup` does the
fuller job — install `uv`, then `uv sync --all-packages` over every workspace member. **No
committed artefact times this step, so no figure is printed for it.**

**3 · `docker compose -f compose.yaml up -d --wait`**, then
`docker compose -f compose.yaml run --rm crdb-align`

The dry run parsed the compose file rather than starting a second container beside the one
already running — `docker compose -f compose.yaml config`, exit
0 [src: `…#runs.1.steps.1.exit_code`], in
0.472 [src: `…#runs.1.steps.1.duration_s`] seconds.

*Proves:* the node is pinned, not floating. The compose file names
`cockroachdb/cockroach:v26.2.5` exactly, and `crdb-align` sets the local cluster's
`gc.ttlseconds` to 4500 — a deliberately tight retention window — because the local default is
the *more permissive* of the two and a time-travel assumption that is legal on a laptop should
not be legal only there. This page used to call 4500 *the value CockroachDB Cloud Basic
enforces*; that is **withdrawn**, because 4500 was a value we had set ourselves and read back
[src: `docs/upstream/STRIKE-LEDGER.md` §3 claim 4].

**4 · the one command that is the whole point:**

```bash
python scripts/proof/gate_refusal.py \
    --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
```

*Proves:* the whole claim, on your hardware, from a database you started. It bootstraps a
throwaway database, applies the migration chain, seeds one history, and attempts the same
merge three times: refused, refused again under a forged projection, then admitted after a
signed disposition. It writes its own `evidence/gate-refusal/proof-<UTC>.json` — compare it
against the committed one.

Run on this repository at `HEAD` on 2026-08-14 it printed, and exited `0` — the transcript is
the committed `evidence/gate-refusal/proof-20260814T032418Z.json`:

```
chain         271/271 applied, 0 failed, 71.797s
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held · open_blocking 0->1 · gate_epoch 0->1 · outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
```

An older recording in the dry run took 70.351 seconds
[src: `qa/judge-dry-run.json#runs.1.steps.2.duration_s`] against a smaller migration tree,
so expect longer rather than shorter. Every timing in this repository is a laptop timing
taken while other jobs shared the same container; they are upper bounds, not benchmarks.

**Optional · `python -m pytest --crdb=none --collect-only -q`** — exit
0 [src: `…#runs.1.steps.3.exit_code`], in
30.112 [src: `…#runs.1.steps.3.duration_s`] seconds.

*Proves:* the suite is real and imports cleanly with no database anywhere —
9290 [src: `qa/test-state.json#totals.none.tests`] tests were counted by the census, with
0 [src: `qa/test-state.json#totals.none.errored`] collection errors, against no cluster.

> **CORRECTED — this line printed a superseded figure, and here is which figure superseded
> which.** It read `8845` while `qa/test-state.json#totals.none.tests` read
> **`9290`**. The full quartet moved the same way, and both readings are of the same field
> in the same file, one census apart:
>
> | | tests | passed | failed | skipped |
> |---|---:|---:|---:|---:|
> | this page, until now | 8845 | 8065 | 44 | 736 |
> | `qa/test-state.json#totals.none`, today | **9290** | **8323** | **44** | **923** |
>
> The earlier census was taken **before the demo API's own rows were merged into it**; the
> later one includes them. `failed` is unchanged at `44` in both, which is the useful part: the
> count that went up is the denominator, and the failures did not move.
> `docs/HONESTY.md` and `docs/submission/DEVPOST.md` were re-derived against the artefact days
> before this page was, so for those days the two disagreed — **the artefact was right both
> times.** `docs/submission/JUDGING-AXES.md` §4 carries the same correction with the same
> numbers. Neither number was moved to make the other agree, and re-derivation is one command:
> `python -c "import json;print(json.load(open('qa/test-state.json'))['totals']['none'])"`.
>
> Two things the artefact says about itself that this page will not round off: the census
> **predates the producer migrations and has not been retaken**, so it describes a tree that no
> longer exists; and `totals.cluster` records `245` errored with one target timed out and one
> unmeasured, which is a different and worse reading than `totals.none` and is not the one
> quoted above.

The longer account of these same five minutes, including every way they go wrong, is
[`FIRST-FIVE-MINUTES.md`](FIRST-FIVE-MINUTES.md).

---

## Stop 5 · The credentialled path — our live ledger, read-only

Everything above needed nothing from us. This stop is the only one that does, and it is
optional: it lets you read **our** CockroachDB Cloud cluster rather than one you started.

**There is exactly ONE published route to MAINLINE's ledger, and it is a SQL login.** Connect
`psql` — or any SQL client — as the read-only **`mainline_judge`** login, over pgwire, from
your own machine, using [`docs/deploy/JUDGE-PACK.md`](../deploy/JUDGE-PACK.md) §2
(*"Read-only credentials — the ledger, in your own SQL client"*), which carries the host, the
port, the database and the `sslmode`. §2.4 is five minutes from zero to a refusal you can see,
and §3 carries the questions with the answers they returned on the live cluster.

**Where the password is.** It is in the **judge-credentials field of the submission form**,
and nowhere in this repository — not in a file, not in an artefact, not in an environment
variable, not in `SUBMISSION.json`. `check_submission_ready.py` scans that file for eight
credential shapes on every run and fails the submission if one appears.

**What that login can and cannot do**, measured [src: `evidence/deploy/judge-access.json`,
verdict `PROVEN`, `failures: []`]: **14 of 14** `mainline_audit` views readable; **11 of 11**
base-table reads, inserts, `CREATE TABLE` and `DROP VIEW` attempts refused, each with the
expected SQLSTATE. You cannot damage anything, and that is a measurement rather than a
promise.

### Managed MCP — available, working, and deliberately not published

That heading is [`docs/deploy/JUDGE-PACK.md`](../deploy/JUDGE-PACK.md) §4's, word for word,
because this page has no business saying it differently. **The CockroachDB Managed MCP Server
is a SEPARATE path and it does not reach our data with any credential we publish.** It is a
tool we use, evidenced below; it is not a second way in.

* **Why we do not hand you the key.** The credential that opens
  `https://cockroachlabs.cloud/mcp` is an **account-level CockroachDB Cloud service-account
  key**, not a read-only one. Its measured tool list carries `create_database`, `create_table`
  and `insert_rows`, and `list_clusters` enumerates every cluster the account owns — so
  `evidence/deploy/judge-access.json` records `mcp_channel.credential_publishable` as
  **`false`**, and `why_not_publishable` names those four verbs. It is not this deployment's
  credential to hand to a stranger. Read it back in one command:

  ```bash
  python -c "import json;print(json.load(open('evidence/deploy/judge-access.json'))['mcp_channel']['credential_publishable'])"
  ```

  It prints `False`.

* **What you can reproduce is the mechanism, not our data.**
  [`MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md) §1 is the
  copy-pasteable configuration for pointing **your own** MCP client at the Managed MCP Server
  with **your own** key against **your own** cluster; its §0 is the two-path table that says
  which credential goes where. A judge cannot read MAINLINE's ledger over MCP with a
  credential we hand out, because we do not hand one out.

* **The sessions we ran against ours are committed, and they are not clean.**
  `evidence/deploy/judge-run.json` (2026-08-11) drove the sixteen-question pack over this
  channel as SQL identity `managed-mcp` — not `root`, not the database owner — and records
  **15 of 16**. `evidence/mcp/pack-run.json` (2026-08-16) re-ran the same sixteen through the
  pack's own runner to the same **15 of 16**, `exit_code` `1`, verdict
  **`DIVERGED — KNOWN GAP`**. The one FAIL is **`N01`** and it is preserved rather than
  rounded off: `mainline_qa` **is** readable by the `managed-mcp` identity, which the pack
  asserted it was not. The `mainline_judge` login this stop publishes refuses that same
  statement at `42501`. Both numbers in two commands:

  ```bash
  python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['passed'],'of',d['total'],'exit',d['exit_code'])"
  python -c "import json;d=json.load(open('evidence/deploy/judge-run.json'))['channels']['mcp'];print(d['passed'],'of',d['total'],d['sql_identity'])"
  ```

  They print `15 of 16 exit 1` and `15 of 16 managed-mcp`. **The 15 is not rounded to 16 here
  and is not rounded to 16 anywhere else** — that refusal is what makes the other fifteen
  worth reading.

> **CORRECTED — this stop used to offer a second route, and there is not a second route.**
> An earlier version of this stop listed the Managed MCP Server as a second published
> read-only route, sufficient on its own. That was false for the reason directly
> above, and the identical wording had already been found and corrected in `SUBMISSION.json`'s
> `judge_access.how` field: [`RULES-MATRIX.md`](RULES-MATRIX.md) §3 R2 records that
> correction and dates it **2026-08-16**. This page was the last file carrying it, and it is
> recorded here rather than deleted quietly, because a project that publishes a correction and
> then contradicts it is worse off than one that never corrected anything.
>
> **Four documents already said it correctly, and this stop now says what they say rather than
> inventing a fifth phrasing:** `SUBMISSION.json` → `judge_access.how` (*"The CockroachDB
> Managed MCP Server is a SEPARATE path and it does not reach our data with any credential we
> publish"*); [`JUDGE-PACK.md`](../deploy/JUDGE-PACK.md) §4, the heading above;
> [`MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md) §0 and §1 (*"your own"*
> key, *"your own"* cluster); and [`census/close-block.md`](census/close-block.md) §7.2 —
> *"the read-only endpoint a stranger can actually verify is the `mainline_judge` pgwire login
> — **not** the MCP one-liner."*

---

## Stop 6 · What is not here, and what we are not claiming

~~**There is no demo URL yet, and two files that read `PROVEN` do not change that.**~~
**SUPERSEDED 2026-08-15 — there is a demo URL, and a third file that reads `PROVEN` was taken
through it.** `evidence/demo/live-beats.json` records eleven requests to
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` with
`target_is_local_emulator: false`, `failures: []`, and the four beats at
`00000` / `23514` `gate_closed_when_issued` / `P0001` `mainline.fn_permit_merge_gate` /
`00000`. It needed no credential of ours and neither do you.

~~**`docs/submission/SUBMISSION.json` nevertheless still holds the literal `UNRESOLVED` for
`demo_url` and for `video_url`, and this page is not the file that resolves them.**~~
**SUPERSEDED 2026-08-16 for the `demo_url` half — that field now holds the origin.**
`SUBMISSION.json:20` carries the live Function URL, and the file's own
`notes.demo_url` opens `RESOLVED 2026-08-16` and preserves the two claims that preceded it
rather than deleting them. The disagreement between a document and the wire that this
paragraph used to record is closed, and it closed by the document being written to match the
wire rather than by this page asserting it. **`video_url` is still the literal `UNRESOLVED`,
it is genuinely unresolved — the film has not been uploaded — and this page is not the file
that resolves it.** Both halves in one command:

```bash
python -c "import json;d=json.load(open('docs/submission/SUBMISSION.json'));print(d['demo_url']);print(d['video_url'])"
```

`check_submission_ready.py`, re-run for this page **without** `--check-urls`, prints
`PASS demo URL <the origin> (not fetched; pass --check-urls to require HTTP 200)` and
`FAIL video URL video_url is UNRESOLVED`. It still exits non-zero, and `video URL` is one of
the rows keeping it there — no exit code is printed here that nobody took.

Read the rest of this stop before you open `evidence/deploy/`, because it is the one place where
an honest artefact could be misread as a deployment. **The two *acceptance* artefacts read
`verdict: PROVEN` as of 2026-08-14, and both were taken over a local socket — that is still
true of them, and the live-beats transcript above is a separate artefact and not a re-labelling
of either:**

| artefact | database under test | HTTP hop | what it proves |
|---|---|---|---|
| `evidence/deploy/acceptance.json` | `w_w3` on `localhost:26257`, `is_cockroachdb_cloud: false` | `http://127.0.0.1:8792`, `target_is_local_emulator: true` | the real handler and the real console bundle work, reproducibly, on a laptop |
| `evidence/deploy/cloud-acceptance.json` | `mainline_demo` on `mainline-dev-31219.…cockroachlabs.cloud:26257`, `is_cockroachdb_cloud: true` | `http://127.0.0.1:8791`, `target_is_local_emulator: true` | the same handler against the database the demo would actually meet |

The HTTP hop in both is `scripts/deploy/local_furl.py`, an emulator of a Lambda Function URL,
and it says so in a header it sets on every response:
`x-mainline-not-the-demo-url: … It is not the deployed demo and must not be published as
one.` **One artefact's `mode_description` field claims the run was "against CockroachDB
Cloud" when its own `target_provenance` says `localhost` — read `target_provenance`, not
`mode_description`.** At the time of writing, `cloud-acceptance.json` was untracked in the
working tree; if it is not in your clone, that is why.

The plan that created the origin is committed at
`evidence/deploy/terraform-plan-furl.txt` — `Plan: 24 to add, 0 to change, 0 to destroy` at line 843:
11 resources in `module.api[0]` and 13 in `module.guard[0]`, the cost guard that
`infra/envs/demo/main.tf:631` now instantiates. **An earlier version of this page said 11**,
which was the count before the guard was wired in; the artefact is the authority and this
sentence is derived from it, so re-read it with
`grep -n '^Plan:' evidence/deploy/terraform-plan-furl.txt` rather than trusting us. **It is a
plan and it stays a plan** — a record of what was going to be created, not a claim about what
now exists; what exists is measured over HTTP and is quoted at the top of this stop. Writing a
hostname into `SUBMISSION.json` before the origin existed would have turned our own gate green
and still handed you a 404, which is precisely the failure that file exists to prevent — and it
is why that field still holds the sentinel today rather than being back-filled by this page.
[`RULES-MATRIX.md`](RULES-MATRIX.md) carries the rule-by-rule verdicts, each with the command
that re-derives it.

**Three commands hand you the same evidence, with the URL and nothing else** — no account, no
credential, no AWS access, no database, no build:

| command | what it answers |
|---|---|
| `.venv/Scripts/python.exe scripts/demo/demo_ready.py` | *is the deployed world ready?* — eight facts, read-only, zero writes ([`docs/demo/DEMO-READY.md`](../demo/DEMO-READY.md)) |
| `.venv/Scripts/python.exe scripts/proof/live_beats.py --base-url <the URL>` | the four beats off the URL, each with the SQLSTATE the database produced ([`docs/demo/LIVE-BEATS.md`](../demo/LIVE-BEATS.md)) |
| `.venv/Scripts/python.exe scripts/proof/memory_loop.py --base-url <the URL>` | STORE → RETRIEVE → ACT, forty rows with a table and a column behind each ([`docs/demo/MEMORY-LOOP.md`](../demo/MEMORY-LOOP.md)) |

**And the film is not shot in the MAINLINE console.** It is shot in the software the people in
the story use — a permit-to-work screen at `/operator.html#/permit` and a management-of-change
screen at `/operator.html#/change` — with the refusal landing inside those screens, because
that is where a refusal lands in reality.

> ~~Those two screens are **in the tree and not on the origin yet**: measured 2026-08-15,
> `GET /operator.html` returns the console shell byte-for-byte identical to `GET /`, which is
> the SPA fallback.~~
>
> **SUPERSEDED — re-measured 2026-08-16, and the operator surface IS on the origin.**
> `GET /operator.html` returns **200, 5,097 bytes**, `<title>Control of Work</title>`,
> against `GET /` at **200, 4,749 bytes**, `<title>MAINLINE console</title>` — different
> length, different SHA-256 (`37454502e640e505c35b28c8…` vs `9bd68bcdf30799d3b57c9e35…`),
> and it loads its **own** bundle rather than the console's:
> `GET /assets/operator-D24tzVGh.js` → **200, 96,734 B** and
> `GET /assets/operator-DTSzHtCs.css` → **200, 33,043 B**. **It is not the SPA fallback.**
> `/judge` and `/console` *are* the fallback and still return the console shell at 4,749
> bytes, which is how the difference was isolated.
>
> **One limit, kept explicit.** `#/permit` and `#/change` are hash fragments resolved
> client-side; a hash is never sent to the server, so the readings above prove the document
> and its assets serve and prove **nothing** about what either route renders. Open
> `<origin>/operator.html#/permit` in a browser to settle that — no `curl` can.
>
> Re-derive the whole finding in one command:
> `curl -s -o /dev/null -w "%{http_code} %{size_download}\n" <origin>/operator.html`



Five more, taken from [`docs/HONESTY.md`](../HONESTY.md). Nothing here is softened for a
submission; if anything, read it first.

* **The migration count everyone quotes is a survey, not a deployment.** The newest
  committed proof records 271 of 271
  applied [src: `evidence/gate-refusal/proof-20260814T032418Z.json#chain.applied_count`] with
  0 failures [src: `…#chain.failed_count`] — but the applier that produced it continues past
  every failure by design. It was not always this number: an earlier committed run records
  246 of 261 applied [src: `evidence/gate-refusal/proof-20260810T004200Z.json#chain.applied_count`]
  with 15 failures [src: `…#chain.failed_count`], every one of them a table whose triggers
  and views were written and whose producer was not. Those producers landed. The
  forward-only runner a real deployment uses has been driven over the whole tree and **wrote
  no artefact under `qa/` or `evidence/`**, so `docs/HONESTY.md` prints no figure for it and
  neither does this page — including now that the news is good. Re-derive the count; never
  quote a remembered one.
* **The conformance suite has never been demonstrated end to end.** For the whole of this
  build its cases errored against a bare node instead of skipping, and `docs/HONESTY.md`
  calls that the single largest gap between what this repository contains and what it has
  shown. A first census exists — [`qa/conformance-census.json`](../../qa/conformance-census.json),
  taken against a fully migrated schema — and of 71 declared cases it records 55 that could
  not run at all, 6 red, and 10 that held. A first modest result is not a demonstrated suite,
  and it is a long way from one.
* **The corpus is authored and the model transcripts are recorded cassettes.** Every
  procedure, clause, setpoint, incident, permit, operator and site under `verticals/` was
  written for this repository. The compressor-setpoint story is a designed worked example —
  no real incident, no real fatality, no real site. Agent tests replay captured
  request/response pairs, so a green agent test proves this code handles that recorded
  exchange and proves nothing about a live model today; where a live call is genuinely
  required the test skips and the reason is published in the census. The private keys under
  `evidence/reference-ledger/keys/` are named `NOT-SECRET` because they are: published on
  purpose so a stranger can verify the offline bundle without asking anyone for anything.
* **Inference is in Sydney and the database is in Singapore.** Bedrock runs in
  `ap-southeast-2`; the CockroachDB Cloud cluster is in `aws-ap-southeast-1`, because
  `ap-southeast-2` is Advanced-tier only and this project is on Basic. There is **no
  end-to-end Australian residency** and any claim of one would be false. The recall path
  crosses a region boundary on every embedding call and this repository holds no p50, no p99
  and no load profile for that hop. The one cross-region cost that *is* measured is DDL, not
  recall.
* **Every timing here is a local timing.** The inner loop is a single-node CockroachDB in
  Docker on one laptop, and the seconds on this page were recorded while other jobs shared
  the same container [src: `qa/judge-dry-run.json#operator_notes`].
  **Nothing has ever run against CockroachDB Cloud in CI** — re-checked 2026-08-14 and still
  true. The cluster exists and several transcripts against it are committed
  (`evidence/deploy/cloud-chain.json` `APPLIED`, `evidence/deploy/cloud-seed.json`
  `SEEDED AND REFUSABLE`); every one of them was driven by hand. No automated lane has ever
  pointed at it.
  Two further limits belong beside this one: `trappoint-verify` exits `2` over
  the reference ledger because
  9 [src: `qa/test-state.json#external_checks.custody_bundle_verification.counts.passed`] of
  its 16 [src: `…counts.total`] checks ran and held while
  7 [src: `…counts.not_checked`] — the cryptographic half — did not run at all; and the test
  census in `qa/test-state.json` was taken before the producer migrations landed and has not
  been retaken, so it describes a tree that no longer exists.
