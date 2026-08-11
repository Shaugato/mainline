# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The incident timeline and its control failures.

``mainline.event`` and ``mainline.control_failure`` (ARCHITECTURE.md §5.4).

---------------------------------------------------------------------------------------------
1. The timeline is a non-homogeneous, self-exciting Poisson process
---------------------------------------------------------------------------------------------
    lambda_site(t) = base_site * seasonal(t) * reporting_growth(t) * excitation(t | history)

* **seasonal** — southern-hemisphere summer peak.  This is the corpus's own reason for the 2026
  MOC's justification (*"reduce spurious trips at summer ambient"*): the seasonality is in the
  data, so the justification reads as a real operational pressure rather than a plot device.
* **reporting_growth** — near-miss reporting rates rise across twenty-two years.  Mean 1.0, so
  it re-weights *when* events appear without changing how many.
* **excitation** — after a severity-4-or-worse event at a site, that site reports harder for a
  few months and the rate decays back.  The process depends on its own history, which is what
  puts clusters of related near-misses immediately after each major event.  A precursor-recall
  harness tested against a homogeneous process is tested against a world where precursors are
  independent of what they precede, which is the one property that matters.

Sampled by **Ogata thinning**: candidates from a homogeneous process at a bound that dominates
every term, kept with probability ``lambda(t)/bound``.  The sample is then *exact*, not
approximate — and the bound is asserted at every evaluation, so a parameter change that broke
domination would raise rather than silently biasing the corpus.

---------------------------------------------------------------------------------------------
2. Severity is dual-axis, and the gate is not simply max(actual, potential)
---------------------------------------------------------------------------------------------
``severity_gate = max(severity_actual, potential_admitted)``.  A *potential* of 4 or 5 counts at
its face value only if a deterministic fatal-potential trigger fires (the fonds is one of the
ICMM MUE classes flagged ``fatal_potential_trigger``) **or** a named human ratified it under
signature.  Otherwise it is admitted at 3.

That produces a class of rows the corpus needs and no naive generator would emit: an event whose
``severity_potential`` is 5, whose ``severity_basis`` is ``model_rated``, and whose
``severity_gate`` is 3 — a model said "this could have killed someone" and the gate did not arm.
Those rows are legal under ``model_cannot_arm``; a row with ``severity_gate >= 4`` and
``severity_basis = 'model_rated'`` is not, and ``_assert_gate_invariants`` refuses to emit one.

The histogram is authored as a *shape* and apportioned to whatever the Poisson process produced,
by largest remainder.  Anchored events are removed from the apportionment first, so planting the
2009 fatality does not inflate the severity-5 count.

