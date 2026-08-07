# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Generator parameters — every numeric knob in stage 1, in one place.

Vocabulary lives in ``mainline_corpus.gazetteer``; *rates and shapes* live here.  The split
matters: a reviewer arguing about whether the corpus has enough severity-4 events should be able
to find the number without reading a sampler, and a reviewer checking that no asset tag was
invented should be able to read the gazetteer without wading through Poisson parameters.

Nothing here is a projected column and nothing here is a database default.  These are the
parameters of the *world*, and the tests that consume them assert ranges and ratios, never
hard-coded totals (decision D10) — a corpus tweak must not turn CI red, because a founder who
learns to ignore red CI has lost the only alarm they have.
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "ANCHOR_SEVERITY_LOCK",
    "ASSET_TARGET",
    "DOC_TARGET",
    "EVENT_KINDS",
    "EVENT_KIND_WEIGHTS",
    "EXCITATION_DECAY_DAYS",
    "EXCITATION_MAX_CONCURRENT",
    "EXCITATION_PEAK",
    "EXCITATION_WINDOW_DAYS",
    "GENERATOR_VERSION",
    "MOC_TARGET",
    "PEOPLE_SEPARATED_FRACTION",
    "PEOPLE_TARGET",
    "P_MAJOR",
    "REPORTING_GROWTH_END",
    "REPORTING_GROWTH_START",
    "SEASONAL_AMPLITUDE",
    "SEASONAL_PEAK_YEAR_FRACTION",
    "SEVERITY_TARGET_HISTOGRAM",
    "SITE_BASE_RATE_PER_YEAR",
]

#: Bumped whenever a change here alters the emitted bytes.  Recorded in ``index.json`` and, via
#: ``corpus-freeze-load``, in ``corpus.lock.json``.
GENERATOR_VERSION: Final[str] = "skeleton-1.0.0"

# ── census targets ───────────────────────────────────────────────────────────────────────────
# Approximate by construction: the event count is a Poisson draw, not a fixed number, because a
# fixed number would mean the intensity function is decorative.

ASSET_TARGET: Final[int] = 180
PEOPLE_TARGET: Final[int] = 140
PEOPLE_SEPARATED_FRACTION: Final[float] = 0.30
DOC_TARGET: Final[int] = 36
MOC_TARGET: Final[int] = 340

# ── the incident timeline: a non-homogeneous, self-exciting Poisson process ───────────────────
#
# lambda_site(t) = base_site * seasonal(t) * reporting_growth(t) * excitation(t)
#
# Sampled by Ogata thinning against a bound that dominates every term, so the sample is exact
# rather than approximate.  See `events.py` for the implementation and for the proof obligation
# the bound carries.

#: Events per year per site before any modulation.  Marrindal carries the most because it is the
#: concentrator with the hydrocarbon transfer facility on it and it is the site on camera.
SITE_BASE_RATE_PER_YEAR: Final[dict[str, float]] = {
    "MRD": 18.0,
    "CVY": 9.9,
    "YND": 9.9,
    "TLG": 6.3,
}

#: Seasonal modulation, amplitude and phase.  Southern-hemisphere summer: the peak sits in
#: mid-January.  This is the "summer ambient" the 2026 MOC blames for its spurious trips, so the
#: corpus's own seasonality is what makes that justification legible rather than arbitrary.
SEASONAL_AMPLITUDE: Final[float] = 0.35
SEASONAL_PEAK_YEAR_FRACTION: Final[float] = 0.04  # ~15 January

#: Reporting maturity: near-miss reporting rates rise over twenty-two years.  Linear from
#: ``START`` at the epoch to ``END`` at ``NOW``; mean 1.0, so it re-weights the timeline without
#: changing the expected total.
REPORTING_GROWTH_START: Final[float] = 0.75
REPORTING_GROWTH_END: Final[float] = 1.25

#: Post-incident reporting spike.  After a severity-4-or-worse event at a site, that site's
#: reporting intensity jumps and decays back: people look harder for a while.  This is a genuine
#: self-excitation — the process depends on its own history — and it is what puts clusters of
#: related near-misses immediately after each major event, which is precisely the shape a
#: precursor-recall harness needs to be tested against.
EXCITATION_PEAK: Final[float] = 1.8
EXCITATION_DECAY_DAYS: Final[float] = 45.0
EXCITATION_WINDOW_DAYS: Final[float] = 180.0
#: The thinning bound assumes at most this many spikes overlap at one site.  The sampler asserts
#: it rather than trusting it; exceeding it raises instead of silently biasing the sample.
EXCITATION_MAX_CONCURRENT: Final[int] = 3

#: Probability that a candidate point is a *major* event (severity_gate >= 4).  Drawn at sample
#: time, before severities are allocated, because excitation must depend on the event's own
#: magnitude and severity allocation happens afterwards.  Value is the target histogram's own
#: 4-and-5 share, so the two agree by construction: (6 + 34) / 1150.
P_MAJOR: Final[float] = 0.0348

# ── severity ────────────────────────────────────────────────────────────────────────────────
#
# The shape is authored; the total is not.  The generator scales this histogram to whatever the
# Poisson process produced, by largest-remainder apportionment, so the RATIOS are exact and the
# TOTAL follows the timeline.  research/06-build/demo-engineering.md §4 quotes
# {5:6, 4:34, 3:180, 2:430, 1:500} at n = 1150.
SEVERITY_TARGET_HISTOGRAM: Final[dict[int, int]] = {5: 6, 4: 34, 3: 180, 2: 430, 1: 500}

