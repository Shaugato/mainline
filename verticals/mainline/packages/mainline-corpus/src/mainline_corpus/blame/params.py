# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Every numeric knob in stage 1b — the authored causality — in one place.

The split mirrors ``skeleton/params.py``: vocabulary lives in ``mainline_corpus.gazetteer``,
*rates and shapes* live here.  A reviewer arguing about whether 55 % of causal facts leaving a
documentary trace is realistic should find the number without reading a sampler.

Three of these constants are **exact targets rather than shapes**, and that is deliberate.
``DECOY_TARGET``, ``ORPHAN_TARGET``, ``WEAKENING_CHAIN_TARGET`` and ``FLEET_GROUP_TARGET`` come
from ``research/06-build/demo-engineering.md`` §1 stage 5, where each rate exists to make one
architectural claim provable on camera.  A corpus with 58 decoys instead of 60 would still be a
fine corpus and a worse *exhibit*, because the number is quoted.  Everything else here is a
shape, and the verifier asserts ratios rather than totals (decision D10).
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "BLAME_RATIO_MAX",
    "BLAME_RATIO_MIN",
    "CAUSAL_WINDOW_DAYS",
    "CLAUSE_COUNT_BY_FAMILY",
    "DECOY_TARGET",
    "DERIVED_WINDOW_DAYS",
    "FLEET_GROUP_TARGET",
    "GENERATOR_VERSION",
    "NEGATIVE_CONTROL_FLOOR",
    "ORPHAN_TARGET",
    "P_DOC_TRACE_BASE",
    "SPLIT_DOC_TARGET",
    "WEAKENING_CHAIN_TARGET",
]

#: Bumped whenever a change here alters the emitted bytes.  Recorded in ``index.json`` and, via
#: ``corpus-freeze-load``, in ``corpus.lock.json``.
GENERATOR_VERSION: Final[str] = "blame-1.0.0"

# ── the clause universe ──────────────────────────────────────────────────────────────────────
#
# Blame edges point at `clause_uuid`, and every one of the eight realism injectors is a
# statement about clauses rather than about documents.  The clause universe is therefore
# authored here, from the document set and revision cadence stage 1 scheduled.  It is
# STRUCTURE ONLY: which obligations exist, where each was born, what control class it asserts,
# which revision touched it and how the edit moved the control.  Not one word of clause text is
# written here; `corpus-render-cache` renders the prose and `corpus-docx` sets the type.

#: Clauses per document, by code family, as an inclusive range drawn per document.  A permit
#: form set is not a procedure and a one-page safety alert is not a standard; a single global
#: rate would flatten the corpus into a shape no document control system has ever had.
CLAUSE_COUNT_BY_FAMILY: Final[dict[str, tuple[int, int]]] = {
    "PRO": (28, 44),
    "STD": (24, 36),
    "PTW": (14, 22),
    "MOC": (4, 8),
    "ALERT": (3, 6),
}

#: Clauses per numbered section of a generation-1 document.  Sections are the *procedural*
#: grouping — prepare, isolate, verify, execute, restore — which is exactly the organising
#: principle the 2016 retypeset abandons (see ``RETYPESET_CHAPTER_ORDER``).
SECTION_SIZE: Final[tuple[int, int]] = (3, 6)

#: Probability that a generation-1 clause carries a third numbering level and a bracketed item,
#: ``7.3.2(b)``.  Real procedures mix depths; a corpus where every label has two components
#: makes the retypeset's label change look like a formatting tweak rather than a renumbering.
P_DEEP_LABEL: Final[float] = 0.22

#: Probability that a clause is born at the document's first issue rather than being introduced
#: by a later revision.  The remainder are spread across the cadence, which is what gives
#: ``control_delta = 'introduce'`` a real population and gives orphan clauses somewhere to live.
P_BORN_AT_FIRST_ISSUE: Final[float] = 0.68

#: Fraction of a document's live clauses a revision touches, by the driver stage 1 recorded.
#: A retypeset touches every clause by definition and is not listed.  These are *fractions of
#: live clauses*, drawn uniformly from the range, then clamped to at least one clause: a
#: revision that changed nothing would not have been issued.
TOUCH_FRACTION_BY_DRIVER: Final[dict[str, tuple[float, float]]] = {
    "routine_review": (0.08, 0.20),
    "incident": (0.14, 0.30),
    "regulator": (0.10, 0.24),
    "moc": (0.10, 0.26),
    "introduce": (0.05, 0.12),
}

