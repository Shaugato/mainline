<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0034 — Byte-reproducible `.docx`, and the dependency we did not take

**Status:** Accepted · **Date:** 2026-08-10 · **Domain:** corpus-demo · **Worker:** `corpus-docx`
**Implements:** corpus-demo **D4** (byte-reproducible `.docx`) and **D6** (the 2016 retypeset is a
genuinely different second template) · `research/06-build/demo-engineering.md` §1 stage 3

## Context

Stage 3 turns the committed answer key into controlled documents a judge can open. Two things
have to be true of the result and only one of them is about typography.

The first is legibility: a procedure must read as a controlled document in a two-second shot —
letterhead, numbered clause styles, revision-history table.

The second is the claim `MANIFEST.docx.sha256` makes. That file says *the same inputs produce the
same bytes on your machine as on ours*. It is the cheapest claim in the submission for a sceptic
to check and the most expensive one to be caught getting wrong, and it is false the moment a
build clock, a umask, a locale or a zlib version reaches a byte.

## Decision 1 — write the OOXML directly; take no new dependency

The brief names `docxtpl` 0.20 and `python-docx`. **Neither is in `uv.lock`.** `uv.lock` is a
plan invariant that exactly one worker owns, and PL-1 requires every proof to run on a stranger's
machine from that one resolution. Adding a dependency from here meant either editing a file this
worker does not own or shipping a module CI could not resolve.

So the package writes WordprocessingML and the OPC container itself: `zipwriter.py` (133 lines)
and `ooxml.py` (fragment builders), with `template.py` implementing the two ideas `docxtpl` adds
to Jinja2 — `{%p … %}` replaces its paragraph, `{%tr … %}` replaces its row.

This is not only a workaround. The brief's longest paragraph is about patching `python-docx`'s
`_ZipPkgWriter`, which stamps `time.localtime()` into every zip member. **There is no
`_ZipPkgWriter` to patch, because there is no `_ZipPkgWriter`.** The reproducibility property is
structural rather than repaired, and it cannot be undone by a minor-version bump in a library we
do not control.

**What this gives up, stated plainly.** `python-docx` has been read by far more documents than
our writer has written; a malformed part it would have rejected, we can emit. That risk is not
theoretical — see "What went wrong" below, where exactly that happened and was caught. It is
mitigated, not eliminated, by `verify.opens_with_python_docx`, an **optional** check that runs
only when `python-docx` happens to be importable and skips with a reason otherwise. If the
dependency ever lands in `uv.lock`, that check should become mandatory; the templates are
`docxtpl`-loadable and nothing in the render path is a private dialect.

## Decision 2 — the five pins that make the bytes a function of the inputs

| # | Source of variance | Pin |
|---|---|---|
| 1 | Member timestamps (`time.localtime()` via `ZipFile.writestr`) | `date_time = (1980, 1, 1, 0, 0, 0)` on every member |
| 2 | Member order (dict insertion order) | `sorted()` over part names — a code-point sort with no locale involvement |
| 3 | Host metadata (`create_system` 3 on POSIX / 0 on Windows, umask in `external_attr`) | `create_system = 0`, `external_attr = 0`, versions 20, flag bits 0, no extra field, no comment |
| 4 | Compression | **`ZIP_STORED`** — see below |
| 5 | Session state in `docProps` / `settings` | no `w:rsid`, no `TotalTime`, no `LastPrinted`, no `Pages`/`Words`; `dcterms:created`/`modified` are the *document's* effective date |

Pin 2 has a happy consequence rather than a special case: ASCII puts `[Content_Types].xml`
(`0x5B`) before `_rels/.rels` (`0x5F`) before `docProps/` before `word/`, so the deterministic
order and the order an OPC reader expects are the same order. `write_package` asserts it anyway.

### Why `ZIP_STORED` rather than a pinned DEFLATE level

The brief says "pin the compression level". **Pinning a level does not pin an implementation.**
DEFLATE output is a function of the zlib *build*, not only of the input and the level: several
distributions now ship zlib-ng, CPython links whatever the platform provides, and two conforming
implementations may legitimately emit different byte streams for identical input at identical
level. A cross-OS byte-equality claim resting on a level is a claim that is true on the machine
it was written on.

Storing is the only compression setting whose output is a pure function of the input on every
platform. OPC permits stored parts; Word opens them. The cost is size — twenty-one files, about
1.1 MB stored — and the purchase is the exact equality the `done_when` asks for. This is the one
place where the implementation deliberately differs from the letter of the brief, and it differs
in the direction of the brief's own stated goal.

### `dcterms` carries the document's date, not the build's

Zip metadata gets the 1980 epoch because no reader is meant to look at it. `docProps/core.xml`
gets the document's own `effective_on` because Word displays it and a controlled document whose
properties say 1980 contradicts its own letterhead. A document date is an *input*, so it may
safely be an output; a build date is not.

## Decision 3 — the retypeset is a second style sheet, not a string substitution

`house_style.py` holds two `HouseStyle` objects that differ in `styles.xml`, `numbering.xml`,
margins, fonts, heading case, sub-point numbering (`(a)` against `1)`) and the position of the
revision-history table (back in generation 1, front in generation 2). The clause *ordering*
difference is not styling at all: it comes from the answer key's `g1_ordinal`/`g2_ordinal`.

