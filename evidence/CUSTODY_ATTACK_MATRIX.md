<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0

GENERATED FILE — do not edit.
Produced by tests/integration/custody/nemesis/matrix.py from a nemesis run against a
real, disposable CockroachDB. Regenerate with:
  python -m pytest tests/integration/custody/nemesis
-->

# ATTACK-DEPTH — the custody attack matrix

**Generated from a run, not written by hand.** Each row below is what happened when the attack was executed as real SQL against a disposable single-node CockroachDB seeded with the reference log, and a bundle exported from the mutated database was then put through the check set.

- attacks executed: **0** of 1
- reported `SKIP`: **1** — A15
- detected by zero checks: **14**
- detected by exactly one check (flagged, not failed): **0**
- verifier that produced these rows: none

| Environment | |
|---|---|
| generated_at | 2026-08-10T08:38:28Z |

## The matrix

| Attack | Tier | Detected by (observed) | Latency | Expected (registry) | Agrees |
|---|---|---|---|---|---|
| **A15** `object_lock_downgrade` | T2 | — SKIP(no-credentials) | not run | check 8 | n/a |

Latency is measured from the moment the attack commits to the moment the first finding exists — the question a reader is actually asking is *how long after the attack would somebody know?* For attacks whose primary defence is a database refusal the honest answer is *before it happened*, and those refusals are listed below rather than folded into a millisecond count.

## Holes in the argument — CI FAILS on this section being non-empty

- A1 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A2 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A3 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A4 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A5 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A6 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A7 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A8 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A9 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A10 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A11 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A12 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A13 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of
- A14 is in spec/custody/attacks.yaml and is ABSENT from this run. An attack missing from the matrix is indistinguishable from one nobody thought of

## What each attack did, and what the database said

### A15 · `object_lock_downgrade` (T2)

> Call PutObjectRetention to shorten a COMPLIANCE retention, or DeleteObjectVersion on a checkpoint object.

**SKIP(no-credentials)** — this attack was not executed by this run, and is recorded here rather than omitted.

The static defence is proven instead by policy-as-code over the OpenTofu plan JSON (`infra/policy/custody/object_lock.rego`, `scripts/custody/check_evidence_plan.py`): the bucket must declare `object_lock_enabled` AT CREATION and versioning, and no principal in the write account may hold `s3:DeleteObject*`, `s3:PutObjectRetention`, `s3:PutObjectLegalHold` or `s3:BypassGovernanceRetention`. GT-18 is a one-shot: Object Lock cannot be retrofitted, so it must be right the first time.

## What is not defeated

- **T3** — a managed-service operator with storage-path access is outside every mechanism in the database. Only Object Lock in a separate account and external witnesses touch that adversary, and neither is a complete answer.
- **T4** — a cloud-org admin colluding with the signer can mint valid-looking history *going forward*. What they cannot do is change history a timestamp authority already timestamped or a witness already cosigned. The window of undetectable mutation is ~60 seconds and that is the honest number.
- **Insincerity** — nothing here detects a rubber-stamped disposition. The chain makes rubber-stamping *measurable*; it does not make it impossible.

Cross-referenced to [`spec/custody/attacks.yaml`](../spec/custody/attacks.yaml) and [`spec/custody/checks.yaml`](../spec/custody/checks.yaml).

