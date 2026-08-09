<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# The stage-3 templates — generated artefacts, not hand-authored documents

## Do not edit a `.docx` in this directory

Every file here is **built from source** by
`verticals/mainline/packages/mainline-corpus/src/mainline_corpus/docx/build_templates.py`, and
`corpusgen docx verify` compares the committed bytes against a fresh build on every run. A
hand-edited template fails that check rather than silently becoming the source of truth.

```
# rewrite all eight
python -m mainline_corpus.docx build-templates
# compare instead of writing
python -m mainline_corpus.docx build-templates --check
```

## What is here

Four document families times two house generations:

| | generation 1 (2004–2016) | generation 2 (2016 retypeset) |
|---|---|---|
| procedure | `pro_g1.docx` | `pro_g2.docx` |
| standard | `std_g1.docx` | `std_g2.docx` |
| management-of-change record | `moc_g1.docx` | `moc_g2.docx` |
| permit-to-work form set | `ptw_g1.docx` | `ptw_g2.docx` |

The two generations are **genuinely different templates**, which is decision **D6** and the
reason clause reflow in this corpus is real rather than simulated:

* different numbering schemes — `7.3` / `7.3.2(b)` against `5.2.1`;
* different style sheets — Arial with black rules against Calibri with a slate heading colour,
  full capitals against small capitals, different margins and different clause indents;
* different sub-point numbering — `(a) (b) (c)` against `1) 2) 3)`, in `word/numbering.xml`;
* the revision-history table at the **back** in generation 1 and at the **front** in generation 2.

A reader shown two of these side by side can say which generation each belongs to without
reading a word of the body. That is the point: the film's claim is that a clause's identity
survives a change of that magnitude.

## The template language

Each template carries Jinja tags in the `docxtpl` idiom — `{{ value }}`, `{%p statement %}` for a
statement that replaces its paragraph, `{%tr statement %}` for one that replaces its table row.
`mainline_corpus.docx.template` implements that idiom directly rather than importing `docxtpl`;
see `docs/adr/0034-reproducible-docx.md` for why, and for what that trade gives up.

## Reproducibility

These files are byte-reproducible. Zip member timestamps are pinned to the DOS epoch
`1980-01-01T00:00:00`, members are stored rather than deflated, member order is a code-point
sort, and no part carries a `w:rsid`, an editing-time counter or a locale-dependent string.
`docProps/app.xml` records the producer and its version. Digests are listed in
`../rendered/MANIFEST.docx.sha256` alongside the rendered documents.
