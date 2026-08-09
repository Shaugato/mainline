<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Evidence-plan fixtures — one deliberately-broken plan per rule

**A gate nobody has watched refuse anything is a gate that asserts nothing.** That is PL-2
applied to policy-as-code: the merge gate in `scripts/custody/check_evidence_plan.py`
exists to stop a plan that would provision an evidence store which is not indelible, and
the only evidence that it *would* stop one is that it is observed stopping fifteen of them.

```sh
python scripts/custody/check_evidence_plan.py
```

That command is the whole harness. It asserts, in one run, that

1. `plan_compliant.json` **passes every rule**, and
2. each `plan_broken_*.json` is **refused by the rule that declares it**, and
3. each broken fixture is **surgical** — it trips one rule and not three, because a
   mutation that trips three proves that *something* failed, not that this rule works, and
   the harness prints `(also tripped …)` when it is not.

## Where the compliant fixture came from

`plan_compliant.json` is the **byte-for-byte, unedited output of `terraform show -json`**
over the real `infra/envs/evidence` root module. It is not hand-written, and that matters:
a synthetic fixture drifts from the shape the tool actually emits, and the day it drifts
the gate starts passing plans it has never seen.

It was produced **with no AWS credentials**, which is possible because two design choices
in the module make the whole stack plannable offline:

- `var.account_id` short-circuits the `aws_caller_identity` data source, so no STS call is
  made; and
- the bucket ARN in the policy documents is **derived from the bucket name** (an S3 bucket
  ARN is `arn:<partition>:s3:::<name>` — it carries no account and no region) rather than
  read off `aws_s3_bucket.evidence.arn`. Without that, every statement in the bucket policy
  would be *"known after apply"* on a first-apply plan, and a merge gate cannot read a
  policy that does not exist yet. Rule **PLAN-1** exists to make that failure loud rather
  than silent, and `plan_broken_plan1_unresolved_policy.json` is what it looks like.

To reproduce it (the provider block is overridden only so that the plan runs with no
credentials and no remote state; nothing about the resources changes):

```sh
cd infra/envs/evidence
cat > zz_offline_override_override.tf <<'HCL'
terraform { backend "local" {} }
provider "aws" {
  region                      = var.region
  access_key                  = "AKIAIOSFODNN7EXAMPLE"
  secret_key                  = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  skip_region_validation      = true
}
HCL
tofu init -reconfigure
tofu plan -refresh=false -out=tfplan.bin \
  -var site_code=blk07 \
  -var account_id=111122223333 \
  -var signer_role_arn=arn:aws:iam::111122223333:role/mainline-relay \
  -var writer_role_arn=arn:aws:iam::111122223333:role/mainline-relay \
  -var break_glass_role_arn=arn:aws:iam::111122223333:role/mainline-break-glass \
  -var cloudtrail_bucket_name=mainline-org-trail-archive \
  -var 'reader_role_arns=["arn:aws:iam::111122223333:role/mainline-auditor"]'
tofu show -json tfplan.bin > ../../policy/custody/fixtures/plan_compliant.json
rm zz_offline_override_override.tf tfplan.bin
```

The account id, the role ARNs and the bucket name are all fictitious. `111122223333` is
one of AWS's own documentation account numbers.

## Where the broken fixtures came from

Each is a **mutation of the compliant plan**, declared in code in
`scripts/custody/check_evidence_plan.py` under `MUTATIONS`, so a reader can see in one
place exactly what makes each fixture bad. They are trimmed to the four keys the gate reads
(`format_version`, `terraform_version`, `planned_values`, `resource_changes`) and minified,
because a quarter-megabyte of duplicated plan per rule is a repository nobody clones.

They are **generated and committed**, not generated at test time, and CI asserts zero
diff:

```sh
python scripts/custody/check_evidence_plan.py regen-fixtures --check
```

