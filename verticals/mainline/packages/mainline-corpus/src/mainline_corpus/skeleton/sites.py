# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The four sites.

``mainline.site`` (migration 0021) is narrower than the corpus needs: it carries the identity,
the ledger partition key, the RLS scope token, the tenant and the taxonomy version, and nothing
else.  Everything a *generator* needs about a site — its name, what it does, how much of the
event timeline it carries — is corpus scaffolding and is emitted separately.

``site_role`` is deliberately NOT emitted.  It appears on the projected-column denylist because
on ``permit`` and ``change_request`` it is trigger-filled from the site, and this package holds
one denylist rather than a per-table matrix that would need to be right in fifteen places.  The
value the loader should use is registered as a pending field with its derivation, so nothing is
lost and nothing is guessed.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from . import clock
from .model import PendingField, Site

__all__ = ["SiteWorld", "build_sites"]

_TAXONOMY_VER = 1


class SiteWorld:
    """The site set plus the lookups every other generator needs."""

    __slots__ = ("_by_code", "operator", "sites", "tenant_id")

    def __init__(self, sites: Sequence[Site], operator: Mapping[str, Any], tenant_id: str) -> None:
        self.sites = tuple(sites)
        self.operator = operator
        self.tenant_id = tenant_id
        self._by_code = {site.code: site for site in self.sites}

    def __iter__(self) -> Any:
        return iter(self.sites)

    def __len__(self) -> int:
        return len(self.sites)

    def by_code(self, code: str) -> Site:
        try:
            return self._by_code[code]
        except KeyError as exc:
            raise KeyError(
                f"unknown site code {code!r}; the gazetteer declares {sorted(self._by_code)}"
            ) from exc

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(site.code for site in self.sites)

    @property
    def weights(self) -> tuple[float, ...]:
        return tuple(site.event_weight for site in self.sites)

    def table_rows(self) -> list[dict[str, Any]]:
        """Rows for ``mainline.site``.

        ``site_code`` is lower-cased because 0021 carries ``site_code_is_lower_case``; the
        UPPERCASE code stays the corpus's natural key so ``sid("site", "MRD")`` is stable and
        quotable.
        """
        return [
            {
                "opened_at": clock.iso(
                    dt.datetime(
                        site.commissioned_on.year,
                        site.commissioned_on.month,
                        site.commissioned_on.day,
                        tzinfo=clock.TZ,
                    )
                ),
                "site_code": site.code.lower(),
                "site_id": site.site_id,
                "taxonomy_ver": _TAXONOMY_VER,
                "tenant_id": self.tenant_id,
            }
            for site in self.sites
        ]

    def registry_rows(self) -> list[dict[str, Any]]:
        return [site.to_row() for site in self.sites]

    def pending(self) -> list[PendingField]:
        return [
            PendingField(
                table="mainline.site",
                key=site.code,
                column="site_role",
                owner="dm-foundation",
                reason=(
                    "site_role is the RLS scope token (a database role name) and is on this "
                    "package's projected-column denylist. The corpus does not create roles, so "
                    "it does not assert one."
                ),
                facts={
                    "proposed_value": f"mainline_site_{site.code.lower()}",
                    "constraint": "site_role must be lower case and unique (migration 0021)",
                    "site_code": site.code.lower(),
                },
            )
            for site in self.sites
        ]


def build_sites() -> SiteWorld:
    """Read ``sites.yaml`` and mint site identities.

    No randomness at all: four sites, four ``uuid5`` values, four rows.  A generator that drew
    anything here would make the site ids depend on draw order, and every other worker computes
    ``sid("site", "MRD")`` from the natural key.
    """
    doc = gaz.load("sites")
    raw_sites = gaz.as_sequence(doc, "sites", origin="sites.yaml")
    operator = gaz.as_mapping(doc, "operator", origin="sites.yaml")

    sites: list[Site] = []
    seen: set[str] = set()
    for entry in raw_sites:
        code = str(entry["code"])
        if code in seen:
            raise gaz.GazetteerError(f"sites.yaml: duplicate site code {code!r}")
        seen.add(code)
        sites.append(
            Site(
                site_id=str(rng.sid("site", code)),
                code=code,
                name=str(entry["name"]),
                full_name=str(entry["full_name"]),
                kind=str(entry["kind"]),
                ref_slug=str(entry["ref_slug"]),
                tz_offset_hours=int(entry["tz_offset_hours"]),
                commissioned_on=clock.coerce_date(
                    entry["commissioned_on"], origin=f"sites.yaml/{code}/commissioned_on"
                ),
                event_weight=float(entry["event_weight"]),
                on_camera=bool(entry["on_camera"]),
            )
        )

    if len(sites) < 3:
        raise gaz.GazetteerError(
            "sites.yaml declares fewer than three sites; fleet siblings need at least three to "
            "be a cohort rather than a coincidence (decision D16)"
        )
    if sum(1 for site in sites if site.on_camera) != 1:
        raise gaz.GazetteerError("exactly one site must carry `on_camera: true`")

    return SiteWorld(sites, operator, str(rng.sid("tenant", "kestrel")))
