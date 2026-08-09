# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Thresholds, register keys and caveats — one place, so a number has one producer.

Every threshold below was chosen **after** measuring the corpus, and each records the measured
value it was set beneath.  That order matters and is stated deliberately: a floor chosen before
the measurement is a wish, and a floor chosen at the measurement is a change detector rather
than a property test.  These are set with headroom, so an unrelated parameter change does not
turn this stage red, and a *real* regression — a retypeset that stopped reordering, a scheme
that stopped diverging — does.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

__all__ = [
    "MEASURED",
    "MIN_DOCUMENT_KENDALL_TAU",
    "MIN_LABEL_CHANGE_FRACTION",
    "MIN_MEAN_KENDALL_TAU",
    "MIN_ORDINAL_CHANGE_FRACTION",
    "MIN_PAIRS",
    "MIN_RETYPESET_DOCUMENTS",
    "MUST_NOT_CLAIM",
    "REGISTER_KEYS",
    "STAGE",
    "STAGE_TITLE",
    "TAUTOLOGICAL_REGISTERS",
]

STAGE: Final[str] = "3r"
STAGE_TITLE: Final[str] = "the reflow injector — the 2016 retypeset, measured"

#: The corpus as measured on the commit this stage was written against.  Recorded so a reader
#: can see the distance between the floor and the fact, and so a future drift is visible as a
#: difference from a *number* rather than only as a pass or a fail.
MEASURED: Final[Mapping[str, float]] = {
    "documents": 24.0,
    "pairs": 624.0,
    "label_change_fraction": 1.0,
    "ordinal_change_fraction": 598.0 / 624.0,
    "kendall_tau_min": 0.286,
    "kendall_tau_mean": 0.390,
    "kendall_tau_max": 0.562,
    "label_register_recall": 0.0,
    "ordinal_register_recall": 26.0 / 624.0,
}

#: A retypeset that touched fewer than twenty documents is not the one-project, whole-fonds
#: event decision D6 describes.  Measured 24.
MIN_RETYPESET_DOCUMENTS: Final[int] = 20

#: Measured 624.  Below five hundred the scoreboard's denominators stop being interesting.
MIN_PAIRS: Final[int] = 500

#: A retypeset renumbers *everything* — that is what makes it a retypeset and not an amendment.
#: Measured 1.0, and this is the one threshold set **at** the measurement rather than beneath
#: it, because "some clauses kept their old label" would mean the two schemes overlap, which is
#: precisely the property :func:`mainline_corpus.reflow.measure.schemes_are_disjoint` denies.
MIN_LABEL_CHANGE_FRACTION: Final[float] = 1.0

#: Position may legitimately survive: a clause that was first under the old scheme can be first
#: under the new one by coincidence.  Measured 0.958.
MIN_ORDINAL_CHANGE_FRACTION: Final[float] = 0.90

#: Normalised Kendall tau *distance* — the fraction of clause pairs whose relative order the
#: reflow inverted.  0.0 is "same order, renumbered"; 0.5 is the expectation under a uniformly
#: random permutation.  A pure renumbering scores 0, so a floor here is what separates decision
#: D6's *scheme change* from a formatting tweak.  Measured min 0.286 across 24 documents.
MIN_DOCUMENT_KENDALL_TAU: Final[float] = 0.20

#: Measured 0.390 over the whole retypeset.
MIN_MEAN_KENDALL_TAU: Final[float] = 0.30

#: The four registers, in scoreboard order.  Each is "match a post-2016 clause to a pre-2016
#: clause when this field agrees", which is how a document register, a spreadsheet and a
#: document-management system in fact do it.  ``clause_uuid`` is the MAINLINE way and is
#: included as a **control**, not as evidence: see ``TAUTOLOGICAL_REGISTERS``.
REGISTER_KEYS: Final[tuple[tuple[str, str], ...]] = (
    (
        "printed_label",
        (
            "the clause number as printed — what a paper register, a spreadsheet column and "
            "every cross-reference in a neighbouring document actually key on"
        ),
    ),
    (
        "ordinal",
        (
            "position within the document — what an importer that walks paragraphs in order "
            "keys on when the label is unparseable"
        ),
    ),
    (
        "control_class",
        (
            "what the clause is *about* — the closest offline stand-in for a content or "
            "semantic match, and the only register here whose failures are ambiguity rather "
            "than blindness"
        ),
    ),
    (
        "clause_uuid",
        (
            "the identity the document carries through the reflow — MAINLINE's answer, present "
            "as a control"
        ),
    ),
)

#: Registers whose score is a property of the corpus's construction and not a measurement of
#: anything.  ``verify`` refuses to let the scoreboard omit this list, and ``build`` writes it
#: into ``reflow_scoreboard.json`` so a number lifted out of the file travels with its caveat.
TAUTOLOGICAL_REGISTERS: Final[tuple[str, ...]] = ("clause_uuid",)

MUST_NOT_CLAIM: Final[tuple[str, ...]] = (
    (
        "This stage does not measure MAINLINE's clause linker. It measures what a register keyed "
        "on a printed label, an ordinal or a control class loses when a document is retypeset."
    ),
    (
        "The clause_uuid register scores 1.000 by construction: the corpus carries that identity "
        "across the reflow, so a register keyed on it cannot miss. It is a control, not evidence."
    ),
    (
        "The corpus is synthetic. These numbers bound a label-keyed register from above on a "
        "world built to be legible; a real fonds is messier, and the losses would be larger."
    ),
    (
        "No clause text is compared anywhere in this stage. A real content-similarity register "
        "would score between control_class and clause_uuid, and is not measured here."
    ),
)
