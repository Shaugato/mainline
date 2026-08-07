# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The versioned analyser — the part of channel D that actually matters.

Dense embeddings systematically lose exactly the tokens a permit gate needs: ``K-401``,
``TK-12``, ``CC-07``, ``H2S``, ``%LEL``, ``30 CFR 57.22239``, ``7783-06-4`` and OEM part
numbers.  Channel D exists to keep them, so the analyser's contract is stricter than a search
engine's:

1. **Identifier structure is preserved, not destroyed.**  ``K-401`` is emitted whole *and* as
   its components, case-folded, never stemmed.  Stemming ``K-401`` — or splitting it on the
   letter/digit boundary into ``k``, ``401`` — is how a channel loses the one token that
   identifies the vessel that killed someone.  Components are split on **explicit separators
   only**: ``H2S`` stays ``h2s``.
2. **Quantities are SI-normalised**, so ``1000 ppm`` and ``0.1 %`` produce the same term —
   and ``25 %LEL`` and ``25 %`` never do (see :mod:`trappoint_recall.lexical.units`).
3. **Citations and CAS numbers are verbatim** in the sense that matters: canonicalised to a
   space-free structured form, never stemmed, never split into prose.
4. **Prose, and only prose**, is lowercased, stopped and Porter-stemmed.
5. **Every token carries its class**, so the writer, the query builder and any future
   learned-sparse weighting can treat identifier evidence differently from prose evidence
   without re-deriving what a token is.

**A changed analyser invalidates every posting in ``mainline.lex_posting``.**  It is therefore
a migration, not a patch.  :data:`ANALYSER_VERSION` and :func:`rule_fingerprint` exist so that
CI notices; ``tests/unit/recall_lexical/test_analyser_golden.py`` turns "notices" into "fails".
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from trappoint_recall.lexical.porter import PORTER_VERSION, stem
from trappoint_recall.lexical.stopwords import (
    STOPWORD_LIST_VERSION,
    STOPWORDS,
    is_stopword,
)
from trappoint_recall.lexical.units import (
    UNIT_PATTERN,
    UNIT_TABLE_VERSION,
    bare_unit_symbol,
    canonical_quantity,
    unit_key_for_match,
    unit_table_digest_material,
)

__all__ = [
    "ANALYSER_VERSION",
    "IDENTIFIER_CLASSES",
    "TERM_CHARSET",
    "Token",
    "TokenClass",
    "analyse",
    "analyse_query",
    "is_well_formed_term",
    "rule_fingerprint",
]

#: Bump on ANY behavioural change.  The number after the slash is the posting-format
#: generation: two analysers with different generations must not share a ``lex_posting``.
ANALYSER_VERSION: Final[str] = "trappoint-lex-analyser/1"


class TokenClass(StrEnum):
    """What kind of thing a token is — decided by the analyser, never by the writer."""

    IDENTIFIER = "identifier"
    QUANTITY = "quantity"
    CITATION = "citation"
    CAS = "cas"
    PROSE = "prose"


#: The classes that are case-folded but **never** stemmed and never stopped.
IDENTIFIER_CLASSES: Final[frozenset[TokenClass]] = frozenset(
    {TokenClass.IDENTIFIER, TokenClass.QUANTITY, TokenClass.CITATION, TokenClass.CAS}
)


@dataclass(frozen=True, slots=True)
class Token:
    """One emitted term, with its class and its provenance in the normalised text."""

    text: str
    token_class: TokenClass
    position: int
    start: int
    end: int


# ── normalisation ────────────────────────────────────────────────────────────────────────────

#: Applied before anything else.  Every one of these is a character that appears in real
#: incident text and would otherwise fragment an identifier.
_CHAR_MAP: Final[dict[int, str]] = {
    0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2014: "-", 0x2015: "-",
    0x2212: "-",           # minus sign
    0x00AD: "",            # soft hyphen
    0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"',
    0x00B2: "2", 0x00B3: "3",   # superscript 2/3 → m2 / m3
    0x00B5: "u", 0x03BC: "u",   # micro sign and greek mu → u
    0x00A0: " ", 0x2007: " ", 0x202F: " ",
    0x2044: "/",           # fraction slash
}


def normalise(text: str) -> str:
    """NFKC, hazard-safe character folding, case folding.

    ``str.casefold`` and not ``str.lower``: an analyser that treats ``ẞ`` and ``ss``
    differently on two sides of the same query is an analyser with a silent recall hole.
    """
    folded = unicodedata.normalize("NFKC", text).translate(_CHAR_MAP)
    return folded.casefold()


# ── the scanner rules, in priority order ─────────────────────────────────────────────────────

#: ``29 CFR 1910.146``, ``30 C.F.R. 57.22239``.
_RE_CFR = re.compile(r"(\d{1,2})\s*c\.?\s*f\.?\s*r\.?\s*(?:part\s*)?(\d+(?:\.\d+)*)")

