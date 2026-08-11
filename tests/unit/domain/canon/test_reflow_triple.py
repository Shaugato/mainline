# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""CANONHOLD exit criterion 1 — the reflow triple collapses to ONE digest.

PL-2 RED-BEFORE-GREEN.  This module was committed and run before any
implementation existed.  Recorded red run (2026-08-04, local, Python 3.14.3)::

    tests/unit/domain/canon/test_reflow_triple.py::test_three_forms_yield_one_canon_sha256
    E   ModuleNotFoundError: No module named 'mainline_domain'

That is the right reason to be red: the canonicaliser did not exist.  The
assertion below is the product claim — renumbering, retypesetting and OCR
damage are *non-events* for clause identity — so a suite that had never been
red here would assert nothing.
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
    / "reflow-triple.json"
)


@pytest.fixture(scope="module")
def triple() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


def test_three_forms_yield_one_canon_sha256(triple: dict[str, Any]) -> None:
    """Retypeset + renumbered + OCR-noised ⇒ exactly one ``canon_sha256``."""
    from mainline_domain.canon import canonicalise

    results = [canonicalise(form["raw"]) for form in triple["forms"]]

    texts = {r.canon_text for r in results}
    assert len(texts) == 1, (
        "canonicalisation is not reflow-invariant; got distinct texts:\n"
        + "\n".join(
            f"  {form['id']}: {r.canon_text!r}" for form, r in zip(triple["forms"], results)
        )
    )
    assert results[0].canon_text == triple["expected_canon_text"]

    digests = {r.canon_sha256 for r in results}
    assert len(digests) == 1, "three presentations of one clause produced more than one digest"
    assert len(results[0].canon_sha256) == 32


def test_printed_labels_differ_but_identity_does_not(triple: dict[str, Any]) -> None:
    """The renumbering is retained as presentation and excluded from identity."""
    from mainline_domain.canon import canonicalise

    results = [canonicalise(form["raw"]) for form in triple["forms"]]
    labels = [r.printed_label for r in results]

    assert labels == [form["printed_label"] for form in triple["forms"]]
    assert len(set(labels)) == 2, "the fixture must actually exercise a renumbering"
    assert len({r.canon_sha256 for r in results}) == 1
    for r in results:
        assert r.numbering_prefix is not None
        assert r.numbering_prefix not in r.canon_text


def test_canon_version_is_stamped_on_every_result(triple: dict[str, Any]) -> None:
    from mainline_domain.canon import canonicalise
    from mainline_domain.canon.version import CANON_VERSION

    for form in triple["forms"]:
        assert canonicalise(form["raw"]).canon_version == CANON_VERSION
    assert CANON_VERSION == triple["canon_version"]
