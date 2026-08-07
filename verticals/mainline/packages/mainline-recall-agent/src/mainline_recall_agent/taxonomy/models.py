# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The archival spine as Python values: nodes, paths, facet values, cue rows, bond rows.

Three properties are enforced by construction rather than by convention, because each of
them is a way the vector index goes silently wrong:

1. **Every node's label is validated.**  Not only on the way in — on the way *back* too.
   A node read out of ``mainline.activity_node`` whose label is a thing is a defect that
   already happened, and finding it at read time is the only remaining chance to see it.
2. **Every path is contiguous, single-site and single-version.**  A cue row filed under a
   scope from another site, or under a level-3 node whose level-2 parent is missing, is
   retrievable only by an arm nobody generates.  There is no error message for that at
   query time; there is just an incident that never comes back.
3. **Scope ids are derived, not drawn.**  ``activity_node.scope_id`` has a
   ``gen_random_uuid()`` default, but this package supplies UUIDv5 values derived from
   ``(site_id, taxonomy_ver, level, label path)``.  Two consequences make it worth the
   deviation: a re-run of the same induction produces the same node identities, so the
   version diff is about *labels* and not about fresh UUIDs; and a bond written by one
   process and a cue written by another agree on the scope without a round trip.

``CueRow`` and ``BondRow`` carry exactly the columns of ``mainline.event_cue`` (migration
0040) and ``mainline.event_bond`` (0046).  They deliberately do **not** carry ``cue_id``:
that is the database's to mint.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from mainline_recall_agent.providers.types import FACETS

from .errors import (
    ArchivalPathError,
    CueEmissionError,
    Level1Unfrozen,
    TaxonomyVersionError,
)
from .labels import validate_label

__all__ = [
    "BOND_BASES",
    "INDUCED_BY",
    "LEVEL_FILE",
    "LEVEL_FONDS",
    "LEVEL_NAMES",
    "LEVEL_SERIES",
    "NODE_NAMESPACE",
    "ActivityNode",
    "ArchivalPath",
    "BondRow",
    "CueRow",
    "EventRef",
    "FacetValue",
    "TaxonomySnapshot",
    "derive_scope_id",
]

#: ISAD(G) multi-level description, as ARCHITECTURE §5.4 names it.
LEVEL_FONDS: Final[int] = 1
LEVEL_SERIES: Final[int] = 2
LEVEL_FILE: Final[int] = 3
LEVEL_NAMES: Final[Mapping[int, str]] = {
    LEVEL_FONDS: "fonds",
    LEVEL_SERIES: "series",
    LEVEL_FILE: "file",
}

#: ``activity_node.induced_by`` CHECK, verbatim.
INDUCED_BY: Final[frozenset[str]] = frozenset({"icmm_mue", "llm_induced", "human"})

#: ``event_bond.bond_basis`` CHECK, verbatim.  Note it is NOT the same vocabulary as
#: ``induced_by``: ``induced_by`` says how the *node* came to exist, ``bond_basis`` says
#: how *this event* came to be attached to it.  A coded MSHA accident class bonding an
#: event to an LLM-induced node is ``coded``.
BOND_BASES: Final[frozenset[str]] = frozenset({"coded", "llm_induced", "human"})

#: Namespace for derived scope ids: ``uuid5(NODE_NAMESPACE, "site|ver|level|a / b / c")``.
#: Fixed forever — changing it re-identifies every node in every deployment.
NODE_NAMESPACE: Final[uuid.UUID] = uuid.UUID("bae0289f-2d1f-5572-8e4b-4e0adae7f81b")


def derive_scope_id(
    *, site_id: str, taxonomy_ver: int, level: int, label_path: Sequence[str]
) -> str:
    """Deterministic ``scope_id`` for a node at ``label_path`` under one site and version."""
    if level != len(label_path):
        raise TaxonomyVersionError(
            "a node's level must equal the depth of its label path",
            level=level,
            label_path=list(label_path),
        )
    key = f"{site_id}|{taxonomy_ver}|{level}|{' / '.join(label_path)}"
    return str(uuid.uuid5(NODE_NAMESPACE, key))