---------------------------------------------------------------------------------------------
3. What stage 1 does not know
---------------------------------------------------------------------------------------------
``narrative``, ``source_sha256``, ``severity_span``, and ``control_failure``'s
``evidence_span`` / ``quote_sha256`` are all functions of text that does not exist yet.  They are
emitted null and registered in ``pending.jsonl``.  Filling ``source_sha256`` with a hash of
something that is not the raw source bytes would be a lie in a custody column, and the custody
column is the exhibit.
"""

from __future__ import annotations

import bisect
import datetime as dt
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .. import gazetteer as gaz
from .. import rng
from . import clock, params
from .assets import AssetWorld
from .model import ControlFailure, Event, PendingField
from .sites import SiteWorld
from .taxonomy import Fonds, TaxonomyWorld

__all__ = ["EventWorld", "build_events"]

_REF_PREFIX: Mapping[str, str] = {
    "incident": "INC",
    "near_miss": "NM",
    "regulator_notice": "RN",
    "oem_alert": "OEM",
    "audit_finding": "AF",
    "capa": "CAPA",
}
_REF_WIDTH: Mapping[str, int] = {"near_miss": 4}

_HIGH_GATE_KINDS: tuple[str, ...] = ("incident", "near_miss", "regulator_notice")
_HIGH_GATE_WEIGHTS: tuple[float, ...] = (0.55, 0.35, 0.10)

_POTENTIAL_ALWAYS: frozenset[str] = frozenset({"near_miss", "oem_alert", "audit_finding", "capa"})

_ICAM_TIERS: tuple[str, ...] = (
    "absent_or_failed_defence",
    "task_or_environmental_condition",
    "individual_or_team_action",
    "organisational_factor",
)
_ICAM_WEIGHTS: tuple[float, ...] = (0.40, 0.25, 0.20, 0.15)

_CRITICALITY_WEIGHT: Mapping[str, float] = {"critical": 3.0, "high": 2.0, "medium": 1.0, "low": 0.5}

_PLACEHOLDER = re.compile(r"\{(?P<name>[a-z_]+)(?::(?P<arg>[a-z_]+))?\}")


class EventWorld:
    """Every event, its control failures, and the pending register they generate."""

    __slots__ = ("_by_ref", "control_failures", "events", "pending")

    def __init__(
        self,
        events: Sequence[Event],
        control_failures: Sequence[ControlFailure],
        pending: Sequence[PendingField],
    ) -> None:
        self.events = tuple(events)
        self.control_failures = tuple(control_failures)
        self.pending = tuple(pending)
        self._by_ref = {event.external_ref: event for event in events}

    def get(self, external_ref: str) -> Event:
        return self._by_ref[external_ref]

    def major_events_at(self, site_code: str) -> tuple[Event, ...]:
        return tuple(
            event
            for event in self.events
            if event.site_code == site_code and event.severity_gate >= 4
        )

    def histogram(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.events:
            key = str(event.severity_gate)
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    def rows(self) -> list[dict[str, Any]]:
        return [event.to_row() for event in self.events]

    def registry_rows(self) -> list[dict[str, Any]]:
        return [event.to_registry_row() for event in self.events]

    def control_failure_rows(self) -> list[dict[str, Any]]:
        return [failure.to_row() for failure in self.control_failures]


# ── the intensity function ───────────────────────────────────────────────────────────────────


def _seasonal(moment: dt.datetime) -> float:
    phase = clock.year_fraction(moment) - params.SEASONAL_PEAK_YEAR_FRACTION
    return 1.0 + params.SEASONAL_AMPLITUDE * math.cos(2.0 * math.pi * phase)


def _reporting_growth(progress: float) -> float:
    return (
        params.REPORTING_GROWTH_START
        + (params.REPORTING_GROWTH_END - params.REPORTING_GROWTH_START) * progress
    )


def _excitation(now_days: float, major_days: Sequence[float]) -> float:
    """``1 + PEAK * sum(exp(-dt/tau))`` over major events inside the window.

    ``major_days`` is kept sorted so the window is a slice, not a scan.  The concurrency check is
    the proof obligation the thinning bound carries: if more than
    ``EXCITATION_MAX_CONCURRENT`` spikes overlap, the bound no longer dominates and the sample
    would be quietly wrong.  It raises instead.
    """
    low = bisect.bisect_left(major_days, now_days - params.EXCITATION_WINDOW_DAYS)
    high = bisect.bisect_right(major_days, now_days)
    total = 0.0
    for moment in major_days[low:high]:
        total += math.exp(-(now_days - moment) / params.EXCITATION_DECAY_DAYS)
    # The check is on the SUM of decayed contributions, not on the count of spikes in the
    # window: four events 150 days apart contribute far less than one event yesterday, and the
    # thinning bound is stated in terms of the sum.
    if total > params.EXCITATION_MAX_CONCURRENT:
        raise RuntimeError(
            f"excitation sum {total:.2f} at t={now_days:.1f}d exceeds "
            f"EXCITATION_MAX_CONCURRENT={params.EXCITATION_MAX_CONCURRENT}. The thinning bound no "
            "longer dominates the intensity and the sample would be biased rather than merely "
            "slow. Raise the bound parameter; do not raise the tolerance."
        )
    return 1.0 + params.EXCITATION_PEAK * total


def _sample_site_timeline(
    site_code: str, base_rate_per_year: float, seeded_major_days: Sequence[float]
) -> list[tuple[float, bool]]:
    stream = rng.stream(f"event.timeline/{site_code}")
    horizon = clock.days_between(clock.EPOCH, clock.NOW)
    per_day = base_rate_per_year / 365.25
    growth_max = max(params.REPORTING_GROWTH_START, params.REPORTING_GROWTH_END)
    bound = (
        per_day
        * (1.0 + params.SEASONAL_AMPLITUDE)
        * growth_max
        * (1.0 + params.EXCITATION_PEAK * params.EXCITATION_MAX_CONCURRENT)
    )

    majors = sorted(seeded_major_days)
    accepted: list[tuple[float, bool]] = []
    position = 0.0
    while True:
        position += rng.exponential_interval(stream, bound)
        if position >= horizon:
            break
        intensity = (
            per_day
            * _seasonal(clock.from_days(position))
            * _reporting_growth(position / horizon)
            * _excitation(position, majors)
        )
        if not rng.poisson_thin_accept(stream, intensity, bound):
            continue
        major = rng.unit(stream) < params.P_MAJOR
        accepted.append((position, major))
        if major:
            bisect.insort(majors, position)
    return accepted


# ── severity apportionment ───────────────────────────────────────────────────────────────────


def _apportion(total: int, shape: Mapping[int, int]) -> dict[int, int]:
    """Scale ``shape`` to ``total`` by largest remainder.

    Exact ratios, exact total, no float drift, and the same answer on every platform.
    """
    if total <= 0:
        return {level: 0 for level in shape}
    weight_total = sum(shape.values())
    exact = {level: total * weight / weight_total for level, weight in shape.items()}
    floors = {level: int(value) for level, value in exact.items()}
    shortfall = total - sum(floors.values())
    order = sorted(shape, key=lambda level: (-(exact[level] - floors[level]), -level))
    for level in order[:shortfall]:
        floors[level] += 1
    return floors


# ── detail generation ────────────────────────────────────────────────────────────────────────


class _Vocabulary:
    """Cached views over the gazetteer files this module reads."""

    __slots__ = ("bands", "concepts", "control_classes", "eras", "phases", "stems")

    def __init__(self) -> None:
        phrases = gaz.load("phrases")
        self.eras = tuple(
            (str(entry["key"]), int(entry["from"]), int(entry["to"]))
            for entry in gaz.as_sequence(phrases, "eras", origin="phrases.yaml")
        )
        self.concepts = {
            str(entry["key"]): {key: str(value) for key, value in entry.items() if key != "key"}
            for entry in gaz.as_sequence(phrases, "concepts", origin="phrases.yaml")
        }
        self.phases = tuple(
            str(item) for item in gaz.as_sequence(phrases, "task_phases", origin="phrases.yaml")
        )
        self.stems = {
            str(kind): tuple(str(item) for item in stems)
            for kind, stems in gaz.as_mapping(phrases, "title_stems", origin="phrases.yaml").items()
        }
        self.bands = {
            int(level): dict(entry)
            for level, entry in gaz.as_mapping(
                phrases, "consequence_bands", origin="phrases.yaml"
            ).items()
        }
        self.control_classes = tuple(
            gaz.as_sequence(gaz.load("control_classes"), "classes", origin="control_classes.yaml")
        )

    def era_key(self, year: int) -> str:
        for key, low, high in self.eras:
            if low <= year <= high:
                return key
        return self.eras[-1][0]

    def concept(self, key: str, year: int) -> str:
        try:
            surfaces = self.concepts[key]
        except KeyError as exc:
            raise gaz.GazetteerError(f"phrases.yaml: no concept {key!r}") from exc
        return surfaces[self.era_key(year)]


def _render_title(
    template: str,
    *,
    vocab: _Vocabulary,
    year: int,
    asset: str,
    asset_class: str,
    phase: str,
    energy: str,
) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        arg = match.group("arg")
        if name == "concept":
            if arg is None:
                raise gaz.GazetteerError("phrases.yaml: {concept} used without a key")
            return vocab.concept(arg, year)
        if name == "asset":
            return asset
        if name == "asset_class":
            return asset_class
        if name == "phase":
            return phase
        if name == "energy":
            return energy
        raise gaz.GazetteerError(f"phrases.yaml: unknown title placeholder {{{name}}}")

    return _PLACEHOLDER.sub(replace, template)


def _candidate_fonds(taxonomy: TaxonomyWorld, hazards: Sequence[str]) -> list[Fonds]:
    hazard_set = set(hazards)
    return [item for item in taxonomy.fonds if hazard_set & set(item.hazard_energies)]


def _choose_severity_axes(
    stream: rng.Stream, *, gate: int, kind: str, trigger: bool
) -> tuple[int, int, int, str]:
    """Return ``(actual, potential, potential_admitted, admission_reason)`` for a target gate."""
    potential_driven = kind in _POTENTIAL_ALWAYS or rng.unit(stream) < params.P_POTENTIAL_DRIVEN

    if gate == 3 and rng.unit(stream) < params.P_UNADMITTED_HIGH_POTENTIAL:
        # A high maximum-reasonable-outcome that nothing admitted.  The gate stays at 3, which is
        # the entire point: `severity_gate` is not `max(actual, potential)`.
        actual = int(rng.unit(stream) * 4)  # 0..3
        potential = 4 + int(rng.unit(stream) * 2)  # 4 or 5
        return actual, potential, 3, "potential_not_admitted"

    if potential_driven:
        # The gate is armed by the maximum reasonable outcome, not by what happened.
        actual = int(rng.unit(stream) * gate)  # 0 .. gate-1
        if gate >= 4:
            reason = "deterministic_trigger" if trigger else "human_ratified"
        else:
            reason = "potential_admitted"
        return actual, gate, gate, reason

    # Outcome-driven: the injury classification alone reaches the gate, so admission is moot.
    # It is still recorded honestly — without a trigger or a ratification, a potential of 4+
    # would only ever have been admitted at 3.
    admitted = gate if (trigger or gate < 4) else 3
    return gate, gate, admitted, "actual_outcome"


def _choose_basis(
    stream: rng.Stream, *, kind: str, gate: int, actual: int, admission_reason: str
) -> str:
    if kind == "regulator_notice":
        return "regulator_class"
    if gate >= 4:
        # A model's opinion may never arm the gate; `model_cannot_arm` is a shipped CHECK.
        # A severe outcome or a deterministic MUE trigger is a coded field; anything else that
        # reached 4 got there because a named person signed for it.
        if actual >= 3 or admission_reason == "deterministic_trigger":
            return "coded_field"
        return "human_rated"
    if admission_reason == "potential_not_admitted":
        return "model_rated" if rng.unit(stream) < 0.6 else "human_rated"
    return rng.weighted(stream, ("coded_field", "human_rated", "model_rated"), (0.42, 0.33, 0.25))


def _assert_gate_invariants(event: Event) -> None:
    if event.severity_gate != max(event.severity_actual, event.potential_admitted):
        raise RuntimeError(
            f"{event.external_ref}: severity_gate {event.severity_gate} is not "
            f"max(actual={event.severity_actual}, admitted={event.potential_admitted})"
        )
    if event.severity_gate >= 4 and event.severity_basis == "model_rated":
        raise RuntimeError(
            f"{event.external_ref}: severity_gate {event.severity_gate} with severity_basis "
            "'model_rated' violates CHECK model_cannot_arm. An LLM's rating may never arm a "
            "blocking gate; the loader would be refused and it would be right to refuse."
        )
    for value in (event.severity_actual, event.severity_potential, event.severity_gate):
        if not 0 <= value <= 5:
            raise RuntimeError(f"{event.external_ref}: severity {value} outside 0..5")
    if event.potential_admitted > event.severity_potential:
        raise RuntimeError(
            f"{event.external_ref}: admitted {event.potential_admitted} exceeds the potential "
            f"{event.severity_potential} it was admitted from"
        )


def _control_failures_for(
    stream: rng.Stream,
    *,
    vocab: _Vocabulary,
    event_ref: str,
    event_id: str,
    activity_root: str,
    allowed_energies: Sequence[str],
    kind: str,
) -> list[ControlFailure]:
    allowed = set(allowed_energies)
    candidates = [
        entry
        for entry in vocab.control_classes
        if activity_root in {str(item) for item in entry["mue"]}
    ]
    if not candidates:
        raise gaz.GazetteerError(
            f"control_classes.yaml declares no control class for fonds {activity_root!r}. Every "
            "fonds needs at least one, or events in it can carry no control failure and the "
            "mechanism join key is empty for that whole branch of the taxonomy."
        )
    matched = [
        entry for entry in candidates if allowed & {str(item) for item in entry["hazard_energies"]}
    ]
    pool = matched or candidates

    low, high = params.CONTROL_FAILURES_PER_EVENT[kind]
    count = min(low + int(rng.unit(stream) * (high - low + 1)), len(pool))
    chosen = rng.sample_without_replacement(stream, pool, count)

    failures: list[ControlFailure] = []
    for entry in sorted(chosen, key=lambda item: str(item["key"])):
        control_class = str(entry["key"])
        class_energies = [str(item) for item in entry["hazard_energies"]]
        overlap = [item for item in class_energies if item in allowed]
        hazard = rng.pick(stream, overlap or class_energies)
        role = str(entry["barrier_role"])
        if role == "either":
            role = rng.pick(stream, ("preventive", "recovery"))
        failures.append(
            ControlFailure(
                failure_id=str(rng.sid("control_failure", f"{event_ref}/{control_class}")),
                event_id=event_id,
                event_ref=event_ref,
                control_class=control_class,
                barrier_role=role,
                failure_mode=rng.pick(stream, [str(item) for item in entry["failure_modes"]]),
                icam_tier=rng.weighted(stream, _ICAM_TIERS, _ICAM_WEIGHTS),
                hazard_energy=hazard,
            )
        )
    return failures


def _consequence(
    vocab: _Vocabulary, stream: rng.Stream, *, actual: int, energy: str
) -> dict[str, Any]:
    band = vocab.bands[actual]
    return {
        "days_lost": int(band["days_lost"]),
        "energy_class": energy,
        "exposure_minutes": round(2.0 + rng.unit(stream) * 240.0, 1),
        "injuries": int(band["injuries"]),
        "label": str(band["label"]),
    }


def _source_key(site_code: str, moment: dt.datetime, external_ref: str) -> str:
    return (
        f"s3://kestrel-mainline-demo-raw/{site_code.lower()}/{moment.year:04d}/{external_ref}.pdf"
    )


# ── anchored events ──────────────────────────────────────────────────────────────────────────


def _build_anchored(
    world: SiteWorld, taxonomy: TaxonomyWorld, assets: AssetWorld, vocab: _Vocabulary
) -> tuple[list[Event], list[ControlFailure]]:
    doc = gaz.load("anchors")
    entries = gaz.as_sequence(doc, "events", origin="anchors.yaml")
    events: list[Event] = []
    failures: list[ControlFailure] = []

    for entry in entries:
        external_ref = str(entry["external_ref"])
        site = world.by_code(str(entry["site"]))
        occurred_at = clock.coerce_datetime(
            entry["occurred_at"], origin=f"anchors.yaml/{external_ref}/occurred_at"
        )
        tags = tuple(str(tag) for tag in entry["assets"])
        missing = [tag for tag in tags if not assets.has(tag)]
        if missing:
            raise gaz.GazetteerError(
                f"anchors.yaml: event {external_ref} names unknown assets {missing}"
            )
        activity_root = str(entry["activity_root"])
        fonds = taxonomy.fonds_for(activity_root)
        activity_file = str(entry["activity_file"])
        scope_id = taxonomy.scope_id(site.code, 3, activity_file)

        actual = int(entry["severity_actual"])
        potential = int(entry["severity_potential"])
        trigger = bool(entry["fatal_potential_trigger"])
        basis = str(entry["severity_basis"])
        # A potential of 4+ is admitted at face value only when a deterministic fatal-potential
        # trigger fired or a named human ratified it under signature; otherwise it counts as 3.
        admitted = potential if (trigger or basis == "human_rated" or potential < 4) else 3
        gate = max(actual, admitted)

        hazard = _anchor_hazard(fonds, assets, tags)
        stream = rng.stream(f"event.anchor/{external_ref}")
        event = Event(
            event_id=str(rng.sid("event", external_ref)),
            external_ref=external_ref,
            site_id=site.site_id,
            site_code=site.code,
            kind=str(entry["kind"]),
            occurred_at=occurred_at,
            ingested_at=occurred_at + dt.timedelta(hours=float(entry["reported_lag_hours"])),
            title=str(entry["summary_facts"][0]),
            scope_id=scope_id,
            activity_root=activity_root,
            activity_series=str(entry["activity_series"]),
            activity_file=activity_file,
            assets=tags,
            hazard_energy=hazard,
            severity_actual=actual,
            severity_potential=potential,
            severity_gate=gate,
            severity_basis=basis,
            potential_admitted=admitted,
            admission_reason="authored_anchor",
            fatal_potential_trigger=trigger,
            consequence_proxy=_consequence(vocab, stream, actual=actual, energy=hazard),
            source_object_key=_source_key(site.code, occurred_at, external_ref),
            canon_version=1,
            major=gate >= 4,
            anchored=True,
            summary_facts=tuple(str(item) for item in entry["summary_facts"]),
            fleet_sibling_of=(
                None if entry.get("fleet_sibling_of") is None else str(entry["fleet_sibling_of"])
            ),
        )
        _assert_gate_invariants(event)
        events.append(event)

        for failure in entry["control_failures"]:
            control_class = str(failure["control_class"])
            failures.append(
                ControlFailure(
                    failure_id=str(rng.sid("control_failure", f"{external_ref}/{control_class}")),
                    event_id=event.event_id,
                    event_ref=external_ref,
                    control_class=control_class,
                    barrier_role=str(failure["barrier_role"]),
                    failure_mode=str(failure["failure_mode"]),
                    icam_tier=str(failure["icam_tier"]),
                    hazard_energy=str(failure["hazard_energy"]),
                )
            )

    return events, failures


def _anchor_hazard(fonds: Fonds, assets: AssetWorld, tags: Sequence[str]) -> str:
    """The hazard energy an anchored event released: the fonds/asset intersection, first match."""
    asset_energies: set[str] = set()
    for tag in tags:
        asset_energies.update(assets.get(tag).hazard_energies)
    for candidate in fonds.hazard_energies:
        if candidate in asset_energies:
            return candidate
    return fonds.hazard_energies[0]


# ── the public builder ───────────────────────────────────────────────────────────────────────


def build_events(world: SiteWorld, taxonomy: TaxonomyWorld, assets: AssetWorld) -> EventWorld:
    """Sample the timeline, apportion severity, and flesh out every event."""
    vocab = _Vocabulary()
    anchored, anchored_failures = _build_anchored(world, taxonomy, assets, vocab)

    # Anchored majors excite the process exactly as sampled ones do.
    seeded: dict[str, list[float]] = {site.code: [] for site in world.sites}
    for event in anchored:
        if event.severity_gate >= 4:
            seeded[event.site_code].append(clock.days_between(clock.EPOCH, event.occurred_at))

    candidates: list[tuple[float, str, bool]] = []
    for site in world.sites:
        base = params.SITE_BASE_RATE_PER_YEAR.get(site.code)
        if base is None:
            raise RuntimeError(f"no base event rate declared for site {site.code!r}")
        for position, major in _sample_site_timeline(site.code, base, seeded[site.code]):
            candidates.append((position, site.code, major))
    candidates.sort(key=lambda item: (item[0], item[1]))

    # ── severity apportionment ───────────────────────────────────────────────────────────────
    total = len(candidates) + len(anchored)
    quota = _apportion(total, params.SEVERITY_TARGET_HISTOGRAM)
    for event in anchored:
        level = event.severity_gate
        if quota.get(level, 0) > 0:
            quota[level] -= 1
        else:  # an anchored severity outside the authored shape simply adds to the total
            quota.setdefault(level, 0)

    gates = _assign_gates(candidates, quota)

    # ── external references, assigned in strict time order ───────────────────────────────────
    reserved = {event.external_ref for event in anchored}
    counters: dict[tuple[str, int], int] = {}

    detail_stream_names = [f"{code}:{index:05d}" for index, (_, code, _) in enumerate(candidates)]

    events: list[Event] = list(anchored)
    failures: list[ControlFailure] = list(anchored_failures)

    for index, ((position, site_code, major), gate) in enumerate(
        zip(candidates, gates, strict=True)
    ):
        site = world.by_code(site_code)
        stream = rng.sub_stream("event.detail", detail_stream_names[index])
        occurred_at = clock.from_days(position)

        kind = (
            rng.weighted(stream, _HIGH_GATE_KINDS, _HIGH_GATE_WEIGHTS)
            if gate >= 4
            else rng.weighted(stream, params.EVENT_KINDS, params.EVENT_KIND_WEIGHTS)
        )

        members = assets.members_at(site_code)
        if not members:
            raise RuntimeError(f"site {site_code} has no member assets to attach an event to")
        primary = rng.weighted(
            stream, members, [_CRITICALITY_WEIGHT.get(item.criticality, 1.0) for item in members]
        )

        fonds_pool = _candidate_fonds(taxonomy, primary.hazard_energies)
        if not fonds_pool:
            raise RuntimeError(
                f"asset {primary.tag} carries hazard energies {primary.hazard_energies} that match "
                "no fonds; the taxonomy and the asset gazetteer disagree"
            )
        own = taxonomy.fonds_by_code.get(primary.activity_root)
        if own is not None and own in fonds_pool and rng.unit(stream) < 0.75:
            fonds = own
        else:
            fonds = rng.pick(stream, fonds_pool)

        allowed = sorted(set(fonds.hazard_energies) & set(primary.hazard_energies))
        if not allowed:
            raise RuntimeError(
                f"empty hazard intersection between {primary.tag} and fonds {fonds.code}; "
                "_candidate_fonds should have excluded it"
            )
        hazard = rng.pick(stream, allowed)

        series_label, files = rng.pick(stream, fonds.series)
        file_label = rng.pick(stream, files)
        scope_id = taxonomy.scope_id(site_code, 3, file_label)

        tags = [primary.tag]
        for companion in assets.companions(primary.tag):
            if len(tags) >= 3:
                break
            if rng.unit(stream) < 0.45:
                tags.append(companion)

        actual, potential, admitted, admission_reason = _choose_severity_axes(
            stream, gate=gate, kind=kind, trigger=fonds.fatal_potential_trigger
        )
        basis = _choose_basis(
            stream, kind=kind, gate=gate, actual=actual, admission_reason=admission_reason
        )

        prefix = _REF_PREFIX[kind]
        width = _REF_WIDTH.get(kind, 3)
        year = occurred_at.year
        counter = counters.get((kind, year), 0)
        while True:
            counter += 1
            external_ref = f"{prefix}-{year:04d}-{counter:0{width}d}"
            if external_ref not in reserved:
                break
        counters[(kind, year)] = counter
        reserved.add(external_ref)

        lag_low, lag_high = params.INGEST_LAG_HOURS[kind]
        lag = lag_low * (lag_high / lag_low) ** rng.unit(stream)

        title = _render_title(
            rng.pick(stream, vocab.stems[kind]),
            vocab=vocab,
            year=year,
            asset=primary.tag,
            asset_class=primary.asset_class,
            phase=rng.pick(stream, vocab.phases),
            energy=hazard,
        )

        event = Event(
            event_id=str(rng.sid("event", external_ref)),
            external_ref=external_ref,
            site_id=site.site_id,
            site_code=site_code,
            kind=kind,
            occurred_at=occurred_at,
            ingested_at=occurred_at + dt.timedelta(hours=lag),
            title=title,
            scope_id=scope_id,
            activity_root=fonds.code,
            activity_series=series_label,
            activity_file=file_label,
            assets=tuple(tags),
            hazard_energy=hazard,
            severity_actual=actual,
            severity_potential=potential,
            severity_gate=gate,
            severity_basis=basis,
            potential_admitted=admitted,
            admission_reason=admission_reason,
            fatal_potential_trigger=fonds.fatal_potential_trigger,
            consequence_proxy=_consequence(vocab, stream, actual=actual, energy=hazard),
            source_object_key=_source_key(site_code, occurred_at, external_ref),
            canon_version=1,
            major=major,
            anchored=False,
        )
        _assert_gate_invariants(event)
        events.append(event)
        failures.extend(
            _control_failures_for(
                stream,
                vocab=vocab,
                event_ref=external_ref,
                event_id=event.event_id,
                activity_root=fonds.code,
                allowed_energies=allowed,
                kind=kind,
            )
        )

    events.sort(key=lambda item: (item.occurred_at, item.external_ref))
    failures.sort(key=lambda item: (item.event_ref, item.control_class))

    pending = _pending_for(events, failures)
    return EventWorld(events, failures, pending)


def _assign_gates(
    candidates: Sequence[tuple[float, str, bool]], quota: Mapping[int, int]
) -> list[int]:
    """Give every sampled candidate a gate severity consistent with the apportioned quota.

    Majors take the 4s and 5s first, in time order, because the excitation that shaped the
    timeline assumed exactly those points were the severe ones.  If the Bernoulli draw produced
    too few majors the earliest non-majors are promoted; too many, and the surplus fall to 3.
    """
    remaining = {level: int(count) for level, count in quota.items()}
    high_needed = remaining.get(5, 0) + remaining.get(4, 0)

    major_positions = [index for index, item in enumerate(candidates) if item[2]]
    if len(major_positions) < high_needed:
        for index, item in enumerate(candidates):
            if len(major_positions) >= high_needed:
                break
            if not item[2]:
                major_positions.append(index)
        major_positions.sort()
    high_positions = set(major_positions[:high_needed])

    gates = [0] * len(candidates)
    stream = rng.stream("event.severity")

    for index in sorted(high_positions):
        if remaining.get(5, 0) > 0:
            gates[index] = 5
            remaining[5] -= 1
        else:
            gates[index] = 4
            remaining[4] = max(0, remaining.get(4, 0) - 1)

    low_levels = [level for level in sorted(remaining, reverse=True) if level <= 3]
    bag: list[int] = []
    for level in low_levels:
        bag.extend([level] * remaining.get(level, 0))
    low_positions = [index for index in range(len(candidates)) if index not in high_positions]
    shortfall = len(low_positions) - len(bag)
    if shortfall > 0:
        bag.extend([1] * shortfall)
    bag = rng.shuffled(stream, bag)[: len(low_positions)]
    for index, level in zip(low_positions, bag, strict=True):
        gates[index] = level
    return gates


def _pending_for(events: Sequence[Event], failures: Sequence[ControlFailure]) -> list[PendingField]:
    pending: list[PendingField] = []
    for event in events:
        pending.append(
            PendingField(
                table="mainline.event",
                key=event.external_ref,
                column="narrative",
                owner="corpus-render-cache",
                reason=(
                    "history first, text second: stage 1 authors causality and stage 2 renders "
                    "prose. The structural facts needed to render it are in the registry row."
                ),
                facts={
                    "activity_file": event.activity_file,
                    "assets": list(event.assets),
                    "hazard_energy": event.hazard_energy,
                    "kind": event.kind,
                    "severity_actual": event.severity_actual,
                    "summary_facts": list(event.summary_facts),
                },
            )
        )
        pending.append(
            PendingField(
                table="mainline.event",
                key=event.external_ref,
                column="source_sha256",
                owner="corpus-docx",
                reason=(
                    "the digest of the raw source bytes cannot exist before the source document "
                    "does. Filling it with a hash of something else would be a lie in a custody "
                    "column, and the custody column is the exhibit."
                ),
                facts={"source_object_key": event.source_object_key},
            )
        )
    for failure in failures:
        pending.append(
            PendingField(
                table="mainline.control_failure",
                key=f"{failure.event_ref}/{failure.control_class}",
                column="evidence_span",
                owner="corpus-render-cache",
                reason=(
                    "offsets are into canon_text, which does not exist until the narrative is "
                    "rendered and canonicalised."
                ),
                facts={"event_ref": failure.event_ref, "control_class": failure.control_class},
            )
        )
    return pending
