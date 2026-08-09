# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Run every case, one test each, and keep what they observed.

The command-line runner reports a suite. This module reports **cases**, one pytest node per
case id, which is what makes the corpus usable from an editor, from ``-k``, and from a CI
annotation that points at the one thing that broke.

It is also where the anomaly markers land. ``tests/conftest.py`` attaches
``@pytest.mark.anomaly(...)`` from the manifest at collection, so ``ANOMALY_COVERAGE.md`` is
generated from collected markers exactly as ``testing-invariants`` §2 asks, while the
anomaly mapping keeps one owner.

Three things are asserted per case, in an order chosen so the first failure is the most
informative one:

1. the outcome class — refused when the manifest says refused, completed when it says
   completed. A gate that admits what it must refuse is the only failure that matters more
   than a wrong exhibit;
2. the exact SQLSTATE;
3. the exact exhibit, which is the whole reason this suite is worth running.

``asserts_stored_row`` is checked separately, in :func:`test_stored_row_expectations`,
because *"the row was rewritten"* and *"the write was refused"* are two claims and a case
that conflated them would let either one hide the other's failure.
"""

from __future__ import annotations

import os

import pytest

from trappoint_conformance.manifest import Case, Manifest
from trappoint_conformance.runner import CaseResult, Status, resolve_schema

_SATISFIED = tuple(
    token for token in os.environ.get("TRAPPOINT_REQUIRES", "").split(",") if token.strip()
)


def _selected(manifest: Manifest, profile: str) -> tuple[Case, ...]:
    return manifest.for_profile(profile)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrise over the manifest's cases for the profile under test."""
    if "case_result" not in metafunc.fixturenames:
        return
    from trappoint_conformance.manifest import load_manifest

    profile = os.environ.get("TRAPPOINT_PROFILE", "trappoint-ref")
    ids = [case.id for case in _selected(load_manifest(), profile)]
    metafunc.parametrize("case_id", ids, ids=ids)


@pytest.fixture
def case_result(report, case_id: str) -> CaseResult:
    """The one result this test is about."""
    result = report.get(case_id)
    if result is None:
        pytest.fail(f"{case_id} was not run; the manifest selects it for this profile")
    if result.status is Status.SKIPPED:
        pytest.skip(f"SKIP WITH REASON: {result.detail}")
    if result.status is Status.PENDING:
        pytest.fail(
            f"{case_id} has no implementation. test_manifest_totality owns this failure "
            f"and explains it better; if that test is green and this one is not, the "
            f"corpus loader did not run."
        )
    return result


@pytest.mark.db
def test_case_outcome_class(case_result: CaseResult) -> None:
    """Refused when the manifest says refused; completed when it says completed."""
    observed = case_result.observed
    assert observed is not None, case_result.detail
    if case_result.case.cls == "admit":
        assert observed.completed, (
            f"{case_result.case.id} must COMPLETE — a gate that refuses everything is not "
            f"a gate — and it was refused with {observed.sqlstate} on "
            f"{observed.constraint or '<no exhibit>'}: {observed.message[:200]}"
        )
    else:
        assert not observed.completed, (
            f"{case_result.case.id}: the history COMPLETED. The gate admitted a write it "
            f"must refuse with {case_result.case.expect_sqlstate} on "
            f"{case_result.case.expect_constraint!r}."
        )


@pytest.mark.db
def test_case_sqlstate(case_result: CaseResult) -> None:
    """The exact code, and only that code."""
    observed = case_result.observed
    assert observed is not None, case_result.detail
    assert observed.sqlstate == case_result.case.expect_sqlstate, (
        f"{case_result.case.id}: expected {case_result.case.expect_sqlstate}, observed "
        f"{observed.sqlstate}: {observed.message[:200]}"
    )


