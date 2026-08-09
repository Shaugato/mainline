<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The hostile-document corpus

Forty-nine hostile documents and eight negative controls, each asserting a **named
outcome** — not that an exception was raised.

Every file under `corpus/` is one document, one declared attack class, and one expected
verdict. Run them:

```
pytest tests/security/injection -q
```

Nothing here needs AWS, a CockroachDB cluster, a model, or a credential. Two lanes are
optional and **neither is simulated when it is absent**: the ANCHORLOCK integration lane
skips with the import error in the skip reason when `mainline_domain` is not importable,
and the schema-drift alarm skips the same way when `mainline_agentkit` is not.

---

## What this corpus is evidence of, and what it is not

**It is evidence that a hostile document reaches a component with no capability to act on
it, and that the several ways we notice it are additive.** Each case names the layer that
refused it, so a reviewer can see that the layers do different work rather than the same
work three times.

**It is not evidence of detection coverage, and no coverage claim is made anywhere.** The
corpus is ours. We wrote both the attacks and the controls, which is the weakest possible
adversarial setting — it is published with the repository precisely so that a stranger
can add a case we did not think of. Every blocked or anchor-rejected document writes a
`document_intake_finding`: **the injection is evidence.**

### What none of this fixes

> **A plausible-but-false narrative in an otherwise clean PDF. Content authenticity is
> out of scope; provenance is in scope.**

That sentence is the honest boundary of the whole posture and it is worth being precise
about. If a contractor submits an incident report that is well-formed, contains no
imperative, forges no anchor, names no tool, and simply *lies* — the pressure was 120 kPa
when it was 400, the isolation was verified when it was not — then nothing in this
directory will notice. Six layers of injection defence are six layers of "did this
document try to give the reader instructions", and a lie gives no instructions.

What MAINLINE does instead is refuse to let the lie become anonymous. The bytes are in S3
under Object Lock with their digest in the custody ledger before parsing begins; the
clause that results carries a blame pointer to the incident that wrote it; the merge that
relies on it is a signed, dated, attributable act. **Provenance is what makes a false
narrative someone's, and that is a different guarantee from truth.** We say so here, in
the package README, in `VERIFY.md` and on camera, rather than letting a reader assume the
stronger claim.

Two more limits, stated for the same reason:

* **The offline screen is not Bedrock Guardrails.** `LocalPromptAttackScreen` is a small
  set of high-precision regular expressions, with no classifier and no notion of intent.
  It will not catch a paraphrase it has never seen and it is trivially evadable by anyone
  who reads `screen.py` — which is committed and meant to be read. It exists because a
  degradation ladder whose bottom rung is "no screening" is not a ladder, and because a
  corpus that only ran when an AWS account was reachable would not run.
* **The guardrail is committed, not applied.** `config/guardrail.json` is a real
  `CreateGuardrail` body and CI asserts its shape, including that `crossRegionConfig` is
  absent. It has never been applied to a live account: AWS credentials are not valid on
  the build machine (PL-3). The document is the committed intent; it is not evidence that
  a guardrail exists.

---

## The twelve classes

| Class | Cases | What it is |
|---|---|---|
| `direct_instruction_override` | 5 | "Ignore all previous instructions", in five registers |
| `role_play_framing` | 4 | Reassigning the reader's identity |
| `encoded_payload` | 4 | base64, including one that decodes to something harmless |
| `homoglyph_injection` | 4 | Cyrillic look-alikes, in prose and inside an equipment tag |
| `zero_width_injection` | 4 | Invisible characters, including one splitting a tag |
| `fake_system_reminder` | 4 | Forged operator markup, including our own delimiters |
| `tool_name_mention` | 4 | MCP verbs, IAM actions, JSON tool definitions |
| `credential_exfiltration` | 4 | System-prompt disclosure and egress requests |
| `severity_inflation` | 4 | Arguing a fatality potential the coded field does not carry |
| `severity_deflation` | 4 | The dangerous direction, and the one with a motive |
| `forged_equipment_tag` | 5 | A clause redirected to equipment the document never names |
| `pdf_table_cell` | 3 | Injected text in a table cell, including a real PDF file |

Plus **eight negative controls**: clean procedures, second-person safety prose, en dashes,
the word "tool" in its plant sense, a severity value in the coded field it belongs to, and
a URL in a reference list. *A screen that refuses everything passes a corpus made entirely
of attacks.* The negative controls are what make the positive results mean anything, and
`test_negative_controls_are_clean` is as load-bearing as any case above it.

---

## The six named outcomes

| Outcome | Layer | Meaning |
|---|---|---|
| `blocked_prompt_attack` | L2 | A named detector fired. The extraction never ran. |
| `flagged_obfuscation` | L2 | Masking with no imperative. Routed to a human, not blocked. |
| `contained_unknown_field` | L3 | The payload carried a key the schema does not declare. |
| `contained_type_violation` | L3 | A declared key with an undeclared shape or an off-enum value. |
| `anchor_rejected` | L4 | The cue named a hard anchor absent from its own source document. |
| `value_only_distortion` | L3 | **The residual.** Schema-valid; only declared values moved. |

