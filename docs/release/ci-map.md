<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The CI map

**Fifteen workflows. This page is what they prove, so you do not have to open fifteen
YAML files to find out.**

The third column is the one to read. A CI lane that lists what it checks is advertising;
a CI lane that lists what it *does not* check is evidence. Every row below names both,
and where a lane asserts nothing today it says so in the row rather than in a footnote.

Last measured: **2026-08-10**, against CockroachDB v26.2.5 and the checkout at that date.

---

## The five-minute read, in order

If you have five minutes and want to know whether this repository is honest, run them in
this order. Each one answers a different question and only the third needs Docker.

| # | Lane | The question it answers |
|---|---|---|
| 1 | `ci` | Does the code the repository ships type-check, lint, and pass its hermetic tests — with **nothing skipped silently**? |
| 2 | `supply-chain` → job `gate-svc-has-no-model-sdk` | Is the loudest security claim in the product (§8.2, "no model can reach the merge gate") *falsifiable*, and does it currently hold? |
| 3 | `release-proof` | Does the **database itself** refuse a permit merge when a recalled precursor carries no signed disposition? |
| 4 | `db` | Does the reference schema apply to a fresh node whose GC horizon is pinned to Cloud's, and is the fingerprint stable? |
| 5 | `cloud-verify` | Has any of this ever run against a *real managed cluster* — or does the lane admit that it has not? |

---

## Every lane

Durations are the **`timeout-minutes` budget of the longest job**, not observed
wall-clock, except where a row says *measured*. A budget is an upper bound the lane is
allowed to spend; publishing it as though it were a measurement would be the same kind
of small lie this table exists to make impossible.

### The lanes rebuilt or created in this wave

| Workflow | Trigger | What it proves | What it does **not** prove | Budget |
|---|---|---|---|---|
| **`ci`** | push, PR, dispatch | The lockfile describes every distribution on disk; format is clean; no ruff count rose; mypy checks **every** package and none is silently unchecked; the seven import contracts hold and no distribution sits outside all of them; every file names its licence; the hermetic suite passes with cluster tests **skipped by name**; no sequence in any migration; every workflow parses. | Anything requiring a database, a credential, or a network call. No refusal, no fingerprint, no time travel, no TypeScript. Cluster-backed tests are **skipped, not run** — the run log prints the reason for each. | 12 min/job |
| **`db`** | push (paths), PR, dispatch | The reference vertical applies to a fresh node; the schema fingerprint is stable across two attestations; the conformance suite's illegal histories are refused with the SQLSTATEs the spec names — on a node pinned to **`gc.ttlseconds = 4500`**, Cloud Basic's value, asserted by read-back. Also ratchets the image-pin census. | Nothing about Cloud (one node, in-memory store, `--insecure`). Nothing about the MAINLINE merge gate — that is `release-proof`. Nothing multi-node. | 12 min/job |
| **`cloud-verify`** | nightly 17:00 UTC, dispatch | That the schema fingerprint is a property of the **schema** and not of the environment — the only lane with a second environment to compare against. Records Cloud's real `gc.ttlseconds`. | **Nothing at all when `CRDB_CLOUD_DSN` is unset** — and in that case it reports `skipped` with a named reason and a table of what is consequently unconfirmed. It never returns green for an assertion it did not evaluate. Calls no model. | 30 min |
| **`supply-chain`** | push (deps), PR, weekly, dispatch | `uv.lock` is byte-identical after a re-lock; a CycloneDX 1.6 SBOM exists for **all 30 distributions**, reproducible per commit; `pip-audit` finds no advisory against the locked set; and **`mainline-gate-svc`'s resolved dependency closure contains no model SDK**. | The SBOM describes the *Python* graph only — the console has its own (`pnpm run check:licences`). `pip-audit` knows only about published advisories, which is a lower bound on risk, not a clean bill. | 20 min/job |
| **`console`** | push/PR on `apps/console/**`, dispatch | `pnpm run ci` in full: eslint at `--max-warnings 0`, `tsc` twice, `vitest run`, a production `vite build`, bundle budgets (D13), and a dependency-licence audit. The pnpm version on PATH is asserted against `packageManager`. | Nothing about the database or any claim the console *displays*. `vitest` runs against jsdom with no backend; the "re-derives every claim it shows" promise is the Playwright suite, which is **not run here** because it needs a live cluster. | 20 min — *measured green locally at ~2 min on Node 24.14.0 / pnpm 11.5.3, 2026-08-10* |

### The lanes owned elsewhere

Summarised from each workflow's own header. Read the file for the full argument.

