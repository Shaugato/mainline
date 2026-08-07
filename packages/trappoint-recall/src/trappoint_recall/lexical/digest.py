# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The analyser's digest: making a silent analyser change impossible.

An analyser change is a **re-index**.  Every row of ``mainline.lex_posting`` is keyed by a term
this analyser produced; change the tokeniser and those keys refer to a vocabulary that no
longer exists, so document frequencies are wrong, IDF is wrong, and channel D quietly returns
a different set of precursors for the same permit.  Nothing raises.  A permit that would have
been blocked merges.

Two layers catch it, because they fail for different reasons:

``rule_fingerprint()``
    A hash of the analyser's **data** — the stopword list, the unit table, the regex sources,
    the character map, the component-length rule, and the version strings of the stemmer and
    the analyser.  This is what moves when somebody adds a unit or removes a stopword.

``corpus_digest()``
    A hash of the analyser's **behaviour** — the exact token stream, with classes, produced for
    every document in :data:`~trappoint_recall.lexical.golden_corpus.GOLDEN_CORPUS`.  This is
    what moves when the *code* changes, including changes that leave every table untouched.

Both are committed to ``data/analyser_golden.json`` alongside the per-document token streams,
so a failure names the document and shows the diff instead of printing two hex strings.

Regeneration is deliberately awkward: :func:`main` refuses to rewrite the file without
``--acknowledge-reindex``, and prints what accepting it commits the operator to.  A one-key
"update the golden" is how a re-index becomes an accident.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from trappoint_recall.lexical.analyser import (
    ANALYSER_VERSION,
    analyse,
    rule_fingerprint,
)
from trappoint_recall.lexical.golden_corpus import GOLDEN_CORPUS

__all__ = [
    "GOLDEN_PATH",
    "build_golden",
    "canonical_tokens",
    "corpus_digest",
    "document_digest",
    "load_golden",
    "main",
]

GOLDEN_PATH: Final[Path] = Path(__file__).resolve().parent / "data" / "analyser_golden.json"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_tokens(text: str) -> list[list[str]]:
    """``[[term, token_class], …]`` — the analyser's whole observable output.

    Character offsets are deliberately excluded: they move when the *input* is edited, and
    what is being pinned is the analyser, not the corpus.  The class is included because a
    term that changes class changes whether it is stemmed and whether it is stopped, which is
    a behavioural change even when the string is identical.
    """
    return [[token.text, token.token_class.value] for token in analyse(text)]


def document_digest(text: str) -> str:
    return hashlib.sha256(_canonical_json(canonical_tokens(text)).encode("utf-8")).hexdigest()


def corpus_digest(corpus: Mapping[str, str] = GOLDEN_CORPUS) -> str:
    """One digest over every document's token stream, keyed by document id."""
    payload = {name: canonical_tokens(text) for name, text in sorted(corpus.items())}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def build_golden(corpus: Mapping[str, str] = GOLDEN_CORPUS) -> dict[str, Any]:
    """Compute the whole golden record for the given corpus."""
    return {
        "_note": (
            "Committed expectations for the lexical analyser. A diff here is a RE-INDEX of "
            "mainline.lex_posting, not a test update. See digest.py."
        ),
        "analyser_version": ANALYSER_VERSION,
        "rule_fingerprint": rule_fingerprint(),
        "corpus_digest": corpus_digest(corpus),
        "documents": {
            name: {
                "text": text,
                "digest": document_digest(text),
                "tokens": canonical_tokens(text),
            }
            for name, text in sorted(corpus.items())
        },
    }


def load_golden(path: Path = GOLDEN_PATH) -> dict[str, Any]:
    """Read the committed golden record."""
    with path.open(encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


_ACKNOWLEDGEMENT: Final[str] = """\
Rewriting data/analyser_golden.json asserts ALL of the following:

  * the analyser change was intended;
  * mainline.lex_posting, lex_stats and lex_doclen will be REBUILT for every site before
    channel D is trusted again, because the existing rows key on the old vocabulary;
  * ANALYSER_VERSION has been bumped, so two writers cannot share one posting list across
    the change;
  * the change is recorded as a migration, not as a patch.

If any of those is not true, revert the analyser instead.
"""


def main(argv: list[str] | None = None) -> int:
    """Print or (with an explicit acknowledgement) rewrite the golden record."""
    parser = argparse.ArgumentParser(
        prog="trappoint-lex-golden",
        description="Show or regenerate the lexical analyser's golden digest.",
    )
    parser.add_argument(
        "--acknowledge-reindex",
        action="store_true",
        help="rewrite data/analyser_golden.json; see the printed acknowledgement",
    )
    args = parser.parse_args(argv)
    golden = build_golden()
    if not args.acknowledge_reindex:
        print(f"analyser_version : {golden['analyser_version']}")
        print(f"rule_fingerprint : {golden['rule_fingerprint']}")
        print(f"corpus_digest    : {golden['corpus_digest']}")
        if GOLDEN_PATH.exists():
            committed = load_golden()
            same = committed.get("corpus_digest") == golden["corpus_digest"]
            print(f"committed        : {'MATCHES' if same else 'DIFFERS'}")
            if not same:
                print("\n" + _ACKNOWLEDGEMENT, file=sys.stderr)
                return 1
        else:
            print("committed        : ABSENT (run with --acknowledge-reindex to create)")
            return 1
        return 0
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(_canonical_json(golden) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN_PATH}")
    print("\n" + _ACKNOWLEDGEMENT)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
