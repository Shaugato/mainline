# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The clause text of a registry entry, and how to read it back.

A registry entry is a clause, so its authoritative form is *text* — the same
``canon_text`` every other clause carries, subject to the same canonicalisation,
the same digest and the same blame edges.  This module fixes the one-line
grammar that makes that text machine-readable without giving up being
human-readable::

    SAFE-DIRECTION REGISTRY ENTRY. Parameter: max_operating_pressure.
    Dimension: pressure. Direction: LOWER_IS_SAFER. Status: RATIFIED.
    Rationale: <prose to the end of the clause>

(one line in the document; wrapped here only to fit this docstring).

THREE PROPERTIES THE GRAMMAR HAS TO HAVE, AND WHY
-------------------------------------------------
**Canon-stable.**  ``canonicalise(encode(entry)).canon_text == encode(entry)``,
asserted by test.  If canonicalisation moved a byte of this text, the digest
stored on the clause would not be the digest of the text this module wrote, and
every downstream identity claim about the registry document would be built on a
mismatch.  The concrete traps are all avoided by construction: the line starts
with a letter, so :func:`~mainline_domain.canon.numbering.excise_numbering`
finds no numbering prefix to strip; every character is ASCII, so NFKC folding is
a no-op; there are no double spaces, so whitespace collapse is a no-op; and no
token starts with a digit, so numeric OCR repair cannot reach it.

**Total on its own output and partial on everything else.**  The decoder matches
the whole string or fails.  There is no lenient mode.  A clause in the registry
document that does not match this grammar is not a registry entry that needs
interpreting — it is a clause somebody edited into a shape this system cannot
read, and the loader turns it into an abstention rather than a best guess.

**Unable to express an abstention.**  ``SafeDirection.ABSTAIN`` is refused by
:func:`encode`.  ``ABSTAIN`` is what the *system* answers when it has no ratified
entry; a clause that declared it would be a signed statement that a parameter is
permanently unanswerable, which is not a thing anyone should be able to ratify
and which would be indistinguishable, downstream, from the coverage gap it was
hiding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from ..quantity.errors import UnknownUnitError
from ..quantity.units import dimensionality_for_label
from .errors import RegistryEncodingError
from .model import RATIFIABLE_DIRECTIONS, EntryStatus, SafeDirection

__all__ = [
    "ENCODING_VERSION",
    "PREAMBLE",
    "DecodedEntry",
    "decode",
    "encode",
]

#: Bump this when the grammar changes.  Like ``canon_version``, a bump is a
#: migration and not a flag: every registry clause in every commit was written
#: under some version of this grammar, and a decoder that silently accepted two
#: would make "what did the registry say in March" unanswerable.
ENCODING_VERSION: Final[int] = 1

PREAMBLE: Final[str] = "SAFE-DIRECTION REGISTRY ENTRY."

#: Parameter keys are lowercase snake_case.  Enforced, not merely expected: the
#: key is the join between a clause in a procedure and a clause in the registry,
#: and ``Max_Operating_Pressure`` failing to match ``max_operating_pressure``
#: would present as an unknown parameter — an abstention, so a ``weaken``, so a
#: blocking check on a permit that had nothing wrong with it.
_PARAMETER_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{2,62}$")

_CLAUSE_RE: Final[re.Pattern[str]] = re.compile(
    r"^SAFE-DIRECTION REGISTRY ENTRY\."
    r" Parameter: (?P<parameter>[a-z][a-z0-9_]{2,62})\."
    r" Dimension: (?P<dimension>[a-z][a-z0-9_]{1,40})\."
    r" Direction: (?P<direction>[A-Z][A-Z_]{2,60})\."
    r" Status: (?P<status>[A-Z]{3,20})\."
    r" Rationale: (?P<rationale>\S.*)$"
)

#: Characters the rationale may not contain.  ``.`` followed by a space is
#: allowed *inside* the rationale because it is the last field and runs to the
#: end of the clause, but the field separators before it are literal, so nothing
#: in a rationale can forge one.
_RATIONALE_FORBIDDEN: Final[re.Pattern[str]] = re.compile(r"[\r\n\t]|  +")


