# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Wiring for the recall run-loop suite.

One fixture builds the recorded cluster, one builds the orchestrator over it, and one runs
the loop. Nothing here is shared mutable state across tests: every fixture is function-scoped
because half of this suite works by injecting a failure and asserting what survived it, and a
session-scoped cluster would carry one test's injection into the next.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from _run_corpus import (
    ACTIVITY_SCOPE_ID,
    CORPUS_COMMIT,
    CORPUS_ROOT,
    INDEX_GENERATION,
    PERMIT_CONTROL_CLASSES,
    PERMIT_ID,
    PLAN_DIGEST,
    POLICY_VERSION,
    SITE_ID,
    clause_control_classes,
)
from _run_fakes import (
    FakeCluster,
    FakeKernelTransport,
    FixtureArmRunner,
    FixtureLexicalRunner,
    FixtureReranker,
    arm_outcome,
    lexical_hits,
    verdicts,
)
from mainline_recall_agent.run.kernel import MaterialiseClient
from mainline_recall_agent.run.orchestrator import RecallOrchestrator, RunOutcome, RunRequest
from trappoint_recall.run.contract import ExposureCueRef

KERNEL_BASE_URL = "https://kernel.mainline.invalid"

EXPOSURE_CUES: tuple[ExposureCueRef, ...] = (
    ExposureCueRef(
        facet="mechanism",
        cue_sha256="11" * 32,
        template_sha256="ff" * 32,
        gen_model="au.anthropic.claude-sonnet-5",
        prompt_version="recall.cue/1",
        embed_model="BAAI/bge-large-en-v1.5@fixture",
    ),
    ExposureCueRef(
        facet="precondition",
        cue_sha256="12" * 32,
        template_sha256="ff" * 32,
        gen_model="au.anthropic.claude-sonnet-5",
        prompt_version="recall.cue/1",
        embed_model="BAAI/bge-large-en-v1.5@fixture",
    ),
    ExposureCueRef(
        facet="recurrence_test",
        cue_sha256="13" * 32,
        template_sha256="ff" * 32,
        gen_model="au.anthropic.claude-sonnet-5",
        prompt_version="recall.cue/1",
        embed_model="BAAI/bge-large-en-v1.5@fixture",
        insufficient_evidence=True,
    ),
)


@dataclass
class Harness:
    """Everything one run needs, plus the recorders the assertions read."""

    cluster: FakeCluster
    transport: FakeKernelTransport
    orchestrator: RecallOrchestrator
    request: RunRequest
    reranker: Any

    def run(self) -> RunOutcome:
        """Execute the run loop once."""
        return self.orchestrator.run(self.request)


def _request() -> RunRequest:
    return RunRequest(
        permit_id=PERMIT_ID,
        site_id=SITE_ID,
        activity_scope_id=ACTIVITY_SCOPE_ID,
        policy_version=POLICY_VERSION,
        corpus_commit=CORPUS_COMMIT,
        corpus_root=CORPUS_ROOT,
        index_generation=INDEX_GENERATION,
        exposure_cues=EXPOSURE_CUES,
        clause_control_classes=clause_control_classes(),
        permit_control_classes=PERMIT_CONTROL_CLASSES,
    )


@pytest.fixture
def request_fixture() -> RunRequest:
    """A fresh :class:`RunRequest` with a fresh ``run_id``."""
    return _request()


@pytest.fixture
def cluster() -> FakeCluster:
    """A clean recorded cluster."""
    return FakeCluster()


@pytest.fixture
def build_harness() -> Callable[..., Harness]:
    """Build a harness, overriding any collaborator an injection test needs to replace."""

    def _build(
        *,
        cluster: FakeCluster | None = None,
        arm_runner: Any | None = None,
        lexical_runner: Any | None = None,
        reranker: Any | None = "default",
        transport: FakeKernelTransport | None = None,
        with_kernel: bool = True,
        request: RunRequest | None = None,
    ) -> Harness:
        cluster = cluster if cluster is not None else FakeCluster()
        transport = transport if transport is not None else FakeKernelTransport()
        run_request = request if request is not None else _request()

        arms = (
            arm_runner
            if arm_runner is not None
            else FixtureArmRunner(
                arm_outcome(index_generation=INDEX_GENERATION, plan_digest=PLAN_DIGEST)
            )
        )
        lexical = (
            lexical_runner
            if lexical_runner is not None
            else FixtureLexicalRunner(hits=lexical_hits())
        )
        judge = FixtureReranker(table=verdicts()) if reranker == "default" else reranker

        kernel = (
            MaterialiseClient(base_url=KERNEL_BASE_URL, transport=transport)
            if with_kernel
            else None
        )
        orchestrator = RecallOrchestrator(
            session=cluster.session(),
            writer=cluster,
            arm_runner_factory=lambda _request: arms,
            lexical_runner_factory=lambda _request: lexical,
            reranker_factory=(None if judge is None else (lambda _request: judge)),
            kernel=kernel,
        )
        return Harness(
            cluster=cluster,
            transport=transport,
            orchestrator=orchestrator,
            request=run_request,
            reranker=judge,
        )

    return _build


@pytest.fixture
def harness(build_harness: Callable[..., Harness]) -> Harness:
    """The clean-path harness: every channel available, the kernel answering 200."""
    return build_harness()


@pytest.fixture
def clean_outcome(harness: Harness) -> RunOutcome:
    """One completed clean run, for the tests that only inspect its artefacts."""
    return harness.run()
