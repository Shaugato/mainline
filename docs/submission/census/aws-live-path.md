<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CENSUS — AWS in the live request path

**Worker:** W1 · **Date:** 2026-08-16 · **Tree:** `c951558` (the plan cites `5f57146`; sibling
workers have since committed, and nothing in this file depends on the difference) ·
**Plan:** [`../feature-census-plan.md`](../feature-census-plan.md), rulings **R2** and **R4** binding.

**Scope, and the boundary is the whole point.** This file lists the AWS services that
**execute when a stranger sends one HTTP request to the demo origin**, and nothing else.
An AWS service that this repository uses somewhere else, or that Terraform applied but no
request touches, is **not in this file** — it belongs to W2. §4 names each one that was
considered and handed over, so that the exclusion is visible rather than merely absent, and
closes with the two **evidence artefacts** that look like live-path proof and are not (§4.6, §4.7).

**The origin:**

```
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

**Every command in this file was run today from this workstation and every "observed" block
is pasted output, not a prediction.** Nothing here required AWS credentials: the whole census
is checkable by a stranger with `curl`, and the repository half with `grep`. Where a claim
*cannot* be settled without an account, the row says so in as many words (§2.5, §6).

---

## 0. THE ONE-SENTENCE ANSWER

Five AWS services run on the path of a single unauthenticated request: **Lambda** executes the
handler, a **Lambda Function URL** is the hostname and the reason the demo is free to access,
**IAM** supplies the role credentials the handler signs with, **SSM Parameter Store** hands back
the database DSN over a **hand-rolled SigV4 request that does not use boto3**, and **CloudWatch
Logs** is the function's declared log destination and takes the invocation record.

The first four are **entailed by a single anonymous 200** (§1.2). CloudWatch is the one row a
stranger cannot fully close: they can hold the AWS-issued invocation id, and reading the event
itself needs the account (§2.5). The sixth candidate, **KMS**, is folded into §2.4 with its one
unverified premise stated rather than claimed.

---

## 1. WHAT A JUDGE CAN GET FROM THIS ORIGIN WITHOUT AN ACCOUNT

Two of these cost one request each and nobody has written them down; the third costs nothing at all,
because it is already committed to the repository. All three are quoted verbatim.

### 1.1 `GET /v1/` — a 404 that is a complete route census

The API declines an undeclared path by **enumerating every resource it does declare**. One
request, no credentials, and the reader has the whole public surface — 17 routes.

```console
$ curl -s https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/ | python -m json.tool
{
    "error": {
        "declared": [
            "/v1/audit",
            "/v1/change-requests/{cr_id}",
            "/v1/checks/{check_id}/disposition",
            "/v1/clauses/{clause_uuid}/ancestry",
            "/v1/clauses/{clause_uuid}/versions/{commit_id}",
            "/v1/demo/gate-run",
            "/v1/demo/subjects",
            "/v1/ledger",
            "/v1/lessons/{lesson_id}/propagation",
            "/v1/permits/{permit_id}",
            "/v1/permits/{permit_id}/blocking-checks",
            "/v1/permits/{permit_id}/checks:materialise",
            "/v1/permits/{permit_id}/merge",
            "/v1/permits/{permit_id}/silence",
            "/v1/permits/{permit_id}/suspend",
            "/v1/recall-runs/{run_id}",
            "/v1/receipts/{receipt_id}"
        ],
        "detail": "no resource is declared at GET /v1/",
        "kind": "no_route",
        "status": 404
    }
}
```

Count it in one line:

```console
$ curl -s https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/ \
    | python -c "import sys,json;print(len(json.load(sys.stdin)['error']['declared']))"
17
```

**Where it comes from:** `verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:606-611`
— the 404 branch passes `declared=sorted({r.template for r in ROUTES})` at **`:610`**, and `ROUTES`
is the registry built at `app.py:320`. The list is therefore *derived from the router*, not
maintained beside it, so it cannot drift from what the function will actually serve.

**Why this matters for the census specifically:** it is an AWS-side proof as well as an API one.
A 404 with **our** JSON body means the Function URL resolved, Lambda cold-started or reused a
container, and our handler ran. An AWS-level refusal looks completely different
(`{"Message":"Forbidden"}` with a 403, which is what `authorization_type = AWS_IAM` returns to an
unsigned caller). See §2.2.

### 1.2 `GET /v1/health` — the AWS-to-CockroachDB link, proven in one request

```console
$ curl -sD- https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health
HTTP/1.1 200 OK
Date: Sun, 16 Aug 2026 07:37:34 GMT
Content-Type: application/json; charset=utf-8
Content-Length: 410
Connection: keep-alive
x-amzn-RequestId: 38f0222d-1c3e-429f-b168-52ff4521f03a
x-mainline-api: demo-read
cache-control: no-store
X-Amzn-Trace-Id: Root=1-6a8168bc-789b873974c391164cbbb388;Parent=4be1cf340289007c;Sampled=0;Lineage=1:b4f06713:0

