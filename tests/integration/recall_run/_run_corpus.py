# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The fixture corpus the recall run loop is exercised against.

One permit, three cited clause versions, nine events, and a retrieval whose every stage lands
on a hand-checked outcome. It is small enough that the expected partition is written out in
:data:`EXPECTED_COUNTS` and can be verified by reading, and wide enough that every branch of
the admission arithmetic fires at least once:

===================  =========  ==============================================================
Event                Outcome    The branch it exists to exercise
===================  =========  ==============================================================
``E_ANC_SEV4``       blocking   Channel A. Deterministic ancestry, uncapped, ``tau`` never read
``E_ANC_SEV5``       blocking   Channels A **and** B on one event: A wins the origin, both
                                channels survive in ``features['channels']``
``E_BOND_SEV5``      blocking   Channel B at depth 1 — bonded to an *ancestor* of the permit's
                                activity node, which is where "a fatality never decays" lives
``E_PROB_HI``        blocking   Probabilistic, reranked relevant, ``p >= tau(3)``
``E_PROB_HI2``       blocking   Probabilistic, found by C **and** D, ``p >= tau(4)``
``E_PROB_LO``        silenced   ``p < tau(2)`` — a ``below_tau`` ledger row with its arithmetic
``E_PROB_SWEEP``     advisory   Coarse-sweep-only below severity 5: demoted, never blocking
``E_SEV0``           silenced   No ``tau(0)`` exists, so it is a bounded negative, not a
                                comparison against a bar that was never calibrated
``E_DUP``            deduped    MMR-suppressed sibling of ``E_PROB_HI``, attached as
                                ``also_matched`` — visible, not hidden
===================  =========  ==============================================================

The scores are deterministic by construction, not by luck
---------------------------------------------------------
``recall_policy.arms['feature_weights']`` here sets **every** slot of the frozen feature spec
to zero except ``rerank_verdict``, whose weight is 1.0. The raw score is therefore exactly the
judge's verdict code — ``1.0`` relevant, ``0.0`` not relevant, ``-1.0`` never ranked — and the
three-knot calibrator maps those to ``0.90``, ``0.30`` and ``0.05``. That is not a way of
avoiding the fusion stack: RRF, MMR and the rerank all run, and their outputs decide *which*
candidates exist and which are siblings. It is a way of making the *admission* boundary a
fact a reader can check rather than a float that drifts when someone retunes a weight.

The weights are written out slot by slot from :data:`FEATURE_NAMES` rather than by name, so a
new slot in the frozen spec makes this fixture fail loudly instead of silently acquiring a
non-zero contribution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID

from trappoint_recall.fusion.featurespec import FEATURE_NAMES

__all__ = [
    "ACTIVITY_SCOPE_ID",
    "ANCESTRY_ROWS",
    "BONDED_ROWS",
    "CITED_CLAUSES",
    "CLAUSE_ISOLATION",
    "CLAUSE_NO_CAT",
    "CLAUSE_VENTILATION",
    "CONTAINMENT",
    "CORPUS_COMMIT",
    "CORPUS_ROOT",
    "EVENTS",
    "EXPECTED_COUNTS",
    "EXPECTED_OUTCOMES",
    "EXPECTED_SILENCE_REASONS",
    "E_ANC_SEV4",
    "E_ANC_SEV5",
    "E_BOND_SEV5",
    "E_DUP",
    "E_PROB_HI",
    "E_PROB_HI2",
    "E_PROB_LO",
    "E_PROB_SWEEP",
    "E_SEV0",
    "INDEX_GENERATION",
    "PARENT_SCOPE_ID",
    "PERMIT_CONTROL_CLASSES",
    "PERMIT_ID",
    "PLAN_DIGEST",
    "POLICY_ROW",
    "POLICY_VERSION",
    "SITE_ID",
    "TAU",
    "THYMOGATE_ROW",
    "Event",
    "clause_control_classes",
    "feature_weights",
]

# ── identities ───────────────────────────────────────────────────────────────────────────
SITE_ID: Final = UUID("11111111-1111-4111-8111-111111111111")
PERMIT_ID: Final = UUID("22222222-2222-4222-8222-222222222222")
ACTIVITY_SCOPE_ID: Final = UUID("33333333-3333-4333-8333-333333333333")
PARENT_SCOPE_ID: Final = UUID("44444444-4444-4444-8444-444444444444")

CLAUSE_ISOLATION: Final = UUID("aaaaaaaa-0000-4000-8000-000000000001")
CLAUSE_VENTILATION: Final = UUID("aaaaaaaa-0000-4000-8000-000000000002")
CLAUSE_NO_CAT: Final = UUID("aaaaaaaa-0000-4000-8000-000000000003")

_COMMIT_ISOLATION: Final = "a1" * 32
_COMMIT_VENTILATION: Final = "a2" * 32
_COMMIT_NO_CAT: Final = "a3" * 32