@pytest.mark.db
def test_case_exhibit(case_result: CaseResult, conn, profile: str) -> None:
    """The exact exhibit. This is the assertion the whole suite exists for."""
    observed = case_result.observed
    assert observed is not None, case_result.detail
    if case_result.case.cls == "admit":
        # An admitted history has no driver-reported constraint, because nothing refused.
        # `spec/errors.md` §3.1 defines the exhibit for `00000` as *the SQL object that had
        # to permit the write*, so the assertion is that the object EXISTS — a legal
        # history that completes because the mechanism was never installed is not the same
        # claim as one that completes because the mechanism permitted it.
        assert not observed.constraint, (
            f"{case_result.case.id} completed and still reported an exhibit "
            f"({observed.constraint!r}); nothing refused, so nothing can have named itself."
        )
        found, how = _object_exists(conn, profile, case_result.case.expect_constraint)
        assert found, (
            f"{case_result.case.id} is an `admit` case whose exhibit is "
            f"{case_result.case.expect_constraint!r} — the object that had to permit the "
            f"write — and no such {how} exists on this cluster. A history that completes "
            f"because the mechanism is absent is not the same claim as one that completes "
            f"because the mechanism permitted it."
        )
        return
    assert observed.constraint == case_result.case.expect_constraint, (
        f"{case_result.case.id}: {observed.sqlstate} was raised, but by "
        f"{observed.constraint or '<no exhibit>'}, not by "
        f"{case_result.case.expect_constraint!r}. The right code from the wrong mechanism "
        f"reads as a pass to anyone not looking closely, which is exactly what naming the "
        f"exhibit exists to catch."
    )


@pytest.mark.db
def test_stored_row_expectations(case_result: CaseResult) -> None:
    """Where the manifest declares ``asserts_stored_row``, the case recorded evidence.

    The *content* of the evidence is asserted inside the case itself — it is
    case-specific, and a generic assertion here would be a second, weaker copy of it. What
    this test adds is that the evidence **exists**: a case that quietly stopped reading the
    row back would still pass its refusal assertions, and ``CF-07`` without its stored row
    is a case that no longer tests the claim the company is built on.
    """
    if not case_result.case.asserts_stored_row:
        pytest.skip("SKIP WITH REASON: this case declares no stored-row expectation")
    observed = case_result.observed
    assert observed is not None, case_result.detail
    assert observed.stored, (
        f"{case_result.case.id} declares asserts_stored_row "
        f"({case_result.case.asserts_stored_row!r}) and recorded nothing. The rewrite is "
        f"the claim; the refusal is only the consequence."
    )


@pytest.mark.db
def test_cf07_is_the_first_case_green(report) -> None:
    """CF-07 is not one case among seventy-one.

    It is the only test of the claim the company is built on: that ``severity`` and
    ``virulence`` are projections of the blame closure rather than inputs, and that the
    clearance lattice therefore judges what the ancestry says rather than what the writer
    said about itself. If it is red, nothing else being green is interesting.
    """
    result = report.get("CF-07")
    if result is None or result.status is Status.SKIPPED:
        pytest.skip("SKIP WITH REASON: CF-07 is not selected for this profile")
    assert result.status is Status.PASSED, (
        f"CF-07 is RED: {result.detail}\n\nThis is the case that must be green before any "
        f"other result is worth reading."
    )
    observed = result.observed
    assert observed is not None
    assert observed.stored.get("blocking_check") == [(5, "blood_fatal")], (
        f"CF-07 passed its refusal assertion but the stored row reads "
        f"{observed.stored.get('blocking_check')!r} rather than [(5, 'blood_fatal')]. The "
        f"23503 alone would pass against an implementation that trusted the inserter."
    )


def _object_exists(conn, profile: str, exhibit: str) -> tuple[bool, str]:
    """Resolve an ``admit``-class exhibit in the catalogue.

    Three shapes appear in the manifest and each is looked up as itself rather than by a
    single fuzzy search: a **constraint or unique index** (``blocking_check_dedupe_key_key``),
    a **column** (``mainline.permit_event.chain_digest``), and a **policy** (``gate_write``).
    A lookup that matched any of the three would report success for an object of the wrong
    kind, which is the failure this assertion exists to catch.
    """

    schema = resolve_schema(profile)
    local = exhibit.split(".")
    with conn.cursor() as cur:
        if len(local) == 3:
            cur.execute(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
                (schema, local[1], local[2]),
            )
            return bool(cur.fetchone()[0]), f"column {local[1]}.{local[2]}"
        name = local[-1]
        cur.execute(
            "SELECT count(*) FROM information_schema.table_constraints "
            "WHERE constraint_schema = %s AND constraint_name = %s",
            (schema, name),
        )
        if cur.fetchone()[0]:
            return True, "constraint"
        cur.execute(
            "SELECT count(*) FROM pg_indexes WHERE schemaname = %s AND indexname = %s",
            (schema, name),
        )
        if cur.fetchone()[0]:
            return True, "index"
        cur.execute(
            "SELECT count(*) FROM pg_policies WHERE schemaname = %s AND policyname = %s",
            (schema, name),
        )
        if cur.fetchone()[0]:
            return True, "policy"
        return False, "constraint, index or policy"
