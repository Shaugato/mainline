# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Locked CANONHOLD outputs.

These digests are what blame edges attach to.  If one of them moves, the correct
response is a ``canon_version`` bump plus a re-normalisation migration — never an
edit to the fixture.  The fixture is checked in so that an opposing expert can
reproduce a clause digest with the committed inputs and ``sha256sum``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "domain"
    / "canon"
    / "golden-vectors.json"
)

_DOC: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
_VECTORS: list[dict[str, Any]] = _DOC["vectors"]


@pytest.mark.parametrize("vector", _VECTORS, ids=[v["id"] for v in _VECTORS])
def test_golden_vector(vector: dict[str, Any]) -> None:
    from mainline_domain.canon import canonicalise

    result = canonicalise(vector["raw"])

    assert result.canon_text == vector["canon_text"]
    assert result.canon_sha256.hex() == vector["canon_sha256_hex"]
    assert result.printed_label == vector["printed_label"]
    assert result.numbering_prefix == vector["numbering_prefix"]
    assert [list(span) for span in result.furniture_spans] == vector["furniture_spans"]
    assert len(result.segments) == vector["segment_count"]
    assert [
        {"start": r.start, "end": r.end, "before": r.before, "after": r.after}
        for r in result.ocr_repairs
    ] == vector["ocr_repairs"]


def test_fixture_declares_the_version_it_was_locked_at() -> None:
    from mainline_domain.canon import CANON_VERSION

    assert _DOC["canon_version"] == CANON_VERSION, (
        "the golden vectors were locked at a different canon_version; "
        "a bump requires a re-normalisation migration, not a fixture rewrite"
    )


@pytest.mark.parametrize("vector", _VECTORS, ids=[v["id"] for v in _VECTORS])
def test_every_offset_is_inside_canon_text(vector: dict[str, Any]) -> None:
    """Spans are load-bearing: an out-of-range offset is a corrupted evidence row."""
    from mainline_domain.canon import canonicalise

    result = canonicalise(vector["raw"])
    length = len(result.canon_text)

    for repair in result.ocr_repairs:
        assert 0 <= repair.start < repair.end <= length
        assert result.canon_text[repair.start : repair.end] == repair.after
        assert len(repair.before) == len(repair.after)

    for segment in result.segments:
        assert 0 <= segment.start < segment.end <= length

    for start, end in result.furniture_spans:
        assert 0 <= start <= end <= len(vector["raw"])
