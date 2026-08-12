# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``canon(canon(x)) == canon(x)`` — proved over generated document text.

Why this property and not some notion of "correctness": a canonicaliser whose
second application disagrees with its first cannot be re-run.  It cannot be
re-run during a re-normalisation migration, it cannot be re-run by an opposing
expert reproducing a digest, and it cannot be re-run by a verifier checking that
a stored ``canon_sha256`` matches its stored ``canon_text``.  Every one of those
is a load-bearing use in this system, so idempotence is not a nicety — it is the
property that makes the digest evidence.

The alphabet is deliberately document-shaped: letters, digits, the punctuation
procedures actually use, line breaks, and the exact troublemakers the pipeline
exists to absorb (SOFT HYPHEN, NO-BREAK SPACE, ligatures, smart quotes, the
dash family, LINE SEPARATOR).  Uniform random Unicode would test the standard
library's NFKC, not this module.
"""

# ruff: noqa: RUF001
#
# RUF001 flags "ambiguous" characters in string literals: NO-BREAK SPACE, LINE SEPARATOR,
# the smart quotes, HYPHEN, EN DASH, MINUS SIGN. Here that ambiguity IS the subject under
# test. `_TROUBLEMAKERS` is the fixture -- the exact characters a procedure PDF puts into
# text and the canonicaliser has to absorb -- and the discretionary-break tuple in
# `test_canon_text_has_no_residual_presentation` is the assertion that they are gone
# afterwards. "Did you mean `-` (HYPHEN-MINUS)?": no. Applying ruff's suggestion would
# replace every vector with the ASCII character the canonicaliser is supposed to
# PRODUCE, so the property would be proved against input that never needed
# canonicalising, and the suite would pass vacuously while the module rotted.
#
# The suppression is file-level, not per-line, for two reasons: every ambiguous character
# in this file is a vector, so there is no other kind to keep gated; and a per-line
# directive would have to be appended to the fixture lines themselves, where the
# requirement is that those bytes never move.

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_TROUBLEMAKERS = [
    "­",  # SOFT HYPHEN
    " ",  # NO-BREAK SPACE
    "​",  # ZERO WIDTH SPACE
    " ",  # LINE SEPARATOR
    "ﬁ",  # LATIN SMALL LIGATURE FI
    "ﬂ",  # LATIN SMALL LIGATURE FL
    "‘",
    "’",
    "“",
    "”",
    "‐",
    "–",
    "—",
    "−",
    "°",
    "µ",
    "≤",
    "≥",
    "±",
    "•",
    "§",
]

_CHARS = st.sampled_from(
    list("abcdefghijklmnopqrstuvwxyz")
    + list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    + list("0123456789")
    + list(" \t\n\r-.,;:()[]/%'\"")
    + _TROUBLEMAKERS
)

_FRAGMENTS = st.sampled_from(
    [
        "Page ",
        " of ",
        "Rev. ",
        "Section ",
        "7.3.2(b)",
        "4.1.1",
        "(a) ",
        "iv) ",
        "isola-\ntion",
        "lock-\nout",
        "ver-\nify",
        "P-101A",
        "LOTO-4471",
        "AS 2865",
        "10 % LEL",
        "1O0 kPa",
        "286S",
        "Uncontrolled when printed",
        "Confidential",
        "shall verify that",
        "the Authorised Gas Tester",
        "• ",
        "i.e. ",
        "50 psig",
        "\n",
        " ",
        "\n\n",
    ]
)

_TEXT = st.one_of(
    st.text(alphabet=_CHARS, max_size=160),
    st.lists(_FRAGMENTS, max_size=24).map("".join),
)


@settings(max_examples=1200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(raw=_TEXT)
def test_canon_is_idempotent(raw: str) -> None:
    from mainline_domain.canon import canonicalise

    once = canonicalise(raw)
    twice = canonicalise(once.canon_text)

    assert twice.canon_text == once.canon_text
    assert twice.canon_sha256 == once.canon_sha256


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(raw=_TEXT)
def test_canon_never_empties_non_blank_text(raw: str) -> None:
    """A canonicaliser that can return '' for real text can delete a control."""
    from mainline_domain.canon import canonicalise

    result = canonicalise(raw)
    if raw.strip() and any(ch.isalnum() for ch in raw):
        assert result.canon_text != "" or result.numbering_prefix is not None


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(raw=_TEXT)
def test_numbering_excision_reaches_a_fixpoint(raw: str) -> None:
    """One pass removes every leading label, so a second pass removes none.

    This is the property that carries idempotence: without the fixpoint loop,
    ``1. 2.3 Before`` would shed one label per application and the digest would
    depend on how many times the canonicaliser had been run.
    """
    from mainline_domain.canon import canonicalise

    result = canonicalise(raw)
    assert canonicalise(result.canon_text).numbering_prefix is None
    if result.printed_label is not None:
        assert result.printed_label == result.printed_label.strip()
        assert " " not in result.printed_label


@settings(max_examples=400, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(raw=_TEXT)
def test_canon_text_has_no_residual_presentation(raw: str) -> None:
    """No line breaks, no runs of whitespace, no discretionary break characters."""
    from mainline_domain.canon import canonicalise

    text = canonicalise(raw).canon_text
    assert "\n" not in text
    assert "\r" not in text
    assert "\t" not in text
    assert "  " not in text
    assert text == text.strip()
    for discretionary in ("­", "​", "‌", "‍", "⁠", "﻿"):
        assert discretionary not in text
