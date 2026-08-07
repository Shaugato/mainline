# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Registry errors.

Note what is *not* here: there is no "parameter not found" exception.  A missing
parameter is not an error, it is an **abstention** — a first-class answer the
registry returns, carrying its reason, which decision D6 resolves to ``weaken``.
Making it an exception would invite a caller to catch it and continue, and the
one thing that must never happen is for an unknown parameter to end up treated
as neutral.

The exceptions below are for the cases where the registry itself is broken —
a source that cannot answer, an entry that cannot be encoded — because those are
bugs in this system rather than gaps in a site's coverage, and a bug must not be
laundered into an abstention that looks like ordinary under-coverage.
"""

from __future__ import annotations

__all__ = [
    "RegistryEncodingError",
    "RegistryError",
    "RegistrySourceError",
    "SeedError",
]


class RegistryError(Exception):
    """Base for registry faults."""


class RegistryEncodingError(RegistryError):
    """A registry entry could not be encoded into, or decoded out of, clause text.

    Decoding failures do **not** propagate: the loader catches them and records
    the clause as an abstention with reason ``malformed_clause``, because a
    garbled clause in a live document must block rather than crash the gate.
    Encoding failures do propagate, because they mean this code was asked to
    write a clause it cannot write, which is never a runtime condition.
    """


class RegistrySourceError(RegistryError):
    """The clause source could not supply what the loader needs.

    Raised, not abstained.  If the ancestry of ``as_of_commit`` cannot be walked
    then the registry ``as of that commit`` is not under-covered — it is
    unknown, and an unknown registry must not be silently reported as an empty
    one.  An empty registry abstains on everything, which resolves to ``weaken``
    on everything, which looks like a system-wide false alarm rather than the
    infrastructure failure it is.
    """


class SeedError(RegistryError):
    """The committed seed TOML is malformed or self-inconsistent."""
