# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fixtures for the taxonomy suite, and the offline guarantee it depends on.

Everything here runs with **no AWS account, no CockroachDB and no network**.  That is not a
convenience: the induction pipeline's whole claim is that it can be red-greened on a laptop,
and a suite that quietly acquired a boto3 session, timed out, and fell back to something
plausible would go green while the claim died.  So the guarantee is enforced by blocking
outbound connection establishment, exactly as ``tests/unit/recall_providers`` does.

The expensive fixtures — two full induction runs over the 1 000-document fixture corpus —
are session-scoped.  They are the same objects several test modules assert different things
about, and running the pipeline once per assertion would make the suite slow enough that
someone would eventually mark it.
"""

from __future__ import annotations

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-recall-agent" / "src"
EVAL_SRC = REPO_ROOT / "packages" / "trappoint-recall" / "src"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "recall_taxonomy"
MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

# Work whether or not the uv workspace has been synced: an editable install wins, and a bare
# checkout still runs, so "the suite would not import" can never be why a lane reports green.
for candidate in (PACKAGE_SRC, EVAL_SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from mainline_recall_agent.taxonomy import (  # noqa: E402
    InductionConfig,
    InductionDocument,
    InductionRun,
    Level1Register,
    RuleBasedInductionJudge,
    load_level1_register,
    run_induction,
)

SITE_ID = "11111111-1111-4111-8111-111111111111"

#: The corpus is synthetic and every artefact built from it says so. Kept here as a constant
#: because three fixtures pass it through and a typo in one of them would produce a report
#: whose provenance string quietly stopped saying SYNTHETIC.
CORPUS_PROVENANCE = (
    "SYNTHETIC fixture corpus (tests/fixtures/recall_taxonomy/narratives.jsonl) — "
    "PRELIMINARY, measures the pipeline and not a model"
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: needs a live CockroachDB and the consumed migrations 0032/0033. "
        "Skips with a reason naming what is missing; never runs against a fixture table.",
    )


class NetworkAccessInTest(RuntimeError):
    """Raised when a test in this directory tries to open a socket."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise NetworkAccessInTest(
            "a test in tests/unit/recall_taxonomy attempted an outbound connection. This "
            "suite must pass with no credentials, no cluster and no network: the induction "
            "runs against the committed rule table and the committed corpus."
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse, raising=True)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse, raising=True)
    monkeypatch.setattr(socket, "create_connection", _refuse, raising=True)


def load_fixture_corpus(path: Path | None = None) -> list[InductionDocument]:
    """Read ``narratives.jsonl``: one meta line, then one document per line."""
    source = path or (FIXTURES / "narratives.jsonl")
    documents: list[InductionDocument] = []
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("kind") == "meta":
                continue
            documents.append(
                InductionDocument(
                    doc_id=record["doc_id"],
                    title=record["title"],
                    narrative=record["narrative"],
                    truth_activity_root=record["truth_activity_root"],
                    truth_series=record["truth_series"],
                    truth_file=record["truth_file"],
                )
            )
    return documents


def corpus_meta(path: Path | None = None) -> dict[str, Any]:
    source = path or (FIXTURES / "narratives.jsonl")
    with source.open(encoding="utf-8") as handle:
        record: dict[str, Any] = json.loads(handle.readline())
    return record


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def register() -> Level1Register:
    return load_level1_register(FIXTURES / "icmm_mue_l1.json")


@pytest.fixture(scope="session")
def judge() -> RuleBasedInductionJudge:
    return RuleBasedInductionJudge.from_json(FIXTURES / "offline_induction_rules.json")


@pytest.fixture(scope="session")
def corpus() -> list[InductionDocument]:
    return load_fixture_corpus()


@pytest.fixture(scope="session")
def induction(
    corpus: list[InductionDocument],
    register: Level1Register,
    judge: RuleBasedInductionJudge,
) -> InductionRun:
    """The reference run: the whole corpus, taxonomy version 1, no parent."""
    return run_induction(
        documents=corpus,
        register=register,
        judge=judge,
        site_id=SITE_ID,
        taxonomy_ver=1,
        corpus_provenance=CORPUS_PROVENANCE,
        induced_at=datetime(2026, 8, 4, 0, 0, tzinfo=UTC),
        notes="reference fixture run",
    )


@pytest.fixture(scope="session")
def induction_v2(
    corpus: list[InductionDocument],
    register: Level1Register,
    judge: RuleBasedInductionJudge,
    induction: InductionRun,
) -> InductionRun:
    """A second run over two thirds of the corpus, at a raised support floor.

    Deliberately *not* a rerun of the same configuration.  A diff between two identical runs
    is empty by construction and would prove only that the code is deterministic; the
    property under test is that a re-induction which genuinely moves labels is visible in
    the version record, because that is the change a later reader has to be able to
    attribute.
    """
    return run_induction(
        documents=corpus[: (len(corpus) * 2) // 3],
        register=register,
        judge=judge,
        site_id=SITE_ID,
        taxonomy_ver=2,
        parent=induction.snapshot,
        parent_assignments=induction.assignments,
        config=InductionConfig(min_support=12),
        corpus_provenance=CORPUS_PROVENANCE,
        induced_at=datetime(2026, 8, 5, 0, 0, tzinfo=UTC),
        notes="re-induction on a corpus slice at a raised support floor",
    )
