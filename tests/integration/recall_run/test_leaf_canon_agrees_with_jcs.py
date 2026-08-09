# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The narrow canonicaliser is narrow, not different.

``spec/wire/candidate-commitment.md`` section 10 makes a dependency claim that is load-bearing
for the whole mechanism: *the reference PER verifier imports the Python standard library and
nothing else.* The person a silence receipt is written for does not trust us, so the tool they
check it with cannot be ours to change — not even a package from this repository.

That claim costs a second RFC 8785 implementation, and a second implementation is a second
chance to be wrong. :mod:`trappoint_recall.per.canon` therefore accepts only the frozen leaf
profile (a flat object of ``int`` and ``str`` members) and refuses everything else — and this
suite is the reason that restriction is honest rather than merely convenient. Every leaf the
narrow canonicaliser will accept is canonicalised twice, once by it and once by the full
RFC 8785 implementation in ``trappoint_jcs``, and the **bytes** are compared.

Both directions are asserted:

* agreement, over randomised leaves and over the specification's worked example; and
* refusal, over the values the profile excludes — because a canonicaliser that accepted a
  float, a bool or a nested object would produce bytes ``trappoint_jcs`` renders differently,
  and the divergence would be discovered by an opposing expert rather than by CI.

``trappoint_jcs`` is a workspace package, not a third-party oracle; the check it provides is
therefore agreement between two implementations written to the same RFC, not independent
validation of the RFC itself. That is stated here rather than implied.
"""

from __future__ import annotations

import pytest

trappoint_jcs = pytest.importorskip(
    "trappoint_jcs",
    reason=(
        "trappoint-jcs is a workspace package; without it this differential has no oracle and "
        "reporting a pass would assert something it did not check"
    ),
)

from hypothesis import given, settings  # noqa: E402  (after importorskip, deliberately)
from hypothesis import strategies as st  # noqa: E402

from trappoint_recall.per.canon import MAX_SAFE_INTEGER, canonicalise_leaf  # noqa: E402
from trappoint_recall.per.errors import NotCanonicalisable  # noqa: E402
from trappoint_recall.per.leaf import MICRO, Leaf, leaf_preimage  # noqa: E402

#: Section 3.2's worked example, byte for byte. If this line and the specification ever
#: disagree, one of them is wrong and a reader has no way to tell which — so it is pinned here.
SPEC_EXAMPLE_LEAF = Leaf(
    ord=7,
    event_id="0f4a3b21-8c5d-4e6f-9a0b-1c2d3e4f5061",
    score_q=451200,
    tau_applied_q=450000,
    outcome="silenced",
)
SPEC_EXAMPLE_BYTES = (
    b'{"event_id":"0f4a3b21-8c5d-4e6f-9a0b-1c2d3e4f5061","ord":7,"outcome":"silenced",'
    b'"score_q":451200,"tau_applied":450000}'
)

_UUIDS = st.uuids().map(str)
_OUTCOMES = st.sampled_from(("blocking", "advisory", "silenced", "deduped"))
_MICRO = st.integers(min_value=0, max_value=MICRO)

_LEAF_OBJECTS = st.builds(
    lambda ordinal, event_id, score_q, tau_q, outcome: {
        "ord": ordinal,
        "event_id": event_id,
        "score_q": score_q,
        "tau_applied": tau_q,
        "outcome": outcome,
    },
    st.integers(min_value=1, max_value=1_000_000),
    _UUIDS,
    _MICRO,
    _MICRO,
    _OUTCOMES,
)


def test_the_specification_example_is_reproduced_by_both() -> None:
    """The worked example in section 3.2 is the bytes both implementations emit."""
    assert leaf_preimage(SPEC_EXAMPLE_LEAF) == SPEC_EXAMPLE_BYTES
    assert trappoint_jcs.canonicalise(SPEC_EXAMPLE_LEAF.member()) == SPEC_EXAMPLE_BYTES


@settings(max_examples=250, deadline=None)
@given(member=_LEAF_OBJECTS)
def test_randomised_leaves_canonicalise_identically(member: dict[str, int | str]) -> None:
    """The differential: same object, same bytes, over the whole accepted profile."""
    assert canonicalise_leaf(member) == trappoint_jcs.canonicalise(member)


@settings(max_examples=250, deadline=None)
@given(member=_LEAF_OBJECTS)
def test_the_evidentiary_payload_profile_accepts_a_leaf(member: dict[str, int | str]) -> None:
    """A PER leaf is canonicalisable by the custody ledger's stricter profile too.

    Ruling CU-5 refuses binary floats in a hashed preimage. This is the assertion behind the
    D10 decision to quantise ``tau_applied`` even though it is not the sort key: a leaf that
    was canonicalisable by one profile and not the other would be a trap for whoever wires PER
    into the ledger next.
    """
    assert canonicalise_leaf(member) == trappoint_jcs.canonicalise_payload(member)


@pytest.mark.parametrize(
    ("value", "why"),
    [
        (1.0, "a float renders differently under ES6 number formatting"),
        (True, "bool is an int subclass in Python and would serialise as 0/1, not true"),
        (None, "null is not in the frozen leaf profile"),
        ({"a": 1}, "the leaf object is flat"),
        ([1, 2], "the leaf object holds no arrays"),
        (MAX_SAFE_INTEGER + 1, "above 2**53-1 an ECMAScript renderer disagrees"),
    ],
)
def test_the_narrow_profile_refuses_what_it_cannot_promise(value: object, why: str) -> None:
    """Narrower than RFC 8785, and it says so by refusing rather than by guessing."""
    with pytest.raises(NotCanonicalisable):
        canonicalise_leaf({"ord": value})  # type: ignore[dict-item]
    assert why


def test_member_order_is_utf16_code_unit_order_not_python_string_order() -> None:
    """RFC 8785 section 3.2.3 ordering, on names where the two orderings actually differ.

    Python compares ``str`` by code point; RFC 8785 compares by UTF-16 code unit. The two
    disagree across the supplementary-plane boundary: ``U+1F600`` encodes as the surrogate
    pair ``D83D DE00``, so it sorts **below** ``U+E000`` in UTF-16 while sorting above it by
    code point. Every member name the leaf profile actually uses is ASCII, where the two
    orderings coincide — so nothing else in this file would catch a regression here.
    """
    bmp = "\ue000"
    astral = "\U0001f600"
    assert bmp < astral, "by code point the BMP name sorts first"

    member: dict[str, int | str] = {bmp: 1, astral: 2}
    emitted = canonicalise_leaf(member)
    assert emitted == trappoint_jcs.canonicalise(member)
    assert emitted.index(astral.encode()) < emitted.index(bmp.encode()), (
        "UTF-16 code-unit order puts the surrogate-pair name first, and that is the order "
        "RFC 8785 specifies"
    )
