# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Canonical form of a CAT — everything judgemental, done before the encoder.

:mod:`mainline_domain.cat.preimage` is deliberately dumb: it hashes whatever
tuple it is handed.  That is only safe if the tuple was put into one canonical
form first, and this module is that form.  It implements §7 of
``verticals/mainline/spec/cat-key-v1.md`` and nothing beyond it, so a
re-implementer reading the spec arrives here.

Four rules, in the order they apply:

1. **Closed slots** are NFKC-normalised, case-folded, whitespace-collapsed and
   stripped.  ``deontic`` is the one exception: upper-cased instead of folded,
   because the taxonomy labels are upper-case by convention and rule R1's order
   is written in them.
2. **Free-text lists** get the same treatment per element, plus removal of
   trailing ``.``/``;``/``,`` (unless that would empty the element), plus
   dropping of empties and duplicates.
3. **List order** is by the UTF-8 **bytes** of the normalised element.  Not
   locale order — a locale collation would make ``cat_key`` depend on the
   machine's environment, and identity may not depend on a machine.
4. **Quantities** are SI-normalised with the reference class preserved, by
   worker W2's converter.  A gauge↔absolute crossing raises and the error
   propagates.

Why case-folding a list element is safe and case-folding an anchor would not be:
these are free-text conditions and exceptions, whose identity is their meaning;
``P-101A`` never reaches this module, because equipment tags are ANCHORLOCK's
job and anchors keep their case.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from typing import Final

from ..contracts import CAT, Quantity
from .quantity_bridge import ConverterSpec, resolve_converter, si_normalise

__all__ = [
    "normalise_cat",
    "normalise_deontic",
    "normalise_list",
    "normalise_phrase",
    "normalise_slot",
    "sort_key",
]

_WHITESPACE: Final[re.Pattern[str]] = re.compile(r"\s+")
_TRAILING_PUNCTUATION: Final[str] = ".;,"

# Closed slots, in the order they appear in the tuple.  `deontic` is handled
# separately and is not in this set.
_CLOSED_SLOTS: Final[tuple[str, ...]] = (
    "actor",
    "action",
    "object_class",
    "hazard_energy",
    "parameter",
    "comparator",
    "coverage_quantifier",
)
_LIST_SLOTS: Final[tuple[str, ...]] = ("conditions", "exceptions", "verification")