#: Anchored events (the 2009 fatality, the 2013 seal fire, ...) carry the severities written in
#: ``anchors.yaml`` and are removed from the allocation before it runs, so planting an anchor
#: does not inflate the histogram.
ANCHOR_SEVERITY_LOCK: Final[bool] = True

#: Probability that an event's gate severity is driven by *potential* rather than actual outcome
#: — a near miss with a fatal maximum reasonable outcome.  Near misses and OEM alerts are always
#: potential-driven; this is the rate for everything else.
P_POTENTIAL_DRIVEN: Final[float] = 0.42

#: Probability that a severity-3 event additionally carries an UNADMITTED high potential — a
#: model or an investigator said "this could have been a 4", and the gate stayed at 3 because
#: neither a deterministic fatal-potential trigger fired nor a named human ratified it under
#: signature.  These rows are the corpus's demonstration that `severity_gate` is not merely
#: `max(actual, potential)`; they are the only rows where `severity_basis = 'model_rated'`
#: coexists with a high `severity_potential`, and they are still legal under `model_cannot_arm`
#: because the GATE stayed below 4.
P_UNADMITTED_HIGH_POTENTIAL: Final[float] = 0.14

# ── event kinds ─────────────────────────────────────────────────────────────────────────────
EVENT_KINDS: Final[tuple[str, ...]] = (
    "incident",
    "near_miss",
    "regulator_notice",
    "oem_alert",
    "audit_finding",
    "capa",
)
EVENT_KIND_WEIGHTS: Final[tuple[float, ...]] = (0.27, 0.41, 0.05, 0.04, 0.13, 0.10)

#: Control failures recorded per event, by kind.  An ICAM report with no extractable control
#: failure is not a usable event (incident-ingestion.md §5), so incidents always have at least
#: one; low-signal kinds may have exactly one.
CONTROL_FAILURES_PER_EVENT: Final[dict[str, tuple[int, int]]] = {
    "incident": (2, 5),
    "near_miss": (1, 3),
    "regulator_notice": (1, 3),
    "oem_alert": (1, 2),
    "audit_finding": (1, 3),
    "capa": (1, 2),
}

#: Ingest lag in hours, by kind — the bitemporal gap between ``occurred_at`` and ``ingested_at``.
#: A regulator notice arrives weeks later; an incident is notified within the shift.
INGEST_LAG_HOURS: Final[dict[str, tuple[float, float]]] = {
    "incident": (0.5, 30.0),
    "near_miss": (2.0, 200.0),
    "regulator_notice": (240.0, 1400.0),
    "oem_alert": (24.0, 720.0),
    "audit_finding": (48.0, 900.0),
    "capa": (24.0, 600.0),
}

# ── people ──────────────────────────────────────────────────────────────────────────────────
#: Employment start dates are spread from before the epoch to shortly before ``NOW``.
PERSON_START_EARLIEST_YEAR: Final[int] = 1996
PERSON_START_LATEST_YEAR: Final[int] = 2025
#: Minimum tenure in days before a separation may be recorded, so nobody separates before they
#: started and nobody has a two-day career.
PERSON_MIN_TENURE_DAYS: Final[float] = 400.0

# ── documents ───────────────────────────────────────────────────────────────────────────────
#: Multiplicative jitter on the authored cadence: a document with ``cadence_years: 2.0`` is
#: reissued somewhere between 1.3 and 3.0 years apart, never exactly biennially.
REVISION_INTERVAL_JITTER: Final[tuple[float, float]] = (0.65, 1.5)
#: A revision landing within this many days after a severity-4-or-worse event at the same site,
#: touching the same fonds, is marked ``driver: incident``.  This is a *structural* hint for
#: ``corpus-blame-key``; it is not a blame edge and it is not an answer key.
REVISION_INCIDENT_WINDOW_DAYS: Final[float] = 220.0
#: Fixed retypeset date for every document with ``retypeset_2016: true``.  One date, because the
#: retypeset was one project.
RETYPESET_DATE: Final[str] = "2016-11-21"

# ── MOC stream ──────────────────────────────────────────────────────────────────────────────
#: Share of MOCs by declared intent.  ``weaken`` is deliberately the smallest: the product's
#: claim is that weakenings are rare and consequential, and a corpus where a third of changes
#: are weakenings would make the gate look like a nuisance rather than a rare, correct refusal.
MOC_INTENT_WEIGHTS: Final[dict[str, float]] = {
    "strengthen": 0.31,
    "restate": 0.24,
    "introduce": 0.19,
    "replace": 0.17,
    "weaken": 0.09,
}
#: Terminal state distribution for historical MOCs.
MOC_TERMINAL_STATE_WEIGHTS: Final[dict[str, float]] = {
    "merged": 0.78,
    "closed": 0.09,
    "abandoned": 0.08,
    "dispositioned": 0.05,
}
#: MOC volume rises with the same reporting-maturity curve as events, because the two are the
#: same organisational phenomenon.
MOC_GROWTH_START: Final[float] = 0.6
MOC_GROWTH_END: Final[float] = 1.4
