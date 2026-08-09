<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Custodian-patrol fixtures — what these are, and what they are not

These files are **recorded response shapes**, committed so that the parsing, the
canonicalisation, the hashing, the pagination refusal and the missing-field refusal in
`mainline_custody_patrol` are all exercised on a machine with **no CockroachDB Cloud
organisation and no AWS credentials** — which is every machine in this build
(`VERIFY.md`).

They are **not** evidence of anything, they are **not** a claim that the live APIs answer
in exactly this shape, and no exhibit, README, deck or demo may cite them as a collection
that happened. A fixture is how we prove the *collector* works. It says nothing about the
platform it models.

## The field names are the fragile part, deliberately

`ARCHITECTURE.md` §19 lists **GT-21** as unanswered: the existence and field names of
`ccloud audit list --starting-from`, `cluster backup list` and the `-o json` global flag
are **day-1 outputs**, not documented facts we may rely on. So the collector never uses
`.get()` on a `ccloud` response — every read goes through `require_field`, and a renamed
field raises `CcloudFieldMissing` naming the members the response *did* carry.

`renamed-field/audit-list.json` is that failure, committed. It is byte-identical to
`audit-list.json` except that `entries` is called `items`. The test that consumes it
(`test_ccloud_fold.py::test_a_renamed_field_is_a_hard_failure`) is the proof that a CLI
upgrade cannot silently turn *"I could not find the audit records"* into *"there were no
audit records"* — which is the single worst sentence an attestation can contain.

## The pagination cursor is deliberately absent from the fixtures

Both `ccloud` fixtures set `pagination.next_page` to `null`. The next-page **argument**
is the part of GT-21 that is still unresolved, and this repository does not hard-code a
guess at an undocumented flag. A response carrying a non-null cursor makes the fold
refuse (`CcloudPaginationUnresolved`) unless the caller supplies a `PageCursor` saying
how to ask for the next page. The tests build that case in-process rather than
committing a fixture for it, precisely so that nobody reads a committed fixture as a
statement about what the flag is called.

## The AWS fixtures encode the call shape the live path must make

`kms-key-policy.json`, `s3-object-lock.json` and `iam-snapshot.json` are shaped so that a
reviewer can see the three properties the live path is required to preserve, in a file
that runs today:

* KMS `Sign` is conditioned on `SigningAlgorithm = ECDSA_SHA_256` (CU-3), and
  `ScheduleKeyDeletion` / `DisableKey` / `PutKeyPolicy` are denied outside the two-person
  break-glass role (CU-10).
* The bucket is `ObjectLockEnabled` with a `COMPLIANCE` default retention of seven years
  and versioning `Enabled` — properties that **cannot be retrofitted** (GT-18), which is
  why they are read back on every patrol rather than trusted from the plan that created
  them.
* No principal in the IAM snapshot holds `DeleteObject*` or `PutObjectRetention`.

None of that is *enforced* by the fixtures — enforcement is policy-as-code over the
OpenTofu plan JSON (`infra/policy/custody/*.rego`, CU-10), owned by the evidence-infra
worker. What the fixtures give us is that the shape is legible now, and that the first
run against live credentials fails loudly rather than succeeding wrongly.

## Regenerating

There is nothing to regenerate today and that is the honest state. When a Cloud
organisation and an AWS account exist, a recorded response replaces the corresponding
file **with its secrets and account identifiers redacted to the zero account**
(`000000000000`) and its user e-mails replaced with `example.test` addresses — and the
commit that does it says so, because a fixture that quietly became real data is a
disclosure nobody reviewed.
