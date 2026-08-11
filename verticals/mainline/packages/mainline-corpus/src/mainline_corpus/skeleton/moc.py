# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The management-of-change stream (``mainline.change_request``, ARCHITECTURE.md §5.5).

The change request is a **gated subject**, not a form.  Finding S16 is what turns *"the permit
is a protected branch"* into *"the repository is a protected branch and the permit is one of its
refs"*, and it is what gives the MOC Ancestry Audit a live enforcement surface instead of a
retrospective report.  So an MOC row here carries the same alphabet of states a permit does.

── What is emitted and what is refused ──────────────────────────────────────────────────────
``site_role``, ``head_seq``, ``gate_epoch``, ``open_blocking``, ``open_residue`` and
``open_conflicts`` are projections and are absent.  ``merged_commit`` is **null**, including on
rows whose terminal state is ``merged``, because stage 1 mints no commits.

That is not an oversight and it is not a hole to paper over.  ``cr_merge_evidence`` says
``state <> 'merged' OR merged_commit IS NOT NULL``: a merged change request with no merge
evidence is exactly the thing the database should refuse, and it will refuse it until the worker
that mints commits binds them.  The gap is registered in ``pending.jsonl`` with that worker
named.  A skeleton that invented a 32-byte value to satisfy the constraint would have converted
a true refusal into a silent pass, one hop upstream, which is the defect class this whole
product exists to eliminate.

── Register numbering ───────────────────────────────────────────────────────────────────────
``MOC-2019-0221`` is the 221st entry in the 2019 change register — not the 221st *safety*
change.  Real registers carry every change, most of which never touch a control.  The corpus
holds the safety-relevant subset, so reference numbers advance in gaps.  Anchored references
keep their authored positions and the walk skips them.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from . import clock, params
from .documents import DocumentWorld
from .model import ChangeRequest, PendingField
from .people import PeopleWorld
from .sites import SiteWorld

__all__ = ["MocWorld", "build_mocs"]

_MAX_REGISTER_GAP = 26


