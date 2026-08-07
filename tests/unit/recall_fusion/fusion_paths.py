# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Path resolution for the fusion suite, in a module with a unique name.

``conftest.py`` is the natural home for these constants, but every suite in the repository
has one and ``from conftest import ...`` binds to whichever was imported first when two
suites run in the same session. A uniquely-named module is imported by the file that needs
it, which is what makes the syntax scan in ``test_no_severity_multiplication.py`` able to
state which trees it walked.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

__all__ = [
    "CASSETTE_ROOT",
    "FUSION_PACKAGE",
    "REPO_ROOT",
    "RERANK_PACKAGE",
    "SUBSTRATE_SRC",
    "SUITE_DIR",
    "VERTICAL_SRC",
    "ensure_import_paths",
]

SUITE_DIR: Final[Path] = Path(__file__).resolve().parent
REPO_ROOT: Final[Path] = SUITE_DIR.parents[2]
SUBSTRATE_SRC: Final[Path] = REPO_ROOT / "packages" / "trappoint-recall" / "src"
VERTICAL_SRC: Final[Path] = (
    REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-recall-agent" / "src"
)
CASSETTE_ROOT: Final[Path] = SUITE_DIR / "cassettes"

FUSION_PACKAGE: Final[Path] = SUBSTRATE_SRC / "trappoint_recall" / "fusion"
RERANK_PACKAGE: Final[Path] = VERTICAL_SRC / "mainline_recall_agent" / "rerank"


def ensure_import_paths() -> None:
    """Put the suite directory and both package sources on ``sys.path``.

    Normally a no-op under the uv workspace. It exists so the suite also runs from a bare
    checkout, because the arithmetic that decides whether a fatality is raised must be
    checkable by anyone who clones the repository.
    """
    for entry in (SUITE_DIR, SUBSTRATE_SRC, VERTICAL_SRC):
        text = str(entry)
        if entry.is_dir() and text not in sys.path:
            sys.path.insert(0, text)
