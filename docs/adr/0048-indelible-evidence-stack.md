<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0048 — CU-11: the indelible evidence stack has no destroy path

**Status:** Accepted · **Date:** 2026-08-10 · **Decider:** custody lead · **Milestone:** K2 / K6
**Supersedes:** nothing · **Implements:** `docs/leads/custody.md` §2 decisions **CU-10** and **CU-11**
**Depends on:** ADR 0041 (checkpoint wire format), ADR 0043 (log signature, ECDSA P-256 note type `0x02`)
**Implemented by:** `infra/modules/evidence-store/` · `infra/envs/evidence/` ·
`infra/policy/custody/*.rego` · `scripts/custody/check_evidence_plan.py` ·
`verticals/mainline/packages/mainline-anchor/`

## Context

ARCHITECTURE.md §7.3 step 3 puts the signed checkpoint into *"S3 Object Lock COMPLIANCE,
versioned bucket, separate AWS account, 7-year default retention plus Legal Hold"*, and
§11.6 states that *"crypto-shredding is document destruction"* — the KMS key policy denies
`ScheduleKeyDeletion` and `DisableKey` to every principal except a two-person break-glass
role, and the demo/prod split reuses the key across rebuilds, because **a recreated key
means yesterday's ledger is unreadable, which is the same offence committed by accident**.

Day-1 check **GT-18** is the one entry in §19 whose fallback column is empty:

> Object Lock bucket created **COMPLIANCE + versioning before any other Terraform runs**;
> backup retention set **once** at provisioning. *Fallback: none — get it right the first
> time.*

That is not rhetoric. Three facts make this configuration a one-shot:

1. **Object Lock can only be enabled when a bucket is created.** No API retrofits it, and
   `aws_s3_bucket_object_lock_configuration` configures a bucket that already has it rather
   than enabling it.
2. **Versioning cannot be suspended** on a bucket with Object Lock, ever.
3. **A COMPLIANCE retention cannot be shortened** by anyone, including the account root.

Three further facts shape everything below, and each of them is a way the obvious
implementation is wrong:

4. **`PutObject` succeeds against a bucket with no Object Lock configuration.** The
   `x-amz-object-lock-*` parameters are accepted and silently ignored; you get an ordinary,
   deletable object and a `200`. **Asking for COMPLIANCE is not evidence of COMPLIANCE.**
5. **Delete markers are not WORM-protected.** A locked object version cannot be deleted,
   but a delete marker can be placed on top of it, after which S3 behaves in most ways as
   though the object is gone. *Hiding is not deleting and works just as well on a reader
   who does not already suspect.*
6. **`s3:PutObjectRetention` and `s3:PutObjectLegalHold` are required merely to SEND the
   lock headers on `PutObject`.** They are not only the standalone-API permissions.

## Decision

### 1 · The evidence stack is a separate OpenTofu root module and `just destroy` cannot reach it

`infra/envs/evidence` is stack `10-indelible`. Teardown touches only `20-platform` and
`30-app`. The refusal is enforced in **three** places, because a single guard is a guard
somebody walks past at 02:00:

| # | mechanism | what it produces |
|---|---|---|
| 1 | `lifecycle { prevent_destroy = true }` on every resource | `tofu destroy` fails and names the resource |
| 2 | `check_evidence_plan.py destroy-guard` (exit 2) and rule `DESTROY-1` | a message a human reads, and a merge that fails if a plan schedules the delete |
| 3 | S3 Object Lock COMPLIANCE itself | with 1 and 2 removed, the bucket still cannot be emptied |

**Only 3 is a control.** 1 and 2 exist so that whoever would have discovered 3 the hard way
discovers it in a plan instead.

### 2 · The controls are proven over `tofu show -json`, never over `moto` (CU-10)

`scripts/custody/check_evidence_plan.py` is a stdlib-only merge gate carrying **fifteen
rules**, each with a stable id, a one-line reason and **at least one committed,
deliberately-broken plan fixture that it and only it refuses**:

`OL-1` object lock at creation · `OL-2` versioning · `OL-3` COMPLIANCE ≥ 7 years · `OL-4`
public access blocked · `OL-5` no crypto-shredding surface · `IAM-1` no destructive object
actions · `IAM-2` retention grants constrained · `KMS-1` destruction denied outside
break-glass · `KMS-2` no rotation · `KMS-3` no short deletion window · `KMS-4`
P-256/SIGN_VERIFY · `GT18-1` one checkpoint bucket in the plan · `GT18-2` none anywhere else
in the repository · `PLAN-1` the policies are readable · `DESTROY-1` nothing indelible is
being deleted.

