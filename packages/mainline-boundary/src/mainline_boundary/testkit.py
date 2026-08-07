# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Assertion helpers for boundary suites.

:func:`assert_enforced` is the piece that matters, and it has **three** outcomes
rather than two:

* violations                          → **fail**, with every finding printed;
* nothing examined, reasons recorded  → **skip**, quoting the reasons;
* nothing examined, no reason         → **fail**, because a check that examined
  nothing and cannot say why is not a passing check.

A green tick from a suite built on this helper therefore always means "something
was inspected and found clean". That is the whole difference between an
enforcement and a comment, and it is the reason this lives in the package rather
than in one repository's ``conftest.py``: anyone asserting the same property of
their own kernel gets the same three outcomes.

``pytest`` is imported lazily so the package stays importable — and every
plan-time enforcement stays runnable from the CLI — in an environment that has no
test framework installed.
"""

from __future__ import annotations

from typing import Any

from .findings import Report


def assert_enforced(report: Report, *, minimum_examined: int = 1) -> None:
    """Fail on violations; skip (loudly) on a stated reason; fail on vacuity."""
    import pytest

    if report.violations:
        pytest.fail(report.summary(), pytrace=False)
    if report.examined < minimum_examined:
        if report.skips:
            reasons = "\n".join(f"  {s}" for s in report.skips)
            pytest.skip(
                f"{report.enforcement} examined {report.examined} subject(s) "
                f"(needed {minimum_examined}). NOT A PASS:\n{reasons}"
            )
        pytest.fail(
            f"{report.enforcement} examined {report.examined} subject(s) and recorded no "
            "reason. A check with an empty subject set asserts nothing; treat this as a "
            "broken check, not a clean result.\n" + report.summary(),
            pytrace=False,
        )


def assert_violates(report: Report, *rules: str) -> None:
    """Assert a deliberately-broken input produced (at least) the named rule ids.

    PL-2 in one call. A refusal nobody has watched refuse is not evidence, so
    every positive assertion in these suites is paired with a mutation that must
    trip a named rule — not merely "something failed".
    """
    import pytest

    violated = report.rules_violated()
    missing = [r for r in rules if r not in violated]
    if missing:
        pytest.fail(
            f"expected {report.enforcement} to violate {list(rules)} but it did not "
            f"report {missing}. Observed: {sorted(violated)}\n{report.summary()}",
            pytrace=False,
        )


def resource_of(document: dict[str, Any], address: str) -> dict[str, Any]:
    """The ``planned_values`` entry for ``address``, for in-memory mutation."""
    for entry in document["planned_values"]["root_module"]["resources"]:
        if entry["address"] == address:
            assert isinstance(entry, dict)
            return entry
    raise KeyError(f"{address} is not in the plan fixture")


def configuration_of(document: dict[str, Any], address: str) -> dict[str, Any]:
    """The ``configuration`` entry for ``address``, for in-memory mutation.

    Most interesting mutations live here rather than in ``planned_values``,
    because at plan time the security-relevant links are references, not values.
    """
    for entry in document["configuration"]["root_module"]["resources"]:
        if entry["address"] == address:
            assert isinstance(entry, dict)
            return entry
    raise KeyError(f"{address} is not in the plan fixture configuration")
