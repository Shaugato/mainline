# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The M5 THYMOGATE panel — the fleet's known killers, promiscuously expressed.

The analogy is AIRE. In the thymic medulla, the autoimmune regulator drives *promiscuous
gene expression*: tissue-restricted antigens from all over the body are displayed in one
place, so that a lymphocyte which would fail catastrophically in the periphery fails
harmlessly here instead. Negative selection happens against a curated presentation of
everything that matters, not against whatever the organism happens to encounter.

The panel is that presentation. It is a small, curated set of the fleet's known killers —
**one per hazard-energy class, at mixed archival levels** — and a retrieval configuration
is certified only if it recalls **every** one. Not most. Every.

Why one per hazard-energy class
--------------------------------
A retriever tuned on a corpus dominated by mobile-plant incidents will be excellent at
kinetic energy and blind to radiation, and its aggregate recall will look fine because
radiation is rare. Aggregate metrics average over exactly the failure that kills someone.
Requiring one item per class turns "rare" from a discount into an obligation: the eight
classes are the vertical's own ``control_failure.hazard_energy`` CHECK list, so the panel
covers the whole space the schema admits.

Why mixed levels
----------------
Level-Materialised Bonds make one arm per ancestor both correct and necessary. A
configuration that only ever matches at file level (level 3) would pass a file-only panel
and would miss every fatality whose bond sits at the series or fonds level. Mixing the
levels makes that failure visible instead of averaged away.

Why the panel is a corpus artefact
-----------------------------------
Recall lead D14: THYMOGATE lives with the harness, not the retriever. If the retriever
owned the panel, a tuned retriever would certify itself. The panel is built here, from
the corpus, and the certificate is emitted by a run — see
:mod:`trappoint_recall.corpora.thymogate`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trappoint_recall.corpora.canonical import digest_hex
from trappoint_recall.corpora.g4_retro import RetroPermit
from trappoint_recall.corpora.model import HAZARD_ENERGY_CLASSES, EventRecordSet, HazardEnergy
from trappoint_recall.eval.corpus import EvalQuery

__all__ = [
    "PANEL_SCHEMA_VERSION",
    "Panel",
    "PanelError",
    "PanelItem",
    "ScopeLevel",
    "build_panel",
    "load_panel",
    "save_panel",
]

PANEL_SCHEMA_VERSION: Final = 1

ScopeLevel = Literal[1, 2, 3]
"""1 fonds, 2 series, 3 file — the archival level at which the bond is asserted."""


class PanelError(ValueError):
    """Raised when a panel is incomplete, duplicated, or fails its coverage obligation."""


