# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Controlled documents and their revision cadence.

``mainline.doc`` (migration band 0027) plus a corpus-scaffolding revision stream.

``doc.open_token_count`` is a **projected** column — a trigger writes it from the control series
the document still carries, and ``no_orphan_controls`` reads it to refuse superseding a document
that is still carrying controls.  It is not emitted, and the emitter would refuse it if it were.

Every document is emitted ``state: 'live'``.  Supersession is deliberately left to
``corpus-blame-key``'s document-split injector, because a superseded document must have
``open_token_count = 0`` and only the worker that moves the control series knows when that is
true.  A skeleton that guessed would produce a corpus that fails to load for a reason that has
nothing to do with the skeleton.

── The revision cadence ─────────────────────────────────────────────────────────────────────
Each document's cadence is authored (``cadence_years`` in ``documents.yaml``) and jittered from
a per-document stream, so adding a document does not move any other document's revision dates.
Three kinds of revision exist and they are marked, because ``corpus-blame-key`` needs to know
which revisions are *candidates* for a documentary blame edge:

* ``routine_review``  — the cadence fired.
* ``incident``        — the revision landed inside ``REVISION_INCIDENT_WINDOW_DAYS`` of a
                        severity-4-or-worse event at the same site, in the same fonds.  This is a
                        **structural hint, not an answer key.**  The answer key is authored by
                        the worker that authors causality; a skeleton that emitted blame edges
                        would be marking its own homework.
* ``retypeset``       — the 2016 full retypeset, one date for every document that had one.

