<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `evidence-store` — the COMPLIANCE bucket and the log signing key

The two objects that make a MAINLINE checkpoint something other than a row in a table we
own: an **S3 bucket with Object Lock in COMPLIANCE mode** and an **ECDSA P-256 KMS key**
whose private half has never existed outside an HSM.

> **A hash chain inside a table the adversary owns is a checksum, not evidence.**

This module is the part of the answer that is not code. It is small on purpose, it is
consumed by `infra/envs/evidence` (stack `10-indelible`) and by nothing else, and every
choice in it is one-way.

## GT-18: there is no second chance

Day-1 check **GT-18** has an empty "fallback" column, which is unusual and correct:

- **Object Lock can only be enabled when a bucket is created.** There is no API that
  retrofits it. `aws_s3_bucket_object_lock_configuration` alone does *not* enable it — it
  configures a bucket that already has it.
- **Versioning cannot be suspended** on a bucket with Object Lock, ever.
- **A COMPLIANCE retention cannot be shortened** by anyone, including the account root.

So there is no variable in this module that can turn a control off. No
`object_lock_enabled`, no `enable_versioning`, no `retention_mode`. `retention_years` is
validated at a floor of seven and only moves up. A flag that lets an operator provision
without the control is a flag that produces an unrecoverable bucket at 02:00.

## Usage

```hcl
module "evidence_store" {
  source = "../../modules/evidence-store"

  bucket_name          = "mainline-custody-blk07"
  account_id           = "111122223333"
  region_hint          = "ap-southeast-1"
  signer_role_arn      = aws_iam_role.relay.arn        # the SOLE holder of kms:Sign
  writer_role_arn      = aws_iam_role.relay.arn
  reader_role_arns     = [aws_iam_role.auditor.arn]
  break_glass_role_arn = aws_iam_role.break_glass.arn  # two-person control
}
```

`region_hint` is used **only** to derive the ARN partition; the provider's own region is
authoritative for placement. Supplying `account_id` and deriving the bucket ARN from its
name is what lets the whole stack be *planned with no credentials*, which is what makes
`scripts/custody/check_evidence_plan.py` able to read a real plan on a machine that has
none.

## Three choices a reviewer will want the reason for

### 1. SSE-S3 (`AES256`), not SSE-KMS

AWS states it without hedging: *"if you encrypt your objects with AWS KMS server-side
encryption and your AWS KMS key is deleted your objects may become unreadable."*

A checkpoint note is a **public commitment** — an origin line, a tree size, a base64 root
hash, and a signature. It contains no personal information and nothing confidential. A
customer-managed encryption key would therefore buy no confidentiality at all, and would
add a crypto-shredding surface to the one bucket whose entire purpose is that nothing can
remove its contents. **Encrypting evidence under a deletable key is a delete button with
extra steps.** (ARCHITECTURE.md §11.7 also forbids claiming CMEK on the checkpoint tier,
so the alternative was not available to be claimed either way.)

Rule **OL-5** in the merge gate enforces this.

### 2. `s3:DeleteObject` is denied to *every* principal, not just the writer

A COMPLIANCE-locked object version cannot be deleted. But AWS is explicit that **delete
markers are not WORM-protected, regardless of any retention period or legal hold** — so a
principal with `s3:DeleteObject` can place a delete marker on top of a locked checkpoint
and make the bucket behave, in most ways, as though it were gone.

Hiding the checkpoint is not deleting it, and it works just as well against someone who
does not already suspect. The Deny covers `DeleteObject`, `DeleteObjectVersion`,
`BypassGovernanceRetention`, and the control-plane APIs (`PutBucketVersioning`,
`PutObjectLockConfiguration`, `DeleteBucket`, `PutBucketPolicy`, lifecycle, replication).

### 3. The one grant that looks wrong and is not

The writer role is granted **`s3:PutObjectRetention` and `s3:PutObjectLegalHold`**, which
appear on every list of actions a write principal must not hold — including the one in
`docs/leads/custody.md` CU-10.

They are granted because **S3 requires them in order to send the `x-amz-object-lock-*`
headers on `PutObject` at all.** Banning them outright does not produce a stricter writer;
it produces a writer that cannot lock anything, and a checkpoint object with no explicit
retention, relying entirely on a bucket default that a future operator can weaken for the
*next* object without anyone noticing.

So the grant is **constrained by condition** rather than removed, and the constraint is in
the bucket policy where it binds every principal at once:

