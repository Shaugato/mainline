# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Wiring for the recall run-loop suite.

One fixture builds the recorded cluster, one builds the orchestrator over it, and one runs
the loop. Nothing here is shared mutable state across tests: every fixture is function-scoped
because half of this suite works by injecting a failure and asserting what survived it, and a
session-scoped cluster would carry one test's injection into the next.

The harness itself lives in :mod:`_run_harness`, not here. A ``conftest.py`` in a non-package
directory is imported under the bare name ``conftest``, and this repository has several — so a
test module importing a symbol *from* ``conftest`` binds to whichever one pytest loaded first.
Fixtures are safe (pytest resolves those per-directory); named imports are not.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from _run_fakes import FakeCluster
from _run_harness import Harness, build_harness, run_request
from mainline_recall_agent.run.orchestrator import RunOutcome, RunRequest


@pytest.fixture
def request_fixture() -> RunRequest:
    """A fresh :class:`RunRequest` with a fresh ``run_id``."""
    return run_request()


@pytest.fixture
def cluster() -> FakeCluster:
    """A clean recorded cluster."""
    return FakeCluster()


@pytest.fixture(name="build_harness")
def build_harness_fixture() -> Callable[..., Harness]:
    """Expose :func:`_run_harness.build_harness` as a fixture."""
    return build_harness


@pytest.fixture
def harness(build_harness: Callable[..., Harness]) -> Harness:
    """The clean-path harness: every channel available, the kernel answering 200."""
    return build_harness()


@pytest.fixture
def clean_outcome(harness: Harness) -> RunOutcome:
    """One completed clean run, for the tests that only inspect its artefacts."""
    return harness.run()
