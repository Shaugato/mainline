# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Build the four node lists, with the facts each prompt is allowed to see.

Stage 1 left four columns pending with ``corpus-render-cache`` named as the owner:

======================================  =====  ===================================
column                                  count  node kind
======================================  =====  ===================================
``mainline.event.narrative``             1127  ``event_narrative``
``mainline.clause_version.canon_text``   2597  ``clause_text``
``mainline.control_failure.evidence_span`` 2527  bound from ``event_narrative``
``mainline.blame_edge.evidence_quote_sha256`` 238  bound from ``revision_reason``
======================================  =====  ===================================

plus the two the database does not carry but the documents do: the MOC justification block and
the revision-history "reason for change" cell.

------------------------------------------------------------------------------------------
What goes in ``facts``, and why the boundary is sharp
------------------------------------------------------------------------------------------
``facts`` is canonicalised into the cache key.  Anything in it becomes part of the corpus's
identity; anything left out cannot influence a word of the text.  So ``facts`` carries exactly
what a person writing this document would have known — the asset, the energy, the controls that
failed, the era's vocabulary — and carries **no uuid, no digest, no counter and no clock**.
Two consequences, both wanted: the cache is small, and re-running stage 1 with an unrelated
generator added does not re-key a single entry.

Everything the *orchestrator* needs after rendering — the control-failure rows to bind spans
for, the quote refs to digest — travels in ``RenderNode.context``, which is never hashed and
never written.

------------------------------------------------------------------------------------------
Camera-facing
------------------------------------------------------------------------------------------
A node is camera-facing when the film points at it, and the predicate is data, not a list
somebody maintains: an event with ``anchored`` set, a clause revision on the spine clause, a
document revision named in ``spine.json``, or an anchored MOC dossier.  Twenty-one nodes.
Every one of them must resolve to the ``authored`` tier, because ``corpus-spine-authored``
wrote the words that appear on screen and no generator may paraphrase them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from .. import gazetteer as gaz
from . import vocab
from .corpusio import World
from .protocol import RenderNode

__all__ = ["build_nodes", "long_date"]

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def long_date(value: str) -> str:
    """``"2013-06-12"`` or an ISO datetime → ``"12 June 2013"``.

    Written out rather than delegated to ``strftime``: ``%B`` is locale-dependent, and a build
    machine with a non-English locale would silently produce a different corpus.
    """
    day = dt.date.fromisoformat(value[:10])
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def _iso_day(value: str) -> str:
    return value[:10]


def _setpoint_table() -> dict[str, Mapping[str, Any]]:
    setpoints = gaz.load("setpoints")
    return {
        str(entry["key"]): entry
        for entry in gaz.as_sequence(setpoints, "parameters", origin="setpoints.yaml")
    }


def _task_phase(external_ref: str, title: str) -> str:
    """Recover the task phase the skeleton put in the title, or fall back deterministically.

    The phrase is in ``phrases.yaml``'s ``task_phases`` and the skeleton already chose one when
    it built the title.  Reading it back off the title keeps the narrative and the title
    consistent; when a title used a stem without a phase, a stable choice is derived from the
    reference — never a draw, because a draw here would re-key the cache on every unrelated
    change upstream.
    """
    phrases = gaz.load("phrases")
    options = [str(item) for item in gaz.as_sequence(phrases, "task_phases", origin="phrases.yaml")]
    for phase in options:
        if phase in title:
            return phase
    position = sum(external_ref.encode("utf-8")) % len(options)
    return options[position]