E_ANC_SEV4: Final = UUID("e0000000-0000-4000-8000-000000000001")
E_ANC_SEV5: Final = UUID("e0000000-0000-4000-8000-000000000002")
E_BOND_SEV5: Final = UUID("e0000000-0000-4000-8000-000000000003")
E_PROB_HI: Final = UUID("e0000000-0000-4000-8000-000000000004")
E_PROB_HI2: Final = UUID("e0000000-0000-4000-8000-000000000005")
E_PROB_LO: Final = UUID("e0000000-0000-4000-8000-000000000006")
E_PROB_SWEEP: Final = UUID("e0000000-0000-4000-8000-000000000007")
E_SEV0: Final = UUID("e0000000-0000-4000-8000-000000000008")
E_DUP: Final = UUID("e0000000-0000-4000-8000-000000000009")

POLICY_VERSION: Final = "recall-policy-2026.08.01"
INDEX_GENERATION: Final = "gen-2026-08-01T00:00:00Z"
CORPUS_COMMIT: Final = bytes.fromhex("c0" * 32)
CORPUS_ROOT: Final = bytes.fromhex("c1" * 32)
PLAN_DIGEST: Final = bytes.fromhex("d0" * 32)

#: The control classes the proposed work touches. Feeds ``control_class_overlap``, whose
#: weight is zero here — the fixture asserts admission, not the weighting.
PERMIT_CONTROL_CLASSES: Final[frozenset[str]] = frozenset({"isolation", "ventilation"})

#: ARCHITECTURE 6.4's calibrated defaults. Monotone downward in severity.
TAU: Final[dict[str, float]] = {"1": 0.85, "2": 0.75, "3": 0.60, "4": 0.45, "5": 0.35}

