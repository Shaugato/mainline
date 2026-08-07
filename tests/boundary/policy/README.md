<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The Rego re-statement of E1, E2 and E4

ARCHITECTURE.md §8.2 says E2 "is the one that convinces a security reviewer,
because it does not depend on our code being correct". A Python checker that we
wrote **is** our code. So the same three plan-level assertions are written a
second time here, in Rego, and evaluated by an engine we did not write.

Where the Python and the Rego disagree, one of them is wrong, and
`tests/boundary/test_e2_network.py` says so rather than picking a winner.

| file | package | asserts |
|---|---|---|
| `plan.rego` | `mainline.boundary.plan` | shared plan reading: resources, configuration references, Plane tags, kernel egress, kernel-reachable security groups |
| `e1_iam.rego` | `mainline.boundary.e1` | the kernel task role's permissions boundary carries an unconditional `Deny` with `Resource: "*"` on `bedrock:*`, `bedrock-runtime:*`, `bedrock-agentcore:*` |
| `e2_network.rego` | `mainline.boundary.e2` | no `bedrock-*` endpoint in or reachable from the kernel; kernel TCP/443 only to the interface-endpoint security group; no 443 to `0.0.0.0/0` |
| `e4_egress.rego` | `mainline.boundary.e4` | the kernel's outbound protocol set is exactly `{26257, 443}`, each to an enumerated destination |

## Running them

```sh
conftest test --policy tests/boundary/policy --all-namespaces \
    tests/boundary/fixtures/plan.json
```

or

```sh
opa eval --format json --data tests/boundary/policy \
    --input tests/boundary/fixtures/plan.json 'data.mainline.boundary'
```

Every rule is a `deny` whose message begins with the same rule id the Python
checker uses, so a finding can be traced to the same line of §8.2 whichever
engine reported it.

## Two deliberate differences from the Python

1. **`NotAction` is not reasoned about.** `e1_iam.rego` requires an
   `Action`-based unconditional `Deny`. A `NotAction`-shaped deny may well be
   sound, but an auditor should not have to work that out.
2. **Module calls are refused.** These policies resolve configuration references
   by unqualified address, so `e2_network.rego` denies outright if the plan
   contains `module_calls` rather than silently analysing the wrong thing. The
   Python walks child modules properly; when infra grows modules, this policy
   grows with it, loudly.

## What none of this proves

That the deployed account matches the plan. A plan is what we intend to apply.
`E1`'s live `iam simulate-principal-policy` leg (behind
`MAINLINE_BOUNDARY_LIVE_AWS=1`) is what closes that gap, and it does not run
today because AWS credentials are not valid on the build machine.