def _asset_facts(world: World, tags: Sequence[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tag in tags:
        asset = world.asset_by_tag.get(str(tag))
        if asset is None:
            raise KeyError(f"event names asset {tag!r}, which stage 1 did not build")
        out.append(
            {
                "asset_class": str(asset["asset_class"]),
                "label": str(asset["label"]),
                "service": str(asset["service"]),
                "tag": str(tag),
            }
        )
    return out


# ── event narratives ────────────────────────────────────────────────────────────────────


def _event_nodes(world: World) -> list[RenderNode]:
    nodes: list[RenderNode] = []
    for event, registry in world.iter_events():
        event_id = str(event["event_id"])
        external_ref = str(event["external_ref"])
        occurred = str(event["occurred_at"])
        site = world.site_by_id[str(event["site_id"])]
        failures = sorted(
            world.control_failures_by_event.get(event_id, ()),
            key=lambda row: str(row["control_class"]),
        )
        consequence = dict(event["consequence_proxy"])
        facts = {
            "activity_file": str(registry["activity_file"]),
            "activity_root": str(registry["activity_root"]),
            "activity_series": str(registry["activity_series"]),
            "assets": _asset_facts(world, registry["assets"]),
            "consequence": {
                "days_lost": int(consequence["days_lost"]),
                "injuries": int(consequence["injuries"]),
                "label": str(consequence["label"]),
            },
            "control_failures": [
                {
                    "barrier_role": str(row["barrier_role"]),
                    "control_class": str(row["control_class"]),
                    "control_label": vocab.control_label(str(row["control_class"])),
                    "failure_mode": str(row["failure_mode"]),
                    "hazard_energy": str(row["hazard_energy"]),
                    "icam_tier": str(row["icam_tier"]),
                }
                for row in failures
            ],
            "event_ref": external_ref,
            "hazard_energy": str(registry["hazard_energy"]),
            "hazard_media": list(vocab.hazard_media(str(registry["hazard_energy"]))),
            "hazard_release": vocab.hazard_release(str(registry["hazard_energy"])),
            "kind": str(event["kind"]),
            "occurred_on": _iso_day(occurred),
            "severity_actual": int(event["severity_actual"]),
            "severity_potential": int(event["severity_potential"]),
            "site": str(site["full_name"]),
            "summary_facts": [str(item) for item in registry.get("summary_facts", ())],
            "task_phase": _task_phase(external_ref, str(event["title"])),
            "title": str(event["title"]),
            "vocabulary": vocab.surfaces_for("event_narrative", _iso_day(occurred)),
        }
        nodes.append(
            RenderNode(
                kind="event_narrative",
                key=external_ref,
                facts=facts,
                camera_facing=bool(registry.get("anchored")),
                context={
                    "event_id": event_id,
                    "control_failures": [dict(row) for row in failures],
                    "site_code": str(site["code"]),
                },
            )
        )
    return nodes


# ── clause bodies ───────────────────────────────────────────────────────────────────────


def _clause_nodes(world: World) -> list[RenderNode]:
    setpoints = _setpoint_table()
    spine_clause_key = str(world.spine.get("clause_key", ""))
    nodes: list[RenderNode] = []
    for revision in sorted(
        world.clause_revisions, key=lambda row: (str(row["revision_key"]), str(row["clause_key"]))
    ):
        clause_key = str(revision["clause_key"])
        registry = world.clause_registry_by_key[clause_key]
        revision_key = str(revision["revision_key"])
        doc_revision = world.doc_revision_by_key[revision_key]
        doc_id = str(doc_revision["doc_id"])
        doc = world.doc_by_id[doc_id]
        doc_meta = world.doc_registry_by_id[doc_id]
        effective_on = str(revision["effective_on"])
        control_class = str(registry["control_class"])

        setpoint_key = revision.get("setpoint_key") or registry.get("setpoint_key")
        setpoint_facts: dict[str, Any] | None = None
        if setpoint_key:
            parameter = setpoints[str(setpoint_key)]
            setpoint_facts = {
                "from": revision.get("setpoint_from"),
                "key": str(setpoint_key),
                "label": str(parameter["label"]),
                "strengthen_direction": str(parameter["strengthen_direction"]),
                "to": revision.get("setpoint_to"),
                "unit": str(parameter["unit_display"]),
            }

        facts = {
            "activity_root": str(registry["activity_root"]),
            "barrier_role": str(registry["barrier_role"]),
            "control_class": control_class,
            "control_delta": str(revision["control_delta"]),
            "control_label": vocab.control_label(control_class),
            "doc_code": str(revision["doc_code"]),
            "doc_family": str(doc_meta["family"]),
            "doc_title": str(doc["title"]),
            "effective_on": effective_on,
            "printed_label": str(revision["printed_label"]),
            "setpoint": setpoint_facts,
            "site": str(world.site_by_id[str(revision["site_id"])]["full_name"]),
            "template_generation": int(revision["template_generation"]),
            "vocabulary": vocab.surfaces_for("clause_text", effective_on),
        }
        nodes.append(
            RenderNode(
                kind="clause_text",
                key=f"{revision_key}#{clause_key}",
                facts=facts,
                camera_facing=clause_key == spine_clause_key,
                context={
                    "clause_key": clause_key,
                    "clause_uuid": str(revision["clause_uuid"]),
                    "revision_key": revision_key,
                    "ordinal": int(revision["ordinal"]),
                    "printed_label": str(revision["printed_label"]),
                },
            )
        )
    return nodes


# ── MOC justifications ──────────────────────────────────────────────────────────────────


def _moc_nodes(world: World) -> list[RenderNode]:
    nodes: list[RenderNode] = []
    for dossier in sorted(world.moc_dossiers, key=lambda row: str(row["external_ref"])):
        opened_on = _iso_day(str(dossier["opened_at"]))
        precursors = [
            {
                "event_ref": str(item["event_ref"]) if isinstance(item, dict) else str(item),
                "severity_gate": item.get("severity_gate") if isinstance(item, dict) else None,
            }
            for item in dossier.get("precursor_events", ())
        ]
        facts = {
            "clause_count": int(dossier["clause_count"]),
            "doc_codes": [str(code) for code in dossier["doc_codes"]],
            "intent": str(dossier["intent"]),
            "moc_ref": str(dossier["external_ref"]),
            "opened_on": opened_on,
            "precursor_events": precursors,
            "site": str(world.site_by_id[str(dossier["site_id"])]["full_name"]),
            "terminal_state": str(dossier["terminal_state"]),
            "vocabulary": vocab.surfaces_for("moc_justification", opened_on),
            "weakening_steps": int(dossier["weakening_steps"]),
        }
        nodes.append(
            RenderNode(
                kind="moc_justification",
                key=str(dossier["external_ref"]),
                facts=facts,
                camera_facing=bool(dossier.get("anchored")),
                context={"cr_id": str(dossier["cr_id"]), "site_code": str(dossier["site_code"])},
            )
        )
    return nodes


# ── revision reasons ────────────────────────────────────────────────────────────────────


def _revision_nodes(world: World) -> list[RenderNode]:
    event_titles = {str(row["external_ref"]): str(row["title"]) for row in world.events}
    nodes: list[RenderNode] = []
    for revision in sorted(world.doc_revisions, key=lambda row: str(row["revision_key"])):
        revision_key = str(revision["revision_key"])
        doc_id = str(revision["doc_id"])
        doc = world.doc_by_id[doc_id]
        doc_meta = world.doc_registry_by_id[doc_id]
        effective_on = str(revision["effective_on"])
        citations = [
            {
                "control_label": (
                    vocab.control_label(str(item["control_class"]))
                    if item.get("control_class")
                    else None
                ),
                "event_ref": item["event_ref"],
                "event_title": event_titles.get(str(item["event_ref"]), ""),
                "hazard_energy": item.get("hazard_energy"),
                "kind": item["kind"],
                "quote_ref": item["quote_ref"],
                "severity_gate": item.get("severity_gate"),
            }
            for item in world.quote_refs_by_revision.get(revision_key, ())
        ]
        facts = {
            "clauses_touched": len(world.clause_revisions_by_revision.get(revision_key, ())),
            "doc_code": str(revision["doc_code"]),
            "doc_family": str(doc_meta["family"]),
            "doc_title": str(doc["title"]),
            "driver": str(revision["driver"]),
            "driving_change_ref": revision.get("driving_change_ref"),
            "driving_event_ref": revision.get("driving_event_ref"),
            "effective_on": effective_on,
            "required_citations": citations,
            "rev_no": int(revision["rev_no"]),
            "site": str(world.site_by_id[str(revision["site_id"])]["full_name"]),
            "template_generation": int(revision["template_generation"]),
            "vocabulary": vocab.surfaces_for("revision_reason", effective_on),
        }
        nodes.append(
            RenderNode(
                kind="revision_reason",
                key=revision_key,
                facts=facts,
                camera_facing=revision_key in world.spine_revision_keys,
                context={
                    "doc_id": doc_id,
                    "revision_key": revision_key,
                    "quote_refs": [dict(item) for item in citations],
                },
            )
        )
    return nodes


def build_nodes(world: World) -> list[RenderNode]:
    """Every render node, in a fixed order: by kind, then by key.

    The order is the order entries are written and the order the census counts, so it must not
    depend on a dict's insertion order or on which generator ran first.
    """
    nodes = [
        *_clause_nodes(world),
        *_event_nodes(world),
        *_moc_nodes(world),
        *_revision_nodes(world),
    ]
    nodes.sort(key=lambda node: (node.kind, node.key))
    seen: set[str] = set()
    for node in nodes:
        if node.node_id in seen:
            raise ValueError(
                f"duplicate node id {node.node_id!r}. A node id is a natural key; two nodes "
                "sharing one would share a cache entry and the census would under-count."
            )
        seen.add(node.node_id)
    return nodes
