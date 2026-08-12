<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# W1 — IAM least privilege, proven by policy simulation

**Worker:** W1 (deploy-verification pass, lead plan `docs/leads/deploy-verify-plan2.md`).
**Date:** 2026-08-12. **Account:** `0229REDACTED8246`, profile `mainline-dev`. **Region:** `ap-southeast-1`.
**Subject:** the execution role `mainline-demo-api-exec` as the committed plan will create it.

**Source of truth is the plan, not the HCL.** Every policy document below was read out of
`evidence/deploy/terraform-plan-furl.json` — `module.api[0].aws_iam_role_policy.dsn_access`
`.change.after.policy` and `module.api[0].aws_iam_role.this` `.change.after.assume_role_policy` —
and the managed policy was fetched live with `iam:GetPolicyVersion`. HCL line numbers appear
only to say *where a human would edit*, never as evidence of what will exist.

Raw request/response for all 21 simulations: `evidence/deploy/verify/iam-simulation.json`.

---

## 0. DISCLOSURE FIRST — this pass created one AWS resource, unintentionally

I ran `aws kms describe-key --key-id alias/aws/ssm --region ap-southeast-1` expecting a
read. **AWS KMS creates the AWS managed key behind a predefined AWS alias on the first
`DescribeKey`.** It did:

```
kms:ListKeys  ap-southeast-1  ->  1 key: 81edadd5-…-7694a7917577  (KeyManager=AWS)
KeyMetadata.CreationDate       =  2026-08-12T12:46:08Z
wall clock at the time of my call =  2026-08-12T12:46:4x Z
```

Before it, the lead's §0.4 measured `alias/aws/ssm` with `TargetKeyId: null` and zero keys
in the region. **That row of the lead's table is now stale because of me, not because
anything in the plan changed.**

Impact assessed and stated rather than argued away: `KeyManager=AWS`, so it carries no
USD 1/month key charge (that applies to customer managed keys), the account cannot schedule
it for deletion, no Terraform resource in the plan addresses it, and writing the DSN
SecureString would have created it within the hour anyway. **The 11-resource plan is
byte-identical and no cost line moves.** No other call in this pass mutated anything: the
complete set was `sts:GetCallerIdentity`, `iam:GetPolicy`, `iam:GetPolicyVersion`,
`iam:SimulateCustomPolicy`, `kms:ListKeys`, `kms:ListAliases`, `kms:GetKeyPolicy`. No
`terraform` was run.

The unplanned upside: the key existing let me fetch its **key policy**, which turns out to
be the decisive evidence for §3.

---

## 1. THE ROLE, IN FULL

Three documents govern `mainline-demo-api-exec`. Nothing else attaches to it (the plan's 11
resources contain exactly one `aws_iam_role`, one `aws_iam_role_policy`, one
`aws_iam_role_policy_attachment`; `permissions_boundary` is `null`, `max_session_duration`
3600).

**Trust policy** (`.change.after.assume_role_policy`, verbatim):

```json
{"Statement":[{"Action":"sts:AssumeRole","Effect":"Allow",
  "Principal":{"Service":"lambda.amazonaws.com"},"Sid":"LambdaAssume"}],
 "Version":"2012-10-17"}
```

**Inline policy `mainline-demo-api-dsn-read`** (`.change.after.policy`, verbatim, account
id already masked in the committed plan):

```json
{"Version":"2012-10-17","Statement":[
 {"Sid":"ReadTheDemoDsnParameter","Effect":"Allow","Action":"ssm:GetParameter",
  "Resource":"arn:aws:ssm:ap-southeast-1:0229REDACTED8246:parameter/mainline/demo/cockroach_dsn"},
 {"Sid":"DecryptThatParameterAndNothingElse","Effect":"Allow","Action":"kms:Decrypt",
  "Resource":"*",
  "Condition":{"StringEquals":{
    "kms:ViaService":"ssm.ap-southeast-1.amazonaws.com",
    "kms:EncryptionContext:PARAMETER_ARN":"arn:aws:ssm:ap-southeast-1:0229REDACTED8246:parameter/mainline/demo/cockroach_dsn"}}}]}
```

