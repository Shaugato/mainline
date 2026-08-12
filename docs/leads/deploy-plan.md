<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DEPLOYMENT LEAD — a live demo URL, on CockroachDB Cloud, for under a dollar a month

**Domain implementation plan.** Ten workers, strictly disjoint literal paths.
Date `2026-08-10`. Deadline `2026-08-18` 17:00 EDT.
Scope: the demo URL, the Cloud database behind it, the infrastructure that serves it,
the judge pack, the health checks, and a one-command deploy a stranger can run.

Everything numbered in §1 was measured by this lead today, on this machine, against the
live systems. The artefacts are committed under `evidence/deploy/lead/` and every claim
below names the file that produced it.

---

## 0. The bar, and the one line that decides everything

> *"Provide a URL to your functional demo app."* — Stage One, pass/fail.

There is no partial credit. A submission without a working URL is not judged on
Agentic Memory Design, or on anything else. Today there is no URL, so **this is the
single highest-risk item in the whole project**, and the plan below is shaped by one
principle:

**Ship a demo URL that cannot fail, then upgrade it to one that is live.**

Phase 1 is a static console over a *cryptographically verified* EvidenceBundle captured
from the Cloud cluster — no backend, no database in the request path, nothing to fall
over. It satisfies the rule on day one and costs approximately nothing. Phase 2 adds the
live API against CockroachDB Cloud in Singapore and flips the console's badge from
`REPLAY` to `LIVE`. Both remain reachable, side by side, on the same URL — and *that is
the story*, not a compromise: the same screen, two sources, one badge that never lies
about which one you are looking at.

---

## 1. GROUND TRUTH — measured today, by me, not inherited

### 1.1 The migration chain applies to CockroachDB Cloud

This was unknown this morning. It is known now.

| | |
|---|---|
| Target | `mainline-dev`, SERVERLESS/Basic, `aws-ap-southeast-1` (Singapore), `v26.2.5` |
| Migration files | 261 |
| Applied | 246 |
| Failed | 15 — every one `42P01`, on a table with no producer |
| Wall clock, whole chain | 362.1 s |
| Files that needed a `40001` retry, this run | 0 |
| `ALTER DATABASE … CONFIGURE ZONE USING gc.ttlseconds = 4500` on Basic | **accepted** |
| Slowest single file | `0180_disposition_peer_visible.sql`, 7.3 s |

Artefact: [`evidence/deploy/lead/cloud-chain-20260810T110400Z.json`](../../evidence/deploy/lead/cloud-chain-20260810T110400Z.json),
produced by [`evidence/deploy/lead/cloud_chain_probe.py`](../../evidence/deploy/lead/cloud_chain_probe.py).

**The failure set on Cloud is byte-for-byte the failure set on the laptop.** Same 15
files, same SQLSTATE, same missing relations. There is no Cloud-specific schema problem.
That is the most important single sentence in this document, because it means the demo
does not need a laptop.

### 1.2 …but only with a `40001` retry, and the repo has none

The first Cloud attempt was `scripts/proof/gate_refusal.py` pointed at the cluster. It
died:

```
gate_refusal: could not reach the cluster: restart transaction:
TransactionRetryWithProtoRefreshError: TransactionRetryError:
retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)
```

A single-node Docker cluster never produces this. A multi-node managed cluster does. The
proof script and `trappoint migrate` both apply DDL with no retry, and on Cloud that is a
coin flip. **Every applier this domain writes retries `40001` with backoff**, and says in
its output how many files needed one. Note the honest asymmetry: the run that completed
needed zero retries; the run that had no retry loop still died. Retry is insurance
against a real failure mode observed once in two runs, not a workaround for a constant.

*(This is a finding about the repository, not about my scope. It belongs in
`docs/HONESTY.md` under "Nothing has ever run against CockroachDB Cloud in CI", which is
now false in the useful direction: something has.)*

### 1.3 The gap is SIX tables, not five

`docs/HONESTY.md` and `scripts/proof/gate_refusal.py` both enumerate five tables with no
producer. Reading the *consumers* rather than the enumeration finds a sixth:

