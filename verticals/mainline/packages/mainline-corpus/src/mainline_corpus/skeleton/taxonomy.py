# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The three-level archival activity taxonomy.

``mainline.activity_node`` (ARCHITECTURE.md §5.4), one tree per site.

Three properties this module is responsible for, each enforced rather than assumed:

* **``CHECK l1_frozen``** — ``level <> 1 OR frozen = true``.  Every level-1 row is emitted with
  ``frozen: true`` and ``induced_by: 'icmm_mue'``, because level 1 is anchored to the buyer's
  ICMM Material Unwanted Event register and its codes are baked into the physical vector index:
  re-inducting level 1 is a re-partition, not a data change.
* **``UNIQUE (site_id, taxonomy_ver, level, label)``** — labels are checked for collision per
  level *before* anything is emitted, so a gazetteer edit that duplicates a series label fails
  here with a readable message rather than at ``COPY`` time.
* **``activity_root`` is denormalised onto every level** — it is the level-1 code, and it is the
  prefix column of the C-SPANN index.  A level-3 node whose ``activity_root`` disagreed with its
  root's code would put its clauses in the wrong ANN partition, where they would be invisible to
  every recall arm and visibly present in every count.  The builder derives it; it is never read
  from the file at levels 2 and 3.

Levels 2 and 3 carry ``induced_by: 'human'``.  In production they are LLM-induced; here they are
written by hand in ``taxonomy.yaml``, and stamping model provenance on a hand-written row would
be a lie in a provenance column.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from .model import ActivityNode, Site
from .sites import SiteWorld

__all__ = ["Fonds", "TaxonomyWorld", "build_taxonomy"]


class Fonds:
    """One level-1 class, with its authored series/file structure and hazard profile."""

    __slots__ = ("code", "fatal_potential_trigger", "hazard_energies", "label", "mue", "series")

    def __init__(self, entry: Mapping[str, Any]) -> None:
        self.code = str(entry["code"])
        self.label = str(entry["label"])
        self.mue = str(entry["mue"])
        self.fatal_potential_trigger = bool(entry["fatal_potential_trigger"])
        self.hazard_energies = tuple(str(item) for item in entry["hazard_energies"])
        self.series = tuple(
            (str(block["label"]), tuple(str(name) for name in block["files"]))
            for block in entry["series"]
        )
        if not self.series:
            raise gaz.GazetteerError(f"taxonomy.yaml: fonds {self.code!r} declares no series")


class TaxonomyWorld:
    """Every activity node, plus the lookups the event generator needs."""

    __slots__ = ("_scope_by_key", "fonds", "fonds_by_code", "nodes", "taxonomy_ver")

    def __init__(
        self,
        nodes: Sequence[ActivityNode],
        fonds: Sequence[Fonds],
        taxonomy_ver: int,
    ) -> None:
        self.nodes = tuple(nodes)
        self.fonds = tuple(fonds)
        self.fonds_by_code = {item.code: item for item in fonds}
        self.taxonomy_ver = taxonomy_ver
        self._scope_by_key = {
            (node.site_code, node.level, node.label): node.scope_id for node in nodes
        }

    def roots(self) -> tuple[str, ...]:
        return tuple(item.code for item in self.fonds)

    def fonds_for(self, code: str) -> Fonds:
        try:
            return self.fonds_by_code[code]
        except KeyError as exc:
            raise KeyError(f"unknown activity root {code!r}") from exc

    def scope_id(self, site_code: str, level: int, label: str) -> str:
        try:
            return self._scope_by_key[(site_code, level, label)]
        except KeyError as exc:
            raise KeyError(
                f"no activity node at site {site_code!r} level {level} labelled {label!r}"
            ) from exc

    def rows(self) -> list[dict[str, Any]]:
        return [node.to_row() for node in self.nodes]


def _node(
    site: Site,
    *,
    level: int,
    label: str,
    activity_root: str,
    parent_scope: str | None,
    taxonomy_ver: int,
) -> ActivityNode:
    key = f"{site.code}/{taxonomy_ver}/{level}/{label}"
    return ActivityNode(
        scope_id=str(rng.sid("activity_node", key)),
        site_id=site.site_id,
        site_code=site.code,
        level=level,
        parent_scope=parent_scope,
        label=label,
        activity_root=activity_root,
        taxonomy_ver=taxonomy_ver,
        induced_by="icmm_mue" if level == 1 else "human",
        frozen_node=level == 1,
    )


def build_taxonomy(world: SiteWorld) -> TaxonomyWorld:
    """Materialise the taxonomy for every site."""
    doc = gaz.load("taxonomy")
    taxonomy_ver = int(doc["taxonomy_ver"])
    raw = gaz.as_sequence(doc, "level1", origin="taxonomy.yaml")
    fonds = [Fonds(entry) for entry in raw]

    if not 12 <= len(fonds) <= 25:
        raise gaz.GazetteerError(
            f"taxonomy.yaml declares {len(fonds)} level-1 classes; the register must hold "
            "between 12 and 25 fonds (diachronic-recall.md §3)"
        )
    codes = [item.code for item in fonds]
    if len(set(codes)) != len(codes):
        raise gaz.GazetteerError("taxonomy.yaml: duplicate level-1 code")

    # UNIQUE (site_id, taxonomy_ver, level, label) is per level, so collisions are only checked
    # within a level -- but they are checked before a single row is minted.
    for level, labels in (
        (1, [item.label for item in fonds]),
        (2, [name for item in fonds for name, _ in item.series]),
        (3, [name for item in fonds for _, files in item.series for name in files]),
    ):
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            raise gaz.GazetteerError(
                f"taxonomy.yaml: level-{level} labels are not unique within a site: {duplicates}. "
                "activity_node carries UNIQUE (site_id, taxonomy_ver, level, label)."
            )

    nodes: list[ActivityNode] = []
    for site in world.sites:
        for item in fonds:
            root = _node(
                site,
                level=1,
                label=item.label,
                activity_root=item.code,
                parent_scope=None,
                taxonomy_ver=taxonomy_ver,
            )
            nodes.append(root)
            for series_label, files in item.series:
                series = _node(
                    site,
                    level=2,
                    label=series_label,
                    activity_root=item.code,
                    parent_scope=root.scope_id,
                    taxonomy_ver=taxonomy_ver,
                )
                nodes.append(series)
                for file_label in files:
                    nodes.append(
                        _node(
                            site,
                            level=3,
                            label=file_label,
                            activity_root=item.code,
                            parent_scope=series.scope_id,
                            taxonomy_ver=taxonomy_ver,
                        )
                    )

    scope_ids = [node.scope_id for node in nodes]
    if len(set(scope_ids)) != len(scope_ids):
        raise RuntimeError("activity node scope_id collision; the uuid5 key is not unique")

    return TaxonomyWorld(nodes, fonds, taxonomy_ver)
