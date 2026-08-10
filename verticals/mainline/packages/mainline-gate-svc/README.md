<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# `mainline-gate-svc`

The deterministic merge-gate caller for the MAINLINE binding. One explicit
`SERIALIZABLE` transaction, one `CALL mainline.merge_permit(…)`, one verdict — and a
dependency closure short enough that "no model can reach the merge gate" is a fact
somebody can check in under a minute rather than a sentence somebody has to trust.

## Why this package exists

`ARCHITECTURE.md` §8.2 draws the deterministic/LLM boundary and asserts it four ways.
E3 — the code-path leg — scans exactly two roots
(`mainline_boundary.astscan.DEFAULT_KERNEL_ROOTS`):

```
packages/trappoint-*
verticals/mainline/packages/mainline-gate-svc      <- this directory
```

Until this directory existed, the second root matched nothing, the scanner recorded
`E3-ROOT-ABSENT` as a **skip with a reason**, and `tests/boundary/test_e3_code.py`
refused — correctly — to call that a pass. `.importlinter` contract 1 forbade importing
`mainline_gate_svc`, and `boundary.yml` triggered on this path. Three assertions about
a package that was never written.

They are now assertions about code.

## What it does

```python
from mainline_gate_svc import load_config, merge_permit
from trappoint_core import GateRefused, MergeRequest

config = load_config()  # refuses to start holding a credential
try:
    outcome = merge_permit(request, config=config)
except GateRefused as refusal:
    print(refusal.sqlstate, refusal.constraint)  # e.g. 23514 gate_closed_when_issued
```

A merge that **returns** is a merge that **committed**: `MergeOutcome` has no `ok` flag
and no `refused` variant, because a refusal a caller can handle by forgetting to check a
field is a refusal that becomes a silence.

| condition | what leaves `merge_permit` | retried? |
|---|---|---|
| committed | `MergeOutcome` | — |
| `23514` `23503` `23505` `P0001` | `GateRefused` with SQLSTATE **and** constraint name | **never** — attempted exactly once, ever |
| `40001` | retried; `RetryBudgetExhausted` if the budget runs out | yes, and only this |
| `42501` | `AuthorisationDenied` — a fact about the writer, not a diagnosis of the subject | never |
| any other SQLSTATE | `UnmodelledRefusal` — a defect, not an edge case (`spec/errors.md` §1.1) | never |
| cluster unreachable | `ConnectionUnavailable` — undecided; the gate never ran | — |

## The three dependencies

```
psycopg[binary]   the wire, without the `pool` extra: the retry unit is the whole
                  transaction, and one connection per attempt makes an aborted
                  connection handed back to a pool (25P02) unreachable
trappoint-core    MergeRequest, run_gate, GateRefused, ISOLATION_STATEMENT
mainline-domain   the binding's deterministic vocabulary and version stamp
```

No `boto3`. No `botocore`. No `anthropic`. No `strands`. No `httpx`. No `pydantic-ai`.
No `mainline-agentkit`. The absence is **enforced on four surfaces**, in
`tests/test_no_model_in_closure.py`:

1. **runtime** — import the package in a fresh interpreter, walk `sys.modules`;
2. **declared** — walk `importlib.metadata.requires` transitively, because a runtime
   absence with a declared dependency is still a supply-chain reach;
3. **source** — an AST scan over `src/`, so the claim survives a checkout where nothing
   is installed;
4. **environment** — `load_config` refuses to start when the process holds an AWS or
   model-provider variable. There is no override flag, on purpose.

Adding one name to `[project.dependencies]` turns surface 2 red. That is the mechanism,
and it has been observed red: see the commit that introduces this package.

## Configuration

| variable | meaning |
|---|---|
| `MAINLINE_GATE_DSN` | this service's own DSN; read first |
| `MAINLINE_TEST_DSN` / `TRAPPOINT_DSN` / `COCKROACH_URL` / `CRDB_URL` | the four spellings this repository's fixtures already honour, read in that order |

The connection carries `application_name=mainline-gate-svc`, a libpq
`connect_timeout`, and `options=-c statement_timeout=…` — the last measured working on
CockroachDB CCL v26.2.5, so the timeout is in force for the *first* statement of the
transaction rather than set by a statement inside it.

**Write `127.0.0.1`, not `localhost`.** Measured on this Windows host against the local
node, everything else identical:

| host in the DSN | connect |
|---|---|
| `localhost` | 5060.8 ms, 5022.5 ms |
| `127.0.0.1` | 5.5 ms, 5.3 ms |

`localhost` resolves to `::1` first, the node does not answer there, and libpq waits out
the entire `connect_timeout` before falling back to IPv4 — once per attempt, because the
retry unit is the whole transaction. The gate's server-side p95 budget is 120 ms. This
service does not rewrite the host for you: a process that quietly edited an operator's
connection string would be a process whose wire log disagreed with its configuration.

## CLI

```
mainline-gate preflight        # what the process would start with; opens no connection
mainline-gate isolation        # the isolation statement, verbatim
mainline-gate merge REQUEST    # REQUEST is a JSON file, or '-' for stdin
```

Exit codes are the interface: `0` merged · `2` refused to start · `3` gate refused ·
`4` `42501` denied · `5` undecided · `6` unmodelled SQLSTATE.

## Tests

```
pytest verticals/mainline/packages/mainline-gate-svc/tests -q
```

Nothing here needs a cluster. The refusal-shape suite drives a scripted connection,
because the once-only property is a property of the **client** and a test that needed a
live node to observe it is a test nobody runs before pushing. The live half — a real
refusal from a real CockroachDB — is the gate-refusal proof under `scripts/proof/`.