@dataclass(frozen=True, slots=True)
class ActivityNode:
    """One row of ``mainline.activity_node``.

    ``__post_init__`` re-states three of the table's own constraints (``level BETWEEN 1
    AND 3``, ``induced_by IN (...)``, ``l1_frozen``) plus the one the table cannot state:
    that ``label`` names a function performed.
    """

    scope_id: str
    site_id: str
    level: int
    parent_scope: str | None
    label: str
    activity_root: str
    taxonomy_ver: int
    induced_by: str
    frozen: bool

    def __post_init__(self) -> None:
        if self.level not in LEVEL_NAMES:
            raise TaxonomyVersionError(
                "activity_node.level is 1 (fonds), 2 (series) or 3 (file)",
                level=self.level,
                label=self.label,
            )
        if self.induced_by not in INDUCED_BY:
            raise TaxonomyVersionError(
                "activity_node.induced_by outside the declared vocabulary",
                induced_by=self.induced_by,
                allowed=sorted(INDUCED_BY),
            )
        if self.level == LEVEL_FONDS and not self.frozen:
            raise Level1Unfrozen(
                "level 1 is frozen by CONSTRAINT l1_frozen; a fonds row with frozen=false "
                "is refused here as well as by the database, so no writer can compose a "
                "statement the database is going to reject",
                label=self.label,
            )
        if self.level == LEVEL_FONDS and self.parent_scope is not None:
            raise TaxonomyVersionError(
                "a fonds has no parent scope", label=self.label, parent=self.parent_scope
            )
        if self.level != LEVEL_FONDS and self.parent_scope is None:
            raise TaxonomyVersionError(
                "a series or file must name its parent scope; an orphan node is a K-means "
                "tree with no ancestor arm pointing at it",
                label=self.label,
                level=self.level,
            )
        if not self.activity_root.strip():
            raise TaxonomyVersionError("activity_root is the level-1 code and is mandatory")
        validate_label(self.label, where=f"{LEVEL_NAMES[self.level]} label")

    @property
    def level_name(self) -> str:
        return LEVEL_NAMES[self.level]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "site_id": self.site_id,
            "level": self.level,
            "parent_scope": self.parent_scope,
            "label": self.label,
            "activity_root": self.activity_root,
            "taxonomy_ver": self.taxonomy_ver,
            "induced_by": self.induced_by,
            "frozen": self.frozen,
        }


@dataclass(frozen=True, slots=True)
class ArchivalPath:
    """A contiguous fonds -> series -> file chain, shortest legal length 1.

    Built by :func:`~mainline_recall_agent.taxonomy.sources.resolve_path` from the node
    table, never assembled by a caller from ids it happens to hold.  ARCHITECTURE's P2
    rule — *a projection is enforced, never trusted* — has an application-side reading
    here: the writer derives the prefix set from the authoritative table and refuses when
    the table does not corroborate it.
    """

    nodes: tuple[ActivityNode, ...]

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ArchivalPathError("an archival path contains at least the fonds")
        if self.nodes[0].level != LEVEL_FONDS:
            raise ArchivalPathError(
                "an archival path starts at the fonds", first_level=self.nodes[0].level
            )
        sites = {node.site_id for node in self.nodes}
        if len(sites) != 1:
            raise ArchivalPathError(
                "an archival path may not cross sites; a cue filed under another site's "
                "scope is unreachable by this site's arms, permanently and silently",
                sites=sorted(sites),
            )
        versions = {node.taxonomy_ver for node in self.nodes}
        if len(versions) != 1:
            raise ArchivalPathError(
                "an archival path may not mix taxonomy versions", versions=sorted(versions)
            )
        roots = {node.activity_root for node in self.nodes}
        if len(roots) != 1:
            raise ArchivalPathError(
                "every node on a path denormalises the same level-1 code",
                activity_roots=sorted(roots),
            )
        for index, node in enumerate(self.nodes):
            if node.level != index + 1:
                raise ArchivalPathError(
                    "an archival path may not skip a level",
                    expected_level=index + 1,
                    found_level=node.level,
                    label=node.label,
                )
            if index and node.parent_scope != self.nodes[index - 1].scope_id:
                raise ArchivalPathError(
                    "parent link does not match the preceding node on the path",
                    label=node.label,
                    declared_parent=node.parent_scope,
                    path_parent=self.nodes[index - 1].scope_id,
                )

    def __iter__(self) -> Iterator[ActivityNode]:
        return iter(self.nodes)

    def __len__(self) -> int:
        return len(self.nodes)

    @property
    def depth(self) -> int:
        return len(self.nodes)

    @property
    def fonds(self) -> ActivityNode:
        return self.nodes[0]

    @property
    def leaf(self) -> ActivityNode:
        return self.nodes[-1]

    @property
    def site_id(self) -> str:
        return self.nodes[0].site_id

    @property
    def taxonomy_ver(self) -> int:
        return self.nodes[0].taxonomy_ver

    @property
    def activity_root(self) -> str:
        return self.nodes[0].activity_root

    def activity_path_string(self) -> str:
        """The ``{activity_path}`` slot of the embedding template (recall.md D3).

        The same string on the event side and the permit side.  Rendered here, once, so
        the two sides cannot drift: ``providers.base.embed_text`` takes it as an argument
        and has no opinion about how it was built.
        """
        return " / ".join(node.label for node in self.nodes)

    def scope_ids(self) -> tuple[str, ...]:
        return tuple(node.scope_id for node in self.nodes)


