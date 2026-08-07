# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The golden corpus: one document per analyser behaviour that must never change silently.

Each entry pins a specific claim.  If a change to the tokeniser, the unit table, the stopword
list or the stemmer alters any of them, ``tests/unit/recall_lexical/test_analyser_golden.py``
fails and names the document — which is the point.  **A changed analyser invalidates every
posting in ``mainline.lex_posting``**, so the correct response to this test going red is
either to revert the change or to schedule a re-index, never to regenerate the file.

The texts are synthetic.  They are written in the register of MSHA Part 50 narratives and CSB
investigation summaries, but they describe no real incident and name no real person.
"""

from __future__ import annotations

from typing import Final

__all__ = ["GOLDEN_CORPUS"]

GOLDEN_CORPUS: Final[dict[str, str]] = {
    # ── the headline claim: an identifier survives, whole and in parts, unstemmed ──────────
    "identifier-tag": "Vessel K-401 overpressured after the PSV on TK-12 lifted late.",
    "identifier-near-miss": "Pump K402 tripped on high vibration; unrelated to the K-401 event.",
    "identifier-leading-zero": "Control loop CC-07 was bypassed; CC-7 had been bypassed in 2019.",
    "identifier-glued": "H2S alarmed in the sump while N2 purge was still lined up.",
    "identifier-slash": "OEM part 4C/9911-B was substituted with a non-OEM equivalent.",
    "identifier-underscore": "Tag FT_1042A read zero flow for eleven minutes before the alarm.",
    # ── quantities: SI normalisation, and the conflation that must not happen ─────────────
    "quantity-ppm": "Hydrogen sulfide reached 10 ppm at the breathing zone.",
    "quantity-percent-equivalence": "Methane measured 0.1 % by volume, equal to 1000 ppm.",
    "quantity-lel": "The atmosphere was 25 %LEL when the hot work permit was signed.",
    "quantity-percent-not-lel": "The tank was 25 % full when the transfer was stopped.",
    "quantity-pressure": "Discharge pressure was 100 psi against a 689 kPa relief setting.",
    "quantity-gauge": "Suction showed 30 psig; the absolute equivalent was never recorded.",
    "quantity-temperature": "Bearing temperature rose to 50 °C, then 122 degF on the spare.",
    "quantity-time": "Isolation was left in place for 30 min beyond the shift handover.",
    "quantity-negative": "Ambient was -5 °C and the drain froze solid overnight.",
    "quantity-scientific": "Leak rate was estimated at 1.2e-3 m3/h through the packing.",
    # ── citations and CAS numbers ─────────────────────────────────────────────────────────
    "citation-cfr": "Cited under 30 CFR 57.22239 and separately under 29 C.F.R. 1910.146.",
    "citation-section": "§ 57.22239(a) requires continuous monitoring during entry.",
    "citation-standards": "AS/NZS 3000 wiring rules, ISO 45001, ASME B31.3 and API RP 754 apply.",
    "citation-whs": "Contrary to WHS Regulation 2011 r 341, no rescue plan was in place.",
    "cas-valid": "Hydrogen sulfide (CAS 7783-06-4) and benzene (71-43-2) were both present.",
    "cas-invalid-checksum": "The label read 7783-06-9, which is not a valid registry number.",
    # ── prose: stemming, stopping, and the negations that are NOT stopped ─────────────────
    "prose-negation": "The isolation valve was not closed before the blind was removed.",
    "prose-stemming": "Operators were operating the operated valve under an operational permit.",
    "prose-hyphenated": "The lock-out tag-out procedure was signed off by a pre-start check.",
    "prose-stopwords": "It was on the deck and under the grating, over by the sump.",
    # ── unicode and typography that would otherwise fragment an identifier ───────────────
    # RUF001: the en dash and non-breaking hyphen ARE the test; they are what a copied-in
    # OEM manual actually contains, and they must not fragment the tag.
    "unicode-dashes": "Vessel K–401 and K‑402 appear with an en dash and a non-breaking hyphen.",  # noqa: RUF001
    "unicode-superscript": "Concentration was 3 mg/m³ and the volume was 12 m² of surface.",
    "unicode-micro": "Dust loading measured 40 µg/m3 on the personal sampler.",
    "unicode-casefold": "STRASSE and Straße both appear in the OEM manual heading.",
    # ── shapes that must NOT become identifiers or quantities ─────────────────────────────
    "boundary-word-unit": "The crew went in metres of water with a bar stock lever in hand.",
    "boundary-bare-number": "Only 3 of the 5 gas detectors had been bump tested.",
    "empty-ish": "   ---   ",
}
