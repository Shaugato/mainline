# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
r"""Committed data files, their bytes, and the digest a published number carries.

Everything the harness measures with is a file in this package: the catalogue
declaration, the fixture revisions and the paraphrase cassettes.  Nothing is
fetched, generated at run time, or read from an environment variable.

``catalogue_sha256()`` IS THE PROVENANCE OF EVERY PUBLISHED NUMBER
------------------------------------------------------------------
The digest covers the three files' **bytes**, each length-prefixed, in a fixed
order, behind a domain separator::

    b"mainline/mutation/catalogue/v1\\n"
    || u32be(len(catalogue-v1.toml))          || catalogue-v1.toml
    || u32be(len(fixtures-v1.toml))           || fixtures-v1.toml
    || u32be(len(paraphrase-cassettes-v1.json)) || paraphrase-cassettes-v1.json

Length prefixes rather than a separator string, because a separator is a string
that can appear in a file and a length is not.  The preimage is reconstructable
by hand from three files and this docstring, which is the standard every digest
in this repository is held to.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from functools import cache, lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Final

__all__ = [
    "CASSETTE_FILE",
    "CATALOGUE_DOMAIN",
    "CATALOGUE_FILE",
    "FIXTURES_FILE",
    "catalogue_sha256",
    "data_bytes",
    "data_path",
    "load_cassettes",
    "load_catalogue_toml",
    "load_fixtures_toml",
]

CATALOGUE_FILE: Final[str] = "catalogue-v1.toml"
FIXTURES_FILE: Final[str] = "fixtures-v1.toml"
CASSETTE_FILE: Final[str] = "paraphrase-cassettes-v1.json"

#: Domain separator for :func:`catalogue_sha256`.
CATALOGUE_DOMAIN: Final[bytes] = b"mainline/mutation/catalogue/v1\n"

#: The order is fixed here and nowhere else.  A digest whose input order is a
#: directory listing is a digest that changes with the filesystem.
_DIGEST_ORDER: Final[tuple[str, ...]] = (CATALOGUE_FILE, FIXTURES_FILE, CASSETTE_FILE)

_LENGTH_PREFIX_BYTES: Final[int] = 4


def data_path(name: str) -> Path:
    """Return the on-disk path of one committed data file.

    Uses :mod:`importlib.resources` so the harness works from an installed wheel
    as well as from a source checkout; a data file addressed by
    ``__file__``-relative path stops existing the moment somebody zips the
    package, and a measurement that only runs from a checkout is a measurement
    nobody else can reproduce.
    """
    return Path(str(resources.files("mainline_mutation") / "data" / name))


@cache
def data_bytes(name: str) -> bytes:
    """Return the raw bytes of one committed data file.

    Bytes, not text: the digest is over what is on disk, and a text read would
    silently normalise line endings on Windows and produce a different digest
    from the same commit.
    """
    return data_path(name).read_bytes()


@lru_cache(maxsize=1)
def catalogue_sha256() -> str:
    """The 64-hex digest stamped on every published number and every SQL row.

    See the module docstring for the preimage.  Cached because it is read on
    every result row and the files do not change inside a process.
    """
    parts = [CATALOGUE_DOMAIN]
    for name in _DIGEST_ORDER:
        payload = data_bytes(name)
        parts.append(len(payload).to_bytes(_LENGTH_PREFIX_BYTES, "big"))
        parts.append(payload)
    return hashlib.sha256(b"".join(parts)).hexdigest()


@lru_cache(maxsize=1)
def load_catalogue_toml() -> dict[str, Any]:
    """Parse ``catalogue-v1.toml``.  Structure is validated in :mod:`.catalogue`."""
    return tomllib.loads(data_bytes(CATALOGUE_FILE).decode("utf-8"))


@lru_cache(maxsize=1)
def load_fixtures_toml() -> dict[str, Any]:
    """Parse ``fixtures-v1.toml``.  Structure is validated in :mod:`.fixtures`."""
    return tomllib.loads(data_bytes(FIXTURES_FILE).decode("utf-8"))


@lru_cache(maxsize=1)
def load_cassettes() -> dict[str, Any]:
    """Parse ``paraphrase-cassettes-v1.json``.

    The file carries a ``provenance_statement`` that says in full sentences that
    these were HAND-AUTHORED and that no model was called.  That statement is
    copied verbatim into every published artefact by :mod:`.report`, because a
    provenance note that lives only next to the data is a note nobody reading
    the number will see.
    """
    parsed: dict[str, Any] = json.loads(data_bytes(CASSETTE_FILE).decode("utf-8"))
    return parsed