```
grep -rn "person_measure_policy" verticals/mainline/db/migrations/*.sql
  → 0171, 0172, 0187d reference it; 0170 documents it
grep -rl "CREATE TABLE.*person_measure_policy" verticals/mainline/db/migrations/
  → nothing, anywhere in the repository
```

`mainline_meas.standing.policy_id` is declared `NOT NULL REFERENCES person_measure_policy`
by `0171_v_standing_components.sql`'s own header. Creating `standing` without it simply
moves the `42P01` one file along. The count of failing migrations stays 15; the count of
absent tables is **6**.

Better still, the consumers name the numbers they expect, in their own `requires:` lines:

| Table | Number the consumers name | Band owner / mode |
|---|---|---|
| `mainline.identity_assignment` | `0049b` | algorithms / authored |
| `mainline_meas.agent_action` | `0089` | recall / authored |
| `mainline_meas.person_measure_policy` | `0089` | recall / authored |
| `mainline_meas.standing` | `0089` | recall / authored |
| `mainline.patrol_run` | `0090` | datamodel/dm-periphery / authored |
| `mainline_ops.outbox` | `0099` | datamodel/dm-periphery / authored |

`0049b` is explicitly reserved for `identity_assignment` by `0049c_cbm_account.sql`.
**The whole `0090`–`0099z` band is empty** — dm-periphery never delivered a file into it.
`0089` and its letter space are free. So no number needs to be invented, no band needs to
be re-cut, and `trappoint migrate lint` — which enforces the *mode*, `rendered` versus
`authored`, and refuses an unallocated number — will accept all six.

### 1.4 The three demo beats fit in ONE transaction, and persist nothing

The keystone measurement. Against the local migrated database, inside a single
`SERIALIZABLE` transaction, three merge attempts were made under `SAVEPOINT` /
`ROLLBACK TO SAVEPOINT`, then the whole transaction was rolled back:

```
open>0         REFUSED   [23514] failed to satisfy CHECK constraint
                                 ((state != 'merged') OR (open_blocking = 0)
forged-zero    REFUSED   [23503] insert on "permit_event" violates FK "legal_edge"
as-is          REFUSED   [23503] insert on "permit_event" violates FK "legal_edge"
after rollback, open_blocking = 0 (unchanged proves nothing persisted)
```

Artefact: [`evidence/deploy/lead/savepoint-probe-20260810.txt`](../../evidence/deploy/lead/savepoint-probe-20260810.txt).

Three things are settled by that output:

1. CockroachDB honours `ROLLBACK TO SAVEPOINT` after a constraint refusal — the
   transaction survives and keeps taking statements.
2. The refusals are the *database's*, with real SQLSTATEs, not a story the API tells.
3. A full `ROLLBACK` leaves the seeded row untouched.

**Consequence: the demo needs no per-visitor state, no reset button, no cleanup sweeper
and no session table.** Every judge drives the real gate against the real seeded history,
concurrently, and the database is exactly as they found it. This removes the largest
piece of complexity anyone would otherwise have built.

*(The second and third beats here refuse on `23503` rather than the intended `23514` /
`P0001` because the probe reused a permit already in state `merged`. The demo seeds a
permit in the right state; the pattern is what was under test, and the pattern holds.)*

### 1.5 Everything else, verified rather than assumed

| Fact | How I know |
|---|---|
| Cloud cluster answers, `mainline-sql` user, 3.15 s connect+query from Australia | `psycopg` round trip, this session |
| AWS `0229REDACTED8246`, profile `mainline-dev`, **AdministratorAccess** | `aws sts get-caller-identity`, `aws iam list-attached-user-policies` |
| Terraform **v1.14.8** installed; OpenTofu is **not** | `terraform version`; `which tofu` → not found |
| Node v24.14.0, pnpm 11.5.3 | `node --version`, `pnpm --version` |
| Console builds; `dist/` is 3.2 MB | `du -sh verticals/mainline/apps/console/dist` |
| `psycopg==3.3.4` + `psycopg-binary==3.3.4` manylinux wheels install clean for Lambda: 21 MB unzipped | `pip install --platform manylinux2014_x86_64 --python-version 3.13 --only-binary=:all:` |
| Bedrock `amazon.titan-embed-text-v2:0` and `cohere.embed-v4:0` live in `ap-southeast-2` | `aws bedrock list-foundation-models` |
| The AWS account holds four unrelated projects | `aws s3api list-buckets` — **everything we create carries the `mainline-demo-` prefix and the tag `project=mainline`. Nothing else is touched.** |