| Workflow | Trigger | What it proves | What it does **not** prove | Budget |
|---|---|---|---|---|
| **`release-proof`** | push (paths), PR, dispatch | The central claim, both halves: the database **refuses** a permit merge when a recalled precursor has no signed disposition, **and admits** the same merge once one is signed. Evidence JSON uploaded on pass *and* on fail. | Nothing about Cloud, the console, or model behaviour. One node. | 20 min |
| **`boundary`** | push, PR, dispatch, schedule | The determinism boundary (§8.2) on four independent enforcements in four independent jobs, so one bad regex cannot take out more than one. | The live AWS IAM leg is behind `MAINLINE_BOUNDARY_LIVE_AWS=1` and is **deliberately not set**, per PL-3. E1/E2/E4 read committed OpenTofu plan JSON, not a live account. | no per-job timeout set |
| **`db-schema`** | push, PR, dispatch | The MI ratchet: every `enforced` invariant's owning tests must pass, and a promotion cannot be claimed without them. Kept out of `db.yml` so a promotion owed elsewhere cannot change the red lane's colour. | Not a conformance lane; not a refusal proof. | 30 min |
| **`schema`** | PR, push, schedule, dispatch | The schema-**mutating** suites — migrations and unwelding — which drop constraints and disable triggers, run serially on a disposable container that no other job shares. | Nothing that a shared-cluster suite proves; this lane exists precisely because it cannot share. | 30 min |
| **`custody-chain`** | push, PR, dispatch | K2 in dependency order: canonical bytes → hashes → Merkle tree → signature → anchor → verifier → attack matrix. | Each step is meaningless without its predecessor, which is why the order is the lane. | 25 min |
| **`claims`** | push, PR, dispatch | The arithmetic behind what the repository is entitled to *say*: forbidden sentences, shot-list runtime, voice-over claims, honesty-card freshness. Two jobs assert a check **can fail** (PL-2). | Nothing technical. This lane guards prose. | 6 min |
| **`judge-pack`** | push, PR, dispatch | The Tier-3 questions in `demo/VERIFY.md` are still legal against the live schema — including the ones that must **fail**. | It checks the questions, not the answers a judge will like. | 6 min |
| **`mutation-ratchet`** | nightly, PR, dispatch | Publishes the irreducible delta-false-negative rate per mutation class with Wilson bounds (R-A1). A measured residual risk, not an argued-away one. | It measures a weakness; it does not remove it. The number is named in the honesty card. | 20 min |
| **`nightly-differential`** | nightly, dispatch | Hypothesis differential at 2000 examples × 120 steps against both a pure-Python oracle and a real cluster, compared on outcome **and** constraint name; the READ COMMITTED downgrade differential; 64-way parallel merge. | Too slow for per-push, so a regression can live in `main` for up to a day. | 180 min |
| **`skills`** | push, PR, dispatch | Every shipped skill validates, every script it ships can actually fail, the de-branded tree really is de-branded, and our docs claim no upstream merge we were not given. | Asserts nothing about upstream maintainers, by design (BUILD_PLAN §11). | 20 min |

---

## Facts worth knowing before you trust a green tick

**One place sets up the Python workspace.** `.github/actions/setup-workspace` — uv, the
interpreter, the cache keyed on `uv.lock`, and `uv sync --frozen`. Five lanes use it. It
does *not* run `harden-runner`, because each job's `allowed-endpoints` list is a security
decision that must stay readable at the call site, not a union hidden in a shared file.

**`--frozen` is the load-bearing flag, not `--all-packages`.** CI installs exactly what
`uv.lock` records, which is exactly what a stranger's `uv sync` installs. Until
2026-08-10 that sentence was false: the lockfile listed **7** members against **27**
distributions on disk, so `uv lock --check` and `uv sync --frozen --all-packages` could
not both pass, and every green tick either job had shown was against a workspace that had
stopped describing this repository. It is now 30 and 30.

**Cluster tests skip; they are not deselected.** `ci` runs `pytest --crdb=none`, not
`-m "not requires_cluster"`. A marker filter *deselects*, and a deselected test is
indistinguishable in the report from a deleted one. `--crdb=none` makes each fixture skip
and print its own reason, so `-ra` renders a census of exactly what the lane did not
prove. Measured: the testkit subset gives 26 passed, 2 skipped, **3.62 s** — against a
full-suite run on 2026-08-10 that started **thirteen** private CockroachDB containers,
killed the host node, and *wedged* rather than failing.

**The version constant is asserted, not restated.** `db.yml` reads the CockroachDB image
from `compose.yaml` via `trappoint migrate image` and refuses to contain a version
literal anywhere — including in a comment. It also ratchets a repository-wide census;
today, outside `compose.yaml` and the testkit that owns the pin, there are **34**
occurrences of the floating `latest-` tag and **21** restatements of the version. Those
numbers may fall. CI refuses to let them rise.

**Local is the *easier* exam, so `db` makes it harder.** A fresh single-node cluster
defaults to `gc.ttlseconds = 14400`; CockroachDB Cloud Basic is **4500**. A time-travel
assertion that passes at 14400 may simply have read a version Cloud would already have
collected. `db.yml` pins 4500 before any test and asserts it by read-back.

**The database and the models are in different countries.** The cluster is CockroachDB
Cloud Basic in **Singapore**; inference is AWS Bedrock in **ap-southeast-2, Sydney**.
Every embedding call on a recall path crosses that gap, and Bedrock Rerank is not
available in ap-southeast-2 at all. `cloud-verify` records this in its step summary on
every run, including the runs where it skips.

---

## What no lane covers

Stated here rather than discovered later.

* **The console's browser suite.** `pnpm run test:browser` (Playwright + axe) needs a
  live backend and is not in `console.yml`. The console's central promise — that it
  re-derives every claim it displays — is therefore **not** asserted in CI.
* **Live AWS.** No lane authenticates to AWS. `boundary`'s IAM leg reads committed
  OpenTofu plan JSON; the live `simulate-principal-policy` call is gated off (PL-3).
* **Multi-node CockroachDB.** Every lane except `cloud-verify` uses one node. Range
  splits, rebalancing and cross-node contention are unexercised locally.
* **`evidence/sbom/` is generated, not committed.** `boundary.yml` gates on that path.
  `supply-chain.yml` produces the tree and uploads it as the `sbom-cyclonedx` artifact,
  and emits a `::notice` saying the path is untracked — so the gate is visible as a gate
  on nothing until somebody decides to commit it.
* **`actionlint` has never been run on the author's machine.** It is not installed there.
  The five rebuilt workflows were validated locally by an equivalent checker (YAML shape,
  `needs` graph, `needs.*.outputs.*` resolution, expression contexts, duplicate ids,
  local-action existence, and `bash -n` over every `run:` body), which was itself proven
  by planting seven defects and confirming it went red on all of them. That is weaker
  than `actionlint`, which also runs shellcheck. The `workflows` job in `ci.yml` runs the
  real thing on every push.
