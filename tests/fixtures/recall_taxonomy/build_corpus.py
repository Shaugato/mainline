# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Generate the synthetic taxonomy fixture corpus and the offline judge's rule table.

Run: ``python tests/fixtures/recall_taxonomy/build_corpus.py``.  It writes
``narratives.jsonl`` and ``offline_induction_rules.json`` beside itself, deterministically —
no RNG anywhere, every choice is a function of the leaf index and the document index — so
re-running it on any machine reproduces the committed files byte for byte.

READ THIS BEFORE QUOTING ANY NUMBER PRODUCED ON THIS CORPUS
-----------------------------------------------------------
The offline judge's rule table and the corpus's human-confirmation labels are emitted from
**one** table, :data:`LEAVES`, below.  They are not independent.  A holdout accuracy measured
on this corpus therefore measures the *pipeline* — that the split happens before induction,
that variants merge, that the classifier fits on merged labels, that scoring walks the tree
to each level and that the interval is computed — and it measures **nothing at all** about a
model's ability to label mining narratives.  The corpus stamps itself ``SYNTHETIC`` and every
report built from it carries that string in ``corpus_provenance``.

The real measurement is G1/G3/G4 on the MSHA and CSB corpora (worker
``recall-corpora-goldsets``) with a live judge, and it is not this worker's to make.

What the corpus does contain on purpose
---------------------------------------
* **Label variants.**  One document in five gets a re-worded file label from the judge, so
  the merge phase has genuine near-duplicates to fold and the version diff has something to
  report.  Variants are chosen to share enough content tokens to clear the merge threshold —
  which is a property of the fixture, and the test that asserts merging works asserts it
  against this fixture, not against the world.
* **Unclassifiable documents.**  16 narratives carry no trigger term at all, so the judge
  abstains on them exactly as it is instructed to when a narrative does not say what work
  was being performed.  They have no truth label, and the holdout scorer counts them as
  misses rather than excluding them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

HERE: Final[Path] = Path(__file__).resolve().parent

DOCS_PER_LEAF: Final[int] = 41
UNCLASSIFIABLE_DOCS: Final[int] = 16
VARIANT_MODULUS: Final[int] = 5