#: ``§ 57.22239``, ``sec. 57.22239``.
_RE_SECTION = re.compile(r"(?:§|sec\.|section)\s*(\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)")

#: ``AS/NZS 3000``, ``AS 2865-2009``, ``NZS 4541``.
#:
#: Known, bounded imprecision: the analyser has already case-folded, so the bare ``AS`` form
#: cannot be distinguished from the English word, and "as 2011 required" yields the term
#: ``as:2011``.  It is left in deliberately.  The term is produced identically on the document
#: and the query side, and its document frequency in a corpus full of years drives its IDF to
#: nearly zero — so it costs a posting row and changes no ranking.  Suppressing it would need
#: original-case text, which NFKC + casefold does not preserve length-wise, and a
#: length-unsafe offset map is a worse defect than a near-zero-IDF term.
_RE_ASNZS = re.compile(r"\b(as/nzs|as|nzs)\s*[- ]?\s*(\d{4,5}(?:\.\d+)*)(?:[:\-]\d{4})?")

#: ``ISO 45001``, ``API RP 754``, ``ASME B31.3``, ``NFPA 70E``, ``IEC 61511-1``.
_RE_BODY = re.compile(
    r"\b(iso|iec|api|asme|ansi|nfpa|astm|ieee|en)\s*(?:rp|std)?\s*[- ]?\s*"
    r"([a-z]?\d{2,5}(?:[.-]\d+)*[a-z]?)"
)

#: ``WHS Regulation 2011 r 341``, ``WHS Reg r341``.
_RE_WHS = re.compile(r"\bwhs\s+reg(?:ulation)?s?\s*(?:\d{4})?\s*r\.?\s*(\d+[a-z]?)")

#: CAS registry number shape.  The checksum is what makes this a CAS number rather than a
#: hyphenated identifier, and a failed checksum falls through to the identifier rule.
_RE_CAS = re.compile(r"\b(\d{2,7})-(\d{2})-(\d)\b")

#: A signed decimal or scientific-notation number.
_RE_NUMBER = re.compile(r"[+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?")

#: A generic token: alphanumerics joined by the separators that appear inside plant tags.
#: Trailing separators are excluded so that "K-401." does not become "k-401.".
_RE_WORD = re.compile(r"[a-z0-9]+(?:[-/_.][a-z0-9]+)*")

#: Terms are constrained to this shape so that the literal renderer used by the Managed-MCP
#: audit surface has a decidable safety argument rather than a hopeful one.
TERM_CHARSET: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9:._/+-]*$")

_MIN_COMPONENT_LEN: Final[int] = 2


def is_well_formed_term(term: str) -> bool:
    """True when a term is safe to render as a SQL literal and to store as a posting key."""
    return bool(term) and len(term) <= 128 and TERM_CHARSET.match(term) is not None


def _cas_checksum_ok(body: str, check: str) -> bool:
    """CAS check digit: sum of position-weighted digits, read right to left, mod 10."""
    digits = body[::-1]
    total = sum((i + 1) * int(d) for i, d in enumerate(digits))
    return total % 10 == int(check)


# ── the scanner ──────────────────────────────────────────────────────────────────────────────


class _Emitter:
    """Accumulates tokens, filters malformed ones, and keeps positions monotone."""

    __slots__ = ("tokens",)

    def __init__(self) -> None:
        self.tokens: list[Token] = []

    def emit(self, text: str, cls: TokenClass, start: int, end: int) -> None:
        if not is_well_formed_term(text):
            return
        self.tokens.append(Token(text, cls, len(self.tokens), start, end))


def _emit_identifier(out: _Emitter, surface: str, start: int, end: int) -> None:
    """Whole token first, then its components — split on separators only.

    ``K-401`` → ``k-401``, ``401``.  ``TK-12`` → ``tk-12``, ``tk``, ``12``.  ``H2S`` → ``h2s``
    and nothing else, because there is no separator to split on and ``h``/``2``/``s`` are not
    evidence of anything.  Single-character tokens are dropped, whole or component: their
    document frequency approaches N, so their IDF approaches zero and they cost a posting row
    for no signal.  ("Only 3 of the 5 detectors" should not put ``3`` and ``5`` in the index;
    a dimension symbol like ``k`` for kelvin is emitted by the quantity rule, not here, and is
    therefore unaffected.)
    """
    if len(surface) >= _MIN_COMPONENT_LEN:
        out.emit(surface, TokenClass.IDENTIFIER, start, end)
    parts = re.split(r"[-/_.]", surface)
    if len(parts) < 2:
        return
    seen: set[str] = {surface}
    for part in parts:
        if len(part) < _MIN_COMPONENT_LEN or part in seen:
            continue
        seen.add(part)
        out.emit(part, TokenClass.IDENTIFIER, start, end)
        # `TK-012` and `TK-12` are the same vessel written twice.  Emitting the zero-stripped
        # component on BOTH sides (this analyser runs on documents and queries alike) makes
        # them meet without making anything else meet.  The length rule applies here too, so
        # `CC-07` and `CC-7` meet on `cc` and not on `7`: a one-character term is noise
        # wherever it comes from, and a rule that held everywhere except in one branch is a
        # rule nobody can reason about.
        if part.isdigit():
            stripped = part.lstrip("0")
            if (
                len(stripped) >= _MIN_COMPONENT_LEN
                and stripped != part
                and stripped not in seen
            ):
                seen.add(stripped)
                out.emit(stripped, TokenClass.IDENTIFIER, start, end)


