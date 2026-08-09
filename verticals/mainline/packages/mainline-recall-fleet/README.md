<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# mainline-recall-fleet

**The recall agent's binding to the agent fleet.** One wire, one register, one ledger row.

MAINLINE has two model runtimes, and both are deliberate. `mainline-agentkit` issues every
single-shot, zero-tool, JSON-Schema-constrained call in the Cognition plane. The recall
agent's `BedrockClaudeJudge` issues the listwise rerank and the cue synthesis, because a
listwise judge over forty candidates is not the shape `quarantined_call` has.

The cost of the second runtime is that the recall agent — the largest model caller in the
repository — sits outside the fleet's controls. This package is the seam that puts it back
inside, without editing a line of either package.

---

## What it actually changes

Measured against the body `mainline_recall_agent.providers.judge.BedrockTransport.send`
puts on the wire, and asserted in `tests/agents/recall_fleet/test_body_contract.py`:

| Clause | Raw recall body | Bound body |
|---|---|---|
| `A5.thinking_adaptive` | **absent** | `{"type": "adaptive"}` |
| `A4.effort_declared` | **absent** | the leg's effort (`low` / `high` / `xhigh`) |
| everything else in the contract | already conforming | unchanged |

Those are the only two, and the test asserts *exactly* those two so that if the recall
package later adds them upstream the suite fails and this package's justification has to
be rewritten rather than quietly kept.

Beyond the body, binding through `FleetJudgeTransport` also buys:

* **Residency asserted once, at construction.** `au.*` or nothing — a bare
  foundation-model id bypasses the very ARNs the VPC-endpoint policy enumerates, and
  `global.*` / `apac.*` can route a Queensland fatality narrative offshore. Asserting per
  call, on the live path only, would be a control a caller could decline.
* **Guardrail interventions become refusals.** Bedrock reports a Guardrail block *out of
  band from `stop_reason`*, so a judge that branches on `stop_reason` alone reads an
  intervened response as a clean completion with empty content. A guardrail that fires and
  is then ignored is not a guardrail.
* **An unrecognised `stop_reason` fails closed.** A stop reason nobody has classified is
  not evidence that the model answered. `test_the_unbound_judge_would_have_accepted_that_stop_reason`
  measures the difference rather than asserting it.
* **Silence is one row, built by one implementation.** `fleet_silence_row()` returns a
  `mainline_meas.silence_ledger` row carrying the replayability quad. This package holds no
  driver and no credential; the caller writes the row through its own SQL role.

Every translation exists so that the recall orchestrator's degraded path — complete on
channels A+B, record `arms_degraded`, write the silence rows, **and still block the
merge** — fires on exactly the exception classes it already catches. A binding that
introduced a new exception class for a refusal would be a binding that silently disabled
that path.

---

## The register

`legs.py` declares five legs and validates them **at import**, which is the difference
between a rule and a control:

| leg | agent | tier | effort | prompt version |
|---|---|---|---|---|
| `recall.cue.event` | `mainline-recall` | T1 | low | `mainline-cue-1` |
| `recall.cue.exposure` | `mainline-recall` | T1 | low | `mainline-cue-1` |
| `recall.rerank.listwise` | `mainline-recall` | T1 | xhigh | `recall-judge-1` |
| `recall.taxonomy.propose` | `mainline-taxonomy` | T2 | low | `mainline-taxonomy-induction-1` |
| `recall.taxonomy.refine` | `mainline-taxonomy` | T2 | high | `mainline-taxonomy-induction-1` |

Every leg: `tools = ()`, `may_write_gate_field = False`, `sql_role = agent_recaller`. That
last one is the covenant CockroachDB already carries on the schema
(`0009x_covenant_comment.sql`) made executable in Python — *the role that detects a
precursor may never write one* — and a leg naming a gate-writing role fails the import.

The prompt versions are **literals on purpose**. A register that imports its source can
never disagree with it, and a register that cannot disagree cannot detect the drift
decision A13 exists to detect. `test_register_prompt_versions_match_the_recall_package`
is where the two are compared, once, in CI; `FleetJudgeTransport` refuses a request whose
version differs, before the wire.

`fleet_yaml_fragment()` **emits** the rows for `spec/agents/fleet.yaml` rather than
writing that file: two files claiming to be the register is the failure mode this domain
exists to refuse. The fragment is deterministic, so a diff is a real change.

---

## Using it

```python
from mainline_agentkit import select_transport
from mainline_recall_agent.providers.judge import BedrockClaudeJudge
from mainline_recall_fleet import FleetJudgeTransport, fleet_silence_row, get_leg

leg = get_leg("recall.rerank.listwise")
wire = FleetJudgeTransport(
    inner=select_transport(),  # cassette offline, InvokeModel live
    leg=leg,
    inference_profile_arn=resolved_arn,  # au.* — asserted here, once
    iam_role_arn=execution_role_arn,
)
judge = BedrockClaudeJudge(
    resolved_model=resolved,
    transport=wire,
    prompt_version=leg.prompt_version,
    max_tokens=leg.max_tokens,
)
```

The retry rule stays where it belongs: one call, one repair, then `DeadLetter`. This
transport does not retry, because a retry helper inside a transport is exactly the
blanket-retry helper ARCHITECTURE §6.5 bans.

---

## What this package does not claim

* *We claim replayability and arithmetic reproducibility, never reproducibility of model
  output.* The model proposes; the arithmetic decides; both are on the record.
* *A precursor the model declined to summarise must still block the merge.*
* *Inference is pinned to `au.*` inference profiles in the configured Bedrock region. This
  package pins inference only and makes no claim about database residency; on the free
  demo tier the cluster is in Singapore, so end-to-end Australian data residency is FALSE
  for that deployment and is never claimed.*

**Unverified, and stated rather than implied.** No live Bedrock call has been made from
this machine — AWS credentials are not valid here as of 2026-08-09 (PL-3). What the tests
prove is *our* body shape, *our* refusal translation and *our* register; that the endpoint
accepts the body is `GT-AG-01`'s job, and AR-1 (forced `tool_choice` on a single-turn
strict tool form) is the pre-committed answer if it says no.

**It does not hash `agent_identity`.** `identity_components()` returns the seven
components in concatenation order and stops there, because `mainline-provenance` owns the
formula and two implementations of one digest is one implementation too many.

---

## Tests

```
uv run pytest tests/agents/recall_fleet
```

54 tests, all offline: no AWS account, no cluster, no cassette store.

`uv.lock` does not yet list this package. The workspace globs (`verticals/*/packages/*`)
pick it up the moment its `pyproject.toml` lands, but the lockfile is regenerated by the
toolchain owner — several existing members are missing from it too, so this is the
repository's current state rather than a new gap.