class MocWorld:
    __slots__ = ("change_requests", "pending")

    def __init__(
        self, change_requests: Sequence[ChangeRequest], pending: Sequence[PendingField]
    ) -> None:
        self.change_requests = tuple(change_requests)
        self.pending = tuple(pending)

    def rows(self) -> list[dict[str, Any]]:
        return [item.to_row() for item in self.change_requests]

    def registry_rows(self) -> list[dict[str, Any]]:
        return [item.to_registry_row() for item in self.change_requests]

    def intent_histogram(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.change_requests:
            counts[item.intent] = counts.get(item.intent, 0) + 1
        return dict(sorted(counts.items()))


def _anchored(
    world: SiteWorld, documents: DocumentWorld, people: PeopleWorld
) -> list[ChangeRequest]:
    doc = gaz.load("anchors")
    entries = gaz.as_sequence(doc, "change_requests", origin="anchors.yaml")
    out: list[ChangeRequest] = []
    for entry in entries:
        external_ref = str(entry["external_ref"])
        site = world.by_code(str(entry["site"]))
        opened_at = clock.coerce_datetime(
            entry["opened_at"], origin=f"anchors.yaml/{external_ref}/opened_at"
        )
        activity_root = str(entry["activity_root"])
        touched = documents.for_fonds(site.code, activity_root)
        author_stream = rng.sub_stream("moc.author", external_ref)
        candidates = people.authors_at(site.code, opened_at)
        if not candidates:
            candidates = tuple(person for person in people.at(site.code) if person.rank >= 2)
        out.append(
            ChangeRequest(
                cr_id=str(rng.sid("change_request", external_ref)),
                external_ref=external_ref,
                site_id=site.site_id,
                site_code=site.code,
                ref_name=str(entry["ref_name"]),
                target_ref=str(entry["target_ref"]),
                state=str(entry["terminal_state"]),
                opened_at=opened_at,
                intent=str(entry["intent"]),
                activity_root=activity_root,
                doc_codes=tuple(sorted(item.doc_code for item in touched)),
                author_sub=rng.pick(author_stream, candidates).signer_sub,
                anchored=True,
            )
        )
    return out


def build_mocs(world: SiteWorld, people: PeopleWorld, documents: DocumentWorld) -> MocWorld:
    """Materialise roughly ``MOC_TARGET`` change requests across the window."""
    anchored = _anchored(world, documents, people)
    reserved: dict[int, set[int]] = {}
    for item in anchored:
        year, position = _split_ref(item.external_ref)
        reserved.setdefault(year, set()).add(position)

    schedule = rng.stream("moc.schedule")
    detail = rng.stream("moc.detail")

    first_year = clock.EPOCH.year
    last_year = clock.NOW.year
    years = list(range(first_year, last_year + 1))

    # Volume per year follows the same reporting-maturity curve as the event timeline, because
    # they are the same organisational phenomenon: an organisation that reports more also
    # formalises more of its changes.
    weights: list[float] = []
    for year in years:
        progress = (year - first_year) / max(1, last_year - first_year)
        share = (
            params.MOC_GROWTH_START + (params.MOC_GROWTH_END - params.MOC_GROWTH_START) * progress
        )
        # The final year is partial (the corpus stops on 2026-08-04).
        if year == last_year:
            share *= clock.NOW.timetuple().tm_yday / 365.25
        weights.append(share)
    weight_total = sum(weights)

    target = params.MOC_TARGET - len(anchored)
    per_year = [round(target * weight / weight_total) for weight in weights]
    drift = target - sum(per_year)
    for index in range(abs(drift)):
        step = 1 if drift > 0 else -1
        per_year[index % len(per_year)] = max(0, per_year[index % len(per_year)] + step)

    intents = list(params.MOC_INTENT_WEIGHTS)
    intent_weights = [params.MOC_INTENT_WEIGHTS[key] for key in intents]
    states = list(params.MOC_TERMINAL_STATE_WEIGHTS)
    state_weights = [params.MOC_TERMINAL_STATE_WEIGHTS[key] for key in states]
    site_codes = list(world.codes)
    site_weights = list(world.weights)

    generated: list[ChangeRequest] = []
    used_refs = {item.external_ref for item in anchored}

    for year, count in zip(years, per_year, strict=True):
        if count <= 0:
            continue
        year_start = dt.datetime(year, 1, 1, tzinfo=clock.TZ)
        year_end = min(dt.datetime(year + 1, 1, 1, tzinfo=clock.TZ), clock.NOW)
        span = clock.days_between(year_start, year_end)
        if span <= 0:
            continue

        offsets = sorted(rng.unit(schedule) * span for _ in range(count))
        position = 0
        taken = reserved.get(year, set())
        for offset in offsets:
            while True:
                position += 1 + int(rng.unit(schedule) * _MAX_REGISTER_GAP)
                if position not in taken:
                    break
            external_ref = f"MOC-{year:04d}-{position:04d}"
            if external_ref in used_refs:  # pragma: no cover - the walk already skips reserved
                continue
            used_refs.add(external_ref)

            opened_at = (year_start + dt.timedelta(days=offset)).replace(
                minute=0, second=0, microsecond=0
            )
            opened_at = opened_at.replace(hour=7 + int(rng.unit(detail) * 9))

            site_code = rng.weighted(detail, site_codes, site_weights)
            site = world.by_code(site_code)
            site_docs = documents.at(site_code)
            if not site_docs:
                raise RuntimeError(f"site {site_code} has no documents for an MOC to touch")
            anchor_doc = rng.pick(detail, site_docs)
            activity_root = anchor_doc.activity_root
            touched = documents.for_fonds(site_code, activity_root) or (anchor_doc,)

            candidates = people.authors_at(site_code, opened_at)
            if not candidates:
                candidates = tuple(person for person in people.at(site_code) if person.rank >= 2)
            if not candidates:
                raise RuntimeError(f"no eligible MOC author at {site_code} in {year}")

            generated.append(
                ChangeRequest(
                    cr_id=str(rng.sid("change_request", external_ref)),
                    external_ref=external_ref,
                    site_id=site.site_id,
                    site_code=site_code,
                    ref_name=f"cr/{external_ref}",
                    target_ref=site.main_ref,
                    state=rng.weighted(detail, states, state_weights),
                    opened_at=opened_at,
                    intent=rng.weighted(detail, intents, intent_weights),
                    activity_root=activity_root,
                    doc_codes=tuple(sorted(item.doc_code for item in touched)),
                    author_sub=rng.pick(detail, candidates).signer_sub,
                    anchored=False,
                )
            )

    everything = sorted(anchored + generated, key=lambda item: item.external_ref)
    pending = [
        PendingField(
            table="mainline.change_request",
            key=item.external_ref,
            column="merged_commit",
            owner="corpus-blame-key",
            reason=(
                "stage 1 mints no commits. `cr_merge_evidence` refuses a merged change request "
                "with no merge evidence, and that refusal is correct until the commit exists."
            ),
            facts={
                "ref_name": item.ref_name,
                "state": item.state,
                "target_ref": item.target_ref,
            },
        )
        for item in everything
        if item.state == "merged"
    ]
    return MocWorld(everything, pending)


def _split_ref(external_ref: str) -> tuple[int, int]:
    _, year, position = external_ref.split("-")
    return int(year), int(position)
