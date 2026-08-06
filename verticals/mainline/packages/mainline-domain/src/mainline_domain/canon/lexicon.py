# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Loader for the committed de-hyphenation lexicon.

The lexicon is data, and it is *evidence-grade* data: two runs of the
canonicaliser that disagree about whether ``lock-out`` keeps its hyphen produce
two digests for one clause, which is an identity miss the system will report as
residue.  So the file is committed, versioned with ``canon_version``, loaded
once, and never fetched or overridden at runtime.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from ..data import data_file

__all__ = ["DomainLexicon", "load_lexicon"]

_LEXICON_FILE: Final[tuple[str, ...]] = ("gazetteer", "domain-lexicon.toml")


@dataclass(frozen=True, slots=True)
class DomainLexicon:
    """Casefolded closed forms and hyphenated compounds."""

    version: int
    words: frozenset[str]
    compounds: frozenset[str]

    def is_word(self, token: str) -> bool:
        return token.casefold() in self.words

    def is_compound(self, left: str, right: str) -> bool:
        return f"{left.casefold()}-{right.casefold()}" in self.compounds


def _string_list(raw: object, key: str) -> frozenset[str]:
    if not isinstance(raw, list):
        raise TypeError(f"domain-lexicon.toml: [lexicon].{key} must be an array of strings")
    out: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise TypeError(f"domain-lexicon.toml: [lexicon].{key} contains a non-string entry")
        out.add(item.casefold())
    return frozenset(out)


@lru_cache(maxsize=1)
def load_lexicon() -> DomainLexicon:
    """Load and cache the committed lexicon.  Raises if the file is missing."""
    with data_file(*_LEXICON_FILE).open("rb") as handle:
        document = tomllib.load(handle)

    section = document.get("lexicon")
    if not isinstance(section, dict):
        raise TypeError("domain-lexicon.toml: missing [lexicon] table")

    version = section.get("version")
    if not isinstance(version, int):
        raise TypeError("domain-lexicon.toml: [lexicon].version must be an integer")

    return DomainLexicon(
        version=version,
        words=_string_list(section.get("words"), "words"),
        compounds=_string_list(section.get("compounds"), "compounds"),
    )
