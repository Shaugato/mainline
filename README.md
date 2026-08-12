<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MAINLINE

**Institutional safety memory as a version-controlled repository whose commits are written by incidents.**

Every clause of a procedure, setpoint, isolation standard and critical control carries a **blame pointer to the event that wrote it**. The permit-to-work is a **protected branch**. Its merge is *refused by the database* until every recalled precursor carries a signed disposition.

Recall is not displayed beside the decision. **Recall is a precondition of the decision.**

If you are judging this, [`docs/submission/JUDGE-START.md`](docs/submission/JUDGE-START.md)
is ninety seconds: what to look at, what to run, and what we are not claiming.

**What the rules ask for, and where each one is:**

| Required | Where it is |
|---|---|
| **Demo URL** | `UNRESOLVED` |
| **Judge access — free and unrestricted** | `UNRESOLVED` |
| **Video, under 3 minutes** | `UNRESOLVED` |
| **Which CockroachDB tools and AWS services, and how** | [`docs/TOOL-USAGE.md`](docs/TOOL-USAGE.md) — every tool and every service with a file, a line number, and a verdict saying whether it has actually run |
| **Repository and licence** | `https://github.com/Shaugato/mainline` — **public since 2026-08-11** · root [`LICENSE`](LICENSE) is Apache-2.0 |

`UNRESOLVED` is a **literal token**, not a placeholder somebody forgot to replace. Those three
rows render from [`docs/submission/SUBMISSION.json`](docs/submission/SUBMISSION.json), the one
file in this repository where a submission URL may be written, and every field in it starts
life as that exact string. That file has since landed and is tracked; those three fields still
hold `UNRESOLVED` because nothing is deployed and no film exists, so the rows still say so. A
submission checklist that looks finished before it is finished is the one failure mode this
repository is built to refuse — including when the thing being described is the submission.

`python scripts/submission/check_submission_ready.py` reads that file, prints exactly what is
missing and what would resolve it, and reports **0 rows NOT CHECKED** — because a question
nobody could answer is an unresolved row, never a pass.

---

## Clone it, then four commands — no account, no credential

```bash
git clone -c core.longpaths=true https://github.com/Shaugato/mainline.git
```

