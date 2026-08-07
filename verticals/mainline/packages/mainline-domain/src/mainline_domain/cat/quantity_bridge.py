# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Reading quantities out of prose, and the seam to W2's quantity algebra.

This module does exactly two things, and the boundary between them is the whole
design:

**1. It finds quantities in text and classifies them.**  A number plus a unit
token, plus whatever pressure/temperature reference the prose declares.  It
never converts anything.  Its output is a :class:`~mainline_domain.contracts.Quantity`
whose ``unit`` is the unit *as written* and whose ``reference`` is what the text
*said*, which for a bare ``kPa`` is ``'none'`` — meaning **unstated**, not
``absolute``.  Guessing absolute is precisely the mistake decision D5 exists to
make unrepresentable: ``50 psig`` is ``344.7 kPa`` gauge and is not ``446 kPa``
absolute, and a system that assumes wrongly turns a weakening into a
strengthening on the way past the gate.

**2. It adapts W2's SI converter, and refuses to become one.**  Conversion,
comparison and SI normalisation belong to ``mainline_domain.quantity`` (worker
W2), which owns the vendored Pint definition file where gauge units carry their
offsets.  Nothing here contains a conversion factor and nothing here may ever
contain one: two sources of truth for what a kilopascal is will disagree, and
the disagreement surfaces as a ``safe_direction`` comparison that silently
flips.

The seam is a ``Protocol``, not an import, so this package builds and its tests
run whether or not W2 has landed — and, more importantly, so that CATSEAL's
behaviour without a converter is a *stated* behaviour (units stay as written)
rather than an accident of import order.

Error contract, which W2 must honour and which a test in
``tests/unit/domain/cat/`` pins:

* A unit the converter does not know raises :class:`UnconvertibleUnitError` (a
  ``LookupError``).  Callers may choose to keep the unit verbatim.
* **A gauge↔absolute crossing must NOT be a** ``LookupError``.  It is a
  different kind of failure — the caller asked for something unsafe rather than
  something unknown — and it must propagate out of every function here
  uncaught.  :func:`si_normalise` deliberately catches only ``LookupError`` so
  that a converter which raised the wrong class would surface as an unhandled
  error rather than as a silently kept unit.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Final, Literal, Protocol, runtime_checkable

from ..contracts import Quantity, Reference
from .lexicon import Grammar, UnitClasses, load_lexicons

__all__ = [
    "ConverterSpec",
    "QuantityMatch",
    "SiConverter",
    "UnconvertibleUnitError",
    "default_converter",
    "iter_quantities",
    "quantity_pattern",
    "resolve_converter",
    "si_normalise",
    "si_normalise_all",
]


class UnconvertibleUnitError(LookupError):
    """The converter does not know this unit.

    A ``LookupError``, and that is load-bearing: it is the *only* exception
    :func:`si_normalise` will absorb.  Anything else — above all a gauge↔absolute
    crossing — propagates.
    """


@runtime_checkable
class SiConverter(Protocol):
    """W2's SI normaliser, seen from here.

    ``to_si`` must preserve ``reference``: ``50 psig`` becomes a gauge quantity
    in pascals, never an absolute one.  It must raise (not return, not log) on a
    reference crossing, and it must raise :class:`UnconvertibleUnitError` — or any
    ``LookupError`` — for a unit it does not know.
    """

    def to_si(self, quantity: Quantity) -> Quantity:
        """Return ``quantity`` in SI units with its ``reference`` unchanged."""
        ...


ConverterSpec = SiConverter | Literal["auto"] | None
"""What callers may pass where a converter is expected.

``None``
    Do not convert.  Units stay exactly as written, and the resulting
    ``cat_key`` is a function of the unit as written.  Reproducible, and honest
    about the fact that no unit algebra ran.
``'auto'``
    Use W2's converter *if the package is importable*.  Convenient for a
    service process, and **never** appropriate where a ``cat_key`` is about to
    be stored: whether the conversion happened would then depend on which
    distribution was installed, and identity must not depend on that.
a converter object
    Use it.  This is the production path.
"""

# The attribute W2 is expected to publish.  One name, in one place, so that a
# rename in W2 is a one-line change here rather than a scavenger hunt.
_W2_MODULE: Final[str] = "mainline_domain.quantity"
_W2_ENTRY_POINT: Final[str] = "to_si"