#: (activity_root, series_label, file_label, triggers, variants)
LEAVES: Final[tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...]] = (
    (
        "MUE-05",
        "locking out and proving zero energy state",
        "applying personal locks to isolation points",
        (
            "personal danger lock",
            "lock box",
            "isolation point register",
            "group lockout board",
        ),
        (
            "applying personal locks at isolation points",
            "applying personal locks to isolation points before work",
        ),
    ),
    (
        "MUE-05",
        "locking out and proving zero energy state",
        "proving zero energy before opening a system",
        (
            "zero energy check",
            "try test try",
            "proving dead",
            "stored charge was not proved",
        ),
        ("proving zero energy before opening a circuit",),
    ),
    (
        "MUE-05",
        "releasing residual pressure from closed systems",
        "bleeding down hydraulic accumulators",
        (
            "hydraulic accumulator",
            "bleed down valve",
            "residual hydraulic pressure",
            "accumulator discharge",
        ),
        ("bleeding down the hydraulic accumulators",),
    ),
    (
        "MUE-05",
        "releasing residual pressure from closed systems",
        "venting trapped compressed air",
        (
            "trapped compressed air",
            "air receiver",
            "vent to atmosphere",
            "pneumatic line under pressure",
        ),
        ("venting trapped compressed air lines",),
    ),
    (
        "MUE-03",
        "controlling interaction between people and moving machines",
        "positioning people clear of reversing machines",
        (
            "reversing alarm",
            "blind spot behind the machine",
            "reverse manoeuvre",
            "spotter was not used",
        ),
        ("positioning people clear of a reversing machine",),
    ),
    (
        "MUE-03",
        "controlling interaction between people and moving machines",
        "authorising entry to an operating work area",
        (
            "operating area authorisation",
            "entry authority was not obtained",
            "work area was still live",
            "area access permit",
        ),
        ("authorising entry to an operating area",),
    ),
    (
        "MUE-03",
        "communicating intent before approaching a moving machine",
        "establishing positive communication with an operator",
        (
            "positive communication",
            "eye contact with the operator",
            "radio call was not acknowledged",
            "hand signal",
        ),
        ("establishing positive communication with the operator",),
    ),
    (
        "MUE-03",
        "communicating intent before approaching a moving machine",
        "parking and immobilising before dismounting",
        (
            "park brake was not applied",
            "immobilise before dismounting",
            "chocks were not placed",
            "left in gear",
        ),
        ("parking and immobilising before dismounting the machine",),
    ),
    (
        "MUE-04",
        "securing people against falls from elevated work",
        "anchoring fall-arrest to a rated point",
        (
            "fall arrest lanyard",
            "rated anchor point",
            "harness was clipped to",
            "anchorage rating",
        ),
        ("anchoring fall-arrest to a rated anchor point",),
    ),
    (
        "MUE-04",
        "securing people against falls from elevated work",
        "covering and barricading floor penetrations",
        (
            "floor penetration",
            "open penetration cover",
            "hole in the walkway",
            "barricade was removed",
        ),
        ("covering and barricading open floor penetrations",),
    ),
    (
        "MUE-04",
        "accessing elevated work positions",
        "erecting and handing over temporary access structures",
        (
            "scaffold handover tag",
            "incomplete scaffold",
            "temporary platform was not tagged",
            "scafftag",
        ),
        ("erecting and handing over temporary access platforms",),
    ),
    (
        "MUE-04",
        "accessing elevated work positions",
        "climbing fixed access with three points of contact",
        (
            "three points of contact",
            "fixed ladder",
            "stepped backwards off the landing",
            "descending the access way",
        ),
        ("climbing fixed access using three points of contact",),
    ),
    (
        "MUE-12",
        "verifying atmosphere before and during entry",
        "testing for oxygen deficiency and h2s",
        (
            "oxygen deficient atmosphere",
            "gas test was not repeated",
            "h2s reading",
            "atmospheric monitor alarm",
        ),
        ("testing for oxygen deficiency and h2s levels",),
    ),
    (
        "MUE-12",
        "verifying atmosphere before and during entry",
        "ventilating a space before occupancy",
        (
            "forced ventilation was not running",
            "purge the vessel",
            "ventilation duct was removed",
            "air mover",
        ),
        ("ventilating a confined space before occupancy",),
    ),
    (
        "MUE-12",
        "controlling entry and standby arrangements",
        "maintaining a standby attendant and entry log",
        (
            "standby person left the entry",
            "entry log was not signed",
            "attendant post was unmanned",
            "entry permit board",
        ),
        ("maintaining a standby attendant and an entry log",),
    ),
    (
        "MUE-12",
        "controlling entry and standby arrangements",
        "planning rescue before entering",
        (
            "rescue plan was not in place",
            "retrieval line",
            "tripod and winch were not rigged",
            "no rescue drill",
        ),
        ("planning rescue arrangements before entering",),
    ),
    (
        "MUE-09",
        "charging blast holes",
        "securing and guarding charged ground",
        (
            "charged ground was not guarded",
            "sleeping shot",
            "explosives left in the hole overnight",
            "blast guard",
        ),
        ("securing and guarding charged blast ground",),
    ),
    (
        "MUE-09",
        "charging blast holes",
        "handling detonators separately from bulk product",
        (
            "detonators were carried with",
            "bulk emulsion",
            "initiating system",
            "magazine issue record",
        ),
        ("handling detonators separately from bulk explosive product",),
    ),
    (
        "MUE-09",
        "clearing and re-entering after firing",
        "evacuating and sentrying the exclusion zone",
        (
            "sentry post was not placed",
            "blast exclusion zone",
            "clearance sweep",
            "all clear was given early",
        ),
        ("evacuating and sentrying the blast exclusion zone",),
    ),
    (
        "MUE-09",
        "clearing and re-entering after firing",
        "inspecting for misfires before re-entry",
        (
            "misfire",
            "unfired charge",
            "re-entry after the blast",
            "post blast inspection",
        ),
        ("inspecting for misfires before re-entry to the face",),
    ),
    (
        "MUE-15",
        "transferring bulk chemicals between containments",
        "connecting and disconnecting transfer lines",
        (
            "transfer hose coupling",
            "decant line was not drained",
            "camlock fitting",
            "wrong connection was made",
        ),
        ("connecting and disconnecting chemical transfer lines",),
    ),
    (
        "MUE-15",
        "transferring bulk chemicals between containments",
        "containing and recovering a spill",
        (
            "spill kit",
            "bund was not intact",
            "product reached the drain",
            "containment berm",
        ),
        ("containing and recovering a chemical spill",),
    ),
    (
        "MUE-15",
        "protecting people from chemical exposure",
        "selecting and fitting respiratory protection",
        (
            "respirator fit test",
            "wrong cartridge",
            "air purifying respirator",
            "face seal",
        ),
        ("selecting and fitting correct respiratory protection",),
    ),
    (
        "MUE-15",
        "protecting people from chemical exposure",
        "decontaminating people after exposure",
        (
            "emergency shower",
            "decontamination area",
            "skin contact with the reagent",
            "eyewash station",
        ),
        ("decontaminating people after chemical exposure",),
    ),
)

