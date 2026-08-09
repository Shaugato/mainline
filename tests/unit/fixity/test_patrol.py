# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One occurrence, start to finish: accounting, routing and write order."""

from __future__ import annotations

import dataclasses
import uuid
from decimal import Decimal

import pytest
from fixity_corpus import (
    AS_OF_HLC,
    CLAUSE_ISOLATION,
    FINISHED,
    HISTORIAN_BAR,
    STARTED,
    binding,
    gas_test_cat,
    observation,
    scope,
)
from mainline_fixity import (
    PatrolAccountUnbalanced,
    PatrolRun,
    Subject,
    UnstartedPatrol,
    run_patrol,
)


def subjects_for(*items: Subject) -> tuple[Subject, ...]:
    return items


def drifting() -> Subject:
    return Subject(
        binding=binding(),
        documented=gas_test_cat("10"),
        observed=observation(gas_test_cat("14"), err_bar=HISTORIAN_BAR),
    )


def agreeing() -> Subject:
    return Subject(
        binding=binding(CLAUSE_ISOLATION),
        documented=gas_test_cat("10"),
        observed=observation(gas_test_cat("10"), err_bar=HISTORIAN_BAR, obs_seed="obs-2"),
    )


def run(*items: Subject):
    return run_patrol(
        scope(),
        items,
        __import__("fixity_corpus").build_registry(),
        __import__("fixity_corpus").COMMIT,
        as_of_hlc=AS_OF_HLC,
        started_at=STARTED,
        finished_at=FINISHED,
    )


def test_the_denominator_is_stated_and_the_arithmetic_closes():
    result = run(drifting(), agreeing())
    assert result.run.account.n_in_scope == 2
    assert result.run.account.n_checked == 2
    assert result.run.account.n_not_checked == 0
    assert result.run.account.balanced()


def test_a_proposed_binding_is_in_the_denominator_and_out_of_the_numerator():
    hypothesis = Subject(
        binding=binding(bind_kind="proposed"),
        documented=gas_test_cat("10"),
        observed=observation(gas_test_cat("14"), err_bar=HISTORIAN_BAR),
    )
    result = run(drifting(), hypothesis)
    assert result.run.account.n_in_scope == 2
    assert result.run.account.n_checked == 1
    assert result.run.account.n_not_checked == 1
    # A hypothesis about which clause governs which asset must not produce a
    # finding attributed to a clause nobody bound.
    assert len(result.findings) == 1


def test_agreement_produces_no_row_but_is_still_counted():
    result = run(agreeing())
    assert result.findings == ()
    assert result.warrants == ()
    assert result.run.account.n_checked == 1
    assert len(result.comparisons) == 1


def test_an_undocumented_control_is_a_warrant_and_never_a_finding():
    subject = Subject(
        binding=binding(),
        documented=None,
        observed=observation(gas_test_cat("10"), err_bar=HISTORIAN_BAR),
    )
    result = run(subject)
    assert result.findings == ()
    assert len(result.warrants) == 1
    assert result.warrants[0].warrant_class == "A2"


def test_an_absence_opens_an_a6_warrant_and_an_advisory_finding():
    subject = Subject(binding=binding(), documented=gas_test_cat("10"), observed=None)
    result = run(subject)
    assert len(result.warrants) == 1
    assert result.warrants[0].warrant_class == "A6"
    assert len(result.findings) == 1
    assert result.findings[0].undetermined
    assert not result.findings[0].would_block
    assert result.blocking_proposals == ()
    assert "MI05" in result.warrants[0].detail["note"]


def test_a_bounded_negative_opens_no_warrant():
    subject = Subject(
        binding=binding(),
        documented=gas_test_cat("10"),
        observed=observation(gas_test_cat("10.5"), err_bar=HISTORIAN_BAR),
    )
    result = run(subject)
    assert result.warrants == ()
    assert len(result.findings) == 1
    assert result.findings[0].undetermined
    assert result.comparisons[binding().clause_uuid].bounded_negative is not None


def test_the_run_row_is_written_before_the_findings_that_reference_it():
    result = run(drifting())
    assert "INSERT INTO mainline.patrol_run" in result.statements[0].sql
    assert "INSERT INTO mainline.drift_finding" in result.statements[1].sql


def test_warrants_are_written_after_findings():
    result = run(drifting())
    assert "discordance_warrant" in result.statements[-1].sql


def test_a_blocking_proposal_is_only_ever_a_proposal():
    result = run(drifting())
    assert len(result.blocking_proposals) == 1
    severity_index, gate_index = 10, 11
    finding_statement = result.statements[1]
    assert finding_statement.params[severity_index] == 5
    assert finding_statement.params[gate_index] == "blocking"


def test_redelivery_of_the_same_occurrence_produces_the_same_ids():
    first, second = run(drifting()), run(drifting())
    assert first.run.run_id == second.run.run_id
    assert [f.finding_id for f in first.findings] == [f.finding_id for f in second.findings]
    assert [w.warrant_id for w in first.warrants] == [w.warrant_id for w in second.warrants]


def test_an_unbalanced_account_refuses_to_become_a_run():
    from mainline_fixity import PatrolAccount

    with pytest.raises(PatrolAccountUnbalanced, match="unstated denominator"):
        PatrolRun(
            run_id=uuid.uuid5(uuid.NAMESPACE_OID, "bad-run"),
            scope=scope(),
            account=PatrolAccount(n_in_scope=10, n_checked=3, n_not_checked=3),
            as_of_hlc=AS_OF_HLC,
            started_at=STARTED,
            finished_at=FINISHED,
        )


def test_a_run_whose_clock_disagrees_with_itself_refuses():
    from mainline_fixity import PatrolAccount

    with pytest.raises(UnstartedPatrol):
        PatrolRun(
            run_id=uuid.uuid5(uuid.NAMESPACE_OID, "backwards-run"),
            scope=scope(),
            account=PatrolAccount(n_in_scope=0, n_checked=0, n_not_checked=0),
            as_of_hlc=AS_OF_HLC,
            started_at=FINISHED,
            finished_at=STARTED,
        )


def test_a_run_without_a_follower_read_timestamp_refuses():
    from mainline_fixity import PatrolAccount

    with pytest.raises(ValueError, match="cannot say when it looked"):
        PatrolRun(
            run_id=uuid.uuid5(uuid.NAMESPACE_OID, "timeless-run"),
            scope=scope(),
            account=PatrolAccount(n_in_scope=0, n_checked=0, n_not_checked=0),
            as_of_hlc=Decimal(0),
            started_at=STARTED,
            finished_at=FINISHED,
        )


def test_the_run_records_the_scope_predicate_it_was_given():
    result = run(drifting())
    assert result.statements[0].params[5] == scope().scope_pred


def test_an_in_flight_run_is_unrepresentable():
    # `agent_patroller` holds INSERT on patrol_run and no UPDATE, so `finished_at`
    # is mandatory: a crashed patrol writes no row, the occurrence is not marked
    # done, and at-least-once redelivery re-runs it.
    fields = {f.name for f in dataclasses.fields(PatrolRun)}
    assert "finished_at" in fields
    assert all(
        f.default is dataclasses.MISSING
        for f in dataclasses.fields(PatrolRun)
        if f.name == "finished_at"
    )