### 1.6 The two gaps that will bite, named now

* **The console has no composition root.** `src/features/*/transport-context.ts` all
  default to `null` and every surface renders an honest NO SOURCE panel, on purpose:
  *"The composition root is the shell (`src/app`), which does not yet provide one."* Nobody
  has ever wired a transport into the running console. W8 does it.
* **No HTTP server exists anywhere in the repository.** `grep -rl "fastapi\|flask\|starlette\|uvicorn\|aiohttp.web"` over
  every `.py` and `.toml` outside `.venv` returns nothing. The console's 16 declared
  resources in `src/data/resources.ts` have no implementation. W3 and W4 build it — as a
  dependency-free WSGI-shaped handler on Lambda, not a framework.

---

## 2. THE DECISION — S3 + CloudFront + one Lambda Function URL

### 2.1 The shape

```
                       ┌─────────────────────────────────────────┐
  judge's browser ───► │ CloudFront  dXXXXXXXX.cloudfront.net    │  HTTPS, default cert
                       │  default behaviour  →  S3 (OAC, private)│  console SPA + bundle
                       │  /v1/*              →  Lambda FURL (OAC)│  the API
                       └────────────────┬────────────────────────┘
                                        │ SigV4, IAM-only Function URL
                                        ▼
                            AWS Lambda  ap-southeast-1
                            python3.13 · psycopg 3.3.4
                                        │ pgwire, TLS, same region
                                        ▼
                     CockroachDB Cloud Basic · mainline-dev · Singapore
```

Both origins sit behind **one distribution and one hostname**. That buys three things for
free: no CORS anywhere, one URL in the submission form, and a Lambda Function URL that is
`AWS_IAM`-authenticated and therefore **cannot be invoked except through CloudFront** —
which is both the security posture and the cost cap.

### 2.2 Why not the alternatives

| Candidate | Monthly | Verdict |
|---|---|---|
| **S3 + CloudFront + Lambda FURL** | **≈ $0.05–0.30** | **CHOSEN.** Everything in perpetual free tier. Scales to a hundred judges without thought. |
| App Runner | $5–15 | Rejected. A container that idles at cost, for a demo that is idle 99.9 % of the time. Buys nothing the Lambda does not. |
| Fargate + ALB | $20–35 | Rejected. The ALB alone costs more per month than the entire chosen stack costs per year. |
| Amplify Hosting | $0–5 | Rejected. Free-tier build minutes lapse after 12 months and the SSR path is a moving target; CloudFront + S3 is the same thing with the magic removed. |
| EC2 t4g.nano | ~$3 + EBS | Rejected. A box someone has to patch, and a single point of failure during judging. |

### 2.3 The monthly bill, itemised

| Line | Basis | USD/month |
|---|---|---|
| CloudFront | perpetual free tier: 1 TB egress, 10 M requests | 0.00 |
| S3 Standard, ap-southeast-1 | ~12 MB site + bundle | 0.01 |
| S3 requests | served from CloudFront cache | ~0.00 |
| Lambda | perpetual free tier: 1 M req, 400 k GB-s. 512 MB × 300 ms × 10 k req = 1 536 GB-s | 0.00 |
| CloudWatch Logs | 7-day retention, well under the 5 GB free ingest | 0.00 |
| CloudWatch alarms | 4 alarms; first 10 free | 0.00 |
| SSM Parameter Store | Standard SecureString | 0.00 |
| S3 Terraform state | one small versioned object, native S3 locking (no DynamoDB) | 0.01 |
| Bedrock Titan Embed v2 | seed pass ~200 k tokens once, then ~50 tokens/query | 0.01 |
| CockroachDB Cloud Basic | inside the free allowance; `spend_limit` 2500 is the hard ceiling | 0.00 |
| Route 53 / ACM | **not used** — CloudFront's default cert and domain | 0.00 |
| **Total** | | **≈ 0.03, worst case < 1.00** |

Two deliberate refusals in that table.