`moto` is refused because its Object Lock enforcement is incomplete: **a green test against
a mock that does not enforce the control is worse than no test**, since it converts an
unproven property into a believed one. The same rules are shipped in Rego for a customer's
own `conftest`/OPA pipeline — and both `.rego` files state in their header that **they have
never been executed**, because `opa` is not installed here.

### 3 · The plan must be READABLE, so the module derives ARNs from inputs

An S3 bucket ARN is `arn:<partition>:s3:::<name>` — no account, no region. Referencing
`aws_s3_bucket.evidence.arn` in the policy document would make every statement *"known
after apply"* on a first-apply plan, and **a merge gate cannot read a policy that does not
exist yet**. The module therefore derives the ARN from `var.bucket_name` and takes
`var.account_id` rather than calling `aws_caller_identity`.

Two consequences, both wanted: the break-glass `NotPrincipal` ARN is a constant a reviewer
reads off the plan, and the whole stack **plans offline with no AWS credentials at all** —
which is how `infra/policy/custody/fixtures/plan_compliant.json` came to be the
byte-for-byte output of a real `tofu show -json` rather than a hand-written imitation.

Rule `PLAN-1` makes the alternative loud: a policy the gate cannot read is a `FAIL`, never
a skip.

### 4 · SSE-S3, not SSE-KMS, on the checkpoint bucket

AWS: *"if you encrypt your objects with AWS KMS server-side encryption and your AWS KMS key
is deleted your objects may become unreadable."*

A checkpoint note is a public commitment carrying no personal information, so a
customer-managed encryption key buys no confidentiality here and adds a crypto-shredding
surface to the one bucket whose entire purpose is that nothing can remove its contents.
**Encrypting evidence under a deletable key is a delete button with extra steps.**
(ARCHITECTURE.md §11.7 forbids claiming CMEK on the checkpoint tier in any case.) Rule
`OL-5`.

### 5 · A NARROWER READING OF CU-10's LITERAL WORDING, recorded rather than applied quietly

CU-10 says the gate must fail if *"any principal in the write account holds
`s3:DeleteObject*`, `s3:PutObjectRetention`, `s3:PutObjectLegalHold` or
`s3:BypassGovernanceRetention`"*.

Fact 6 above makes the literal reading self-defeating: a writer without
`s3:PutObjectRetention` and `s3:PutObjectLegalHold` **cannot send the lock headers at
all**. Banning them does not produce a stricter writer. It produces a writer whose objects
carry no explicit retention, relying entirely on a bucket default that a future operator
can weaken for the *next* object without anyone noticing — and it makes the anchor's
`PutObject` fail with `AccessDenied` on the first live call.

**Ruling.** The gate splits the list in two:

- **`IAM-1` — unconditional.** `s3:DeleteObject`, `s3:DeleteObjectVersion`,
  `s3:BypassGovernanceRetention`, `s3:PutBucketVersioning`, `s3:PutObjectLockConfiguration`,
  `s3:DeleteBucket`, `s3:DeleteBucketPolicy` are refused for **any** `Allow`, to **any**
  principal, in any form — wildcards (`s3:*`, `s3:Delete*`) expanded, because a gate that
  compared exact strings would pass `s3:*`, which is the most common way this control is
  actually lost.
- **`IAM-2` — conditional.** `s3:PutObjectRetention` and `s3:PutObjectLegalHold` may be
  granted **only** alongside three bucket-policy `Deny` statements that pin them:
  `s3:object-lock-mode StringNotEquals COMPLIANCE`,
  `s3:object-lock-remaining-retention-days NumericLessThan 2555`, and
  `s3:object-lock-legal-hold StringNotEquals ON`. Missing any one is a merge failure naming
  which.

The writer's whole power over the lock is then *"COMPLIANCE, full term, hold ON"* — which
is **stronger** than CU-10's literal reading, because under it the retention is set
explicitly per object *and* cannot be set wrongly, rather than being absent and inherited.

This is a deviation from a lead ruling's wording in service of its intent. It is recorded
here, in the module README, and in the gate's own failure message, and it is machine-checked
rather than remembered: a future edit that drops a `Deny` fails CI rather than passing
review.

### 6 · Every external system in the anchor is a `typing.Protocol` whose fake asserts the call shape