@dataclass(frozen=True, slots=True)
class FacetValue:
    """One synthesised Recurrence-Condition Cue facet for one event.

    ``insufficient_evidence`` is the escape ARCHITECTURE §5.4 requires the cue synthesiser
    to be able to take.  A facet that took it is **not populated**: it produces no cue row
    at any level, because a row whose text says "insufficient evidence" is a point in the
    index that matches everything vaguely and evidences nothing.
    """

    facet: str
    text: str = ""
    source_span: tuple[int, int] | None = None
    insufficient_evidence: bool = False

    def __post_init__(self) -> None:
        if self.facet not in FACETS:
            raise CueEmissionError(
                "unknown facet", facet=self.facet, allowed=list(FACETS)
            )
        if self.insufficient_evidence and self.text.strip():
            raise CueEmissionError(
                "a facet that declares insufficient evidence must not also carry cue text; "
                "one of the two statements is false and the writer cannot tell which",
                facet=self.facet,
            )
        if not self.insufficient_evidence and not self.text.strip():
            raise CueEmissionError(
                "a facet with no text must declare insufficient_evidence. A blank cue that "
                "is silently dropped is a facet the synthesiser failed on and nobody "
                "recorded; a blank cue that is silently written is a point in the index "
                "with no content behind it",
                facet=self.facet,
            )

    @property
    def populated(self) -> bool:
        """True exactly when this facet produces a cue row at every level of the path."""
        return not self.insufficient_evidence


@dataclass(frozen=True, slots=True)
class EventRef:
    """The columns of ``mainline.event`` the LMB and bond writers actually read."""

    event_id: str
    site_id: str
    severity_gate: int = 0
    severity_basis: str = "coded_field"

    def __post_init__(self) -> None:
        if not self.event_id or not self.site_id:
            raise CueEmissionError("an event reference needs both event_id and site_id")


@dataclass(frozen=True, slots=True)
class CueRow:
    """One row of ``mainline.event_cue`` — one (archival level x populated facet) pair."""

    event_id: str
    site_id: str
    scope_id: str
    scope_level: int
    facet: str
    taxonomy_ver: int
    cue_text: str
    source_span: tuple[int, int] | None
    is_derived: bool
    gen_model: str
    prompt_version: str

    @property
    def dedupe_key(self) -> tuple[str, str, str, str]:
        """The table's own ``UNIQUE (event_id, scope_id, facet, prompt_version)``."""
        return (self.event_id, self.scope_id, self.facet, self.prompt_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "site_id": self.site_id,
            "scope_id": self.scope_id,
            "scope_level": self.scope_level,
            "facet": self.facet,
            "taxonomy_ver": self.taxonomy_ver,
            "cue_text": self.cue_text,
            "source_span": list(self.source_span) if self.source_span else None,
            "is_derived": self.is_derived,
            "gen_model": self.gen_model,
            "prompt_version": self.prompt_version,
        }


