# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The fallback hard-anchor extractor: regex plus a committed word list, no model.

Layer 4 needs an anchor set for the source document and an anchor set for the model's
proposal. When ``mainline_domain.anchors`` is importable, that is the extractor layer 4
uses and this module is not reached. When it is not - a fork that took only the Apache
substrate, a container that ships the quarantine without the algorithms domain - this is
what runs, and it is real code rather than a stub returning nothing, because an extractor
that finds no anchors turns every anchor-based refusal into a pass.

**The two must agree, and a test says so.** The class precedence, the surface patterns
and the normalisation rules below are the ones ANCHORLOCK uses, and the word lists are
copied from its committed TOML gazetteers at recorded digests.
``tests/security/injection/test_corpus.py`` runs both extractors over every corpus
document and fails on any disagreement, so a divergence is a red test rather than a
quiet difference in what counts as an anchor.

**Precedence, most-constrained first**, exactly as ANCHORLOCK orders it::

    cas > regulatory_citation > isolation_point_id > instrument_loop
        > equipment_tag > setpoint

A match that overlaps an already-claimed span is discarded. ``named_role`` is **not**
implemented here and is not checked by layer 4 in either lane - see
:data:`mainline_quarantine.anchoring.CHECKED_CLASSES` for why.

**Unknown prefixes fail closed.** A hyphenated ``LETTERS-DIGITS`` token whose code is in
no list is still extracted as an ``equipment_tag``. More anchors means more identity
constraints means more blocking, never less - which is the polarity a refusal product
needs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from .errors import AnchorExtractorUnavailable

__all__ = [
    "CAS_PATTERN",
    "GazetteerAnchorExtractor",
    "Gazetteers",
    "cas_check_digit",
    "is_valid_cas",
    "load_gazetteers",
]

CAS_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<![\d-])(\d{2,7})-(\d{2})-(\d)(?![\d-])")

#: ``(class, raw, norm, span)`` - the flat shape both extractor lanes produce.
_Anchor = tuple[str, str, str, tuple[int, int]]


def cas_check_digit(body: str) -> int:
    """Return the expected check digit for a CAS number's first two groups."""
    if not body.isdigit():
        raise ValueError(f"CAS body must be digits, got {body!r}")
    return sum(int(digit) * weight for weight, digit in enumerate(reversed(body), start=1)) % 10


def is_valid_cas(first: str, second: str, check: str) -> bool:
    """Return ``True`` iff the three groups form a checksum-valid CAS number."""
    if first.startswith("0"):
        # CAS numbers are not zero-padded; a leading zero means this is a date or a part
        # number that happens to share the shape.
        return False
    return cas_check_digit(first + second) == int(check)


@dataclass(frozen=True, slots=True)
class Gazetteers:
    """The committed word lists, already ordered for alternation."""

    equipment_codes: frozenset[str]
    instrument_codes: tuple[str, ...]
    isolation_prefixes: tuple[str, ...]
    citation_bodies: tuple[str, ...]
    citation_regulations: tuple[str, ...]
    subdivision_tokens: dict[str, str]
    setpoint_units: tuple[str, ...]
    setpoint_qualifiers: tuple[str, ...]
    source: str


def _strings(document: Any, key: str, source: str) -> tuple[str, ...]:
    raw = document.get(key)
    if not isinstance(raw, list) or not raw:
        raise AnchorExtractorUnavailable(
            f"{source}: {key} must be a non-empty array of strings; an empty word list "
            f"disables a refusal"
        )
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            raise AnchorExtractorUnavailable(f"{source}: {key} contains an empty entry")
        out.append(item)
    return tuple(out)


def _longest_first(values: tuple[str, ...]) -> tuple[str, ...]:
    """Alternation order. Without this, ``AS`` shadows ``AS/NZS``."""
    return tuple(sorted(set(values), key=lambda value: (-len(value), value)))