def _collapse(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def normalise_slot(text: str) -> str:
    """Closed-vocabulary slot: NFKC, case-fold, collapse whitespace, strip (§7.1)."""
    return _collapse(unicodedata.normalize("NFKC", text)).casefold()


def normalise_deontic(text: str) -> str:
    """Upper-case the deontic: the one closed slot that is not folded (§7.1).

    ``casefold()`` on ``'MUST_NOT'`` gives ``'must_not'``, which is a different
    string from every label in :data:`~mainline_domain.cat.schema.DEONTIC_LABELS`
    and would fail validation — the upper-casing here is what keeps the tuple's
    deontic and rule R1's ladder written in the same alphabet.
    """
    return _collapse(unicodedata.normalize("NFKC", text)).upper()


def normalise_phrase(text: str) -> str:
    """One free-text list element: §7.1 plus trailing sentence marks (§7.2).

    Trailing ``.``, ``;``, ``,`` and whitespace are stripped **unless stripping
    would empty the element**, in which case the element is left alone.

    Both halves of that rule are load-bearing and both were found by a property
    test rather than by reasoning.

    * *Greedy* rather than one-at-a-time: removing exactly one mark makes
      ``'a..'`` normalise to ``'a.'`` and then to ``'a'``, so the function is
      not idempotent — and a non-idempotent normaliser means a CAT can have two
      canonical forms and therefore two ``cat_key``s, which is an identity split.
    * *Unless it would empty*: an element that normalises to nothing is dropped
      by :func:`normalise_list`, so an unconditional strip would delete an
      exception consisting only of punctuation.  Deleting an exception is the
      one direction rule R4 must never be wrong in.  Keeping it verbatim is also
      idempotent, because a value that strips to empty strips to empty again.
    """
    collapsed = _collapse(unicodedata.normalize("NFKC", text)).casefold()
    stripped = collapsed.rstrip(_TRAILING_PUNCTUATION + " ")
    return stripped if stripped else collapsed


def sort_key(element: str) -> bytes:
    """§7.3: order by the UTF-8 bytes of the normalised element."""
    return element.encode("utf-8")


def normalise_list(elements: Iterable[str]) -> tuple[str, ...]:
    """Normalise, drop empties, de-duplicate, then order by UTF-8 bytes (§7.2, §7.3).

    De-duplication keeps the first occurrence, which is irrelevant to the result
    (the survivors are identical strings) and relevant to reading the code: it
    says the operation is *set-like*, so a clause that says "unless impracticable"
    twice does not encode two exceptions and does not look, to rule R4, like an
    exception was added.
    """
    seen: set[str] = set()
    kept: list[str] = []
    for element in elements:
        normalised = normalise_phrase(element)
        if not normalised or normalised in seen:
            continue
        seen.add(normalised)
        kept.append(normalised)
    return tuple(sorted(kept, key=sort_key))


def _normalise_quantity(
    quantity: Quantity | None,
    converter_spec: ConverterSpec,
    *,
    keep_unconvertible: bool,
) -> Quantity | None:
    converter = resolve_converter(converter_spec)
    return si_normalise(quantity, converter, keep_unconvertible=keep_unconvertible)


def normalise_cat(
    cat: CAT,
    converter: ConverterSpec = None,
    *,
    keep_unconvertible: bool = True,
) -> CAT:
    """Return the canonical form of ``cat``.  Idempotent.

    :param converter: ``None`` (default) leaves units exactly as written;
        ``'auto'`` uses W2's converter if its package is importable; a converter
        object uses it.  **A stored ``cat_key`` must never be produced with
        ``'auto'``**: whether the conversion ran would then depend on which
        distributions happened to be installed, and identity may not depend on
        that.  Pass ``None`` or an explicit converter, always.
    :param keep_unconvertible: a unit the converter does not know is kept
        verbatim (spec §10).  A gauge↔absolute crossing is never "unconvertible"
        and always raises.

    Idempotence is a property test, not a claim: NFKC is idempotent, ``casefold``
    is idempotent on NFKC-normalised text for the scripts this corpus uses,
    whitespace collapse is idempotent, and sorting a sorted list is a no-op —
    but the composition is what matters and the composition is what is tested.
    """
    normalised_lists = {slot: normalise_list(getattr(cat, slot)) for slot in _LIST_SLOTS}
    normalised_slots = {slot: normalise_slot(getattr(cat, slot)) for slot in _CLOSED_SLOTS}
    return CAT(
        actor=normalised_slots["actor"],
        deontic=normalise_deontic(cat.deontic),
        action=normalised_slots["action"],
        object_class=normalised_slots["object_class"],
        hazard_energy=normalised_slots["hazard_energy"],
        parameter=normalised_slots["parameter"],
        comparator=normalised_slots["comparator"],
        value=_normalise_quantity(cat.value, converter, keep_unconvertible=keep_unconvertible),
        conditions=normalised_lists["conditions"],
        exceptions=normalised_lists["exceptions"],
        verification=normalised_lists["verification"],
        frequency=_normalise_quantity(
            cat.frequency, converter, keep_unconvertible=keep_unconvertible
        ),
        coverage_quantifier=normalised_slots["coverage_quantifier"],
    )


def normalise_all(cats: Sequence[CAT], converter: ConverterSpec = None) -> tuple[CAT, ...]:
    """:func:`normalise_cat` over a sequence, in order."""
    return tuple(normalise_cat(cat, converter) for cat in cats)
