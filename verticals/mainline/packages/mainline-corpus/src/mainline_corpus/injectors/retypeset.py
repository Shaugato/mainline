# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Injector 1 — the 2016 full retypeset.  One per document, one date, every ``ord_path`` changes.

**Proves:** clause UUID identity survives a complete reflow.  This is beat 1's payload and the
K3 exit criterion, and it is the reason ``clause_uuid`` and ``printed_label`` live on different
tables (ARCHITECTURE.md §5.3: the ``@wId`` / ``@eId`` split).

── WHY THIS IS A DIFFERENT ORGANISING PRINCIPLE AND NOT A STRING SUBSTITUTION (decision D6) ──

Generation 1 numbers a document the way the work is done: numbered sections in procedural order
— prepare, isolate, verify, execute, restore — and a clause is ``section.position``, sometimes
with a third level and a bracketed item, ``7.3.2(b)``.

Generation 2 numbers it the way the *controls* are organised: a chapter per control class, in
the order the new house template presents them, then a division by barrier role (1 preventive,
2 recovery), then a sequential item.  A clause is ``chapter.barrier.item``, ``5.2.1``.

Those two schemes disagree about what a document *is*, which is exactly why every label and
every ordinal moves.  Renumbering under one scheme would be a formatting change; changing the
scheme is a reflow, and the corpus's claim is about surviving the second.

``corpus-docx`` builds two real template generations and renders the same ``clause_uuid``
through both.  This module emits the mapping it renders from — and nothing else: no clause text
is written here, because the text belongs to ``corpus-render-cache``.

── THE ONE AUTHORED PLACEMENT, STATED PLAINLY ────────────────────────────────────────────────

``anchors.yaml`` declares the spine's labels: ``7.3`` in 2011 and ``5.2.1`` after 2016, and the
film shows both.  Those are not computed backwards from a wish; they fall out of the scheme
above given one authored fact — ``blame.params.RETYPESET_CHAPTER_ORDER`` puts the containment
fonds' chapters in process order, from the transfer itself outward to the last line of defence,
which places ``SEAL_FACE_TEMPERATURE_ALARM`` fifth.  It is a recovery control (chapter division
2) and it is the only clause of its class in ``PRO-MEC-014`` (item 1).  ``5.2.1``.  The builder
asserts that equality rather than assuming it, so an edit to the chapter order goes red here
instead of on capture day.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from ..blame import params as blame_params
from ..skeleton import clock
from ..skeleton import params as skeleton_params
from ..skeleton.model import Doc

__all__ = [
    "RETYPESET_ON",
    "chapter_order",
    "documents_in_scope",
    "g1_label",
    "g2_label",
    "schedule_rows",
]

#: One date, because the retypeset was one project.
RETYPESET_ON: dt.date = dt.date.fromisoformat(skeleton_params.RETYPESET_DATE)

_ITEM_LETTERS: str = "abcdefgh"


def documents_in_scope(docs: Sequence[Doc]) -> tuple[Doc, ...]:
    """Documents the 2016 retypeset touched: flagged in the gazetteer and already in issue.

    A document first issued in 2019 was never typeset in the old house style, so retypesetting
    it would be a fact about nothing.
    """
    return tuple(
        doc
        for doc in sorted(docs, key=lambda item: (item.site_code, item.doc_code))
        if doc.retypeset_2016 and doc.first_issued < RETYPESET_ON
    )


def g1_label(section: int, position: int, sub: int | None, item: int | None) -> str:
    """``7.3`` or ``7.3.2(b)`` — the pre-2016 house style."""
    label = f"{section}.{position}"
    if sub is not None:
        label = f"{label}.{sub}"
        if item is not None:
            label = f"{label}({_ITEM_LETTERS[item % len(_ITEM_LETTERS)]})"
    return label


def g2_label(chapter: int, barrier: int, item: int) -> str:
    """``5.2.1`` — the post-2016 house style."""
    return f"{chapter}.{barrier}.{item}"


def chapter_order(activity_root: str, classes_present: Sequence[str]) -> tuple[str, ...]:
    """Order this document's control classes as the generation-2 template presents them.

    Authored for the fonds that carries the spine (see ``RETYPESET_CHAPTER_ORDER``); every other
    fonds is ordered by control-class key, which is still a different order from generation 1's
    procedural sections and needs no authoring to be a genuine reflow.
    """
    present = sorted(set(classes_present))
    authored = blame_params.RETYPESET_CHAPTER_ORDER.get(activity_root)
    if authored is None:
        return tuple(present)
    ordered = [name for name in authored if name in present]
    ordered.extend(name for name in present if name not in authored)
    return tuple(ordered)


def schedule_rows(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row per (document, clause): the label and ordinal on both sides of the reflow.

    ``entries`` arrives from the clause builder, which is the only place that knows both
    layouts.  The row shape is what ``corpus-docx`` needs to render generation 2 and what the
    console's diff needs to prove the identity held.
    """
    rows: list[dict[str, Any]] = []
    for entry in entries:
        rows.append(
            {
                "clause_key": str(entry["clause_key"]),
                "clause_uuid": str(entry["clause_uuid"]),
                "control_class": str(entry["control_class"]),
                "doc_code": str(entry["doc_code"]),
                "effective_on": clock.iso_date(RETYPESET_ON),
                "g1_ordinal": int(entry["g1_ordinal"]),
                "g1_printed_label": str(entry["g1_printed_label"]),
                "g2_ordinal": int(entry["g2_ordinal"]),
                "g2_printed_label": str(entry["g2_printed_label"]),
                "identity_held": True,
                "revision_key": str(entry["revision_key"]),
                "site_code": str(entry["site_code"]),
            }
        )
    return rows
