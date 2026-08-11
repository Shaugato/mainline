# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""ANCHORLOCK extraction — seven classes, regex plus committed gazetteer.

Three properties make hard anchors load-bearing, and all three are properties of
*this* implementation, not of an aspiration:

1. **Paraphrase-invariant.**  A model rewriting for style does not turn
   ``P-101A`` into a synonym.  Nothing here consults a model, so nothing here
   can be talked out of an anchor.
2. **Cheap and exact.**  Regex and word lists.  No threshold, no embedding, no
   drift, no calibration to maintain.
3. **Their disappearance is signal.**  See :mod:`mainline_domain.anchors.drop`.

**Class precedence.**  Several classes share a surface shape (``ISO 45001`` vs
``ISOL-4471``; ``PIT-1204`` vs ``P-101A``), so extraction runs in a fixed order
and a match that overlaps an already-claimed span is discarded:

``cas`` > ``regulatory_citation`` > ``isolation_point_id`` > ``instrument_loop``
> ``equipment_tag`` > ``setpoint`` > ``named_role``

The order runs most-constrained first.  A CAS number must satisfy a checksum; a
citation must name a standards body; an isolation point must carry a hyphen and a
known prefix.  Only then does the loose ``LETTERS-DIGITS`` shape get a look.

**Unknown prefixes fail closed.**  A hyphenated ``LETTERS-DIGITS`` token whose
code appears in no gazetteer is still extracted, as an ``equipment_tag``.  More
anchors means more identity constraints means more blocking — never less.  The
cost of the choice is nuisance adjudication; the cost of the other choice is a
tag that can be swapped without anyone noticing.

Input is expected to be ``canon_text``: every span this module produces is a
half-open offset into the string it was given.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Final

from ..contracts import Anchor, AnchorClass, AnchorSet
from .cas import CAS_PATTERN, is_valid_cas
from .gazetteer import Gazetteers, load_gazetteers

__all__ = ["compiled_patterns", "extract_anchors", "iter_anchors"]

_WS: Final[re.Pattern[str]] = re.compile(r"\s+")


def _alternation(values: tuple[str, ...]) -> str:
    return "|".join(re.escape(value) for value in values)


class _Patterns:
    """Regexes built from the gazetteers.  Built once, cached."""

    __slots__ = (
        "citation_body",
        "citation_reg",
        "equipment",
        "instrument",
        "isolation",
        "role",
        "setpoint",
    )

    def __init__(self, gaz: Gazetteers) -> None:
        self.citation_body = re.compile(
            r"(?<![A-Za-z0-9])(?P<body>" + _alternation(gaz.citation_bodies) + r")"
            r"[ \t]?(?P<number>\d{2,6}(?:[.\-]\d{1,4})*)"
            r"(?::(?P<year>\d{4}))?(?![\w])"
        )
        self.citation_reg = re.compile(
            r"(?<![A-Za-z0-9])(?P<name>" + _alternation(gaz.citation_regulations) + r")"
            r"(?:[ \t]*(?P<tok1>" + _alternation(tuple(gaz.subdivision_kinds)) + r")\.?)?"
            r"(?:[ \t]*(?P<tok2>" + _alternation(tuple(gaz.subdivision_kinds)) + r")\.?)?"
            r"[ \t]*(?P<number>\d{1,4}[A-Za-z]?(?:\.\d{1,3})*)(?![\w])",
            re.IGNORECASE,
        )
        self.isolation = re.compile(
            r"(?<![A-Za-z0-9])(?P<prefix>" + _alternation(gaz.isolation_prefixes) + r")"
            r"-(?P<number>\d{1,6})(?P<suffix>[A-Z]{0,2})(?![\w-])"
        )
        self.instrument = re.compile(
            r"(?<![A-Za-z0-9])(?:(?P<area>\d{1,3})-)?"
            r"(?P<code>"
            + _alternation(tuple(sorted(gaz.instrument_codes, key=lambda c: (-len(c), c))))
            + r")"
            r"-?(?P<number>\d{2,5})(?P<suffix>[A-Z]{0,2})(?![\w-])"
        )
        self.equipment = re.compile(
            r"(?<![A-Za-z0-9])(?:(?P<area>\d{1,3})-)?"
            r"(?P<code>[A-Z]{1,4})(?P<sep>-?)(?P<number>\d{2,5})(?P<suffix>[A-Z]{0,2})(?![\w-])"
        )
        self.setpoint = re.compile(
            r"(?<![\w.-])(?:(?P<cmp><=|>=|<|>|=|\+/-)[ \t]*)?"
            r"(?P<value>\d{1,7}(?:[.,]\d{1,6})?)[ \t]*"
            r"(?P<unit>" + _alternation(gaz.setpoint_units) + r")"
            r"(?![A-Za-z0-9])"
            r"(?:[ \t]*(?P<qual>" + _alternation(gaz.setpoint_qualifiers) + r")(?![A-Za-z0-9]))?"
        )
        self.role = re.compile(
            r"(?<![A-Za-z])(?P<role>"
            + "|".join(re.escape(variant) for variant, _ in gaz.role_variants)
            + r")(?![A-Za-z])",
            re.IGNORECASE,
        )