@lru_cache(maxsize=4)
def load_gazetteers(path: Path) -> Gazetteers:
    """Load a gazetteer JSON document. Strict: a malformed file raises."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AnchorExtractorUnavailable(f"cannot read gazetteer {path}: {exc}") from exc
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnchorExtractorUnavailable(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise AnchorExtractorUnavailable(f"{path} must contain a JSON object")

    source = str(path)
    subdivisions = document.get("subdivision_tokens")
    if not isinstance(subdivisions, dict) or not subdivisions:
        raise AnchorExtractorUnavailable(f"{source}: subdivision_tokens must be a non-empty map")

    return Gazetteers(
        equipment_codes=frozenset(_strings(document, "equipment_codes", source)),
        instrument_codes=_longest_first(_strings(document, "instrument_codes", source)),
        isolation_prefixes=_longest_first(_strings(document, "isolation_prefixes", source)),
        citation_bodies=_longest_first(_strings(document, "citation_bodies", source)),
        citation_regulations=_longest_first(_strings(document, "citation_regulations", source)),
        subdivision_tokens={str(k): str(v) for k, v in subdivisions.items()},
        setpoint_units=_longest_first(_strings(document, "setpoint_units", source)),
        setpoint_qualifiers=_longest_first(_strings(document, "setpoint_qualifiers", source)),
        source=source,
    )


def _alternation(values: tuple[str, ...]) -> str:
    return "|".join(re.escape(value) for value in values)


class _Patterns:
    """Regexes built from one gazetteer. Built once per extractor."""

    __slots__ = (
        "citation_body",
        "citation_reg",
        "equipment",
        "instrument",
        "isolation",
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
            r"(?:[ \t]*(?P<tok1>" + _alternation(tuple(gaz.subdivision_tokens)) + r")\.?)?"
            r"(?:[ \t]*(?P<tok2>" + _alternation(tuple(gaz.subdivision_tokens)) + r")\.?)?"
            r"[ \t]*(?P<number>\d{1,4}[A-Za-z]?(?:\.\d{1,3})*)(?![\w])",
            re.IGNORECASE,
        )
        self.isolation = re.compile(
            r"(?<![A-Za-z0-9])(?P<prefix>" + _alternation(gaz.isolation_prefixes) + r")"
            r"-(?P<number>\d{1,6})(?P<suffix>[A-Z]{0,2})(?![\w-])"
        )
        self.instrument = re.compile(
            r"(?<![A-Za-z0-9])(?:(?P<area>\d{1,3})-)?"
            r"(?P<code>" + _alternation(gaz.instrument_codes) + r")"
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


@dataclass(frozen=True, slots=True)
class GazetteerAnchorExtractor:
    """The fallback extractor. Constructed from a gazetteer JSON path."""

    gazetteers: Gazetteers
    patterns: _Patterns
    name: str = "gazetteer-fallback"

    @classmethod
    def from_path(cls, path: Path) -> GazetteerAnchorExtractor:
        """Build an extractor from a committed gazetteer document."""
        gaz = load_gazetteers(path)
        return cls(gazetteers=gaz, patterns=_Patterns(gaz))

    def extract(self, text: str) -> tuple[tuple[str, str, str, tuple[int, int]], ...]:
        """Return ``(class, raw, norm, span)`` for every anchor, in precedence order.

        One pass per class, most-constrained first, each discarding a match that overlaps
        a span an earlier class already claimed. The order is the control: ``ISO 45001``
        must be read as a citation before ``ISOL-4471``'s shape gets a look, and
        ``PIT-1204`` as an instrument loop before the loose equipment shape claims it.
        """
        claimed: list[tuple[int, int]] = []
        out: list[_Anchor] = []
        for stage in (
            self._cas,
            self._citations,
            self._isolation,
            self._instrument,
            self._equipment,
            self._setpoint,
        ):
            out.extend(stage(text, claimed))
        return tuple(out)

    # -- one pass per class, in precedence order --------------------------------

    def _cas(self, text: str, claimed: list[tuple[int, int]]) -> list[_Anchor]:
        out: list[_Anchor] = []
        for match in CAS_PATTERN.finditer(text):
            first, second, check = match.group(1), match.group(2), match.group(3)
            if not is_valid_cas(first, second, check):
                continue
            if _claim(claimed, match.start(), match.end()):
                out.append(
                    (
                        "cas",
                        match.group(0),
                        f"{int(first)}-{second}-{check}",
                        (match.start(), match.end()),
                    )
                )
        return out

    def _citations(self, text: str, claimed: list[tuple[int, int]]) -> list[_Anchor]:
        out: list[_Anchor] = []
        for match in self.patterns.citation_body.finditer(text):
            if _claim(claimed, match.start(), match.end()):
                out.append(
                    (
                        "regulatory_citation",
                        match.group(0),
                        f"{match.group('body').upper()} {match.group('number')}",
                        (match.start(), match.end()),
                    )
                )
        for match in self.patterns.citation_reg.finditer(text):
            kind = "REG"
            for group in ("tok1", "tok2"):
                token = match.group(group)
                if token is not None:
                    kind = self.gazetteers.subdivision_tokens[token.casefold()]
            if _claim(claimed, match.start(), match.end()):
                out.append(
                    (
                        "regulatory_citation",
                        match.group(0),
                        f"{match.group('name').upper()} {kind} {match.group('number').upper()}",
                        (match.start(), match.end()),
                    )
                )
        return out

    def _isolation(self, text: str, claimed: list[tuple[int, int]]) -> list[_Anchor]:
        out: list[_Anchor] = []
        for match in self.patterns.isolation.finditer(text):
            if _claim(claimed, match.start(), match.end()):
                norm = f"{match.group('prefix')}-{match.group('number')}{match.group('suffix')}"
                out.append(
                    ("isolation_point_id", match.group(0), norm, (match.start(), match.end()))
                )
        return out

    def _instrument(self, text: str, claimed: list[tuple[int, int]]) -> list[_Anchor]:
        out: list[_Anchor] = []
        for match in self.patterns.instrument.finditer(text):
            if _claim(claimed, match.start(), match.end()):
                out.append(
                    (
                        "instrument_loop",
                        match.group(0),
                        _tag_norm(
                            match.group("area"),
                            match.group("code"),
                            match.group("number"),
                            match.group("suffix"),
                        ),
                        (match.start(), match.end()),
                    )
                )
        return out

    def _equipment(self, text: str, claimed: list[tuple[int, int]]) -> list[_Anchor]:
        out: list[_Anchor] = []
        for match in self.patterns.equipment.finditer(text):
            code = match.group("code")
            if not match.group("sep") and code not in self.gazetteers.equipment_codes:
                continue
            if _claim(claimed, match.start(), match.end()):
                out.append(
                    (
                        "equipment_tag",
                        match.group(0),
                        _tag_norm(
                            match.group("area"), code, match.group("number"), match.group("suffix")
                        ),
                        (match.start(), match.end()),
                    )
                )
        return out

    def _setpoint(self, text: str, claimed: list[tuple[int, int]]) -> list[_Anchor]:
        out: list[_Anchor] = []
        for match in self.patterns.setpoint.finditer(text):
            if not _claim(claimed, match.start(), match.end()):
                continue
            comparator = match.group("cmp") or ""
            qualifier = match.group("qual") or ""
            value = match.group("value").replace(",", "")
            out.append(
                (
                    "setpoint",
                    match.group(0),
                    f"{comparator}{value}{match.group('unit')}{qualifier}",
                    (match.start(), match.end()),
                )
            )
        return out
