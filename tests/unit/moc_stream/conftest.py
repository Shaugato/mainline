# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Fixtures for the MOC-stream suite (stage 1c of the corpus).

``mainline-corpus`` has no ``pyproject.toml`` yet — that file is ``corpus-contract``'s
deliverable — so the package is not an installed workspace member and cannot be imported by
name.  The path is inserted here, deliberately and visibly, rather than the suite skipping:
a stage whose reproducibility claim quietly did not run is worse than one that failed.

The stage is built ONCE per session into a temporary directory.  It is a pure, in-memory
rebuild of stages 1, 1b and 1c and takes a couple of seconds; doing it per test would make the
suite slow enough that somebody starts skipping it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parents[2]
_SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-corpus" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

FIXTURE_DIR = REPO_ROOT / "verticals" / "mainline" / "fixtures" / "corpus" / "moc-stream"
MIGRATIONS = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Every row of a JSONL file, in file order."""
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def migrations() -> Path:
    return MIGRATIONS


@pytest.fixture(scope="session")
def stream() -> Any:
    """The whole stage, built in memory, with every internal check already run."""
    from mainline_corpus.moc_stream.build import build_moc_stream

    return build_moc_stream(repo_root=REPO_ROOT)


@pytest.fixture(scope="session")
def regenerated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A freshly generated tree, written to a temporary directory."""
    from mainline_corpus.moc_stream.build import generate

    out = tmp_path_factory.mktemp("moc-stream-regen")
    generate(out, repo_root=REPO_ROOT)
    return out


@pytest.fixture(scope="session")
def regenerated_twice(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Two independently generated trees, for the byte-identity assertion."""
    from mainline_corpus.moc_stream.build import generate

    first = tmp_path_factory.mktemp("moc-stream-a")
    second = tmp_path_factory.mktemp("moc-stream-b")
    generate(first, repo_root=REPO_ROOT)
    generate(second, repo_root=REPO_ROOT)
    return first, second
