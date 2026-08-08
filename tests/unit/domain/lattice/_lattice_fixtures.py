# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Constructors for the DELTALATTICE unit suite.  Asserts nothing itself.

The module name is deliberately not ``_support``: pytest's prepend import mode
puts every test directory on ``sys.path``, and two modules sharing a name resolve
to whichever collection reached first — a silent failure that produces a suite
testing somebody else's helpers.  ``tests/integration/recall_schema/_support.py``
and ``tests/integration/algorithms/candidates/_support.py`` both already exist.

Everything here builds a *legal* object.  A fixture that quietly builds an
illegal CAT would let a rule pass a test on an input the extractor can never
produce, so :func:`cat` runs :func:`~mainline_domain.cat.validate_cat` on every
tuple it returns.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid5

from mainline_domain.cat.schema import EMPTY_CAT, validate_cat
from mainline_domain.contracts import CAT, Anchor, AnchorClass, AnchorSet, Quantity
from mainline_domain.quantity.algebra import quantity
from mainline_domain.quantity.units import label_for_dimensionality
from mainline_domain.registry.model import (
    EntryStatus,
    RegistryEntry,
    Resolution,
    SafeDirection,
    SafeDirectionRegistry,
)

__all__ = [
    "AS_OF",
    "SITE_ID",
    "anchors",
    "cat",
    "commit",
    "empty_registry",
    "qty",
    "registry",
]

#: A stable site and commit for every test in the suite.  Both are arbitrary; what
#: matters is that they are the SAME arbitrary values everywhere, because
#: :func:`~mainline_domain.lattice.decide` refuses a registry that was read at a
#: commit other than the one under test.
SITE_ID: Final[UUID] = uuid5(UUID("00000000-0000-0000-0000-000000000000"), "mainline/lattice/site")


def commit(label: str) -> bytes:
    """A deterministic 32-byte commit id.  ``commit_obj.id_is_sha256`` wants 32."""
    return hashlib.sha256(f"mainline/lattice/{label}".encode()).digest()


AS_OF: Final[bytes] = commit("as-of")


def qty(value: str, unit_token: str) -> Quantity:
    """A :class:`Quantity` from a printed magnitude and a *document* token.

    Goes through :func:`mainline_domain.quantity.algebra.quantity` rather than
    constructing the dataclass, so the reference frame is derived from the unit
    exactly the way the extractor derives it.  A hand-built ``Quantity`` with the
    wrong ``reference`` would make R2 pass a test it should fail.
    """
    return quantity(Decimal(value), unit_token)


def cat(**overrides: object) -> CAT:
    """A legal CAT: :data:`EMPTY_CAT` with the named slots replaced.

    Starting from ``EMPTY_CAT`` rather than from a fully populated tuple keeps
    each test's *difference* to the slots it names, which is the only thing the
    lattice is allowed to react to.
    """
    unknown = set(overrides) - set(CAT.__dataclass_fields__)
    if unknown:
        raise TypeError(f"not CAT slots: {sorted(unknown)}")
    fields = {name: getattr(EMPTY_CAT, name) for name in CAT.__dataclass_fields__}
    fields.update(overrides)
    built = CAT(**fields)  # type: ignore[arg-type]
    validate_cat(built)
    return built


def _entry(
    parameter: str,
    direction: SafeDirection,
    unit_token: str,
    *,
    status: EntryStatus = EntryStatus.RATIFIED,
    signed: bool = True,
) -> RegistryEntry:
    probe = qty("1", unit_token)
    return RegistryEntry(
        parameter=parameter,
        # `label_for_dimensionality` is best-effort and may answer None for a
        # dimensionality with no seeded label; the field is for messages only and
        # must never be None, so the raw dimensionality is the fallback.
        dimension_label=label_for_dimensionality(probe.dimension) or probe.dimension,
        dimensionality=probe.dimension,
        direction=direction,
        status=status,
        rationale=f"fixture direction for {parameter}",
        clause_uuid=uuid5(SITE_ID, f"clause/{parameter}"),
        ratification_commit=commit(f"ratify/{parameter}"),
        ratified_by_sub="sub-fixture-principal-engineer",
        ratification_signed=signed,
        gen=1,
        canon_sha256=hashlib.sha256(f"canon/{parameter}".encode()).digest(),
    )


def registry(
    *entries: tuple[str, SafeDirection, str],
    as_of: bytes = AS_OF,
    abstentions: dict[str, Resolution] | None = None,
    document_present: bool = True,
) -> SafeDirectionRegistry:
    """A DIRECTRIX registry holding exactly the parameters named.

    Each entry is ``(parameter, direction, unit_token)``; the unit fixes the
    entry's dimensionality, and :meth:`SafeDirectionRegistry.resolve` abstains
    when a clause measures the parameter in a different one.
    """
    return SafeDirectionRegistry(
        site_id=SITE_ID,
        as_of_commit=as_of,
        doc_code="REG-SAFE-DIRECTION",
        entries={p: _entry(p, d, u) for p, d, u in entries},
        abstentions=dict(abstentions or {}),
        encoding_version=1,
        document_present=document_present,
    )


def empty_registry(*, as_of: bytes = AS_OF, document_present: bool = True) -> SafeDirectionRegistry:
    """A registry that answers about nothing.  Every parameter abstains (D6)."""
    return registry(as_of=as_of, document_present=document_present)


def anchors(*items: tuple[AnchorClass, str]) -> AnchorSet:
    """An :class:`AnchorSet` from ``(class, normalised form)`` pairs.

    ``raw`` is set equal to ``norm`` and the span is degenerate: nothing in rule
    R8 reads either, and inventing plausible spans would suggest they mattered.
    """
    return AnchorSet(
        frozenset(Anchor(cls=cls, raw=norm, norm=norm, span=(0, 0)) for cls, norm in items)
    )
