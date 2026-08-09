# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Injector 7 — fleet siblings.  Nine groups: one canonical event, three sites, local wording.

**Proves:** cherry-pick, and dedup-to-one-check.  An OEM advisory or a regulator notice reaches
three sites, each of which rewrites it into its own procedure in its own words.  There is ONE
event.  A system that files the lesson per document produces three obligations and, later, three
separate blocking checks for the same fact — which is how a permit accumulates a wall of
duplicates that operators learn to click through.  ``event_bond`` exists so that one canonical
event carries three bonds and the gate raises one check.

Two properties of this selection are load-bearing:

* the group's three clauses are at **three different sites**, and the blame edges therefore
  cross the site boundary.  ``blame_edge.site_id`` is the *clause's* site, because the edge is
  read under the clause's row-level security scope; the event that generated it lives at one
  site and is bonded to the others.  A group whose three clauses were at one site would prove
  nothing about deduplication that a single site's duplicate clauses do not already prove.
* the three clauses were reworded **locally**, so their control class matches and their text
  does not.  Text is the renderer's job; what is authored here is the shared mechanism.

Like the decoys, these are **found and not injected**: ``mainline.event`` is stage 1's table.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..blame import params
from ..blame.eventindex import EventIndex
from ..skeleton import clock

__all__ = ["FleetGroup", "FleetMember", "plan", "schedule_rows"]

#: Kinds a canonical fleet-wide lesson arrives as.  An incident is local to the plant it
#: happened at; these three are addressed to a fleet.  An OEM bulletin names an equipment class,
#: not a site.  A regulator's notice to one site of a company is read by every site of that
#: company.  A corporate audit visits each operation with the same checklist, so the same gap is
#: written up three times — which is the archetype this injector is about, arriving through the
#: assurance function instead of through a vendor.
_CANONICAL_KINDS: frozenset[str] = frozenset({"oem_alert", "regulator_notice", "audit_finding"})

#: How long a site may take to write a fleet-wide lesson into its own procedure.  Three years,
#: and that is not slack: a procedure on a two-to-three-year cadence with jitter is reissued
#: once in that span, and three sites must EACH have reissued the right document before a group
#: exists.  A tighter window does not make the corpus more realistic — it makes the corpus
#: contain fewer fleet lessons than a real fleet has.
_RESPONSE_WINDOW_DAYS: float = 1095.0


@dataclass(frozen=True, slots=True)
class FleetMember:
    site_code: str
    clause_key: str
    clause_uuid: str
    doc_code: str
    revision_key: str
    response_lag_days: float


@dataclass(frozen=True, slots=True)
class FleetGroup:
    group_id: str
    canonical_event_ref: str
    canonical_site: str
    control_class: str
    hazard_energy: str
    severity_gate: int
    members: tuple[FleetMember, ...]

    @property
    def sites(self) -> tuple[str, ...]:
        return tuple(sorted(member.site_code for member in self.members))


#: Revisions an injector produced for a structural reason.  A retypeset renumbers a document and
#: a split moves obligations between documents; neither is a site writing a fleet-wide lesson
#: into its own procedure, and binding the canonical event to one would put a fabricated
#: response into the answer key.
_STRUCTURAL_INJECTORS: frozenset[str] = frozenset(
    {"retypeset", "document_split", "document_split_reflow"}
)


def _first_response(
    candidates: Sequence[Any],
    fact: Any,
    *,
    skip_used: bool,
    used: set[str],
    reserved: frozenset[str],
) -> tuple[Any, float] | None:
    """Return the earliest genuine reissue inside the response window, or ``None``."""
    for revision in candidates:
        if revision.injector in _STRUCTURAL_INJECTORS or revision.clause_key in reserved:
            continue
        if skip_used and revision.clause_key in used:
            continue
        lag = clock.days_between(
            fact.occurred_at,
            clock.coerce_datetime(revision.effective_on, origin="fleet/response"),
        )
        if 0.0 <= lag <= _RESPONSE_WINDOW_DAYS:
            return revision, lag
    return None