class PanelItem(BaseModel):
    """One known killer the configuration must recall."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: Annotated[str, Field(min_length=1, description="Stable id, e.g. TG-gravity-01.")]
    hazard_energy: HazardEnergy
    scope_level: Annotated[
        int, Field(ge=1, le=3, description="1 fonds, 2 series, 3 file. Mixed across the panel.")
    ]
    query_id: Annotated[str, Field(min_length=1)]
    permit_text: Annotated[
        str,
        Field(
            min_length=1,
            description="The permit presented to the configuration. Carries no outcome.",
        ),
    ]
    site_id: Annotated[str, Field(min_length=1)]
    activity_path: Annotated[str, Field(min_length=1)]
    asset_class: Annotated[str, Field(min_length=1)]
    must_recall_doc_id: Annotated[
        str,
        Field(
            min_length=1,
            description="The event that must come back. Missing it fails certification.",
        ),
    ]
    wall: Annotated[
        datetime,
        Field(
            description=(
                "The time wall of the fatality this item was drawn from. THYMOGATE runs "
                "under the same temporal discipline as every other measurement: a "
                "certificate earned by letting the configuration see the fatality it is "
                "supposed to have predicted certifies nothing."
            )
        ),
    ]
    severity: Annotated[int, Field(ge=1, le=5, description="Panel members are severity 5.")]
    rationale: Annotated[
        str,
        Field(
            min_length=1,
            description="Why this item is on the panel, in one sentence a stranger can read.",
        ),
    ]

    @model_validator(mode="after")
    def _panel_members_are_fatal(self) -> PanelItem:
        if self.severity != 5:
            raise ValueError(
                f"{self.item_id}: panel members are the fleet's known killers, so severity "
                f"must be 5, got {self.severity}. A panel of near misses certifies a "
                "system against the wrong population."
            )
        return self

    def to_eval_query(self) -> EvalQuery:
        """The permit, in the harness's query type, for running a configuration."""
        return EvalQuery(
            query_id=self.query_id,
            kind="retro",
            text=self.permit_text,
            site_id=self.site_id,
            activity_path=self.activity_path,
            asset_class=self.asset_class,
            severity=self.severity,
            wall=self.wall,
            truth_doc_id=self.must_recall_doc_id,
            bonded_sev5=(),
            facets={"narrative": self.permit_text},
            blinded=True,
        )

    def canonical(self) -> dict[str, object]:
        """The projection the panel digest is taken over.

        Deliberately excludes ``rationale``: reworded prose must not change the digest,
        because a certificate that expires when someone fixes a typo is a certificate
        people learn to ignore.
        """
        return {
            "item_id": self.item_id,
            "hazard_energy": self.hazard_energy,
            "scope_level": self.scope_level,
            "query_id": self.query_id,
            "permit_text": self.permit_text,
            "site_id": self.site_id,
            "activity_path": self.activity_path,
            "asset_class": self.asset_class,
            "must_recall_doc_id": self.must_recall_doc_id,
            "wall": self.wall.astimezone(UTC).isoformat(),
            "severity": self.severity,
        }


