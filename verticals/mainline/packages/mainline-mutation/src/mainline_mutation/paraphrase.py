# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Committed adversarial paraphrases.  No model is reached, here or anywhere.

WHAT THIS IS AND WHAT IT IS NOT, STATED FIRST
----------------------------------------------
The cassettes in ``data/paraphrase-cassettes-v1.json`` are **hand-authored**.
They are what a competent adversary with a language model *would* write; they
are not a recording of what one *did* write.  AWS credentials are not valid on
this machine (PL-3) and decision D12 keeps the live Bedrock path off by default
and out of CI, so a cassette recorded from a live call cannot be produced
honestly today.

Every published artefact therefore carries ``paraphrase_provenance:
"hand-authored"`` and the file's ``provenance_statement`` verbatim.  A reader who
sees a kill rate for the adversarial-paraphrase class must be able to tell,
without leaving the artefact, that the adversary was a person and not a model.
When a live recording becomes possible, the entries gain ``provenance:
"recorded"`` and a ``model_id``, the digest moves, and every number computed
under the old cassettes is visibly a number about a different adversary.

THE ANCESTOR DIGEST IS CHECKED, NOT DECORATIVE
-----------------------------------------------
Each entry pins the ``canon_sha256`` of the fixture it paraphrases.  Editing a
fixture without re-authoring its paraphrase would leave a rewrite that no longer
corresponds to the clause it claims to weaken — a mutant measuring nothing, in a
class whose whole purpose is to measure the hardest case.  :func:`paraphrase_for`
raises rather than degrading.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from mainline_domain.canon import canonicalise

from .errors import FixtureError
from .model import Revision
from .resources import load_cassettes
from .version import PARAPHRASE_PROFILE

__all__ = [
    "PARAPHRASE_DOMAIN",
    "CassetteEntry",
    "cassette_key",
    "paraphrase_for",
    "provenance_label",
    "provenance_statement",
]

#: Domain separator for :func:`cassette_key`, matching the generator that wrote
#: the committed file.
PARAPHRASE_DOMAIN: Final[bytes] = b"mainline/mutation/paraphrase/v1\n"


@dataclass(frozen=True, slots=True)
class CassetteEntry:
    """One committed paraphrase and everything a reader needs to weigh it."""

    key: str
    fixture_id: str
    profile: str
    ancestor_canon_sha256: str
    paraphrase: str
    adversary_note: str
    provenance: str
    model_id: str | None


def cassette_key(fixture_id: str, ancestor_canon_sha256: str, profile: str) -> str:
    """The lookup key: fixture, ancestor digest and profile, hashed together."""
    preimage = b"".join(
        (
            PARAPHRASE_DOMAIN,
            f"fixture={fixture_id}\n".encode(),
            f"ancestor_canon_sha256={ancestor_canon_sha256}\n".encode(),
            f"profile={profile}\n".encode(),
        )
    )
    return hashlib.sha256(preimage).hexdigest()


@lru_cache(maxsize=1)
def _by_key() -> dict[str, CassetteEntry]:
    document = load_cassettes()
    entries: dict[str, CassetteEntry] = {}
    for raw in document["entries"]:
        entry = CassetteEntry(
            key=str(raw["key"]),
            fixture_id=str(raw["fixture_id"]),
            profile=str(raw["profile"]),
            ancestor_canon_sha256=str(raw["ancestor_canon_sha256"]),
            paraphrase=str(raw["paraphrase"]),
            adversary_note=str(raw["adversary_note"]),
            provenance=str(raw["provenance"]),
            model_id=None if raw["model_id"] is None else str(raw["model_id"]),
        )
        expected = cassette_key(entry.fixture_id, entry.ancestor_canon_sha256, entry.profile)
        if expected != entry.key:
            raise FixtureError(
                f"cassette {entry.key} does not hash to its own contents (expected "
                f"{expected}); a cassette whose key is not a function of what it contains is a "
                "cassette that can be swapped without the digest moving"
            )
        entries[entry.key] = entry
    return entries


def provenance_statement() -> str:
    """The file's own provenance sentence, copied verbatim into every artefact."""
    return str(load_cassettes()["provenance_statement"])


def provenance_label() -> str:
    """One word for the SQL column: ``'hand-authored'`` today, ``'recorded'`` later.

    Derived from the entries rather than declared, and it RAISES on a file whose
    entries disagree. A cassette set that was half recorded and half invented
    would be published under whichever label happened to be written down, and the
    adversarial-paraphrase kill rate would silently be about two adversaries.
    """
    labels = {str(entry.provenance) for entry in _by_key().values()}
    if len(labels) != 1:
        raise FixtureError(
            f"the cassette file mixes provenances {sorted(labels)}; a kill rate over a mixed set "
            "would be a number about two different adversaries under one label"
        )
    return labels.pop()


def paraphrase_for(revision: Revision, *, profile: str = PARAPHRASE_PROFILE) -> CassetteEntry:
    """The committed paraphrase of one fixture, or a refusal naming what moved.

    :raises FixtureError: when no cassette matches — which happens exactly when
        the fixture's text was edited and its paraphrase was not re-authored.
    """
    digest = canonicalise(revision.document()).canon_sha256.hex()
    key = cassette_key(revision.fixture_id, digest, profile)
    entry = _by_key().get(key)
    if entry is None:
        raise FixtureError(
            f"no committed paraphrase for {revision.fixture_id} at canon_sha256 {digest} under "
            f"profile {profile!r}. The fixture's text has moved since the cassette was written; "
            "re-author the paraphrase rather than relaxing the check, because a rewrite that no "
            "longer corresponds to the clause it claims to weaken measures nothing"
        )
    return entry
