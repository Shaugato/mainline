# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Constructors for the ORIGINDIFF unit suite.  Asserts nothing itself.

The module name is deliberately not ``_support`` and not ``_lattice_fixtures``.
pytest's prepend import mode puts every collected test directory on ``sys.path``,
so two modules sharing a name resolve to whichever collection reached first — a
silent failure that produces a suite exercising somebody else's helpers.
``tests/unit/domain/lattice/_lattice_fixtures.py`` already exists and this module
must not collide with it.

Everything here builds a *legal* object: :func:`cat` runs
:func:`~mainline_domain.cat.schema.validate_cat` on every tuple it returns, so a
rule can never pass a test on an input the extractor cannot produce.

THE SALAMI CHAIN IS BUILT HERE AND IT IS NOT A CONTRIVANCE
-----------------------------------------------------------
:func:`salami_chain` returns twenty-one Control Assertion Tuples in which every
adjacent pair is a ``restate`` under the nine rules and the composition is a
``weaken``.  It exploits two cells the lattice is *deliberately* silent in, both
documented in ``lattice/rules.py``:

* ``r3_comparator`` says nothing about ``=`` ↔ ``<=`` in either direction, because
  that swap is the commonest restatement in a real procedure library and firing on
  it would breach the nuisance ceiling;
* ``r2_setpoint`` falls silent whenever the comparator *family* changes, because
  a magnitude under ``<=`` and a magnitude under ``=`` are two readings of two
  different assertions.

Alternating the comparator on every commit therefore hides an arbitrarily large
setpoint drift from the parent diff.  Against the blame origin — same comparator
at generation 0 and generation 20, same family — R2 compares two magnitudes and
the drift is a weakening with one witness.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Final
from uuid import UUID, uuid5

from mainline_domain.cat.schema import EMPTY_CAT, validate_cat
from mainline_domain.contracts import CAT, Anchor, AnchorClass, AnchorSet, Quantity
from mainline_domain.diachronic.origin import BlameOrigin, BlameOriginRow, resolve_origin
from mainline_domain.quantity.algebra import quantity
from mainline_domain.quantity.units import label_for_dimensionality
from mainline_domain.registry.model import (
    EntryStatus,
    RegistryEntry,
    SafeDirection,
    SafeDirectionRegistry,
)

__all__ = [
    "AS_OF",
    "CLAUSE_UUID",
    "ORIGIN_EVENT",
    "PRESSURE_PARAMETER",
    "SALAMI_STEPS",
    "SITE_ID",
    "anchors",
    "cat",
    "commit",
    "empty_registry",
    "inert_origin",
    "inert_origin_row",
    "origin_row",
    "pressure_cat",
    "pressure_registry",
    "qty",
    "registry",
    "resolved_origin",
    "salami_chain",
]

SITE_ID: Final[UUID] = uuid5(
    UUID("00000000-0000-0000-0000-000000000000"), "mainline/diachronic/site"
)

PRESSURE_PARAMETER: Final[str] = "max_operating_pressure"

#: The unit every fixture quantity is written in.  A named constant rather than a
#: default literal because ruff's bandit rule (S107) reads any string default on a
#: parameter called `*_token` as a hardcoded credential, and silencing a security
#: rule with a `noqa` is a worse habit than naming a constant.
DEFAULT_UNIT_TOKEN: Final[str] = "kPa"

#: Twenty commits, because that is the number the brief names and because a
#: shorter chain would not demonstrate that the drift is unbounded.
SALAMI_STEPS: Final[int] = 20


def commit(label: str) -> bytes:
    """Return a deterministic 32-byte commit id.  ``commit_obj.id_is_sha256`` wants 32."""
    return hashlib.sha256(f"mainline/diachronic/{label}".encode()).digest()


AS_OF: Final[bytes] = commit("as-of")


def qty(value: str, unit_token: str = DEFAULT_UNIT_TOKEN) -> Quantity:
    """Return a :class:`Quantity` from a printed magnitude and a *document* unit token.

    Goes through :func:`mainline_domain.quantity.algebra.quantity` rather than
    constructing the dataclass, so the reference frame is derived exactly the way
    the extractor derives it.  A hand-built ``Quantity`` with the wrong
    ``reference`` would make rule R2 pass a test it should fail.
    """
    return quantity(Decimal(value), unit_token)