| fixture | rule | what was changed, and why that is the realistic failure |
|---|---|---|
| `plan_broken_ol1_no_object_lock.json` | **OL-1** | `object_lock_enabled = false`. The bucket is created without the control and there is no API that adds it later. This is GT-18's one-shot, missed. |
| `plan_broken_ol2_versioning_suspended.json` | **OL-2** | Versioning `Suspended`. Object Lock needs versioning; without it an overwrite *is* a deletion. |
| `plan_broken_ol3_governance_one_year.json` | **OL-3** | `GOVERNANCE`, one year. The copy-paste from a backup bucket — it looks locked and any principal with `s3:BypassGovernanceRetention` can remove it. |
| `plan_broken_ol4_public_policy_allowed.json` | **OL-4** | `block_public_policy = false`. One of the four, off. |
| `plan_broken_ol5_sse_kms.json` | **OL-5** | SSE-KMS under a customer key. AWS: *"if… your AWS KMS key is deleted your objects may become unreadable."* A delete button with extra steps, on the one bucket that is supposed to have none. |
| `plan_broken_iam1_writer_can_delete.json` | **IAM-1** | `s3:DeleteObject` appended to the writer's Allow — *"it needs to clean up its own failed uploads"*. It also needs to be unable to: a delete marker hides a locked version, and delete markers are not WORM-protected. |
| `plan_broken_iam2_unconstrained_retention.json` | **IAM-2** | The `s3:object-lock-mode` Deny removed, leaving `s3:PutObjectRetention` granted unconditionally — the power to write a one-day GOVERNANCE retention over an object that should have had seven COMPLIANCE years. |
| `plan_broken_kms1_destruction_ungated.json` | **KMS-1** | The `Deny`/`NotPrincipal` statement removed. Key destruction becomes reachable by ordinary account administration. |
| `plan_broken_kms2_rotation_enabled.json` | **KMS-2** | `enable_key_rotation = true` — a no-op on an asymmetric key that tells a reader the key is being rotated. |
| `plan_broken_kms3_seven_day_window.json` | **KMS-3** | A seven-day deletion window. Three weeks of notice traded for nothing. |
| `plan_broken_kms4_symmetric_key.json` | **KMS-4** | `SYMMETRIC_DEFAULT` / `ENCRYPT_DECRYPT`. The key cannot sign at all; C2SP note type `0x02` is ECDSA P-256 only. |
| `plan_broken_gt18_two_buckets.json` | **GT18-1** | A second checkpoint bucket in the same plan. Two places a stranger is told to look. |
| `plan_broken_plan1_unresolved_policy.json` | **PLAN-1** | The bucket policy as `"known after apply"`. The gate refuses rather than shrugging — this is the failure mode where a policy check silently checks nothing. |
| `plan_broken_destroy1_key_deleted.json` | **DESTROY-1** | The CloudTrail planned for deletion. (The trail and not the KMS key, deliberately: a delete plan has `after: null`, so deleting the key would also trip KMS-4 and PLAN-1 and the fixture would prove that *something* failed rather than that DESTROY-1 works.) |
| `foreign_bucket.tf.fixture` | **GT18-2** | A second team's root module declaring "a bucket for the checkpoints" six weeks later, Object Lock configured almost right. Not a `.tf`: a fixture that participates in the build is not a fixture, so `tofu` never reads it and `terraform fmt` never rewrites it. The selftest copies it into a scratch tree and scans there. |

## What these fixtures do **not** prove

They prove the **gate** works. They do not prove **AWS** works.

No live AWS call has been made from the machine that produced them. That every rule here
corresponds to a control S3 and KMS actually enforce is an argument from the AWS
documentation — cited inline in `infra/modules/evidence-store/main.tf` — and not a
measurement. The `--live` flag on the gate reports `SKIP(no-credentials)`, printed as
loudly as a `FAIL`, and attack **A15** (`object_lock_downgrade`) in
`spec/custody/attacks.yaml` is likewise reported `SKIP(no-credentials)` and never silently
absent.

Deliberately **not `moto`** (ruling CU-10): its Object Lock enforcement is incomplete, and
a green test against a mock that does not enforce the control is worse than no test,
because it converts an unproven property into a believed one.