def _sanitise_designator(raw: str) -> str:
    """``57.22239(a)`` → ``57.22239.a``.  Parentheses are not in :data:`TERM_CHARSET`."""
    return re.sub(r"[()]", ".", raw).strip(".")


def _render_cfr(m: re.Match[str]) -> str:
    return f"cfr:{m.group(1)}:{_sanitise_designator(m.group(2))}"


def _render_section(m: re.Match[str]) -> str:
    return "sec:" + _sanitise_designator(m.group(1))


def _render_asnzs(m: re.Match[str]) -> str:
    return f"{m.group(1).replace('/', '')}:{_sanitise_designator(m.group(2))}"


def _render_body(m: re.Match[str]) -> str:
    return f"{m.group(1)}:{_sanitise_designator(m.group(2))}"


def _render_whs(m: re.Match[str]) -> str:
    return f"whsreg:{_sanitise_designator(m.group(1))}"


#: ``(pattern, renderer, designator group)``.  Order is priority order; the first match at a
#: position wins and consumes the whole citation, which is what keeps ``30 CFR 57.22239``
#: from being read as the quantity ``30`` followed by the identifier ``57.22239``.
_CITATION_RULES: Final[
    tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], str], int], ...]
] = (
    (_RE_CFR, _render_cfr, 2),
    (_RE_WHS, _render_whs, 1),
    (_RE_SECTION, _render_section, 1),
    (_RE_ASNZS, _render_asnzs, 2),
    (_RE_BODY, _render_body, 2),
)


def _try_citation(text: str, pos: int, out: _Emitter) -> int:
    for pattern, render, designator_group in _CITATION_RULES:
        m = pattern.match(text, pos)
        if m is None:
            continue
        out.emit(render(m), TokenClass.CITATION, m.start(), m.end())
        # The bare designator is emitted as an identifier so that a permit citing
        # "57.22239" without the title still meets the incident that cites the full rule.
        designator = _sanitise_designator(m.group(designator_group) or "")
        if designator:
            out.emit(designator, TokenClass.IDENTIFIER, m.start(), m.end())
        return m.end()
    return -1


def _try_cas(text: str, pos: int, out: _Emitter) -> int:
    m = _RE_CAS.match(text, pos)
    if m is None:
        return -1
    if not _cas_checksum_ok(m.group(1) + m.group(2), m.group(3)):
        return -1  # not a CAS number; the identifier rule will take it whole
    out.emit(f"cas:{m.group(1)}-{m.group(2)}-{m.group(3)}", TokenClass.CAS, m.start(), m.end())
    return m.end()


def _try_quantity(text: str, pos: int, out: _Emitter) -> int:
    num = _RE_NUMBER.match(text, pos)
    if num is None:
        return -1
    after = num.end()
    while after < len(text) and text[after] == " ":
        after += 1
    unit = UNIT_PATTERN.match(text, after)
    if unit is None:
        return -1
    key = unit_key_for_match(unit)
    try:
        value = float(num.group(0))
    except ValueError:  # pragma: no cover - _RE_NUMBER cannot produce this
        return -1
    term, symbol = canonical_quantity(value, key)
    out.emit(term, TokenClass.QUANTITY, num.start(), unit.end())
    out.emit(symbol, TokenClass.IDENTIFIER, num.start(), unit.end())
    return unit.end()


def _classify_word(surface: str, start: int, end: int, out: _Emitter) -> None:
    bare = bare_unit_symbol(surface)
    if bare is not None:
        out.emit(bare, TokenClass.IDENTIFIER, start, end)
        return
    has_alpha = any(c.isalpha() for c in surface)
    has_digit = any(c.isdigit() for c in surface)
    if has_digit:
        # Anything carrying a digit is identifier-class: a pure number may be a unit number
        # ("pump 401"), a year, or a setpoint, and none of those survive stemming.
        _emit_identifier(out, surface, start, end)
        return
    if not has_alpha:  # pragma: no cover - _RE_WORD cannot match this
        return
    if "-" in surface or "/" in surface or "_" in surface or "." in surface:
        # `lock-out`, `pre-start`: the hyphenated whole is kept as an identifier (it is a
        # term of art) AND each part is stemmed as prose, so `lockout` still meets it via
        # the prose side once the writer's text says `lock out`.
        out.emit(surface, TokenClass.IDENTIFIER, start, end)
        for part in re.split(r"[-/_.]", surface):
            _emit_prose(part, start, end, out)
        return
    _emit_prose(surface, start, end, out)