@lru_cache(maxsize=1)
def compiled_patterns() -> _Patterns:
    return _Patterns(load_gazetteers())


def _claim(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    """Accept ``[start, end)`` unless it overlaps a span already claimed."""
    for claimed_start, claimed_end in spans:
        if start < claimed_end and claimed_start < end:
            return False
    spans.append((start, end))
    return True


def _tag_norm(area: str | None, code: str, number: str, suffix: str) -> str:
    core = f"{code}-{number}{suffix}"
    return f"{area}-{core}" if area else core


def iter_anchors(canon_text: str) -> Iterator[Anchor]:
    """Yield every anchor in ``canon_text``, in class-precedence order."""
    gaz = load_gazetteers()
    pat = compiled_patterns()
    claimed: list[tuple[int, int]] = []

    # 1. CAS — checksum-validated, so it can safely run first.
    for match in CAS_PATTERN.finditer(canon_text):
        first, second, check = match.group(1), match.group(2), match.group(3)
        if not is_valid_cas(first, second, check):
            continue
        if _claim(claimed, match.start(), match.end()):
            yield Anchor(
                cls=AnchorClass.CAS,
                raw=match.group(0),
                norm=f"{int(first)}-{second}-{check}",
                span=(match.start(), match.end()),
            )

    # 2. Regulatory citations — standards bodies, then named regulations.
    for match in pat.citation_body.finditer(canon_text):
        body = match.group("body").upper()
        number = match.group("number")
        if _claim(claimed, match.start(), match.end()):
            yield Anchor(
                cls=AnchorClass.REGULATORY_CITATION,
                raw=match.group(0),
                norm=f"{body} {number}",
                span=(match.start(), match.end()),
            )
    for match in pat.citation_reg.finditer(canon_text):
        name = match.group("name").upper()
        kind = "REG"
        for group in ("tok1", "tok2"):
            token = match.group(group)
            if token is not None:
                kind = gaz.subdivision_kinds[token.casefold()]
        if _claim(claimed, match.start(), match.end()):
            yield Anchor(
                cls=AnchorClass.REGULATORY_CITATION,
                raw=match.group(0),
                norm=f"{name} {kind} {match.group('number').upper()}",
                span=(match.start(), match.end()),
            )

    # 3. Isolation points — hyphen mandatory, prefix from the gazetteer.
    for match in pat.isolation.finditer(canon_text):
        if _claim(claimed, match.start(), match.end()):
            yield Anchor(
                cls=AnchorClass.ISOLATION_POINT_ID,
                raw=match.group(0),
                norm=f"{match.group('prefix')}-{match.group('number')}{match.group('suffix')}",
                span=(match.start(), match.end()),
            )

    # 4. Instrument loops — ISA function codes win over the equipment shape.
    for match in pat.instrument.finditer(canon_text):
        if _claim(claimed, match.start(), match.end()):
            yield Anchor(
                cls=AnchorClass.INSTRUMENT_LOOP,
                raw=match.group(0),
                norm=_tag_norm(
                    match.group("area"),
                    match.group("code"),
                    match.group("number"),
                    match.group("suffix"),
                ),
                span=(match.start(), match.end()),
            )

    # 5. Equipment tags — a hyphen, or a known code, is required.
    for match in pat.equipment.finditer(canon_text):
        code = match.group("code")
        if not match.group("sep") and code not in gaz.equipment_codes:
            continue
        if _claim(claimed, match.start(), match.end()):
            yield Anchor(
                cls=AnchorClass.EQUIPMENT_TAG,
                raw=match.group(0),
                norm=_tag_norm(
                    match.group("area"), code, match.group("number"), match.group("suffix")
                ),
                span=(match.start(), match.end()),
            )

    # 6. Setpoints — value + unit AS WRITTEN.  No SI conversion here (D5).
    for match in pat.setpoint.finditer(canon_text):
        if not _claim(claimed, match.start(), match.end()):
            continue
        comparator = match.group("cmp") or ""
        qualifier = match.group("qual") or ""
        value = match.group("value").replace(",", "")
        yield Anchor(
            cls=AnchorClass.SETPOINT,
            raw=match.group(0),
            norm=f"{comparator}{value}{match.group('unit')}{qualifier}",
            span=(match.start(), match.end()),
        )

    # 7. Named roles — phrase match, longest variant first.
    variant_norms = dict(gaz.role_variants)
    for match in pat.role.finditer(canon_text):
        if not _claim(claimed, match.start(), match.end()):
            continue
        surface = _WS.sub(" ", match.group("role")).casefold()
        norm = variant_norms.get(surface)
        if norm is None:
            continue
        yield Anchor(
            cls=AnchorClass.NAMED_ROLE,
            raw=match.group(0),
            norm=norm,
            span=(match.start(), match.end()),
        )


def extract_anchors(canon_text: str) -> AnchorSet:
    """Extract the full anchor set of one clause version."""
    return AnchorSet(items=frozenset(iter_anchors(canon_text)))