| Deny statement | condition | effect on the writer |
|---|---|---|
| `DenyAnyRetentionModeOtherThanCompliance` | `StringNotEquals s3:object-lock-mode = COMPLIANCE` | the only mode it can ever set |
| `DenyAnyRetentionThatIsNotComplianceForTheFullTerm` | `NumericLessThan s3:object-lock-remaining-retention-days = 2555` | the shortest term it can ever set |
| `DenyTurningOffALegalHold` | `StringNotEquals s3:object-lock-legal-hold = ON` | it can turn a hold on and never off |

The writer's entire power over the lock is therefore *"COMPLIANCE, full term, hold ON"*.
Rule **IAM-2** fails the merge if either action is ever granted **without** all three
guards present — so the exception is machine-checked rather than remembered, and a future
edit that drops a Deny fails CI rather than passing review.

This is a **deliberate, narrower reading of CU-10's literal wording**, and it is recorded
as such in `docs/adr/0048-indelible-evidence-stack.md` rather than applied quietly.

## What the gate checks

```sh
python scripts/custody/check_evidence_plan.py            # selftest, 15 rules
python scripts/custody/check_evidence_plan.py check plan.json
```

`OL-1` object lock at creation · `OL-2` versioning · `OL-3` COMPLIANCE ≥ 7 y · `OL-4`
public access blocked · `OL-5` no crypto-shredding surface · `IAM-1` no destructive object
actions · `IAM-2` retention grants constrained · `KMS-1` destruction denied outside
break-glass · `KMS-2` no rotation · `KMS-3` no short deletion window · `KMS-4` P-256
sign-verify · `GT18-1` one checkpoint bucket in the plan · `GT18-2` none anywhere else in
the repository · `PLAN-1` the policies are readable · `DESTROY-1` nothing indelible is
being deleted.

The same rules are shipped in Rego (`infra/policy/custody/*.rego`) for a customer's own
`conftest`/OPA pipeline. **The Rego has never been executed** — `opa` is not installed on
the machine it was written on — and both files say so at the top. The Python gate is the
authoritative one and every rule in it is observed refusing a committed fixture.

## Stated gaps

- **The `legal_hold` half of §11.6 is not here.** ARCHITECTURE.md requires that key
  deletion be denied *"unconditionally while any `legal_hold` row is open"*. That is a
  condition on a **database fact**, which no KMS key policy and no plan-time rule can see.
  It belongs in an organisation-level SCP fed by the custodian patrol and is **not
  implemented by anything in `infra/`**. Saying so is cheaper than being asked.
- **`Deny` + `NotPrincipal` is the sharpest edge in IAM.** A role ARN in `NotPrincipal`
  does not cover the assumed-role *session* ARN in every evaluation context, so the module
  lists both forms. The gate checks that the statement exists and covers both actions; that
  it lists both ARN forms is a review point, not an automated one.
- **Nothing here has been applied.** No AWS credentials are valid on the machine this
  module was written on. `tofu validate` and a full offline `tofu plan` both pass; a live
  `apply` has never run.
- **CloudTrail's destination bucket policy is out of scope**, deliberately: this stack must
  not hold write access to the account that audits it.

## Inputs

| name | type | default | notes |
|---|---|---|---|
| `bucket_name` | `string` | — | Validated as an S3 name, and **rejected** if it contains `bulk`, `audit`, `backup` or `log` — those buckets are GOVERNANCE by design (ARCHITECTURE.md §10.2) and COMPLIANCE on them turns an over-retention mistake into a permanent discovery liability. |
| `retention_years` | `number` | `7` | 7–100. Up only. |
| `signer_role_arn` | `string` | — | The sole holder of `kms:Sign`. |
| `writer_role_arn` | `string` | — | `PutObject`/`GetObject` plus the two condition-bound lock actions. |
| `reader_role_arns` | `list(string)` | `[]` | Read-only verification. |
| `break_glass_role_arn` | `string` | — | The only principal not denied key destruction. |
| `key_administrator_role_arns` | `list(string)` | `[]` | Read and tag only. |
| `kms_alias_name` | `string` | `mainline-log-signing` | Without the `alias/` prefix. |
| `account_id` | `string` | `""` | Skips the STS lookup; makes the break-glass ARN readable in the plan. |
| `region_hint` | `string` | `ap-southeast-1` | ARN partition only. |
| `tags` | `map(string)` | `{}` | `mainline:evidence-class` is set by the module and cannot be overridden. |

## Outputs

`bucket_name` · `bucket_arn` · `bucket_region` · `retention_years` · `kms_key_arn` ·
`kms_key_id` · `kms_alias_arn` · `evidence_tags` · `signing_algorithm`.

**Sign through `kms_key_arn`, never through `kms_alias_arn`.** An alias can be repointed at
a different key, and a checkpoint signed by a different key is an unverifiable checkpoint
that still looks fine.