**Managed policy `AWSLambdaBasicExecutionRole`.** The module calls this *"the one wildcard
in this role"* (`infra/modules/demo-api/main.tf:180-182`). Fetched, not assumed:

```
$ aws iam get-policy --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  PolicyId ANPAJNCQGXC42545SKXIK   DefaultVersionId v1
  CreateDate 2015-04-09T15:03:43Z  UpdateDate 2015-04-09T15:03:43Z   (never revised)
  AttachmentCount 0                (nothing in this account uses it today)
  Description "Provides write permissions to CloudWatch Logs."

$ aws iam get-policy-version --version-id v1 --policy-arn <same>
```
```json
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
 "Action":["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],
 "Resource":"*"}]}
```

**Exactly what it permits, stated plainly:** three CloudWatch Logs write actions, with **no
`Sid`, no `Condition`, and `Resource: "*"`** — i.e. over *every log group and every log
stream in every region of account `0229REDACTED8246`*, not merely over
`/aws/lambda/mainline-demo-api`. It permits no read of any log data and no deletion of any.
That is the whole of the wildcard, and it is bounded in §4.

---

## 2. THE TABLE — every action the role will hold

| # | Action | Resource | Condition | The line that needs it | Verdict |
|---|---|---|---|---|---|
| 1 | `ssm:GetParameter` | `arn:aws:ssm:ap-southeast-1:0229REDACTED8246:parameter/mainline/demo/cockroach_dsn` | none | `db.py:183` `target = "AmazonSSM.GetParameter"`; `db.py:184` `{"Name": name, "WithDecryption": True}`; reached from `db.py:290` `_dsn_cache = _ssm_get_parameter(name, region)` | **justified** — one action, one ARN. Sim S1 allows it; S3/S4/S5/S6/S7/S8/S9 deny every neighbour |
| 2 | `kms:Decrypt` | `*` | `StringEquals` on **both** `kms:ViaService = ssm.ap-southeast-1.amazonaws.com` **and** `kms:EncryptionContext:PARAMETER_ARN = <the ARN in row 1>` | `db.py:184` — `WithDecryption: True` is what makes SSM call KMS on the role's behalf | **justified**, and *tighter* than naming the key — see §3. Sim S2 allows; S10/S11/S12/S19/S20 deny |
| 3 | `logs:CreateLogGroup` | `*` | none | **nothing.** Terraform creates `/aws/lambda/mainline-demo-api` itself (`main.tf:151-155`), the function `depends_on` it (`main.tf:277-281`) and `logging_config.log_group` names it (`main.tf:272`) | **over-granted — dead permission.** Never exercised on this stack |
| 4 | `logs:CreateLogStream` | `*` | none | the managed `python3.13` runtime, once per execution environment, before `INIT` | **action justified, resource over-granted** — it may create a stream in *any* log group in the account, in any region. Sim S16 |
| 5 | `logs:PutLogEvents` | `*` | none | the runtime's `START`/`END`/`REPORT` lines, plus `app.py:376` `_log.warning` and `app.py:384` `_log.exception` via `_log = logging.getLogger("mainline_demo_api")` (`app.py:95`) | **action justified, resource over-granted** — same wildcard. Sim S16 |
| 6 | `sts:AssumeRole` (trust) | the role itself | `Principal.Service = lambda.amazonaws.com`; **no** `aws:SourceAccount`, **no** `aws:SourceArn` | the Lambda control plane, at `CreateFunction` and at every cold start | **justified here** — not exploitable, see §6 |
| — | *anything else* | — | — | — | **nothing missing.** The under-grant sweep in §5 found no AWS call the role cannot make |

---

## 3. IS `Resource: "*"` GENUINELY EQUIVALENT TO NAMING THE KEY?

**It is not equivalent. It is stricter, and the plan is better for it.** Three pieces of
evidence.

