# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Injector 2 — document split and clause migration.  Eight documents, 2019.

**Proves:** blame crosses document boundaries.  A clause that carries a 2013 fatality's blame
and then moves into a different standard six years later is the case every "attach the incident
to the document" system gets wrong, because it filed the lesson against a filename.

The spine's split is planted: ``MOC-2019-0221`` moves clauses out of ``PRO-MEC-014`` into
``STD-ISO-006`` on 2019-02-19, and stage 1 already scheduled a revision of both documents on
that date.  The other seven are selected from documents that stage 1 happened to reissue in
2019 — selection, not invention, so the split lands on a revision the cadence produced rather
than on a date this injector wished into existence.

── TWO DELIBERATE RESTRAINTS ─────────────────────────────────────────────────────────────────

**No document is superseded.**  Every split here is partial: the source document survives and
keeps most of its obligations.  ``doc.state = 'superseded'`` requires ``open_token_count = 0``,
and ``open_token_count`` is a PROJECTED column written by a trigger from the control series the
document still carries.  A corpus that flipped a document to superseded would be asserting a
projection it cannot evidence — decision D8, one hop upstream.  ``doc.jsonl`` is stage 1's file
and this injector does not touch it.

**The migration is atomic on the source document's revision date.**  The receiving document
reflows its own numbering at its next scheduled issue, which is what actually happens: the
change record has one effective date, and the document that inherits the clauses renumbers when
it is next printed.  Modelling a limbo window in which the clause is in both documents, or in
neither, would put a genuine document-control pathology into a corpus that is meant to be the
*clean* case against which the pathologies are measured.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from ..skeleton import clock
from ..skeleton.build import Skeleton
from ..skeleton.model import Doc, DocRevision

__all__ = ["SplitPlan", "plan", "schedule_rows"]

#: Families that may receive migrated clauses.  A one-page safety alert and a single-issue MOC
#: record are not documents obligations migrate *into*; they are the record of a change.
_RECEIVING_FAMILIES: frozenset[str] = frozenset({"PRO", "STD", "PTW"})


@dataclass(frozen=True, slots=True)
class SplitPlan:
    """One document split: which clauses leave, when, and under whose change record."""

    source_site: str
    source_doc_code: str
    source_doc_id: str
    target_doc_code: str
    target_doc_id: str
    effective_on: dt.date
    source_revision_key: str
    target_reflow_revision_key: str | None
    change_ref: str
    migration_fraction: float
    anchored: bool

    @property
    def key(self) -> str:
        return f"{self.source_site}/{self.source_doc_code}->{self.target_doc_code}"


def _anchor_facts() -> tuple[str, str, str, str, dt.date]:
    """``(site, source doc, target doc, change ref, date)`` for the planted spine split."""
    spine = gaz.as_mapping(gaz.load("anchors"), "spine", origin="anchors.yaml")
    dates = gaz.as_mapping(spine, "dates", origin="anchors.yaml/spine")
    return (
        str(spine["site"]),
        str(spine["document_origin"]),
        str(spine["document_after_split"]),
        "MOC-2019-0221",
        clock.coerce_date(dates["split"], origin="anchors.yaml/spine/dates/split"),
    )


def _revisions_by_doc(skeleton: Skeleton) -> dict[tuple[str, str], tuple[DocRevision, ...]]:
    grouped: dict[tuple[str, str], list[DocRevision]] = {}
    for revision in skeleton.documents.revisions:
        site_code = revision.revision_key.split("/", 1)[0]
        grouped.setdefault((site_code, revision.doc_code), []).append(revision)
    return {key: tuple(sorted(items, key=lambda r: r.rev_no)) for key, items in grouped.items()}


def _change_ref_for(skeleton: Skeleton, site_code: str, on: dt.date) -> str:
    """Find the change record nearest ``on`` at ``site_code``.

    A split is a change, and a change that no MOC records is a change nobody approved.  The
    nearest existing MOC is used rather than a minted one, because ``change_request`` is stage
    1's table exactly as ``event`` is.
    """
    candidates = [cr for cr in skeleton.mocs.change_requests if cr.site_code == site_code]
    if not candidates:
        raise RuntimeError(
            f"site {site_code} has no change request to record a document split against; a "
            "migration with no change record is a change nobody approved"
        )
    target = dt.datetime(on.year, on.month, on.day, tzinfo=clock.TZ)
    return min(
        candidates,
        key=lambda cr: (abs((cr.opened_at - target).total_seconds()), cr.external_ref),
    ).external_ref


def _target_for(
    doc: Doc,
    *,
    site_docs: Sequence[Doc],
    excluded: set[str],
    stream: rng.Stream,
) -> Doc | None:
    """Pick the document that receives ``doc``'s migrating clauses.

    Preference order, and each step is a statement about how real document sets are cut up:
    a *standard* absorbs obligations a *procedure* sheds; a document covering the same asset
    classes is where a maintainer would look first; and a document already chosen as a split
    source is never a target, because a corpus in which obligations chain through three
    documents in one year is not testing migration, it is testing the generator.
    """
    pool = [
        other
        for other in site_docs
        if other.doc_code != doc.doc_code
        and other.doc_code not in excluded
        and other.family in _RECEIVING_FAMILIES
        # A receiving document must reach the post-2016 numbering, or a clause that arrives in
        # 2019 has no generation-2 label to be printed under and the migration cannot be shown.
        and (other.retypeset_2016 or other.template_generation >= 2)
    ]
    if not pool:
        return None
    shared = [other for other in pool if set(other.asset_classes) & set(doc.asset_classes)] or pool
    standards = [other for other in shared if other.family == "STD"] or shared
    return rng.pick(stream, sorted(standards, key=lambda item: item.doc_code))


