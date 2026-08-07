# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The gazetteers are evidence, so their identity must be computable.

PL-2 RED-BEFORE-GREEN.  This module was written and run before the loader
exposed a version or a fingerprint, and re-run against the pre-change loader
afterwards to record the exact output.  Red run (2026-08-07, local,
Python 3.14.3) — **7 failed, 1 passed**::

    E   AttributeError: 'Gazetteers' object has no attribute 'versions'
    E   ImportError: cannot import name 'require_version' from
        'mainline_domain.anchors.gazetteer'
    E   ImportError: cannot import name 'gazetteer_fingerprint' from
        'mainline_domain.anchors.gazetteer'

The one test that passed red is
:func:`test_every_committed_gazetteer_declares_an_integer_version`, and that is
the point: the *data* already declared a version.  Nothing read it.

The hole this closes: every committed gazetteer already declared ``version``,
and **nothing read it**.  A word list could therefore be edited with no version
bump, no digest change and no trace — which makes anchor drop unfalsifiable,
because the set of things that count as an anchor would depend on which checkout
ran the extractor.  CANONHOLD has ``canon_version`` bound into its digest
preimage for exactly this reason; ANCHORLOCK needs the same property, and this
is it.

What the fingerprint deliberately covers: the **bytes of the committed files**,
not the parsed entries.  A comment-only edit changes it.  That is correct — the
fingerprint identifies the artefact an opposing expert would be handed, and
"which bytes were in the tree" is the question it has to answer.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import pytest

GAZETTEER_DIR = (
    Path(__file__).resolve().parents[4]
    / "verticals"
    / "mainline"
    / "packages"
    / "mainline-domain"
    / "src"
    / "mainline_domain"
    / "data"
    / "gazetteer"
)

ANCHOR_GAZETTEERS = (
    "citations.toml",
    "equipment.toml",
    "instrument.toml",
    "isolation.toml",
    "roles.toml",
    "setpoint-units.toml",
)


def test_every_committed_gazetteer_declares_an_integer_version() -> None:
    """A word list with no version is a word list that can drift silently."""
    for name in ANCHOR_GAZETTEERS:
        document = tomllib.loads((GAZETTEER_DIR / name).read_text(encoding="utf-8"))
        [table] = [value for value in document.values() if isinstance(value, dict)]
        assert isinstance(table.get("version"), int), f"{name} declares no integer version"


def test_the_loader_reports_every_gazetteer_version() -> None:
    from mainline_domain.anchors.gazetteer import load_gazetteers

    versions = dict(load_gazetteers().versions)
    assert set(versions) == set(ANCHOR_GAZETTEERS)
    assert all(isinstance(v, int) and v >= 1 for v in versions.values())


def test_a_gazetteer_without_a_version_is_refused() -> None:
    """Strict, not lenient: a missing version raises rather than defaulting to 0."""
    from mainline_domain.anchors.gazetteer import require_version

    assert require_version({"version": 3}, "equipment.toml") == 3
    with pytest.raises(TypeError, match="version"):
        require_version({}, "equipment.toml")
    with pytest.raises(TypeError, match="version"):
        require_version({"version": "1"}, "equipment.toml")
    with pytest.raises(ValueError, match="version"):
        require_version({"version": 0}, "equipment.toml")


def test_the_fingerprint_is_stable_and_reproducible_by_hand() -> None:
    """32 bytes, identical across calls, and recomputable with sha256sum + tomllib."""
    from mainline_domain.anchors.gazetteer import gazetteer_fingerprint, load_gazetteers

    loaded = load_gazetteers()
    assert len(loaded.fingerprint) == 32
    assert load_gazetteers().fingerprint == loaded.fingerprint

    entries = []
    for name in ANCHOR_GAZETTEERS:
        raw = (GAZETTEER_DIR / name).read_bytes()
        document = tomllib.loads(raw.decode("utf-8"))
        [table] = [value for value in document.values() if isinstance(value, dict)]
        version = table["version"]
        assert isinstance(version, int)
        entries.append((name, version, hashlib.sha256(raw).digest()))

    assert gazetteer_fingerprint(entries) == loaded.fingerprint


def test_the_fingerprint_moves_when_anything_moves() -> None:
    """Content, version and file-set changes must each be visible."""
    from mainline_domain.anchors.gazetteer import gazetteer_fingerprint

    base = [
        ("equipment.toml", 1, hashlib.sha256(b"a").digest()),
        ("roles.toml", 1, hashlib.sha256(b"b").digest()),
    ]
    changed_content = [
        ("equipment.toml", 1, hashlib.sha256(b"a2").digest()),
        ("roles.toml", 1, hashlib.sha256(b"b").digest()),
    ]
    changed_version = [
        ("equipment.toml", 2, hashlib.sha256(b"a").digest()),
        ("roles.toml", 1, hashlib.sha256(b"b").digest()),
    ]
    dropped_file = [("equipment.toml", 1, hashlib.sha256(b"a").digest())]

    fingerprints = {
        gazetteer_fingerprint(base),
        gazetteer_fingerprint(changed_content),
        gazetteer_fingerprint(changed_version),
        gazetteer_fingerprint(dropped_file),
    }
    assert len(fingerprints) == 4


def test_the_fingerprint_does_not_depend_on_the_order_entries_are_passed() -> None:
    """Two runs that walk the directory differently must agree."""
    from mainline_domain.anchors.gazetteer import gazetteer_fingerprint

    entries = [
        ("equipment.toml", 1, hashlib.sha256(b"a").digest()),
        ("roles.toml", 2, hashlib.sha256(b"b").digest()),
        ("citations.toml", 3, hashlib.sha256(b"c").digest()),
    ]
    assert gazetteer_fingerprint(entries) == gazetteer_fingerprint(list(reversed(entries)))


def test_a_name_boundary_cannot_be_forged() -> None:
    """Length-prefixed encoding: no concatenation of names can collide."""
    from mainline_domain.anchors.gazetteer import gazetteer_fingerprint

    digest = hashlib.sha256(b"x").digest()
    left = gazetteer_fingerprint([("ab", 1, digest), ("c", 1, digest)])
    right = gazetteer_fingerprint([("a", 1, digest), ("bc", 1, digest)])
    assert left != right


def test_the_fingerprint_is_reachable_from_the_package_surface() -> None:
    """W7/W8 stamp it onto identity rows; it must not be a private detail."""
    import mainline_domain.anchors as anchors

    assert "gazetteer_fingerprint" in anchors.__all__
    assert anchors.load_gazetteers().fingerprint == anchors.gazetteer_fingerprint(
        [
            (
                name,
                dict(anchors.load_gazetteers().versions)[name],
                hashlib.sha256((GAZETTEER_DIR / name).read_bytes()).digest(),
            )
            for name in ANCHOR_GAZETTEERS
        ]
    )
