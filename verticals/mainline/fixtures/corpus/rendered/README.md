<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The rendered controlled documents

## Check them yourself, with a tool we did not write

```
cd verticals/mainline/fixtures/corpus
sha256sum -c rendered/MANIFEST.docx.sha256
```

`MANIFEST.docx.sha256` is exactly GNU `sha256sum` output — digest, two spaces, path, LF — with no
header and no comment line, so it parses. It covers all eight templates and all thirteen
rendered documents, twenty-one files, with paths relative to this directory's parent.

To regenerate:

```
python -m mainline_corpus.docx render     # documents + both manifests
python -m mainline_corpus.docx verify     # the reproducibility proof
```

## What "reproducible" is claimed to mean here

**Executed and asserted** by `corpusgen docx verify`:

* two in-process renders produce identical bytes;
* two renders in *fresh subprocesses* produce identical bytes — which is not the same test, and
  catches hash-seed, import-order and module-state effects an in-process repeat cannot see;
* those agree with each other and with the bytes committed in this directory;
* `MANIFEST.docx.sha256` reproduces exactly;
* the red control passes: the *unpinned* zip path still stamps a wall clock, so the equality
  above is produced by the pin rather than by two runs happening to land in the same second.

**Engineered here, asserted elsewhere:** equality across `ubuntu-latest` and `windows-latest`.
Everything that could differ between operating systems is removed at the source — members are
stored rather than deflated (so no zlib build can differ), member metadata is pinned, generated
XML is LF-only, no locale is consulted and no clock is read. The matrix job that *proves* it
lives in CI, which this worker does not own. Nothing here claims that job is green.

## The pair that carries beat 1

| | `MRD-PRO-MEC-014-r009-2016-11-02-g1.docx` | `MRD-PRO-MEC-014-r010-2016-11-21-g2.docx` |
|---|---|---|
| house style | 2004–2016 | 2016 retypeset |
| `clause_uuid` | `2ad35fa5-d174-5eb1-8550-05adfa90e08d` | **the same** |
| printed label | `7.3` | `5.2.1` |
| ordinal | 25 | 29 |
| heading | SECTION 7 — Monitoring, alarms and setpoints | CHAPTER 5 — seal-face high-temperature alarm and trip |

Nineteen days apart, one obligation, two documents that disagree about what a document *is*. The
label moved, the position moved, the identity did not. `MANIFEST.docx.json` states that as data
under `retypeset_pair`, and `CVY/PRO-HSE-012` goes through the same reflow so the claim is about
the retypeset rather than about one lucky document.

## Where the prose comes from — read the census before quoting it

`MANIFEST.docx.json` carries `renderer_census`, generated from the render rather than asserted.
Each clause body resolves through a provider chain, highest authority first:

1. `authored` — `fixtures/corpus/authored/clause_bodies.json`, hand-written;
2. `cache` — `fixtures/corpus/cache/clause_bodies.index.json`, written by the stage-2 renderer;
3. `structural` — composed deterministically from the gazetteer and the clause's own facts.

Providers that have not landed are skipped, never faked, and `body_providers_available` in the
sidecar says which were present. **Do not describe this prose as model-generated unless the
census says a model generated it.**

The composed tier is not filler. Each body states the obligation in the corpus's stable control
vocabulary, then names the same control in the words of the document's own decade — a 2013
revision says "change request" where a 2016 revision says "management of change" — because the
vocabulary drift the corpus measures has to be present on the page, not only in the JSONL behind
it. The definitions table at the front of each document prints that drift explicitly.

## Not claimed

That these documents were produced by, or reviewed by, anyone in the mining industry. Kestrel
Resources Pty Ltd is fictional, its four sites are fictional, and every incident reference in a
revision table points at a synthetic event in this repository's answer key.
