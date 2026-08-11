# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The people the record names (``mainline.person``, migration 0022).

Roughly 140 people, 30 % of whom carry ``separated_at``.  That fraction is the author-churn
injector, and it is the reason the film can say *you cannot simply ask someone*: the engineer who
wrote the clause left the company five years before anybody needed to know why.

Three structural guarantees, made by construction rather than by hope:

* **Role quotas are filled first.**  Every site gets its permit issuers, supervisors, isolation
  officer, HSE advisor, area authority and manager before a single role is drawn at random.
  ``clearance_legal`` needs ``min_signer_rank`` up to 6 and ``req_foreign_org`` needs a signer
  from outside the operator; a purely weighted draw would satisfy those *usually*, and a corpus
  that is only usually loadable is a corpus that fails on the day it is filmed.
* **Anchored people are planted, not drawn.**  D. Okonjo separated 2021-07-16, and the sub
  ``kestrel:okonjo.d`` is a foreign key from the 2013 commit.
* **Nobody separates before they start**, and nobody has a four-day career: separation is drawn
  inside ``[effective_from + PERSON_MIN_TENURE_DAYS, NOW]`` or not at all.

``person`` is append-only with ``PRIMARY KEY (signer_sub, effective_from DESC)``; stage 1 emits
exactly one row per person, which is the enrolment row.  Later rows (a rank change, a ticket
expiry) are a mutation the corpus does not need and would have to justify.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from . import clock, params
from .model import Person
from .sites import SiteWorld

__all__ = ["PeopleWorld", "build_people"]

#: Roles every site must have, filled before any weighted draw.  Two permit issuers because one
#: person cannot both issue and accept, and a second signer is required by half the clearance
#: lattice.
_REQUIRED_ROLES_PER_SITE: tuple[str, ...] = (
    "permit_issuer",
    "permit_issuer",
    "supervisor",
    "supervisor",
    "isolation_officer",
    "hse_advisor",
    "area_authority",
    "manager",
)


class PeopleWorld:
    """The person set plus the lookups the document and MOC generators need."""

    __slots__ = ("_by_role", "_by_site", "_by_sub", "people")

    def __init__(self, people: Sequence[Person]) -> None:
        self.people = tuple(people)
        self._by_sub = {person.signer_sub: person for person in people}
        by_site: dict[str, list[Person]] = {}
        by_role: dict[str, list[Person]] = {}
        for person in people:
            by_site.setdefault(person.home_site, []).append(person)
            by_role.setdefault(person.role_key, []).append(person)
        self._by_site = {code: tuple(items) for code, items in by_site.items()}
        self._by_role = {role: tuple(items) for role, items in by_role.items()}

    def get(self, sub: str) -> Person:
        return self._by_sub[sub]

    def at(self, site_code: str) -> tuple[Person, ...]:
        return self._by_site.get(site_code, ())

    def authors_at(self, site_code: str, moment: dt.datetime) -> tuple[Person, ...]:
        """People who could plausibly have authored a document revision at ``moment``.

        Rank 2 and above (a tradesperson does not reissue a controlled procedure), employed at
        the time, at that site.  Returned in a stable order so the caller's draw is reproducible.
        """
        return tuple(
            person
            for person in self.at(site_code)
            if person.rank >= 2
            and person.effective_from <= moment
            and (person.separated_at is None or person.separated_at > moment)
        )

    @property
    def separated_fraction(self) -> float:
        if not self.people:
            return 0.0
        return sum(1 for person in self.people if person.separated_at is not None) / len(
            self.people
        )

    def rows(self) -> list[dict[str, Any]]:
        return [person.to_row() for person in self.people]


def _snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    body = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _make_person(
    *,
    sub: str,
    given: str,
    surname: str,
    display_name: str,
    org_key: str,
    org_name: str,
    role_key: str,
    role_label: str,
    rank: int,
    home_site: str,
    effective_from: dt.datetime,
    separated_at: dt.datetime | None,
    enrolment_assurance: str,
    tickets: Sequence[str],
    identity_source: str,
) -> Person:
    snapshot = {
        "authorisations": list(tickets),
        "display_name": display_name,
        "full_name": f"{given} {surname}",
        "home_site": home_site,
        "role": role_label,
    }
    return Person(
        signer_sub=sub,
        given=given,
        surname=surname,
        display_name=display_name,
        org_key=org_key,
        org_name=org_name,
        role_key=role_key,
        role_label=role_label,
        rank=rank,
        home_site=home_site,
        effective_from=effective_from,
        separated_at=separated_at,
        enrolment_assurance=enrolment_assurance,
        tickets=tuple(tickets),
        competency_source_id=str(rng.sid("competency", sub)),
        competency_sha256=_snapshot_digest(snapshot),
        identity_source=identity_source,
    )