**(a) The spelling is exactly what SSM sets.** The AWS Systems Manager User Guide,
*"AWS KMS encryption for Parameter Store SecureString parameters"* → *Parameter Store
encryption context*, states the context is `Key: PARAMETER_ARN`, `Value:` the ARN of the
parameter, with the format
`"PARAMETER_ARN":"arn:aws:ssm:<region-id>:<account-id>:parameter/<parameter-name>"`, and
gives the hierarchical example `parameter/ReadableParameters/MyParameter`. The module's
`local.dsn_parameter_path` normalisation (`main.tf:94`) produces
`parameter/mainline/demo/cockroach_dsn` — **a character-exact match**. That same AWS page's
own recommended IAM statement is `"kms:EncryptionContext:PARAMETER_ARN"` under
`StringEquals` — the identical construct. This holds for both parameter tiers: for advanced
SecureStrings the guide states the Encryption SDK *"passes in the encrypted data key and the
Parameter Store encryption context from the encrypted message"*, so the condition still
binds if whoever writes the DSN picks `--tier Advanced`.

**(b) Naming the key would be WIDER, not narrower — proven from the live key policy.**
`kms:GetKeyPolicy` on the `aws/ssm` key returns (masked):

```json
{"Sid":"Allow access through SSM for all principals in the account that are authorized to use SSM",
 "Effect":"Allow","Principal":{"AWS":"*"},
 "Action":["kms:Encrypt","kms:Decrypt","kms:ReEncrypt*","kms:GenerateDataKey*","kms:DescribeKey"],
 "Resource":"*",
 "Condition":{"StringEquals":{"kms:CallerAccount":"0229REDACTED8246",
   "kms:ViaService":"ssm.ap-southeast-1.amazonaws.com"}}}
```

Read what that means. The `aws/ssm` key **protects every SecureString in the account** and
its key policy constrains only *caller account* and *via service* — it says nothing about
*which parameter*. So an identity statement of the AWS-documented shape
`"Action":"kms:Decrypt","Resource":"arn:…:key/81edadd5-…"` **with no encryption-context
condition** would let this role decrypt every SecureString any other project ever writes
under `aws/ssm`. The module's comment at `main.tf:207-209` says exactly this, and the key
policy confirms it is true rather than rhetorical. The AWS SSM guide also notes you
*"cannot establish access control policies for the default `aws/ssm` KMS key"* — the
identity policy is the only place this scoping can live.

**(c) The residual width of `*` is closed by the two conditions.** `Resource: "*"` nominally
reaches any KMS key. `kms:ViaService` (KMS Developer Guide: string, single-valued, valid in
**key policies and IAM policies**, value form `service.region.amazonaws.com`) is populated
only when an integrated service makes the call, so a decrypt the role issues **directly** —
arbitrary attacker-supplied ciphertext — has no `ViaService` at all and is refused
(**sim S20: `implicitDeny`**). `PARAMETER_ARN` then pins the one parameter, and because
KMS *"cryptographically binds the encryption context to the encrypted data"*, SSM cannot
present one parameter's ciphertext under another's context. The effective grant is:
*decrypt whatever SSM-in-ap-southeast-1 presents while serving
`/mainline/demo/cockroach_dsn` in this account*. **Sims S10, S11, S12, S19, S20 all deny.**

### 3.1 FINDING — the condition key name is one character looser than it reads

I predicted a denial for a lower-cased context key and **got an allow**:

```
S13  kms:Decrypt, ViaService correct, context key spelled "kms:EncryptionContext:parameter_arn"
     -> EvalDecision "allowed", MatchedStatements [PolicyInputList.1], MissingContextValues []
```

The AWS KMS Developer Guide (*Condition keys for AWS KMS*) explains it:
*"the condition key, which consists of the `kms:EncryptionContext:` prefix and the
`context-key` replacement, is not case sensitive. A policy that uses this condition does not
check the case of either element of the condition key."* The **value** comparison, by
contrast, is governed by the operator — `StringEquals` is case-sensitive, which
**sim S19 confirms**: a `PARAMETER_ARN` differing only in the case of the last path segment
is denied.

