# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Where the committed corpora artefacts live, in one place both the fixtures and the
tests import.

Deliberately **not** ``conftest``. pytest's prepend import mode gives every rootless test
directory's ``conftest.py`` the module name ``conftest``, so two suites that both do
``from conftest import ...`` resolve to whichever one was imported first — which shows up
as an ``ImportError`` naming a completely unrelated suite. A uniquely-named module has no
such collision, which is why the recall harness suite next door uses
``corpus_resolution.py`` for the same reason.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

SUITE_DIR: Final[Path] = Path(__file__).resolve().parent
REPO_ROOT: Final[Path] = SUITE_DIR.parents[2]
PACKAGE_SRC: Final[Path] = REPO_ROOT / "packages" / "trappoint-recall" / "src"

FIXTURES: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "recall"
GOLDSETS: Final[Path] = FIXTURES / "goldsets"
GS0: Final[Path] = GOLDSETS / "gs0"
PANEL: Final[Path] = FIXTURES / "thymogate_panel.json"

QRELS_FILES: Final[tuple[Path, ...]] = (
    GOLDSETS / "g1_citations.qrels.jsonl",
    GOLDSETS / "g2_codes.qrels.jsonl",
    GOLDSETS / "g3_adjudicated.qrels.jsonl",
    GOLDSETS / "g4_retro.qrels.jsonl",
)

__all__ = [
    "FIXTURES",
    "GOLDSETS",
    "GS0",
    "PACKAGE_SRC",
    "PANEL",
    "QRELS_FILES",
    "REPO_ROOT",
    "SUITE_DIR",
    "ensure_import_paths",
]


def ensure_import_paths() -> None:
    """Put the package source on ``sys.path``.

    The uv workspace installs ``trappoint-recall`` editable, so this is normally a no-op.
    It exists so the suite also runs from a bare checkout: "the corpora suite would not
    import" must never be the reason a time-wall leakage assertion did not run.
    """
    for entry in (PACKAGE_SRC,):
        text = str(entry)
        if entry.is_dir() and text not in sys.path:
            sys.path.insert(0, text)
