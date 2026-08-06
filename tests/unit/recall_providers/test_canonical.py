# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""RFC 8785 canonicalisation — the thing every cassette key rests on."""

from __future__ import annotations

import pytest

from mainline_recall_agent.providers.canonical import (
    canonical_json,
    es6_number,
    request_digest,
)
from mainline_recall_agent.providers.errors import CanonicalisationError


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (-0.0, "0"),
        (1, "1"),
        (100.0, "100"),
        (1.5, "1.5"),
        (0.5, "0.5"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (-1.5e-8, "-1.5e-8"),
        (333333333.3333333, "333333333.3333333"),
    ],
)
def test_es6_number_matches_ecmascript(value: float, expected: str) -> None:
    assert es6_number(value) == expected


def test_nan_and_infinity_are_refused_not_coerced() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(CanonicalisationError):
            es6_number(bad)


def test_object_keys_sort_by_utf16_code_unit_not_code_point() -> None:
    """The JCS subtlety ``json.dumps(sort_keys=True)`` gets wrong.

    U+1F600 is above the BMP and encodes as the surrogate pair D83D DE00, so under UTF-16
    code units it sorts *before* U+FF3A (fullwidth Z).  Under Unicode code points — which
    is what Python's default string comparison uses — it sorts after.  Two implementations
    disagreeing here produce two different digests for the same request, and the cassette
    misses for a reason nobody can reproduce.
    """
    document = {"\U0001f600": 1, "Ｚ": 2, "a": 3}
    assert canonical_json(document) == '{"a":3,"\U0001f600":1,"Ｚ":2}'.encode()
    # The naive implementation, for contrast:
    import json

    assert json.dumps(document, sort_keys=True, separators=(",", ":")).encode() != (
        canonical_json(document)
    )


def test_control_characters_use_the_short_escapes() -> None:
    assert canonical_json({"k": "a\nb\tc\x01"}) == b'{"k":"a\\nb\\tc\\u0001"}'


def test_non_ascii_is_emitted_as_utf8_not_escaped() -> None:
    assert canonical_json({"k": "é"}) == '{"k":"é"}'.encode()


def test_digest_is_insensitive_to_key_order_and_whitespace() -> None:
    a = {"b": [1, 2, {"z": True, "y": None}], "a": "x"}
    b = {"a": "x", "b": [1, 2, {"y": None, "z": True}]}
    assert request_digest(a) == request_digest(b)


def test_digest_is_sensitive_to_value_change() -> None:
    assert request_digest({"a": 1}) != request_digest({"a": 1.0000001})


def test_unsupported_types_raise_rather_than_stringify() -> None:
    with pytest.raises(CanonicalisationError):
        canonical_json({"k": {1, 2}})
    with pytest.raises(CanonicalisationError):
        canonical_json({1: "int key"})