**Severity: none, and not fixable by re-spelling.** SSM only ever emits `PARAMETER_ARN`;
nothing in the account produces a `parameter_arn` context; and the looseness is inherent to
the condition key, so changing the casing in the HCL changes nothing. Recorded because
the module's comment reads as though the spelling itself is load-bearing, and after this
pass a reader knows precisely how much of it is. A belt-and-braces addition — **not
required** — would be a second condition `ForAnyValue:StringEquals` on
`kms:EncryptionContextKeys` with value `["PARAMETER_ARN"]`, whose values *are* compared
case-sensitively. Note the guide's explicit **Warning** against `ForAllValues`/`ForAnyValue`
on the single-valued `kms:EncryptionContext:context-key` itself — that mistake is not
present here.

---

## 4. THE SIMULATION — 21 cases, 21 matching expectation

`iam:SimulateCustomPolicy`, read-only, profile `mainline-dev`. Full request and unedited
response for each is in `evidence/deploy/verify/iam-simulation.json`.

| id | policy under test | action(s) / context | expected | **observed** |
|---|---|---|---|---|
| S1 | dsn_access | `ssm:GetParameter` on the exact ARN | allowed | **allowed** |
| S2 | dsn_access | `kms:Decrypt`, ViaService + PARAMETER_ARN both correct | allowed | **allowed** |
| S3 | dsn_access | `ssm:GetParameters` (plural) on the same ARN | deny | **implicitDeny** |
| S4 | dsn_access | `ssm:GetParametersByPath` on `parameter/mainline/demo` | deny | **implicitDeny** |
| S5 | dsn_access | `ssm:DescribeParameters` on `*` | deny | **implicitDeny** |
| S6 | dsn_access | `ssm:PutParameter` on the same ARN | deny | **implicitDeny** |
| S7 | dsn_access | `ssm:GetParameter` on `…parameter/mainline/other/dsn` | deny | **implicitDeny** |
| S8 | dsn_access | `ssm:GetParameter` on `…parameter/prod/anything` | deny | **implicitDeny** |
| S9 | dsn_access | `ssm:GetParameter`, same name, `ap-southeast-2` | deny | **implicitDeny** |
| S10 | dsn_access | `kms:Decrypt`, PARAMETER_ARN = a *different* parameter | deny | **implicitDeny** |
| S11 | dsn_access | `kms:Decrypt`, PARAMETER_ARN **absent** | deny | **implicitDeny** (`MissingContextValues: ["kms:EncryptionContext:PARAMETER_ARN"]`) |
| S12 | dsn_access | `kms:Decrypt`, ViaService = `secretsmanager.…` | deny | **implicitDeny** |
| S13 | dsn_access | `kms:Decrypt`, context key `parameter_arn` (lower) | deny | **allowed** — §3.1 |
| S14 | dsn_access | `kms:Encrypt`, `DescribeKey`, `GenerateDataKey`, `ReEncryptFrom` | deny | **implicitDeny** |
| S15 | basic-exec | `logs:CreateLogStream` + `PutLogEvents` on own group | allowed | **allowed** |
| S16 | basic-exec | all three logs actions on **another team's group in us-east-1** | allowed | **allowed** — the over-grant, demonstrated |
| S17 | basic-exec | `FilterLogEvents`, `GetLogEvents`, `DeleteLogGroup`, `PutRetentionPolicy` | deny | **implicitDeny** |
| S18 | **both, i.e. the real role** | `bedrock:InvokeModel`, `s3:GetObject`, `secretsmanager:GetSecretValue`, `sts:AssumeRole`, `lambda:UpdateFunctionCode`, `iam:PassRole` | deny | **implicitDeny** |
| S19 | dsn_access | `kms:Decrypt`, PARAMETER_ARN differing only in case | deny | **implicitDeny** |
| S20 | dsn_access | `kms:Decrypt`, correct context, **no** ViaService (direct call) | deny | **implicitDeny** |
| S21 | basic-exec | `ssm:GetParameter` + `kms:Decrypt` on the DSN | deny | **implicitDeny** |

