# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Assets and the energy graph (``mainline.asset_edge``, ``mainline.permit_boundary``).

Zero randomness.  Every tag is either written by hand in ``assets.yaml`` or derived from a
hand-written tag by one of the four rules the file declares.  A drawn asset tag would not
collide with the Aho-Corasick anchor extractor, and an asset graph that the extractor cannot see
is an asset graph that never produces a refusal.

── The thing this module exists for ─────────────────────────────────────────────────────────
``boundary_certificate.under_declared`` counts assets in the **backward energy closure** of a
declared permit boundary that the crew did not declare.  Edges point from the energy source
toward the exposed item, so the closure walks *upstream*.  For the 2026 permit:

    declared   : {P-4104, M-4104, SG-4100}
    upstream   : M-4104 <- SG-4100 <- TX-3002        (declared / declared)
                 P-4104 <- ACC-4104 <- HPU-4104      (NEITHER declared)
                 P-4104 <- TT-4104, PT-4104, HX-4120 (governing controls)
    under-declared, energy-bearing: ACC-4104, HPU-4104

That is the canonical multi-source-isolation fatality in miniature: electrical energy positively
isolated and proven dead, trapped hydraulic pressure still inside the boundary the crew believes
is dead.  ``expected_under_declared`` is computed here from the graph — not asserted from the
gazetteer's ``known_under_declared`` list — and the two are compared.  If they disagree the
graph is wrong, and that is the correct place for it to surface.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from .model import Asset, AssetEdge, PermitBoundary
from .sites import SiteWorld

__all__ = ["AssetWorld", "build_assets"]

_TAG_RE = re.compile(r"^(?P<code>[A-Z]{1,4})-(?P<number>\d{2,6})$")

_ENERGY_KINDS = ("energises", "stores_energy", "governs", "supersedes")

#: Companion metadata.  Derived assets are real assets with real hazard profiles; a motor that
#: carried no hazard energy would let an isolation event pick it and then find no energy to
#: release.
_COMPANION_PROFILE: Mapping[str, tuple[str, str, tuple[str, ...]]] = {
    "motor": ("MOTOR-CLASS-A", "drive motor", ("electrical", "kinetic")),
    "instrument": ("INST-CLASS-A", "instrument loop", ("electrical",)),
    "accumulator": ("ACC-CLASS-A", "energy accumulator", ("pressure",)),
}


def _number_of(tag: str) -> str:
    match = _TAG_RE.match(tag)
    if match is None:
        raise gaz.GazetteerError(
            f"assets.yaml: tag {tag!r} does not have the shape CODE-NNNN. Every tag must carry an "
            "explicit hyphen, which is what makes an unknown prefix extractable by the shipped "
            "anchor automaton."
        )
    return match.group("number")


class AssetWorld:
    """Assets, edges, declared boundaries, and the closure arithmetic."""

    __slots__ = (
        "_by_site",
        "_by_tag",
        "_upstream",
        "assets",
        "boundaries",
        "edges",
        "graph_version",
        "under_declared",
    )

    def __init__(
        self,
        assets: Sequence[Asset],
        edges: Sequence[AssetEdge],
        boundaries: Sequence[PermitBoundary],
        under_declared: Mapping[str, tuple[str, ...]],
        graph_version: str,
    ) -> None:
        self.assets = tuple(assets)
        self.edges = tuple(edges)
        self.boundaries = tuple(boundaries)
        self.under_declared = dict(under_declared)
        self.graph_version = graph_version
        self._by_tag = {asset.tag: asset for asset in assets}
        by_site: dict[str, list[Asset]] = {}
        for asset in assets:
            by_site.setdefault(asset.site_code, []).append(asset)
        self._by_site = {code: tuple(items) for code, items in by_site.items()}
        upstream: dict[str, set[str]] = {}
        for edge in edges:
            upstream.setdefault(edge.to_tag, set()).add(edge.from_tag)
        self._upstream = upstream

    def at(self, site_code: str) -> tuple[Asset, ...]:
        return self._by_site.get(site_code, ())

    def members_at(self, site_code: str) -> tuple[Asset, ...]:
        return tuple(asset for asset in self.at(site_code) if asset.role == "member")

    def get(self, tag: str) -> Asset:
        try:
            return self._by_tag[tag]
        except KeyError as exc:
            raise KeyError(f"unknown asset tag {tag!r}") from exc

    def has(self, tag: str) -> bool:
        return tag in self._by_tag

    def companions(self, tag: str) -> tuple[str, ...]:
        """Tags immediately upstream of ``tag`` — its supply, stores and governing controls."""
        return tuple(sorted(self._upstream.get(tag, ())))

    def backward_closure(self, seeds: Iterable[str], *, halt_at: Iterable[str] = ()) -> set[str]:
        """Every tag that can push energy into, or governs, one of ``seeds``.

        Expansion **halts at** any tag in ``halt_at`` — the tag is reported as reachable but is
        not expanded through.  That is what an applied isolation means physically: energy
        upstream of a proven-dead isolation point is contained, so the site transformer is not an
        exposure just because the switchboard it feeds is in scope.  Without the halt the
        closure walks the whole distribution system and ``under_declared`` becomes a number
        nobody believes, which is worse than not computing it.
        """
        stop = set(halt_at)
        seen: set[str] = set()
        stack = [tag for tag in seeds]
        while stack:
            tag = stack.pop()
            for parent in self._upstream.get(tag, ()):
                if parent in seen:
                    continue
                seen.add(parent)
                if parent not in stop:
                    stack.append(parent)
        return seen

    def asset_rows(self) -> list[dict[str, Any]]:
        return [asset.to_row() for asset in self.assets]

    def edge_rows(self) -> list[dict[str, Any]]:
        return [edge.to_row() for edge in self.edges]

    def boundary_rows(self) -> list[dict[str, Any]]:
        return [boundary.to_row() for boundary in self.boundaries]


