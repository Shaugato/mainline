<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Chapter 4 — The map: what is where, and why it is split that way

*You are here: chapter 4 of 5. Front door: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md).
Linked terms are defined in [`GLOSSARY.md`](GLOSSARY.md).*

Chapter 3 ended with an obligation that came from a real incident, and said *"and every one
of those lives somewhere in the tree"*. This chapter is that tree. It is a map with an
argument in it: the split is not tidiness, it is the thing that makes one of our claims
falsifiable.

---

## 1 · Sixty seconds: two halves and one wall between them

Think of a workshop with two rooms.

**The first room holds general-purpose tooling** — a specification, SQL templates, a
migration runner, an offline verifier, a test harness. None of it knows what a safety
permit is. Anyone may take that room away, build something completely different with it,
and never speak to us again. It is Apache-2.0.

**The second room holds the actual product** — MAINLINE, a permit-to-work system for
industrial sites. It knows about scaffolds and confined spaces and the people who sign for
them. It is source-available under a licence that becomes Apache-2.0 later.

**Between the rooms there is a wall with a door that only opens one way.** The product may
reach into the toolkit. The toolkit may not reach into the product. That direction is the
entire point: if the toolkit reached back, then "you can take the toolkit and go" would be
false, because the toolkit would not build without the product.

The wall is not a policy note. It is a program that runs on every build and fails it. That
program is `import-linter`, its rules live in `.importlinter`, and the rule that draws this
wall is **contract 1** — `.importlinter:114`, `name = 1. The Apache substrate never imports
the FSL vertical`.

The rest of this chapter is what is in each room, and what happens at the wall.

---

## 2 · One boundary doing three jobs

`import-linter` is a build-time checker. It reads every Python file in the repository,
builds the real graph of what imports what, and fails the build when an import crosses a
line the configuration forbids. The configuration is one file, `.importlinter`, holding
**seven contracts** over **twenty-nine root packages** (`.importlinter:64–96`).

Contract 1 lists fourteen substrate distributions as *sources* — every one of them the name
of a directory under `packages/` — and twenty vertical modules as *forbidden*
(`.importlinter:117–152`). `allow_indirect_imports = False` means a reach through a helper
counts, which is the shape this failure actually takes.

The same line does three jobs at once:

| It is the … | Because … |
|---|---|
| **layer** boundary | the substrate is general and the vertical is specific; below the line nothing knows what a permit is. |
| **licence** boundary | above the line is `LicenseRef-FSL-1.1-ALv2`; below it is Apache-2.0. An Apache file importing an FSL file makes the Apache half unbuildable on its own, and "forkable" becomes a word rather than a property. |
| **liability** boundary | the [gate](GLOSSARY.md#gate) — the database objects that refuse an illegal write — is downstream of nothing that can reach a language model. Contracts 2 and 5 assert that separately, over the same graph. |

Each of the seven contracts protects one sentence said elsewhere in the repository.
`.importlinter:16–46` gives the file's own words; the short version:

| # | Contract name in the file | The sentence it keeps true |
|---|---|---|
| 1 | `licence-boundary` (`:114`) | the substrate is Apache-2.0 and forkable |
| 2 | `no-model-in-kernel` (`:174`) | no model SDK is importable from the migration runner or the [conformance suite](GLOSSARY.md#conformance) |
| 3 | `verifier-minimal` (`:219`) | the canonicaliser an opposing expert re-implements has one dependency |
| 4 | `no-blanket-retry` (`:257`) | a refusal is attempted exactly once, ever — no `tenacity`-style decorator anywhere |
| 5 | `gate-service-model-free` (`:324`) | no model can reach the merge gate, directly or transitively |
| 6 | `testkit-forkable` (`:368`) | the test harness survives a fork that deletes `verticals/` |
| 7 | `verifier-offline` (`:416`) | the offline verifier imports no database driver and no network client |

**A caveat the file states about itself, kept here rather than smoothed over.** Import-linter
skips a forbidden name that does not resolve to anything, so a contract can list a module
that has not been written yet and say nothing about it (`.importlinter:104–106`). Four such
names have no source on disk today; §8 names them rather than leaving them to be discovered.

---

## 3 · The tree, room by room

Every directory below was listed in this session, and every member named is one that was in
the listing. The licence column follows `README.md:400–412` and `REUSE.toml`, which is the
machine-readable map a checker parses.

### 3.1 · `spec/` — the normative substrate specification · Apache-2.0

The written contract the substrate has to satisfy: `TRAPPOINT-SPEC.md`, `errors.md`,
`CHANGELOG.md`, `VERSIONING.md`, and five subdirectories — `invariants/` (16 files, one per
invariant `I01`–`I16`), `wire/` (8), `custody/` (7), `binding/` (3), `conformance/` (2).

Plain version: this is where the rules are written down in English before any of them exist
as code. A rule here without a mechanism under `packages/` is a rule nobody enforces, which
is why the invariant files each carry a **NOT CLAIMED** section.

### 3.2 · `packages/` — the substrate, 14 distributions · Apache-2.0

[TRAPPOINT](GLOSSARY.md#trappoint) is the substrate: a specification, deterministic SQL
templates, and a conformance suite. Eleven of these fourteen are `trappoint-*`; three are
`mainline-*` and are explained below.

| Distribution | What it is, in its own `pyproject.toml` description |
|---|---|
| `trappoint-core` | the gate client: one explicit `SERIALIZABLE` transaction, a retry loop that retries `40001` and nothing else, a typed refusal carrying the constraint name |
| `trappoint-sql` | the render engine: deterministic SQL from kernel templates plus a vertical binding |
| `trappoint-migrate` | forward-only schema migration with a lock table, a dirty marker, and a gap-free attestation chain |
| `trappoint-conformance` | the runner that asserts illegal histories against an exact [SQLSTATE](GLOSSARY.md#sqlstate) and an exact exhibit name |
| `trappoint-model` | a pure-Python oracle for the merge gate, plus a differential that runs generated operations against both the oracle and a real cluster |
| `trappoint-diagnose` | the [MUS](GLOSSARY.md#mus) and [NAA](GLOSSARY.md#naa) of a refusal, computed with the database's own constraint engine as the oracle |
| `trappoint-jcs` | RFC 8785 [canonicalisation](GLOSSARY.md#canonicalisation) — one fixed byte form, so two machines hashing it agree |
| `trappoint-ledger` | the tamper-evidence log: RFC 6962 Merkle tree, signed checkpoints, receipts |
| `trappoint-verify` | the offline verifier: given an exported segment and a signed root, recompute and answer, on a laptop, with no network |
| `trappoint-recall` | the recall evaluation harness and its metrics |
| `trappoint-testkit` | one CockroachDB for the whole test session, and a `--crdb=none` that turns a wedged machine into a skip with a reason |
| `mainline-agentkit` | the Bedrock call runtime — schema-constrained, `au.*`-only, cassette replay |
| `mainline-boundary` | four separately-runnable proofs that no model can reach the merge gate (IAM, network, code, egress) |
| `mainline-mcp` | a typed client for CockroachDB's Managed MCP Server, with hard limits expressed as types |

**Why three `mainline-*` names sit under an Apache-2.0 substrate directory.** They are
Apache-2.0 and they are MAINLINE domain knowledge, which is exactly why contract 6 forbids
`trappoint-testkit` from importing them: contract 1 permits them, because they are not FSL,
and a second vertical inheriting the test harness does not want them
(`.importlinter:364–367`).

### 3.3 · `verticals/mainline/` — the product · LicenseRef-FSL-1.1-ALv2

A [vertical](GLOSSARY.md#vertical) is a product built on the substrate. This one is
permit-to-work. Source-available under the Functional Source License 1.1 with an Apache-2.0
future grant (`REUSE.toml:184–195`); both `FSL-1.1-ALv2.txt` and
`LicenseRef-FSL-1.1-ALv2.txt` ship in `LICENSES/` with byte-identical text.

**`verticals/mainline/packages/` — 16 distributions.**

| Distribution | What it is |
|---|---|
| `mainline-domain` | the algorithms domain: CANONHOLD, ANCHORLOCK, DIRECTRIX, CATSEAL, DELTALATTICE, CBM |
| `mainline-gate-svc` | the only process that calls `mainline.merge_permit` — one transaction, one `CALL`, a dependency closure with no model in it |
| `mainline-archivist` | ingest and appraise: every field of an event row is a coded fact, a verbatim span, or a capped model rating that cannot arm the gate |
| `mainline-cartographer` | the [blame](GLOSSARY.md#blame) resolver — resolves a clause's blame pointer, proposes edges that can never block |
| `mainline-corpus` | the seeded, model-free, network-free body of documents every recall and blame claim is measured against |
| `mainline-recall-agent` | model providers for recall (embeddings, a listwise judge), offline-first |
| `mainline-recall-fleet` | the fleet binding: one wire, one register, one ledger row |
| `mainline-delta-oracle` | the independent semantic opinion on a clause edit, physically separated from the code that decides |
| `mainline-cherrypick` | cross-site lesson propagation — only tightenings travel, and a resolution is proposed, never auto-applied |
| `mainline-sequencer` | the lease-CAS singleton ledger sequencer and the receipt sink |
| `mainline-anchor` | per-checkpoint anchor fanout: beacon, KMS signature, S3 Object Lock, RFC 3161 timestamps, external witnesses |
| `mainline-custody-patrol` | [custody](GLOSSARY.md#custody) of the custodian — periodic attestations about the platform the ledger sits on |
| `mainline-fixity` | as-documented versus as-operated, compared through the same lattice, with `UNKNOWN` kept first class |
| `mainline-quarantine` | the six-layer prompt-injection posture, as executable controls |
| `mainline-mutation` | the mutation ratchet: KILL/SURVIVE catalogues and a Wilson-bounded residual-risk number |
| `mainline-steward` | every scheduled ops run becomes one hashed attestation row |

`mainline-corpus` has source but **no `pyproject.toml`**, so it is not an installable
distribution and cannot be a root package for the linter. It is registered instead through
contract 1's forbidden list, and `.importlinter:58–62` records both the reason and the
condition under which it joins.

**`verticals/mainline/apps/` — 3 applications.**

- `console/` — the browser front end (Vite, TypeScript). Two HTML entry points, §7.
- `demo-api/` — the Python package `mainline_demo_api` that the deployed Lambda runs; 18
  modules including `app.py`, `gate_run.py`, `cr_gate_run.py`, `reads.py`, `health.py`,
  `refusal.py`, `static_site.py`.
- `steward/` — a container image, its `entrypoint.sh`, `schedules.yaml`, prompts and
  runbooks.

**`verticals/mainline/db/` — the schema.** `migrations/` (271 files, §4), plus `seeds/`,
`invariants/`, `queries/`, `ext/`, `demo/`, `evidence/`, and three declarative files:
`GRANTS.yaml`, `RLS-MATRIX.yaml`, `migrations.allocation.toml`. `migrations.lock.json` is
the runner's lock state.

### 3.4 · `skills/` — CockroachDB Agent Skills · Apache-2.0

Two authored skills — `designing-diachronic-gates/` and
`designing-vector-recall-prefixes/` — plus `upstream/`, which holds an upstream-PR-shaped
contribution, and `validate-spec.py`.

**These are DESIGNED, not exercised.** The census says so and this page does not upgrade it:
`crdb_agent_skills`, verdict `DESIGNED`, basis *"two skills are on disk, each shipping an
executable assertion script; neither script's run is captured under `evidence/`, so they are
shipped and not evidenced"* [src: evidence/tool-usage/crdb-features.json#rows.crdb_agent_skills.verdict_basis].

### 3.5 · `infra/` — OpenTofu / Terraform · LicenseRef-FSL-1.1-ALv2

`modules/` holds four modules — `demo-api/`, `demo-site/`, `evidence-store/`, `cost-guard/`,
each `main.tf` + `variables.tf` + `outputs.tf` + `versions.tf` with a long `README.md`.
`envs/` holds two environments, `demo/` and `evidence/`; `policy/custody/` holds Rego policy.

### 3.6 · `evidence/`, `qa/` and `docs/` — where every number comes from · CC-BY-4.0 prose

`evidence/` holds machine-written transcripts: `chain/`, `gate-refusal/`, `deploy/`,
`demo/`, `tool-usage/`, `aws/`, `ccloud/`, `producers/`, `mcp/`, `mutation/`, `provenance/`,
`reference-ledger/`, `ci/`, `qa/`, `custody-nemesis-run.json`, `CUSTODY_ATTACK_MATRIX.md`.
`qa/` holds the counted ratchets and censuses — `test-state.json`,
`conformance-census.json`, `ruff-ratchet.json`, `mypy-ratchet.json`, `judge-dry-run.json`
and the JUnit XML files behind them. `docs/` holds the prose, including this page and the
dense layer-3 corpus: `HONESTY.md`, `CI-STATE.md`, `TOOL-USAGE.md`, `deploy/RUNBOOK.md`.

The convention that makes the whole document checkable: **a bare number carries
`[src: <path>#<json-pointer>]` into `evidence/` or `qa/`.** The `qa/` ratchets are
Apache-2.0; the prose in all three trees is CC-BY-4.0.

---

## 4 · The migration chain: two numbers that are not interchangeable

There are **271** `.sql` files under `verticals/mainline/db/migrations/`, from
`0001a_schema_mainline.sql` to `0199_exposure_receipt_fk_silence.sql`
[src: evidence/chain/chain-20260810T062542Z.json#tree.files_on_disk] — re-counted by listing
the directory in this session: 271 files, 271 entries, nothing else lives there.

Two different programs have run that stream, and they answer two different questions.

**The census applier continues past every failure.** It exists to survey the whole stream:
what would each file do, given the chance? A failure does not stop it. Its own artefact says
so — *"CONTINUING PAST FAILURES so that `failed` is a census of the whole stream and not the
first stop"* [src: evidence/deploy/chain-261.json#$comment]. The gate proof runs a second
one, inside `scripts/proof/gate_refusal.py`.

**The forward-only runner halts on the first refusal.** This is `trappoint migrate up`,
written by `scripts/chain/apply_chain.py` into its artefact, and it is what a deployment
uses. Halting is correct for a deployment and useless for a survey: everything below the
halt is never executed, so the census's total says nothing about whether a deployment would
have worked.

Confusing the two is not hypothetical — this repository published the census number as
though it were the deployment number, and `docs/HONESTY.md:112–137` keeps the correction
rather than deleting the mistake.

| | census applier, continue-on-error | forward-only runner, `trappoint migrate up` |
|---|---|---|
| Files given | 271 [src: evidence/deploy/chain-261.json#files] | 271 [src: evidence/chain/chain-20260810T062542Z.json#result.files] |
| Applied | 271 [src: evidence/deploy/chain-261.json#applied] | 271 [src: evidence/chain/chain-20260810T062542Z.json#result.applied] |
| Failed | 0 [src: evidence/deploy/chain-261.json#failed] | 0 [src: evidence/chain/chain-20260810T062542Z.json#result.failed] |
| Left dirty | not a concept it has | `false` [src: evidence/chain/chain-20260810T062542Z.json#result.dirty] |
| Versions forced past a failure | not a concept it has | 0 [src: evidence/chain/chain-20260810T062542Z.json#operation.forced_versions] |
| Attestation head ordinal | none written | 271 [src: evidence/chain/chain-20260810T062542Z.json#attestation.head.ordinal] |
| Wall clock, seconds | 46.35 [src: evidence/deploy/chain-261.json#wall_clock_seconds] | 2724.962 [src: evidence/chain/chain-20260810T062542Z.json#wall_clock_seconds] |

Both readings are on the same pinned local node, `CockroachDB CCL v26.2.5`
[src: evidence/chain/chain-20260810T062542Z.json#cluster.version]. Nearly all of the
fifty-nine-fold time difference is the runner's `--attest each` mode: a schema fingerprint
recomputed twice and compared after every statement
[src: evidence/chain/chain-20260810T062542Z.json#operation.attest_meaning]. A deployment
that wants the attestation chain pays for it.

**Two things the runner does that no census reaches.** It writes the attestation chain — 272
rows including genesis [src: evidence/chain/chain-20260810T062542Z.json#attestation.rows] —
and it asserts the grants matrix from `GRANTS.yaml`: 112 statements applied
[src: evidence/chain/chain-20260810T062542Z.json#grants.statements_asserted] and 11 skipped
because the object they grant on does not exist
[src: evidence/chain/chain-20260810T062542Z.json#grants.statements_skipped]. Those eleven
relations are named in the artefact and none of them blocks a migration.

**The earlier reading is kept, and it is worse.** Before the seven missing producers landed,
the census over a 261-file tree read 246 applied and 15 failed
[src: evidence/gate-refusal/proof-20260810T004200Z.json#chain.applied_count,
evidence/gate-refusal/proof-20260810T004200Z.json#chain.failed_count,
evidence/gate-refusal/proof-20260810T004200Z.json#chain.files], every failure a `42P01`
("relation does not exist"), and the forward-only runner against that same tree halted at
`0121_trg_check_materialised` and left the version dirty. That artefact is still in the tree.

---

## 5 · The deployed shape

One origin. A judge's browser talks to exactly one hostname, and that hostname is an **AWS
Lambda Function URL** — a URL AWS attaches directly to a function, with no API gateway and
no CDN in front of it.

| Piece | What it is | Where it is defined |
|---|---|---|
| Origin | `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`, `authorization_type = NONE` | `docs/deploy/RUNBOOK.md:24–49` |
| Runtime | AWS Lambda, `python3.13`, `arm64`, running `mainline_demo_api` | `infra/modules/demo-api/main.tf` |
| Static assets | the console SPA and the evidence bundle travel **inside the Lambda package** — no S3 in the request path | `docs/deploy/RUNBOOK.md:54–57` |
| Database credential | read once per cold start from an SSM parameter — an AWS Systems Manager Parameter Store entry — at `/mainline/demo/cockroach_dsn`, signed with SigV4 out of `hashlib` and `hmac` rather than by importing `boto3` | `infra/envs/demo/variables.tf:321`; `…/demo-api/src/mainline_demo_api/db.py:17–30` |
| Database | CockroachDB Cloud **Basic**, database `mainline_demo`, region `aws-ap-southeast-1` (Singapore) | `docs/deploy/RUNBOOK.md:48`; cluster row at `docs/deploy/cloud-database.md:31` |
| Transport | pgwire over TLS, same region as the function | `docs/deploy/RUNBOOK.md:46` |

Its health route answered `ok: true`, database `mainline_demo`, deploy chain 271 of 271
files, cluster `CockroachDB CCL v26.2.5`
[src: evidence/demo/live-beats.json#world.health], on a run with
`target_is_local_emulator: false` and `credentials_used: "none"`
[src: evidence/demo/live-beats.json#target_is_local_emulator]. Three things fall out of the
single origin, and they are engineering choices rather than selling points: no CORS to
configure, one resource to be wrong about, and one hostname serving both the live source and
the recorded-replay source.

### 5.1 · CloudFront is BLOCKED, not declined

A content delivery network in front of the origin is written, planned, and **cannot be
created on this account**. That distinction matters: we did not decide against it, AWS
refused it. A real `terraform apply` on `2026-08-10` created the origin access control and
the bucket, then stopped:

```
Error: creating CloudFront Distribution: operation error CloudFront:
CreateDistributionWithTags, https response error StatusCode: 403,
RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
Your account must be verified before you can add new CloudFront resources.
To verify your account, please contact AWS Support and include this error message.
```

That block is verbatim from `docs/deploy/RUNBOOK.md:1541–1545` (Appendix A), kept with its
`RequestID` because redacting it would make the evidence unverifiable. It is not a Terraform
problem, an IAM problem or a module problem: the same refusal comes from a bare AWS CLI call
with a three-field distribution config and no Terraform anywhere
(`docs/deploy/RUNBOOK.md:1553–1555`), from an identity holding `AdministratorAccess`.

The hold is on creating **new** CloudFront resources; a distribution predating it continues
to serve, and this account has one that belongs to a different project in a different region
(`docs/deploy/RUNBOOK.md:1571–1594`). `infra/envs/demo` keeps `module.site` behind
`var.enable_cloudfront`, default `false`. Nothing has to be redesigned if Support lifts it.

The runbook is written as though the hold never clears, because a runbook that assumes a
support queue will answer in time is not a runbook (`docs/deploy/RUNBOOK.md:31`).

---

## 6 · Which CockroachDB tools and which AWS services — the census answers, not this page

Two machine-written censuses hold the verdicts. This section quotes them and promotes
nothing. **The authority is a command, not a paragraph:**

```bash
python scripts/submission/capture_tool_evidence.py --check   # non-zero if anything is stale
```

It is standard-library only, takes no network and no credential, and re-derives both files
from the tree (`docs/TOOL-USAGE.md:22–28`). If this page and the JSON disagree, the JSON
wins. The verdict vocabulary is the censuses' own: **EXERCISED** — *"it ran, and a committed
artefact or a check in this repository records the result"*; **DESIGNED** — *"the code or
configuration is complete and on disk; nothing recorded has run it end to end"*;
**NOT-AVAILABLE** — *"checked on this platform and absent; no dependency was taken on it"*.

**CockroachDB** [src: evidence/tool-usage/crdb-features.json#totals] — 14 rows: 12
`EXERCISED`, 2 `DESIGNED`, 0 `NOT-AVAILABLE`; counted as 4 tools inside which 10 engine
features are separately accounted, because counting a feature as a tool to clear a bar is
the arithmetic this repository exists to refuse (`docs/TOOL-USAGE.md:10–15`).

| Verdict | Rows |
|---|---|
| `EXERCISED` | the database itself at `v26.2.5`; `SERIALIZABLE` isolation; PL/pgSQL triggers and functions; named `CHECK` constraints as the refusal exhibit; the C-SPANN vector index; `AS OF SYSTEM TIME`; follower reads; row-level security; `SHOW CREATE` / `pg_get_functiondef`; `crdb_internal`; CockroachDB Cloud and the `ccloud` CLI; the Managed MCP Server |
| `DESIGNED` | `CHANGEFEED` (change data capture out of the outbox); Agent Skills |

Two of those rows carry a measured caveat inside the census and are worth reading there
rather than here: the vector index is chosen by the planner only when named explicitly
[src: evidence/tool-usage/crdb-features.json#rows.crdb_vector_index.verdict_basis], and
`CHANGEFEED` reads `DESIGNED` because no changefeed has ever been created on any cluster in
this project [src: evidence/tool-usage/crdb-features.json#rows.crdb_changefeed.verdict_basis].

**AWS** [src: evidence/tool-usage/aws-services.json#totals] — 12 rows: 6 `EXERCISED`, 5
`DESIGNED`, 1 `NOT-AVAILABLE`.

| Verdict | Rows |
|---|---|
| `EXERCISED` | Bedrock (Claude inference via `au.*` profiles); Bedrock embeddings (Titan v2, Cohere embed v4); Lambda; CloudWatch; IAM; SSM Parameter Store |
| `DESIGNED` | S3 + Object Lock; KMS; CloudTrail; CloudFront + Origin Access Control; EventBridge |
| `NOT-AVAILABLE` | Bedrock Rerank |

Three scopings the censuses state and this page repeats without softening:

- **Bedrock executes in this repository and NOT in the demo request path.** The `EXERCISED`
  verdict rests on live calls from `mainline-agentkit`, recorded under `evidence/aws/`. The
  deployed handler's whole third-party closure is `psycopg`, asserted by its own suite
  (`…/apps/demo-api/src/mainline_demo_api/db.py:29–30`; `…/demo-api/tests/test_envelope.py`).
- **CloudWatch's basis is narrower than its title**: *"METRICS READ, NOTHING PROVISIONED"*
  [src: evidence/tool-usage/aws-services.json#rows.aws_cloudwatch.verdict_basis].
- **There is no end-to-end Australian residency.** Inference runs on Bedrock in
  `ap-southeast-2` (Sydney); the database is in `aws-ap-southeast-1` (Singapore). The hop
  between them is unmeasured under load (`README.md:293`).

---

## 7 · The doors a human actually opens

| Entry point | What it is | State |
|---|---|---|
| `GET /` on the demo URL | the console single-page app, served from inside the Lambda package | live |
| `GET /v1/health` | liveness plus the cluster fingerprint | live |
| `GET /v1/*` | the read resources — subjects, permits, blocking checks, recall runs, clause ancestry | live |
| `POST /v1/demo/gate-run` | the four beats in one transaction, rolled back — nothing persists | live |
| `/operator.html#/permit` | the site supervisor's screen | **in the tree, not on the deployed origin** |
| `/operator.html#/change` | the safety engineer's screen | **in the tree, not on the deployed origin** |

`operator.html` is a second HTML entry point in the same Vite build. The file is
`verticals/mainline/apps/console/operator.html` and the router is
`verticals/mainline/apps/console/src/operator/route.ts` — both listed in this session,
alongside the route directories `permit/`, `change/`, `hazard/`, `issue/`, `kernel/`,
`chrome/` and `boot.ts`.

**It is not on the deployed origin, and clicking will not tell you that.** Measured
`2026-08-15`: `GET /operator.html` on the live URL returns the console shell byte-for-byte
identical to `GET /` — the single-page fallback, which is what a not-yet-deployed second
entry point looks like (`README.md:66–70`). The API half is live; the screens ship when the
orchestrator redeploys.

`verticals/mainline/apps/steward/` has no HTTP door at all. Its schedule is a container
entrypoint today, not an EventBridge rule — which is exactly why the EventBridge census row
reads `DESIGNED`
[src: evidence/tool-usage/aws-services.json#rows.aws_eventbridge.verdict_basis].

---

## 8 · Findability audit: names on the map with nothing behind them

Every component named anywhere in this architecture document should be openable at a path.
Four names are not, and all four are in `.importlinter`:

| Name | Where it appears | Status on disk |
|---|---|---|
| `mainline_console_api` | contract 1 (`.importlinter:137`), contract 6 (`:379`) | no source directory exists |
| `mainline_custody_relay` | contract 1 (`:140`), contract 6 (`:382`) | no source directory exists |
| `mainline_ingest` | contract 1 (`:145`), contract 6 (`:387`) | no source directory exists |
| `mainline_provisioner` | contract 1 (`:147`), contract 6 (`:390`) | no source directory exists |

Searched by `find . -type d -name <name>` over the tree excluding `.venv/` and `.git/`: zero
hits for each. This is **not a defect**, and the configuration says so before anyone asks:
*"Forbidden entries that do not exist yet are skipped by import-linter rather than erroring,
so this list is written for the whole vertical up front and the contract starts enforcing
each package the day it lands"* (`.importlinter:104–106`).

The honest consequence, stated plainly: **a contract listing a module that does not exist
asserts nothing about that module.** It is a reservation, not an enforcement. `README.md:408`
describes the custody relay as part of the vertical; today that name is a reservation in the
linter and not a directory.

One further name resolves, but not as a distribution: `mainline_corpus` has source at
`verticals/mainline/packages/mainline-corpus/src/mainline_corpus` and no `pyproject.toml`,
so it is registered through contract 1's forbidden list rather than as a root package (§3.3).

---

## 9 · And here is what is missing from that map

Everything above is a thing you can open. That is the easy half. The map is honest about
where its own boxes are, and dishonest by omission unless it also says which boxes are
outlines: a skill that has never been run as a skill, a changefeed that has never been
created, seven custody checks that were never written, a conformance suite whose first
census is mostly cases that could not run at all.

**Chapter 5, [`05-what-is-not-built.md`](05-what-is-not-built.md), enumerates every one of
them** — with the artefact that records each gap, and the reason each is still on the page
rather than deleted.
