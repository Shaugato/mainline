# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixtures and the one assertion helper the whole boundary suite is built on.

:func:`assert_enforced` is the piece that matters. It has three outcomes, not
two, and the third is why it exists:

* violations       → **fail**, with every finding printed;
* nothing examined, reasons recorded → **skip**, quoting the reasons;
* nothing examined, no reason        → **fail**, because a check that examined
  nothing and cannot say why is not a passing check.

A green tick from this suite therefore always means "something was inspected and
found clean". That is the whole difference between an enforcement and a comment.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parent.parent.parent

# The boundary package is a workspace member. When the workspace has not been
# installed (a bare checkout, or a reviewer running one file), fall back to the
# source tree so the suite still runs — the enforcements must never be
# unrunnable for a packaging reason.
_SRC = _REPO_ROOT / "packages" / "mainline-boundary" / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mainline_boundary.planfacts import PlanFacts

PLAN_FIXTURE = _REPO_ROOT / "tests" / "boundary" / "fixtures" / "plan.json"
POLICY_DIR = _REPO_ROOT / "tests" / "boundary" / "policy"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _REPO_ROOT


@pytest.fixture(scope="session")
def plan_path() -> Path:
    if not PLAN_FIXTURE.is_file():
        pytest.fail(
            f"the committed plan fixture is missing at {PLAN_FIXTURE}. E1, E2 and E4 "
            "read it; without it they assert nothing, and 'asserts nothing' must never "
            "be reported as green."
        )
    return PLAN_FIXTURE


@pytest.fixture(scope="session")
def plan_document(plan_path: Path) -> Mapping[str, Any]:
    return json.loads(plan_path.read_text(encoding="utf-8"))


@pytest.fixture
def plan_facts(plan_document: Mapping[str, Any]) -> PlanFacts:
    return PlanFacts.from_dict(plan_document)


@pytest.fixture
def mutate_plan(
    plan_document: Mapping[str, Any],
) -> Callable[[Callable[[dict[str, Any]], None]], PlanFacts]:
    """Deep-copy the fixture, apply a mutation, and return the resulting facts.

    PL-2 in one fixture. Every enforcement in this suite is paired with at least
    one mutation that must make it fail: a refusal that has never been observed
    refusing is not evidence of anything.
    """

    def _mutate(mutation: Callable[[dict[str, Any]], None]) -> PlanFacts:
        document = deepcopy(dict(plan_document))
        mutation(document)
        return PlanFacts.from_dict(document)

    return _mutate


@pytest.fixture(scope="session")
def policy_dir() -> Path:
    return POLICY_DIR


# The assertion helpers live in `mainline_boundary.testkit`, not here.
#
# Two reasons. A `conftest.py` is imported by pytest under a module name derived
# from its directory, so two of them in one run collide and the suites stop being
# runnable together — which would make it easy to run only the lane that passes.
# And `assert_enforced`'s three-outcome contract is the reusable part of this
# package: anyone asserting the same property of their own kernel should get the
# same "examined nothing is not a pass" behaviour without copying it.
#
# See: mainline_boundary.testkit.assert_enforced / assert_violates /
#      resource_of / configuration_of
