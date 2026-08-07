# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the calibration lane.

``calibration_dataset`` holds the resolution rule and is imported by name; pytest's prepend
import mode already puts this directory on ``sys.path``, and the module puts it there
explicitly too so the lane runs under importlib import mode and from a bare checkout.

The lane never skips. A reliability diagram that can be skipped because a corpus is missing
is not a lane, so the committed synthetic set is the floor and every artefact it produces is
stamped with what it is worth.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from calibration_dataset import (  # noqa: E402
    ARTEFACTS,
    CalibrationSet,
    ensure_import_paths,
    load_calibration_set,
)

ensure_import_paths()

__all__ = ["ARTEFACTS"]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "artefact: emits a committed evaluation artefact. The file's shape is the contract; "
        "its numbers carry the corpus label that produced them.",
    )


@pytest.fixture(scope="session")
def calibration_set() -> CalibrationSet:
    return load_calibration_set()


@pytest.fixture(scope="session")
def artefacts_dir() -> Path:
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    return ARTEFACTS
