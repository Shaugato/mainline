# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Make the judge pack importable, exactly the way a judge running the CLI does.

The pack deliberately is not an installed distribution: a stranger clones the repository
and runs `python verticals/mainline/demo/judge/cli.py validate` with nothing but PyYAML in
the environment. These tests import it the same way — by putting the demo directory on the
path — so what CI exercises is the artefact the judge actually runs, not a packaged
lookalike.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
DEMO_DIR = REPO_ROOT / "verticals" / "mainline" / "demo"
JUDGE_DIR = DEMO_DIR / "judge"

if str(DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(DEMO_DIR))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def judge_dir() -> Path:
    return JUDGE_DIR


@pytest.fixture(scope="session")
def pack_path() -> Path:
    return JUDGE_DIR / "QUESTIONS.yaml"


@pytest.fixture(scope="session")
def pack(pack_path: Path):
    from judge.pack import load_pack

    return load_pack(pack_path)