_OCCURRED: Final = datetime(2019, 3, 14, 6, 30, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Event:
    """One ``mainline.event`` row plus the ``control_failure`` classes joined to it."""

    event_id: UUID
    severity_gate: int
    title: str
    control_classes: tuple[str, ...]


EVENTS: Final[tuple[Event, ...]] = (
    Event(E_ANC_SEV4, 4, "Isolation defeated during line break", ("isolation",)),
    Event(E_ANC_SEV5, 5, "Fatality: stored energy released on a bypassed lock", ("isolation",)),
    Event(E_BOND_SEV5, 5, "Fatality: H2S ingress in a confined space", ("ventilation",)),
    Event(E_PROB_HI, 3, "Blind flange omitted from an isolation register", ("isolation",)),
    Event(E_PROB_HI2, 4, "Purge omitted before hot work on a vent line", ("ventilation",)),
    Event(E_PROB_LO, 2, "Housekeeping finding near a vent stack", ("housekeeping",)),
    Event(E_PROB_SWEEP, 2, "Gas detector calibration overdue", ("detection",)),
    Event(E_SEV0, 0, "Uncoded observation awaiting severity assignment", ()),
    Event(E_DUP, 1, "Blind flange omitted — duplicate investigation file", ("isolation",)),
)

#: ``mainline.permit_clause``: (clause_uuid, commit hex, relation).
CITED_CLAUSES: Final[tuple[tuple[UUID, str, str], ...]] = (
    (CLAUSE_ISOLATION, _COMMIT_ISOLATION, "cites"),
    (CLAUSE_VENTILATION, _COMMIT_VENTILATION, "cites"),
    (CLAUSE_NO_CAT, _COMMIT_NO_CAT, "cites"),
)


def clause_control_classes() -> dict[UUID, tuple[str, ...]]:
    """The CAT control classes each cited clause version asserts.

    ``CLAUSE_NO_CAT`` deliberately asserts none. Channel A then has no join key for it, which
    is a fact about the retrieval rather than an absence of one: the orchestrator writes a
    ``silence_ledger(reason='unreachable')`` row naming the clause, because *retrieval was not
    attempted for it* is a different statement from *it was attempted and found nothing*.
    """
    return {
        CLAUSE_ISOLATION: ("isolation",),
        CLAUSE_VENTILATION: ("ventilation",),
        CLAUSE_NO_CAT: (),
    }


#: Rows :data:`~mainline_recall_agent.run.channels.ANCESTRY_SQL` returns, in its column order:
#: event_id, clause_uuid, commit hex, closure_gen, closure max_severity, truncated,
#: severity_gate, title, occurred_at, control_classes[], failure_modes[], hazard_energies[].
ANCESTRY_ROWS: Final[tuple[tuple[Any, ...], ...]] = (
    (
        E_ANC_SEV5,
        CLAUSE_ISOLATION,
        _COMMIT_ISOLATION,
        7,
        5,
        False,
        5,
        "Fatality: stored energy released on a bypassed lock",
        _OCCURRED,
        ["isolation"],
        ["lock_bypassed"],
        ["stored_mechanical"],
    ),
    (
        E_ANC_SEV4,
        CLAUSE_ISOLATION,
        _COMMIT_ISOLATION,
        7,
        5,
        False,
        4,
        "Isolation defeated during line break",
        _OCCURRED,
        ["isolation"],
        ["register_incomplete"],
        ["pressure"],
    ),
)

#: ``clause_blame_current.ancestor_events @> ARRAY[event]`` — the inverted-index confirmation
#: channel A re-derives every admission through. An event absent from this map is one the
#: index cannot confirm, and channel A refuses it rather than trusting the array it just read.
CONTAINMENT: Final[dict[UUID, tuple[tuple[UUID, str], ...]]] = {
    E_ANC_SEV5: ((CLAUSE_ISOLATION, _COMMIT_ISOLATION),),
    E_ANC_SEV4: ((CLAUSE_ISOLATION, _COMMIT_ISOLATION),),
}

#: Rows :data:`~mainline_recall_agent.run.channels.BONDED_SEV5_SQL` returns:
#: event_id, severity_gate, title, occurred_at, scope_id, bond_basis, depth.
BONDED_ROWS: Final[tuple[tuple[Any, ...], ...]] = (
    (
        E_ANC_SEV5,
        5,
        "Fatality: stored energy released on a bypassed lock",
        _OCCURRED,
        ACTIVITY_SCOPE_ID,
        "same_activity",
        0,
    ),
    (
        E_BOND_SEV5,
        5,
        "Fatality: H2S ingress in a confined space",
        _OCCURRED,
        PARENT_SCOPE_ID,
        "ancestor_activity",
        1,
    ),
)


def feature_weights() -> dict[str, float]:
    """Zero on every frozen slot except ``rerank_verdict``.

    Written from :data:`FEATURE_NAMES` rather than by hand: a slot added to the frozen spec
    lands here as an explicit zero, so the fixture's determinism survives a spec change
    instead of quietly inheriting a default weight from the shipped preliminary set.
    """
    weights = dict.fromkeys(FEATURE_NAMES, 0.0)
    weights["rerank_verdict"] = 1.0
    return weights


#: Maps the judge's verdict code straight onto ``p_relevant``:
#: ``-1 -> 0.05`` (never ranked), ``0 -> 0.30`` (not relevant), ``1 -> 0.90`` (relevant).
_CALIBRATOR: Final[dict[str, Any]] = {
    "schema": "trappoint.recall.calibrator.isotonic/1",
    "increasing": True,
    "out_of_bounds": "clip",
    "interpolation": "linear_between_knots",
    "x": [-1.0, 0.0, 1.0],
    "y": [0.05, 0.30, 0.90],
    "provenance": {
        "fixture": "tests/integration/recall_run/_run_corpus.py",
        "note": (
            "a three-knot fixture calibrator, NOT a fitted artefact. It exists so the "
            "admission boundary in this suite is a fact a reader can check."
        ),
    },
}

#: One anchored ``mainline_meas.recall_policy`` row, in POLICY_SQL's column order.
POLICY_ROW: Final[tuple[Any, ...]] = (
    POLICY_VERSION,
    3,
    "BAAI/bge-large-en-v1.5@fixture",
    "au.anthropic.claude-opus-5",
    "recall.listwise/1",
    32,
    json.dumps(TAU),
    json.dumps({"feature_weights": feature_weights()}),
    json.dumps(_CALIBRATOR),
    4096,
    "cccccccc-0000-4000-8000-00000000000f",
)

#: The THYMOGATE certificate POLICY_ROW names, in THYMOGATE_SQL's column order. Clean.
THYMOGATE_ROW: Final[tuple[Any, ...]] = (
    "cccccccc-0000-4000-8000-00000000000f",
    "b1" * 32,
    "b2" * 32,
    24,
    0,
    "pass",
)

#: The partition this corpus must produce, exactly. MI17 in longhand.
EXPECTED_COUNTS: Final[dict[str, int]] = {
    "n_candidates": 9,
    "n_blocking": 5,
    "n_advisory": 1,
    "n_silenced": 2,
    "n_deduped": 1,
}

EXPECTED_OUTCOMES: Final[dict[UUID, str]] = {
    E_ANC_SEV4: "blocking",
    E_ANC_SEV5: "blocking",
    E_BOND_SEV5: "blocking",
    E_PROB_HI: "blocking",
    E_PROB_HI2: "blocking",
    E_PROB_SWEEP: "advisory",
    E_PROB_LO: "silenced",
    E_SEV0: "silenced",
    E_DUP: "deduped",
}

#: Every ``silence_ledger`` row a clean run of this corpus writes, as a sorted multiset of
#: reasons. Five withheld warnings, each with its arithmetic attached — which is the entire
#: evidentiary point of the ledger.
EXPECTED_SILENCE_REASONS: Final[tuple[str, ...]] = (
    "below_tau",  # E_PROB_LO scored 0.30 against tau(2) = 0.75
    "bounded_negative",  # E_PROB_SWEEP: a coarse-sweep hit never blocks below severity 5
    "bounded_negative",  # E_SEV0: no tau(0) exists, so no comparison was made
    "dedup_sibling",  # E_DUP collapsed into E_PROB_HI and attached as also_matched
    "unreachable",  # CLAUSE_NO_CAT asserts no CAT class, so channel A never ran for it
)
