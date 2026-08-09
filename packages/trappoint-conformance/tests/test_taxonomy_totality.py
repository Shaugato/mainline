# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal taxonomy is total, and the manifest stays inside it.

``spec/errors.md`` §1.1: over the gate path the taxonomy is **total** over
``{40001, 23514, 23503, 23505, P0001}``. Any other SQLSTATE fails the suite — because it
means the database refused for a reason nobody modelled, and an unmodelled refusal is a
refusal nobody can explain to a regulator, a customer, or a court.

Two halves, and both are needed.

**Statically**, every code the manifest declares must be inside the class its case belongs
to. A manifest that expected ``23502`` would define a suite that passes when a ``NOT NULL``
projected column is left unset by a trigger, which is a defect wearing a green tick.

**Dynamically**, every code the suite *observes* is classified, and :func:`classify` raises
rather than returning an ``UNKNOWN`` member. An enum with a catch-all is a taxonomy that can
absorb anything, and absorbing anything is how a suite comes to pass against a database that
refused for a reason nobody thought of.
"""

from __future__ import annotations

import pytest

from trappoint_conformance.manifest import Manifest
from trappoint_conformance.sqlstate import (
    ADMIT_CODES,
    DENY_CODES,
    REFUSE_CODES,
    RETRY_CODES,
    Outcome,
    UnmodelledRefusal,
    classify,
)

CLASS_CODES = {
    "gate": REFUSE_CODES,
    "retry": RETRY_CODES,
    "deny": DENY_CODES,
    "admit": ADMIT_CODES,
}


def test_every_declared_sqlstate_is_inside_its_class(manifest: Manifest) -> None:
    """No case expects a code its own expectation class does not contain."""
    wrong = [
        f"{case.id}: class {case.cls!r} expects {case.expect_sqlstate}"
        for case in manifest.cases
        if case.expect_sqlstate not in CLASS_CODES.get(case.cls, frozenset())
    ]
    assert not wrong, (
        "These cases declare a SQLSTATE outside their own expectation class:\n  "
        + "\n  ".join(wrong)
        + "\n\nThe classes are the contract of spec/errors.md §1; a case that expects a "
        "code its class does not contain has defined a suite that passes on a defect."
    )


def test_every_declared_secondary_sqlstate_is_modelled(manifest: Manifest) -> None:
    """Secondary expectations obey the same taxonomy as primary ones."""
    modelled = REFUSE_CODES | RETRY_CODES | DENY_CODES | ADMIT_CODES
    wrong = [
        f"{case.id}: secondary {case.secondary_sqlstate}"
        for case in manifest.cases
        if case.secondary_sqlstate and case.secondary_sqlstate not in modelled
    ]
    assert not wrong, "\n  ".join(["Unmodelled secondary expectations:", *wrong])


def test_the_taxonomy_has_no_catch_all() -> None:
    """An unmodelled code raises. It does not classify."""
    with pytest.raises(UnmodelledRefusal):
        classify("23502")
    assert not hasattr(Outcome, "UNKNOWN"), (
        "Outcome grew a catch-all member. A taxonomy that can absorb anything is how a "
        "suite comes to pass against a database that refused for a reason nobody modelled."
    )


def test_the_four_classes_are_disjoint() -> None:
    """No code belongs to two classes."""
    seen: dict[str, str] = {}
    for name, codes in CLASS_CODES.items():
        for code in codes:
            assert code not in seen, (
                f"{code} is in both {seen[code]} and {name}. A code in two classes means "
                f"the runner's decision about what to assert depends on which branch it "
                f"reaches first."
            )
            seen[code] = name


@pytest.mark.db
def test_no_observed_sqlstate_falls_outside_the_taxonomy(observations) -> None:
    """Everything the suite actually saw is classified."""
    unmodelled: list[str] = []
    for case_id, sqlstate, message in observations:
        if sqlstate == "00000":
            continue
        try:
            classify(sqlstate)
        except UnmodelledRefusal as exc:
            unmodelled.append(f"{case_id}: {exc} :: {message[:120]}")
    assert not unmodelled, (
        "The database refused for reasons outside the modelled taxonomy:\n  "
        + "\n  ".join(unmodelled)
        + "\n\nThis is a defect, not an edge case. Each line is a refusal nobody can "
        "explain from the specification."
    )
