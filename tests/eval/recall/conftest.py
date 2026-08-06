# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the recall evaluation suite, and the ``g4alpha`` marker.

Corpus resolution, in order:

1. ``$TRAPPOINT_RECALL_CORPUS`` — an explicit override for a lane pointed at a real set.
2. ``tests/fixtures/recall/gs0`` — GS0, once ``recall-corpora-goldsets`` lands it.
3. ``tests/eval/recall/fixtures/harness_selftest`` — the committed self-test corpus.

The fallback is never a skip. A release gate that can be skipped because a corpus is
missing is not a release gate, and the suite must be able to be red on day one. The
report stamps which corpus produced the numbers, and the self-test corpus stamps itself
SYNTHETIC and PRELIMINARY so a passing run on it is never mistaken for a G4-alpha
measurement.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[2]
_PACKAGE_SRC = _REPO_ROOT / "packages" / "trappoint-recall" / "src"

# ``oracles.py`` sits beside this file and is imported by name. pytest's prepend import
# mode already puts this directory on sys.path; doing it explicitly means the suite also
# runs under importlib import mode without a package skeleton in tests/.
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# The uv workspace installs trappoint-recall in editable mode; this makes the suite
# runnable from a bare checkout too, so "the gate suite would not import" can never be
# the reason a lane reports green.
if _PACKAGE_SRC.is_dir() and str(_PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_SRC))

from trappoint_recall.eval.corpus import EvalCorpus, load_corpus  # noqa: E402

SELFTEST_CORPUS = Path(__file__).resolve().parent / "fixtures" / "harness_selftest"
GS0_CORPUS = _REPO_ROOT / "tests" / "fixtures" / "recall" / "gs0"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "g4alpha: the five G4-alpha release gates. Required to be RED before green; "
        "this lane records red/green and never skips.",
    )


def resolve_corpus_path() -> Path:
    override = os.environ.get("TRAPPOINT_RECALL_CORPUS")
    if override:
        path = Path(override)
        if not path.is_dir():
            raise RuntimeError(
                f"TRAPPOINT_RECALL_CORPUS points at {path}, which is not a directory. "
                "Refusing to silently fall back: an override that misses is a "
                "misconfiguration, not a default."
            )
        return path
    if (GS0_CORPUS / "queries.jsonl").is_file():
        return GS0_CORPUS
    return SELFTEST_CORPUS


@pytest.fixture(scope="session")
def corpus_path() -> Path:
    return resolve_corpus_path()


@pytest.fixture(scope="session")
def corpus(corpus_path: Path) -> EvalCorpus:
    return load_corpus(corpus_path)