@dataclass(frozen=True, slots=True)
class QuantityMatch:
    """One quantity found in text, with the span that evidences it."""

    quantity: Quantity
    span: tuple[int, int]
    """Half-open span into the text searched, covering number **and** unit."""
    raw: str
    reference_span: tuple[int, int] | None
    """Span of the prose marker that set a non-default reference, if any."""


# --------------------------------------------------------------------------- #
# Finding quantities                                                           #
# --------------------------------------------------------------------------- #

# A number: optional sign, digits with optional thousands separators, optional
# fraction.  No exponent form — a procedure does not write `1e3 kPa`, and
# accepting one would make `5e` in `5 each` ambiguous.
_NUMBER: Final[str] = r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d{1,12})(?:\.\d{1,9})?|[+-]?\.\d{1,9}"


@lru_cache(maxsize=1)
def quantity_pattern() -> re.Pattern[str]:
    """Return the compiled number+unit pattern, built from the committed unit table.

    Canonical tokens match case-sensitively (``m`` and ``M`` are different
    units); aliases match case-insensitively (``Months`` is ``months``).  The
    two alternations are separate named groups so the matcher knows which rule
    applied without re-testing the text.

    Canonical comes first in the alternation, but the trailing
    ``(?![A-Za-z0-9])`` sits outside both groups, so the engine backtracks: in
    ``'12 months'`` the canonical ``month`` matches, the lookahead fails on the
    ``s``, and the alias ``months`` is tried and succeeds.
    """
    units = load_lexicons().units
    canonical = "|".join(re.escape(token) for token in units.token_order)
    aliases = "|".join(re.escape(token) for token in units.alias_order)
    return re.compile(
        rf"(?<![\w.])(?P<value>{_NUMBER})[ \t]?"
        rf"(?:(?P<symbol>{canonical})|(?i:(?P<spelled>{aliases})))"
        rf"(?![A-Za-z0-9])"
    )


def _declared_reference(
    text: str,
    match_start: int,
    match_end: int,
    *,
    dimension: str,
    units: UnitClasses,
    grammar: Grammar,
) -> tuple[Reference, tuple[int, int] | None]:
    """Find the reference class the *prose* declares around a quantity.

    Only applied to dimensions where a reference means anything (pressure,
    temperature).  ``'approximately 5 m (gauge)'`` is a typo, not a gauge length,
    and treating it as one would put a meaningless discriminator into a
    ``cat_key``.
    """
    if dimension not in units.referenced_dimensions:
        return "none", None
    # Look just after the unit for '(g)', 'gauge', '(a)', 'absolute', ...
    tail = text[match_end : match_end + 24]
    for marker in grammar.reference_marker_order:
        position = tail.casefold().find(marker)
        if position != -1 and tail[:position].strip(" ") == "":
            reference = grammar.reference_markers[marker]
            start = match_end + position
            return _as_reference(reference), (start, start + len(marker))
    # Look before the value for a differential/delta cue.
    head_start = max(0, match_start - 48)
    head = text[head_start:match_start].casefold()
    for marker in grammar.reference_marker_order:
        if grammar.reference_markers[marker] != "delta":
            continue
        position = head.rfind(marker)
        if position != -1:
            start = head_start + position
            return "delta", (start, start + len(marker))
    return "none", None


def _as_reference(value: str) -> Reference:
    if value not in ("absolute", "gauge", "delta", "none"):
        raise ValueError(f"unit-class/grammar declared an illegal reference {value!r}")
    return value  # type: ignore[return-value]


def iter_quantities(text: str) -> Iterator[QuantityMatch]:
    """Yield every quantity in ``text``, left to right, non-overlapping.

    The unit is never guessed.  A bare number with no unit token yields nothing
    at all — the caller sees "no quantity here", which is what makes a clause
    reading ``shall not exceed 50`` come out as ``confidence='low'`` with
    ``value=None`` rather than as an invented ``50 kPa``.
    """
    lexicons = load_lexicons()
    units = lexicons.units
    grammar = lexicons.grammar
    for match in quantity_pattern().finditer(text):
        raw_unit = match.group("symbol") or match.group("spelled") or ""
        canonical = units.canonical(raw_unit)
        if canonical is None:  # pragma: no cover - the pattern is built from the table
            continue
        dimension = units.dimension[canonical]
        try:
            value = Decimal(match.group("value").replace(",", "").lstrip("+"))
        except InvalidOperation:  # pragma: no cover - _NUMBER cannot produce this
            continue
        declared = units.reference.get(canonical)
        if declared is not None:
            # The unit token itself carries the reference: `psig` is gauge no
            # matter what the surrounding prose says.  A unit is stronger
            # evidence than an adjacent word.
            reference, reference_span = _as_reference(declared), None
        else:
            reference, reference_span = _declared_reference(
                text,
                match.start(),
                match.end(),
                dimension=dimension,
                units=units,
                grammar=grammar,
            )
        yield QuantityMatch(
            quantity=Quantity(
                value=value, unit=canonical, dimension=dimension, reference=reference
            ),
            span=(match.start(), match.end()),
            raw=match.group(0),
            reference_span=reference_span,
        )


