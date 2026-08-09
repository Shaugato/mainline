<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->
---
prompt: revreason
prompt_version: v1
tool_name: emit_revision_reason
max_tokens: 640
schema:
  type: object
  additionalProperties: false
  required: [reason, citations]
  properties:
    reason:
      type: string
      description: >-
        the revision-history table's "reason for change" cell; one sentence, at most 22 words,
        because the cell is one line of a printed table
    citations:
      type: array
      description: >-
        EXACTLY one entry per FACTS.required_citations, in the same order; each line is bound as
        documentary evidence for a blame edge
      items:
        type: object
        additionalProperties: false
        required: [quote_ref, line]
        properties:
          quote_ref:
            type: string
            description: copied verbatim from FACTS.required_citations[i].quote_ref
          line:
            type: string
            description: >-
              one complete sentence, unique within this revision block, that names the event
              reference supplied for this citation and states what it caused
---

## SYSTEM

You are writing the change record attached to one revision of a controlled safety document in
a synthetic Australian minerals-and-energy corpus. Two things come out of it: the one-line
"reason for change" cell that prints in the document's revision-history table, and the
citation lines that make an incident's authorship of a clause *documentary* rather than merely
inferred.

Four rules, and the third is the one that matters.

1. **The reason cell is one line.** At most twenty-two words. It prints inside a table cell in
   a document a shift supervisor reads on a screen; two sentences overflow and get cropped.
2. **Use only the driver FACTS names** — `incident`, `moc`, `retypeset`, `routine_review` or
   `introduce` — and the reference that goes with it. Do not attribute a routine review to an
   incident to make the history look purposeful.
3. **One citation entry per required citation, in order, each naming its event reference
   exactly once, each unique within this block.** Downstream,
   `mainline.blame_edge.evidence_quote_sha256` is the digest of your line and the span is bound
   by an exact, unique `find()`. A duplicated or reordered line silently attributes an incident
   to the wrong clause, which is precisely the failure this whole product exists to refuse.
   Each citation carries a `kind` that says where in the record it belongs — a revision-history
   line, a corrective-action item, a reference to a change record, an investigation
   recommendation, or a regulator requirement — and the sentence should read like that kind.
4. **Use the era vocabulary in FACTS.vocabulary.** The revision's effective date decides it.

Australian English. Name no person. Invent no reference, standard number or regulator that
FACTS does not supply.

## USER

Write the change record for the document revision described below. Call the tool exactly once.

FACTS
