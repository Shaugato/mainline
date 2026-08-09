<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-custody-patrol` — custody of the custodian

A tamper-evident log proves its own contents beautifully and, on its own, can say nothing
whatever about the platform underneath it. So an adversary holding cloud-admin rights does
not attack the log — they change the platform: disable a trigger, rewrite a key policy,
shorten a retention period. This package is the periodic, hashed, Object-Locked answer to
*"and who was watching the watchers"*.

Every fifteen minutes it collects **eight** facts about the platform, canonicalises each
one under RFC 8785, writes the full JSON to **S3 Object Lock COMPLIANCE in a second AWS
account**, and folds the digest into the MAINLINE ledger as a `custodian_attestation`
leaf. `mainline.custodian_attestation` (migration `0078`) keeps only the object key and
the digest — because a copy held in the database we are attesting *about* is a copy the
adversary being attested about can rewrite.

| kind | what it answers |
|---|---|
| `ccloud_audit` | the CockroachDB Cloud audit stream — the record a cluster admin does not author, and therefore the one a `DISABLE TRIGGER` shows up in |
| `ccloud_backup` | backup inventory and retention; a restore nobody can point at is not a backup |
| `inspect_database` | the cluster's own index-consistency reporting |
| `schema_fingerprint` | the normalised, order-stable digest of the whole schema |
| `trigger_definitions` | the self-attesting gate: what the triggers **actually are**, not what the migrations said they would be (verifier check 11) |
| `kms_key_policy` | who may use, disable or schedule deletion of the log signing key |
| `s3_object_lock` | the retention mode and period **actually** configured on the bucket |
| `iam_snapshot` | who could have done any of the above |

## The three properties everything else is arranged around

**An unrun patrol is never reportable as a clean one.** A collector that cannot run
produces a `Refusal`, the run's `complete` is `False`, and `summary_lines()` prints the
refusal as loudly as a success. There is no silent default anywhere: `resolve_shim()`
refuses rather than inventing an empty response, and a `ccloud` response that has lost a
field raises `CcloudFieldMissing` naming the members it *did* carry. *A silently renamed
field is how a provisioning agent lies*, and a field that degraded to a default would turn
"I could not find the audit records" into "there were no audit records".

**The object leaves our reach before the row that names it exists.** The order —
collect → canonicalise → hash → put under COMPLIANCE → **verify the store's own digest** →
row and leaf — is not negotiable. The reverse order produces a row pointing at an object
we could still decide not to write, which is a promise rather than a commitment.

**Pagination is refused, not guessed.** `ARCHITECTURE.md` §19 GT-21 records the `ccloud`
next-page argument as an unresolved day-1 output. A response carrying a cursor refuses
unless the caller supplies a `PageCursor` saying how to ask for the next page. Attesting
page 1 of *n* as though it were the window is an omission, and non-omission is the
proposition plaintiffs actually attack.

## What is honest about today's state

* **AWS credentials are not valid on any machine in this build**, and there is no
  CockroachDB Cloud organisation attached to it. Every external capability is a
  `typing.Protocol` with a fixture-backed fake that asserts the **exact call shape** the
  live path will make — `object_lock_mode="COMPLIANCE"`, a retention date in the future,
  a store that reports back its own digest. The first live run therefore fails loudly
  rather than succeeding wrongly.
* **Tier T3 is not defeated.** A principal inside the Cockroach Labs or AWS storage path
  is outside what any of this constrains. It raises the cost of T1 (a rogue DBA with
  arbitrary SQL) and T2 (a cloud-org admin) by putting the evidence where they cannot
  reach it. Saying that first is the only version of the sentence that helps a customer.
* **GT-05 is unanswered on CockroachDB Cloud.** `pg_get_triggerdef()` was confirmed on
  CockroachDB CCL v26.2.5 on 2026-08-07; Cloud Standard is unverified. Where it is absent
  the fingerprint's `grade` is `weak` and `trigger_definitions.granularity` is `coarse`,
  **in the attested data**, so verifier check 11 reports `PASS(coarse)` and the claim
  softens in the same artefact rather than quietly keeping its stronger wording.
* **`INSPECT DATABASE` is attempted, and its unavailability is itself attested.** Zero
  findings and no inspection never render the same way.

## One fingerprint, two callers

`trappoint_migrate.attest.fingerprint` computes the schema digest at migration-apply time;
this package computes it from the live cluster on patrol. If the two differed, the drift
alarm would be comparing two different questions and answering neither. They share
`collapse_whitespace`, and
`tests/test_fingerprint_stability.py::test_matches_the_migration_runner_byte_for_byte`
drives **both** implementations over one identical row set and asserts the digests are
equal — with no cluster, no driver behaviour and no credentials.

Stability is asserted on **every run**, not only in CI: `stable_schema_fingerprint`
computes the digest twice and raises `FingerprintUnstable` if the two disagree, naming
the category that moved. A fingerprint that flickers is worse than no fingerprint,
because the first false alarm is the last one anybody reads.

## Using it

```python
from datetime import UTC, datetime, timedelta

from mainline_custody_patrol import (
    CustodyPatrol,
    FixtureCcloud,
    FixtureCloudControlPlane,
    PsycopgSqlSource,
    resolve_shim,
)

shim, source = resolve_shim()  # refuses rather than defaulting
patrol = CustodyPatrol(
    object_store=evidence_store,  # your ObjectStore; COMPLIANCE is passed per call
    sql=PsycopgSqlSource(conn),  # conn.autocommit must be True — the probes may fail
    ccloud=shim,
    ccloud_source=source,
    cloud=control_plane,
    sink=ledger_sink,  # emit(kind, subject_id, payload)
    site_code="SITE-01",
    cluster_id="cl-…",
    kms_key_id="arn:aws:kms:…",
    evidence_bucket="mainline-custody-site-01",
)
now = datetime.now(tz=UTC)
run = patrol.run(window_from=now - timedelta(minutes=15), window_to=now)
if not run.complete:
    raise SystemExit("\n".join(run.summary_lines()))
```

The patrol never opens its own connection and never opens its own transaction: a custodian
attestation and its ledger leaf commit together or not at all, so the caller's transaction
is the unit of atomicity.

## Scope

This package **collects and commits**. It does not schedule (EventBridge does, `rate(15
minutes)`), does not sequence (`mainline-sequencer` does), does not sign (the log key is
KMS's), and does not verify (`trappoint-verify` does, offline, on a stranger's machine).
Everything it produces is designed to be checked by somebody who does not have to trust us.
