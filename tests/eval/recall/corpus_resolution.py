# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Where the G4-alpha numbers come from — one resolution rule, one place.

Both the pytest fixtures (``conftest.py``) and the CI lane runner (``g4alpha_lane.py``)
have to answer the same question: *which corpus produced this verdict?* Answering it
twice is how a lane ends up reporting a colour measured on a corpus other than the one
it names, so the rule lives here and both import it.

Resolution order:

1. ``$TRAPPOINT_RECALL_CORPUS`` — an explicit override, for a lane pointed at a real set.
2. ``tests/fixtures/recall/gs0`` — GS0, once ``recall-corpora-goldsets`` lands it.
3. ``tests/eval/recall/fixtures/harness_selftest`` — the committed self-test corpus.

**The fallback is never a skip.** A release gate that can be skipped because a corpus is
missing is not a release gate, and the suite must be able to be red on day one. An
override that points at nothing is a misconfiguration and raises, because silently
falling back from a real corpus to a synthetic one would publish a synthetic number
under a real corpus's name.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Final

__all__ = [
    "GS0_CORPUS",
    "PACKAGE_SRC",
    "REPO_ROOT",
    "SELFTEST_CORPUS",
    "SUITE_DIR",
    "corpus_provenance",
    "ensure_import_paths",
    "resolve_corpus_path",
]

SUITE_DIR: Final[Path] = Path(__file__).resolve().parent
REPO_ROOT: Final[Path] = SUITE_DIR.parents[2]
PACKAGE_SRC: Final[Path] = REPO_ROOT / "packages" / "trappoint-recall" / "src"

SELFTEST_CORPUS: Final[Path] = SUITE_DIR / "fixtures" / "harness_selftest"
GS0_CORPUS: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "recall" / "gs0"

ENV_OVERRIDE: Final = "TRAPPOINT_RECALL_CORPUS"


def ensure_import_paths() -> None:
    """Put the suite directory and the package source on ``sys.path``.

    The uv workspace installs ``trappoint-recall`` in editable mode, so this is normally
    a no-op. It exists so the suite also runs from a bare checkout: "the gate suite would
    not import" must never be the reason a lane reports anything other than red.
    """
    for entry in (SUITE_DIR, PACKAGE_SRC):
        text = str(entry)
        if entry.is_dir() and text not in sys.path:
            sys.path.insert(0, text)


def resolve_corpus_path(environ: dict[str, str] | None = None) -> Path:
    """Return the corpus directory this run must measure.

    Raises:
        RuntimeError: if ``$TRAPPOINT_RECALL_CORPUS`` is set but is not a directory.
    """
    env = os.environ if environ is None else environ
    override = env.get(ENV_OVERRIDE)
    if override:
        path = Path(override)
        if not path.is_dir():
            raise RuntimeError(
                f"{ENV_OVERRIDE} points at {path}, which is not a directory. "
                "Refusing to silently fall back: an override that misses is a "
                "misconfiguration, not a default."
            )
        return path
    if (GS0_CORPUS / "queries.jsonl").is_file():
        return GS0_CORPUS
    return SELFTEST_CORPUS


def corpus_provenance(path: Path) -> dict[str, object]:
    """Describe a corpus well enough that a reader knows what the verdict is worth.

    Loads the corpus through the package's own loader so the description cannot drift
    from the thing that was measured. Falls back to a structural description if the
    corpus will not load — the lane reports that as an inability to run, not as a pass.
    """
    ensure_import_paths()
    source: str
    if os.environ.get(ENV_OVERRIDE):
        source = "env:TRAPPOINT_RECALL_CORPUS"
    elif path == GS0_CORPUS:
        source = "gs0"
    else:
        source = "selftest"

    record: dict[str, object] = {"path": str(path), "source": source}
    try:
        from trappoint_recall.eval.corpus import load_corpus

        corpus = load_corpus(path)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        record["loaded"] = False
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record

    record["loaded"] = True
    record["label"] = corpus.label()
    record["name"] = corpus.name
    record["preliminary"] = corpus.preliminary
    record["synthetic"] = corpus.synthetic
    record["split_policy_id"] = corpus.split_policy_id
    record["n_queries"] = len(corpus.queries)
    record["n_retro_sev5"] = len(corpus.retro_severity_5)
    record["n_routine"] = len(corpus.by_kind("routine"))
    return record