#: Control-delta weights for a touched clause, by driver.  ``remove`` is rare everywhere: a
#: procedure that deletes obligations at the rate it restates them is not a procedure anybody
#: has worked under.  ``weaken`` is rarest of all outside the weakening-chain injector, for the
#: reason ``skeleton/params.py`` gives about MOC intents — a corpus where weakenings are common
#: makes a correct refusal look like a nuisance.
DELTA_WEIGHTS_BY_DRIVER: Final[dict[str, dict[str, float]]] = {
    "routine_review": {"restate": 0.62, "strengthen": 0.26, "weaken": 0.07, "remove": 0.05},
    "incident": {"restate": 0.22, "strengthen": 0.74, "weaken": 0.02, "remove": 0.02},
    "regulator": {"restate": 0.24, "strengthen": 0.70, "weaken": 0.03, "remove": 0.03},
    "moc": {"restate": 0.46, "strengthen": 0.34, "weaken": 0.14, "remove": 0.06},
    "retypeset": {"restate": 1.0},
    "introduce": {"restate": 0.70, "strengthen": 0.30},
}

# ── causality ────────────────────────────────────────────────────────────────────────────────

#: How far back a clause revision may reach for the event that generated it.  Wider than
#: ``skeleton.params.REVISION_INCIDENT_WINDOW_DAYS`` (220) on purpose: an investigation that
#: closes in six months and a procedure on a two-year cadence produce a revision that is a year
#: downstream of its own cause, and a corpus that only ever puts causes inside the *derived*
#: window would make ``derived_documentary`` trivially complete.
CAUSAL_WINDOW_DAYS: Final[float] = 400.0

#: The window inside which two independent documentary facts *co-locate* a cause: the commit
#: landed within this many days of the event and its CAT delta intersects the failed controls.
#: This is the ``derived_documentary`` test from incident-ingestion.md §6, and it is the same
#: 220 days stage 1 used for its structural hint — deliberately, so the two agree.
DERIVED_WINDOW_DAYS: Final[float] = 220.0

#: Probability that a clause revision inside the causal window of a mechanism-matching event was
#: in fact generated by that event.  The complement is the honest half of the corpus: revisions
#: that look causal and are not, which is what the negative-control set is drawn from.
P_INCIDENT_DRIVEN: Final[float] = 0.42

#: The same probability when stage 1 already recorded ``driver = 'incident'`` and named the
#: event.  Not 1.0: a revision issued after an incident routinely also carries clauses that had
#: nothing to do with it, and a corpus that attributed every clause of an incident revision to
#: the incident would be marking its own homework.
P_INCIDENT_DRIVEN_WHEN_DECLARED: Final[float] = 0.78

#: DECISION D7.  Each true causal fact independently draws whether it left a documentary trace.
#: The draw is what makes held-out asserted-link masking have real positives and gives the
#: Chapman capture-recapture estimator something to estimate; without it, channel A would see
#: either everything or nothing and both numbers would be meaningless.
#:
#: The base is 0.55.  The adjustments below are not decoration: a regulator's improvement notice
#: names the clause it requires in the notice itself, and a fatality's CAPA register is the most
#: complete document any mine produces, so those facts leave traces far more often than a
#: near-miss whose corrective action was a verbal briefing.  The realised mean is asserted to
#: stay inside ``P_DOC_TRACE_MEAN_BAND`` so a future adjustment cannot silently drift the corpus
#: into "everything is asserted".
P_DOC_TRACE_BASE: Final[float] = 0.55
P_DOC_TRACE_BY_KIND: Final[dict[str, float]] = {
    "regulator_notice": 0.84,
    "capa": 0.76,
    "incident": 0.58,
    "oem_alert": 0.50,
    "audit_finding": 0.44,
    "near_miss": 0.30,
}
#: Additive bonus when the generating event armed the gate (``severity_gate >= 4``).
P_DOC_TRACE_SEVERE_BONUS: Final[float] = 0.14
#: Additive bonus when stage 1 recorded ``driver = 'incident'`` and named this very event: the
#: revision-history line exists, which IS the trace.
P_DOC_TRACE_DECLARED_BONUS: Final[float] = 0.30
P_DOC_TRACE_MEAN_BAND: Final[tuple[float, float]] = (0.48, 0.62)

#: Share of *untraced* causal facts that an SME later confirmed under signature during
#: adjudication.  These become ``asserted_human``: active, blocking, and invisible to channel A,
#: which is precisely the population that makes capture-recapture's independence assumption
#: worth stating out loud.
P_ASSERTED_HUMAN_OF_UNTRACED: Final[float] = 0.09

#: Days a provisional edge survives before it lapses to ``dormant``.  An audit that accumulates
#: an ever-growing wall of unreviewed machine claims is itself a plaintiff exhibit
#: (incident-ingestion.md §6), so every provisional edge carries an expiry.
PROVISIONAL_DAYS: Final[float] = 180.0

#: The band ``blame_edges / clause_versions`` must land in.  demo-engineering.md §1 stage 4
#: quotes 2310 / 11240 = 0.206 in its illustrative lock; the generator asserts the ratio rather
#: than either total, and refuses to emit a corpus outside the band.
BLAME_RATIO_MIN: Final[float] = 0.15
BLAME_RATIO_MAX: Final[float] = 0.30

# ── the eight realism injectors (demo-engineering.md §1 stage 5) ──────────────────────────────

