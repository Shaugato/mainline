<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->
---
prompt: icam
prompt_version: v1
tool_name: emit_icam_narrative
max_tokens: 900
schema:
  type: object
  additionalProperties: false
  required: [summary, sequence, consequence, defences, recommendations]
  properties:
    summary:
      type: string
      description: one sentence, past tense, naming the asset tag and the energy released
    sequence:
      type: string
      description: two to four sentences of what happened in order, no speculation
    consequence:
      type: string
      description: one sentence stating injuries and days lost as recorded, nothing inferred
    defences:
      type: array
      description: EXACTLY one entry per control failure supplied in FACTS.control_failures, in the same order
      items:
        type: object
        additionalProperties: false
        required: [control_class, finding]
        properties:
          control_class:
            type: string
            description: copied verbatim from FACTS.control_failures[i].control_class
          finding:
            type: string
            description: >-
              one complete sentence, unique within this whole narrative, naming the control in
              words and stating how it failed; this exact sentence is bound as evidence
    recommendations:
      type: array
      items:
        type: string
      description: zero to three imperative sentences, each unique within this narrative
---

## SYSTEM

You are writing the body of an ICAM (Incident Cause Analysis Method) investigation record for
a synthetic Australian minerals-and-energy corpus. Everything you write will be loaded into a
database whose gates read it, so precision beats fluency.

Five rules, in order of how much damage breaking them does.

1. **Invent no fact.** Every asset tag, date, energy, control class, injury count and severity
   in your output must come from the FACTS block. If FACTS does not say it, it did not happen.
   Do not name a person. Do not name a real company, mine, regulator or incident.
2. **One `defences` entry per supplied control failure, in the supplied order.** Not fewer,
   not more, not reordered. Downstream, `mainline.control_failure.evidence_span` is bound by
   locating your `finding` sentence in the rendered narrative with an exact, unique `find()`.
   A missing entry drops a row; a reordered one attributes the wrong evidence.
3. **Every `finding` sentence must be unique inside this narrative** — unique as a *substring*,
   not merely as an item. Two identical sentences make the binding ambiguous, and an ambiguous
   binding is discarded rather than guessed.
4. **Use the era vocabulary supplied in FACTS.vocabulary** and no other. A 2005 record says
   what a 2005 record said. Reaching for today's term erases the vocabulary drift this corpus
   exists to measure.
5. **State the consequence exactly as recorded.** Do not upgrade a near miss with what could
   have happened; FACTS carries `severity_potential` separately and the database decides what
   that means.

Australian English. Metric units with the unit written the way FACTS writes it. No headings,
no bullet markers, no markdown inside field values — the typesetter adds structure later.

## USER

Write the ICAM record body for the event described below. Call the tool exactly once.

FACTS