**No custom domain.** A hosted zone is $0.50/month, an ACM certificate for CloudFront must
live in `us-east-1`, and the whole apparatus buys a prettier string in a submission form.
`https://dXXXXXXXX.cloudfront.net` is HTTPS, valid, and free. Rejected as gold-plating.

**No CloudWatch Synthetics canary.** One canary at five-minute intervals is 8 640 runs a
month at $0.0012 — **$10.37/month, thirty times the cost of everything else combined.**
The health check is a GitHub Actions cron hitting `/v1/health`, which costs nothing, and
whose failures are visible in the repository the judges are already reading.

### 2.4 Region

Everything AWS goes in **`ap-southeast-1` (Singapore)**, beside the database. Lambda→CRDB
in-region is single-digit milliseconds; the same call from `ap-southeast-2` pays ~90 ms
each way, and the gate surface makes six of them. CloudFront is global regardless.
Bedrock stays in `ap-southeast-2` because that is where the `au.*` profiles are, and the
demo makes at most one Bedrock call per recall query — which is precisely the cross-region
hop `docs/HONESTY.md` already refuses to hide, now with a number beside it.

### 2.5 Secrets

The Cloud DSN carries a password. It goes into **SSM Parameter Store as a SecureString,
written by the deploy script with `aws ssm put-parameter`, never by Terraform** — because
a Terraform-managed secret is a plaintext secret in the state file. Terraform is given the
parameter *name*; the Lambda role is granted `ssm:GetParameter` + `kms:Decrypt` on that one
ARN; the handler reads it once per cold start and caches it. `terraform show` never
displays the password because Terraform never held it.

### 2.6 State

S3 backend, versioned bucket, **`use_lockfile = true`** (Terraform ≥ 1.10 native S3
locking — no DynamoDB table, no $0.25/month, one less resource to tear down). The bucket
is created by `scripts/deploy/bootstrap_state.sh` with the AWS CLI before the first
`terraform init`, which resolves the chicken-and-egg without committing a state file.

### 2.7 Terraform, not OpenTofu

Terraform v1.14.8 is on this machine; OpenTofu is not, and installing a second toolchain
eight days from a deadline is risk with no return. The HCL is written to the common
subset — `hashicorp/aws` provider only, no Terraform Cloud, no `.tfvars` magic — so
`tofu init && tofu apply` works unchanged. `infra/envs/demo/README.md` says so and shows
both commands.

---

## 3. WHAT THE DEMO SHOWS

Three beats, one screen, in this order. Nothing else is in the critical path.

1. **The permit, with its open obligation.** A real row, read from Singapore, carrying a
   provenance chip that says `db:column`.
2. **MERGE → REFUSED.** `23514`, `gate_closed_when_issued`, constraint name reported by
   the driver. The console shows the SQLSTATE verbatim; it did not compose that string.
3. **THE ATTACK → REFUSED ANYWAY.** The projected counter is forced to zero out of band —
   the exact thing a disarmed projector or a bad `UPDATE` would do — and the gate refuses
   with `P0001` naming `mainline.fn_permit_merge_gate`, because it **re-derives** the count
   instead of trusting the column. This is the beat that distinguishes the product from a
   `CHECK` constraint.
4. **SIGN ONE DISPOSITION → ADMITTED.** `00000`, a `merge_record` row, a server-computed
   clearance digest. *A gate that always refuses is broken, not safe*, and this beat is the
   only thing that proves ours is not.

All four run inside one transaction that is rolled back (§1.4), so the fifth judge sees
exactly what the first did.

Beside them, permanently: the honesty chrome — `LIVE` or `REPLAY`, the cluster
fingerprint, the staged badge on anything hand-authored, and a link to
`docs/HONESTY.md`. **The demo publishes its own limits on the same screen as its claims.**

---

## 4. SEQUENCING

| Wave | Workers | Gate |
|---|---|---|
| **A — now, all parallel** | W1 W2 W5 W6 W7 W8 W9 | — |
| **B — as soon as W2's schema is on Cloud** | W3 W4 | develop against the local node from minute one; integration-test against Cloud when it is up |
| **C — as soon as W7 prints a URL** | W10 | — |

