<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# JUDGE START

Ninety seconds, then five minutes, then the list of things this project does not claim.
Every figure below resolves to a file in this repository, named beside it.

---

## What to look at if you have 90 seconds

**1 · [`evidence/gate-refusal/`](../../evidence/gate-refusal/) — the product's central claim,
as a transcript rather than a sentence.**

Open the newest `proof-<UTC>.json`. It is what one CockroachDB cluster did at one instant,
written by `scripts/proof/gate_refusal.py`. Four fields carry the whole argument:

| Field | Value |
|---|---|
| `refusal` | `REFUSED`, SQLSTATE `23514`, constraint `gate_closed_when_issued` |
| `drift_refusal` | `REFUSED`, SQLSTATE `P0001`, `mainline.fn_permit_merge_gate` |
| `admission` | `ADMITTED`, SQLSTATE `00000`, after one signed disposition |
| `verdict` | `PROVEN` |

Three attempts at the same permit merge. The first is a plain `CHECK` constraint refusing a
merge while an obligation is open. The second is the same merge with the projected counter
**forced to zero out of band** — the exact attack a materialised-conflict design has to
survive — and the gate refuses anyway, because the function re-derives the count instead of
believing the column. The third is the same history admitted once a competent person signs.
A gate that always refuses is broken, not safe, so the third line is not decoration.

The `projection` block is the newest and the strongest part. One insert of one blocking
check moved `open_blocking` from
0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.open_blocking.before] to
1 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.open_blocking.after],
bumped the gate epoch, emitted a `check_opened` CDC row, and projected a severity of
4 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.severity.projected_onto_the_check]
onto a row where the client had supplied
0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.severity.supplied_by_this_script].
The client did not write the number that closed the gate. The database did.

**2 · [`docs/HONESTY.md`](../HONESTY.md) — the reason to believe the first artefact.**

It publishes what is broken, what is synthetic and what was never built, and every quantity
on it carries an inline reference to the file under `qa/` or `evidence/` that produced it.
`tests/release/test_honesty_is_checkable.py` reads the document, follows every reference and
**fails the build when a number and its source disagree** — and fails it again when evidence
*appears* that the document has not absorbed. A page of caveats nobody can falsify is a
disclaimer; this one is a test.

---

## What to run if you have five minutes

