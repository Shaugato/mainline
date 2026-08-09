<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# Prompts — the four stage-2 render nodes

`demo-engineering.md` §1 stage 2 names exactly four things a model may write in this corpus:
the **ICAM narrative**, the **clause body**, the **MOC justification**, and the
revision-table **"reason for change"** cell. There is one prompt file per node kind and there
are no others, because a fifth prompt would be a fifth place the corpus could acquire prose
nobody declared.

| file | `prompt` | node kind | fills |
|---|---|---|---|
| `icam.md` | `icam` | `event_narrative` | `mainline.event.narrative`, and the spans `mainline.control_failure.evidence_span` points into |
| `clause.md` | `clause` | `clause_text` | `mainline.clause_version.canon_text` |
| `moc.md` | `moc` | `moc_justification` | the MOC dossier body `corpus-docx` typesets into `MOC-*.docx` |
| `revreason.md` | `revreason` | `revision_reason` | the revision-history "reason for change" cell, and the citation lines `mainline.blame_edge.evidence_quote_sha256` digests |

## File format

Each file is YAML front matter followed by two fenced sections:

```
---
prompt: icam
prompt_version: v1
tool_name: emit_icam_narrative
max_tokens: 900
schema: { … strict JSON Schema … }
---

## SYSTEM
… system prompt …

## USER
… user prompt …
```

`mainline_corpus.prompts.load("icam")` parses that into a `Prompt`. The parse is strict:
a missing section, an unknown front-matter key, a schema that is not
`additionalProperties: false`, or a schema with an optional property is a `PromptError`.
Strict tool-use JSON is only strict if the schema is, and a schema that drifted open would
turn a refusal into a silently-shorter response.

## `prompt_version` is the ONLY thing that may invalidate the cache

The render cache is keyed by `sha256(canonical_prompt ‖ model_id ‖ prompt_version)`.
Because the canonical prompt already contains the template's own digest, **editing a prompt
body changes every key that prompt produced** — the cache does not go stale, it goes *absent*,
and `corpusgen render` rebuilds exactly the affected entries.

So the rule is procedural, not mechanical: **edit a prompt, bump its `prompt_version` in the
same commit.** The version is what a human reads in `corpus.lock.json` and on the honesty
card; leaving it at `v1` across a rewrite makes the lock say something false about which text
produced the corpus. `render/verify.py` cross-checks the committed entries' recorded
`prompt_template_sha256` against the files on disk and refuses when they disagree, so the
omission is caught — but it is caught as a diff, and the version is what explains it.

Every prompt here starts at **`v1`**. `demo-engineering.md`'s illustrative lock fragment shows
`{"icam":"v3","clause":"v5","moc":"v2","revreason":"v2"}`; those were an example of the
*shape* of the field. Shipping `v3` for a prompt that has been written once would be a small
lie about this corpus's history, and this domain does not get to tell small ones.

## What these prompts are not

They are **not** on the demo's critical path. `--offline` is the default (ADR 0032): the
`template` tier composes the bulk of the corpus deterministically from the skeleton and the
gazetteer, and the `authored` tier supplies every camera-facing word verbatim from
`fixtures/corpus/authored/`. These files exist so that the `bedrock` tier is a *real,
reviewable* implementation rather than a claim — and so that if AWS credentials become valid
before D-5, turning the model on is a policy flag and a cache rebuild, not a redesign.