def cat(**overrides: object) -> CAT:
    """Return a legal CAT: :data:`EMPTY_CAT` with the named slots replaced."""
    unknown = set(overrides) - set(CAT.__dataclass_fields__)
    if unknown:
        raise TypeError(f"not CAT slots: {sorted(unknown)}")
    fields = {name: getattr(EMPTY_CAT, name) for name in CAT.__dataclass_fields__}
    fields.update(overrides)
    built = CAT(**fields)  # type: ignore[arg-type]
    validate_cat(built)
    return built


def pressure_cat(comparator: str, value: str, **overrides: object) -> CAT:
    """Return the pressure-cap clause the salami chain edits, with slots overridden."""
    fields: dict[str, object] = {
        "actor": "the authorised person",
        "deontic": "MUST",
        "action": "operate",
        "object_class": "pressure vessel",
        "hazard_energy": "pressure",
        "parameter": PRESSURE_PARAMETER,
        "comparator": comparator,
        "value": qty(value),
        "coverage_quantifier": "all",
    }
    fields.update(overrides)
    return cat(**fields)


def _entry(
    parameter: str,
    direction: SafeDirection,
    unit_token: str,
    *,
    status: EntryStatus = EntryStatus.RATIFIED,
) -> RegistryEntry:
    probe = qty("1", unit_token)
    return RegistryEntry(
        parameter=parameter,
        dimension_label=label_for_dimensionality(probe.dimension) or probe.dimension,
        dimensionality=probe.dimension,
        direction=direction,
        status=status,
        rationale=f"fixture direction for {parameter}",
        clause_uuid=uuid5(SITE_ID, f"clause/{parameter}"),
        ratification_commit=commit(f"ratify/{parameter}"),
        ratified_by_sub="sub-fixture-principal-engineer",
        ratification_signed=True,
        gen=1,
        canon_sha256=hashlib.sha256(f"canon/{parameter}".encode()).digest(),
    )


def registry(
    *entries: tuple[str, SafeDirection, str], as_of: bytes = AS_OF
) -> SafeDirectionRegistry:
    """Return a DIRECTRIX registry holding exactly the parameters named."""
    return SafeDirectionRegistry(
        site_id=SITE_ID,
        as_of_commit=as_of,
        doc_code="REG-SAFE-DIRECTION",
        entries={p: _entry(p, d, u) for p, d, u in entries},
        abstentions={},
        encoding_version=1,
        document_present=True,
    )


def pressure_registry(as_of: bytes = AS_OF) -> SafeDirectionRegistry:
    """Return a registry with ``max_operating_pressure`` ratified ``lower_is_safer``."""
    return registry(
        (PRESSURE_PARAMETER, SafeDirection.LOWER_IS_SAFER, "kPa"),
        as_of=as_of,
    )


def empty_registry(as_of: bytes = AS_OF) -> SafeDirectionRegistry:
    """Return a registry that answers about nothing.  Every parameter abstains (D6)."""
    return registry(as_of=as_of)


def anchors(*items: tuple[AnchorClass, str]) -> AnchorSet:
    """Return an :class:`AnchorSet` from ``(class, normalised form)`` pairs."""
    return AnchorSet(
        frozenset(Anchor(cls=cls, raw=norm, norm=norm, span=(0, 0)) for cls, norm in items)
    )


# --------------------------------------------------------------------------- #
# The salami chain                                                             #
# --------------------------------------------------------------------------- #

#: 3.53 % per commit.  Chosen so that twenty compounded steps double the cap
#: (1.0353 ** 20 ≈ 2.0) — a doubling is unmistakable in an exhibit, and each
#: individual step is small enough to read as a rounding decision in a revision.
_STEP_FACTOR: Final[Decimal] = Decimal("1.0353")

#: The cap the incident wrote.  350 kPa, stated as a cap: ``<= 350 kPa``.
_ORIGIN_VALUE: Final[Decimal] = Decimal("350")