@dataclass(frozen=True, slots=True)
class BondRow:
    """One row of ``mainline.event_bond`` — channel B's set membership, not a score."""

    event_id: str
    scope_id: str
    taxonomy_ver: int
    bond_basis: str
    scope_level: int = LEVEL_FILE

    def __post_init__(self) -> None:
        if self.bond_basis not in BOND_BASES:
            raise CueEmissionError(
                "event_bond.bond_basis outside the declared vocabulary",
                bond_basis=self.bond_basis,
                allowed=sorted(BOND_BASES),
            )

    @property
    def primary_key(self) -> tuple[str, str, int]:
        return (self.event_id, self.scope_id, self.taxonomy_ver)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "scope_id": self.scope_id,
            "taxonomy_ver": self.taxonomy_ver,
            "bond_basis": self.bond_basis,
            "scope_level": self.scope_level,
        }


@dataclass(frozen=True, slots=True)
class TaxonomySnapshot:
    """The whole frozen tree for one ``(site_id, taxonomy_ver)``, plus merge aliases.

    ``aliases`` maps every label the induction saw and merged away to the ``scope_id`` it
    was merged into.  It is not decoration: holdout confirmation labels and historical
    bonds are written against the pre-merge wording, and resolving them through the alias
    map is the difference between measuring the taxonomy and measuring a rename.
    """

    site_id: str
    taxonomy_ver: int
    nodes: tuple[ActivityNode, ...]
    aliases: Mapping[str, str] = field(default_factory=dict)
    register_id: str = ""
    register_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.nodes:
            raise TaxonomyVersionError("a taxonomy snapshot with no nodes is not a taxonomy")
        seen: set[str] = set()
        for node in self.nodes:
            if node.scope_id in seen:
                raise TaxonomyVersionError("duplicate scope_id in snapshot", scope=node.scope_id)
            seen.add(node.scope_id)
            if node.site_id != self.site_id or node.taxonomy_ver != self.taxonomy_ver:
                raise TaxonomyVersionError(
                    "snapshot nodes must share the snapshot's site and taxonomy version",
                    label=node.label,
                )
        index = {node.scope_id: node for node in self.nodes}
        for node in self.nodes:
            if node.parent_scope is not None and node.parent_scope not in index:
                raise TaxonomyVersionError(
                    "snapshot contains a node whose parent is absent from the snapshot",
                    label=node.label,
                    parent=node.parent_scope,
                )

    def by_scope(self, scope_id: str) -> ActivityNode | None:
        return next((node for node in self.nodes if node.scope_id == scope_id), None)

    def at_level(self, level: int) -> tuple[ActivityNode, ...]:
        return tuple(node for node in self.nodes if node.level == level)

    def leaves(self) -> tuple[ActivityNode, ...]:
        parents = {node.parent_scope for node in self.nodes if node.parent_scope}
        return tuple(node for node in self.nodes if node.scope_id not in parents)

    def path_to(self, scope_id: str) -> ArchivalPath:
        chain: list[ActivityNode] = []
        cursor: str | None = scope_id
        while cursor is not None:
            node = self.by_scope(cursor)
            if node is None:
                raise ArchivalPathError(
                    "snapshot does not contain a node on this ancestry chain", scope_id=cursor
                )
            chain.append(node)
            cursor = node.parent_scope
        return ArchivalPath(tuple(reversed(chain)))

    def resolve_label(self, label: str, *, level: int | None = None) -> ActivityNode | None:
        """Find a node by label, following the merge alias map when the label is a member."""
        for node in self.nodes:
            if node.label == label and (level is None or node.level == level):
                return node
        aliased = self.aliases.get(label)
        if aliased is not None:
            merged = self.by_scope(aliased)
            if merged is not None and (level is None or merged.level == level):
                return merged
        return None

    def label_keys(self) -> frozenset[tuple[int, str, str]]:
        """``(level, activity_root, label)`` for every node — the diff's identity set."""
        return frozenset((n.level, n.activity_root, n.label) for n in self.nodes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site_id": self.site_id,
            "taxonomy_ver": self.taxonomy_ver,
            "register_id": self.register_id,
            "register_sha256": self.register_sha256,
            "nodes": [node.to_dict() for node in self.nodes],
            "aliases": dict(sorted(self.aliases.items())),
        }