#: One full retypeset per document, all on one date, because the retypeset was one project.
#: The date itself is ``skeleton.params.RETYPESET_DATE``; only documents whose first issue
#: precedes it and whose gazetteer entry says ``retypeset_2016: true`` are in scope.
#:
#: The generation-2 template numbers clauses ``chapter.barrier.item`` where the chapter is the
#: clause's control class, ordered as the new template presents them, and ``barrier`` is 1 for a
#: preventive control and 2 for a recovery control.  That is a GENUINELY DIFFERENT organising
#: principle from generation 1's procedural sections — which is decision D6, and is why clause
#: reflow in this corpus is real rather than a string substitution.
RETYPESET_BARRIER_INDEX: Final[dict[str, int]] = {"preventive": 1, "recovery": 2}

#: The order the generation-2 template presents containment controls in: process order, from
#: the transfer itself outward to the last line of defence.  Authored for this one fonds because
#: the spine's clause must land at ``5.2.1`` (``anchors.yaml``'s ``clause_label_2016``) and the
#: film shows that label; every other fonds orders its chapters by control-class key, which is
#: still a different order from the procedural one and needs no authoring.
RETYPESET_CHAPTER_ORDER: Final[dict[str, tuple[str, ...]]] = {
    "CONTAINMENT-OF-HYDROCARBONS": (
        "HYDROCARBON_TRANSFER_CONTROL",
        "BUND_AND_DRAINAGE_CONTAINMENT",
        "EMERGENCY_ISOLATION_ON_RELEASE",
        "SEAL_SUPPORT_SYSTEM_INTEGRITY",
        "SEAL_FACE_TEMPERATURE_ALARM",
    ),
}

#: Documents that split in 2019, migrating a share of their clauses to another live document at
#: the same site.  The spine's ``PRO-MEC-014 -> STD-ISO-006`` under ``MOC-2019-0221`` is one of
#: the eight and is planted; the other seven are selected deterministically.
SPLIT_DOC_TARGET: Final[int] = 8
SPLIT_MIGRATION_FRACTION: Final[tuple[float, float]] = (0.18, 0.34)
SPLIT_YEAR: Final[int] = 2019

#: Clauses with no recorded origin: an event generated them and the record says nothing at all.
#: The only edge the system can offer is ``inferred_semantic``, which never blocks a permit and
#: blocks exactly one thing — a commit that weakens the clause it points at.  That is beat 3.
ORPHAN_TARGET: Final[int] = 12
#: An orphan's cause must sit OUTSIDE the derived window, or the co-location test would find it
#: and the clause would not be an orphan.
ORPHAN_MIN_LAG_DAYS: Final[float] = 260.0
ORPHAN_MAX_LAG_DAYS: Final[float] = 1500.0

#: Slow weakening across three MOCs and roughly six years, on one clause per chain.  Fixity
#: patrol and bisect exist for exactly this shape: no single step looks like much.
WEAKENING_CHAIN_TARGET: Final[int] = 4
WEAKENING_CHAIN_STEPS: Final[int] = 3
WEAKENING_CHAIN_SPAN_YEARS: Final[tuple[float, float]] = (4.5, 7.5)

#: Decoy events: same asset, same date window, same era vocabulary, DIFFERENT hazard energy and
#: a disjoint failed-control class set.  They separate mechanism matching from vocabulary
#: matching, and they are SELECTED from the sampled timeline rather than injected into it —
#: ``mainline.event`` is stage 1's table and a second writer would fork the corpus.
DECOY_TARGET: Final[int] = 60
DECOY_WINDOW_DAYS_LADDER: Final[tuple[float, ...]] = (120.0, 240.0, 400.0, 700.0, 1100.0)

#: Fleet siblings: one canonical event, three sites, locally reworded clauses.  One canonical
#: event with three bonds, never three checks.
FLEET_GROUP_TARGET: Final[int] = 9
FLEET_SITES_PER_GROUP: Final[int] = 3

#: Negative controls: clause revisions with a documented NON-incident cause, each paired with
#: the event a linker would most plausibly attribute it to.  The false-attribution rate on this
#: set is the number a buyer's lawyer asks for first, so the set is drawn adversarially — the
#: nearest plausible distractor, never a random one.
NEGATIVE_CONTROL_FLOOR: Final[int] = 200
NEGATIVE_CONTROL_TARGET: Final[int] = 260
NEGATIVE_CONTROL_WINDOW_DAYS: Final[float] = 400.0
#: The documented non-incident causes, and their share.  Every one of these is a real reason a
#: controlled document is reissued and none of them is an incident.
NON_INCIDENT_CAUSE_WEIGHTS: Final[dict[str, float]] = {
    "scheduled_review": 0.46,
    "template_migration": 0.22,
    "regulatory_update": 0.19,
    "typo_fix": 0.13,
}

#: Vocabulary drift is emitted as a dated term-substitution schedule the renderer consumes, plus
#: the dated pairs ``corpus-embed-lift`` measures lexical against semantic recall over.  Both
#: come from ``phrases.yaml``'s era table; nothing new is invented here.
DRIFT_PAIR_ERA_GAP: Final[int] = 2
