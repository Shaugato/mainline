# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The golden digest: a silent analyser change is a CI failure.

Read this before "fixing" a failure here.  Every row in ``mainline.lex_posting`` is keyed by a
term this analyser produced.  Change the analyser and those keys name a vocabulary that no
longer exists: ``df`` is wrong, IDF is wrong, and channel D returns a different set of
precursors for the same permit — with nothing raising anywhere.  A red test here means either
revert, or schedule a rebuild of every site's index and bump ``ANALYSER_VERSION``.  It does not
mean regenerate the golden.

The suite is deliberately three assertions rather than one, because they fail for different
reasons and the difference is the diagnosis:

* the **rule fingerprint** moves when a table moves (a unit, a stopword, a regex);
* the **corpus digest** moves when behaviour moves, including code changes that touch no table;
* the **per-document token streams** say *which* document changed and *how*, which is the only
  form of this failure a human can act on.

``test_the_digest_is_not_vacuous`` is the PL-2 obligation: a golden test that would pass
against a mutated analyser asserts nothing, so the mutation is performed and the failure
demanded.
"""

from __future__ import annotations

import pytest
from trappoint_recall.lexical import analyser as analyser_module
from trappoint_recall.lexical.analyser import ANALYSER_VERSION, rule_fingerprint
from trappoint_recall.lexical.digest import (
    build_golden,
    canonical_tokens,
    corpus_digest,
    document_digest,
    load_golden,
)
from trappoint_recall.lexical.golden_corpus import GOLDEN_CORPUS

pytestmark = pytest.mark.golden


@pytest.fixture(scope="module")
def golden() -> dict[str, object]:
    return load_golden()


def test_analyser_version_matches_the_committed_record(golden: dict[str, object]) -> None:
    assert golden["analyser_version"] == ANALYSER_VERSION, (
        "ANALYSER_VERSION changed without the golden record being re-cut. Two writers must "
        "never share one posting list across an analyser version boundary."
    )


def test_rule_fingerprint_matches(golden: dict[str, object]) -> None:
    assert rule_fingerprint() == golden["rule_fingerprint"], (
        "The analyser's DATA changed: a stopword, a unit, a regex, the character map or the "
        "component-length rule. This is a re-index, not a patch."
    )


def test_corpus_digest_matches(golden: dict[str, object]) -> None:
    assert corpus_digest() == golden["corpus_digest"], (
        "The analyser's BEHAVIOUR changed. See the per-document failures for which document "
        "moved; if none of them did, the corpus itself was edited."
    )


def test_the_corpus_itself_was_not_edited(golden: dict[str, object]) -> None:
    documents = golden["documents"]
    assert isinstance(documents, dict)
    assert set(documents) == set(GOLDEN_CORPUS), (
        "The golden corpus gained or lost a document. Each entry pins a named behaviour; "
        "removing one removes the protection, and adding one without re-cutting the record "
        "leaves it unpinned."
    )
    for name, text in GOLDEN_CORPUS.items():
        assert documents[name]["text"] == text, f"golden corpus text for {name!r} was edited"


@pytest.mark.parametrize("name", sorted(GOLDEN_CORPUS))
def test_document_token_stream(name: str, golden: dict[str, object]) -> None:
    documents = golden["documents"]
    assert isinstance(documents, dict)
    expected = documents[name]
    actual = canonical_tokens(GOLDEN_CORPUS[name])
    assert actual == expected["tokens"], (
        f"analyser output changed for {name!r}\n"
        f"  committed: {[t[0] for t in expected['tokens']]}\n"
        f"  now:       {[t[0] for t in actual]}"
    )
    assert document_digest(GOLDEN_CORPUS[name]) == expected["digest"]


def test_the_digest_is_not_vacuous(monkeypatch: pytest.MonkeyPatch) -> None:
    """PL-2: prove the golden test can fail.

    The mutation is the smallest one that a careless edit could plausibly introduce — allowing
    single-character identifier components back in — and it is exactly the kind of change that
    alters every posting list without altering a single visible behaviour in a demo.
    """
    baseline = corpus_digest()
    monkeypatch.setattr(analyser_module, "_MIN_COMPONENT_LEN", 1)
    mutated = corpus_digest()
    assert mutated != baseline, (
        "mutating the analyser did not move the corpus digest, so the golden test cannot "
        "detect an analyser change and asserts nothing"
    )


def test_build_golden_is_a_pure_function_of_the_analyser() -> None:
    """Two builds in one process must agree; a digest that depends on iteration order lies."""
    assert build_golden()["corpus_digest"] == build_golden()["corpus_digest"]


def test_fingerprint_covers_the_stopword_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half of PL-2: a table edit must move the fingerprint."""
    baseline = rule_fingerprint()
    monkeypatch.setattr(
        analyser_module, "STOPWORDS", frozenset(analyser_module.STOPWORDS | {"zzzz"})
    )
    assert rule_fingerprint() != baseline