#: Sentence frames for the discriminative content.  Deliberately neutral: the trigger is the
#: signal, and a frame that carried its own vocabulary would leak class information into
#: every document that used it.
_FRAMES: Final[tuple[str, ...]] = (
    "the review noted: {trigger}.",
    "witness statements refer to {trigger}.",
    "the icam team recorded {trigger} as an absent or failed control.",
    "the record shows {trigger} at the time of the event.",
    "a prior audit had raised {trigger}.",
)

#: Shared filler.  Contains no trigger term of any leaf, checked by :func:`_self_check`.
_FILLER: Final[tuple[str, ...]] = (
    "the task had been briefed at the start of shift and the crew were experienced.",
    "conditions were fine and visibility was good.",
    "the supervisor was attending another job at the time.",
    "the work order had been raised the previous day.",
    "two contractors and one employee were present.",
    "the area had been inspected earlier in the week.",
    "the crew were on the second half of a twelve hour shift.",
    "no injuries were sustained and the job was stopped.",
    "the event was reported the same day.",
    "the crew stood the job down and notified the shift controller.",
)

_KINDS: Final[tuple[str, ...]] = ("incident", "near miss", "audit finding")
_SEVERITIES: Final[tuple[int, ...]] = (1, 2, 3, 4, 5, 2, 3, 1, 4, 2)


def _document(leaf_index: int, doc_index: int, serial: int) -> dict[str, Any]:
    root, series, leaf, triggers, variants = LEAVES[leaf_index]
    chosen = [
        triggers[(doc_index + offset) % len(triggers)]
        for offset in range(3 if doc_index % 2 else 2)
    ]
    sentences = [
        _FRAMES[(doc_index + position) % len(_FRAMES)].format(trigger=trigger)
        for position, trigger in enumerate(chosen)
    ]
    sentences.insert(0, _FILLER[doc_index % len(_FILLER)])
    sentences.append(_FILLER[(doc_index * 3 + 4) % len(_FILLER)])
    kind = _KINDS[(leaf_index + doc_index) % len(_KINDS)]
    return {
        "doc_id": f"FX-{serial:04d}",
        "kind": kind,
        "title": f"{kind}: {chosen[0]}",
        "narrative": " ".join(sentences),
        "severity_gate": _SEVERITIES[(leaf_index * 7 + doc_index) % len(_SEVERITIES)],
        "severity_basis": "coded_field",
        "truth_activity_root": root,
        "truth_series": series,
        "truth_file": leaf,
        "has_variant_label": doc_index % VARIANT_MODULUS == 0 and bool(variants),
    }


def _unclassifiable(index: int, serial: int) -> dict[str, Any]:
    sentences = [
        _FILLER[(index + offset) % len(_FILLER)] for offset in range(4)
    ]
    return {
        "doc_id": f"FX-{serial:04d}",
        "kind": "audit finding",
        "title": "audit finding: administrative record only",
        "narrative": " ".join(sentences),
        "severity_gate": 0,
        "severity_basis": "coded_field",
        "truth_activity_root": "",
        "truth_series": "",
        "truth_file": "",
        "has_variant_label": False,
    }