def plan(universe: Any, walk: Any, index: EventIndex) -> tuple[FleetGroup, ...]:
    """Find nine canonical events whose lesson was written down at three different sites."""
    clause_of = {clause.clause_key: clause for clause in universe.clauses}

    # (site, control class) -> the clause revisions that could be a local response, by date.
    responses: dict[tuple[str, str], list[Any]] = {}
    for revision in walk.revisions:
        clause = clause_of[revision.clause_key]
        responses.setdefault((revision.site_code, clause.control_class), []).append(revision)
    for items in responses.values():
        items.sort(key=lambda r: (r.effective_on, r.revision_key))

    # The spine clause is never a fleet member.  Its causality is planted — INC-2013-044 wrote
    # it, that edge is asserted and on camera — and a fleet group that reached for it would
    # overwrite the one causal fact the whole film is built on.
    reserved: frozenset[str] = frozenset({universe.spine_clause_key})

    groups: list[FleetGroup] = []
    used_events: set[str] = set()
    used_clauses: set[str] = set()
    # What is forbidden is two groups with the SAME three clauses: one fact counted twice, which
    # would flatter every deduplication number computed over this set.
    seen_member_sets: set[frozenset[str]] = set()

    for fact in index.all_facts:
        if len(groups) >= params.FLEET_GROUP_TARGET:
            break
        if fact.event.kind not in _CANONICAL_KINDS or fact.external_ref in used_events:
            continue
        for control_class in sorted(fact.control_classes):
            members: list[FleetMember] = []
            for site_code in sorted({key[0] for key in responses}):
                candidates = responses.get((site_code, control_class), ())
                # Two passes.  The first prefers a clause no other group has claimed, so nine
                # groups spread across the corpus instead of orbiting the same six obligations.
                # The second allows a reused clause, because a clause responding to two fleet
                # alerts across twenty-two years is ordinary and refusing it would only make the
                # corpus contain fewer fleet lessons than a real fleet has.
                chosen = _first_response(
                    candidates, fact, skip_used=True, used=used_clauses, reserved=reserved
                ) or _first_response(
                    candidates, fact, skip_used=False, used=used_clauses, reserved=reserved
                )
                if chosen is None:
                    continue
                revision, lag = chosen
                members.append(
                    FleetMember(
                        site_code=site_code,
                        clause_key=revision.clause_key,
                        clause_uuid=revision.clause_uuid,
                        doc_code=revision.doc_code,
                        revision_key=revision.revision_key,
                        response_lag_days=round(lag, 2),
                    )
                )
                if len(members) == params.FLEET_SITES_PER_GROUP:
                    break
            if len(members) < params.FLEET_SITES_PER_GROUP:
                continue
            signature = frozenset(member.clause_key for member in members)
            if signature in seen_member_sets:
                continue
            seen_member_sets.add(signature)
            used_events.add(fact.external_ref)
            used_clauses.update(signature)
            groups.append(
                FleetGroup(
                    group_id=f"fleet-{len(groups) + 1:02d}",
                    canonical_event_ref=fact.external_ref,
                    canonical_site=fact.event.site_code,
                    control_class=control_class,
                    hazard_energy=fact.event.hazard_energy,
                    severity_gate=fact.severity_gate,
                    members=tuple(members),
                )
            )
            break

    if len(groups) != params.FLEET_GROUP_TARGET:
        raise RuntimeError(
            f"found {len(groups)} fleet-sibling groups, needed {params.FLEET_GROUP_TARGET}. A "
            "group needs one OEM or regulator event whose failed control class was written into "
            "a clause at three different sites within "
            f"{_RESPONSE_WINDOW_DAYS:.0f} days. Widen the response window rather than shipping "
            "fewer: 'one canonical event, three bonds, never three checks' is measured against "
            "this count."
        )
    return tuple(groups)


def schedule_rows(groups: Sequence[FleetGroup]) -> list[dict[str, Any]]:
    """One row per (group, member): the three bonds a single canonical event carries."""
    rows: list[dict[str, Any]] = []
    for group in groups:
        for member in group.members:
            rows.append(
                {
                    "canonical_event_ref": group.canonical_event_ref,
                    "canonical_site": group.canonical_site,
                    "clause_key": member.clause_key,
                    "clause_uuid": member.clause_uuid,
                    "control_class": group.control_class,
                    "cross_site": member.site_code != group.canonical_site,
                    "doc_code": member.doc_code,
                    "group_id": group.group_id,
                    "hazard_energy": group.hazard_energy,
                    "member_site": member.site_code,
                    "response_lag_days": member.response_lag_days,
                    "revision_key": member.revision_key,
                    "severity_gate": group.severity_gate,
                    "sites_in_group": len(group.members),
                }
            )
    rows.sort(key=lambda row: (row["group_id"], row["member_site"]))
    return rows
