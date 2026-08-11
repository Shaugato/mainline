# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Reading ``(comparator, value, range, tolerance)`` out of canonical clause text.

Input is always ``CanonResult.canon_text`` from CANONHOLD, never raw text.  By
the time text reaches here the smart quotes, ligatures, soft hyphens, line wraps
and page furniture are gone and whitespace is collapsed to single spaces, so
this grammar can be small and literal instead of defensive.  Every span it
returns is an offset into that same ``canon_text``, which is the offset space
the whole system uses.

WHAT IT REFUSES TO DO
---------------------
It does not guess a unit.  ``a maximum of 50`` yields a measurement with
``value=None`` and ``bare_number`` set: the number is recorded, the quantity is
not manufactured.  Worker W3's CAT extractor turns that into
``cat_confidence='low'`` and the lattice treats an unreadable setpoint as it
treats every other unanswerable question.  Inventing a unit from the parameter
name would be the single highest-leverage silent-failure generator available:
``max_operating_pressure: 50`` could be psig or bar, and those are a factor of
14 apart in the direction of the failure nobody survives.

It does not do relative tolerance arithmetic either.  ``50 kPa ± 5 %`` is
recorded as a value and a *relative* tolerance; turning that into ``±2.5 kPa``
is a decision about whether the percentage is of the setpoint or of the span,
which is an instrumentation question this module has no standing to answer.

WHAT IT DOES DO
---------------
Six shapes, and they are the six that carry setpoints in the corpus:

===========================  =======================================================
``not exceed 50 psig``       comparator ``le``, value
``at least 2 points``        comparator ``ge``, value in ``[tally]``
``>= 19.5 %vol``             comparator ``ge``, value, symbol form
``50 +/- 2 kPa``             value with an absolute tolerance
``50 kPa +/- 5 %``           value with a relative tolerance
``between 40 and 60 degC``   comparator ``between``, value and upper
===========================  =======================================================

TWO KNOWN GAPS, BOTH FAILING TOWARDS SILENCE
--------------------------------------------
A unit token must be **adjacent** to its number, so ``2 isolation points`` reads
as a bare 2 rather than as two tallies.  And spelled-out numerals are not read at
all, so ``two isolation points`` yields nothing.  Both are recorded in
``novelty/directrix.yaml`` under ``unverified``.

Neither is fixed by relaxation, and the reason is asymmetric cost.  Allowing one
intervening word before a counting noun would read ``2 isolation points``
correctly and would also read ``50 metre levels`` and ``3 shift hours`` as things
they are not, at a false-positive rate nobody has measured.  Under-reading
produces a bare number, which W3 marks ``cat_confidence='low'``, which over
blood-written ancestry defaults to ``weaken`` — adjudication.  Over-reading
produces a confident wrong comparison — a verdict.  The gap stays until somebody
measures the alternative on the corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal

from ..contracts import Quantity
from .algebra import as_decimal, quantity
from .errors import UnitParseError
from .units import AMBIGUOUS_TOKENS, UNIT_TOKENS
from .version import PARSE_VERSION

__all__ = [
    "COMPARATORS",
    "Comparator",
    "Measurement",
    "parse_measurements",
    "parse_one",
]

Comparator = Literal["lt", "le", "eq", "ge", "gt", "approx", "between", "none"]

COMPARATORS: Final[tuple[Comparator, ...]] = (
    "lt",
    "le",
    "eq",
    "ge",
    "gt",
    "approx",
    "between",
    "none",
)


@dataclass(frozen=True, slots=True)
class Measurement:
    """One measurement phrase found in ``canon_text``.

    ``value`` is ``None`` exactly when no unit token followed the number; the
    digits are then in ``bare_number`` and the caller must decide what an
    unqualified number means.  This module never decides that.

    ``tolerance`` is an absolute tolerance in the same frame as ``value``.
    ``tolerance_relative`` is a fraction (``Decimal('0.05')`` for ``± 5 %``) and
    is never converted into an absolute one — see the module docstring.
    """

    comparator: Comparator
    value: Quantity | None
    upper: Quantity | None
    tolerance: Quantity | None
    tolerance_relative: Decimal | None
    bare_number: Decimal | None
    span: tuple[int, int]
    raw: str
    parse_version: int


# --------------------------------------------------------------------------- #
# lexical pieces                                                               #
# --------------------------------------------------------------------------- #

#: A printed magnitude.  Thousands separators are permitted because procedures
#: print them; exponent notation is not, because no procedure prints it and a
#: pattern that accepts ``1e5`` also accepts the ``e`` of an adjacent word.
_NUMBER: Final[str] = r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?"

#: Every token the vocabulary knows, longest first so ``%LEL`` wins over ``%``
#: and ``kPag`` wins over ``kPa``.  Ambiguous tokens are in the alternation on
#: purpose: matching ``C`` and then *refusing* it is a diagnosis, whereas not
#: matching it at all silently drops the setpoint.
_UNIT_ALTERNATION: Final[str] = "|".join(
    re.escape(token)
    for token in sorted(set(UNIT_TOKENS) | set(AMBIGUOUS_TOKENS), key=lambda t: (-len(t), t))
)