`value_only_distortion` is the honest one and it is admitted, not refused. The record now
carries a value an attacker moved — `severity-deflate-003-interval-widened` widens a
gas-test interval from 30 minutes to 120 — and the finding names the exact field paths.
Refusing it here would be a lie about what the posture achieves; hiding it would be worse.
What catches it *after* this is the deterministic first pass and the CAT verifier, which
hard-reject any numeric, unit or comparator disagreement between the two readings, and
those belong to the algorithms domain.

### Why short-circuiting matters

The layers fire in order and the first refusal wins. So a case whose expected outcome is
`contained_unknown_field` is *also* asserting that layer 2 did **not** fire on it — which
is a stronger statement than it looks. It is the statement that the corpus is not passing
because one over-eager regular expression catches everything.

`severity-inflate-001` and `severity-inflate-003` are the same intent written two ways:
one as data in an appendix table, one as an instruction. The first is caught by layer 3
because the schema has no `severity` field; the second by layer 2 because it is an
imperative. That pair is the argument that the layers are additive rather than redundant.

### The pessimistic assumption

For layers 3 and 4, a case supplies the payload a **fully compromised** model would
return — one that did exactly what the injected text asked. We do not claim the model
resists injection. We claim that if it does not, the deterministic layers after it still
refuse. That is the only version of this claim that can be tested without a model in the
loop, and it is the stronger one.

---

## Adding a case

Drop one JSON file into `corpus/`. No generator, no registry, no code change: the suite
globs the directory.

```json
{
  "$license": "SPDX-FileCopyrightText: 2026 MAINLINE contributors / SPDX-License-Identifier: FSL-1.1-ALv2",
  "id": "override-006-your-case",
  "class": "direct_instruction_override",
  "title": "One line a reviewer can read",
  "note": "Why this outcome is the right one, and what the case does NOT prove.",
  "media_type": "text/plain",
  "document": "...the full document text...",
  "document_sha256": "<sha256 of the document text as UTF-8>",
  "injected_span": "the exact substring that is the attack",
  "expected_outcome": "blocked_prompt_attack",
  "expected_layer": "L2_delimit_and_datamark"
}
```

Optional keys, each enabling one more assertion:

* `expected_detector` — the named rule that must fire. Without it the case only asserts an
  outcome, and a case that does not name its detector cannot notice a broad regex
  absorbing it.
* `cue` — `{cue_id, text, declared_anchors[]}`. Enables layer 4 and runs in **both**
  extractor lanes.
* `expected_rejections` — `["equipment_tag:P-205B"]`. Names which anchor was forged.
* `proposal`, `baseline` — what a compromised model returns and the honest reading.
  Enables layer 3 against `fixtures/extraction.schema.json`.
* `expected_distorted_fields` — the field paths a `value_only_distortion` moved.
* `pdf` — a path under `corpus/` whose text operators become the document. Then
  `document_sha256` is the digest of the **PDF file**, because that is what the custody
  preamble records.
* `benign: true` — a negative control. Expected outcome `clean`, expected layer `""`.

Four whole-corpus assertions will then apply to your case automatically: the injected span
must actually be in the document, the digest must match the source bytes, the outcome must
agree with the layer, and any non-clean outcome must have written a finding.

---

## What is in `fixtures/`

| File | What it is |
|---|---|
| `gazetteer.json` | The word lists the fallback anchor extractor uses when `mainline_domain` is not importable. Copied verbatim from the committed ANCHORLOCK TOMLs at recorded digests, so the two extractors cannot drift by a typo. |
| `extraction.schema.json` | The wire schema layer-3 cases are contained by, emitted by `bedrock_schema(ExtractionResult)`. A drift alarm re-derives it whenever `mainline_agentkit` imports. |
| `tool_construction/positive/` | Three modules that **deliberately** build a tool surface, in five shapes. `scripts/agents/assert_no_tool_construction.py` must fail on this directory. PL-2: a scanner that has never been red asserts nothing. |
| `tool_construction/negative/` | The shapes the scan must **not** flag — `"tools": []` and same-name derivations — so its two exceptions are themselves tested. |

---

## What `test_layers.py` proves that the corpus cannot

Three tests there remove a control and assert the corpus stops being refused:
`test_a_screen_with_no_detectors_stops_blocking_the_corpus`,
`test_a_stub_extractor_would_pass_every_forged_anchor`, and
`test_a_schema_without_additional_properties_false_is_refused`. Without them, a case could
be passing for a reason other than the control it names. With them, the corpus is
*sensitive* to the posture rather than merely consistent with it.
