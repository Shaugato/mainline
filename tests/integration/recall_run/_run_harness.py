# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The harness a run test holds, and the builder that wires one.

This lives beside ``conftest.py`` rather than inside it for one mechanical reason. Under
pytest's ``prepend`` import mode, a ``conftest.py`` in a directory that is not a package is
imported under the bare module name ``conftest``; this repository has more than one such
directory, so a test module that says ``from conftest import ...`` resolves against whichever
``conftest`` happened to be imported first. That is invocation-order dependent — it passes on
``pytest tests/`` and fails on ``pytest tests/integration/recall_run tests/concurrency/recall``
— and an import that depends on the order of the command line is a defect waiting for a
Tuesday.

Every symbol a test module needs by name therefore lives in a uniquely-named module and
``conftest.py`` keeps only fixtures, which pytest resolves by its own machinery rather than by
``import``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

__all__ = [
    "EXPOSURE_CUES",
    "KERNEL_BASE_URL",
    "Harness",
    "build_harness",
    "run_request",
]

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


def run_request() -> RunRequest:
    """A fresh :class:`RunRequest` over the fixture corpus, with a fresh ``run_id``."""
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


def build_harness(
    *,
    cluster: FakeCluster | None = None,
    arm_runner: Any | None = None,
    lexical_runner: Any | None = None,
    reranker: Any | None = "default",
    transport: FakeKernelTransport | None = None,
    with_kernel: bool = True,
    request: RunRequest | None = None,
) -> Harness:
    """Build a harness, overriding any collaborator an injection test needs to replace."""
    cluster = cluster if cluster is not None else FakeCluster()
    transport = transport if transport is not None else FakeKernelTransport()
    resolved_request = request if request is not None else run_request()

    arms = (
        arm_runner
        if arm_runner is not None
        else FixtureArmRunner(
            arm_outcome(index_generation=INDEX_GENERATION, plan_digest=PLAN_DIGEST)
        )
    )
    lexical = (
        lexical_runner if lexical_runner is not None else FixtureLexicalRunner(hits=lexical_hits())
    )
    judge = FixtureReranker(table=verdicts()) if reranker == "default" else reranker

    kernel = (
        MaterialiseClient(base_url=KERNEL_BASE_URL, transport=transport) if with_kernel else None
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
        request=resolved_request,
        reranker=judge,
    )