def build_people(world: SiteWorld) -> PeopleWorld:
    """Materialise ~``PEOPLE_TARGET`` people across the four sites."""
    doc = gaz.load("people")
    prefix = str(doc["sub_prefix"])
    given_pool = gaz.as_sequence(doc, "given_names", origin="people.yaml")
    surname_pool = gaz.as_sequence(doc, "surnames", origin="people.yaml")
    orgs = gaz.as_sequence(doc, "orgs", origin="people.yaml")
    roles = gaz.as_sequence(doc, "roles", origin="people.yaml")
    assurance = gaz.as_sequence(doc, "enrolment_assurance", origin="people.yaml")
    tickets_pool = gaz.as_sequence(doc, "competency_tickets", origin="people.yaml")
    identity_source = str(world.operator["identity_source"])

    role_by_key = {str(role["key"]): role for role in roles}
    org_by_key = {str(org["key"]): org for org in orgs}
    for required in _REQUIRED_ROLES_PER_SITE:
        if required not in role_by_key:
            raise gaz.GazetteerError(f"people.yaml: required role {required!r} is not declared")

    identity = rng.stream("person.identity")
    assignment = rng.stream("person.assignment")
    tenure = rng.stream("person.tenure")
    churn = rng.stream("person.churn")
    competency = rng.stream("person.competency")

    people: list[Person] = []
    used_subs: set[str] = set()

    # ── anchored people, planted verbatim ────────────────────────────────────────────────────
    for entry in doc.get("anchored", ()):
        sub = str(entry["sub"])
        org = org_by_key[str(entry["org"])]
        role = role_by_key[str(entry["role"])]
        separated_raw = entry.get("separated_at")
        people.append(
            _make_person(
                sub=sub,
                given=str(entry["given"]),
                surname=str(entry["surname"]),
                display_name=str(entry["display_name"]),
                org_key=str(entry["org"]),
                org_name=str(org["name"]),
                role_key=str(entry["role"]),
                role_label=str(role["label"]),
                rank=int(entry["rank"]),
                home_site=str(entry["home_site"]),
                effective_from=clock.coerce_datetime(
                    entry["effective_from"], origin=f"people.yaml/{sub}/effective_from"
                ),
                separated_at=(
                    None
                    if separated_raw is None
                    else clock.coerce_datetime(
                        separated_raw, origin=f"people.yaml/{sub}/separated_at"
                    )
                ),
                enrolment_assurance=str(entry["enrolment_assurance"]),
                tickets=[str(item) for item in entry["tickets"]],
                identity_source=identity_source,
            )
        )
        used_subs.add(sub)

    # ── the role quota, then the weighted remainder ──────────────────────────────────────────
    plan: list[tuple[str, str]] = []  # (site_code, role_key)
    for site in world.sites:
        for role_key in _REQUIRED_ROLES_PER_SITE:
            plan.append((site.code, role_key))

    remaining = params.PEOPLE_TARGET - len(people) - len(plan)
    if remaining < 0:
        raise RuntimeError(
            f"PEOPLE_TARGET={params.PEOPLE_TARGET} is smaller than the anchored people plus the "
            f"per-site role quota ({len(people) + len(plan)})"
        )
    role_keys = [str(role["key"]) for role in roles]
    role_weights = [float(role["weight"]) for role in roles]
    site_codes = list(world.codes)
    site_weights = list(world.weights)
    for _ in range(remaining):
        plan.append(
            (
                rng.weighted(assignment, site_codes, site_weights),
                rng.weighted(assignment, role_keys, role_weights),
            )
        )

    org_keys = [str(org["key"]) for org in orgs]
    org_weights = [float(org["weight"]) for org in orgs]
    assurance_values = [str(item["value"]) for item in assurance]
    assurance_weights = [float(item["weight"]) for item in assurance]

    for home_site, role_key in plan:
        role = role_by_key[role_key]
        given_entry = rng.pick(identity, given_pool)
        given = str(given_entry["name"])
        initial = str(given_entry["initial"]).lower()

        sub = ""
        surname = ""
        for _attempt in range(64):
            surname = str(rng.pick(identity, surname_pool))
            candidate = f"{prefix}{surname.lower()}.{initial}"
            if candidate not in used_subs:
                sub = candidate
                break
            candidate = f"{prefix}{surname.lower()}.{initial}{len(used_subs)}"
            if candidate not in used_subs:
                sub = candidate
                break
        if not sub:  # pragma: no cover - the pool is two orders of magnitude larger than needed
            raise RuntimeError("exhausted the name pool while minting a unique signer_sub")
        used_subs.add(sub)

        org_key = rng.weighted(assignment, org_keys, org_weights)
        org = org_by_key[org_key]

        # Employment window.
        span_years = params.PERSON_START_LATEST_YEAR - params.PERSON_START_EARLIEST_YEAR
        start_year = params.PERSON_START_EARLIEST_YEAR + int(rng.unit(tenure) * (span_years + 1))
        start_day = 1 + int(rng.unit(tenure) * 365)
        effective_from = dt.datetime(start_year, 1, 1, 6, 0, tzinfo=clock.TZ) + dt.timedelta(
            days=start_day - 1
        )
        if effective_from > clock.NOW:
            effective_from = clock.NOW - dt.timedelta(days=params.PERSON_MIN_TENURE_DAYS)

        separated_at: dt.datetime | None = None
        earliest_exit = effective_from + dt.timedelta(days=params.PERSON_MIN_TENURE_DAYS)
        if earliest_exit < clock.NOW and rng.unit(churn) < params.PEOPLE_SEPARATED_FRACTION:
            window_days = clock.days_between(earliest_exit, clock.NOW)
            separated_at = earliest_exit + dt.timedelta(days=rng.unit(churn) * window_days)
            separated_at = separated_at.replace(hour=17, minute=0, second=0, microsecond=0)

        ticket_count = 1 + int(rng.unit(competency) * 3)
        tickets = sorted(rng.sample_without_replacement(competency, tickets_pool, ticket_count))

        people.append(
            _make_person(
                sub=sub,
                given=given,
                surname=surname,
                display_name=f"{given_entry['initial']}. {surname}",
                org_key=org_key,
                org_name=str(org["name"]),
                role_key=role_key,
                role_label=str(role["label"]),
                rank=int(role["rank"]),
                home_site=home_site,
                effective_from=effective_from,
                separated_at=separated_at,
                enrolment_assurance=rng.weighted(assignment, assurance_values, assurance_weights),
                tickets=[str(item) for item in tickets],
                identity_source=identity_source,
            )
        )

    _assert_invariants(people, world)
    return PeopleWorld(sorted(people, key=lambda person: person.signer_sub))


def _assert_invariants(people: Sequence[Person], world: SiteWorld) -> None:
    """Fail loudly on the properties the clearance lattice depends on."""
    for person in people:
        if not 1 <= person.rank <= 9:
            raise RuntimeError(f"{person.signer_sub}: rank {person.rank} outside 1..9")
        if person.separated_at is not None and person.separated_at <= person.effective_from:
            raise RuntimeError(f"{person.signer_sub}: separated before starting")

    if not any(person.rank >= 6 for person in people):
        raise RuntimeError(
            "no person of rank >= 6 exists; (blood_fatal, emergency_override) requires rank 6 and "
            "the corpus would contain a disposition nobody can legally sign"
        )
    orgs = {person.org_key for person in people if person.separated_at is None}
    if len(orgs) < 2:
        raise RuntimeError(
            "every current person is in one organisation; `req_foreign_org` could never be met"
        )
    for site in world.sites:
        issuers = [
            person
            for person in people
            if person.home_site == site.code and person.role_key == "permit_issuer"
        ]
        if len(issuers) < 2:
            raise RuntimeError(f"site {site.code} has fewer than two permit issuers")
