<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# `mainline-quarantine`

The six-layer prompt-injection posture of `ARCHITECTURE.md` §8.4, as executable controls.

The claim this package is built to make good on is one sentence: **no component that
touches an untrusted document holds a tool, a write credential, or a path to the gate.**
Everything below is either that sentence enforced, or an honest statement of where it
stops.

```
L5  capability starvation      before a byte is read          capability.py
L1  structural quarantine      the call shape, not a branch    (agentkit + the AST scan)
L2  delimit, datamark, screen  sentinel + guardContent tag     sentinel.py guardrail.py screen.py
L3  output-schema containment  additionalProperties: false     containment.py
L4  semantic anchoring         a cue may only name what it read anchoring.py gazetteer.py
L6  the injection is evidence  every refusal is a row          finding.py
```

`pipeline.intake()` runs them in the order they fire — which is **not** the order they are
numbered in §8.4, and the difference is deliberate. Layer 5 is numbered fifth but is a
*precondition*: a process that discovers it holds the wrong SQL role after it has already
read the attacker's bytes has discovered it too late.

---

## The property that makes this package worth separating

**Its import graph is standard library only.** No `boto3`, no driver, no model client, no
YAML parser at module scope. The three third-party modules it can ever touch — `boto3` for
the live guardrail, `PyYAML` for the fleet register, `mainline_domain` for ANCHORLOCK —
are imported *inside functions* and all three are optional extras.

`tests/security/injection/test_layers.py::test_the_quarantine_imports_nothing_that_can_reach_a_model_or_a_database`
walks every source file and fails on a module-level third-party import. That test is what
makes the empty `dependencies = []` in `pyproject.toml` a claim rather than a coincidence:
the component that reads the attacker's bytes holds nothing.

---

## Layer by layer

### L1 — structural quarantine

Not implemented here, because it is not a step. `mainline_agentkit.call.quarantined_call`
has no `tools` parameter, and `scripts/agents/assert_no_tool_construction.py` walks every
`src` tree under `packages/*` and `verticals/*/packages/*` and fails if a dict literal, a
keyword argument, a subscript assignment, a name binding or a JSON string ever constructs
`tools`, `tool_choice`, `toolConfig` or `mcp_servers`.

Two exceptions, both narrow, both tested by fixtures: a literal empty value is the
*declaration of absence* (`"tools": []` in a profile description says the profile holds
none), and a value derived from something already called `tools` is a *read* rather than a
construction. Exactly one file is exempt by exact path — AR-1's `fallback_toolform.py` —
and the exemption holds only while the file exists, carries its marker, and **nothing
imports it**.

### L2 — delimiting, datamarking, and the guardrail

Two wrappers doing different jobs. The **sentinel** is ours, minted per request from eight
random bytes, so a document that learned last week's delimiter cannot close this week's
block; `wrap_untrusted()` refuses outright if the document already contains it, because
re-wrapping around attacker-chosen bytes is how a delimiter becomes decoration.

The **`<amazon-bedrock-guardrails-guardContent_…>` tag** is Amazon's and it is the one with
teeth: `PROMPT_ATTACK` applies **only to tagged spans**, so untagged untrusted text reaches
the model unfiltered and the call returns an ordinary 200.
`assert_untrusted_spans_tagged()` refuses that body. *A guardrail that is configured,
attached, billed and silently not applied is worse than none, because the architecture
diagram claims it.*

`config/guardrail.json` is a committed `CreateGuardrail` body:
`PROMPT_ATTACK` at `inputStrength: HIGH` / `inputAction: BLOCK`, and **no
`crossRegionConfig`** — a guardrail profile routes inference to Regions AWS chooses, and
attaching one would move Australian incident text offshore with no error and no change in
the response shape. A test asserts the key is absent recursively, because an empty object
is not the same as absent. `MISCONDUCT` and `VIOLENCE` are listed and explicitly disabled:
this corpus is cyanide leaching, H₂S and confined-space chemistry, and a content filter at
any strength would refuse exactly the documents the product exists to remember.

`LocalPromptAttackScreen` is the offline half. **It is not Bedrock Guardrails**, has no
classifier, and is trivially evadable by anyone who reads `screen.py`. It exists because a
degradation ladder whose bottom rung is "no screening" is not a ladder, and because CI must
be able to assert a named outcome without an AWS account.

### L3 — output-schema containment