@dataclass(frozen=True, slots=True)
class DecodedEntry:
    """The fields carried by one registry clause, before any row context.

    Deliberately *not* a :class:`~mainline_domain.registry.model.RegistryEntry`:
    that type additionally carries the clause row, the commit and the signature
    state, none of which the text can assert about itself.  Keeping them apart
    means the text can never claim to have been ratified by somebody.
    """

    parameter: str
    dimension_label: str
    dimensionality: str
    direction: SafeDirection
    status: EntryStatus
    rationale: str


def encode(
    *,
    parameter: str,
    dimension_label: str,
    direction: SafeDirection,
    status: EntryStatus,
    rationale: str,
) -> str:
    """Render one registry entry as clause text.

    :raises RegistryEncodingError: on anything that would not decode back — an
        unratifiable direction, a malformed key, an unknown dimension label, a
        rationale carrying a character the grammar cannot survive.
    """
    if direction not in RATIFIABLE_DIRECTIONS:
        raise RegistryEncodingError(
            f"{direction.value} cannot be written to a clause: ABSTAIN is what the "
            "registry answers when no entry applies, not something a signature can "
            "assert about a parameter"
        )
    if not _PARAMETER_RE.match(parameter):
        raise RegistryEncodingError(
            f"{parameter!r} is not a valid parameter key (lowercase snake_case, 3-63 chars)"
        )
    try:
        dimensionality = dimensionality_for_label(dimension_label)
    except UnknownUnitError as exc:
        raise RegistryEncodingError(str(exc)) from exc
    _ = dimensionality

    rationale = rationale.strip()
    if not rationale:
        raise RegistryEncodingError(
            f"{parameter!r} has no rationale. A direction with no stated reason is a "
            "number somebody typed; the rationale is what a later reader disagrees with"
        )
    if _RATIONALE_FORBIDDEN.search(rationale):
        raise RegistryEncodingError(
            f"{parameter!r}: the rationale contains a tab, newline or run of spaces, "
            "which canonicalisation would collapse — the clause would then not be the "
            "text this encoder emitted"
        )

    text = (
        f"{PREAMBLE}"
        f" Parameter: {parameter}."
        f" Dimension: {dimension_label}."
        f" Direction: {direction.value}."
        f" Status: {status.value}."
        f" Rationale: {rationale}"
    )

    # Encode-then-decode, always.  It costs a regex match per entry and it makes
    # "the seeder wrote a clause the loader cannot read" impossible rather than
    # unlikely — the failure mode it forecloses is a registry that looks
    # populated and abstains on everything.
    decode(text)
    return text


def decode(canon_text: str) -> DecodedEntry:
    """Read one registry clause.

    :raises RegistryEncodingError: if the text is not exactly one entry in the
        grammar.  Callers in the loader convert this into an abstention with
        reason ``malformed_clause``; nothing converts it into a guess.
    """
    match = _CLAUSE_RE.match(canon_text)
    if match is None:
        raise RegistryEncodingError(
            "clause is not a safe-direction registry entry under encoding version "
            f"{ENCODING_VERSION}: {canon_text[:160]!r}"
        )

    raw_direction = match.group("direction")
    try:
        direction = SafeDirection(raw_direction)
    except ValueError:
        raise RegistryEncodingError(
            f"{raw_direction!r} is not a safe direction; ratifiable values are "
            + ", ".join(sorted(d.value for d in RATIFIABLE_DIRECTIONS))
        ) from None
    if direction not in RATIFIABLE_DIRECTIONS:
        raise RegistryEncodingError(f"{raw_direction!r} appears in a clause but is not ratifiable")

    raw_status = match.group("status")
    try:
        status = EntryStatus(raw_status)
    except ValueError:
        raise RegistryEncodingError(
            f"{raw_status!r} is not a registry entry status; valid values are "
            + ", ".join(s.value for s in EntryStatus)
        ) from None

    dimension_label = match.group("dimension")
    try:
        dimensionality = dimensionality_for_label(dimension_label)
    except UnknownUnitError as exc:
        raise RegistryEncodingError(
            f"{dimension_label!r} is not a declared dimension label: {exc}"
        ) from exc

    return DecodedEntry(
        parameter=match.group("parameter"),
        dimension_label=dimension_label,
        dimensionality=dimensionality,
        direction=direction,
        status=status,
        rationale=match.group("rationale"),
    )