#: A unit token must not be followed by a word character, or ``m`` would match
#: the start of ``metres of head`` and ``t`` the start of ``the``.  It may be
#: followed by punctuation or end-of-string.
_UNIT: Final[str] = rf"(?:{_UNIT_ALTERNATION})(?![A-Za-z0-9_])"

#: The separator lives INSIDE the optional unit group, so a bare number's span
#: ends at its last digit rather than swallowing the following space.  Spans are
#: offsets into ``canon_text`` that end up in evidence, and an evidence span with
#: a stray space in it is a small lie about what was read.
_MEASURE: Final[re.Pattern[str]] = re.compile(rf"(?P<number>{_NUMBER})(?:\s*(?P<unit>{_UNIT}))?")

_RANGE: Final[re.Pattern[str]] = re.compile(
    rf"\b(?:between|from)\s+(?P<low>{_NUMBER})\s*(?P<low_unit>{_UNIT})?\s*"
    rf"(?:and|to|-)\s*(?P<high>{_NUMBER})\s*(?P<high_unit>{_UNIT})?",
    re.IGNORECASE,
)

#: ``+/-`` is what canon() leaves behind for ``±``: the fold step maps the sign
#: to ASCII, so the Unicode form never reaches this module.  Both are accepted
#: anyway, because a caller handing raw text to a parser documented to take
#: canon text is a mistake that should cost a wrong answer, not a crash.
_TOLERANCE: Final[re.Pattern[str]] = re.compile(
    rf"\s*(?:\+/-|\+-|±)\s*(?P<tol>{_NUMBER})\s*(?P<tol_unit>{_UNIT})?"
)

#: Comparator phrases, scanned in the text *preceding* a number.  Longest and
#: most specific first; the scan takes the match closest to the number, so
#: ``shall not exceed`` beats a stray ``at`` earlier in the sentence.
_COMPARATOR_PHRASES: Final[tuple[tuple[str, Comparator], ...]] = (
    (r"must\s+not\s+exceed", "le"),
    (r"shall\s+not\s+exceed", "le"),
    (r"not\s+to\s+exceed", "le"),
    (r"does\s+not\s+exceed", "le"),
    (r"not\s+exceed", "le"),
    (r"no\s+more\s+than", "le"),
    (r"not\s+more\s+than", "le"),
    (r"no\s+greater\s+than", "le"),
    (r"not\s+greater\s+than", "le"),
    (r"at\s+most", "le"),
    (r"up\s+to\s+and\s+including", "le"),
    (r"maximum\s+of", "le"),
    (r"a\s+maximum\s+of", "le"),
    (r"max(?:imum)?\.?", "le"),
    (r"<=", "le"),
    (r"=<", "le"),
    (r"no\s+less\s+than", "ge"),
    (r"not\s+less\s+than", "ge"),
    (r"at\s+least", "ge"),
    (r"minimum\s+of", "ge"),
    (r"a\s+minimum\s+of", "ge"),
    (r"min(?:imum)?\.?", "ge"),
    (r">=", "ge"),
    (r"=>", "ge"),
    (r"less\s+than", "lt"),
    (r"lower\s+than", "lt"),
    (r"below", "lt"),
    (r"<", "lt"),
    (r"greater\s+than", "gt"),
    (r"more\s+than", "gt"),
    (r"higher\s+than", "gt"),
    (r"above", "gt"),
    (r"exceeds", "gt"),
    (r">", "gt"),
    (r"approximately", "approx"),
    (r"about", "approx"),
    (r"circa", "approx"),
    (r"~=", "approx"),
    (r"~", "approx"),
    (r"equal\s+to", "eq"),
    (r"exactly", "eq"),
    (r"=", "eq"),
)

_COMPARATOR_RE: Final[re.Pattern[str]] = re.compile(
    "|".join(f"(?P<c{i}>{phrase})" for i, (phrase, _) in enumerate(_COMPARATOR_PHRASES)),
    re.IGNORECASE,
)

_COMPARATOR_BY_GROUP: Final[dict[str, Comparator]] = {
    f"c{i}": kind for i, (_, kind) in enumerate(_COMPARATOR_PHRASES)
}

#: How far back a comparator phrase may sit from its number.  Long enough for
#: ``shall not exceed a working pressure of``, short enough that a ``maximum``
#: two sentences earlier does not attach itself to an unrelated figure.
_LOOKBACK: Final[int] = 48