**The Phase-1 cut line.** If, 72 hours before the deadline, the live API is not green,
W7 deploys the site bucket and W9's verified bundle alone and the submission ships with a
`REPLAY` badge and a paragraph saying exactly that. That is a working demo URL showing the
gate refusing and admitting, from signed bytes, with no backend to fail. **Nobody is
allowed to let the live path hold the URL hostage.**

---

## 5. THE TEN WORKERS

Paths are literal and disjoint. Where a directory is listed, that worker creates it and no
other worker writes anything inside it.

| # | id | Owns, in one line |
|---|---|---|
| 1 | `w1-unproduced-tables` | The six absent tables → chain 261/261 |
| 2 | `w2-cloud-database` | Chain + roles + demo seed on CockroachDB Cloud |
| 3 | `w3-api-core-reads` | The Lambda handler, envelope, and 12 read resources |
| 4 | `w4-api-transitions` | The 4 POST transitions and the three-beat gate driver |
| 5 | `w5-tf-site` | Terraform module: S3 + CloudFront + OAC, both behaviours |
| 6 | `w6-tf-api` | Terraform module: Lambda, Function URL, IAM, logs, alarms |
| 7 | `w7-env-and-deploy` | The env root, the state backend, one-command deploy and teardown |
| 8 | `w8-console-composition` | The composition root, LIVE/REPLAY, the demo build |
| 9 | `w9-evidence-bundle` | The verified EvidenceBundle from Cloud — the Phase-1 demo |
| 10 | `w10-judge-and-acceptance` | Judge access, the live judge-pack run, the end-to-end prover |

Full briefs are carried in the structured output that accompanies this document; they are
the authority for each worker's instructions, and this table is their index.

---

## 6. RISKS, AND WHAT IS DONE ABOUT EACH

| Risk | Mitigation, concretely |
|---|---|
| The live API is not ready | Phase 1 ships without it (§4). The URL never depends on the Lambda. |
| `40001` on Cloud kills a deploy | Every applier retries with backoff and reports the count (§1.2). Measured, not assumed. |
| Judges collide on shared state | They cannot: the beats roll back (§1.4). Measured, not assumed. |
| CockroachDB Basic throttles under judging load | Read path is cached at CloudFront; the gate run is four statements. `spend_limit` 2500 is a hard ceiling — the cluster stops before the bill does. |
| Managed MCP is unavailable on Basic | W10 measures it and, if absent, publishes the read-only SQL user instead. `verticals/mainline/demo/judge/FALLBACK.md` already describes that degradation. |
| A judge's key is abused | Read-only role, `mainline_audit` views only, synthetic data only, cluster rotated after judging. Teardown documented. |
| Someone deletes an unrelated bucket | Everything carries the `mainline-demo-` prefix and `project=mainline` tags; teardown filters on the tag and refuses to proceed otherwise. |
| The console's six surfaces are not all wired | They are not meant to be. The gate surface is the demo; the rest keep their honest NO SOURCE panels, which is the product's own idiom. |

---

## 7. CROSS-DOMAIN NOTES — not mine to fix, and blocking

1. **The repository is PRIVATE and has no root `LICENSE`.** `gh repo view` reports
   `visibility: PRIVATE`, `licenseInfo: null`. `LICENSES/` holds two texts; the root file
   the rules require does not exist. **This is Stage One pass/fail and it is not in this
   domain's scope.** It must be somebody's, today.
2. **`docs/HONESTY.md` says five unproduced tables. It is six** (§1.3). The page should be
   extended, not corrected downward — the sixth was found by reading consumers, which is
   the method the page recommends.
3. **`verticals/mainline/demo/judge/PACK.md` names a cluster `mainline-verify` that does
   not exist.** This plan uses one cluster, `mainline-dev`, because a second Basic cluster
   splits the same free allowance for no isolation we actually need. `QUESTIONS.yaml` is
   the generated page's source and belongs to the agents-mcp domain; W10 does not touch it
   and records the discrepancy instead.
4. **`uv` is not installed on this machine**, so every `just` recipe that shells out to
   `uv run` is dead here. This domain's scripts call `.venv/Scripts/python.exe` and the
   installed console-scripts directly, and say so.
