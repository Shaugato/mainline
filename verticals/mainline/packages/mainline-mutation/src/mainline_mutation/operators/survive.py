# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""SURVIVE operators — identity-preserving reformats the pipeline must ignore.

Eleven of the twelve classes are expected to leave ``canon_sha256`` **byte
identical**, and that is not an accident of the fixtures: it is CANONHOLD's
specification.  Furniture stripping, NFKC folding, de-hyphenation, whitespace
collapse, numeric confusable repair and numbering excision are exactly the six
things this catalogue exercises, one class per mechanism, so a regression in any
one of them shows up as a named class going red rather than as an aggregate
drifting.

The twelfth — ``cross_reference_renumbering`` — genuinely changes the text, and
it is the only one that tests the MATCHER rather than the canonicaliser.  It is
kept separate for that reason; folding it in with the other eleven would let a
matcher regression hide behind eleven digest equalities.

WHY A FALSE POSITIVE IS A PRODUCT DEFECT AND NOT A SAFE ERROR
--------------------------------------------------------------
It is tempting to argue that a reformat wrongly flagged as a weakening is the
harmless direction.  It is not.  ``docs/leads/algorithms.md`` §8 R-A7 puts a
nuisance ceiling on the whole design, and a rule that breaches it is **rejected,
not tuned** — because a gate that blocks on retypesetting is a gate that gets
switched off, and a gate that is off refuses nothing at all.
"""

from __future__ import annotations

import random
import re
from typing import Final

from ..errors import OperatorInapplicable
from ..model import MutationApplication, Operator, Revision
from ._text import hyphenate_at

__all__ = ["SURVIVE_OPERATORS"]


# --------------------------------------------------------------------------- #
# Typography.  Every substitution is one NFKC (or fold.py) folds back.          #
# --------------------------------------------------------------------------- #

# RUF001 fires on all four of these and every hit is the POINT of the class.
# `retypeset` measures whether NFKC folding puts a ligature, a curly quote, an en
# dash and a non-breaking space back; a table that avoided "ambiguous" characters
# would be a table that tested nothing.
_TYPOGRAPHY: Final[tuple[tuple[str, str], ...]] = (
    ("fi", "ﬁ"),  # LATIN SMALL LIGATURE FI
    ("fl", "ﬂ"),  # LATIN SMALL LIGATURE FL
    ("'", "’"),  # noqa: RUF001 - RIGHT SINGLE QUOTATION MARK
    (" - ", " – "),  # noqa: RUF001 - EN DASH
)

#: The non-breaking space a typesetter puts between a magnitude and its unit.
_NBSP: Final[str] = " "  # noqa: RUF001 - NO-BREAK SPACE, and that is the point

#: OCR confusables, restricted to the substitutions ``canon/ocr.py`` repairs
#: INSIDE numeric token classes.  A confusable applied to prose would be a real
#: text change wearing the name of a scanning artefact.
_OCR_CONFUSABLES: Final[tuple[tuple[str, str], ...]] = (
    ("0", "O"),
    ("1", "l"),
    ("5", "S"),
)

#: DIGIT-LED ONLY, and the restriction is a measured one. `canon/numbering.py`
#: excises a numbering prefix that begins with a digit; `A.2.7` and `II.4` are
#: NOT excised and survive into `canon_text`. Using one here would make these two
#: classes measure the matcher while carrying the canonicaliser's name, and would
#: duplicate what `appendix_relocation` already exercises deliberately.
_RENUMBERINGS: Final[tuple[str, ...]] = ("12.4(b)", "3.11", "18.1.4", "2.9(a)")
_HEADING_LEVELS: Final[tuple[str, ...]] = ("7.3.2.1", "7.3", "10.1.4", "4.2.6")

#: Every line here MUST match one of ``canon/furniture.py``'s unconditional
#: patterns, or the migration would smuggle a text change into a class that
#: claims to change only the page around the clause.  A running header that
#: survived canonicalisation would make this class measure the matcher while
#: reporting the canonicaliser's name.
_NEW_TEMPLATE: Final[tuple[str, ...]] = (
    "Doc No: DMS-2026-4471",
    "Rev. 7 - 04 Aug 2026",
    "Uncontrolled when printed",
)
_SPLIT_FURNITURE: Final[tuple[str, ...]] = ("Doc No: SPLIT-0002", "Page 1 of 3")
_MERGE_FURNITURE: Final[tuple[str, ...]] = ("Doc No: MERGED-0001", "Page 44 of 96")
_APPENDIX_FURNITURE: Final[tuple[str, ...]] = ("Doc No: ISO-0221 Appendix C", "Page 62 of 96")

_WORD = re.compile(r"\b[a-z]{6,}\b", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")

_MIN_WRAP_WORDS: Final[int] = 7


def retypeset(revision: Revision, rng: random.Random) -> MutationApplication:
    """Ligatures, curly quotes, en dashes and non-breaking spaces.  NFKC folds them all."""
    del rng
    body = revision.raw_text
    applied: list[str] = []
    for plain, fancy in _TYPOGRAPHY:
        if plain in body:
            body = body.replace(plain, fancy, 1)
            applied.append(f"{plain!r}->{fancy!r}")
    body = body.replace(" kPa", f"{_NBSP}kPa").replace(" %", f"{_NBSP}%")
    if body == revision.raw_text:
        raise OperatorInapplicable(
            f"{revision.fixture_id} carries no character this typesetter would change"
        )
    applied.append("thin/non-breaking space before the unit")
    return MutationApplication(
        descendant_document=revision.document(text=body),
        note="; ".join(applied),
    )


def renumber(revision: Revision, rng: random.Random) -> MutationApplication:
    """A section was inserted above; the clause's printed label moves and nothing else."""
    index = rng.randrange(len(_RENUMBERINGS))
    replacement = _RENUMBERINGS[index]
    if replacement == revision.numbering_prefix:
        replacement = _RENUMBERINGS[(index + 1) % len(_RENUMBERINGS)]
    return MutationApplication(
        descendant_document=revision.document(prefix=replacement),
        note=f"numbering prefix {revision.numbering_prefix or '(none)'!r} -> {replacement!r}",
    )