Generation 2's chapter titles are **derived, not authored**: a chapter is a control class, so the
title is that class's `label` in `gazetteer/control_classes.yaml`. `model.g2_heading` then
*asserts* that the label's middle digit matches the class's `barrier_role` — 1 preventive, 2
recovery — and raises `LayoutError` when they disagree. The renderer never trusts the digit it
was handed. That is P2's posture applied to layout: the value a layout reads is derived from an
authoritative source, and the derivation raises when the source is missing.

Generation 1's twelve procedural section titles *are* authored, in `G1_SECTION_TITLES`, and the
module says so. They are template furniture; no camera-facing artefact quotes them, so they
cannot drift against `VO.md` or the honesty card.

## Decision 4 — relationship ids are derived, never accepted

The brief warns that `docxtpl`'s render is not always idempotent with respect to relationship
ids and says to normalise rather than accept the flake. `template.normalise_relationship_ids`
runs on **every** render, whatever produced the input: ids are renumbered `rId1…rIdN` ordered by
`(Type, Target)` — the relationship's meaning, not its position in the file — and every reference
is rewritten in the same two-pass swap, so a rename like `{rId1→rId2, rId2→rId1}` cannot collapse.
`verify.relationship_ids_normalised` then re-derives the map for every `.rels` part of every
rendered document and requires it to be the identity.

## What the proof is, and where it stops

`corpusgen docx verify` runs eleven checks and all eleven pass here. The twelfth thing that
would complete the brief's list is not ours to run, and is named below.

* two in-process renders agree;
* two **subprocess** renders agree — a fresh interpreter is a different test, and is what
  exposes `PYTHONHASHSEED`, import order and module-level state built at first import;
* in-process agrees with subprocess, and both agree with the committed bytes;
* `MANIFEST.docx.sha256` reproduces exactly, over all 21 files;
* the committed templates equal a fresh build, byte for byte;
* the retypeset pair holds the identity claim (below);
* every `.rels` part is already canonical;
* no module in the package contains a clock, an entropy source or a locale lookup — scanned over
  *executable* source, with comments and string literals blanked by `tokenize`, because half
  these modules explain in prose which clock they refuse to call;
* the red control passes (below);
* `python-docx`, when present, opens all thirteen documents.

**The twelfth thing is engineered here and asserted elsewhere.** `ubuntu-latest` against
`windows-latest` requires a CI matrix job, and `.github/workflows/corpus.yml` belongs to
`corpus-freeze-load`. The engineering for it is complete — stored compression, pinned member
metadata, LF-only generated XML, no locale, no clock — and no file in this package claims the
matrix is green, because no file in this package can know.

## The red control, and why the first one was worthless

PL-2: a suite that has never been red asserts nothing. For a reproducibility claim there is a
specific quiet trap — **DOS timestamps have two-second resolution**, so two renders a second
apart agree by accident even with the pin removed, and the suite passes for the wrong reason.

`verify.pin_is_load_bearing` closes it without depending on timing. The first version probed
`zipfile.ZipInfo(filename=…)` and **was wrong**: that constructor's `date_time` default *is* the
DOS epoch, so the control passed while demonstrating nothing. The wall clock enters through
`ZipFile.writestr(name_as_str, data)` — precisely the call `python-docx`'s `_ZipPkgWriter` makes.
The control now exercises that call on a throwaway archive and requires the result to differ from
the epoch we pin to. It is recorded here because a control that passes for the wrong reason is
worse than no control, and the failure mode is easy to repeat.

## What went wrong, and what caught it

`opens_with_python_docx` is optional and skippable, and on its first run it rejected **all
thirteen documents**. `[Content_Types].xml` typed the main part with the WordprocessingML
*namespace URI* instead of its *content type* — a one-token confusion between two similar-looking
URIs. Every one of our own checks passed: our reader never consults `[Content_Types].xml`, so our
reader and our writer agreed with each other perfectly while Word would have called every file
corrupt.

That is the argument for keeping a third-party parse in the loop even when it must be allowed to
skip, and it is the concrete cost of Decision 1 showing up exactly where the decision predicted
it would.

## Consequences

* Editing a committed `.docx` is a build failure, not a change. Templates are generated;
  `build-templates --check` compares.
* Adding a part, a style or a run changes every digest. That is correct — the artefact changed —
  and it means `PRODUCER_VERSION` in `parts.py` is a real input to the manifest.
* The render set is **generation-uniform** by construction: every clause in issue on a target's
  date must carry the same `template_generation`, and `_assert_generation` refuses otherwise.
  One document in the committed answer key fails that test (`MRD/STD-ISO-006` from 2016-11-21
  onward, whose retypeset revision re-issued 25 of 26 clauses in force). Stage 3 renders thirteen
  other documents rather than inventing a generation-2 label for the remaining ten. That is a
  finding for whoever owns the retypeset injector, not a rendering problem to paper over.
* If `python-docx` and `docxtpl` later enter `uv.lock`, nothing here needs rewriting: make the
  optional check mandatory and, if desired, swap `template.render` for `docxtpl` — the templates
  are already in its idiom, and the deterministic writer stays either way.
