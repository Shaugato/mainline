# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Stage 1c parameters — the rates and windows of the MOC stream's scope and lifecycle.

Vocabulary lives in ``mainline_corpus.gazetteer``; the *world's* rates live in
``mainline_corpus.skeleton.params``.  What lives here is narrower: how wide a change request's
declared scope is, how long each of its transitions takes, and how often the gate re-opens.

Nothing here is a projected column and nothing here is a database default.  Tests over this
stage assert invariants and ratios, never hard-coded totals (decision D10).
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "ADMISSIBLE_R5_DRIVERS",
    "EPOCH_BUMP_PROBABILITY",
    "GENERATOR_VERSION",
    "MAX_VEHICLES_PER_REVISION",
    "PROPOSAL_TERMINAL_STATES",
    "REALISED_TERMINAL_STATES",
    "REOPEN_PROBABILITY",
    "SCOPE_SIZE_WEIGHTS",
    "SCOPE_WINDOW_DAYS",
    "STEP_LAG_DAYS",
    "TERMINAL_TRANSITIONS",
]

#: Bumped whenever a change here alters the emitted bytes.  Recorded in this stage's
#: ``index.json`` and, via ``corpus-freeze-load``, in ``corpus.lock.json``.
GENERATOR_VERSION: Final[str] = "moc-stream-1.0.0"

# ── declared scope ──────────────────────────────────────────────────────────────────────────
#
# A change request's scope is the set of clauses it declares it touches.  Four of the five
# binding bases are read from facts another generator already authored; the fifth (``R5``) is
# authored here and is the only one that draws.

#: How far after ``opened_at`` this stage will look for the document revision a change request
#: was the vehicle for.  Bounded deliberately: a change record that "caused" a revision two years
#: later is not a change record, it is a coincidence, and a corpus that binds one has fabricated
#: the relation the gate reads.
SCOPE_WINDOW_DAYS: Final[float] = 400.0

#: How many approved changes one document reissue may implement.
#:
#: Not one.  A controlled document is not reissued per change request — a reissue consolidates
#: every change approved since the last one, which is why change registers advance in gaps while
#: revision numbers advance by one.  Modelling it as one-to-one would leave half the register
#: declaring nothing, and it would also cost the corpus the only natural source of two subjects
#: declaring the same clause, which is precisely what ``open_conflicts`` exists to count.
#:
#: Bounded at three because a reissue that implements a dozen changes is not a reissue, it is a
#: rewrite, and the corpus already has a retypeset injector for that.
MAX_VEHICLES_PER_REVISION: Final[int] = 3

#: Clauses in a change request's declared scope, as ``count -> weight``.  Most changes touch one
#: or two clauses; the long tail is what makes ``open_blocking`` interesting, because a subject
#: with a single obligation never demonstrates that the counter is a count.
SCOPE_SIZE_WEIGHTS: Final[dict[int, float]] = {1: 0.42, 2: 0.27, 3: 0.16, 4: 0.09, 5: 0.06}

#: Drivers a change request may legitimately be the administrative vehicle for.
#:
#: ``incident`` is ABSENT and that is the load-bearing exclusion.  The blame lane authored the
#: causal story of every incident-driven revision; binding an MOC to one here would assert that
#: the change record caused the edit, which contradicts an answer key that says an incident did.
#: ``retypeset`` is absent because the 2016 reflow was one project, not three hundred changes,
#: and ``introduce`` is absent because a document's first issue predates any change register
#: entry against it.
ADMISSIBLE_R5_DRIVERS: Final[frozenset[str]] = frozenset({"routine_review", "moc", "regulator"})

#: Terminal states whose change landed: their declared scope pins a revision that really happened.
REALISED_TERMINAL_STATES: Final[frozenset[str]] = frozenset({"merged", "closed"})

#: Terminal states whose change did not land: their declared scope pins the version the change
#: request declared it was editing, and no revision follows.  ``MOC-2026-0413`` is one of these,
#: and it is the film's refusal.
PROPOSAL_TERMINAL_STATES: Final[frozenset[str]] = frozenset({"abandoned", "dispositioned"})

# ── lifecycle ───────────────────────────────────────────────────────────────────────────────
#
# The edges below are a SUBSET of `mainline.subject_transition`, which is the authority.  This
# stage never invents an edge; `verify.py` re-checks every planned edge against the seeded set
# parsed out of migration 0017b, so a change to the state machine turns this stage red rather
# than producing a plan the database will refuse one worker downstream.

#: ``terminal state -> the ordered edges that reach it from ``draft``.
TERMINAL_TRANSITIONS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "abandoned": (("draft", "abandoned"),),
    "dispositioned": (
        ("draft", "checks_materialised"),
        ("checks_materialised", "dispositioned"),
    ),
    "merged": (
        ("draft", "checks_materialised"),
        ("checks_materialised", "dispositioned"),
        ("dispositioned", "merged"),
    ),
    "closed": (
        ("draft", "checks_materialised"),
        ("checks_materialised", "dispositioned"),
        ("dispositioned", "merged"),
        ("merged", "closed"),
    ),
}

#: Probability that a gated change request re-materialises its checks once — a further precursor
#: arrived while the gate was open, so ``checks_materialised -> checks_materialised`` fires and
#: ``gate_epoch`` bumps.  This is the ordinary, non-dramatic version of the epoch pin, and a
#: corpus in which it never happens leaves the pin untested by anything but the demo.
EPOCH_BUMP_PROBABILITY: Final[float] = 0.18

#: Probability that a change request that had already reached ``dispositioned`` is knocked back
#: to ``checks_materialised`` by a precursor that arrived after disposition, and then disposes
#: again.  Rarer than a re-materialisation, and consequential: it is the shape of the M8 beat.
REOPEN_PROBABILITY: Final[float] = 0.07

#: Inclusive day-range for the lag between consecutive transitions, per edge.  A change request
#: that opens and merges in the same second is not a change request; one that takes nine years
#: is a data-quality defect.  Compressed proportionally when the plan would otherwise run past
#: the corpus's ``NOW``.
STEP_LAG_DAYS: Final[dict[tuple[str, str], tuple[float, float]]] = {
    ("draft", "checks_materialised"): (1.0, 21.0),
    ("draft", "abandoned"): (3.0, 90.0),
    ("checks_materialised", "checks_materialised"): (0.5, 14.0),
    ("checks_materialised", "dispositioned"): (2.0, 45.0),
    ("dispositioned", "checks_materialised"): (0.5, 20.0),
    ("dispositioned", "merged"): (0.5, 18.0),
    ("merged", "closed"): (7.0, 120.0),
}