Anchored revisions (the spine's five dates) are planted and merged with the drawn cadence.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from . import clock, params
from .events import EventWorld
from .model import Doc, DocRevision
from .people import PeopleWorld
from .sites import SiteWorld

__all__ = ["DocumentWorld", "build_documents"]

_SINGLE_ISSUE_FAMILIES: frozenset[str] = frozenset({"MOC", "ALERT"})


class DocumentWorld:
    __slots__ = ("_by_code", "docs", "revisions")

    def __init__(self, docs: Sequence[Doc], revisions: Sequence[DocRevision]) -> None:
        self.docs = tuple(docs)
        self.revisions = tuple(revisions)
        index: dict[tuple[str, str], Doc] = {}
        for doc in docs:
            index[(doc.site_code, doc.doc_code)] = doc
        self._by_code = index

    def get(self, site_code: str, doc_code: str) -> Doc:
        return self._by_code[(site_code, doc_code)]

    def at(self, site_code: str) -> tuple[Doc, ...]:
        return tuple(doc for doc in self.docs if doc.site_code == site_code)

    def for_fonds(self, site_code: str, activity_root: str) -> tuple[Doc, ...]:
        return tuple(doc for doc in self.at(site_code) if doc.activity_root == activity_root)

    def rows(self) -> list[dict[str, Any]]:
        return [doc.to_row() for doc in self.docs]

    def registry_rows(self) -> list[dict[str, Any]]:
        return [doc.to_registry_row() for doc in self.docs]

    def revision_rows(self) -> list[dict[str, Any]]:
        return [revision.to_row() for revision in self.revisions]


#: The closed set of revision drivers.  Emitting anything else would give `corpus-blame-key` a
#: value it has no rule for, and a silent unknown in a provenance-adjacent field is exactly the
#: kind of thing that turns into a wrong blame edge three workers downstream.
REVISION_DRIVERS: frozenset[str] = frozenset(
    {"routine_review", "incident", "regulator", "moc", "retypeset", "introduce"}
)


@dataclass(frozen=True, slots=True)
class _AnchoredRevision:
    driver: str
    author: str | None
    driven_by_event: str | None
    driven_by_change: str | None


def _anchored_revisions(
    gaz_anchors: Mapping[str, Any],
) -> dict[tuple[str, str], dict[dt.date, _AnchoredRevision]]:
    """The spine's dated revisions, keyed by ``(site_code, doc_code)``.

    Only dates, drivers, authorship and the structural pointer to what drove each one.  The
    commit message and the clause body belong to the hand-authored fixtures and are deliberately
    not duplicated here: ``test_camera_strings_agree`` checks that string across four files, and
    a fifth copy would be a fifth thing that can drift.
    """
    spine = gaz.as_mapping(gaz_anchors, "spine", origin="anchors.yaml")
    site = str(spine["site"])
    origin_doc = str(spine["document_origin"])
    split_doc = str(spine["document_after_split"])
    split_on = clock.coerce_date(
        gaz.as_mapping(spine, "dates", origin="anchors.yaml/spine")["split"],
        origin="anchors.yaml/spine/dates/split",
    )

    origin_revisions: dict[dt.date, _AnchoredRevision] = {}
    for entry in gaz.as_sequence(spine, "revisions", origin="anchors.yaml/spine"):
        driver = str(entry["driver"])
        if driver not in REVISION_DRIVERS:
            raise gaz.GazetteerError(
                f"anchors.yaml: revision driver {driver!r} is not in {sorted(REVISION_DRIVERS)}"
            )
        # The key is `effective_on`, not `on`: YAML 1.1 resolves a bare `on` to the boolean
        # `true`, so `{on: 2011-03-14}` parses with the key `True` and the lookup silently fails.
        day = clock.coerce_date(entry["effective_on"], origin="anchors.yaml/spine/revisions")
        origin_revisions[day] = _AnchoredRevision(
            driver=driver,
            author=None if entry.get("author") is None else str(entry["author"]),
            driven_by_event=(
                None if entry.get("driven_by_event") is None else str(entry["driven_by_event"])
            ),
            driven_by_change=(
                None if entry.get("driven_by_change") is None else str(entry["driven_by_change"])
            ),
        )

    return {
        (site, origin_doc): origin_revisions,
        (site, split_doc): {
            split_on: _AnchoredRevision(
                driver="moc",
                author=None,
                driven_by_event=None,
                driven_by_change="MOC-2019-0221",
            )
        },
    }


def _cadence_dates(
    stream: rng.Stream, *, first_issued: dt.date, cadence_years: float
) -> list[dt.date]:
    """Revision dates from ``first_issued`` to ``NOW`` at the authored cadence, jittered."""
    dates = [first_issued]
    if cadence_years <= 0.0:
        return dates
    low, high = params.REVISION_INTERVAL_JITTER
    cursor = first_issued
    horizon = clock.NOW.date()
    while True:
        factor = low + rng.unit(stream) * (high - low)
        step_days = max(30, round(cadence_years * factor * 365.25))
        cursor = cursor + dt.timedelta(days=step_days)
        if cursor >= horizon:
            break
        dates.append(cursor)
    return dates


def build_documents(world: SiteWorld, people: PeopleWorld, events: EventWorld) -> DocumentWorld:
    """Materialise the 36 documents and their revision streams."""
    doc_file = gaz.load("documents")
    expected = int(doc_file["expected_row_count"])
    entries = gaz.as_sequence(doc_file, "documents", origin="documents.yaml")
    anchors = _anchored_revisions(gaz.load("anchors"))
    retypeset_on = dt.date.fromisoformat(params.RETYPESET_DATE)

    docs: list[Doc] = []
    for entry in entries:
        code = str(entry["code"])
        for site_code in (str(item) for item in entry["sites"]):
            site = world.by_code(site_code)
            docs.append(
                Doc(
                    doc_id=str(rng.sid("doc", f"{site_code}/{code}")),
                    site_id=site.site_id,
                    site_code=site_code,
                    doc_code=code,
                    title=str(entry["title"]),
                    family=str(entry["family"]),
                    activity_root=str(entry["mue"]),
                    asset_classes=tuple(str(item) for item in entry["asset_classes"]),
                    first_issued=clock.coerce_date(
                        entry["first_issued"], origin=f"documents.yaml/{code}/first_issued"
                    ),
                    cadence_years=float(entry["cadence_years"]),
                    retypeset_2016=bool(entry["retypeset_2016"]),
                    state="live",
                    superseded_by=None,
                    anchor=None if entry.get("anchor") is None else str(entry["anchor"]),
                    fleet_sibling=bool(entry.get("fleet_sibling", False)),
                    template_generation=int(entry["template_generation"]),
                )
            )

    if len(docs) != expected:
        raise gaz.GazetteerError(
            f"documents.yaml flattens to {len(docs)} rows but declares expected_row_count "
            f"{expected}. The census the honesty card quotes comes from this number, so a "
            "silent drift here would make the card wrong."
        )
    if len(docs) != params.DOC_TARGET:
        raise RuntimeError(
            f"documents.yaml yields {len(docs)} documents; params.DOC_TARGET is {params.DOC_TARGET}"
        )

    revisions: list[DocRevision] = []
    for doc in sorted(docs, key=lambda item: (item.site_code, item.doc_code)):
        stream = rng.sub_stream("doc.cadence", f"{doc.site_code}/{doc.doc_code}")
        author_stream = rng.sub_stream("doc.author", f"{doc.site_code}/{doc.doc_code}")

        if doc.family in _SINGLE_ISSUE_FAMILIES:
            dates: list[dt.date] = [doc.first_issued]
        else:
            dates = _cadence_dates(
                stream, first_issued=doc.first_issued, cadence_years=doc.cadence_years
            )

        planned: dict[dt.date, _AnchoredRevision] = {
            day: _AnchoredRevision("routine_review", None, None, None) for day in dates
        }
        if doc.retypeset_2016 and doc.first_issued < retypeset_on:
            planned[retypeset_on] = _AnchoredRevision("retypeset", None, None, None)
        planned.update(anchors.get((doc.site_code, doc.doc_code), {}))

        site_majors = [
            event
            for event in events.major_events_at(doc.site_code)
            if event.activity_root == doc.activity_root
        ]

        for rev_no, day in enumerate(sorted(planned), start=1):
            anchored = planned[day]
            driver = anchored.driver
            author = anchored.author
            driving_ref = anchored.driven_by_event
            driving_change = anchored.driven_by_change
            if driver == "routine_review":
                for event in site_majors:
                    delta = (day - event.occurred_at.date()).days
                    if 0 < delta <= params.REVISION_INCIDENT_WINDOW_DAYS:
                        driver = "incident"
                        driving_ref = event.external_ref
                        break

            if author is None:
                moment = dt.datetime(day.year, day.month, day.day, 9, 0, tzinfo=clock.TZ)
                candidates = people.authors_at(doc.site_code, moment)
                if not candidates:
                    candidates = tuple(
                        person for person in people.at(doc.site_code) if person.rank >= 2
                    )
                if not candidates:
                    raise RuntimeError(
                        f"no eligible author at {doc.site_code} for {doc.doc_code} rev {rev_no}"
                    )
                author = rng.pick(author_stream, candidates).signer_sub

            generation = (
                2 if (doc.retypeset_2016 and day >= retypeset_on) else doc.template_generation
            )
            if driver not in REVISION_DRIVERS:
                raise RuntimeError(f"{doc.doc_code} rev {rev_no}: unknown driver {driver!r}")
            revisions.append(
                DocRevision(
                    revision_key=f"{doc.site_code}/{doc.doc_code}/{rev_no:03d}",
                    doc_id=doc.doc_id,
                    doc_code=doc.doc_code,
                    site_id=doc.site_id,
                    rev_no=rev_no,
                    effective_on=day,
                    driver=driver,
                    author_sub=author,
                    template_generation=generation,
                    driving_event_ref=driving_ref,
                    driving_change_ref=driving_change,
                )
            )

    docs.sort(key=lambda item: (item.site_code, item.doc_code))
    revisions.sort(key=lambda item: item.revision_key)
    return DocumentWorld(docs, revisions)
