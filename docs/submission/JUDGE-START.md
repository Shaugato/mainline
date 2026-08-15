<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# JUDGE START

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
`gc.ttlseconds` to 4500 — the value CockroachDB Cloud Basic enforces — because the local
default is the *more permissive* of the two and a time-travel assumption that is legal on a
laptop should not be legal only there.

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

Two published routes, both read-only, either one sufficient:

1. **MCP** — point any MCP client at the CockroachDB Managed MCP Server using the
   configuration in [`verticals/mainline/demo/judge/MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md) §1.
2. **psql** — connect as the read-only `mainline_judge` SQL login using
   [`docs/deploy/JUDGE-PACK.md`](../deploy/JUDGE-PACK.md), which carries the host, the
   database and the sixteen questions with their expected answers.

**Where the password is.** It is in the **judge-credentials field of the submission form**,
and nowhere in this repository — not in a file, not in an artefact, not in an environment
variable, not in `SUBMISSION.json`. `check_submission_ready.py` scans that file for eight
credential shapes on every run and fails the submission if one appears.

**What that login can and cannot do**, measured [src: `evidence/deploy/judge-access.json`,
verdict `PROVEN`, `failures: []`]: **14 of 14** `mainline_audit` views readable; **11 of 11**
base-table reads, inserts, `CREATE TABLE` and `DROP VIEW` attempts refused, each with the
expected SQLSTATE. You cannot damage anything, and that is a measurement rather than a
promise.

---

## Stop 6 · What is not here, and what we are not claiming

~~**There is no demo URL yet, and two files that read `PROVEN` do not change that.**~~
**SUPERSEDED 2026-08-15 — there is a demo URL, and a third file that reads `PROVEN` was taken
through it.** `evidence/demo/live-beats.json` records eleven requests to
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` with
`target_is_local_emulator: false`, `failures: []`, and the four beats at
`00000` / `23514` `gate_closed_when_issued` / `P0001` `mainline.fn_permit_merge_gate` /
`00000`. It needed no credential of ours and neither do you.

**`docs/submission/SUBMISSION.json` nevertheless still holds the literal `UNRESOLVED` for
`demo_url` and for `video_url`, and this page is not the file that resolves them.** `video_url`
is genuinely unresolved — the film has not been uploaded. `demo_url` is a disagreement between
a document and the wire, and **where they disagree the wire wins and this paragraph is the
record of it**. `check_submission_ready.py`, RAN 2026-08-14, reported both as unresolved rows;
it has not been re-run here and no exit code is printed for it that nobody took.

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
that is where a refusal lands in reality. Those two screens are **in the tree and not on the
origin yet**: measured 2026-08-15, `GET /operator.html` returns the console shell byte-for-byte
identical to `GET /`, which is the SPA fallback.

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
