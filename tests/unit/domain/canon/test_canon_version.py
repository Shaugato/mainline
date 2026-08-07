# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""``canon_version`` is a migration, not a config flag — enforced, not asserted.

Three ways this could rot, all closed here:

* someone adds an environment override "just for the backfill";
* someone adds a ``canon_version=`` keyword to ``canonicalise`` so a caller can
  pick;
* someone drops the version out of the digest preimage, so a bump silently
  leaves old digests comparing equal to new ones at the S1 exact stage.
"""

from __future__ import annotations

import inspect
from pathlib import Path

PACKAGE = (
    Path(__file__).resolve().parents[4]
    / "verticals"
    / "mainline"
    / "packages"
    / "mainline-domain"
    / "src"
    / "mainline_domain"
)


def test_canon_version_is_an_int_constant() -> None:
    from mainline_domain.canon.version import CANON_VERSION

    assert isinstance(CANON_VERSION, int)
    assert CANON_VERSION >= 1


def test_no_environment_override_anywhere_in_the_canon_package() -> None:
    """Checked on the AST, not on the text — the docstrings name these words."""
    import ast

    banned_names = {"environ", "getenv", "environb"}
    banned_modules = {"os", "dotenv", "configparser"}
    offenders: list[str] = []

    for path in sorted((PACKAGE / "canon").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in banned_names:
                offenders.append(f"{path}:{node.lineno}: attribute {node.attr}")
            elif isinstance(node, ast.Name) and node.id in banned_names:
                offenders.append(f"{path}:{node.lineno}: name {node.id}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in banned_modules:
                        offenders.append(f"{path}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in banned_modules:
                    offenders.append(f"{path}:{node.lineno}: from {node.module} import ...")

    assert offenders == [], f"canon_version must not be overridable at runtime: {offenders}"


def test_canonicalise_takes_no_version_parameter() -> None:
    from mainline_domain.canon import canonicalise

    parameters = inspect.signature(canonicalise).parameters
    assert "canon_version" not in parameters
    assert "version" not in parameters


def test_the_version_is_bound_into_the_digest_preimage() -> None:
    from mainline_domain.canon import canon_digest
    from mainline_domain.canon.version import CANON_VERSION

    text = "Isolate P-101A before entry."
    assert canon_digest(text, CANON_VERSION) != canon_digest(text, CANON_VERSION + 1)


def test_digest_is_sha256_of_the_documented_preimage() -> None:
    """An opposing expert must be able to reproduce this with sha256sum."""
    import hashlib

    from mainline_domain.canon import canon_digest
    from mainline_domain.canon.version import CANON_DIGEST_DOMAIN, CANON_VERSION

    text = "Isolate P-101A before entry."
    expected = hashlib.sha256(
        CANON_DIGEST_DOMAIN + str(CANON_VERSION).encode("ascii") + b"\x1f" + text.encode("utf-8")
    ).digest()
    assert canon_digest(text) == expected


def test_the_lexicon_version_tracks_canon_version() -> None:
    """Editing the de-hyphenation lexicon IS a ``canon_version`` bump.

    ``domain-lexicon.toml`` says so in its header — "adding an entry changes
    digests, so it is a canon_version bump, not an edit" — and until this test
    existed, nothing held anyone to it.  A lexicon entry changes which side of a
    line-wrap hyphen a word lands on, which changes ``canon_text``, which changes
    ``canon_sha256`` for every clause containing that compound.  A digest that
    moves without the version moving is a digest an opposing expert cannot
    reproduce from the version stamped on the row.

    This is a guard, not a discovery: it was green the moment it was written
    (both values are 1).  Its bite was checked by mutation — setting
    ``[lexicon].version = 2`` in the committed file makes it fail, and the
    working tree was restored afterwards.
    """
    from mainline_domain.canon.lexicon import load_lexicon
    from mainline_domain.canon.version import CANON_VERSION

    assert load_lexicon().version == CANON_VERSION, (
        "domain-lexicon.toml changed without a CANON_VERSION bump (or vice versa); "
        "a lexicon edit moves every digest of every clause containing the compound"
    )


def test_no_builtin_hash_anywhere_in_the_package() -> None:
    """``hash()`` is salted per process; every digest here is evidence."""
    import re

    pattern = re.compile(r"(?<![\w.])hash\s*\(")
    offenders: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if pattern.search(line):
                offenders.append(f"{path}:{number}: {stripped}")
    assert offenders == [], f"builtin hash() is banned in mainline_domain: {offenders}"