def _comparator_before(text: str, at: int) -> tuple[Comparator, int]:
    """The comparator governing the number at ``at``, and where its phrase starts.

    Returns ``('none', at)`` when nothing qualifies.  ``none`` is a real answer:
    a bare ``50 psig`` in a clause states a value without stating a bound, and
    rule R3 of the lattice cares about the difference between ``<=`` and ``<``,
    so silently promoting an unbounded value to ``eq`` would fabricate the very
    field the rule reads.
    """
    window_start = max(0, at - _LOOKBACK)
    window = text[window_start:at]
    best: tuple[Comparator, int] | None = None
    for match in _COMPARATOR_RE.finditer(window):
        # Only the run of separators between the phrase and the number may
        # intervene: 'not exceed 50' qualifies, 'not exceed the pressure 50'
        # does not, because the noun phrase in between may carry its own bound.
        between = window[match.end() :]
        if between.strip(" \t()[]:;,-") != "":
            continue
        for group, kind in _COMPARATOR_BY_GROUP.items():
            if match.group(group) is not None:
                best = (kind, window_start + match.start())
                break
    return best if best is not None else ("none", at)


def _make_quantity(number: str, unit_token: str | None) -> tuple[Quantity | None, Decimal | None]:
    """``(value, bare_number)`` — exactly one of the two is not ``None``.

    An ambiguous or unknown unit token does **not** propagate its exception to
    the caller: it degrades the measurement to a bare number, which is what a
    human reader would also be left with.  The exception is not swallowed
    silently — the token is gone from the result, so the CAT extractor sees a
    setpoint with no unit and marks the clause ``low``, which is the state that
    reaches the gate.
    """
    magnitude = as_decimal(number)
    if unit_token is None:
        return None, magnitude
    try:
        return quantity(magnitude, unit_token), None
    except UnitParseError:
        return None, magnitude


def parse_measurements(canon_text: str) -> tuple[Measurement, ...]:
    """Every measurement phrase in the text, in order of appearance.

    Ranges are recognised first and their two endpoints are then excluded from
    the single-value scan, so ``between 40 and 60 degC`` produces one
    ``between`` measurement rather than three overlapping ones.
    """
    found: list[Measurement] = []
    consumed: list[tuple[int, int]] = []

    for match in _RANGE.finditer(canon_text):
        high_unit = match.group("high_unit")
        # 'between 40 and 60 degC' — the unit is printed once, at the end, and
        # governs both endpoints.  'between 40 degC and 60 degC' prints it twice.
        low_unit = match.group("low_unit") or high_unit
        low, low_bare = _make_quantity(match.group("low"), low_unit)
        high, high_bare = _make_quantity(match.group("high"), high_unit)
        span = (match.start(), match.end())
        found.append(
            Measurement(
                comparator="between",
                value=low,
                upper=high,
                tolerance=None,
                tolerance_relative=None,
                bare_number=low_bare if low is None else None,
                span=span,
                raw=canon_text[span[0] : span[1]],
                parse_version=PARSE_VERSION,
            )
        )
        _ = high_bare
        consumed.append(span)

    for match in _MEASURE.finditer(canon_text):
        if any(start <= match.start() < end for start, end in consumed):
            continue

        unit_token = match.group("unit")
        value, bare = _make_quantity(match.group("number"), unit_token)
        comparator, phrase_start = _comparator_before(canon_text, match.start())
        end = match.end()

        tolerance: Quantity | None = None
        tolerance_relative: Decimal | None = None
        tolerance_match = _TOLERANCE.match(canon_text, end)
        if tolerance_match is not None:
            tol_unit = tolerance_match.group("tol_unit")
            if tol_unit in ("%", "pct"):
                tolerance_relative = as_decimal(tolerance_match.group("tol")) / Decimal(100)
            else:
                # '50 +/- 2 kPa' prints the unit once, after the tolerance, and
                # it governs both; '50 kPa +/- 2 kPa' prints it twice.
                tolerance, _ = _make_quantity(tolerance_match.group("tol"), tol_unit or unit_token)
                if value is None and tol_unit is not None:
                    value, bare = _make_quantity(match.group("number"), tol_unit)
            end = tolerance_match.end()
            # The tolerance's own number must not be re-emitted as a second,
            # unrelated measurement: '50 +/- 2 kPa' is one setpoint with a band,
            # not a 50 and a 2, and a spurious '2 kPa' in the CAT would look
            # like a control the descendant dropped.
            consumed.append((tolerance_match.start(), tolerance_match.end()))

        found.append(
            Measurement(
                comparator=comparator,
                value=value,
                upper=None,
                tolerance=tolerance,
                tolerance_relative=tolerance_relative,
                bare_number=bare,
                span=(phrase_start, end),
                raw=canon_text[phrase_start:end],
                parse_version=PARSE_VERSION,
            )
        )

    found.sort(key=lambda m: m.span)
    return tuple(found)


def parse_one(canon_text: str) -> Measurement | None:
    """The single measurement in a phrase, or ``None`` if there is not exactly one.

    ``None`` for *zero or many*, not "the first one".  A clause carrying two
    setpoints has two controls in it, and picking one would silently discard the
    other — which, if the discarded one is the one that moved, is a missed
    weakening.  Callers that want them all call :func:`parse_measurements`.
    """
    measurements = parse_measurements(canon_text)
    return measurements[0] if len(measurements) == 1 else None