def salami_chain(steps: int = SALAMI_STEPS) -> tuple[CAT, ...]:
    """Return ``steps + 1`` CATs: the blame-origin version and one per commit.

    Index 0 is the version the incident wrote.  Every adjacent pair is a
    ``restate`` under the nine rules; the pair ``(0, steps)`` is a ``weaken`` with
    exactly one ``R2_SETPOINT`` witness when ``steps`` is even, because both ends
    then carry the same comparator and R2 has two magnitudes it is willing to
    compare.
    """
    if steps < 1:
        raise ValueError("a salami chain needs at least one step")
    chain = [pressure_cat("<=", str(_ORIGIN_VALUE))]
    value = _ORIGIN_VALUE
    for index in range(1, steps + 1):
        value = (value * _STEP_FACTOR).quantize(Decimal("0.01"))
        chain.append(pressure_cat("=" if index % 2 else "<=", str(value)))
    return tuple(chain)


# --------------------------------------------------------------------------- #
# Origin rows and verdicts, without a cluster                                  #
# --------------------------------------------------------------------------- #


CLAUSE_UUID: Final[UUID] = uuid5(SITE_ID, "clause/isolation")
ORIGIN_EVENT: Final[UUID] = uuid5(SITE_ID, "event/kalgoorlie-1998")


def origin_row(
    *,
    clause_uuid: UUID = CLAUSE_UUID,
    as_of_commit: bytes = AS_OF,
    as_of_gen: int = 20,
    parent_version: bytes | None = None,
    max_severity: int = 5,
    origin_commit: bytes | None = None,
    origin_gen: int = 0,
    origin_severity: int = 5,
    closure_truncated: bool = False,
) -> BlameOriginRow:
    """Return a **resolved** ``mainline.v_blame_origin`` row, shaped as the view emits it.

    ``origin_depth`` is computed rather than passed, exactly as the view computes
    it (``s.gen - o.gen``), so a fixture cannot state a depth its own generations
    contradict.
    """
    parent = commit("gen-19") if parent_version is None else parent_version
    origin = commit("gen-0") if origin_commit is None else origin_commit
    return BlameOriginRow(
        clause_uuid=clause_uuid,
        as_of_commit=as_of_commit,
        site_id=SITE_ID,
        as_of_gen=as_of_gen,
        parent_version=parent,
        max_severity=max_severity,
        closure_gen=1,
        closure_truncated=closure_truncated,
        origin_commit=origin,
        origin_gen=origin_gen,
        origin_depth=as_of_gen - origin_gen,
        origin_event=ORIGIN_EVENT,
        origin_severity=origin_severity,
        origin_basis="asserted_document",
        origin_is_parent=origin == parent,
    )


def inert_origin_row(
    *,
    clause_uuid: UUID = CLAUSE_UUID,
    as_of_commit: bytes = AS_OF,
    as_of_gen: int = 20,
    parent_version: bytes | None = None,
    max_severity: int = 0,
) -> BlameOriginRow:
    """Return a view row with a closure but **no** qualifying blame edge.

    This is what the LEFT JOIN in ``0152_v_blame_origin.sql`` emits for a clause
    whose blame ancestry has been projected and is clean.  It is a *different*
    thing from no row at all, which is
    :class:`~mainline_domain.diachronic.errors.BlameClosureAbsent`.
    """
    return BlameOriginRow(
        clause_uuid=clause_uuid,
        as_of_commit=as_of_commit,
        site_id=SITE_ID,
        as_of_gen=as_of_gen,
        parent_version=commit("gen-19") if parent_version is None else parent_version,
        max_severity=max_severity,
        closure_gen=1,
        closure_truncated=False,
        origin_commit=None,
        origin_gen=None,
        origin_depth=None,
        origin_event=None,
        origin_severity=None,
        origin_basis=None,
        origin_is_parent=False,
    )


def resolved_origin(**overrides: object) -> BlameOrigin:
    """Return a resolved :class:`BlameOrigin`, verified on the first-parent chain."""
    row = origin_row(**overrides)  # type: ignore[arg-type]
    assert row.origin_commit is not None
    return resolve_origin(row, chain=[row.origin_commit, row.as_of_commit])


def inert_origin(**overrides: object) -> BlameOrigin:
    """Return an inert :class:`BlameOrigin` — a clause with no blood-written ancestry."""
    row = inert_origin_row(**overrides)  # type: ignore[arg-type]
    return resolve_origin(row, chain=[row.as_of_commit])
