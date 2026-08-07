<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `mainline-agentkit`

**The whole of MAINLINE's model surface, in one small package.**

There is no agent framework in the Cognition plane. Every MAINLINE model call is a
single-shot, **zero-tool**, JSON-Schema-constrained Bedrock call issued by
`quarantined_call()`. Strands and LangGraph were evaluated and rejected: a framework
whose value is the tool loop is worth nothing to a fleet whose defining security
property is that the components touching untrusted text hold **no tools**, and
LangGraph's checkpointer would be a second, weaker record of a legally significant
process — the same objection that already rejected Step Functions.

Read the signature before anything else:

```python
def quarantined_call[T: BaseModel](
    profile: CallProfile[T],
    untrusted: UntrustedText,
    trusted_context: Mapping[str, Any],
    *,
    transport: Transport | None = None,
    model_id: str | None = None,
    settings: AgentkitSettings | None = None,
    sentinel: str | None = None,
) -> Validated[T]: ...
```

There is no `tools` parameter and there never will be. **That absence is the CaMeL
structural quarantine** — layer 1 of the six-layer prompt-injection posture
(ARCHITECTURE.md §8.4) — and it is asserted three independent ways: by
`inspect.signature` (`tests/test_zero_tool_shape.py`), by an AST scan over every module
in the package, and by `assert_no_tool_surface()` on the built body at runtime. A
component that reads hostile text and holds no capability to act on it cannot be
prompted into acting. That is a property of the call *shape*, and it survives a prompt
the attacker wrote.

---

## Three sentences this package will not let you avoid

> **We claim replayability and arithmetic reproducibility, never reproducibility of
> model output.** The model proposes; the arithmetic decides; both are on the record.

> **Prompt-injection defence does not fix a plausible-but-false narrative in an
> otherwise clean PDF.** Content authenticity is out of scope; provenance is in scope.

> **Inference runs in Australia (`ap-southeast-2`). On the free demo tier the database
> is in Singapore (`aws-ap-southeast-1`), so end-to-end Australian data residency is
> FALSE for that deployment and is never claimed.** On a customer install the database
> is in Australia, under the customer's CMEK key, in the customer's account.

---

## The call profile register

Five profiles, one model generation, differentiated by `output_config.effort`
(decision A4). `spec/agents/fleet.yaml` references these ids in its `call_profiles`
column; `mainline_agentkit.describe_fleet()` emits the register-shaped rows so the
YAML and the code are checked against each other rather than maintained in parallel.

| `profile_id` | agent (§8.4) | tier | effort | output model | may write a gate field |
|---|---|---|---|---|---|
| `triage` | archivist | T1 | `low` | `TriageVerdict` | no |
| `extraction` | archivist | T1 | `low` | `ExtractionResult` | no |
| `adjudication` | cartographer | T1 | `high` | `Adjudication` | no |
| `narration` | cherry_pick_worker | T2 | `high` | `ConflictNarration` | no |
| `disposition_assistant` | disposition_assistant | T2 | `low` | `DisplayOnlyText` | no |

`xhigh` is reserved for the recall domain's listwise rerank profile, which the recall
lead owns. It is deliberately absent here rather than stubbed.

**Every profile is validated at import time.** Schema derivation, forbidden-field
refusal, token-budget sanity and cacheable-prefix length all run in the import, so a
profile that could not have been called correctly cannot be imported at all. Adding
`defeater_code` to `DisplayOnlyText` does not produce a bad disposition — it produces a
failed import.

---

## What each module is for

| Module | The decision it implements |
|---|---|
| `call.py` | The zero-tool call shape, the one-retry-then-dead-letter rule, `warm_then_fanout` |
| `transport.py` | A3: `bedrock-runtime` `InvokeModel`, Anthropic native body, `au.*` profile ARNs resolved at start-up. A6: the sampling-parameter ban |
| `schema.py` | A7: Pydantic → Bedrock-legal JSON Schema, stripped keywords re-imposed client-side |
| `cache.py` | A9: one `cache_control` breakpoint on the last system block; the warm registry |
| `refusal.py` | A8: `stop_reason` before `content`; a refusal becomes a `silence_ledger` row |
| `cassette.py` | The offline provider, its key rule, and the prefix-drift refusal |
| `profiles/` | The register, and the byte-frozen rubric every call shares |
| `fallback_toolform.py` | AR-1: forced `tool_choice` + `strict: true`, **written and unused** |
| `errors.py` | The refusal vocabulary. Nothing in this package catches any of it |