class Panel(BaseModel):
    """The full panel, its provenance, and its digest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = PANEL_SCHEMA_VERSION
    panel_id: Annotated[str, Field(min_length=1)]
    corpus_commit: Annotated[
        str,
        Field(min_length=1, description="Corpus state the panel was drawn from."),
    ]
    built_by: Annotated[str, Field(min_length=1)]
    statement: Annotated[
        str,
        Field(
            min_length=1,
            description="What certification means and what it does not. Rendered wherever "
            "a certificate is shown.",
        ),
    ]
    items: Annotated[Sequence[PanelItem], Field(min_length=1)]

    @model_validator(mode="after")
    def _complete_and_mixed(self) -> Panel:
        ids = [item.item_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate item_id in panel; a duplicated item is counted twice")
        covered = {item.hazard_energy for item in self.items}
        missing = [h for h in HAZARD_ENERGY_CLASSES if h not in covered]
        if missing:
            raise ValueError(
                f"panel does not cover hazard energy classes {missing}. Aggregate recall "
                "averages over exactly the class that kills someone; the panel exists to "
                "make each class an obligation rather than a discount."
            )
        levels = {item.scope_level for item in self.items}
        if len(levels) < 2:
            raise ValueError(
                f"panel uses only scope level(s) {sorted(levels)}. A single-level panel "
                "certifies a configuration that matches at one archival level and misses "
                "every bond above or below it."
            )
        return self

    @property
    def digest(self) -> str:
        """Hex sha256 over the canonical projection of the ordered items."""
        return digest_hex(
            {
                "schema_version": self.schema_version,
                "panel_id": self.panel_id,
                "corpus_commit": self.corpus_commit,
                "items": [item.canonical() for item in self.ordered_items],
            }
        )

    @property
    def ordered_items(self) -> tuple[PanelItem, ...]:
        return tuple(sorted(self.items, key=lambda i: i.item_id))

    @property
    def hazard_coverage(self) -> Mapping[str, int]:
        counts: dict[str, int] = {h: 0 for h in HAZARD_ENERGY_CLASSES}
        for item in self.items:
            counts[item.hazard_energy] += 1
        return dict(counts)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "panel_id": self.panel_id,
            "corpus_commit": self.corpus_commit,
            "built_by": self.built_by,
            "statement": self.statement,
            "items": [item.model_dump(mode="json") for item in self.ordered_items],
        }
        payload["panel_digest"] = self.digest
        return payload


PANEL_STATEMENT: Final = (
    "A THYMOGATE certificate says that this exact retrieval configuration recalled every "
    "member of this exact panel. It does not say the configuration recalls every "
    "precursor in the corpus, and it does not survive a change to either the "
    "configuration or the panel: both digests are bound into the certificate. A "
    "configuration that misses any panel member cannot be certified at all."
)


def build_panel(
    permits: Sequence[RetroPermit],
    records: EventRecordSet,
    *,
    corpus_commit: str,
    panel_id: str = "TG-PANEL-1",
    built_by: str = "trappoint_recall.corpora.panel",
) -> Panel:
    """Curate one panel item per hazard-energy class from the retro permits.

    Selection is deterministic and stated rather than clever: for each hazard-energy
    class, take the *earliest* retro permit whose subject event carries that class, so the
    panel is stable as the corpus grows at the head. Scope levels are assigned round-robin
    over the class order, which guarantees a mix without letting the corpus's own shape
    decide whether the panel is single-level.

    Raises:
        PanelError: when a hazard-energy class has no severity-5 retro permit. That is a
            corpus gap, and it must be visible: a panel quietly built over six of eight
            classes would certify configurations that are blind to the other two.
    """
    by_ref = {p.event_ref: p for p in permits}
    chosen: dict[HazardEnergy, RetroPermit] = {}
    for record in sorted(records.fatal(), key=lambda r: (r.occurred_at, r.external_ref)):
        permit = by_ref.get(record.external_ref)
        if permit is None:
            continue
        chosen.setdefault(record.hazard_energy, permit)

    missing = [h for h in HAZARD_ENERGY_CLASSES if h not in chosen]
    if missing:
        raise PanelError(
            f"no severity-5 retro permit for hazard energy class(es) {missing}. The panel "
            "must cover all eight classes of the vertical's control_failure CHECK list; "
            "building it over fewer would certify a configuration that is blind to the "
            "classes the corpus happens to be thin on."
        )

    items: list[PanelItem] = []
    for index, hazard in enumerate(HAZARD_ENERGY_CLASSES):
        permit = chosen[hazard]
        subject = records.get(permit.event_ref)
        if subject is None:  # pragma: no cover - permits come from records
            raise PanelError(f"panel item {hazard}: event {permit.event_ref} is not in the corpus")
        items.append(
            PanelItem(
                item_id=f"TG-{hazard}-{index + 1:02d}",
                hazard_energy=hazard,
                scope_level=(index % 3) + 1,
                query_id=f"Q-TG-{hazard}",
                permit_text=permit.text,
                site_id=permit.site_ref,
                activity_path=permit.activity_path,
                asset_class=permit.asset_class,
                must_recall_doc_id=permit.truth_doc_id,
                wall=permit.wall,
                severity=5,
                rationale=(
                    f"{hazard} energy: {subject.title}. The precursor "
                    f"{permit.truth_doc_id} preceded a fatality on this activity; a "
                    "configuration that does not recall it is not certified."
                ),
            )
        )
    return Panel(
        panel_id=panel_id,
        corpus_commit=corpus_commit,
        built_by=built_by,
        statement=PANEL_STATEMENT,
        items=tuple(items),
    )


def save_panel(panel: Panel, path: Path | str) -> Path:
    """Write the panel as pretty JSON with its digest, plus a REUSE licence sidecar."""
    from trappoint_recall.corpora.emit import write_json

    return write_json(path, panel.to_dict())


def load_panel(path: Path | str) -> Panel:
    """Load a panel and verify its recorded digest still matches its contents.

    Raises:
        PanelError: on a digest mismatch. A panel whose digest drifted from its contents
            would let a stale certificate look current.
    """
    source = Path(path)
    if not source.is_file():
        raise PanelError(f"panel not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PanelError(f"{source}: expected a JSON object")
    recorded = payload.pop("panel_digest", None)
    panel = Panel.model_validate(payload)
    if recorded is not None and recorded != panel.digest:
        raise PanelError(
            f"{source}: recorded panel_digest {recorded} does not match the digest of the "
            f"contents {panel.digest}. Every certificate bound to the recorded digest is "
            "now unverifiable; rebuild the panel and re-certify rather than editing it."
        )
    return panel