{"applied_by":"scripts/deploy/cloud_chain.py","cluster_version":"CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)","database":"mainline_demo","deploy_chain_applied":271,"deploy_chain_files":271,"migrations_applied":0,"ok":true,"schema_fingerprint":"ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339","seconds":1.1729,"server_date":"2026-08-16T07:37:33.970593Z"}
```

Field by field, and every one of them is load-bearing:

| field | value | what it proves |
|---|---|---|
| `ok` | `true` | the statement answered |
| `cluster_version` | `CockroachDB CCL v26.2.5` | the judge verifies **our CockroachDB version** without an account |
| `database` | `mainline_demo` | which database the function *actually reached*, not which one it was configured for |
| `deploy_chain_applied` / `deploy_chain_files` | `271` / `271` | the number **that request returned today**, re-derived and not recalled. It is the chain ledger's own count on the cluster the endpoint reached — it is not a migration pass-rate and must not be read as "the whole schema applies cleanly". |
| `migrations_applied` | `0` | **true, not broken** — two appliers write two ledgers and this database was built by `cloud_chain.py`, which writes `trappoint.deploy_chain`, not `trappoint.schema_migration`. The endpoint reports both and names which one it quotes (`applied_by`). |
| `schema_fingerprint` | `ec9b1ce7…50339` | a digest of the served schema, so two artefacts can be shown to describe the same database |

**This single request is the census's spine.** A 200 here means: the Function URL routed → Lambda
ran our handler → the handler resolved a DSN → and in the deployed environment a DSN can only
come from SSM (§2.4), signed with the execution role's injected credentials (§2.3) → a pgwire
connection to CockroachDB Cloud in Singapore opened → and a statement returned. **Four of this
file's five services are entailed by that one 200** — Function URL, Lambda, IAM, SSM. The fifth,
**CloudWatch Logs, is not entailed by it**: the response proves an invocation id was issued, not
that a log event was ingested, and §2.5 says so rather than rounding up.

The `schema_fingerprint` in that body is the field §1.3 then puts to work: it is what lets a
committed transcript and a live request be shown to describe the same database.

**Warm latency, measured three times just now** (server-side `seconds`, then wall-clock from
Australia to `ap-southeast-1`):

```console
ok=True seconds=0.0133 total=0.870415s
ok=True seconds=0.0131 total=0.829648s
ok=True seconds=0.0201 total=0.892074s
```

The `seconds` field is the handler's own measurement of connect-plus-query. ~13–20 ms warm
against a managed cluster; the ~0.85 s round trip is intercontinental network, not the function.

**Read these as three samples, not as a performance claim.** They are three single readings taken
from one workstation in Australia against `ap-southeast-1` on one afternoon. This repository holds
no p50, no p99 and no load profile for that hop, and nothing here may be presented as a product
latency characteristic. They are in this file for one purpose: to show that the endpoint answers
*warm*, so a reader knows the 200 in §1.2 is a routine response and not a lucky cold start.

Re-measured in a second round the same day — `seconds` **0.0097 / 0.0110 / 0.0208** — and the
`/v1/health` body at 10:51 UTC carried the **same `Content-Length: 410`, the same
`schema_fingerprint ec9b1ce7…50339` and the same `deploy_chain_applied 271`** as the block above.
Two rounds, hours apart, same answer.

### 1.3 The same origin, recorded anonymously, and committed to the repository

Neither of these is new work by W1 and neither needed a credential. They matter to *this* file
because they are **committed transcripts of AWS invocations of this exact Function URL**, and
because each request carries the AWS-issued invocation id — which is what makes §2.5's CloudWatch
row checkable at all.

**`evidence/demo/live-beats.json`** (generated `2026-08-15T14:11:35Z` by `scripts/proof/live_beats.py`):

```
base_url                  https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/
credentials_used          none - no DSN, no AWS profile, no token; a stranger with the URL
target_is_local_emulator  false
verdict                   PROVEN        failures  []
```

Eleven requests, **eleven distinct `x-amzn-requestid` values**, every URL on this origin, statuses
`{200, 423}` — the 423 being a documented trap, not a fault:

| # | request | status | AWS invocation id (`x-amzn-requestid`) |
|---|---|---|---|
| 1 | `GET /v1/demo/subjects` | 200 | `ba594b22-0b56-48dc-9ff9-3abd8142aad6` |
| 2 | `GET /v1/health` | 200 | `d0e8f5ca-dc2d-4f18-ba9e-897a1a29f01f` |
| 3 | `GET /v1/permits/{permit_id}` | 200 | `387c6a8b-a3eb-443c-9f23-f79ff3a3faa4` |
| 4 | `GET /v1/permits/{permit_id}/blocking-checks` | 200 | `f9578419-25a3-4c8e-bc32-b9b2051eea29` |
| 5 | `GET /v1/permits/{permit_id}/silence` | 200 | `b64b4ec1-b412-4236-bd9c-f5d6d34af32a` |
| 6 | `GET /v1/change-requests/{cr_id}` | 200 | `735645cd-3c85-4f95-973a-7bd1300e9ce9` |
| 7 | `GET /v1/ledger` | 200 | `671f8a7d-fef8-4f3c-9570-7bf4ae73deba` |
| 8 | `POST /v1/demo/gate-run` | 200 | `be1d350a-262c-42d3-9990-6cf27ed41963` |
| 9 | `GET /v1/permits/{permit_id}` | 200 | `45cfd8ed-9cbb-43c0-8222-9b89fef54641` |
| 10 | `POST /v1/permits/{permit_id}/merge` | **423** (documented trap) | `9e97453d-d2de-42ed-87d7-69262d60289a` |
| 11 | `GET /v1/permits/{permit_id}` | 200 | `3839f728-88e1-431f-8865-ea6d3530afec` |

The transcript names the header's issuer itself, and the sentence is worth quoting because it is
the AWS attribution: *"request_id_issued_by: the AWS Lambda Function URL that served this request."*

**The discriminator that makes this a *cloud* transcript and not a local one.** Every one of the
eleven records `emulator_header: null`. The repository ships a local Function-URL emulator
(`scripts/deploy/local_furl.py`) which stamps `X-Mainline-Emulator: local_furl` on everything it
serves; its absence on all eleven, plus `target_is_local_emulator: false`, is a positive check that
these invocations were AWS's. Compare §4.6, where a capture that *does* carry that header is
excluded from this file for exactly that reason.

**`evidence/demo/memory-loop.json`** (generated `2026-08-15T14:18:20Z`) is seven anonymous GETs
against the same origin, `23 / 23` assertions held, verdict `PROVEN`. W1 claims none of its
CockroachDB semantics — those are W3–W6's — only this: **the transcript's `deployment` block is a
`GET /v1/health` on this Function URL, and every non-timestamp field of its recorded body is the
body a request returns today.** Measured: the two bodies carry the same ten keys; **eight are
identical** (`applied_by`, `cluster_version`, `database`, `deploy_chain_applied`,
`deploy_chain_files`, `migrations_applied`, `ok`, `schema_fingerprint`) and exactly two differ
(`seconds`, `server_date`), as they must.

Pasteable, and it needs nothing but the repository and the network:

```console
$ .venv/Scripts/python.exe -c "import json,urllib.request; \
  live=json.load(urllib.request.urlopen('https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health')); \
  saved=json.load(open('evidence/demo/memory-loop.json',encoding='utf-8'))['deployment']['body']; \
  k=('schema_fingerprint','deploy_chain_applied','deploy_chain_files','cluster_version','database','applied_by'); \
  print('MATCH' if all(live[x]==saved[x] for x in k) else 'DRIFT', live['schema_fingerprint'])"
MATCH ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339
```

**Say this:** *"A transcript committed on 15 August and a request made today return the identical
schema fingerprint from the same Lambda Function URL — the deployed database is the one the
evidence describes, and it has not drifted."* That sentence costs a judge one `curl` and one
`grep` to falsify, which is the only reason it is worth writing.

**Never say** that this proves *the deployment* is unchanged. It proves the **schema** the endpoint
serves is unchanged. The function's code, its configuration and its data could all have moved
without touching `schema_fingerprint`; `evidence/deploy/APPLIED.md` is what carries "no redeploy
happened", and it carries it for a specific date, not perpetually.

---

## 2. THE ROWS

Row shape is plan §4. `state` uses the R2 vocabulary: **LIVE** = exercised in this demo's
request path, with a live-origin check.

### 2.1 AWS Lambda

```
state:        LIVE
what it is:   The compute. One Python function is the entire server — router, API, static
              console and refusal logic — invoked per HTTP request.
where:        infra/modules/demo-api/main.tf:326-421 (aws_lambda_function.this)
                :333  handler       = "mainline_demo_api.app.handler"
                :334  runtime       = "python3.13"
                :335  architectures = [var.architecture]
              verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:522  def handler(...)
              infra/envs/demo/main.tf:355  module "api"
verify in 60s: curl -si https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health | head -1
              expected first line:  HTTP/1.1 200 OK
              (and `x-amzn-RequestId` in the headers is the Lambda invocation id)
say this:     "The whole demo API is one Python 3.13 Lambda function in ap-southeast-1. There
              is no web framework and no adapter — `app.handler(event, context)` is the server,
              because a Lambda invocation is already a function call with a dict argument."
never say:    "It runs on ECS / Fargate / EC2 / API Gateway." There is no container service and
              no API Gateway in this stack; the URL is a Lambda Function URL (§2.2).
```

**Detail worth keeping.** The handler parses **API Gateway payload format 2.0**, which is what a
Function URL emits (`app.py:29-35` documents the event shape; `rawPath` is authoritative and
`requestContext.http.path` is the fallback). Format 1.0 is also accepted so that a misconfigured
gateway degrades to a wrong route rather than a crash.

Configuration the environment states rather than inherits, all from `infra/envs/demo/variables.tf`:

| knob | value | line |
|---|---|---|
| region | `ap-southeast-1` (Singapore — where the CockroachDB Cloud cluster is) | `:34` |
| timeout | `14` s — *a reliability bound, explicitly refused as a spend lever* | `:421` |
| memory | `256` MB | `:460` |
| architecture | `arm64` **as declared by this root's default** — see §6, this is the one function attribute not readable from outside | `:197` |
| log level | `WARN` (`api_log_level`) | `:547` |
| max response bytes | `139264` = `136 * 1024`, matching `static_site.py:323` `DEFAULT_MAX_RESPONSE_BYTES` | `api_max_response_bytes` |

The **three** `lifecycle.precondition` blocks at `main.tf:388-420` are worth a judge's eye, and all
three refuse at **plan** time a configuration that would otherwise deploy cleanly and fail later:

1. **Architecture mismatch** (`:389-397`) — it reads the `<zip>.json` manifest the builder writes
   and compares its `architecture` to `var.architecture`, because an aarch64 package on an x86_64
   function *"deploys cleanly and then fails every invocation with an ELFCLASS error"*.
2. **Handler mismatch** (`:399-402`) — the manifest must declare `mainline_demo_api.app.handler`,
   the string the function is configured to call.
3. **Self-countersignature** (`:404-419`) — it refuses `demo_signer_sub == demo_countersigner_sub`,
   because the *database* refuses it: `CONSTRAINT needs_second_signer CHECK (req_second_signer =
   false OR (countersigner_credential_id IS NOT NULL AND countersigner_sub <> signer_sub))`,
   `verticals/mainline/db/migrations/0066_disposition.sql:176`. Without the precondition the stack
   deploys and then fails *"the one beat that writes anything"*, in front of whoever is watching.

That third one is the interesting one for this census: it is **a database CHECK constraint enforced
at Terraform plan time**, which is the AWS half of this project deferring to the CockroachDB half.

---

### 2.2 AWS Lambda Function URL

```
state:        LIVE
what it is:   The hostname. A Lambda-native HTTPS endpoint with authorization_type = NONE,
              which is what makes the demo "free to access" as the contest rules require.
