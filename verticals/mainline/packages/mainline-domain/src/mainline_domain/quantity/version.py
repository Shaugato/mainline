# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Versions of the two committed artefacts this package's answers depend on.

``UNITS_VERSION`` is the version of ``data/units/mainline_units.txt``.  It is
declared here **and** inside the definition file itself (as the dimensionless
constant ``mainline_units_version``), and :func:`mainline_domain.quantity.units.unit_registry`
refuses to return a registry whose file disagrees with this constant.

That double declaration is not belt-and-braces for its own sake.  Pint's
``load_definitions`` on a path that resolves to the wrong file, or to no file at
all under a packaging change, leaves a registry that still answers questions
about ``psi`` — because ``psi`` is in Pint's defaults — and merely does not know
``psig``.  A missing ``psig`` shows up as an ``UndefinedUnitError`` at the worst
possible moment, and a *stale* definition file shows up as nothing at all.
Reading the version back through the registry is the only check that proves the
answers came from the bytes in this repository.

``PARSE_VERSION`` is the version of the phrase grammar in :mod:`.parse`.  It
travels on every parsed measurement so that a re-run years later can say which
grammar read the clause.  Like ``canon_version``, a bump is a deliberate act:
the same clause text may parse differently under a new grammar, so anything
persisted alongside it must be re-derived rather than assumed comparable.
"""

from __future__ import annotations

from typing import Final

__all__ = ["PARSE_VERSION", "UNITS_VERSION"]

UNITS_VERSION: Final[int] = 1

PARSE_VERSION: Final[int] = 1
