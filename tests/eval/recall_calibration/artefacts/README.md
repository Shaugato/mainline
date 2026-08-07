<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# Calibration artefacts

Written by `tests/eval/recall_calibration/test_calibration_report.py` on every run of the
lane. Two files, regenerated rather than hand-maintained:

| file | what it is |
|---|---|
| `calibration_report.json` | The reliability diagram, Brier / ECE / MCE, the fitted calibrator's knots and provenance, the corpus label, and the naive-baseline comparison. |
| `calibration_report.md` | The same reliability diagram, readable without a plotting library, stamped with what the corpus it measured is worth. |

**Read the stamp before the numbers.** The lane resolves its labelled set in a fixed order —
`$TRAPPOINT_RECALL_CALIBRATION_SET`, then the shared GS0 gold set, then the committed
synthetic stand-in — and the artefact records which one it used. A report marked `SYNTHETIC`
characterises the calibrator implementation and nothing about the product; a report marked
`PRELIMINARY` claims no customer-grade floor. Both stamps are reproduced in the Markdown
header so a screenshot cannot lose them.

Three fields are worth knowing about:

* **`fit_folds` and `eval_folds` are disjoint, and the code refuses to make them otherwise.**
  A calibrator scored on its own fold reports the sharpness of its training data.
* **`calibrator.x` / `calibrator.y` are the whole model.** `evaluate_knots` in
  `trappoint_recall.fusion.calibration` reproduces every probability from them with nothing
  but the standard library. There is no pickle anywhere in this path.
* **`baseline` compares the temporally-blocked evaluation against an exchangeable probe.**
  The gap between the two is corpus drift — the conformal exchangeability assumption being
  measured rather than restated. It is reported, never gated on: a floor on it would be a
  claim about the corpus.