where:        infra/modules/demo-api/main.tf:425-453 (aws_lambda_function_url.this)
                :432  authorization_type = var.url_authorization_type
                :452  invoke_mode        = "BUFFERED"
                :434-447  a commented, deliberate ABSENCE of any cors block
              infra/modules/demo-api/variables.tf:49  url_authorization_type, default "NONE"
              infra/envs/demo/outputs.tf:129 api_function_url · :146 api_authorization_type
verify in 60s: curl -s -o /dev/null -w '%{http_code}\n' https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health
              expected first line:  200
              (with NO credentials, NO signature, NO header — that IS the proof of NONE)
say this:     "The demo is a Lambda Function URL with authorization_type NONE. An anonymous
              curl with no signature gets a 200, which is exactly what the rules' 'freely
              accessible' requirement asks a judge to be able to do."
never say:    "CloudFront serves the demo." It does not — see §4.2. Also never say the URL is
              unauthenticated *by accident*: it is a recorded founder decision (D1). Do NOT
              add "…and it runs as a narrow SQL role" to that sentence in the close block
              unless W4/W6 verified it: the DSN is a secret in SSM, no live response names
              its SQL role, and W1 could not check it from outside. The repository DECLARES
              the narrow role (`verticals/mainline/db/GRANTS.yaml`, 100 `mainline_api`
              rows) and a LOCAL probe exercises it (`evidence/demo/cr-gate/role-probe.json`
              connects as `root` and `SET ROLE mainline_api`) — which is a repository fact,
              not a fact about the deployed connection.
```

**The negative control, which is what makes the check mean something.** `authorization_type` admits
exactly two values and the variable refuses everything else at plan time. In the `AWS_IAM` shape the
same anonymous request returns a **403 with AWS's own body**, not ours. So a 200 carrying *our*
JSON is a positive discriminator between the two configurations, not just evidence that something
answered.

**TLS is AWS's, and we did not provision it.** Stated precisely so nobody reads an ACM row into it:

```console
$ echo | openssl s_client -connect ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws:443 \
    -servername ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates
subject=CN=*.lambda-url.ap-southeast-1.on.aws
issuer=C=US, O=Amazon, CN=Amazon RSA 2048 M04
notBefore=Oct 29 00:00:00 2025 GMT
notAfter=Nov 27 23:59:59 2026 GMT
```

*Say:* "HTTPS is terminated by AWS on the Function URL's managed certificate." *Never say:* "we
provisioned an ACM certificate" — we did not, and the wildcard subject shows it is AWS's.

**The missing `cors` block is a security decision, not an omission** (`main.tf:434-447`). Under D1
the SPA and the API answer on **one origin**, so every console request is same-origin and the
browser never sends `Origin`. `cors { allow_origins = ["*"] }` would therefore change nothing about
whether the demo works and exactly one thing about what an attacker can do: it turns "any page on
the internet may make a no-credentials request and not read the answer" into "…and read it."

`invoke_mode = "BUFFERED"` and not `RESPONSE_STREAM`: every response is a small JSON envelope or a
packaged static asset, and streaming would only add a mode in which a partial body reaches the
console with a `200` already on it.

---

### 2.3 AWS IAM (the Lambda execution role)

```
state:        LIVE
what it is:   The identity every request runs as. Lambda injects the role's temporary
              credentials into the handler's environment; db.py reads them and signs with them.
where:        infra/modules/demo-api/main.tf:247-274 (assume-role doc, aws_iam_role.this,
                the AWSLambdaBasicExecutionRole attachment)
              infra/modules/demo-api/main.tf:276-322 (aws_iam_role_policy.dsn_access)
              verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:223-232
                — AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN, read from os.environ