def plan(skeleton: Skeleton) -> tuple[SplitPlan, ...]:
    """Choose the eight splits.  Deterministic; the spine's is always first."""
    from ..blame import params

    site_of_doc = {doc.doc_id: doc.site_code for doc in skeleton.documents.docs}
    revisions = _revisions_by_doc(skeleton)
    anchor_site, anchor_source, anchor_target, anchor_change, anchor_date = _anchor_facts()

    plans: list[SplitPlan] = []
    excluded: set[str] = {anchor_source, anchor_target}
    stream = rng.stream("injector.split")

    def _reflow_key(site_code: str, doc_code: str, on: dt.date) -> str | None:
        stream_revisions = revisions.get((site_code, doc_code), ())
        later = [r for r in stream_revisions if r.effective_on >= on]
        return later[0].revision_key if later else None

    source = skeleton.documents.get(anchor_site, anchor_source)
    target = skeleton.documents.get(anchor_site, anchor_target)
    anchor_revision = next(
        (
            revision
            for revision in revisions[(anchor_site, anchor_source)]
            if revision.effective_on == anchor_date
        ),
        None,
    )
    if anchor_revision is None:
        raise RuntimeError(
            f"stage 1 scheduled no {anchor_source} revision on {anchor_date}; the spine's split "
            "is an authored anchor and the cadence must carry it"
        )
    plans.append(
        SplitPlan(
            source_site=anchor_site,
            source_doc_code=anchor_source,
            source_doc_id=source.doc_id,
            target_doc_code=anchor_target,
            target_doc_id=target.doc_id,
            effective_on=anchor_date,
            source_revision_key=anchor_revision.revision_key,
            target_reflow_revision_key=_reflow_key(anchor_site, anchor_target, anchor_date),
            change_ref=anchor_change,
            migration_fraction=0.26,
            anchored=True,
        )
    )

    # Candidates: any document stage 1 reissued in the split year, biggest families first so a
    # migration has enough clauses to be visible in a two-second shot.
    candidates: list[tuple[str, str, DocRevision]] = []
    for (site_code, doc_code), items in sorted(revisions.items()):
        if doc_code in excluded:
            continue
        doc = skeleton.documents.get(site_code, doc_code)
        if doc.family not in _RECEIVING_FAMILIES:
            continue
        for revision in items:
            if revision.effective_on.year == params.SPLIT_YEAR:
                candidates.append((site_code, doc_code, revision))
                break

    needed = params.SPLIT_DOC_TARGET - len(plans)
    if len(candidates) < needed:
        raise RuntimeError(
            f"only {len(candidates)} documents were reissued in {params.SPLIT_YEAR}; the split "
            f"injector needs {needed} besides the spine's. Widen the year or lengthen the "
            "cadence — do not silently ship fewer splits, because the count is quoted."
        )

    low, high = params.SPLIT_MIGRATION_FRACTION
    for site_code, doc_code, revision in candidates:
        if len(plans) >= params.SPLIT_DOC_TARGET:
            break
        doc = skeleton.documents.get(site_code, doc_code)
        chosen = _target_for(
            doc,
            site_docs=skeleton.documents.at(site_code),
            excluded=excluded,
            stream=rng.sub_stream(stream, f"{site_code}/{doc_code}"),
        )
        if chosen is None:
            continue
        excluded.add(doc_code)
        excluded.add(chosen.doc_code)
        fraction = low + rng.unit(rng.sub_stream(stream, f"fraction/{doc_code}")) * (high - low)
        plans.append(
            SplitPlan(
                source_site=site_code,
                source_doc_code=doc_code,
                source_doc_id=doc.doc_id,
                target_doc_code=chosen.doc_code,
                target_doc_id=chosen.doc_id,
                effective_on=revision.effective_on,
                source_revision_key=revision.revision_key,
                target_reflow_revision_key=_reflow_key(
                    site_code, chosen.doc_code, revision.effective_on
                ),
                change_ref=_change_ref_for(skeleton, site_code, revision.effective_on),
                migration_fraction=round(fraction, 4),
                anchored=False,
            )
        )

    if len(plans) != params.SPLIT_DOC_TARGET:
        raise RuntimeError(
            f"planned {len(plans)} splits, needed {params.SPLIT_DOC_TARGET}. Every candidate "
            "after the first few shared a site with an already-chosen source or target."
        )
    del site_of_doc
    return tuple(plans)


def schedule_rows(
    migrations: Sequence[tuple[SplitPlan, str, str, str]],
) -> list[dict[str, Any]]:
    """One row per migrating clause: what moved, out of where, into where, under which change.

    ``migrations`` carries ``(plan, clause_key, from_label, to_label)`` — the labels are the
    payload, because the point of the injector is that the *label* changed and the identity did
    not.
    """
    by_plan: dict[str, int] = {}
    for plan_item, _clause_key, _from_label, _to_label in migrations:
        by_plan[plan_item.key] = by_plan.get(plan_item.key, 0) + 1
    rows: list[dict[str, Any]] = []
    for plan_item, clause_key, from_label, to_label in migrations:
        rows.append(
            {
                "anchored": plan_item.anchored,
                "change_ref": plan_item.change_ref,
                "clause_key": clause_key,
                "clause_uuid": str(rng.sid("clause", clause_key)),
                "effective_on": clock.iso_date(plan_item.effective_on),
                "from_doc_code": plan_item.source_doc_code,
                "from_printed_label": from_label,
                "migrated_clause_count": by_plan[plan_item.key],
                "site_code": plan_item.source_site,
                "source_revision_key": plan_item.source_revision_key,
                "split_key": plan_item.key,
                "target_reflow_revision_key": plan_item.target_reflow_revision_key,
                "to_doc_code": plan_item.target_doc_code,
                "to_printed_label": to_label,
            }
        )
    return rows