# --------------------------------------------------------------------------- #
# The seam to W2                                                               #
# --------------------------------------------------------------------------- #


def default_converter() -> SiConverter | None:
    """W2's converter if its package is importable, else ``None``.

    Deliberately *not* cached and deliberately not called at import time: a
    module-level lookup would bake "was W2 installed when this process started"
    into the package, and the whole point of the seam is that the answer is
    visible at each call site.
    """
    # Local imports, deliberately: a module-level lookup would bake "was W2
    # installed when this process started" into the package, and the point of
    # the seam is that the answer is visible at each call site.
    import importlib
    import importlib.util

    if importlib.util.find_spec(_W2_MODULE) is None:
        return None
    module = importlib.import_module(_W2_MODULE)
    candidate = getattr(module, _W2_ENTRY_POINT, None)
    if candidate is None or not callable(candidate):
        return None
    # Bound to an explicitly annotated local: narrowing from the guard above
    # does not survive into the closure below, and the declared type does.
    entry: Callable[[Quantity], object] = candidate

    class _ModuleConverter:
        """Adapts W2's module-level ``to_si`` to the :class:`SiConverter` shape."""

        def to_si(self, quantity: Quantity) -> Quantity:
            result = entry(quantity)
            if not isinstance(result, Quantity):
                raise TypeError(
                    f"{_W2_MODULE}.{_W2_ENTRY_POINT} returned {type(result).__name__}, "
                    f"expected contracts.Quantity"
                )
            return result

    return _ModuleConverter()


def resolve_converter(spec: ConverterSpec) -> SiConverter | None:
    """Turn a :data:`ConverterSpec` into a converter or ``None``."""
    if spec is None:
        return None
    if spec == "auto":
        return default_converter()
    if not hasattr(spec, "to_si"):
        raise TypeError(
            f"converter {type(spec).__name__} does not implement SiConverter.to_si; "
            f"pass None to skip conversion or 'auto' to use {_W2_MODULE} if present"
        )
    return spec


def si_normalise(
    quantity: Quantity | None,
    converter: SiConverter | None,
    *,
    keep_unconvertible: bool = True,
) -> Quantity | None:
    """SI-normalise one quantity, preserving its reference class.

    :param keep_unconvertible: when ``True`` (the default) a unit the converter
        does not know is kept verbatim, which is the behaviour spec §10
        describes for site-defined intervals like ``shift``.  When ``False`` the
        :class:`UnconvertibleUnitError` propagates, which is what an ingest path that
        refuses to store an un-normalised setpoint should ask for.

    **Only** ``LookupError`` is absorbed.  A gauge↔absolute crossing is not a
    ``LookupError`` and must escape: converting ``50 psig`` into ``446 kPa``
    absolute would flip a ``safe_direction`` comparison, so a caller must never
    be able to receive that answer, and must not be able to receive a silently
    un-normalised value in its place either.
    """
    if quantity is None or converter is None:
        return quantity
    try:
        converted = converter.to_si(quantity)
    except LookupError:
        if keep_unconvertible:
            return quantity
        raise
    if converted.reference != quantity.reference:
        raise ValueError(
            f"SI conversion changed the reference class from {quantity.reference!r} to "
            f"{converted.reference!r}. A gauge reading is not an absolute one (decision D5); "
            f"a converter that crosses references silently is the failure this check exists for."
        )
    return converted


def si_normalise_all(
    quantities: Sequence[Quantity | None],
    converter: SiConverter | None,
    *,
    keep_unconvertible: bool = True,
) -> tuple[Quantity | None, ...]:
    """:func:`si_normalise` over a sequence, in order."""
    return tuple(
        si_normalise(quantity, converter, keep_unconvertible=keep_unconvertible)
        for quantity in quantities
    )