def _emit_prose(surface: str, start: int, end: int, out: _Emitter) -> None:
    if len(surface) < _MIN_COMPONENT_LEN or is_stopword(surface):
        return
    out.emit(stem(surface), TokenClass.PROSE, start, end)


def _scan(text: str) -> Iterator[Token]:
    out = _Emitter()
    pos = 0
    length = len(text)
    while pos < length:
        ch = text[pos]
        if not (ch.isalnum() or ch in "%§°+-"):
            pos += 1
            continue
        end = _try_citation(text, pos, out)
        if end > pos:
            pos = end
            continue
        end = _try_cas(text, pos, out)
        if end > pos:
            pos = end
            continue
        end = _try_quantity(text, pos, out)
        if end > pos:
            pos = end
            continue
        word = _RE_WORD.match(text, pos)
        if word is None:
            pos += 1
            continue
        _classify_word(word.group(0), word.start(), word.end(), out)
        pos = word.end()
    return iter(out.tokens)


def analyse(text: str) -> list[Token]:
    """Analyse a document or a query.  The **same** function on both sides, always.

    Genre symmetry is not a nicety here: if the document side splits ``K-401`` and the query
    side does not, the channel that exists to find ``K-401`` cannot find ``K-401``.
    """
    return list(_scan(normalise(text)))


@dataclass(frozen=True, slots=True)
class QueryTerms:
    """Deduplicated query terms with weights, plus the classes they came from."""

    weights: Mapping[str, float]
    classes: Mapping[str, TokenClass]

    @property
    def terms(self) -> tuple[str, ...]:
        return tuple(sorted(self.weights))


def analyse_query(
    text: str,
    *,
    class_weights: Mapping[TokenClass, float] | None = None,
) -> QueryTerms:
    """Analyse query text into deduplicated terms.

    Query-term frequency is **not** carried into the score by default (``k3 = 0``, which is
    what Lucene's ``BM25Similarity`` does): saying ``K-401`` twice in a permit description is
    not twice the evidence.  ``class_weights`` is the supported way to make identifier
    evidence outweigh prose evidence, and it is a *query-side* weight, so it composes with
    whatever the document side puts in ``lex_posting.weight``.
    """
    tokens = analyse(text)
    classes: dict[str, TokenClass] = {}
    for token in tokens:
        # First class wins: identifier rules run before prose rules, so a term that was ever
        # produced as an identifier is recorded as one.
        classes.setdefault(token.text, token.token_class)
    if class_weights is None:
        weights = {term: 1.0 for term in classes}
    else:
        weights = {
            term: float(class_weights.get(cls, 1.0)) for term, cls in classes.items()
        }
    return QueryTerms(weights=weights, classes=classes)


def term_frequencies(tokens: Sequence[Token]) -> Counter[str]:
    """Raw term frequency over an analysed token stream."""
    return Counter(token.text for token in tokens)


# ── versioning ───────────────────────────────────────────────────────────────────────────────


def rule_fingerprint_material() -> list[str]:
    """Every input to the analyser's behaviour that is *data* rather than code.

    Code changes are caught by the golden-corpus digest.  This catches the tables, which are
    the things people edit without thinking of them as behaviour.
    """
    material = [
        ANALYSER_VERSION,
        PORTER_VERSION,
        STOPWORD_LIST_VERSION,
        UNIT_TABLE_VERSION,
        f"min_component_len={_MIN_COMPONENT_LEN}",
        f"charset={TERM_CHARSET.pattern}",
        f"word={_RE_WORD.pattern}",
        f"number={_RE_NUMBER.pattern}",
        f"cas={_RE_CAS.pattern}",
    ]
    material.extend(f"stop:{w}" for w in sorted(STOPWORDS))
    material.extend(f"unit:{entry}" for entry in unit_table_digest_material())
    material.extend(
        f"cite:{pattern.pattern}->{render.__name__}:{group}"
        for pattern, render, group in _CITATION_RULES
    )
    material.extend(f"charmap:{k:04x}->{v}" for k, v in sorted(_CHAR_MAP.items()))
    return material


def rule_fingerprint() -> str:
    """sha256 over :func:`rule_fingerprint_material`, hex."""
    digest = hashlib.sha256()
    for line in rule_fingerprint_material():
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
