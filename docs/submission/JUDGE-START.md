<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# JUDGE START

**One path, six stops, no credential until stop 5.** Everything up to and including the
command that reproduces this project's central claim needs nothing from us — no account, no
key, no login, no email. The repository is public: `github.com/Shaugato/mainline`, Apache-2.0,
`master`.

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
the conformance suite has never been demonstrated end to end, and a demo-health lane cannot
be green while no demo is deployed. `CI-STATE.md` says which is which, names the run id, and
records the rule that a red reporting true incompleteness **stays red with a sharper
message**. `continue-on-error` and `|| true` are banned in this repository.

---

## Stop 2 · The Actions tab, with that in hand

`github.com/Shaugato/mainline/actions` — public, no login.

Green at `HEAD` includes `submission`, `claims`, `boundary`, `release-proof`, `console`,
`skills`, `judge-pack` and `mutation-ratchet`. Red at `HEAD` includes `custody-chain`,
`schema`, `demo-health`, `db`, `db-schema` and `ci`. **`CI-STATE.md` tells you which reds
are load-bearing admissions and which are work in flight**, and it is the only honest way to
read that page. A submission that showed you an all-green tab six days before a deadline,
with nothing deployed, would be telling you something about its badges rather than about its
software.

---

## Stop 3 · Ninety seconds — the claim as a transcript

**[`evidence/gate-refusal/`](../../evidence/gate-refusal/)** — the product's central claim,
as a recording rather than a sentence.

Open the newest `proof-<UTC>.json`. It is what one CockroachDB cluster did at one instant,
written by `scripts/proof/gate_refusal.py`. The newest, taken on 2026-08-12
[src: `evidence/gate-refusal/proof-20260812T163857Z.json`]:

| Field | Value |
|---|---|
| `chain` | `271` of `271` applied, `0` failed, `51.336` s |
| `refusal` | `REFUSED`, SQLSTATE `23514`, constraint `gate_closed_when_issued` |
| `drift_refusal` | `REFUSED`, SQLSTATE `P0001`, `mainline.fn_permit_merge_gate` |
| `admission` | `ADMITTED`, SQLSTATE `00000`, after one signed disposition |
| `caveats` | *(none)* — nothing in this run is unproven-but-tolerated |
| `verdict` | `PROVEN` |

Three attempts at the same permit merge. The first is a plain `CHECK` constraint refusing a
merge while an obligation is open. The second is the same merge with the projected counter
**forced to zero out of band** — the exact attack a materialised-conflict design has to
survive — and the gate refuses anyway, because the function re-derives the count instead of
believing the column. The third is the same history admitted once a competent person signs.
A gate that always refuses is broken, not safe, so the third line is not decoration.

The `projection` block is the strongest part. One insert of one blocking check moved
`open_blocking` from
0 [src: `…proof-20260812T163857Z.json#projection.open_blocking.before`] to
1 [src: `…#projection.open_blocking.after`], bumped the gate epoch, emitted a `check_opened`
CDC row, and projected a severity of
4 [src: `…#projection.severity.projected_onto_the_check`]
onto a row where the client had supplied
0 [src: `…#projection.severity.supplied_by_this_script`].
**The client did not write the number that closed the gate. The database did.**

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

Clone into a **short** destination on Windows. Measured with real clones: without the flag a
working tree survives a destination of
44 characters [src: `qa/judge-dry-run.json#clone_threshold.without_longpaths.max_working_dest_chars`]
and fails at
45 [src: `…#clone_threshold.without_longpaths.first_failing_dest_chars`];
with the flag no clone failure was seen up to
140 [src: `…#clone_threshold.with_longpaths.no_failure_observed_up_to`],
but one console replay fixture then exceeds what Windows will hand to an ordinary program,
so past 44 characters `git` can read the tree and a plain `open()` cannot. Unaffected on
macOS and Linux.

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

Run on this repository at `HEAD` on 2026-08-12 it printed, and exited `0`:

```
chain         271/271 applied, 0 failed, 51.336s
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
8845 [src: `qa/test-state.json#totals.none.tests`] tests were counted by the census, with
0 [src: `qa/test-state.json#totals.none.errored`] collection errors, against no cluster.

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

**There is no demo URL yet.** `docs/submission/SUBMISSION.json` holds the literal
`UNRESOLVED` for `demo_url` and for `video_url`, because `terraform apply` has not been run
and the film has not been shot. The plan that would create the origin is committed at
`evidence/deploy/terraform-plan-furl.txt` — `Plan: 24 to add, 0 to change, 0 to destroy` at line 843:
11 resources in `module.api[0]` and 13 in `module.guard[0]`, the cost guard that
`infra/envs/demo/main.tf:631` now instantiates. **An earlier version of this page said 11**,
which was the count before the guard was wired in; the artefact is the authority and this
sentence is derived from it, so re-read it with
`grep -n '^Plan:' evidence/deploy/terraform-plan-furl.txt` rather than trusting us. Writing a
hostname into `SUBMISSION.json` before the origin exists would turn our own gate green and still
hand you a 404, which is precisely the failure that file exists to prevent.
[`RULES-MATRIX.md`](RULES-MATRIX.md) carries the rule-by-rule verdicts, each with the command
that re-derives it.

Five more, taken from [`docs/HONESTY.md`](../HONESTY.md). Nothing here is softened for a
submission; if anything, read it first.

* **The migration count everyone quotes is a survey, not a deployment.** The newest
  committed proof records 271 of 271
  applied [src: `evidence/gate-refusal/proof-20260812T163857Z.json#chain.applied_count`] with
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
  Nothing has ever run against CockroachDB Cloud in CI. The cluster exists and there is a
  captured transcript; no automated lane has ever pointed at it.
  Two further limits belong beside this one: `trappoint-verify` exits `2` over
  the reference ledger because
  9 [src: `qa/test-state.json#external_checks.custody_bundle_verification.counts.passed`] of
  its 16 [src: `…counts.total`] checks ran and held while
  7 [src: `…counts.not_checked`] — the cryptographic half — did not run at all; and the test
  census in `qa/test-state.json` was taken before the producer migrations landed and has not
  been retaken, so it describes a tree that no longer exists.