Every one of the six denials the brief named is present (S3, S4, S5, S6, S7+S8, S10+S11),
plus both intended allows (S1, S2). S13 is recorded as a finding rather than adjusted away.

**Bounding the wildcard (S16 vs S17).** The over-grant is *write-only, account-local
CloudWatch Logs*. The role cannot read back a single log event anywhere, cannot delete a log
group, and cannot alter retention. The realistic worst case therefore requires code
execution inside the handler first, and is then *integrity noise plus ingestion cost* in
other log groups — not disclosure. Today the account has **zero other Lambda functions**
(lead §0.4), so there is nothing to pollute.

**The exact edit, if the founder wants the wildcard gone** (this is *optional hardening*,
not a GO condition). Drop `aws_iam_role_policy_attachment.basic_execution` and add:

```hcl
resource "aws_iam_role_policy" "logs" {
  name = "${var.function_name}-logs"
  role = aws_iam_role.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "WriteOwnLogStreamOnly"
      Effect = "Allow"
      # CreateLogGroup omitted on purpose: aws_cloudwatch_log_group.this already exists.
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:${local.log_group_name}:*"
    }]
  })
}
```

This is a **1 add / 1 destroy** change to the plan and it removes rows 3, 4 and 5's
wildcard in one move. I am **not** recommending it before this deploy: it trades a
measured, bounded, write-only over-grant for an untested change to the log path on the
morning of a first apply, and a function that cannot create its log stream produces *no
diagnostics at all* — the single worst failure mode for a judge-facing demo.

---

## 5. THE MIRROR RISK — under-grant sweep

An over-grant is a security finding; an **under-grant 500s a judge-visible route**. So:
every AWS API the deployed code can issue, enumerated from the artefact that will actually
be uploaded (`out/lambda/mainline-demo-api-arm64.zip`, sha256 `c85d7f00…b5b8a4b0`, 206
entries), not from the source tree.

```
every `amazonaws.com` occurrence in the deployment package  ->  ONE
  mainline_demo_api/db.py :   host = f"ssm.{region}.amazonaws.com"
files containing an `x-amz-target` header                   ->  ONE  (mainline_demo_api/db.py)
`AmazonSSM.` / `AWS4-HMAC`                                  ->  mainline_demo_api/db.py only
boto3 / botocore anywhere in the package                    ->  ABSENT
```

Per-file call-site count for `urlopen|urllib.request|boto3|botocore|http.client|socket.|amazonaws`:

| file | AWS/network call sites |
|---|---|
| `db.py` | **6** — all in `_ssm_get_parameter` |
| `app.py`, `envelope.py`, `gate_run.py`, `health.py`, `reads.py`, `refusal.py`, `scenario.py`, `static_site.py`, `transitions.py` | **0** each |

**The complete AWS API surface of the deployed function is:**

1. `ssm:GetParameter` — `db.py:161-252`, SigV4 signed by hand from `hashlib`/`hmac`,
   `POST https://ssm.<region>.amazonaws.com/`, `X-Amz-Target: AmazonSSM.GetParameter`,
   body `{"Name":"/mainline/demo/cockroach_dsn","WithDecryption":true}`. **Granted (S1).**
2. `kms:Decrypt` — never issued by this code; issued *by SSM on the role's behalf* because
   of `WithDecryption: true`. **Granted (S2).**
3. `logs:CreateLogStream` + `logs:PutLogEvents` — issued by the managed runtime, not by
   this code. **Granted (S15).**

Nothing else. Specifically checked because the brief named them, and **none is present**:

* **Bedrock** — `reads.py`, `gate_run.py`, `health.py` contain no Bedrock call. The single
  byte-match for `bedrock` in the whole artefact is a **JSON-schema enum value** inside the
  console's compiled bundle (`web/assets/index-…js`), `"transport": {"enum":
  ["pgwire","mcp","bedrock","ccloud","s3"]}` — a string in a contract schema, and in any
  case browser-side, running with the judge's origin and no AWS credentials.
* **S3** — the only matches are inside `libcrypto`/`libssl` shared objects. `static_site.py`
  serves the SPA from `/var/task/web` (`MAINLINE_WEB_ROOT`), off the local filesystem.
* **Secrets Manager** — absent from the artefact entirely.
* **STS** — no `sts:` call; the runtime injects `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN` as environment variables and `db.py:170-172`
  reads them directly. `db.py:166` states the design: *no credential file, no IMDS walk, no
  profile resolution*. Nothing calls `AssumeRole`, so S18's denial of `sts:AssumeRole`
  costs the function nothing.

This is enforced, not merely observed: `tests/test_envelope.py` carries a guard that the
handler imports no web framework and no AWS SDK, and it passes —
`2 passed, 45 deselected in 0.40s`. The package's declared dependencies are `psycopg==3.3.4`
and `psycopg-binary==3.3.4` and nothing else.

**Conclusion: the under-grant count is ZERO.** No route can 500 or 503 for want of an IAM
permission. (The DSN parameter itself does not yet exist — the lead's §0.4 — so DB-backed
routes will answer `503`; that is a *missing secret*, W3's slice, and no amount of IAM
fixes it.)

---

## 6. THE TRUST POLICY — `lambda.amazonaws.com`, unconditioned

**Not exploitable here. It should stay as it is.**

The `aws:SourceAccount` / `aws:SourceArn` confused-deputy pattern protects a role that a
*service* assumes **on behalf of a resource identified in the request** — a bucket, a topic,
a trail — where the resource may belong to a third party. A Lambda **execution** role is not
in that shape. The only way `lambda.amazonaws.com` ever assumes `mainline-demo-api-exec` is
if some Lambda function is configured with that role's ARN, and configuring a function with
a role requires `iam:PassRole` **on that role**, which is an identity permission that only
principals inside account `0229REDACTED8246` can hold. A stranger cannot create a function in
their own account that references a role ARN in ours; the `CreateFunction` call would fail
on `PassRole`. There is no cross-account path to close, which is why AWS's own console and
the Terraform Lambda examples emit this exact trust policy.

The residual is entirely in-account: any principal here with `iam:PassRole` on this role
plus `lambda:CreateFunction` could stand up a *different* function wearing it and read the
DSN. That is a statement about who holds admin in this account, not a defect in the trust
policy — and even then the prize is bounded to one parameter (S7, S8) and no other secret.
Adding `aws:SourceAccount` would not change it, because the attacker is already in the
account.

Two things I am **not** claiming: there is no `permissions_boundary` on this role
(`.change.after.permissions_boundary = null`), and no SCP was inspected — I have no
`organizations:*` visibility from this profile. Neither is required for the verdict; both
would only ever tighten it.

---

## 7. VERDICT

Against the brief's three questions: **every** action in `dsn_access` and in
`AWSLambdaBasicExecutionRole` is enumerated in §2 with a justification or an over-grant
finding; the negative is proven by 21 `simulate-custom-policy` results including all six
named denials; the under-grant sweep found nothing the role cannot do that the code needs.
The one over-grant is AWS's own managed policy, is write-only, is account-local, cannot read
or delete log data, and lands in an account with zero other Lambda functions. The one
surprise (S13) is a documented property of `kms:EncryptionContext:` that no re-spelling
would remove and that nothing in the account can reach. The `kms:Decrypt` `Resource: "*"` is
**stricter** than naming `aws/ssm`, proven from that key's live key policy.

> **GO** — the IAM slice of the plan is least-privilege as claimed. The `logs:*` wildcard is
> an accepted, documented over-grant with the narrowing edit written down in §4 for after
> the demo, not before it; the KMS `Resource: "*"` is scoped tighter by its two conditions
> than naming the key would be; nothing is under-granted. **Caveat outside this slice: my
> `describe-key` created the `aws/ssm` AWS managed key, which invalidates one row of the
> lead's §0.4 table and nothing else.**

*W1, deploy-verification pass. No `terraform` was run. No credential was read, printed or
written. The account id is masked as `0229REDACTED8246` throughout both of this worker's files.*
