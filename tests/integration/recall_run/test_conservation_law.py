# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""L3 — the silence conservation law, and the three laws that travel with it.

``candidates_conserved`` (MI17) is a database ``CHECK`` and it will refuse a lying run row.
The point of enforcing the same law in code is not redundancy for its own sake:

> The conservation law must never be the **first** thing that notices.

A ``23514`` arriving at ``INSERT INTO recall_run`` says one integer disagrees with four
others. It does not say *which candidate went missing*, and by then the retrieval has been
discarded and the only available diagnosis is to run it again. Every assertion below is
therefore about the *message* as much as the refusal: the exception must name the event id.

The database half is exercised against a live cluster by
``tests/integration/recall_schema/test_rc05_rc06_conservation.py``. Neither suite replaces the
other: that one asserts the constraint refuses a bad row, this one asserts the agent never
presents one.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from _run_corpus import E_ANC_SEV5, E_BOND_SEV5, E_PROB_HI, EXPECTED_COUNTS
from mainline_recall_agent.run.conservation import CandidateRow, enforce_conservation
from mainline_recall_agent.run.errors import ConservationViolated


def row(
    event_id: UUID,
    *,
    outcome: str = "blocking",
    origin: str = "recall_probabilistic",
    severity: int = 3,
    p_relevant: float = 0.9,
    tau_applied: float = 0.6,
    rank: int = 1,
) -> CandidateRow:
    """One assembled ``recall_candidate`` row."""
    return CandidateRow(
        event_id=event_id,
        rank=rank,
        severity=severity,
        p_relevant=p_relevant,
        tau_applied=tau_applied,
        outcome=outcome,
        origin=origin,
        features={"channels": ["C"]},
    )


def test_a_conserved_partition_is_accepted() -> None:
    """Green half. Without it, every refusal below could be a function that always raises."""
    rows = [
        row(uuid4(), outcome="blocking"),
        row(uuid4(), outcome="advisory"),
        row(uuid4(), outcome="silenced"),
        row(uuid4(), outcome="deduped"),
    ]
    report = enforce_conservation(rows)
    assert report.conserved
    assert report.as_dict() == {
        "n_candidates": 4,
        "n_blocking": 1,
        "n_advisory": 1,
        "n_silenced": 1,
        "n_deduped": 1,
    }


def test_the_law_holds_over_the_real_run(clean_outcome) -> None:
    """The shipped run loop's own output satisfies the law it enforces."""
    report = enforce_conservation(
        clean_outcome.candidates,
        bonded_event_ids=(E_ANC_SEV5, E_BOND_SEV5),
    )
    assert report.as_dict() == EXPECTED_COUNTS


def test_a_duplicated_candidate_is_named() -> None:
    """``recall_candidate`` is keyed ``(run_id, event_id)``: a rediscovery is not a second row."""
    duplicate = uuid4()
    with pytest.raises(ConservationViolated, match=str(duplicate)):
        enforce_conservation([row(duplicate), row(duplicate, outcome="advisory")])


def test_a_lost_bonded_fatality_is_named(clean_outcome) -> None:
    """MI16 in code: an event channel B found and admission dropped must stop the run."""
    survivors = [
        candidate
        for candidate in clean_outcome.candidates
        if candidate.event_id != E_BOND_SEV5
    ]
    with pytest.raises(ConservationViolated, match=str(E_BOND_SEV5)) as raised:
        enforce_conservation(survivors, bonded_event_ids=(E_ANC_SEV5, E_BOND_SEV5))
    assert "fatality never decays" in str(raised.value)


def test_a_downgraded_bonded_fatality_is_named() -> None:
    """Present but not blocking is the subtler version of the same defect."""
    bonded = uuid4()
    rows = [row(bonded, outcome="advisory", origin="bonded", severity=5, tau_applied=0.0)]
    with pytest.raises(ConservationViolated, match="unconditionally"):
        enforce_conservation(rows, bonded_event_ids=(bonded,))


def test_the_probabilistic_cap_is_enforced_before_insert() -> None:
    """Recall lead D2: four probabilistic blocking checks is a refusal, not a rounding."""
    rows = [row(uuid4()) for _ in range(4)]
    with pytest.raises(ConservationViolated, match="cap of 3"):
        enforce_conservation(rows, cap=3)


def test_channels_a_and_b_are_not_capped() -> None:
    """A cap that could suppress a bonded fatality would make MI16 unsatisfiable."""
    bonded = [uuid4() for _ in range(4)]
    rows = [
        row(event_id, origin="bonded", severity=5, tau_applied=0.0, p_relevant=1.0)
        for event_id in bonded
    ]
    report = enforce_conservation(rows, bonded_event_ids=bonded, cap=3)
    assert report.n_blocking == 4


def test_an_uncalibrated_score_is_refused() -> None:
    """Admission compares a calibrated probability; a raw cosine means something else."""
    with pytest.raises(ConservationViolated, match="not a probability"):
        enforce_conservation([row(uuid4(), p_relevant=17.4)])


def test_an_unknown_outcome_is_refused() -> None:
    """The partition has four cells and no fifth; a new one would not close."""
    with pytest.raises(ConservationViolated, match="outside"):
        enforce_conservation([row(uuid4(), outcome="probably_fine")])


def test_a_projection_disagreement_rolls_the_whole_run_back(build_harness) -> None:
    """P2 applied to ourselves: if the database disagrees about severity, we wrote nothing.

    ``fn_candidate_project`` projects ``recall_candidate.severity`` from
    ``event.severity_gate``. Severity-Graded Admission chose ``tau`` by severity, so a
    disagreement means at least one candidate was measured against a bar it should never have
    been held to — plausibly a fatality thresholded as a severity 2. Rolling back is the only
    fail-closed answer; a receipt that says otherwise must not survive.
    """
    harness = build_harness()
    # The database will project severity 5 for a candidate admission scored at 3.
    harness.cluster.severity_projection[E_PROB_HI] = 5

    with pytest.raises(ConservationViolated, match=str(E_PROB_HI)) as raised:
        harness.run()
    assert "fn_candidate_project" in str(raised.value)

    assert harness.cluster.transactions == [], "no transaction may commit after the refusal"
    assert harness.cluster.rolled_back, "the write was attempted and rolled back"
    assert harness.cluster.committed_counts() == {
        "recall_run": 0,
        "recall_candidate": 0,
        "recall_certificate": 0,
        "silence_receipt": 0,
        "silence_ledger": 0,
    }
    assert harness.transport.posts == [], "nothing may be handed to the kernel after a refusal"
