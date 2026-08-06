# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the recall evaluation suite, and the ``g4alpha`` marker.

The corpus resolution rule lives in :mod:`corpus_resolution` because the CI lane runner
(``g4alpha_lane.py``) needs the same answer and a second copy of the rule is how a lane
ends up naming a corpus other than the one it measured.

The fallback is never a skip. A release gate that can be skipped because a corpus is
missing is not a release gate, and the suite must be able to be red on day one. The
report stamps which corpus produced the numbers, and the self-test corpus stamps itself
SYNTHETIC and PRELIMINARY so a passing run on it is never mistaken for a G4-alpha
measurement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ``oracles.py``, ``corpus_resolution.py`` and ``g4alpha_lane.py`` sit beside this file
# and are imported by name. pytest's prepend import mode already puts this directory on
# sys.path; doing it explicitly first means the import below works under importlib import
# mode too, without a package skeleton in tests/.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from corpus_resolution import (  # noqa: E402
    GS0_CORPUS,
    SELFTEST_CORPUS,
    ensure_import_paths,
    resolve_corpus_path,
)

# The uv workspace installs trappoint-recall in editable mode; this makes the suite
# runnable from a bare checkout too, so "the gate suite would not import" can never be
# the reason a lane reports green.
ensure_import_paths()

from trappoint_recall.eval.corpus import EvalCorpus, load_corpus  # noqa: E402

__all__ = ["GS0_CORPUS", "SELFTEST_CORPUS", "resolve_corpus_path"]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "g4alpha: the five G4-alpha release gates. Required to be RED before green; "
        "this lane records red/green and never skips.",
    )


@pytest.fixture(scope="session")
def corpus_path() -> Path:
    return resolve_corpus_path()


@pytest.fixture(scope="session")
def corpus(corpus_path: Path) -> EvalCorpus:
    return load_corpus(corpus_path)
