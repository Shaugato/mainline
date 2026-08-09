# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Fixtures for the injection corpus: paths, extractors, and the two optional lanes.

Two lanes are optional and **neither is faked**. When ``mainline_domain.anchors``
imports, layer 4's integration lane runs against ANCHORLOCK itself; when it does not, the
lane skips with the import error in the skip reason and the committed-gazetteer fallback
carries the corpus. Same for ``mainline_agentkit``: the schema-drift alarm runs when it
imports and skips, loudly, when it does not.

The corpus itself is loaded by :mod:`corpus_loader`, which also puts the workspace source
directories on ``sys.path`` - see that module for why it is not this file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from corpus_loader import CORPUS_DIR, FIXTURES_DIR, REPO_ROOT


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def corpus_dir() -> Path:
    """The corpus directory."""
    return CORPUS_DIR


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """The fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def gazetteer_path() -> Path:
    """The committed fallback gazetteer."""
    return FIXTURES_DIR / "gazetteer.json"


@pytest.fixture(scope="session")
def extraction_schema() -> dict[str, Any]:
    """The committed wire schema layer-3 cases are contained by."""
    document = json.loads((FIXTURES_DIR / "extraction.schema.json").read_text(encoding="utf-8"))
    schema: dict[str, Any] = document["schema"]
    return schema


@pytest.fixture(scope="session")
def fallback_extractor(gazetteer_path: Path):
    """The committed-gazetteer anchor extractor. Always available."""
    from mainline_quarantine.gazetteer import GazetteerAnchorExtractor

    return GazetteerAnchorExtractor.from_path(gazetteer_path)


@pytest.fixture(scope="session")
def domain_anchor_extractor():
    """ANCHORLOCK itself, or a skip that names the import failure."""
    from mainline_quarantine.anchoring import domain_extractor
    from mainline_quarantine.errors import AnchorExtractorUnavailable

    try:
        return domain_extractor()
    except AnchorExtractorUnavailable as exc:
        pytest.skip(f"layer-4 integration lane unavailable: {exc}")


@pytest.fixture(scope="session")
def screen():
    """The offline prompt-attack screen."""
    from mainline_quarantine.screen import LocalPromptAttackScreen

    return LocalPromptAttackScreen()


@pytest.fixture(scope="session")
def fleet_register():
    """The fleet register: the real one, the boundary domain's reference, or a skip.

    ``spec/agents/fleet.yaml`` is the ``agent-contracts-red`` worker's file. Until it
    lands, ``packages/mainline-boundary/tests/fixtures/fleet_reference.yaml`` is a
    transcription of ARCHITECTURE.md 8.4 that the boundary domain committed for exactly
    this reason. Both are READ here and neither is written.
    """
    from mainline_quarantine.capability import FleetRegister

    candidates = (
        REPO_ROOT / "spec/agents/fleet.yaml",
        REPO_ROOT / "packages/mainline-boundary/tests/fixtures/fleet_reference.yaml",
    )
    for candidate in candidates:
        if candidate.is_file():
            return FleetRegister.from_yaml_path(candidate)
    pytest.skip(
        "no fleet register found; looked for "
        + ", ".join(str(path.relative_to(REPO_ROOT).as_posix()) for path in candidates)
    )