**The flag is there because this repository has paths Windows will refuse under a long
destination, and we would rather say so than let you find out at checkout.** The longest
tracked path is
141 characters [src: qa/judge-dry-run.json#path_lengths.max_tracked_path_chars] —
`skills/upstream/cockroachdb-resilience-and-disaster-recovery/verifying-a-restore-by-merkle-root/scripts/verify_restore_merkle_root.py.license`
— against a Windows `MAX_PATH` of 260. A program without long-path support needs
`len(destination) + 1 + len(path)` to stay at or under 259, which leaves a clone destination
of
117 characters [src: qa/judge-dry-run.json#path_lengths.max_safe_clone_prefix_chars].

**This paragraph used to say 214 characters, and name a console replay fixture whose filename
was derived from the HTTP request it recorded.** That fixture is no longer tracked and is not
on disk. `git log --all --diff-filter=A` finds the commit that added it and nothing has
tracked it since, so the number it supported went with it. The artefact still records `214` under
`clone_threshold.longest_tracked_path_chars`, because that is the path the clone
binary-search was run against — **so the 44/45 thresholds it published describe a tree that
no longer exists, and this page no longer quotes them.** The citation on the old sentence
pointed at `path_lengths.max_tracked_path_chars`, which has read `141` throughout. A number
that is right for a different field is the quietest kind of wrong.

Re-measured on 2026-08-12 with real clones of this tree, three probes rather than a binary
search — so these are a bracket, not a threshold:

| destination | `dest + 1 + 141` | `core.longpaths` | result |
|---|---|---|---|
| 111 chars | 253 | `false` | clone exits 0, tree clean, longest file readable by a plain `open()` |
| 122 chars | 264 | `false` | `error: unable to create file …: Filename too long`, exit 128, 7 437 dirty paths |
| 122 chars | 264 | `true` | clone exits 0, **tree clean**, and a plain `open()` still raises `FileNotFoundError` |

The arithmetic puts the boundary at 117/118 and the artefact's own
`max_safe_clone_prefix_chars` agrees; the bracket is what was actually observed.

**The flag fixes `git`, not everything else** — the half a mitigation notice usually omits,
and the third row above is it. With the flag the checkout completes and `git status` is
clean, and a file whose full path exceeds what Windows hands an ordinary program is still
unreadable by one. Clone into something short — `D:\m`, `C:\src\m` — if you want every file
readable by every tool. On macOS and Linux the flag is a no-op.

### The four commands, and the same four without `just`

Both columns are first-class. `just` and `uv` are **not** installed on the machine every
number on this page was measured on [src: qa/judge-dry-run.json#host.tools_on_path], so the
right-hand column is the one that was actually executed. The proof needs Docker and a Python
interpreter, and nothing else.

| The recipe | The same thing, plain |
|---|---|
| `just doctor` | `python scripts/qa/doctor.py` |
| `just setup` | `python -m pip install -e packages/trappoint-migrate` |
| `just up` | `docker compose -f compose.yaml up -d --wait`<br>then `docker compose -f compose.yaml run --rm crdb-align` |
| `just prove` | `python scripts/proof/gate_refusal.py --dsn "postgresql://root@localhost:26257/defaultdb?sslmode=disable"` |

Four things that column is honest about.

* **`python scripts/qa/doctor.py` exits 1 on this machine, and it is right to.** The only rows
  it fails are `uv` and `just`; it prints a numbered remedy under each and it does not block
  the proof.
* **The install step is not optional.** An earlier version of this page said the proof needed
  "nothing but the interpreter". A recorded dry run falsified that
  [src: qa/judge-dry-run.json#runs], and re-running it today into a brand-new
  `python -m venv` falsifies it again — with a different module name, because the import
  order moved:

  ```
  $ <fresh-venv>/python scripts/proof/gate_refusal.py --dsn …
  File "scripts/proof/gate_refusal.py", line 125, in <module>
      import psycopg
  ModuleNotFoundError: No module named 'psycopg'
  ```

  The recorded run stopped at `No module named 'trappoint_migrate'`; today it stops one
  import earlier. Same lesson, different line, and the line is printed rather than
  remembered. The pip line above installs that one distribution and what it pulls in —
  measured `psycopg`, `psycopg-binary`, `psycopg-pool`, `typing-extensions`, `tzdata` and
  `trappoint-migrate` itself, six packages in **19.7 s** on this machine. `just setup` does
  the fuller job: it installs `uv` if absent, then `uv sync --all-packages` across every
  workspace member.
* **`crdb-align`** pins the local node's `gc.ttlseconds` to 4500, the value CockroachDB Cloud
  Basic enforces, so a time-travel assumption that is legal on your laptop is not one that
  fails in the cloud. The local default is the *more permissive* of the two.

What each step cost when it was recorded — one clone of `HEAD`, one shared local node, other
jobs running against the same container, so every figure is an upper bound rather than a
benchmark [src: qa/judge-dry-run.json#operator_notes] — beside what the same command cost
today, run from the clean virtual environment described above:

| Step | Exit | Recorded | Measured 2026-08-12 |
|---|---|---|---|
| `python scripts/qa/doctor.py` | 1, on `uv` and `just` only | 2.788 s [src: qa/judge-dry-run.json#runs.1.steps.0.duration_s] | 1, same two rows |
| `docker compose -f compose.yaml config` | 0 | 0.472 s [src: qa/judge-dry-run.json#runs.1.steps.1.duration_s] | 0, 0.9 s |
| `python -m pip install -e packages/trappoint-migrate` | 0 | *(not timed by any artefact)* | 0, 19.7 s |
| `python scripts/proof/gate_refusal.py …` | 0, `VERDICT PROVEN` | 70.351 s [src: qa/judge-dry-run.json#runs.1.steps.2.duration_s] | 0, **106.2 s** |
| `python -m pytest --crdb=none --collect-only -q` | 0 | 30.112 s [src: qa/judge-dry-run.json#runs.1.steps.3.duration_s] | 0, 13.7 s, 9 324 tests |

That recording names the commit it ran against
[src: qa/judge-dry-run.json#source.head], and the migration tree has grown since, so the
page warned you to expect the proof step to take **longer** than the recorded figure. **It
does: 106.2 seconds against 70.351.** The right-hand column is one run on one busy laptop
and is not a benchmark either; it is here because a page that tells you a command works owes
you the evidence that somebody ran it. The full account — what a judge sees on a clean
machine, and where it goes wrong — is
[`docs/submission/FIRST-FIVE-MINUTES.md`](docs/submission/FIRST-FIVE-MINUTES.md).

`just prove` bootstraps a throwaway database, applies the migration chain, and attempts the
same merge three times. This is the run committed under
[`evidence/gate-refusal/`](evidence/gate-refusal/):

```
chain         271/271 applied, 0 failed, 63.094s
PROJECTION    10/10 held · open_blocking 0->1 · gate_epoch 0->1 · outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
VERDICT       PROVEN
```

Re-run on `2026-08-12` from the clean virtual environment above, exit 0, and it printed the
same six lines — `chain 271/271 applied, 0 failed, 55.611s`, the same two SQLSTATEs, the same
`caveats (none)`, `VERDICT PROVEN` — into a new file beside the others in
[`evidence/gate-refusal/`](evidence/gate-refusal/). **Only the timings and the database name
differ, and the script chooses both.**

Three attempts, and the third is the one that matters. A gate that always refuses is a
broken gate, not a safe one. The first refusal is a plain `CHECK` constraint. The second
is the gate catching a *forged projection* — the counter was set to zero out of band and
the merge was refused anyway, because the function re-derives the count instead of
trusting the column. The third is the same history admitted after one signed disposition.

Read the `PROJECTION` line before the refusals. The script inserted one blocking check and
touched nothing else; the database moved the counter from
0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.open_blocking.before] to
1 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.open_blocking.after],
bumped the gate epoch, emitted the CDC row, and projected a severity of
4 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.severity.projected_onto_the_check]
onto a row the client had left at
0 [src: evidence/gate-refusal/proof-20260810T054407Z.json#projection.severity.supplied_by_this_script].
A counter a client writes is a client's opinion. A counter a trigger writes is the database's.

[`docs/release/QUICKSTART.md`](docs/release/QUICKSTART.md) is the long version of the four
commands.

## Read this before you believe any of it

**[`docs/HONESTY.md`](docs/HONESTY.md)** — what is proven, what is synthetic, what is not
built, and where the machine is. Every number in it carries an inline reference to the
file under `qa/` or `evidence/` that produced it, and
`tests/release/test_honesty_is_checkable.py` fails the build when a number and its source
disagree. The short version, because it should not be buried:

* Seven tables in the schema had **no migration at all** — their triggers, views and RLS
  policies were written and their producer never was. The producers have since landed, and
  the committed proof records 271 of 271
  applied [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.applied_count] with
  0 failures [src: evidence/gate-refusal/proof-20260810T054407Z.json#chain.failed_count].
  Read that as a *census*, not a deployment: the applier that produced it continues past
  every failure. The forward-only runner a deployment actually uses has been driven and
  wrote no artefact under `qa/` or `evidence/`, so `docs/HONESTY.md` prints no figure for it
  and neither does this page.
* **The conformance suite had never been run to completion** for the whole of this build —
  against a bare node its cases error rather than skip. A first census now exists,
  [`qa/conformance-census.json`](qa/conformance-census.json), taken against a fully migrated
  schema: of 71 declared cases it records 55 that could not run at all, 6 red and 10 that
  held. `docs/HONESTY.md` still describes the suite as undemonstrated and has not absorbed
  that census yet. A modest first result is a different artefact from no result, and it is
  nowhere near a passing suite.
* The corpus is **authored**, the model transcripts are **recorded cassettes**, and the
  reference-ledger keys are named `NOT-SECRET` because they are — published on purpose so a
  stranger can verify the offline bundle without asking anyone for a credential.
* The test suite is censused **per package, twice** — with no database and with one shared
  node — and every skip is published with the reason string its own fixture wrote. The
  counts, including the target that does not finish at all, are in
  [`qa/test-state.json`](qa/test-state.json). That census **predates the producer migrations
  and has not been retaken**, so it describes a tree that no longer exists.
* Lint and types are **counted, not clean**: frozen ratchets that may fall and not rise, in
  `qa/ruff-ratchet.json` and `qa/mypy-ratchet.json`. The ruff ratchet is **red today**, on a
  wave whose total went down, because it gates per rule rather than on a headline sum.
* Inference runs on **Bedrock in `ap-southeast-2` (Sydney)** while the database is in
  **`aws-ap-southeast-1` (Singapore)**, because `ap-southeast-2` is Advanced-tier only on
  CockroachDB Cloud.
  There is no end-to-end Australian residency; that claim is false here.
  The cross-region hop is unmeasured under load, and **every timing in the demo is a local
  timing** — a single-node CockroachDB in Docker on one laptop.
* **Bedrock genuinely executes, and nothing else on AWS does.**
  [`evidence/deploy/aws-live.json`](evidence/deploy/aws-live.json) records four live calls
  with their AWS request ids — `sts:GetCallerIdentity`, `bedrock:ListFoundationModels`, a
  Titan v2 embedding (1024-d, L2 norm 1.0) and a Claude Haiku 4.5 `Converse` that returned
  `end_turn` — `calls_failed: []`, whole probe under one cent. Lambda, CloudFront, S3, KMS,
  IAM roles and SSM are **DESIGNED**: `terraform apply` has never been run, which is also why
  the demo URL above is `UNRESOLVED`.

---

## The one-sentence version

> An engineer raises a routine, entirely defensible change to a compressor alarm setpoint. The system runs `blame` on the clause. It was written 2013-06-12 by an author who left the company in 2017, with the commit message *"Lowered 150 to 135 after seal fire INC-2013-044 — two contractors burned."* The permit merge is mechanically refused until a named competent person signs a disposition against a thirteen-year-old death.

No shipping permit system can express that, because every one of them is **synchronic** — it gates on the current state of the world. MAINLINE is **diachronic**: it gates on *ancestry*.

## Why this is memory, not workflow

The memory is not a panel next to the transaction. It is a **precondition of the state transition**, enforced as a database invariant under `SERIALIZABLE` — not as a UI nag that can be dismissed.

The memory also has *semantics* rather than being a document store:

- **provenance** — clause → the incident that wrote it
- **ancestry** — a commit DAG, walked, not a "related documents" list
- **severity floors** — a fatality's relevance never decays
- **archival bonds** — recall keyed to an activity taxonomy, not to keywords
- **fixity** — as-documented reconciled against as-operated
- **logged silence** — every precursor the system *declined* to surface is recorded, with its arithmetic

## Architecture in one layer diagram

```
verticals/mainline/   ← the product (FSL-1.1-ALv2)
        │  runs on
        ▼
packages/trappoint-*  ← the substrate: a spec, a SQL template, a conformance suite (Apache-2.0)
        │  enforced by
        ▼
CockroachDB v26.2     ← the memory layer. Constraints, triggers, SERIALIZABLE, C-SPANN vectors,
                        changefeeds, RLS. The refusal happens here, not in application code.
```

### TRAPPOINT — the kernel

The substrate is not a library; it is a **specification with a conformance suite**. One idiom, three steps:

> **PROJECT** — a row-level trigger writes the cross-row fact onto a scalar column of the subject row, derived from an authoritative table, *never from the inserter*.
> **PIN** — a completed transition takes a composite foreign key onto `(subject_id, epoch)`; any new obligation increments the epoch; `ON UPDATE RESTRICT` makes attaching an obligation to a completed transition *physically impossible*.
> **REFUSE** — a plain-column `CHECK` over the projected scalar refuses the write, for every writer, forever.

Four properties make it load-bearing:

| Property | Why it matters |
|---|---|
| The projected counter is a **materialised conflict** | The gate stays welded even if isolation is downgraded to `READ COMMITTED` |
| Refusal is **structurally redundant** | Proven by an unwelding harness: disable the trigger, drop the constraint — one at a time — and the write *still* fails |
| The ledger is **gap-free by compare-and-swap, not by sequence** | `CREATE SEQUENCE` is banned, because sequence updates are not rolled back. A gap therefore *means* tampering |
| The gate is **self-attesting** | `pg_get_triggerdef()` is snapshotted into the ledger on every migration. Nobody quietly weakens the gate that prevents quietly weakening controls |

Every refusal emits a **minimal unsatisfiable subset** and, where computable, the nearest admissible alternative. A gate that only says "no" gets routed around — and an invariant that is routed around is not an invariant.

The second line of `just prove` is that claim under attack rather than at rest:
`mainline.fn_permit_merge_gate` is handed a projected counter that says zero, re-derives
the obligation count for itself, finds one, and refuses with `P0001`. **P2 projections are
enforced, never trusted.**

## Repository layout

| Path | Contents | Licence |
|---|---|---|
| `spec/` | TRAPPOINT specification, invariants `I01–I16`, SQLSTATE contract, wire formats | Apache-2.0 |
| `packages/trappoint-*` | Substrate: SQL templates, gate runtime, offline verifier, recall prefix builder, MCP surface, conformance suite | Apache-2.0 |
| `skills/` | CockroachDB Agent Skills, upstream-PR-shaped | Apache-2.0 |
| `scripts/` | The proof, the doctor, the censuses, the ratchets | Apache-2.0 |
| `verticals/mainline/` | The product: domain lattice, gate service, recall agent, custody relay, console | LicenseRef-FSL-1.1-ALv2 |
| `infra/` | OpenTofu modules and environments | LicenseRef-FSL-1.1-ALv2 |
| `evidence/` | Transcripts, captured tool evidence, and a signed reference ledger any stranger can verify offline | CC-BY-4.0 |
| `qa/` | The counted ratchets and the censuses — every number, and the command that re-derives it | CC-BY-4.0 prose, Apache-2.0 ratchets |
| `docs/` | Architecture decision records, honesty, submission | CC-BY-4.0 |

The import boundaries are enforced by `import-linter` in CI, and they are simultaneously the **layer** boundary, the **licence** boundary, and the **liability** boundary. `.importlinter` contract 1 forbids any `trappoint_*` distribution from importing any `mainline_*` module, which is what makes the Apache-2.0 half genuinely forkable rather than nominally so.

## Verifying without trusting us

[`VERIFY.md`](VERIFY.md) is the three tiers, ordered by how much you have to take on
faith. **Tier 2 is the one that reproduces the refusal above on your laptop** — clone, bring
the node up, run the proof — and it needs no account of ours and no model call. It is the
four commands on this page.

Tier 1 is an offline bundle check with no credential and no network, and `VERIFY.md` records
what it actually returns today: `16 checks | 8 passed | 1 failed | 7 not checked`, **exit
1**. Seven cryptographic checks are unimplemented and one canonicaliser check has gone red on
real drift. It is a genuine offline verification of the Merkle structure and it is **not** a
verified ledger, and that page will not let you read it as one.

Two artefacts are worth opening on their own:

* [`evidence/gate-refusal/`](evidence/gate-refusal/) — a transcript of what one cluster
  did at one instant, with the SQLSTATE, the constraint name, the projection readings
  either side of a single insert, and the caveats the run could not honestly avoid. The
  earlier runs are kept beside the current one on purpose: a document whose credibility
  rests on showing its own movement may not quietly delete where it moved from.
* [`qa/test-state.json`](qa/test-state.json) — passed, failed, errored and skipped per
  package, **with every skip's reason string**, taken twice: once with no database
  available and once against a live node. Rendered as
  [`docs/release/test-state.md`](docs/release/test-state.md).

## Status

Pre-alpha. Under active construction. Design corpus: `ARCHITECTURE.md` and `BUILD_PLAN.md` live in a companion research repository, not this one; they were produced by a 40-agent design operation and hardened by an adversarial review (28 findings) plus an independent feasibility verification.

**The Actions tab is red in places, on purpose, and one of the reds means nothing at all.**
Before drawing a conclusion from a colour, read [`docs/CI-STATE.md`](docs/CI-STATE.md): it
names every lane, separates the reds that report a true incompleteness — seven of sixteen
custody checks unwritten, a reference vertical with no producer, 21 of 30 invariants pending,
no demo to health-check — from the ones whose jobs died in the runner's network before
executing a single check. A red that reports true incompleteness **stays** red here, with a
sharper message.

**Nothing here claims what it cannot prove**, and the claims that are not proven are
listed by name in [`docs/HONESTY.md`](docs/HONESTY.md) rather than left out.

## Licence

The root [`LICENSE`](LICENSE) is **Apache-2.0** — the licence of the substrate, which is the
part of this repository a stranger may fork unconditionally. The tree is multi-licensed by
directory: the table above is the summary, `LICENSES/` holds every licence text, and
[`docs/submission/LICENSING.md`](docs/submission/LICENSING.md) is the full account — including
why `LICENSES/` carries both `FSL-1.1-ALv2.txt` and `LicenseRef-FSL-1.1-ALv2.txt` with
byte-identical contents. The headers in the tree use the bare spelling; REUSE requires the
`LicenseRef-` form; shipping both and publishing the split as a counted number was chosen over
a mass edit of the files that disagree. `REUSE.toml` carries the annotations for files that
cannot hold a header. [`TRADEMARKS.md`](TRADEMARKS.md) governs the names.