### The request body, in full

```jsonc
{
  "anthropic_version": "bedrock-2023-05-31",
  "max_tokens": 8000,                       // caps thinking PLUS text (A5)
  "system": [ {"type": "text", "text": "…rubric…"},
              {"type": "text", "text": "…task…",
               "cache_control": {"type": "ephemeral"}} ],   // exactly one, on the last
  "messages": [ {"role": "user", "content": [
      {"type": "text", "text": "<trusted_context>…</trusted_context>…"},
      {"type": "text", "text": "<MAINLINE-UNTRUSTED-1a2b…>…document…</MAINLINE-UNTRUSTED-1a2b…>"}
  ]} ],
  "thinking": {"type": "adaptive"},         // explicit on every call, never disabled
  "output_config": {"effort": "low",
                    "format": {"type": "json_schema", "name": "…", "schema": { … }}}
}
```

Absent, and re-checked as absent on every built body: `temperature`, `top_p`, `top_k`,
`tools`, `tool_choice`, `toolConfig`.

---

## Running it

Everything runs **with no AWS account and no network**. The cassette provider is the
default.

```bash
uv run --package mainline-agentkit pytest packages/mainline-agentkit   # 104 tests
cd packages/mainline-agentkit && mypy && ruff check . && ruff format --check .
python packages/mainline-agentkit/tests/make_cassettes.py              # re-record
```

| Environment variable | Default | Meaning |
|---|---|---|
| `MAINLINE_AGENT_PROVIDER` | `cassette` | `cassette` or `bedrock` |
| `MAINLINE_AGENT_ALLOW_LIVE` | unset | The **second** lock on the live path |
| `MAINLINE_CASSETTE_DIR` | unset | Where recorded interactions live |
| `MAINLINE_CASSETTE_MODE` | `replay` | `replay` or `record` |
| `MAINLINE_BEDROCK_REGION` | `ap-southeast-2` | Where the `au.*` profiles are |
| `MAINLINE_AR1_FALLBACK` | unset | The AR-1 tool-form switch. Off |
| `MAINLINE_WARM_TIMEOUT_S` | `30` | Fan-out warming budget |

Reaching Bedrock requires `MAINLINE_AGENT_PROVIDER=bedrock` **and**
`MAINLINE_AGENT_ALLOW_LIVE=1`. A live call that happens by accident costs money and
non-determinism, so it fails loudly instead. `boto3` is an optional extra, imported
lazily inside two functions; `tests/test_transport_residency.py` asserts that a
completed offline run never pulled it into memory.

---

## Honesty about the cassettes, and about what is unverified

**Every committed cassette is `"provenance": "synthetic"`, and a test asserts it.** AWS
credentials are not valid on the build machine as of 2026-08-07 (PL-3), so no
interaction in `tests/cassettes/` was recorded from a live model. They exercise *our*
code paths — the refusal order, the retry budget, the cache assertion, the prefix-drift
refusal — not the model's behaviour. When the live lane records real interactions they
carry `"provenance": "live"` and the field is what tells the two apart.

**AR-7, accepted and named:** everything green in CI is green against recorded output;
live behaviour can diverge silently. The nightly `cloud-verify` lane is where a fixed
sample is replayed against the live path and diffed on *schema conformance and refusal
class*, never on text.

Unverified against the live API, and marked as such in the code:

- **`GT-AG-01`** — that the native `InvokeModel` body accepts `output_config` on an
  `au.*` inference-profile ARN. If it does not, `fallback_toolform` is the
  pre-committed answer and it is already written.
- **`pattern`** is not in the documented-unsupported keyword set, so it stays in the
  wire schema and is *additionally* re-checked client-side. One flag
  (`strip_pattern=True`) moves it if the platform says otherwise.
- **The Bedrock Guardrails response key** (`amazon-bedrock-guardrailAction`) is taken
  from the InvokeModel response contract and is covered by a cassette rather than by a
  live observation. It is treated as a refusal either way.
- **Token estimation** for the cacheable-prefix check is four characters per token. It
  is an estimate, it feeds a *cost* control, and no gate and no ledger row is derived
  from it.

## What this package deliberately does not do

It holds **no database driver and no credential**. A refusal comes back as
`ModelRefused`; the caller — which holds the SQL role — turns it into a
`mainline_meas.silence_ledger` row with `silence_row_for_refusal()` and falls back to
the deterministic channel. There is no code path here that turns a refusal into an
empty result, because **a precursor the model declined to summarise must still block
the merge.**