Four commands. Docker and a Python interpreter, no account and no credential of ours. Each
line below is what was **typed** in a recorded dry run against a fresh clone
[src: qa/judge-dry-run.json], with the exit code and the seconds that run produced. `just`
and `uv` were not installed on that machine
[src: qa/judge-dry-run.json#host.tools_on_path], which is why the plain form is the one on
record.

```bash
git clone -c core.longpaths=true https://github.com/Shaugato/mainline.git
```

Clone into a **short** destination on Windows. Measured with real clones: without the flag a
working tree survives a destination of
44 characters [src: qa/judge-dry-run.json#clone_threshold.without_longpaths.max_working_dest_chars]
and fails at
45 [src: qa/judge-dry-run.json#clone_threshold.without_longpaths.first_failing_dest_chars];
with the flag no clone failure was seen up to
140 [src: qa/judge-dry-run.json#clone_threshold.with_longpaths.no_failure_observed_up_to],
but one console replay fixture then exceeds what Windows will hand to an ordinary program,
so past 44 characters `git` can read the tree and a plain `open()` cannot. Unaffected on
macOS and Linux.

**1 · `python scripts/qa/doctor.py`** — exit
1 [src: qa/judge-dry-run.json#runs.1.steps.0.exit_code], in
2.788 [src: qa/judge-dry-run.json#runs.1.steps.0.duration_s] seconds.

*Proves:* the preflight tells the truth about the machine it is on. It exits non-zero on
exactly two rows — `uv` and `just` are not installed — prints a numbered remedy under each,
and neither blocks the proof. A doctor that reported green here would be the first thing to
distrust.

**2 · `python -m pip install -e packages/trappoint-migrate`**

*Proves:* the setup step is real and small. `scripts/proof/gate_refusal.py` imports exactly
one workspace distribution and one third-party package, `psycopg`. Skip this and the proof
stops at `ModuleNotFoundError: No module named 'trappoint_migrate'`, which is what the dry
run's first interpreter did [src: qa/judge-dry-run.json#findings]. `just setup` does the
fuller job — install `uv`, then `uv sync --all-packages` over every workspace member. **No
committed artefact times this step, so no figure is printed for it.**

**3 · `docker compose -f compose.yaml up -d --wait`**, then
`docker compose -f compose.yaml run --rm crdb-align`

The dry run parsed the compose file rather than starting a second container beside the one
already running — `docker compose -f compose.yaml config`, exit
0 [src: qa/judge-dry-run.json#runs.1.steps.1.exit_code], in
0.472 [src: qa/judge-dry-run.json#runs.1.steps.1.duration_s] seconds.

*Proves:* the node is pinned, not floating. The compose file names
`cockroachdb/cockroach:v26.2.5` exactly, and `crdb-align` sets the local cluster's
`gc.ttlseconds` to 4500 — the value CockroachDB Cloud Basic enforces — because the local
default is the *more permissive* of the two and a time-travel assumption that is legal on a
laptop should not be legal only there.

**4 · `python scripts/proof/gate_refusal.py --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable"`**
— exit 0 [src: qa/judge-dry-run.json#runs.1.steps.2.exit_code], `VERDICT PROVEN`, in
70.351 [src: qa/judge-dry-run.json#runs.1.steps.2.duration_s] seconds.

*Proves:* the whole claim, on your hardware, from a database you started. It bootstraps a
throwaway database, applies the migration chain, seeds one history, and attempts the same
merge three times: refused, refused again under a forged projection, then admitted after a
signed disposition. It writes its own `evidence/gate-refusal/proof-<UTC>.json` — compare it
against the committed one. That recording names the commit it ran against
[src: qa/judge-dry-run.json#source.head], and the migration tree has grown since, so this
step now takes longer than the figure above, not less.

**Optional · `python -m pytest --crdb=none --collect-only -q`** — exit
0 [src: qa/judge-dry-run.json#runs.1.steps.3.exit_code], in
30.112 [src: qa/judge-dry-run.json#runs.1.steps.3.duration_s] seconds.

*Proves:* the suite is real and imports cleanly with no database anywhere —
8845 [src: qa/test-state.json#totals.none.tests] tests were counted by the census, with
0 [src: qa/test-state.json#totals.none.errored] collection errors, against no cluster.

The longer account of a judge's first five minutes, including every way it goes wrong, is
[`FIRST-FIVE-MINUTES.md`](FIRST-FIVE-MINUTES.md).

---

## What we are not claiming

Five things, taken from [`docs/HONESTY.md`](../HONESTY.md). Nothing here is softened for a
submission; if anything, read it first.

* **The migration count everyone quotes is a survey, not a deployment.** The committed proof
  records 271 of 271
  applied [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.applied_count] and
  0 failures [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.failed_count] —
  but the applier that produced it continues past every failure by design. It was not always
  this number: an earlier committed run records 246 of 261
  applied [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.applied_count] with
  15 failures [src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.failed_count],
  every one of them a table whose triggers and views were written and whose producer was not.
  Those producers landed. The forward-only runner a real deployment uses has since been
  driven over the whole tree and **wrote no artefact under `qa/` or `evidence/`**, so
  `docs/HONESTY.md` prints no figure for it and neither does this page — including now that
  the news is good.
* **The conformance suite had never been run to completion.** For the whole of this build its
  cases errored against a bare node instead of skipping, and `docs/HONESTY.md` calls that the
  single largest gap between what this repository contains and what it has shown. A first
  census now exists — [`qa/conformance-census.json`](../../qa/conformance-census.json), taken
  against a fully migrated schema — and of 71 declared cases it records 55 that could not run
  at all, 6 red, and 10 that held. `docs/HONESTY.md` has not absorbed that census yet. A
  first modest result is not a demonstrated suite, and it is a long way from one.
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
* **Every timing in the demo is a local timing.** The inner loop is a single-node CockroachDB
  in Docker on one laptop, the seconds on this page were recorded while other jobs shared the
  same container [src: qa/judge-dry-run.json#operator_notes], and a stopwatch on the demo is
  measuring that, not a managed cluster across a region boundary.
  Nothing has ever run against CockroachDB Cloud in CI; the chain has been applied there by
  hand, and a hand-run is not a lane.
  Two further limits belong beside this one: `trappoint-verify` exits `2` over
  the reference ledger because
  9 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.passed] of its
  16 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.total] checks
  ran and held while
  7 [src: qa/test-state.json#external_checks.custody_bundle_verification.counts.not_checked]
  — the cryptographic half — did not run at all; and the test census in
  `qa/test-state.json` was taken before the producer migrations landed and has not been
  retaken, so it describes a tree that no longer exists.