def reflow_rewrap(revision: Revision, rng: random.Random) -> MutationApplication:
    """A narrower column: every line rewraps and one word hyphenates across the break."""
    words = revision.raw_text.split(" ")
    if len(words) < _MIN_WRAP_WORDS:
        raise OperatorInapplicable(f"{revision.fixture_id} is too short to rewrap")
    width = rng.randrange(4, 9)
    lines: list[str] = []
    for start in range(0, len(words), width):
        lines.append(" ".join(words[start : start + width]))
    body = "\n".join(lines)
    long_words = list(_WORD.finditer(body))
    if long_words:
        target = long_words[rng.randrange(len(long_words))]
        word = target.group(0)
        body = body[: target.start()] + hyphenate_at(word, len(word) // 2) + body[target.end() :]
    return MutationApplication(
        descendant_document=revision.document(text=body),
        note=f"rewrapped at {width} words per line with one hyphenated break",
    )


def document_split(revision: Revision, rng: random.Random) -> MutationApplication:
    """The procedure was split in two; the clause keeps its text and gains new furniture."""
    del rng
    return MutationApplication(
        descendant_document="\n".join(
            [*_SPLIT_FURNITURE, f"{revision.numbering_prefix} {revision.raw_text}".strip()]
        ),
        note=f"furniture {list(revision.furniture_lines)} -> {list(_SPLIT_FURNITURE)}",
    )


def document_merge(revision: Revision, rng: random.Random) -> MutationApplication:
    """Two procedures became one; the clause sits under the merged document's furniture."""
    del rng
    return MutationApplication(
        descendant_document="\n".join(
            [*_MERGE_FURNITURE, f"{revision.numbering_prefix} {revision.raw_text}".strip()]
        ),
        note=f"furniture {list(revision.furniture_lines)} -> {list(_MERGE_FURNITURE)}",
    )


def ocr_noise(revision: Revision, rng: random.Random) -> MutationApplication:
    """A scanned reissue: ``4O0`` for ``400``, ``19.S`` for ``19.5``.  Inside numbers only.

    Two constraints, and both of them are the difference between measuring
    CANONHOLD and measuring this operator.

    **The corrupted character is never the leading one.**  ``canon/ocr.py``
    documents that a numeric literal must BEGIN with a digit for the repair to
    fire, so that ``SO2``, ``Oil`` and ``IS0`` are out of reach.  Corrupting a
    leading character would exercise a limit the canonicaliser declares rather
    than a claim it makes, and would report a deliberate design decision as a
    false positive.  Fixtures whose magnitudes have no repairable non-leading
    position (``5``, ``12``) are SKIPPED with that reason on the record.

    **Only the declared setpoint magnitude is touched.**  Corrupting an
    arbitrary numeric token would corrupt the digits inside an equipment tag —
    ``V-3l1`` for ``V-311`` — which ``ocr.py`` also documents as unrepairable
    ("a damaged anchor is better reported as an anchor drop than silently
    reconstructed").  That is a real and important behaviour and it belongs to
    the KILL catalogue's anchor class, not to a reformatting class.
    """
    del rng
    token = revision.setpoint_value
    if not token:
        raise OperatorInapplicable(
            f"{revision.fixture_id} declares no setpoint magnitude; the only numeric tokens in "
            "its text are inside anchors, and canon/ocr.py documents that damage there is "
            "deliberately NOT repaired"
        )
    corrupted: str | None = None
    for position in range(1, len(token)):
        for digit, confusable in _OCR_CONFUSABLES:
            if token[position] == digit:
                corrupted = token[:position] + confusable + token[position + 1 :]
                break
        if corrupted is not None:
            break
    if corrupted is None:
        raise OperatorInapplicable(
            f"the magnitude {token!r} in {revision.fixture_id} has no confusable character "
            "outside its leading position; canon/ocr.py documents that leading-character damage "
            "is deliberately not repaired, so corrupting it would measure a stated design "
            "decision rather than a claim"
        )
    body = revision.raw_text.replace(token, corrupted, 1)
    return MutationApplication(
        descendant_document=revision.document(text=body),
        note=f"magnitude {token!r} scanned as {corrupted!r}",
    )


def table_to_prose(revision: Revision, rng: random.Random) -> MutationApplication:
    """A limits table row rewritten as a sentence.  The control is identical.

    Applies only to fixtures that ARE a pipe-delimited row, because the mutation
    this class names has a direction: a clause the extractor could not read
    becoming one it can.  Running it backwards would be a different measurement
    (prose becoming opaque), and that is a KILL-shaped mutation, not a SURVIVE one.
    """
    del rng
    cells = [cell.strip() for cell in revision.raw_text.strip().strip("|").split("|")]
    cells = [cell for cell in cells if cell]
    if len(cells) < len(("subject", "parameter", "limit")):
        raise OperatorInapplicable(f"{revision.fixture_id} is not a table row")
    subject, parameter, limit, *rest = cells
    tail = f", and the reading shall be {rest[0]}" if rest else ""
    body = (
        f"The {parameter[0].lower()}{parameter[1:]} of {subject} must not exceed {limit}{tail}."
    )
    return MutationApplication(
        descendant_document=revision.document(text=body),
        note=f"table row {cells} reformatted as one sentence",
    )


def heading_level_change(revision: Revision, rng: random.Random) -> MutationApplication:
    """The clause is promoted or demoted a level.  Its label changes; its content does not."""
    index = rng.randrange(len(_HEADING_LEVELS))
    replacement = _HEADING_LEVELS[index]
    if replacement == revision.numbering_prefix:
        replacement = _HEADING_LEVELS[(index + 1) % len(_HEADING_LEVELS)]
    return MutationApplication(
        descendant_document=revision.document(prefix=replacement),
        note=f"heading level {revision.numbering_prefix or '(none)'!r} -> {replacement!r}",
    )


def whitespace_punctuation_churn(revision: Revision, rng: random.Random) -> MutationApplication:
    """Double spaces, trailing whitespace, a stray tab: four editors, one document."""
    body = revision.raw_text.replace(". ", ".  ")
    words = body.split(" ")
    if len(words) > _MIN_WRAP_WORDS:
        at = rng.randrange(1, len(words) - 1)
        words[at] = words[at] + " "
    body = " ".join(words) + "  \t "
    return MutationApplication(
        descendant_document=revision.document(text=body),
        note="doubled inter-sentence spacing, one interior double space, trailing tab",
    )


def template_migration(revision: Revision, rng: random.Random) -> MutationApplication:
    """A new document management system stamps every page differently."""
    del rng
    return MutationApplication(
        descendant_document="\n".join(
            [*_NEW_TEMPLATE, f"{revision.numbering_prefix} {revision.raw_text}".strip()]
        ),
        note=f"furniture {list(revision.furniture_lines)} -> {list(_NEW_TEMPLATE)}",
    )


def appendix_relocation(revision: Revision, rng: random.Random) -> MutationApplication:
    """The clause moves into Appendix C, taking a new scheme and a new header with it."""
    del rng
    return MutationApplication(
        descendant_document="\n".join([*_APPENDIX_FURNITURE, f"C.1.4 {revision.raw_text}"]),
        note="relocated to Appendix C with appendix numbering and a running header",
    )


_CROSS_REFERENCES: Final[tuple[tuple[str, str], ...]] = (
    ("as set out in clause 4.2", "as set out in clause 9.1"),
    ("see clause 4.2", "see clause 9.1"),
)


def cross_reference_renumbering(revision: Revision, rng: random.Random) -> MutationApplication:
    """A cited clause moved, so the citation's number moved.  The control did not.

    The ONE survive class that genuinely changes ``canon_text``, and therefore
    the one that measures the matcher rather than the canonicaliser.  The
    reference is appended to the fixture rather than assumed present, because a
    class that silently skipped every fixture without one would report a kill
    rate over an empty set.
    """
    del rng
    before, after = _CROSS_REFERENCES[0]
    stripped = revision.raw_text.rstrip()
    ancestor_body = (
        f"{stripped[:-1]}, {before}." if stripped.endswith(".") else f"{stripped}, {before}."
    )
    descendant_body = ancestor_body.replace(before, after)
    return MutationApplication(
        descendant_document=revision.document(text=descendant_body),
        note=(
            f"the ancestor is the fixture carrying {before!r}; the descendant carries "
            f"{after!r} and nothing else changed"
        ),
    )


#: ``cross_reference_renumbering`` is the one operator whose ANCESTOR is not the
#: bare fixture: the cited clause has to exist before it can be renumbered. The
#: runner consults this map so the comparison is reference-vs-descendant and not
#: fixture-vs-descendant, which would make a legitimate addition look like a
#: change of identity.
ANCESTOR_OVERRIDES: Final[dict[str, str]] = {
    "cross_reference_renumbering": _CROSS_REFERENCES[0][0],
}


def ancestor_document(revision: Revision, class_id: str) -> str:
    """The document this class's mutant is compared against.

    Identical to ``revision.document()`` for every class but one; see
    :data:`ANCESTOR_OVERRIDES`.
    """
    phrase = ANCESTOR_OVERRIDES.get(class_id)
    if phrase is None:
        return revision.document()
    stripped = revision.raw_text.rstrip()
    body = f"{stripped[:-1]}, {phrase}." if stripped.endswith(".") else f"{stripped}, {phrase}."
    return revision.document(text=body)


SURVIVE_OPERATORS: Final[dict[str, Operator]] = {
    "retypeset": retypeset,
    "renumber": renumber,
    "reflow_rewrap": reflow_rewrap,
    "document_split": document_split,
    "document_merge": document_merge,
    "ocr_noise": ocr_noise,
    "table_to_prose": table_to_prose,
    "heading_level_change": heading_level_change,
    "whitespace_punctuation_churn": whitespace_punctuation_churn,
    "template_migration": template_migration,
    "appendix_relocation": appendix_relocation,
    "cross_reference_renumbering": cross_reference_renumbering,
}