`verticals/mainline/packages/mainline-anchor` runs one anchoring pass in six steps —
**beacon → sign → object lock → timestamp → publish tiles → push to witnesses** — and every
external system behind it (`KmsSignPort`, `ObjectLockPort`, `TsaPort`, `BeaconPort`,
`TilePublishPort`, `WitnessPushPort`) is a Protocol with an in-process fake. `boto3` is
never imported; the client is injected.

The fakes **refuse** a wrong call rather than recording one:
`ObjectLockMode='COMPLIANCE'`, `ObjectLockLegalHoldStatus='ON'`, a timezone-aware
`RetainUntilDate` seven years out, `SigningAlgorithm='ECDSA_SHA_256'`, `MessageType='RAW'`
— each asserted as a **literal** in the test, never imported from the code under test, so
that changing `OBJECT_LOCK_MODE` to `"GOVERNANCE"` fails rather than passes. Risk 3 in
`docs/leads/custody.md` §6 is that an unexercised path is a broken path; this is its
mitigation, and it is why the first live invocation will fail loudly rather than succeed
wrong.

Because of fact 4, the archive adapter also **reads the object's lock metadata back with
`HeadObject`** and `ArchivedObject.assert_indelible()` refuses — naming the field — unless
S3 itself reports COMPLIANCE, a legal hold that is ON, a `VersionId`, and a retention past
the floor. `ObjectLockNotEnforced` is deliberately not wrapped in `AnchorAborted`: it is a
Class E evidentiary-integrity incident, not a retry.

**Step ordering is fatal for the first three and debt-producing for the last three.** Until
Object Lock accepts the note there is no commitment outside our control, so aborting costs
a retry. After it, the object is indelible and raising would pretend an event that
physically happened did not — so a dead TSA, an unreachable tile store and a silent witness
become `AnchorDebt` rows, exactly the shape of §7.3 step 5's unwitnessed debt. **Going dark
stays possible and self-reports.**

## Consequences

**Good.** GT-18 is checked by a command rather than by a reviewer's memory, and the check is
observed refusing fifteen deliberately-broken plans. The evidence stack plans offline, so
the gate runs today on a machine with no AWS credentials. The bucket policy is fully
resolved in the plan, so what will be granted is reviewable *before* apply — which for a
one-shot control is the only review that counts. The anchor's AWS call shapes are pinned by
tests that fail on the change that would break them.

**Costs, stated.** The writer holds two actions that a naive audit will flag, and the answer
is a paragraph rather than a line — mitigated by `IAM-2` making the paragraph executable.
The Rego is unexecuted and says so; it is documentation with a plausible implementation
until a CI lane runs `conftest` green. `Deny` + `NotPrincipal` is the sharpest edge in IAM
and the module's use of it is reviewed, not proven. And nothing here has ever been applied:
`tofu validate` passes and a full offline plan succeeds, but a live `apply` has not run.

**Unclosed.** The *"unconditionally while any `legal_hold` row is open"* half of §11.6 is a
condition on a **database fact**. No KMS key policy and no plan-time rule can see it; it
belongs in an organisation-level SCP fed by the custodian patrol, and **no file in `infra/`
implements it today.** Attack `A15` (`object_lock_downgrade`) in `spec/custody/attacks.yaml`
remains `SKIP(no-credentials)` — printed as loudly as a `FAIL`, never silently absent —
until credentials exist and the `--live` path runs against a real bucket.

## Alternatives rejected

**`moto` for Object Lock.** Its enforcement is incomplete. See CU-10; the whole point is
that we are testing an *irreversible* control, and a mock that accepts the call without
enforcing it is indistinguishable, from the test's point of view, from a bucket that does
the same — which is the exact failure we are trying to detect.

**GOVERNANCE mode with a tightly-held `s3:BypassGovernanceRetention`.** Removes the sentence
*"a protected object version can't be overwritten or deleted by any user, including the root
user"*, and that sentence is the product. A bypass permission held by nobody today is a
bypass permission held by somebody eventually.

**A single AWS account.** Then the people who operate the application can delete the
evidence, and the separation is a policy hope rather than an organisational fact.

**A `destroy` recipe with a confirmation prompt.** A prompt is a speed bump, and this is not
a speed-bump situation: the bucket physically cannot be emptied, so a `destroy` that got
past the prompt would fail partway through and leave a stack whose state file no longer
describes it — worse than refusing, and harder to explain afterwards.

**Encrypting checkpoints under a customer-managed KMS key.** See decision 4: it adds the one
capability the design exists to remove, in exchange for confidentiality that public
commitments do not need.
