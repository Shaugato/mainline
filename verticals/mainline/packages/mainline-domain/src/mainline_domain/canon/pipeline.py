# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``canon(v)`` — the whole pipeline, in one fixed order.

The order is not a preference; each step exists at its position for a reason
that the step after it depends on:

===  ==============================  ==================================================
 1   strip page furniture            line-based, so it must run while lines still exist,
                                     and on the raw text so its spans are real offsets
 2   fold                            NFKC + confusables + discretionary breaks
 3   de-hyphenate                    needs the line breaks folding left intact
 4   collapse whitespace             after de-hyphenation; this is where reflow dies
 5   repair OCR confusables          before numbering, so ``1O.`` becomes ``10.`` and is
                                     then recognised as a label rather than surviving
                                     into the body as text
 6   excise the numbering prefix     to a fixpoint, so renumbering moves no identity byte
 7   digest                          domain-separated, version-bound
 8   segment                         content-defined, only when layout gave no boundary
===  ==============================  ==================================================

Step 5 before step 6 is the subtle one, and it is what makes the canonicaliser
idempotent.  In the other order, ``1O. Before ...`` canonicalises to
``10. Before ...`` — text that a *second* pass would strip a label from.  A
canonicaliser whose second application disagrees with its first is a
canonicaliser whose digests cannot be reproduced by an opposing expert.

``canonicalise`` takes no ``canon_version`` argument.  See
:mod:`mainline_domain.canon.version`.
"""

from __future__ import annotations

import re
from typing import Final

from ..contracts import CanonResult, OcrRepair, Segment
from .dehyphen import dehyphenate
from .digest import canon_digest, segment_digest
from .fold import fold_text
from .furniture import FurnitureModel, strip_furniture
from .numbering import excise_numbering
from .ocr import repair_numeric_confusables
from .segment import segment_tokens
from .tokens import iter_tokens, token_texts
from .version import CANON_VERSION

__all__ = ["canonicalise"]

_WHITESPACE: Final[re.Pattern[str]] = re.compile(r"\s+")


def _collapse(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def _shift_repairs(repairs: tuple[OcrRepair, ...], offset: int) -> tuple[OcrRepair, ...]:
    """Re-base repair spans past an excised numbering prefix.

    Repairs that landed *inside* the prefix are dropped: the prefix is not part
    of ``canon_text``, so a span into it would be a span into nothing.  Repair is
    a 1:1 substitution, so no span ever straddles the boundary.
    """
    if offset == 0:
        return repairs
    return tuple(
        OcrRepair(
            start=repair.start - offset,
            end=repair.end - offset,
            before=repair.before,
            after=repair.after,
        )
        for repair in repairs
        if repair.start >= offset
    )


def _segments(canon_text: str, *, layout_segmented: bool) -> tuple[Segment, ...]:
    if not canon_text:
        return ()
    if layout_segmented:
        return (Segment(start=0, end=len(canon_text), sha256=segment_digest(canon_text)),)

    tokens = tuple(iter_tokens(canon_text))
    ranges = segment_tokens(token_texts(canon_text))
    out: list[Segment] = []
    for first, last in ranges:
        start = tokens[first].start
        end = tokens[last - 1].end
        out.append(Segment(start=start, end=end, sha256=segment_digest(canon_text[start:end])))
    return tuple(out)


def canonicalise(
    raw_text: str,
    *,
    furniture: FurnitureModel | None = None,
    layout_segmented: bool = False,
) -> CanonResult:
    """Canonicalise one clause.

    :param raw_text: the clause as extracted, including any page furniture that
        came with it and any line wrapping the source imposed.
    :param furniture: a model learned from the pages of the containing document
        (:meth:`FurnitureModel.from_pages`).  Without it only the unconditional
        furniture patterns fire, which is the correct behaviour for a clause
        handed over without document context.
    :param layout_segmented: ``True`` when the caller already has a layout-model
        boundary for this text (Textract ``LAYOUT_*`` blocks), in which case the
        content-defined fallback is not run and the result carries one segment.

    Idempotent: ``canonicalise(canonicalise(x).canon_text).canon_text ==
    canonicalise(x).canon_text`` for every input.
    """
    kept, furniture_spans = strip_furniture(raw_text, furniture)
    folded = fold_text(kept)
    joined = dehyphenate(folded)
    collapsed = _collapse(joined)
    repaired, repairs = repair_numeric_confusables(collapsed)
    body, prefix, label = excise_numbering(repaired)

    return CanonResult(
        canon_text=body,
        canon_sha256=canon_digest(body),
        canon_version=CANON_VERSION,
        numbering_prefix=prefix,
        printed_label=label,
        furniture_spans=furniture_spans,
        ocr_repairs=_shift_repairs(repairs, len(prefix) if prefix else 0),
        segments=_segments(body, layout_segmented=layout_segmented),
    )
