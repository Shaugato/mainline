# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""DIRECTRIX — the ``safe_direction`` registry, self-hosted in the gated DAG.

Public surface::

    from mainline_domain.registry import load_registry, setpoint_delta

    registry = load_registry(source, site_id=site, as_of_commit=head)
    registry.safe_direction("max_operating_pressure")  # LOWER_IS_SAFER
    registry.safe_direction("not_a_parameter")  # ABSTAIN

    setpoint_delta(
        registry,
        "max_operating_pressure",
        ancestor=quantity("400", "kPa"),
        descendant=quantity("600", "kPa"),
    ).delta  # ControlDelta.WEAKEN

THE CLAIM, STATED PRECISELY
---------------------------
``safe_direction(parameter)`` is the table that decides which way a setpoint
move is dangerous.  Here it is not a table: it is a **document in the same
commit DAG the procedures live in**, one clause per parameter, carrying its own
blame edges, ratified by a signed commit.  Editing it is therefore a
``change_request`` that the merge gate governs on exactly the terms it governs
any other weakening — *the gate's own parameters are gated by the gate.*

That recursion is the unclaimed part.  A curated direction registry is ordinary
engineering; what this survey found no prior art for is the registry being
subject to the mechanism it parameterises, so that the cheapest attack on the
whole product — flip one direction, and every subsequent increase reads as a
tightening — stops being an ``UPDATE`` and becomes a signed, blame-bearing,
gate-refusable commit.

TWO REFUSALS THIS PACKAGE PRODUCES
----------------------------------
1. **Unratified ⇒ abstain ⇒ weaken** (decision D6).  An unknown, proposed,
   withdrawn, retired, duplicated, ambiguous or malformed entry does not yield a
   direction and does not yield "neutral"; it yields
   :attr:`~mainline_domain.registry.model.SafeDirection.ABSTAIN`, which
   :func:`~mainline_domain.registry.resolve.setpoint_delta` resolves to
   ``ControlDelta.weaken``.  Under-coverage costs nuisance blocks, never silent
   passes, and the way to clear a nuisance block is to ratify the parameter —
   which is the adoption ratchet.
2. **Gauge crossings raise** (decision D5, in :mod:`mainline_domain.quantity`).
   A comparison this package cannot make honestly is not made.

WHAT IS NOT PROVEN HERE
-----------------------
This package computes the direction and the ruling.  The *merge refusal* those
feed is a ``CHECK`` on ``permit``/``change_request`` owned by the kernel lead,
and the witness-or-refuse trigger that makes an unexplained ``weaken``
un-insertable is worker W4's.  Until those migrations land, what is proven is
that DIRECTRIX abstains where it should and rules where it can — not that a
merge stops.  See ``novelty/directrix.yaml``, ``unverified:``.
"""

from __future__ import annotations

from .doc import DOC_CODE, DOC_TITLE
from .encoding import ENCODING_VERSION, DecodedEntry, decode, encode
from .errors import (
    RegistryEncodingError,
    RegistryError,
    RegistrySourceError,
    SeedError,
)
from .loader import load_registry
from .model import (
    RATIFIABLE_DIRECTIONS,
    AbstentionReason,
    EntryStatus,
    RegistryEntry,
    Resolution,
    SafeDirection,
    SafeDirectionRegistry,
)
from .resolve import (
    SetpointRuling,
    delta_for_abstention,
    setpoint_delta,
    tolerance_delta,
)
from .seed import (
    SeedParameter,
    clause_uuid_for,
    load_seed,
    ratified_variant,
    seed_clause_rows,
    seed_source,
)
from .source import (
    ClauseVersionRow,
    ClauseVersionSource,
    CommitNode,
    InMemoryClauseVersionSource,
)

__all__ = [
    "DOC_CODE",
    "DOC_TITLE",
    "ENCODING_VERSION",
    "RATIFIABLE_DIRECTIONS",
    "AbstentionReason",
    "ClauseVersionRow",
    "ClauseVersionSource",
    "CommitNode",
    "DecodedEntry",
    "EntryStatus",
    "InMemoryClauseVersionSource",
    "RegistryEncodingError",
    "RegistryEntry",
    "RegistryError",
    "RegistrySourceError",
    "Resolution",
    "SafeDirection",
    "SafeDirectionRegistry",
    "SeedError",
    "SeedParameter",
    "SetpointRuling",
    "clause_uuid_for",
    "decode",
    "delta_for_abstention",
    "encode",
    "load_registry",
    "load_seed",
    "ratified_variant",
    "seed_clause_rows",
    "seed_source",
    "setpoint_delta",
    "tolerance_delta",
]
