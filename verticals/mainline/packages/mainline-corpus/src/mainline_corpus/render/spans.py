# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Canonical text assembly, and quote binding by exact-and-unique ``find()``.

ARCHITECTURE §18 **I2** states the ingestion contract in one line: *extraction is
quote-or-abstain; every field carries a quote we then bind ourselves with an exact, unique
``find()`` into ``canon_text``.  We compute offsets; we never trust a model-reported offset.*

This module is that sentence, on the producer side.  Whatever tier wrote the prose — a
hand-authored fixture, the deterministic composer, or Claude on Bedrock — the offsets are
computed **here**, from the assembled canonical text, by searching for the quote.  A tier that
returned an offset would not be believed, and none of them is asked to.

------------------------------------------------------------------------------------------
The span convention, stated once so nobody has to guess
------------------------------------------------------------------------------------------
``[start, end)`` — **0-based, half-open, in Unicode code points**, so ``end - start`` is
exactly ``len(quote)`` and that identity is checkable by anyone holding the two values.

CockroachDB's ``substring`` is **1-based and length-taking**, so the loader converts at the
boundary, once::

    substring(canon_text FROM span[1] + 1 FOR span[2] - span[1])

That snippet is written into the stage-2 ``index.json`` as ``span_sql`` so the loader does not
have to rediscover it.

------------------------------------------------------------------------------------------
Exact and unique, or refuse
------------------------------------------------------------------------------------------
``mainline.control_failure.evidence_span`` is ``INT8[2] NOT NULL`` and ``quote_sha256`` is
``BYTES NOT NULL``.  There is no abstention available at this table: a control failure without
evidence cannot be loaded at all.  So a quote that does not occur, or occurs twice, is a **build
failure** naming the node and the quote — not a dropped row, and certainly not a first-match
guess.  A first-match guess is how an incident gets attributed to the wrong clause, which is the
one outcome this entire product exists to refuse.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

__all__ = [
    "SPAN_CONVENTION",
    "SPAN_SQL",
    "BindingFailure",
    "bind",
    "canon_text",
    "quote_sha256",
]

SPAN_CONVENTION: Final[str] = "unicode_codepoint_offsets_0based_half_open"

SPAN_SQL: Final[str] = "substring(canon_text FROM span[1] + 1 FOR span[2] - span[1])"


class BindingFailure(RuntimeError):
    """A quote could not be bound into its canonical text exactly once."""


def quote_sha256(quote: str) -> str:
    """``sha256`` of the quote's UTF-8 bytes, hex.

    The digest is over the quote *as bound*, not as the renderer produced it — they are the
    same string by construction, and this function is called with the bound one so that the
    digest and the span can never describe different text.
    """
    return hashlib.sha256(quote.encode("utf-8")).hexdigest()


def bind(text: str, quote: str, *, origin: str) -> tuple[int, int]:
    """Return ``[start, end)`` for ``quote`` in ``text``, refusing anything but one match."""
    if not quote:
        raise BindingFailure(f"{origin}: empty quote; there is nothing to bind")
    occurrences = text.count(quote)
    if occurrences == 0:
        raise BindingFailure(
            f"{origin}: quote does not occur in the canonical text.\n"
            f"  quote: {quote!r}\n"
            "The renderer produced a sentence the assembly did not keep. Either the assembly "
            "dropped a section or the tier rewrote the sentence after emitting it; both are "
            "build errors, because an unbound control failure cannot be loaded at all "
            "(evidence_span is NOT NULL)."
        )
    if occurrences > 1:
        raise BindingFailure(
            f"{origin}: quote occurs {occurrences} times in the canonical text.\n"
            f"  quote: {quote!r}\n"
            "Exact-and-unique matching is the ingestion contract (ARCHITECTURE §18 I2). Taking "
            "the first match would silently attribute evidence to whichever occurrence came "
            "first, which is indistinguishable from attributing it to the wrong one."
        )
    start = text.index(quote)
    return start, start + len(quote)


# ── canonical text assembly ─────────────────────────────────────────────────────────────
#
# One function per node kind.  The assembly is what offsets are computed against and what
# `corpus-docx` typesets, so it is spelled out rather than left to whoever writes the .docx
# template: two different assemblies would mean the spans point into a document that was never
# printed.


def _join(sections: Sequence[str]) -> str:
    """Join non-empty sections with a blank line, LF, no trailing whitespace."""
    return "\n\n".join(section.strip() for section in sections if section and section.strip())


def _event_canon(response: Mapping[str, Any]) -> str:
    findings = "\n".join(str(item["finding"]).strip() for item in response["defences"])
    recommendations = "\n".join(str(item).strip() for item in response["recommendations"])
    return _join(
        [
            str(response["summary"]),
            str(response["sequence"]),
            str(response["consequence"]),
            findings,
            recommendations,
        ]
    )


def _clause_canon(response: Mapping[str, Any]) -> str:
    # The printed label is a column of its own and changes at every retypeset; putting it in
    # `canon_text` would make the clause's text differ across a reflow that changed nothing.
    return str(response["body"]).strip()


def _moc_canon(response: Mapping[str, Any]) -> str:
    return _join(
        [str(response["justification"]), str(response["scope_note"]), str(response["risk_note"])]
    )


def _revision_canon(response: Mapping[str, Any]) -> str:
    lines = "\n".join(str(item["line"]).strip() for item in response["citations"])
    return _join([str(response["reason"]), lines])


_ASSEMBLERS: Final[dict[str, Callable[[Mapping[str, Any]], str]]] = {
    "clause_text": _clause_canon,
    "event_narrative": _event_canon,
    "moc_justification": _moc_canon,
    "revision_reason": _revision_canon,
}


def canon_text(node_kind: str, response: Mapping[str, Any]) -> str:
    """Assemble the canonical text for a rendered node."""
    try:
        assembler = _ASSEMBLERS[node_kind]
    except KeyError:
        raise BindingFailure(f"no canonical assembly for node kind {node_kind!r}") from None
    text: str = assembler(response)
    if not text:
        raise BindingFailure(f"{node_kind}: canonical assembly produced empty text")
    return text
