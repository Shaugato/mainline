<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `10-indelible` — the root module with no destroy path

Stack `10-indelible` from ARCHITECTURE.md §10.3. It provisions, **in a second AWS
account**, the S3 Object Lock COMPLIANCE bucket, the ECDSA P-256 log signing key, and a
CloudTrail that delivers to a **third** account.

```
application account            evidence account            log-archive account
  writes checkpoints    ──►      holds them, forever   ──►    records who touched either
  (20-platform, 30-app)          (THIS STACK)                 (out of scope here)
```

Three accounts and not two. A trail whose objects the traced account can delete records
exactly as much as its subject chooses.

## `just destroy` does not reach this stack

**Ruling CU-11.** The refusal is enforced in three places, on purpose, because a single
guard is a guard somebody walks past at 02:00.

1. **`lifecycle { prevent_destroy = true }`** on every resource here and in
   `infra/modules/evidence-store`. `tofu destroy` fails with *"Instance cannot be
   destroyed"* and names the resource.
2. **`python scripts/custody/check_evidence_plan.py destroy-guard`** — exits `2` and prints
   the reason. This is what a `just` recipe calls, so the refusal has a message a human
   reads rather than a Terraform error a human greps. Rule **DESTROY-1** additionally fails
   the merge if any plan schedules a delete on an indelible resource.
3. **S3 Object Lock COMPLIANCE itself.** With (1) and (2) both removed, the bucket still
   cannot be emptied and therefore cannot be deleted, by anyone, including the account
   root.

Only (3) is a control. (1) and (2) exist so that whoever would have discovered (3) the hard
way discovers it in a plan instead.

The recipe the root `justfile` should carry (that file is the kernel toolchain worker's, so
this is a request rather than an edit):

```make
# Stack 10-indelible has no destroy path. CU-11.
evidence-destroy:
    @python scripts/custody/check_evidence_plan.py destroy-guard

# The merge gate. Runs with no credentials and no network.
evidence-gate:
    @python scripts/custody/check_evidence_plan.py
```

**Why a rebuilt KMS key is the same offence as destruction.** Deleting the signing key does
not delete one checkpoint; it makes *every checkpoint ever signed by it* unverifiable at
once. Nobody has to touch the ledger. The ledger simply stops being evidence, and the only
people who find out are the ones who tried to rely on it. BUILD_PLAN.md K6's "fails how"
column says this in four words: **reuse the KMS key across rebuilds.**

## Usage

```sh
cd infra/envs/evidence
tofu init -backend-config=…            # state bucket comes from 00-bootstrap
tofu plan -out=tfplan.bin \
  -var site_code=blk07 \
  -var account_id=<evidence account> \
  -var evidence_account_role_arn=arn:aws:iam::<evidence account>:role/provisioner \
  -var signer_role_arn=… -var writer_role_arn=… -var break_glass_role_arn=… \
  -var cloudtrail_bucket_name=<bucket in the log-archive account>

tofu show -json tfplan.bin > plan.json
python ../../../scripts/custody/check_evidence_plan.py check plan.json   # MERGE GATE
tofu apply tfplan.bin
```

The gate runs **before** apply, and GT-18 is why: Object Lock and versioning cannot be
retrofitted, so a plan that is wrong here is a bucket that has to be abandoned rather than
fixed.

## State encryption — required, and not in this file

ARCHITECTURE.md §10.3 requires OpenTofu **state and plan** encryption with the `aws_kms`
key provider and `enforced = true`. That is an OpenTofu-only `terraform { encryption { … } }`
block, and HashiCorp Terraform rejects it as an unsupported block type. The only validator
available on the machine this module was written on is HashiCorp Terraform 1.14, so
shipping the block here would mean shipping a root module nobody could validate.

It is therefore specified here and added at deployment time alongside the backend
configuration, which the cloud lead owns:

```hcl
terraform {
  encryption {
    key_provider "aws_kms" "state" {
      kms_key_id = var.state_kms_key_arn
      region     = var.region
      key_spec   = "AES_256"
    }

    method "aes_gcm" "state" {
      keys = key_provider.aws_kms.state
    }

    state {
      method   = method.aes_gcm.state
      enforced = true
    }

    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}
```

`enforced = true` in both blocks is the load-bearing part: without it, OpenTofu falls back
to writing plaintext state when the key provider is unavailable, which is the failure mode
that makes people believe their state is encrypted when it is not.

**A plan file for this stack is sensitive** even though the resources are not: it contains
the full IAM policy documents and the break-glass role ARN.

## Region, said precisely

The default is `ap-southeast-1` (Singapore), following the cluster. REGION PIN
(ARCHITECTURE.md §10.1) requires kernel, custody and the database to share a region, and
the platform ground truth (`docs/adr/0002-g1-platform-ground-truth.md`) records that the
demo cluster is Basic-tier in `aws-ap-southeast-1` while Bedrock inference runs in
`ap-southeast-2` (Sydney).

> **Any claim of end-to-end Australian data residency is FALSE for this deployment.**
> Inference is in Australia. On the free demo tier the database is not, and neither is this
> evidence store by default. A customer install moves kernel, memory and custody together
> by changing one variable, and says so in the same sentence.

`mainline_anchor.aws.assert_region` asserts the pin at process start-up against the
`anchor_environment` output, so a mismatch is a refusal to serve rather than a latency
mystery.

## Outputs

`bucket_name` · `bucket_arn` · `kms_key_arn` · `retention_years` · `cloudtrail_arn`, plus
`anchor_environment` — the four values `mainline_anchor` reads, emitted as one object so
that a deployment cannot wire three of the four correctly.

## Stated gaps

- **Never applied.** No AWS credentials are valid on the machine this was written on.
  `tofu validate` passes, a full offline `tofu plan` succeeds, and
  `infra/policy/custody/fixtures/plan_compliant.json` is the byte-for-byte output of that
  plan. A live `apply` has never run.
- **The CloudTrail destination bucket policy is the log-archive account's**, deliberately.
  That bucket must allow `cloudtrail.amazonaws.com` to write with
  `s3:x-amz-acl = bucket-owner-full-control`; this stack must not hold write access to the
  account that audits it.
- **A bucket with Object Lock cannot be a destination for S3 server access logs.** Access
  logging for the checkpoint bucket, if wanted, goes to a different bucket in the
  log-archive account. Not configured here.
- **The `legal_hold` SCP is not implemented anywhere.** §11.6 requires that key deletion be
  denied unconditionally while any `legal_hold` row is open. That is a condition on a
  database fact; it belongs in an organisation SCP fed by the custodian patrol, and no file
  in `infra/` implements it today.
