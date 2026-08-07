<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Recall corpora fixtures

**Every record in here is invented.** These are a *synthetic replica* — records shaped
exactly like MSHA Part 50 extracts, MSHA fatality investigation reports, CSB investigation
reports and Australian state-regulator safety alerts, generated deterministically from a
seed by `trappoint_recall.corpora.synthetic`. No real incident, no real person, no real
operation.

**Real corpora are for the evaluation harness. The demo tenant is synthetic. A real
fatality is never presented as a fictional site's record.** That rule is in
`provenance.json`, it is enforced at construction time by
`trappoint_recall.corpora.provenance.FixtureProvenance` — which refuses
`corpus_class='real_regulator'` with any destination but the harness — and it is checked by
`tests/eval/recall_corpora/test_goldset_invariants.py`. Even these synthetic fixtures are
marked `harness_only`: a corpus that models fatalities has no business in a demo either.

Real data is fetched by `scripts/recall/fetch_corpora.py` into a **gitignored cache**
(`out/recall-corpora/`, or `$MAINLINE_RECALL_CORPUS_CACHE`) and is never committed.

## Layout

| Path | What it is |
|---|---|
| `inputs/msha_part50.psv` | Bar-delimited Part 50 extract, real header spelling. Narratives capped at 384 chars, because that is the real column width. Feeds G2. |
| `inputs/msha_fatality_reports.jsonl` | `{external_ref, text}` envelopes. Everything else — dates, classification, equipment, the work description, the citations — is **parsed out of the report text**, so the real parser is exercised rather than bypassed. |
| `inputs/csb_reports.jsonl` | CSB investigation reports. Severity from published casualty counts. |
| `inputs/au_regulator_alerts.jsonl` | State-regulator alerts. Severity from the regulator's classification. |
| `inputs/g3_adjudication.jsonl` | A 50-pair returned adjudication worksheet: model pre-label, two rater grades, adjudicator, confirmation timestamps. |
| `goldsets/g1_citations.qrels.jsonl` | G1 — distant supervision from investigator citations. |
| `goldsets/g2_codes.qrels.jsonl` | G2 — structured-code co-membership. **Calibrator-only**; the flag is on line 1. |
| `goldsets/g3_adjudicated.qrels.jsonl` | G3 — human-confirmed UMBRELA labels, plus tagged LLM-only pre-labels. |
| `goldsets/g4_retro.qrels.jsonl` + `.queries.jsonl` | G4 — the money metric. One retro permit per fatality, each with its own time wall. |
| `goldsets/negative_control.queries.jsonl` | 300 routine permits from a 24-month replay: the nuisance-rate denominator. |
| `goldsets/gs0/` | GS0 — the corpus a release gate reads: G4 permits + routine replay, G4's distant supervision overlaid with G3's blinded human labels. |
| `goldsets/build_report.json` | Every drop count, every wall, every digest. |
| `thymogate_panel.json` | The M5 panel: one known killer per hazard-energy class, mixed archival levels. |
| `provenance.json` | Digest and provenance of every committed input. |

## Rebuilding

```sh
uv run python scripts/recall/build_goldsets.py --from-fixtures   # hermetic, no network
uv run python scripts/recall/build_goldsets.py --check           # rebuild and diff
uv run python scripts/recall/build_goldsets.py --regenerate-fixtures
```

The build is idempotent: same inputs, byte-identical outputs. `--check` is the CI
assertion that the committed gold sets really are the output of the committed inputs — a
gold set nobody can rebuild is a gold set nobody can review.

## Two things this fixture tree is *not*

**Not a measurement.** Any retrieval number computed here is a number about the generator.
`goldsets/gs0/manifest.json` carries `synthetic: true` and `preliminary: true`, and the
harness stamps both on every report it renders.

**Not auto-selected by the harness.** `tests/eval/recall/corpus_resolution.py` picks up a
corpus at `tests/fixtures/recall/gs0`, and GS0 is deliberately *not* written there. The
harness's satisfiability suite drives `oracles.ShoutingBackend`, which fabricates
distractor document ids (`E-NEAR-<suffix>`, …) that exist only in the harness's own
self-test corpus; against real regulator identifiers those ids are unjudged, `P@block`
skips them, and an indiscriminate blocker would score 1.00 — turning a green test that
proves the noise gates bite into a red one. Rather than fabricate corpus documents to
satisfy a test double, GS0 lives at `goldsets/gs0` and is opted into explicitly:

```sh
TRAPPOINT_RECALL_CORPUS=tests/fixtures/recall/goldsets/gs0 uv run pytest tests/eval/recall
```
