# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the corpora invariant suite.

Everything is session-scoped because the gold sets are on disk and reading them four
hundred times would make the suite slow enough that somebody starts skipping it.

Paths live in :mod:`corpora_paths` rather than here, so that the test module can import
them without importing ``conftest`` — two suites both importing a module called
``conftest`` resolve to whichever was imported first.

Nothing in this suite skips. A missing gold set is a missing gold set, and an invariant
about time-wall leakage that quietly did not run is worse than one that failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from corpora_paths import FIXTURES, GS0, PANEL, ensure_import_paths  # noqa: E402

ensure_import_paths()

from trappoint_recall.corpora.build import SYNTHETIC_PROVENANCE, load_inputs  # noqa: E402
from trappoint_recall.corpora.model import EventRecordSet  # noqa: E402
from trappoint_recall.corpora.panel import Panel, load_panel  # noqa: E402
from trappoint_recall.corpora.provenance import (  # noqa: E402
    ProvenanceManifest,
    load_provenance_manifest,
)
from trappoint_recall.eval.corpus import EvalCorpus, load_corpus  # noqa: E402


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    if not FIXTURES.is_dir():
        pytest.fail(
            f"{FIXTURES} does not exist. Run "
            "`python scripts/recall/build_goldsets.py --regenerate-fixtures` then "
            "`--from-fixtures`."
        )
    return FIXTURES


@pytest.fixture(scope="session")
def records(fixtures_root: Path) -> EventRecordSet:
    """The corpus, loaded through the real loaders from the committed fixtures."""
    return load_inputs(fixtures_root, provenance=SYNTHETIC_PROVENANCE)


@pytest.fixture(scope="session")
def manifest(fixtures_root: Path) -> ProvenanceManifest:
    return load_provenance_manifest(fixtures_root / "provenance.json")


@pytest.fixture(scope="session")
def panel() -> Panel:
    if not PANEL.is_file():
        pytest.fail(
            f"{PANEL} is not built. Run `python scripts/recall/build_goldsets.py --from-fixtures`."
        )
    return load_panel(PANEL)


@pytest.fixture(scope="session")
def gs0() -> EvalCorpus:
    if not (GS0 / "queries.jsonl").is_file():
        pytest.fail(
            f"{GS0} is not built. Run `python scripts/recall/build_goldsets.py --from-fixtures`."
        )
    return load_corpus(GS0)