verify in 60s: sed -n '276,322p' infra/modules/demo-api/main.tf
              expected first line:  data "aws_iam_policy_document" "dsn_access" {
              (then read the two statements; the whole grant is 2 actions on 1 resource)
say this:     "The Lambda's execution role can do two things: write its own log group, and read
              ONE named SSM parameter. `ssm:GetParameter` on one ARN — not a prefix, not a
              wildcard — and `kms:Decrypt` conditioned on `kms:ViaService = ssm.ap-southeast-1
              .amazonaws.com` and on the encryption context naming that same parameter."
never say:    "least privilege" as a slogan with nothing behind it. Say the two actions and the
              one ARN; that is the checkable version and it is stronger.
```

**The grant, in full, because its narrowness is the claim.**

* `ssm:GetParameter` on `local.dsn_parameter_arn` — a single constructed ARN. The comment at
  `main.tf:282-284` records the discipline: *"ONE ARN. Not `parameter/mainline/*`, not
  `parameter/*`. `db.py` calls `GetParameter` and only `GetParameter`, so `GetParameters`,
  `GetParametersByPath` and `DescribeParameters` are all absent as well."*
* `kms:Decrypt`, with two conditions rather than a key ARN — because the AWS-managed `aws/ssm`
  key protects **every** SecureString in the account, so naming it as the resource would be
  *wider* than the conditions are. `kms:ViaService` restricts the grant to decrypts SSM itself
  performs in this region; `kms:EncryptionContext:PARAMETER_ARN` (`restrict_kms_to_parameter`,
  default `true`) reduces it to the ciphertext of exactly one parameter, whatever the `Resource`
  element says.
* `AWSLambdaBasicExecutionRole` for CreateLogGroup / CreateLogStream / PutLogEvents. The module
  names this as **the one wildcard in the role** and says why it is not theirs to narrow
  (`main.tf:268-270`).

**STS is on this path too, and it is worth one sentence rather than a row.** The credentials the
handler signs with are a *session*: `db.py:225` reads `AWS_SESSION_TOKEN` and `db.py:250-251` adds
it as the `x-amz-security-token` header, which is then part of the signed-header list. That is
`sts:AssumeRole` output being consumed on every cold start. It is folded in here rather than given
its own row because a separate "AWS STS" line in a close block would be logo-padding, and plan **R5**
says a row that adds a logo outranks nothing.

**What the handler deliberately does NOT do**, quoted from `db.py:219-221`: *"No credential file,
no IMDS walk, no profile resolution — every one of those is a code path that behaves differently on
a workstation than in a Lambda, and this function must behave the same way in both or it is
untestable."*

---

### 2.4 AWS Systems Manager Parameter Store

```
state:        LIVE
what it is:   Where the CockroachDB Cloud DSN lives. One parameter, fetched once per execution
              environment by name, with WithDecryption sent, over a request the handler
              signs itself. (The APPLIED parameter's type was not read back — see §6.1;
              the deploy procedure writes `--type SecureString`.)
where:        verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:214-305  _ssm_get_parameter
                :205-211  _sign / _signing_key   (the SigV4 key derivation)
                :234      host = f"ssm.{region}.amazonaws.com"
                :237      body = {"Name": name, "WithDecryption": True}
                :311-345  resolve_dsn — $MAINLINE_DSN first, else $MAINLINE_DSN_PARAM via SSM
              infra/modules/demo-api/main.tf:135-137  MAINLINE_DSN_PARAM = local.dsn_parameter_path
              infra/modules/demo-api/main.tf:118      the constructed parameter ARN
              infra/envs/demo/variables.tf:305        dsn_parameter_name = "/mainline/demo/cockroach_dsn"
verify in 60s: .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests/test_envelope.py \
                 -q -k "ssm or aws_sdk"
              expected first line:  ..                    [100%]
              (observed, twice today: "2 passed, 56 deselected" in 1.03 s and 0.93 s)
say this:     "The Lambda reads its database credential from SSM Parameter Store, once per
              execution environment, over an HTTPS request it signs with SigV4 built from
              hashlib and hmac — no boto3 in the deployment package at all."
never say:    "The DSN is in Terraform state" or "in an environment variable". Terraform never
              sees the value: it constructs the parameter's ARN and never reads it, and the
              module's own variable validation REJECTS an attempt to pass MAINLINE_DSN.
              Also do not say "as a SecureString" in the close block unless somebody runs
              §6.1's one command first — the request sends WithDecryption and the runbook
              writes --type SecureString, but W1 never read the applied type back, and an
              unverified adjective is exactly the kind of line a judge can check and we
              cannot. "Reads its credential from SSM Parameter Store" needs no adjective
              and is fully proven by the 200 in §1.2.
```

**Why the 200 in §1.2 is a proof that SSM ran, and not an assumption.** The chain is four steps and
every one is checkable in the repository:

1. `health()` calls `db.resolve_dsn()` and, on `DsnUnavailable`, returns **503 `dsn_unset`** with the
   underlying error as `detail` (`health.py:245-255`). So a 200 entails `resolve_dsn()` succeeded.
2. `resolve_dsn()` takes `$MAINLINE_DSN` if set, otherwise the SSM path (`db.py:311-345`). So a 200
   entails one of those two.
3. In the deployed stack `$MAINLINE_DSN` **cannot** be set: the module composes the function's
   environment as `merge(var.extra_environment, { …module keys… })`, and `extra_environment` has a
   `validation` block whose deny-list's **first entry is `MAINLINE_DSN`**
   (`infra/modules/demo-api/variables.tf:1253-1276`, error text: *"the DSN is never in Terraform
   state — use dsn_parameter_name"*). `MAINLINE_DSN_PARAM` is set unconditionally at `main.tf:137`.
4. Therefore a 200 from `/v1/health` on this origin entails **the signed `ssm:GetParameter`
   succeeded**.

**And it has been falsified once, which is the part that makes it credible.** On 2026-08-14 the
stack was applied *before* the parameter was written. `evidence/deploy/APPLIED.md` records what the
same origin returned:

```
GET  /                     200, 4,655 B, 1.63 s   (static console, served)
GET  /v1/health            ok=false, reason="dsn_unset"
POST /v1/demo/gate-run     503,        kind="dsn_unset"
```

> Both API answers name the cause exactly: *SSM GetParameter '/mainline/demo/cockroach_dsn' in
> ap-southeast-1 answered HTTP 400: {"__type":"ParameterNotFound"}*

That string is a **verbatim SSM API error surfaced by our handler on the public origin**, and it is
reproduced **20 times** in `evidence/deploy/judge-walk.json` (counted today; `dsn_unset` appears 62
times in the same file) by a program that takes a URL and nothing else. The endpoint's failure mode was literally an SSM call failing; its success mode requires that
same call to succeed. An anonymous reader can compare that recorded 503 with today's 200 and needs
no AWS account to do it.

**Reproduce the failing shape locally in ten seconds** (this is the second SSM test, and it proves
the handler names the missing signature rather than hanging on a socket):

```console
$ .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests/test_envelope.py \
    -q -k "ssm or aws_sdk"
..                                                                       [100%]
2 passed, 56 deselected in 0.93s
```

junit-xml, per the measurement rule — `tests=2 failures=0 errors=0 skipped=0`:

```
{'name': 'pytest', 'errors': '0', 'failures': '0', 'skipped': '0', 'tests': '2', 'time': '0.798'}
 - test_the_ssm_call_is_sigv4_signed_and_the_value_is_cached_not_logged
 - test_no_web_framework_or_aws_sdk_is_imported
```

The first of those asserts, against a faked socket, that the request is
`POST https://ssm.ap-southeast-1.amazonaws.com/` with `X-Amz-Target: AmazonSSM.GetParameter`, body
`{"Name": "/mainline/demo/dsn", "WithDecryption": true}`, an `Authorization` header starting
`AWS4-HMAC-SHA256 Credential=…/ap-southeast-1/ssm/aws4_request` with
`SignedHeaders=content-type;host;x-amz-date;x-amz-security-token;x-amz-target` and a 64-hex
signature — **that the value is fetched exactly once per execution environment** (a second
`resolve_dsn()` must not open a second socket) — and that the DSN never reaches a log record.

**AWS KMS — stated with its premise, not claimed.** `WithDecryption: True` is sent on every call
(`db.py:237`) and the execution role carries a `kms:Decrypt` grant scoped by
`kms:EncryptionContext:PARAMETER_ARN`, a context that **only exists for SecureStrings**. If the
applied parameter is a SecureString — which is what `docs/deploy/RUNBOOK.md:345` and
`docs/deploy/PRE-APPLY.md:267-293` prescribe (`aws ssm put-parameter --type SecureString
--overwrite`) — then SSM performs a KMS decrypt under the role's credentials on every cold start,
and KMS is on this path. **I could not verify the applied parameter's type**: doing so needs
`aws ssm describe-parameters`, which needs credentials, which W1 may not use. It is therefore
logged as an open question (§6.1) and **not** written as a census row. A customer-managed
`aws_kms_key` does exist in `infra/` — it belongs to the cost guard, not to this path, and it is
W2's.

---

### 2.5 Amazon CloudWatch Logs

```
state:        LIVE
what it is:   Where every invocation's record goes. One log group, created by Terraform and
              named as the function's log destination, in JSON format with a set level.
where:        infra/modules/demo-api/main.tf:239-243 (aws_cloudwatch_log_group.this)
              infra/modules/demo-api/main.tf:111  log_group_name = "/aws/lambda/${var.function_name}"
              infra/modules/demo-api/main.tf:373-378  logging_config { log_format = "JSON";
                application_log_level = var.log_level; system_log_level = "WARN";
                log_group = aws_cloudwatch_log_group.this.name }
              infra/modules/demo-api/main.tf:382-386  depends_on — the group before the function
              verticals/mainline/apps/demo-api/src/mainline_demo_api/logbudget.py (the ceiling)
verify in 60s: curl -sD- -o /dev/null https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health \
                 | grep -i 'x-amzn-requestid'
              expected first line:  x-amzn-RequestId: <a uuid>
              (observed: x-amzn-RequestId: 38f0222d-1c3e-429f-b168-52ff4521f03a)
              — that id is the key the invocation is recorded under in /aws/lambda/mainline-demo-api
say this:     "Every invocation is logged to a Terraform-managed CloudWatch log group in JSON
              format, and the handler enforces a per-invocation LOG BYTE BUDGET on top, because
              a log group has retention and not a quota — ingestion is the charged term."
never say:    "Here are the logs" to an anonymous reader. Reading the group needs the account.
              What a stranger can check is the request id header and the declaration; say that.
```

**The honest split, because this is the one row a judge cannot fully verify:**

* **Checkable by anyone, right now:** the response carries `x-amzn-RequestId` (the invocation id)
  and `X-Amzn-Trace-Id`. The log group is declared in the module, the function's `logging_config`
  names it, and `depends_on` makes "create the group before the function" a real edge in the
  dependency graph rather than a naming convention two resources happen to agree on.
* **Already recorded, without an account:** `evidence/demo/live-beats.json` holds **eleven distinct
  invocation ids** from eleven anonymous requests to this origin (§1.3), and names their issuer as
  the Function URL. A stranger cannot read the log events, but they can hold eleven ids that AWS
  minted and see that each one came back with our JSON — which is the checkable half of the claim,
  and it is the half this file makes.
* **Needs the AWS account:** actually reading a log event. W1 has no credentials and may not use
  any. This is stated rather than papered over.

**The part that is genuinely interesting, and it is application code, not infrastructure.**
`logbudget.py` is a **cost control**, and its opening argument is the reason:

> a CloudWatch log group has retention, not a quota — `log_retention_days = 7` bounds how long
> bytes are *stored* and bounds *ingestion* not at all, and ingestion is the charged term

Under a flood the refusal path is the hottest path in the function, and a single 120-byte line on
it is tens of megabytes a second of ingestion — a second bill, spent inside a control that exists
to save money. So there are two mechanisms: a pre-record **collapse** (`claim()`, asked *before* a
`LogRecord` exists, so a suppressed line costs one dict lookup) and a hard **ceiling** — a
`logging.Filter` at the exit, where every record has to pass whether or not its author remembered
the module existed. The collapse degrades to the ceiling and never to nothing. The bound is
**bytes per invocation, not lines**, because a line's length is not a constant. Default
`DEFAULT_BUDGET_BYTES = 4096` (`logbudget.py:109`), published to the deployed function as
`MAINLINE_LOG_BUDGET_BYTES` so `aws lambda get-function-configuration` answers the question.

The module also records **what it does not bound** — the Lambda platform's own `START` / `END` /
`REPORT` / `INIT_START` lines — rather than letting a reader assume otherwise. Retention is
`7` days (`infra/envs/demo/variables.tf:808`), chosen to sit inside the 5 GB/month free ingest.

**Adjacent and NOT claimed here:** Lambda also publishes `AWS/Lambda` metrics (Invocations,
Duration, Errors, Throttles) to CloudWatch on every invocation, and seven alarms plus a dashboard
consume them. The alarms, the dashboard, the SNS topic and the Budget are **applied
infrastructure, not request path** — they are W2's rows, and this file does not claim them.

---

## 3. THE TECHNICAL-IMPLEMENTATION FACT NOBODY HAS WRITTEN DOWN

**The deployment package's entire third-party dependency closure is `psycopg`. There is no AWS SDK
in it, and the AWS call it makes is signed by hand.**

Two claims, and both are enforced by tests rather than asserted in prose.

### 3.1 The package pins two wheels and nothing else

`verticals/mainline/apps/demo-api/pyproject.toml:47-50`:

```toml
dependencies = [
  "psycopg==3.3.4",
  "psycopg-binary==3.3.4",
]
```

`retry.py:10-18` states the constraint and the reason:

> `verticals/mainline/apps/demo-api/pyproject.toml` pins the deployment package's dependencies to
> `psycopg==3.3.4` and `psycopg-binary==3.3.4` *and nothing else* — no boto3, no framework, no
> workspace package — so that the artefact's behaviour does not depend on what the Lambda runtime
> happens to ship this month

### 3.2 boto3 is absent *on purpose*, and the module says so where it would have been imported

`db.py:25-30` — this is the comment sitting directly above the SigV4 code:

> The SSM call is signed with SigV4 out of `hashlib` and `hmac` rather than by importing boto3.
> Not because boto3 is unavailable — it is in the runtime image — but because the deployment
> package's behaviour would then depend on which boto3 AWS shipped that month, and because a
> single `GetParameter` is about sixty lines of signing. The handler's whole dependency closure
> stays `psycopg` plus the standard library, and `tests/test_envelope.py` asserts it.

The whole grep, so the absence is visible rather than asserted:

```console
$ grep -rn "boto3\|botocore\|bedrock" verticals/mainline/apps/demo-api/src/mainline_demo_api/*.py
verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:26:importing boto3. Not because boto3 is unavailable — it is in the runtime image — but
verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:27:because the deployment package's behaviour would then depend on which boto3 AWS shipped
verticals/mainline/apps/demo-api/src/mainline_demo_api/retry.py:12:``psycopg-binary==3.3.4`` *and nothing else* — no boto3, no framework, no workspace
```

**Three hits, all three of them comments explaining the absence.** This is the same construction
plan **R4** prescribes for Bedrock and it is the reason W1 can be confident about the boundary:
the request path contains no AWS SDK, so anything the SDK does is by definition not in it.

### 3.3 The test that enforces it, run today

```console
$ .venv/Scripts/python.exe -m pytest \
    verticals/mainline/apps/demo-api/tests/test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported -q
.                                                                        [100%]
1 passed in 0.87s
```

junit-xml: `tests=1 failures=0 errors=0 skipped=0`.

The test does not read source. It **imports every module the zip ships, in a fresh interpreter,
and reads the resulting closure** — because `app.handler` reaches `transitions` and `gate_run` on
the first POST, and a dependency arriving through the write surface is in the package exactly as
much as one arriving through `reads`. It then guards against a vacuous pass in both directions:
`psycopg` must be **present** (it enters only through `db.py`, so its presence proves the probe
actually ran the imports and can see a third-party root), and `{app, db, envelope, health, reads}`
must all be among the discovered modules. A sibling test asserts the banned-root list used here is
byte-identical to `scripts/deploy/bundle_manifest.py`'s `DEFAULT_FORBIDDEN`, so the claim about
the **imports** and the claim about the **bytes** cannot drift apart.

### 3.4 The measured artefact

`evidence/deploy/lambda-bundle.json` (2026-08-11) records the zip that carries all of this:
`arm64`, `manylinux_2_28_aarch64`, **7,989,296 bytes zipped / 28,364,357 unzipped, 206 entries**,
built three times — twice by `build_lambda.sh`, once by `build_lambda.ps1` — to the **identical**
`sha256 c85d7f00a5576e412dfb0124ad93c40104757011179d0029361d9a8db5b8a4b0`, with the packer program
itself hashed (`packer.sha256 eab069d1…`) so that "two builders agree" is checkable and not a
coincidence. Two wheels are in the manifest and only two — `psycopg-3.3.4-py3-none-any.whl` and
`psycopg_binary-3.3.4-cp313-cp313-manylinux_2_28_aarch64.whl` — and `top_level` shows the split:
**`mainline_demo_api` is 11 entries and 283,402 bytes**; the remaining ~28 MB is psycopg's binary
wheel. The application *is* the small part.

The same artefact carries the check that §2.1's `lifecycle.precondition` exists to make unnecessary:
`elf_check` reads **byte 18 of the ELF header of every `.so` in the zip** — 18 shared objects,
`e_machine 0xB7 EM_AARCH64` for the arm64 build and `0x3E EM_X86_64` for the x86_64 one. That is
the "an aarch64 zip on an x86_64 function deploys cleanly and then fails every invocation"
failure mode, refused twice: once at build time by reading the ELF headers, once at **plan** time
by the precondition.

**Say this:** *"The Lambda's dependency closure is psycopg and the standard library. The one AWS
API call it makes — `ssm:GetParameter` — is SigV4-signed from `hashlib` and `hmac` in about sixty
lines, so the artefact's behaviour cannot change because AWS shipped a different boto3 that month.
A test imports every shipped module in a fresh interpreter and reads the closure to prove it, and
the zip is byte-reproducible across two independent builders."*

**Never say:** *"we avoid the AWS SDK"* as if it were unavailable. It is in the runtime image; not
importing it is a choice, and the choice is the interesting part.

---

## 4. WHAT IS *NOT* IN THIS PATH — considered and handed to W2

Every line here exists so the exclusion is auditable. Plan **R3** and **R4** govern.

### 4.1 Amazon S3 — real, applied, and not on the request path

The static console is served **out of the Lambda deployment package**, not from a bucket.
`static_site.py:8-12`, in the module's own words:

> DECISION **D1** therefore makes the demo URL a **public Lambda Function URL** that serves *both*
> the SPA and the API from one origin. There is no S3 bucket in the request path and no CDN, so
> the thing that used to serve `index.html` has to be this handler.

Live corroboration — the response names the packaged file, and the origin is the same host as the API:

```console
$ curl -sD- -o /dev/null https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Content-Length: 4749
x-amzn-RequestId: ca032cab-70f4-4e25-874b-eac312c5a06d
x-mainline-api: demo-static
x-mainline-static: index.html
```

S3 **is** used by this project, in two distinct places that must not be run together — W1 conflated
them on the first pass and the correction is worth stating:

* **the Terraform state bucket** `mainline-demo-tfstate-<account-id>`, created by
  `scripts/deploy/bootstrap_state.sh` with the AWS CLI rather than by Terraform (it cannot be
  created by the run that needs it to already exist). `infra/envs/demo/backend.tf:30` describes it:
  *"versioning on, all public access blocked, SSE-S3 on, tagged `project=mainline`"*.
* **the site bucket** in `infra/modules/demo-site/`, which the unrealised CloudFront design would
  have fronted, and which is where `noncurrent_version_expiration_days` (default **30**,
  `demo-site/variables.tf:296`) actually lives.

Both are **W2's rows**, and the detail above is offered to W2 rather than claimed here.

### 4.2 Amazon CloudFront — declared and refused by AWS (R3)

Not applied, and no sentence in this file implies otherwise. `infra/envs/demo/main.tf:40-44` carries
the real `terraform apply` transcript of 2026-08-10 — *"Error: creating CloudFront Distribution …
StatusCode: 403 … AccessDenied: Your account must be verified before you can add new CloudFront
resources"* — and `:46-51` records that the same refusal comes from a bare
`aws cloudfront create-distribution` under `AdministratorAccess`, so it is an account-level
verification hold on **new** distributions and not a Terraform fault. `enable_cloudfront` defaults to `false`
(`infra/envs/demo/variables.tf`). Decision **D1** gave the hostname to the Function URL so that
nothing could hold the URL hostage. The `aws_lambda_permission.cloudfront_invoke` grant is
`count = 0` in this shape — *"`count = 0` and not 'created but harmless'"*, because a reader who
has to work out that one resource is inert stops checking the next one. **State: DECLARED. W2's row.**

### 4.3 Amazon Bedrock — real, exercised, not on this path (the R4 construction)

`evidence/deploy/aws-live.json` records four live AWS calls on 2026-08-11 including
`bedrock-runtime:InvokeModel` on `amazon.titan-embed-text-v2:0`, HTTP 200, 1024-dim embedding,
L2 norm 1.0 — **in `ap-southeast-2`, from a workstation, with boto3 1.43.66**. None of that is in
the demo's request path: the deployment package has no boto3 (§3), and the region is not even the
demo's. **State: REPO. W2's row.** Say exactly that; the repository already uses this construction
and it reads as confidence.

### 4.4 SNS · Budgets · CloudWatch alarms · CloudWatch dashboard · KMS CMK

All applied, none invoked by a request. Seven alarms
(`mainline-demo-api-{concurrency,duration-p99,errors,throttles,invocations-burst,invocations-hourly,log-ingestion}`,
cross-checked against the plan file in `evidence/deploy/verify/post-apply-dry.json`) feed one SNS
topic into a responder that calls `PutFunctionConcurrency(ReservedConcurrentExecutions=0)`, plus a
Budget. `evidence/deploy/APPLIED.md`: *24 created, 0 changed, 0 destroyed; 37 resources in state;
eleven are the demo API and thirteen the cost guard.* **State: APPLIED. All W2's rows.**

### 4.5 AWS X-Ray — not configured, despite the header

`X-Amzn-Trace-Id` appears on every response with `Sampled=0`. That header is injected by the Lambda
service, not by us, and there is **no `tracing_config` block anywhere in `infra/`**:

```console
$ grep -rn "tracing_config\|xray\|AWSXRay" infra/modules/demo-api/main.tf infra/envs/demo/main.tf
(no output)
```

**Never say "distributed tracing with X-Ray."** The header is present; active tracing is not
enabled. Recorded here specifically because the header is exactly the sort of thing that produces
an accidental overclaim in a close block.

**The last two entries are not services.** They are **evidence artefacts sitting in W1's own input
directories that could be mistaken for AWS proof**, and they are excluded here loudly rather than
quietly, because the film draws on one of them.

### 4.6 The operator screens were captured against a LOCAL EMULATOR, not against AWS

This one is in this file because the film uses those screens, and a close block that says "these
are the deployed console" would be false. `evidence/demo/operator-capture.json` states its own
target in its own fields:

```
target.base_url               http://127.0.0.1:8741
target.emulator_header        local_furl
target.is_the_deployed_url    false
assertions[0]                 "target-is-the-local-emulator" — held: true
```

…and it gives the reason in full, which is discipline rather than a limitation:

> `why_not_the_deployed_url`: *"POST /v1/demo/gate-run drives four beats against the one shared
> public demo subject. Capturing against it would be load-testing the thing a judge is about to
> open, and W7 is forbidden to touch AWS."*

The emulator (`scripts/deploy/local_furl.py`) runs the **same handler module** the Lambda runs — it
imports `mainline_demo_api.app.handler` (`local_furl.py:554-562`) and calls it with a payload-2.0
event dict, exactly as the Function URL does (`local_furl.py:11,16`) — so the screens are honest
about the *application*. They are not evidence about **AWS**, and no AWS row
in this file rests on them. *Say:* "the operator screens were filmed against a local emulator of the
Function URL running the same handler." *Never say:* "these screens are the deployed function
answering." The distinguishing header is right there in the capture and a judge can grep it.

### 4.7 `evidence/demo/judge-path-walk.json` carries verdict `INCOMPLETE` — and is not this path

Flagged because it sits in a directory a judge will open. It is a **local** walk
(`database: w_w3_judge_path_3b0aafc625f2_5a0edd59`, `driver: psycopg 3.3.4`, dated 2026-08-14),
not an HTTP transcript of the origin, and it stops at beat 2 — *"the check offered no defeater
vocabulary, so no judge could choose"*. It is superseded in fact by `live-beats.json`
(2026-08-15, against the live URL, verdict `PROVEN`, `failures: []`) but not in filename.
**No claim in this file depends on it.** Same shape of hazard as §6.3; flagged for W7, not W1's
file to change.

---

## 5. DETECTORS, so the generator can reproduce these rows (R6)

Proposed as prose plus the exact probe, per plan **R6**. **W1 has not edited
`scripts/submission/capture_tool_evidence.py` and has weakened no ratchet.**

| proposed row key | state | detector (exact) |
|---|---|---|
| `aws_lambda` | LIVE | HTTP: `GET {origin}/v1/health` → 200 **and** response header `x-amzn-requestid` present |
| `aws_lambda_function_url` | LIVE | HTTP: unauthenticated `GET {origin}/v1/health` → 200 (a 403 would mean `AWS_IAM`); repo: `grep -c 'authorization_type = var.url_authorization_type' infra/modules/demo-api/main.tf` == 1 |
| `aws_iam_execution_role` | LIVE | repo: `aws_iam_role.this` + `aws_iam_role_policy.dsn_access` present in `infra/modules/demo-api/main.tf`; the policy document's action set is exactly `{ssm:GetParameter, kms:Decrypt}` |
| `aws_ssm_parameter_store` | LIVE | repo: `_ssm_get_parameter` in `db.py` **and** `MAINLINE_DSN` in the `extra_environment` deny-list; test: `pytest -k "ssm or aws_sdk" verticals/.../tests/test_envelope.py` → 2 passed; HTTP: `/v1/health` → 200 (⇒ `resolve_dsn()` succeeded ⇒ SSM answered) |
| `aws_cloudwatch_logs` | LIVE (declaration + request id only) | repo: `aws_cloudwatch_log_group.this` and `logging_config.log_group` referencing it; HTTP: `x-amzn-requestid` header present. **Reading an event needs the account — the detector must not claim more.** |
| `aws_sigv4_no_sdk` (new, technique not service) | LIVE | `grep -c 'boto3' verticals/mainline/apps/demo-api/src/mainline_demo_api/*.py` == 3 **and all three are comments**; `pytest ...::test_no_web_framework_or_aws_sdk_is_imported` → 1 passed |
| `aws_live_transcript_identity` (new) | LIVE | `GET {origin}/v1/health`'s `schema_fingerprint` **equals** `evidence/demo/memory-loop.json → deployment.body.schema_fingerprint`; and every record in `evidence/demo/live-beats.json → requests[]` has a distinct `request_id` with `emulator_header == null` |

The route-census artefact (§1.1) is itself a detector: `len(json['error']['declared']) == 17` on
`GET /v1/`, and the number is derived from `ROUTES`, so it self-updates rather than drifting.

The transcript detector is the cheapest guard in the table and the one most worth adding: it fails
loudly the day the deployed database stops being the database the evidence tree describes, which is
the failure mode a submission judged from documents cannot otherwise see.

---

## 6. OPEN QUESTIONS — escalated, not guessed (R7)

Each needs a credential or an apply, both of which W1 is prohibited from touching.

**6.1 Is the applied SSM parameter a `SecureString`?** If yes, KMS is genuinely on the cold-start
path and earns a row; if it is a plain `String`, `WithDecryption: true` is ignored, no KMS call
happens, and **KMS must not appear in the close block at all**. One command settles it, and it must
be run by whoever holds credentials — it prints the *type*, never the value:

```
aws ssm describe-parameters --profile mainline-dev --region ap-southeast-1 \
  --parameter-filters "Key=Name,Values=/mainline/demo/cockroach_dsn" \
  --query 'Parameters[].[Name,Type]' --output text
# expected: /mainline/demo/cockroach_dsn   SecureString
```

Until it is run, §2.4 states the premise and this file claims no KMS row. **Recommended default if
nobody runs it: leave KMS out.**

**6.2 Which architecture — and which runtime — is actually deployed?** `arm64` is this root's
default and the built zip is `arm64`, but the deployed function's `Architectures` is not readable
from outside. **The same is true of `Runtime`:** `python3.13` is declared at
`infra/modules/demo-api/main.tf:334` and the applied stack was created from that Terraform
(`evidence/deploy/APPLIED.md`: *24 created, 0 changed, 0 destroyed*), which is strong evidence and
is **not** an anonymous read. One command settles both:
`aws lambda get-function-configuration --function-name mainline-demo-api`. Until then §2.1 says
"as declared by this root's default" and not "the function runs on Graviton"; a close block may
say "a Python 3.13 Lambda" on the strength of the declaration plus the apply transcript, but not
"we verified the deployed runtime". Low stakes — the
close block does not need the word arm64 — but the sentence must not be written as measured.

**6.2b A stale line number in `evidence/deploy/APPLIED.md`, found in passing and NOT fixed by W1.**
`APPLIED.md:163` says *"`DEFAULT_MAX_RESPONSE_BYTES` is still `136 * 1024` in `static_site.py:279`"*.
The **value is correct and unchanged** — measured today, `static_site.py:323`
`DEFAULT_MAX_RESPONSE_BYTES: Final = 136 * 1024` — but the **line number has drifted from 279 to
323**. The ratchet is intact; only the citation is stale. Flagged rather than edited because
`evidence/` is a record of what was observed when it was observed, and silently renumbering a
recorded observation is the one edit an evidence tree must never take. **W7's call** whether to
append a dated note. This file cites `:323`, which is where the constant is today.

**6.3 `evidence/deploy/verify/post-apply-dry.json` is a DRY run and its verdict is `NOT SATISFIED`
(9 of 9 checks unsatisfied).** The cause is benign — `terraform output` exited 1 with *"Backend
initialization required"*, so no Function URL was resolved and every downstream check was starved —
but the file is in the evidence tree with a red verdict, and a judge who opens it and does not read
the `why` fields will draw the wrong conclusion. This file cites it only for its alarm-name
cross-check, which *is* satisfied within it (`agree: true`, 7 names from the plan matching 7
derived). **Flagged for W7:** the live-origin transcripts (`evidence/deploy/LIVE.md`,
`judge-walk.json`) supersede it in fact but not in filename, and something should say so in the
place a judge looks first. Not W1's file to change.

**6.4 The standing `materialise_checks` / `exposure_receipt` INSERT gap remains open**, per the
brief. Widening the write surface of an unauthenticated endpoint is the founder's call. Noted, not
touched.

**6.5 The census documents are OUTSIDE the prose ratchet, and W7 should know before the close
block is cut from them.** `scripts/submission/check_submission_prose.py:60-64` declares
`TARGET_GLOBS = ("README.md", "docs/submission/*.md", "docs/TOOL-USAGE.md")`. That middle glob is
**not recursive**, so `docs/submission/census/**` — this file and its five siblings — is not
scanned by the nine SUB rules or the claim-hygiene table. Verified today: the checker reported
`scanned 18 file(s)` and exits 0. The arithmetic, spelled out because a wrong count here would be
the same kind of error this file exists to prevent — the globs offer **19** candidates
(`README.md` = 1, `docs/submission/*.md` = 17, `docs/TOOL-USAGE.md` = 1) and
`docs/submission/MUST-NOT-CLAIM.md` is the `REGISTER_MARKER` file, reported *"not scanned, not
passed"*, leaving **18**. The census files in `docs/submission/census/` are not among them —
that subdirectory is unreachable from a non-recursive `*`.

This is a **gap to close, not a licence to relax**, and W1 has not touched the checker (plan §5.6).
Because the automatic check does not reach here, W1 hand-audited this file against all ten families
in `docs/submission/MUST-NOT-CLAIM.md`. Two needed a guard and both were added rather than argued
away: the live latency samples in §1.2 now carry an explicit "three samples, not a performance
claim" paragraph (family 2), and the `271 / 271` row now says the number was re-derived by the
pasted request and is a chain-ledger count rather than a migration pass-rate (family 6). Families
1, 3, 4, 5, 7, 8, 9 and 10 are not touched by this file's subject matter: the trigger words
`demonstrated`, `conformance`, `residency`, `custody`, `Kestrel`, `in CI` and `nightly` each occur
**exactly once in this file, in the sentence you are reading** — measured, and stated this way
because "the file contains no occurrence of X" is false the moment a file says it.

A **second** hand-audit pass was run over the finished file (§7, rows 16–34). It re-ran every
command rather than trusting the first pass and corrected three citations — the `no_route` line
range, this section's own 18-file arithmetic, and the number of `lifecycle.precondition` blocks.
That is the honest record of a hand-audit: it found things, because hand-audits of one's own
prose always do, which is why §6.5's recommended repair is to bring this directory inside the
automatic checker rather than to promise more care.

**The recommended repair is one character** — `docs/submission/**/*.md` in place of
`docs/submission/*.md` — but changing a ratchet's scope mid-submission may light up files other
workers are still writing, so it is escalated rather than done. **W7's call.**

---

## 7. PROVENANCE — every command this file ran

Run 2026-08-16 from `D:/CoackroachDBxAWS/mainline`. `$ORIGIN` =
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`.

| # | command | result |
|---|---|---|
| 1 | `curl -s $ORIGIN/v1/` | 404 `no_route`, 17 declared routes — §1.1 |
| 2 | `curl -sD- $ORIGIN/v1/health` | 200, full body and headers — §1.2 |
| 3 | `curl -sD- -o /dev/null $ORIGIN/` | 200, `x-mainline-static: index.html` — §4.1 |
| 4 | `curl -sX POST -H 'content-type: application/json' -d '{}' $ORIGIN/v1/demo/gate-run` | `data.verdict = "PROVEN"`, 4 beats, `staged: false` |
| 5 | `openssl s_client … \| openssl x509 -noout -subject -issuer -dates` | `CN=*.lambda-url.ap-southeast-1.on.aws`, issuer Amazon — §2.2 |
| 6 | `curl -s $ORIGIN/v1/health` ×3 | `seconds` 0.0133 / 0.0131 / 0.0201 — §1.2 |
| 7 | `pytest …test_envelope.py::test_no_web_framework_or_aws_sdk_is_imported -q --junitxml` | `tests=1 failures=0 errors=0` — §3.3 |
| 8 | `pytest …test_envelope.py -q -k "ssm or sigv4 or aws_sdk" --junitxml`, then again with the narrower `-k "ssm or aws_sdk"` published in §2.4 | both: `tests=2 failures=0 errors=0`, `2 passed, 56 deselected` — §2.4 |
| 9 | `grep -rn "boto3\|botocore\|bedrock" …/mainline_demo_api/*.py` | 3 hits, all comments — §3.2 |
| 10 | `grep -rn "tracing_config\|xray\|AWSXRay" infra/…` | no output — §4.5 |
| 11 | `grep -rn "MAINLINE_DSN\b" infra/ --include=*.tf` | only the deny-list in `variables.tf` — §2.4 |
| 12 | Terraform variable defaults parsed from `infra/envs/demo/variables.tf` and `infra/modules/demo-api/variables.tf` | table in §2.1 |
| 13 | `pytest tests/deploy/test_docs_are_true.py -q --junitxml` | `tests=54 failures=0 errors=0 skipped=0` — the docs guard is green with this file present |
| 14 | `python scripts/submission/check_submission_prose.py` | `claim hygiene OK` · `submission prose OK` · exit 0 — **and `scanned 18 file(s)`, which is why §6.5 exists** |
| 15 | Hand-audit of this file against the ten families in `docs/submission/MUST-NOT-CLAIM.md` | two guards added (§1.2, §1.2 table); eight families not applicable — §6.5 |

**Second verification pass, later the same day.** Every row above was re-run rather than trusted,
and four evidence artefacts plus the emulator's source were read for the first time. **No claim
changed its answer; seven statements were corrected** (rows 25, 32, 34, 35, 36, 38, 39), which is
the point of running the pass rather than declaring one. Two of the seven are the same mistake
twice and are the ones that mattered: a row asserted `SecureString`, and another asserted the
endpoint "runs as a narrow SQL role" — **both are true of the repository and neither was measured
on the deployment.** Both now carry an explicit ban on the phrase until somebody with the right
access settles it. This is the R4 construction applied to W1's own file: a fact outside the
measured path is named as such, not quietly promoted. Row 40 is a stale citation in an
`evidence/` file, flagged for W7 and deliberately not edited (§6.2b).

One further tightening came out of the same pass and is recorded here because it is the same
species of error. §1.2 previously ended *"five of the six services in this file are on that
chain"*, which quietly swept **CloudWatch Logs** into what a 200 proves. It does not: the response
proves AWS issued an invocation id, not that an event was ingested. §1.2 now names the **four**
services the 200 entails and states the exclusion, which is what §2.5 already said and what §1.2
should have agreed with.

| # | command | result |
|---|---|---|
| 16 | `curl -s $ORIGIN/v1/` and `… \| len(declared)` | 404 `no_route`, **17** — unchanged |
| 17 | `curl -sD- $ORIGIN/v1/health` | 200, `Content-Length: 410`, same fingerprint, `271/271` |
| 18 | `curl -s -o /dev/null -w '%{http_code}' $ORIGIN/v1/health` (no credential of any kind) | `200` — §2.2 |
| 19 | `openssl s_client … \| openssl x509` | `CN=*.lambda-url.ap-southeast-1.on.aws`, Amazon RSA 2048 M04, expires 27 Nov 2026 |
| 20 | three fresh `/v1/health` samples | `seconds` 0.0097 / 0.0110 / 0.0208 — §1.2 |
| 21 | `POST $ORIGIN/v1/demo/gate-run` | `verdict PROVEN`, 4 beats, `failures` none, **`staged: false`**, `data.persisted: false`, `data.transaction.disposition: "rolled_back"`, `isolation: SERIALIZABLE` — so this check writes nothing and is safe to repeat |
| 22 | `pytest …test_envelope.py -q -k "ssm or aws_sdk" --junitxml` | `tests=2 failures=0 errors=0 skipped=0` (`time 0.738`) — §2.4 |
| 23 | `grep -rn "boto3\|botocore\|bedrock" …/mainline_demo_api/*.py` | 3 hits, all comments — §3.2 |
| 24 | `grep -rn "tracing_config\|xray\|AWSXRay" infra/…` | no output, exit 1 — §4.5 |
| 25 | line-by-line re-check of every `path:line` cited in §2 against the working tree | all resolve; **one correction made** — the 404 branch is `app.py:606-611` with `declared=` at `:610`, not `607-611` |
| 26 | parse `evidence/demo/live-beats.json` | 11 requests, 11 distinct `x-amzn-requestid`, all URLs on this origin, `emulator_header` null on all 11, `target_is_local_emulator false`, verdict `PROVEN` — §1.3 |
| 27 | parse `evidence/demo/memory-loop.json` and compare with a live request | `23/23` held, verdict `PROVEN`; the two `/v1/health` bodies share all ten keys, **eight identical**, two (`seconds`, `server_date`) differing. The §1.3 one-liner printed `MATCH ec9b1ce7…50339` — §1.3 |
| 28 | parse `evidence/demo/operator-capture.json` and `judge-path-walk.json` | `is_the_deployed_url false` / verdict `INCOMPLETE` — §4.6, §4.7 |
| 29 | `grep -n "X-Mainline-Emulator\|EMULATOR_VALUE" scripts/deploy/local_furl.py` | `:30` "on **every** response", `:118` `EMULATOR_VALUE = "local_furl"` — the §1.3 discriminator |
| 30 | `pytest tests/deploy/test_docs_are_true.py -q --junitxml` | `tests=54 failures=0 errors=0 skipped=0` — green **after** this file's edits |
| 31 | `python scripts/submission/check_submission_prose.py` | `submission prose OK`, exit 0, `scanned 18 file(s)` — §6.5 still true |
| 32 | `sed -n '55,70p' scripts/submission/check_submission_prose.py` + `ls docs/submission/*.md \| wc -l` | `TARGET_GLOBS` is at **`:60-64`** as cited, and the top-level count is **17**. **One correction made:** §6.5 previously derived 18 as "17 + README.md", which reaches the right total by the wrong route — the real derivation is 19 candidates minus the unscanned `REGISTER` file |
| 33 | the two grep detectors in §5, run as written | `grep -c 'authorization_type = var.url_authorization_type' …/main.tf` → **1**; `grep -c 'boto3' …/mainline_demo_api/*.py` → `db.py:2`, `retry.py:1` = **3**. Both detectors are true as published |
| 34 | `sed -n '388,421p' infra/modules/demo-api/main.tf` and `sed -n '171,180p' …/0066_disposition.sql` | **three** preconditions, not two — §2.1 corrected; `CONSTRAINT needs_second_signer` is at `0066_disposition.sql:175-176` as the module's comment cites |
| 35 | per-word scan of this file for the seven MUST-NOT-CLAIM trigger words | each occurs **exactly once, on line 862** — the sentence that lists them. **One correction made:** §6.5 previously said the file "holds no occurrence" of them, which its own listing sentence falsified. Restated as a count, which is checkable and true |
| 36 | `grep -rn "put-parameter" docs/deploy/RUNBOOK.md docs/deploy/PRE-APPLY.md` | `RUNBOOK.md:345` prescribes `--type SecureString --overwrite`. **One correction made:** §2.4's row said "One SecureString" and its `say this` used the adjective, while §6.1 admits the applied type was never read back. The row now says what was measured — one parameter, `WithDecryption` sent — and `never say` carries the explicit ban on the adjective until §6.1 is run |
| 37 | `variable "url_authorization_type"` default and validation, extracted | `default = "NONE"`, `condition = contains(["NONE", "AWS_IAM"], …)` — §2.2's "admits exactly two values, refused at plan time" is exact |
| 38 | attempt to verify which SQL role the deployed function connects as: `curl $ORIGIN/v1/health \| grep role`, `POST $ORIGIN/…/checks:materialise`, `evidence/demo/cr-gate/role-probe.json`, `grep -c mainline_api …/GRANTS.yaml` | **not verifiable from outside.** No live response names a SQL role; the `checks:materialise` refusal is the APPLICATION's shared-demo-subject guard, not a grant refusal; `role-probe.json` connects as `root` then `SET ROLE mainline_api` **locally**. `GRANTS.yaml` carries 100 `mainline_api` rows. **One correction made:** §2.2's `never say` asserted the endpoint "runs as a narrow SQL role"; that is a declared and locally-exercised fact, not a measured property of the deployed connection, and the row now says so and bans the clause |
| 39 | `sed -n '26,34p' infra/envs/demo/backend.tf` + `noncurrent_version_expiration_days` default | **One correction made:** §4.1 attributed *"noncurrent versions expiring at 30 days"* to the **state** bucket; the 30-day rule is the **site** bucket's (`demo-site/variables.tf:296`, default `30`). `backend.tf:30` describes the state bucket as versioning on, all public access blocked, SSE-S3, tagged. §4.1 now separates the two buckets |
| 40 | `grep -n DEFAULT_MAX_RESPONSE_BYTES …/static_site.py` vs `evidence/deploy/APPLIED.md:163` | constant is `136 * 1024` in both — **unchanged, ratchet intact** — but APPLIED.md cites `static_site.py:279` and it is now `:323`. Stale citation logged as §6.2b, deliberately not edited |

**Prohibitions honoured.** No `terraform apply`, no redeploy, no AWS mutation, no SSM write, no
credential printed or echoed, no commit, no grant widened, no ratchet touched. Every request above
is a read. `DEFAULT_MAX_RESPONSE_BYTES` is quoted at `136 * 1024` and unchanged. The only file W1
wrote is this one.
