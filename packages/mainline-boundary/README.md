<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# mainline-boundary

**Four independent proofs that no model can reach the merge gate.**

> *A regulator must be able to read the merge gate in ten minutes and see no model in it.*
> — ARCHITECTURE.md §8.2

A comment saying so is worth nothing under cross-examination. So the boundary is
drawn physically, and this package is what checks that the drawing is true.

| # | Enforcement | What it reads | Module |
|---|---|---|---|
| **E1** | no model IAM | the kernel task role's **permissions boundary** in an OpenTofu plan | `iam.py` |
| **E2** | no model network path | VPC endpoints + security-group graph in the same plan, **and the same claim re-stated in Rego** | `network.py`, `opa.py` |
| **E3** | no model code path | every `.py` under `packages/trappoint-*` and `verticals/mainline/packages/mainline-gate-svc`, plus the import graph, plus an SBOM diff | `astscan.py`, `sbom.py` |
| **E4** | no model prompt path | the kernel's complete outbound protocol set, plus the FIS blackhole record | `egress.py` |
| — | fleet capability matrix | `spec/agents/fleet.yaml` against §8.1's plane table | `fleet.py` |
| — | CI greps | retry helpers, sampling parameters, per-signer metric labels, §11.7 claims | `greps.py` |

Run any one of them:

```sh
mainline-boundary e1        # or e2 / e3 / e4 / fleet / greps / all
mainline-boundary e2 --json
```

Exit codes are the contract: `0` clean, `1` violations, **`3` vacuous** — the
check examined nothing and gave no reason — and `4` a reasoned skip that examined
nothing. `--strict` turns `4` into `1`.

## The one design rule

**A check that examined nothing must never report green.**

Every result carries `examined`, `skips` and `exemptions` alongside `violations`.
`Report.vacuous` is true when a report has no violations *and* inspected no
subjects, and the test helper turns that into a failure or an explicit skip —
never a pass. Three consequences you can see in the output today:

- `verticals/mainline/packages/mainline-gate-svc` does not exist yet, so E3
  records `E3-ROOT-ABSENT` **as a skip with its reason**, and the suite skips
  rather than passing. The moment the path appears, the skip vanishes and the
  scan is enforced with zero edits.
- No kernel-image SBOM is committed, so the SBOM leg skips with its reason. "No
  previous digest" is not "no new model SDK".
- `spec/agents/fleet.yaml` is owned by another worker and is not here yet, so the
  matrix runs against a reference register committed under `tests/fixtures/` and
  says so. It retargets the real file automatically.

## Why four, and why they are four separate jobs

The value of four enforcements is that **they do not share a failure mode**. One
bad regex, one bad fixture path or one bad parser should take out at most one of
them. `.github/workflows/boundary.yml` therefore runs each in its own job.

Where they cannot help but share something — E2 and E4 both read the same plan
through `planfacts.py` — the shared component is re-stated in **Rego** under
`tests/boundary/policy/` and evaluated by conftest or OPA, an engine we did not
write. Both were run against this fixture and against eleven deliberately broken
variants of it; the two implementations agree on every one.

## The plan-time trap this package is built around

At plan time almost every AWS id is *known after apply*. `aws_iam_policy.arn` does
not exist, so the kernel role's `permissions_boundary` is `null` in
`planned_values`. **A checker that reads `planned_values` alone sees nothing and
calls it clean** — a pass by absence, the exact failure this domain exists to
refuse.

`planfacts.py` therefore exposes three things, not one: known `values`, the
explicit `unknown` map from `resource_changes[].change.after_unknown`, and the
configuration-level **reference graph**. Attributes resolve by value *or* by
reference, and an attribute that resolves to neither is a violation with a stated
reason — never a shrug.

## What this package does not claim

- **That the deployed account matches the plan.** A plan is what we intend to
  apply. E1's live `aws iam simulate-principal-policy` leg closes that gap and is
  behind `MAINLINE_BOUNDARY_LIVE_AWS=1`; it does not run today, because AWS
  credentials are not valid on the build machine as of 2026-08. PL-3 forbids
  putting an unproven capability on a dated path.
- **That the FIS blackhole game-day happened.** It is designed, written down in
  `data/fis-blackhole.yaml`, and marked `verified: false` / `may_be_claimed:
  false`, blocked on §19 GT-16 (task-level FIS network actions on Fargate need
  the SSM agent in the task definition). E4 fails if that marker is flipped
  without a committed attestation, and fails again if any outward-facing document
  says the game-day ran. Do not promise it on camera.
- **That `boto3.client(service_name)` with a variable is visible.** It is not, to
  E3. E1 (no IAM) and E2 (no route) are why that is survivable, and are precisely
  why §8.2 specifies four enforcements rather than one.
- **That the enumerated pgwire destination is PrivateLink.** It is a managed
  prefix list holding the CockroachDB Cloud egress CIDRs. §11.7 forbids claiming
  PrivateLink on a checkpoint-tier cluster, and this package does not.

## Deliberate holes, all of them visible

Exemptions are recorded in the report with their reasons, because an exemption
nobody can see is a hole rather than a decision:

- **the literal rule exempts test files**, since a test asserting the *absence* of
  `bedrock-runtime` must be able to name it. Any other file may use
  `# mainline-boundary: allow-literal <reason>` on the line, and every use appears
  in the report.
- **the sampling-parameter ban exempts
  `verticals/mainline/packages/mainline-corpus/src/mainline_corpus/render`.** That
  renderer targets a different (Sonnet-4.5 Converse) model generation that does
  accept sampling parameters, is offline-by-default, and is not on the merge path.
  A6 bans sampling parameters in the *fleet's* request builders.
- **the must-not-claim grep excuses a match whose surrounding line disclaims
  rather than asserts**, so §11.7's own sentences can be written in the README
  they govern. Every excuse is reported as an exemption.

## Licence

Apache-2.0. This is substrate: it asserts a property of the kernel, so it is
readable and reusable by anyone who wants to assert the same property of theirs.
