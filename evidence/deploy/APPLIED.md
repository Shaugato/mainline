<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# The apply, as it actually happened — 2026-08-14

**Applied by the orchestrator, with the founder's authorisation, against account `<account>`
in `ap-southeast-1`.** Nothing below is predicted; every line was read back from the account
or from a live HTTP request.

## What exists now

    terraform apply    24 created, 0 changed, 0 destroyed
    terraform state    37 resources
    demo_url           https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws

Eleven resources are the demo API; thirteen are the cost guard — three alarms on three
timescales feeding one SNS topic into a responder that calls
`PutFunctionConcurrency(ReservedConcurrentExecutions=0)`, plus the budget. The guard was
instantiated in this apply, which is why the plan is 24 and not the 22 an earlier review saw.

Preceding it, and the first mutating action of the whole deploy: the state bucket
`mainline-demo-tfstate-<account>` — versioned, public access blocked on all four settings,
SSE-S3, tagged, noncurrent versions expiring at 30 days.

## First light, measured

    GET  /                     200, 4,655 B, 1.63 s   (static console, served)
    GET  /v1/health            ok=false, reason="dsn_unset"
    POST /v1/demo/gate-run     503,        kind="dsn_unset"

Both API answers name the cause exactly: *SSM GetParameter '/mainline/demo/cockroach_dsn'
in ap-southeast-1 answered HTTP 400: {"__type":"ParameterNotFound"}*.

**That is the predicted state, not a defect.** `PRE-APPLY.md` G3 records the asymmetry in
advance: Terraform CONSTRUCTS the parameter ARN and never reads it, so an apply with no
parameter in Parameter Store succeeds, creates all twenty-four resources, and produces a
demo whose first request cannot reach a database. The origin is up; the secret is the one
remaining step.

## The step that is deliberately not automated, and the reason

`/mainline/demo/cockroach_dsn` must hold the **`mainline_api`** DSN. Measured on the live
cluster, the three login-capable roles are not interchangeable:

| role | privileges held |
|---|---|
| `mainline-sql` — the DSN in `.env` | **ALL on 417 objects** |
| `mainline_api` | CONNECT 1 · USAGE 36 · SELECT 55 · UPDATE 3 · INSERT 8 · EXECUTE 29 |
| `mainline_judge` | CONNECT 1 · USAGE 21 · SELECT 14 · EXECUTE 28 — no INSERT, no UPDATE |

The Function URL carries `authorization_type = NONE` by the founder's explicit choice, so
whatever this parameter holds is what an anonymous caller's request runs as. Putting the
`.env` DSN here would give a public unauthenticated endpoint `ALL` on 417 objects. It is
`mainline_api` or it is a hole.

Entering a credential is the founder's action, not the orchestrator's, so the value is
placed by him. The mechanism keeps it out of every log either way: the payload goes in via
`--cli-input-json file://…` from a `0600` file so it never enters an argument vector, and it
is read back WITHOUT `--with-decryption`, so the check cannot print it even by accident.
Terraform is given the parameter NAME and never the value — `terraform show` cannot print a
password Terraform never held.