def _asset(
    tag: str,
    *,
    site_id: str,
    site_code: str,
    family_id: str,
    asset_class: str,
    label: str,
    service: str,
    criticality: str,
    activity_root: str,
    hazard_energies: Sequence[str],
    role: str,
) -> Asset:
    return Asset(
        tag=tag,
        site_id=site_id,
        site_code=site_code,
        family_id=family_id,
        asset_class=asset_class,
        label=label,
        service=service,
        criticality=criticality,
        activity_root=activity_root,
        hazard_energies=tuple(hazard_energies),
        role=role,
    )


def build_assets(world: SiteWorld) -> AssetWorld:
    """Materialise every asset, every edge, and the declared boundaries."""
    doc = gaz.load("assets")
    graph_version = str(doc["asset_graph_version"])
    families = gaz.as_sequence(doc, "families", origin="assets.yaml")
    valid_energies = {
        str(entry["key"]) for entry in gaz.as_sequence(gaz.load("hazard_energies"), "energies", origin="hazard_energies.yaml")
    }

    assets: dict[str, Asset] = {}
    edges: set[tuple[str, str, str, str]] = set()

    def add_asset(asset: Asset) -> None:
        existing = assets.get(asset.tag)
        if existing is not None:
            if existing.site_code != asset.site_code:
                raise gaz.GazetteerError(
                    f"assets.yaml: tag {asset.tag!r} is claimed by both {existing.site_code} and "
                    f"{asset.site_code}; tags are unique across the corpus"
                )
            return
        unknown = set(asset.hazard_energies) - valid_energies
        if unknown:
            raise gaz.GazetteerError(
                f"assets.yaml: {asset.tag} declares hazard energies {sorted(unknown)} that are not "
                "in the closed vocabulary of hazard_energies.yaml"
            )
        assets[asset.tag] = asset

    def add_edge(site_code: str, from_tag: str, to_tag: str, kind: str) -> None:
        if kind not in _ENERGY_KINDS:
            raise gaz.GazetteerError(f"assets.yaml: unknown edge kind {kind!r}")
        if from_tag == to_tag:
            raise gaz.GazetteerError(f"assets.yaml: self edge on {from_tag!r}")
        edges.add((world.by_code(site_code).site_id, from_tag, to_tag, kind))

    # ── families and their derived companions ────────────────────────────────────────────────
    for family in families:
        family_id = str(family["id"])
        site = world.by_code(str(family["site"]))
        asset_class = str(family["asset_class"])
        activity_root = str(family["mue"])
        hazards = [str(item) for item in family["hazard_energies"]]
        members = [str(tag) for tag in family["members"]]
        instruments = [str(code) for code in family.get("instruments", ())]
        supply = family.get("energised_by")
        accumulator = family.get("accumulator")

        for tag in members:
            number = _number_of(tag)
            add_asset(
                _asset(
                    tag,
                    site_id=site.site_id,
                    site_code=site.code,
                    family_id=family_id,
                    asset_class=asset_class,
                    label=str(family["label"]),
                    service=str(family["service"]),
                    criticality=str(family["criticality"]),
                    activity_root=activity_root,
                    hazard_energies=hazards,
                    role="member",
                )
            )

            if bool(family.get("has_motor")):
                motor = f"M-{number}"
                klass, label, motor_hazards = _COMPANION_PROFILE["motor"]
                add_asset(
                    _asset(
                        motor,
                        site_id=site.site_id,
                        site_code=site.code,
                        family_id=family_id,
                        asset_class=klass,
                        label=label,
                        service=f"drives {tag}",
                        criticality=str(family["criticality"]),
                        activity_root="ELECTRICAL-SAFETY",
                        hazard_energies=motor_hazards,
                        role="motor",
                    )
                )
                add_edge(site.code, motor, tag, "energises")
                if supply:
                    add_edge(site.code, str(supply), motor, "energises")
            elif supply:
                add_edge(site.code, str(supply), tag, "energises")

            for code in instruments:
                loop = f"{code}-{number}"
                klass, label, inst_hazards = _COMPANION_PROFILE["instrument"]
                add_asset(
                    _asset(
                        loop,
                        site_id=site.site_id,
                        site_code=site.code,
                        family_id=family_id,
                        asset_class=klass,
                        label=label,
                        service=f"governs {tag}",
                        criticality=str(family["criticality"]),
                        activity_root=activity_root,
                        hazard_energies=inst_hazards,
                        role="instrument",
                    )
                )
                add_edge(site.code, loop, tag, "governs")

            if accumulator and tag in {str(item) for item in accumulator["members"]}:
                store = f"ACC-{number}"
                klass, label, _ = _COMPANION_PROFILE["accumulator"]
                add_asset(
                    _asset(
                        store,
                        site_id=site.site_id,
                        site_code=site.code,
                        family_id=family_id,
                        asset_class=klass,
                        label=f"{accumulator['medium']} {label}",
                        service=f"stores {accumulator['medium']} energy released at {tag}",
                        criticality="critical",
                        activity_root="ISOLATION-OF-STORED-ENERGY",
                        hazard_energies=(str(accumulator["energy"]),),
                        role="accumulator",
                    )
                )
                add_edge(site.code, store, tag, "stores_energy")

    # ── standalone assets ────────────────────────────────────────────────────────────────────
    for entry in doc.get("extra_assets", ()):
        site = world.by_code(str(entry["site"]))
        tag = str(entry["tag"])
        _number_of(tag)
        add_asset(
            _asset(
                tag,
                site_id=site.site_id,
                site_code=site.code,
                family_id="standalone",
                asset_class=str(entry["asset_class"]),
                label=str(entry["label"]),
                service=str(entry["service"]),
                criticality=str(entry["criticality"]),
                activity_root=str(entry["mue"]),
                hazard_energies=[str(item) for item in entry["hazard_energies"]],
                role="standalone",
            )
        )

    # ── authored edges ───────────────────────────────────────────────────────────────────────
    for entry in doc.get("extra_edges", ()):
        add_edge(str(entry["site"]), str(entry["from"]), str(entry["to"]), str(entry["kind"]))
    for entry in doc.get("supersedes", ()):
        add_edge(str(entry["site"]), str(entry["new"]), str(entry["old"]), "supersedes")

    # Every edge endpoint must be a declared asset.  A dangling endpoint would silently shrink
    # the energy closure, which is the direction with physical consequences.
    dangling = sorted(
        {tag for _, from_tag, to_tag, _ in edges for tag in (from_tag, to_tag) if tag not in assets}
    )
    if dangling:
        raise gaz.GazetteerError(
            f"assets.yaml: edges reference undeclared tags {dangling}. An edge to a tag that does "
            "not exist removes an asset from the energy closure, which admits a permit that "
            "should have been refused."
        )

    asset_list = sorted(assets.values(), key=lambda item: item.tag)
    edge_list = sorted(
        (AssetEdge(site_id=site_id, from_tag=a, to_tag=b, kind=kind) for site_id, a, b, kind in edges),
        key=lambda item: (item.site_id, item.from_tag, item.to_tag, item.kind),
    )

    world_obj = AssetWorld(asset_list, edge_list, (), {}, graph_version)

    # ── declared boundaries and the under-declaration check ──────────────────────────────────
    boundaries: list[PermitBoundary] = []
    under_declared: dict[str, tuple[str, ...]] = {}
    for entry in doc.get("declared_boundaries", ()):
        permit_ref = str(entry["permit_ref"])
        permit_id = str(rng.sid("permit", permit_ref))
        declared = {str(tag): value for tag, value in entry["declared"].items()}
        missing = sorted(tag for tag in declared if not world_obj.has(tag))
        if missing:
            raise gaz.GazetteerError(
                f"assets.yaml: boundary {permit_ref} declares unknown tags {missing}"
            )
        for tag, point in sorted(declared.items()):
            boundaries.append(
                PermitBoundary(
                    permit_id=permit_id,
                    permit_ref=permit_ref,
                    asset_tag=tag,
                    isolation_point_id=None if point is None else str(point),
                )
            )

        # DERIVED, not read from the file.  `known_under_declared` is the gazetteer's claim; this
        # is the graph's answer, and they have to agree.
        work_scope = [str(tag) for tag in entry.get("work_scope", ())] or sorted(declared)
        unknown_scope = sorted(tag for tag in work_scope if not world_obj.has(tag))
        if unknown_scope:
            raise gaz.GazetteerError(
                f"assets.yaml: boundary {permit_ref} names unknown work-scope tags {unknown_scope}"
            )
        closure = world_obj.backward_closure(work_scope, halt_at=declared)
        energy_bearing = {
            tag
            for tag in closure - set(declared)
            if any(
                edge.from_tag == tag and edge.kind in {"energises", "stores_energy"}
                for edge in edge_list
            )
        }
        derived = tuple(sorted(energy_bearing))
        claimed = tuple(sorted(str(tag) for tag in entry.get("known_under_declared", ())))
        if claimed and set(claimed) - set(derived):
            raise gaz.GazetteerError(
                f"assets.yaml: boundary {permit_ref} claims under-declared tags {claimed} but the "
                f"energy graph yields {derived}. The claim and the graph must agree, or the "
                "corpus is asserting a refusal the data cannot support."
            )
        under_declared[permit_ref] = derived

    return AssetWorld(asset_list, edge_list, boundaries, under_declared, graph_version)