def build_documents() -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    serial = 1
    for leaf_index in range(len(LEAVES)):
        for doc_index in range(DOCS_PER_LEAF):
            documents.append(_document(leaf_index, doc_index, serial))
            serial += 1
    for index in range(UNCLASSIFIABLE_DOCS):
        documents.append(_unclassifiable(index, serial))
        serial += 1
    return documents


def build_rules() -> dict[str, Any]:
    return {
        "_license": (
            "SPDX-FileCopyrightText: 2026 MAINLINE contributors / "
            "SPDX-License-Identifier: CC-BY-4.0"
        ),
        "rules_id": "offline-taxonomy-rules-fixture-1",
        "provenance": (
            "SYNTHETIC. Generated by tests/fixtures/recall_taxonomy/build_corpus.py from the "
            "same LEAVES table that produced the corpus truth labels. The offline judge that "
            "reads this file is a committed stand-in for a language model, declared "
            "non-semantic; a taxonomy induced with it is a function of this table and the "
            "corpus, and of nothing else."
        ),
        "rules": [
            {
                "activity_root": root,
                "series_label": series,
                "file_label": leaf,
                "triggers": list(triggers),
                "variants": list(variants),
            }
            for root, series, leaf, triggers, variants in LEAVES
        ],
    }


def _self_check(documents: list[dict[str, Any]]) -> None:
    """Refuse to write a corpus whose documents do not resolve to their own leaf.

    Two properties, both of which quietly break the fixture if they stop holding: no filler
    sentence may contain a trigger term, and the highest-scoring rule for each document must
    be the rule that generated it.  A fixture that silently mislabels itself would produce a
    holdout score that looks like a classifier problem.
    """
    all_triggers = [
        (index, trigger) for index, leaf in enumerate(LEAVES) for trigger in leaf[3]
    ]
    for sentence in _FILLER:
        for index, trigger in all_triggers:
            if trigger in sentence:
                raise SystemExit(
                    f"filler sentence contains trigger {trigger!r} of leaf {index}: "
                    "shared filler must carry no class signal"
                )
    for document in documents:
        text = f"{document['title']} {document['narrative']}".lower()
        scores = [
            (sum(1 for trigger in leaf[3] if trigger in text), index)
            for index, leaf in enumerate(LEAVES)
        ]
        best_score, best_index = max(scores, key=lambda pair: (pair[0], -pair[1]))
        if not document["truth_file"]:
            if best_score:
                raise SystemExit(
                    f"{document['doc_id']} is meant to be unclassifiable but matched "
                    f"leaf {best_index}"
                )
            continue
        if LEAVES[best_index][2] != document["truth_file"]:
            raise SystemExit(
                f"{document['doc_id']} resolves to {LEAVES[best_index][2]!r} but was "
                f"generated as {document['truth_file']!r}"
            )


def main() -> None:
    documents = build_documents()
    _self_check(documents)
    corpus_path = HERE / "narratives.jsonl"
    meta = {
        "kind": "meta",
        "_license": (
            "SPDX-FileCopyrightText: 2026 MAINLINE contributors / "
            "SPDX-License-Identifier: CC-BY-4.0"
        ),
        "corpus_id": "recall-taxonomy-fixture-1",
        "provenance": (
            "SYNTHETIC — template-generated by build_corpus.py. Scores measured on this "
            "corpus are PRELIMINARY and measure the induction PIPELINE, not a model's "
            "labelling ability: the offline judge's rule table and these truth labels come "
            "from one table. Never quote a number from this corpus as a G4 measurement."
        ),
        "n_documents": len(documents),
        "n_leaves": len(LEAVES),
        "n_unclassifiable": UNCLASSIFIABLE_DOCS,
        "generator": "tests/fixtures/recall_taxonomy/build_corpus.py",
    }
    with corpus_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(meta, sort_keys=True) + "\n")
        for document in documents:
            handle.write(json.dumps(document, sort_keys=True) + "\n")
    rules_path = HERE / "offline_induction_rules.json"
    rules_path.write_text(
        json.dumps(build_rules(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {corpus_path} ({len(documents)} documents)")
    print(f"wrote {rules_path} ({len(LEAVES)} rules)")


if __name__ == "__main__":
    main()