Static half: every object node must carry `additionalProperties: false`, and no property
anywhere may be named in `GATE_ARMING_FIELDS` (`severity`, `potential_admitted`,
`defeater_code`, `rationale`, …). A `severity` field in an extraction schema is not a bug
in a prompt — it is a *capability*, granted to a model, to set the field §8.4 reserves to a
coded field, a regulator classification or a signed human.

Dynamic half: given the payload a fully compromised model would return, report the largest
effect it had — an unknown field (refused), a type or enum violation (refused), or a
`value_only_distortion` naming the exact field paths that moved.

### L4 — semantic anchoring

A cue may only name hard anchors its own source document contains: equipment tags,
isolation points, instrument loops, regulatory citations, CAS numbers and setpoints. Pure
regex plus a committed gazetteer — nothing a model can be talked out of.

Two boundaries stated rather than hidden. **Setpoints are compared as written, never
SI-folded**: `0.35 MPa` does not match `350 kPa` and such a cue is *rejected*, because
folding requires deciding gauge versus absolute and `50 psig → 446 kPa(a)` silently flips a
safe-direction comparison. **`named_role` is not checked**, because roles are legitimately
paraphrased and enforcing them would manufacture rejections carrying no information.

Two implementations, no stub: `DomainAnchorExtractor` wraps the algorithms domain's
ANCHORLOCK extractor through a `Protocol` when it is importable, and
`GazetteerAnchorExtractor` is the committed-word-list fallback. The corpus runs **both** and
fails on any disagreement. There is no third mode in which layer 4 returns "no anchors,
nothing to check" — an extractor that finds nothing turns every anchor-based refusal into a
pass, which is why `AnchorExtractorUnavailable` exists.

### L5 — capability starvation

The structural version of this control is IAM, the network and the grant graph (§8.2
E1–E4, another worker's). This is the in-process guard that runs *before* the process reads
anything: what the process actually holds, compared against `spec/agents/fleet.yaml`. A
gate-writing role is refused from the authoritative 11.2 role matrix rather than from the
register's own boolean — the P2 rule applied to a YAML file. An agent the register does not
list is refused, never treated as unconstrained.

### L6 — the injection is evidence

Every non-clean verdict becomes a `DocumentIntakeFinding` routed to `human_review`. There
is no drop path and the constructor refuses one. The finding carries the **digest** of the
offending span, not the span: an operator triaging a queue of these should not have to
re-read the attack, and the bytes are already in S3 under Object Lock from the custody
preamble, recoverable with the access recorded.

*Ownership note:* the DDL for `mainline.document_intake_finding` belongs to the data-model
domain. `DocumentIntakeFinding.to_row()` is this package's statement of the payload that
table must accept.

---

## What none of this fixes

> **A plausible-but-false narrative in an otherwise clean PDF. Content authenticity is out
> of scope; provenance is in scope.**

Six layers of injection defence answer "did this document try to give its reader
instructions". A lie gives no instructions. What MAINLINE does instead is refuse to let the
lie be anonymous: the bytes are digested and Object-Locked before parsing, the clause
carries a blame pointer, and the merge that relies on it is a signed, dated, attributable
act. Provenance makes a false narrative *someone's*, which is a different guarantee from
truth.

Two further limits, in the same spirit: the local screen is not Guardrails and claims no
detection coverage (AR-9), and `config/guardrail.json` has never been applied to a live
account — AWS credentials are not valid on the build machine (PL-3), so the file is
committed intent, not evidence that a guardrail exists.

---

## Using it

```python
from mainline_quarantine import (
    LocalPromptAttackScreen,
    UntrustedDocument,
    GazetteerAnchorExtractor,
    Cue,
    intake,
)

verdict = intake(
    UntrustedDocument(doc_id="INC-2024-0881", text=extracted, source_sha256=digest),
    screen=LocalPromptAttackScreen(),
    proposal=model_payload,  # what the model returned
    schema=wire_schema,  # what it was constrained by
    baseline=deterministic_reading,  # so a distortion can be named exactly
    cue=Cue(cue_id="c1", text=cue_text, declared_anchors=tuple(model_payload["anchors"])),
    extractor=GazetteerAnchorExtractor.from_path(gazetteer),
)
if not verdict.admitted:
    write_findings(verdict.findings)  # never drop them
```

`verdict.admitted` is `True` for `CLEAN` **and** for `VALUE_ONLY_DISTORTION`, which is
admitted-and-flagged rather than refused. Pretending we refused it would be a lie about
what the posture achieves.

The corpus and its README are at `tests/security/injection/`.
