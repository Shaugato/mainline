<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# mainline-delta-oracle — Path B

The independent semantic opinion on a clause edit. One zero-tool,
JSON-Schema-constrained Claude call per ancestor/descendant pair, framed as
directional NLI, returning a relation and the verbatim span that determines it.

**This package exists to be separate.** `mainline-domain` holds the delta lattice,
and the lattice decides a state transition; principle P7 says no component that
decides a state transition may hold, reach or import a model. A comment saying so
is worth nothing under cross-examination, so the boundary is a distribution
boundary:

```
mainline-delta-oracle ──imports──▶ mainline-domain      (contracts + the silence vocabulary)
mainline-delta-oracle ──imports──▶ mainline-agentkit    (the one model surface; bedrock is an extra)
mainline-domain       ──imports──▶ nothing that can reach a model, ever
```

The reverse arrow is asserted by an AST walk over every module in the domain
(`tests/unit/domain/boundaries/test_no_model_in_domain.py`), which fails the build
the moment a domain module imports `boto3`, `botocore`, `anthropic`, `strands`, or
anything with `bedrock` in its name.

## The guarantee

Everything this package can do wrong resolves toward a refusal.

| what happened | what comes back | what the ratchet does with it |
|---|---|---|
| the model said B contradicts A | `label=weaken` | raises the verdict if the lattice missed it |
| the model said B entails A | `label=strengthen` | ignored unless the lattice agreed — it cannot lower |
| the model said "neutral", confidently | `label=restate` | accepted only above θ, and only as the lattice's own member |
| the model said "I cannot tell" | `abstained=True` | `weaken` |
| `stop_reason: refusal` | `abstained=True` | `weaken` |
| Bedrock Guardrails intervened | `abstained=True` | `weaken` |
| truncated at `max_tokens` | `abstained=True` | `weaken` |
| invalid JSON twice, dead-lettered | `abstained=True` | `weaken` |
| throttled, or timed out | `abstained=True` | `weaken` |
| the supporting quote is not in clause B | `abstained=True` | `weaken` |
| `entails` + numeric disagreement + no number quoted | `abstained=True` | `weaken` |

The last two are this package's own deterministic verifier, not the schema.
§8.2 tier T1 is *proposals under a JSON Schema, always re-checked by a
deterministic verifier*; these two checks are that re-check, and the second one is
the promise the profile's own prompt makes to the model.

**A cassette that was never recorded, a prompt version that does not match the
profile, or a model id that is not an `au.*` inference profile does *not* abstain
— it raises.** An abstention is a statement about the model, written into an
evidentiary ledger; a broken deployment that abstained would be manufacturing
records of questions nobody asked.

## Two things the model is never given

* **The `safe_direction` registry.** DIRECTRIX (worker W2) decides which way a
  setpoint move is dangerous. A model told the answer returns the answer, and the
  second opinion becomes an echo.
* **A `rule_id`.** `R1_DEONTIC` … `R9_COVERAGE` belong to the lattice. A model
  that can name one can emit something shaped like a Path-A witness, and the value
  of two paths is that neither can forge the other.

Both are enforced on the shipped path — `prompt.build_untrusted_text` raises
`PathALeakage` — not in a test that runs against a different string.

## Running it

Cassette-first (decision D12). The default transport is the committed replay store
under `tests/fixtures/domain/oracle/cassettes/`, so the whole of Path B runs with
no AWS account and no network:

```python
from mainline_delta_oracle import (
    AdjudicationOracle,
    DeltaOracleRequest,
    OriginContext,
    PROMPT_VERSION,
)

oracle = AdjudicationOracle()  # cassette transport, discovered from the checkout
verdict = oracle.classify(
    DeltaOracleRequest(
        ancestor_text=...,
        descendant_text=...,
        ancestor_cat=...,
        descendant_cat=...,
        parameter_hint="gas_test_interval",
        prompt_version=PROMPT_VERSION,
        origin=OriginContext(event_summary=..., severity=5, occurred_on="2019-07-14"),
    )
)
```

The live lane needs **both** `MAINLINE_AGENT_PROVIDER=bedrock` and
`MAINLINE_AGENT_ALLOW_LIVE=1`, plus the `bedrock` extra. It is never exercised in
CI: AWS credentials are not valid on the build machine as of 2026-08, and PL-3
forbids putting an unproven capability on a dated path. **Every committed cassette
carries `"provenance": "synthetic"` — none of them has been near Bedrock.**

## Residency, stated precisely

Inference runs in `ap-southeast-2` (Sydney) on an `au.*` inference profile;
agentkit refuses any other model identifier. On the free demo tier the database is
in `aws-ap-southeast-1` (Singapore), so **end-to-end Australian data residency is
false for that deployment** and is never claimed here or anywhere else.

## Where the tests are

Under `tests/unit/domain/resolution/`, beside the ratchet they feed. That is the
directory the repository-root `pytest` configuration collects, and splitting one
worker's suite across two roots to satisfy a naming instinct would mean half of it
never ran.
