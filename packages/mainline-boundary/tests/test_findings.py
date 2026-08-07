# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The report type, whose only interesting property is that it cannot be vacuous quietly."""

from __future__ import annotations

import json

from mainline_boundary.findings import Enforcement, Report


def test_a_clean_report_that_examined_nothing_is_vacuous() -> None:
    report = Report(enforcement=Enforcement.E3_CODE)
    assert report.ok
    assert report.vacuous, "an empty violation list over an empty subject set is not a pass"


def test_examining_something_clears_vacuity() -> None:
    report = Report(enforcement=Enforcement.E3_CODE)
    report.examine(3)
    assert report.ok
    assert not report.vacuous


def test_violations_are_never_vacuous() -> None:
    report = Report(enforcement=Enforcement.E1_IAM)
    report.violate(rule="R", subject="s", detail="d")
    assert not report.ok
    assert not report.vacuous


def test_merge_preserves_the_enforcement_and_accumulates() -> None:
    a = Report(enforcement=Enforcement.E4_EGRESS)
    a.examine(2)
    a.note("first")
    b = Report(enforcement=Enforcement.GREP)
    b.examine(1)
    b.violate(rule="R", subject="s", detail="d")
    b.skip(rule="S", subject="t", reason="because")
    b.exempt(rule="X", subject="u", reason="declared")
    a.merge(b)
    assert a.enforcement == Enforcement.E4_EGRESS
    assert a.examined == 3
    assert len(a.violations) == 1
    assert len(a.skips) == 1
    assert len(a.exemptions) == 1
    assert a.notes == ["first"]


def test_json_round_trips_and_is_sorted() -> None:
    report = Report(enforcement=Enforcement.E2_NETWORK)
    report.examine()
    report.violate(rule="R", subject="s", detail="d", authority="§8.2")
    payload = json.loads(report.to_json())
    assert payload["enforcement"] == "E2"
    assert payload["violations"][0]["authority"] == "§8.2"
    assert payload["ok"] is False


def test_summary_shows_every_recorded_outcome() -> None:
    report = Report(enforcement=Enforcement.E1_IAM)
    report.violate(rule="V", subject="a", detail="broken")
    report.skip(rule="S", subject="b", reason="absent")
    report.exempt(rule="E", subject="c", reason="declared")
    report.note("context")
    text = report.summary()
    for fragment in ("broken", "SKIPPED", "EXEMPT", "context"):
        assert fragment in text


def test_lookup_helpers() -> None:
    report = Report(enforcement=Enforcement.FLEET)
    report.violate(rule="A", subject="x", detail="d")
    report.violate(rule="B", subject="y", detail="d")
    report.skip(rule="C", subject="packages/foo", reason="r")
    assert report.rules_violated() == frozenset({"A", "B"})
    assert len(report.violations_for("A")) == 1
    assert report.skips_for("foo")
    assert not report.skips_for("bar")
